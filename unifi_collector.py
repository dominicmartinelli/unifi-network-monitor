#!/usr/bin/env python3
"""
UniFi Network Statistics Collector
Runs in the background and collects network statistics to SQLite database.
"""

import sqlite3
import time
import signal
import sys
from datetime import datetime
from unifi_logs_simple import LocalUniFiController, load_config


class UniFiCollector:
    def __init__(self, db_path='unifi_stats.db', interval=30):
        """
        Initialize the collector.

        Args:
            db_path: Path to SQLite database file
            interval: Collection interval in seconds (default: 30)
        """
        self.db_path = db_path
        self.interval = interval
        self.running = True
        self.controller = None

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        # Initialize database
        self.init_database()

    def signal_handler(self, sig, frame):
        """Handle shutdown signals gracefully."""
        print(f"\nReceived signal {sig}, shutting down gracefully...")
        self.running = False

    def init_database(self):
        """Create database tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Client bandwidth table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_bandwidth (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                mac TEXT NOT NULL,
                hostname TEXT,
                ip TEXT,
                tx_bytes INTEGER DEFAULT 0,
                rx_bytes INTEGER DEFAULT 0,
                wired_tx_bytes INTEGER DEFAULT 0,
                wired_rx_bytes INTEGER DEFAULT 0,
                tx_rate REAL DEFAULT 0,
                rx_rate REAL DEFAULT 0,
                is_wired INTEGER DEFAULT 0
            )
        ''')

        # WAN statistics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wan_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                wan_ip TEXT,
                tx_bytes INTEGER DEFAULT 0,
                rx_bytes INTEGER DEFAULT 0,
                tx_rate REAL DEFAULT 0,
                rx_rate REAL DEFAULT 0,
                latency INTEGER DEFAULT 0,
                clients INTEGER DEFAULT 0
            )
        ''')

        # Device health table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS device_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                device_name TEXT NOT NULL,
                device_mac TEXT NOT NULL,
                device_type TEXT,
                state INTEGER,
                cpu_usage REAL,
                mem_usage REAL,
                uptime INTEGER,
                temperature REAL
            )
        ''')

        # Create indexes for faster queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_timestamp ON client_bandwidth(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_mac ON client_bandwidth(mac)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_wan_timestamp ON wan_stats(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_device_timestamp ON device_health(timestamp)')

        conn.commit()
        conn.close()

        print(f"Database initialized: {self.db_path}")

    def connect_to_controller(self):
        """Connect to UniFi controller."""
        try:
            config = load_config()

            # Handle verify_ssl as either bool or string
            verify_ssl_value = config.get('verify_ssl_local', False)
            if isinstance(verify_ssl_value, bool):
                verify_ssl = verify_ssl_value
            else:
                verify_ssl = str(verify_ssl_value).lower() == 'true'

            self.controller = LocalUniFiController(
                host=config.get('local_host'),
                username=config.get('local_username'),
                password=config.get('local_password'),
                port=int(config.get('local_port', 443)),
                site=config.get('site', 'default'),
                verify_ssl=verify_ssl
            )

            if self.controller.login():
                print(f"Connected to UniFi controller at {config.get('local_host')}")
                return True
            else:
                print("Failed to login to UniFi controller")
                return False

        except Exception as e:
            print(f"Error connecting to controller: {e}")
            return False

    def collect_data(self):
        """Collect data from UniFi controller and store in database."""
        if not self.controller:
            if not self.connect_to_controller():
                return

        timestamp = int(time.time())

        try:
            # Fetch data from controller
            clients = self.controller.get_clients()
            wan_stats = self.controller.get_wan_stats()
            devices = self.controller.get_devices()

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Store client bandwidth data
            for client in clients:
                mac = client.get('mac')
                if not mac:
                    continue

                cursor.execute('''
                    INSERT INTO client_bandwidth
                    (timestamp, mac, hostname, ip, tx_bytes, rx_bytes,
                     wired_tx_bytes, wired_rx_bytes, tx_rate, rx_rate, is_wired)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    timestamp,
                    mac,
                    client.get('hostname', client.get('name', '')),
                    client.get('ip', ''),
                    client.get('tx_bytes', 0),
                    client.get('rx_bytes', 0),
                    client.get('wired_tx_bytes', 0),
                    client.get('wired_rx_bytes', 0),
                    client.get('tx_bytes-r', 0) + client.get('wired-tx_bytes-r', 0),
                    client.get('rx_bytes-r', 0) + client.get('wired-rx_bytes-r', 0),
                    1 if client.get('is_wired') else 0
                ))

            # Store WAN stats
            if wan_stats:
                gateway = wan_stats[0]
                uplink = gateway.get('uplink', {})

                cursor.execute('''
                    INSERT INTO wan_stats
                    (timestamp, wan_ip, tx_bytes, rx_bytes, tx_rate, rx_rate, latency, clients)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    timestamp,
                    gateway.get('wan1', {}).get('ip', uplink.get('ip', 'N/A')),
                    uplink.get('tx_bytes', gateway.get('tx_bytes', 0)),
                    uplink.get('rx_bytes', gateway.get('rx_bytes', 0)),
                    uplink.get('tx_bytes-r', gateway.get('tx_bytes-r', 0)),
                    uplink.get('rx_bytes-r', gateway.get('rx_bytes-r', 0)),
                    uplink.get('latency', gateway.get('latency', 0)),
                    gateway.get('num_sta', 0)
                ))

            # Store device health
            for device in devices:
                sys_stats = device.get('sys_stats', {}) or device.get('system-stats', {})

                cursor.execute('''
                    INSERT INTO device_health
                    (timestamp, device_name, device_mac, device_type, state,
                     cpu_usage, mem_usage, uptime, temperature)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    timestamp,
                    device.get('name', 'Unknown'),
                    device.get('mac', ''),
                    device.get('type', ''),
                    device.get('state', 0),
                    sys_stats.get('cpu', 0) if sys_stats else 0,
                    sys_stats.get('mem', 0) if sys_stats else 0,
                    device.get('uptime', 0),
                    device.get('general_temperature', 0)
                ))

            conn.commit()
            conn.close()

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Collected: {len(clients)} clients, {len(devices)} devices")

        except Exception as e:
            print(f"Error collecting data: {e}")
            # Try to reconnect on next cycle
            self.controller = None

    def cleanup_old_data(self, days=7):
        """Remove data older than specified days."""
        cutoff = int(time.time()) - (days * 24 * 60 * 60)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM client_bandwidth WHERE timestamp < ?', (cutoff,))
        cursor.execute('DELETE FROM wan_stats WHERE timestamp < ?', (cutoff,))
        cursor.execute('DELETE FROM device_health WHERE timestamp < ?', (cutoff,))

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted > 0:
            print(f"Cleaned up {deleted} old records (older than {days} days)")

    def run(self):
        """Main collection loop."""
        print(f"UniFi Statistics Collector started")
        print(f"Collection interval: {self.interval} seconds")
        print(f"Database: {self.db_path}")
        print("Press Ctrl+C to stop\n")

        cleanup_counter = 0

        while self.running:
            self.collect_data()

            # Cleanup old data once per day (every 2880 cycles at 30s interval)
            cleanup_counter += 1
            if cleanup_counter >= 2880:
                self.cleanup_old_data(days=7)
                cleanup_counter = 0

            # Sleep until next collection
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

        # Logout from controller
        if self.controller:
            try:
                self.controller.logout()
            except:
                pass

        print("\nCollector stopped.")


if __name__ == '__main__':
    # Parse command line arguments
    import argparse

    parser = argparse.ArgumentParser(description='UniFi Network Statistics Collector')
    parser.add_argument('-d', '--database', default='unifi_stats.db',
                        help='Path to SQLite database file (default: unifi_stats.db)')
    parser.add_argument('-i', '--interval', type=int, default=30,
                        help='Collection interval in seconds (default: 30)')

    args = parser.parse_args()

    # Create and run collector
    collector = UniFiCollector(db_path=args.database, interval=args.interval)
    collector.run()
