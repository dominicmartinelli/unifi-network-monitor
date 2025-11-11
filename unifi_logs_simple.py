#!/usr/bin/env python3
"""
Simple UniFi Log Retriever - connects directly to local controller.
"""

import requests
import json
import urllib3
from datetime import datetime
import argparse
import sys
import configparser
import os

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LocalUniFiController:
    def __init__(self, host, username, password, port=443, site='default', verify_ssl=False):
        """Connect to local UniFi controller with username/password."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.site = site
        self.verify_ssl = verify_ssl
        self.base_url = f"https://{host}:{port}"

        self.session = requests.Session()
        self.session.verify = verify_ssl

        print(f"\nConnecting to local UniFi controller:")
        print(f"  Host: {self.host}:{self.port}")
        print(f"  Username: {self.username}")
        print(f"  Site: {self.site}")

    def login(self):
        """Authenticate with username/password."""
        # Try UniFi OS login endpoint first (for Dream Machine, Cloud Key Gen2+)
        login_url = f"{self.base_url}/api/auth/login"
        payload = {
            "username": self.username,
            "password": self.password,
            "remember": False
        }

        print(f"\n  Logging in to UniFi OS...")
        print(f"  URL: {login_url}")
        try:
            response = self.session.post(login_url, json=payload)
            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                print(f"  ✓ Successfully logged in!")
                # Store the token if provided
                data = response.json()
                if 'token' in data:
                    print(f"  Token received")
                return True
            elif response.status_code == 401:
                # Try classic UniFi controller endpoint
                print(f"  UniFi OS login failed, trying classic endpoint...")
                login_url = f"{self.base_url}/api/login"
                print(f"  URL: {login_url}")

                response = self.session.post(login_url, json=payload)
                print(f"  Status: {response.status_code}")

                if response.status_code == 200:
                    print(f"  ✓ Successfully logged in!")
                    return True
                else:
                    print(f"  ✗ Login failed: {response.status_code}")
                    print(f"  Response: {response.text}")
                    return False
            else:
                print(f"  ✗ Login failed: {response.status_code}")
                print(f"  Response: {response.text}")
                return False
        except Exception as e:
            print(f"  ✗ Connection error: {e}")
            return False

    def get_events(self, limit=100):
        """Fetch events from local controller."""
        # For UniFi OS, use proxy path to Network controller
        events_url = f"{self.base_url}/proxy/network/api/s/{self.site}/stat/event"
        params = {'_limit': limit, '_sort': '-time'}

        print(f"\nFetching events...")
        print(f"  URL: {events_url}")
        try:
            response = self.session.get(events_url, params=params)
            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                if data.get('meta', {}).get('rc') == 'ok':
                    events = data.get('data', [])
                    print(f"  ✓ Retrieved {len(events)} events")
                    return events
                else:
                    print(f"  ✗ API error: {data}")
                    return []
            else:
                print(f"  ✗ HTTP {response.status_code}: {response.text[:200]}")
                return []
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def get_alarms(self, limit=100):
        """Fetch alarms from local controller."""
        # For UniFi OS, use proxy path to Network controller
        alarms_url = f"{self.base_url}/proxy/network/api/s/{self.site}/stat/alarm"
        params = {'_limit': limit}

        print(f"\nFetching alarms...")
        print(f"  URL: {alarms_url}")
        try:
            response = self.session.get(alarms_url, params=params)
            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                if data.get('meta', {}).get('rc') == 'ok':
                    alarms = data.get('data', [])
                    print(f"  ✓ Retrieved {len(alarms)} alarms")
                    return alarms
                else:
                    print(f"  ✗ API error: {data}")
                    return []
            else:
                print(f"  ✗ HTTP {response.status_code}: {response.text[:200]}")
                return []
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def get_devices(self):
        """Fetch device list and health status."""
        devices_url = f"{self.base_url}/proxy/network/api/s/{self.site}/stat/device"

        print(f"\nFetching devices...")
        print(f"  URL: {devices_url}")
        try:
            response = self.session.get(devices_url)
            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                if data.get('meta', {}).get('rc') == 'ok':
                    devices = data.get('data', [])
                    print(f"  ✓ Retrieved {len(devices)} devices")
                    return devices
                else:
                    print(f"  ✗ API error: {data}")
                    return []
            else:
                print(f"  ✗ HTTP {response.status_code}: {response.text[:200]}")
                return []
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def get_clients(self):
        """Fetch active clients."""
        clients_url = f"{self.base_url}/proxy/network/api/s/{self.site}/stat/sta"

        print(f"\nFetching clients...")
        print(f"  URL: {clients_url}")
        try:
            response = self.session.get(clients_url)
            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                if data.get('meta', {}).get('rc') == 'ok':
                    clients = data.get('data', [])
                    print(f"  ✓ Retrieved {len(clients)} clients")
                    return clients
                else:
                    print(f"  ✗ API error: {data}")
                    return []
            else:
                print(f"  ✗ HTTP {response.status_code}: {response.text[:200]}")
                return []
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def get_site_health(self):
        """Fetch site health and subsystem status."""
        health_url = f"{self.base_url}/proxy/network/api/s/{self.site}/stat/health"

        print(f"\nFetching site health...")
        print(f"  URL: {health_url}")
        try:
            response = self.session.get(health_url)
            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                if data.get('meta', {}).get('rc') == 'ok':
                    health = data.get('data', [])
                    print(f"  ✓ Retrieved {len(health)} subsystems")
                    return health
                else:
                    print(f"  ✗ API error: {data}")
                    return []
            else:
                print(f"  ✗ HTTP {response.status_code}: {response.text[:200]}")
                return []
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def get_system_info(self):
        """Fetch controller system information (CPU, memory, etc)."""
        # Try multiple endpoints to get system info

        # First, try to get it from the controller device itself
        print(f"\nFetching system info...")

        # Get all devices and find the controller/gateway
        devices = self.get_devices()
        controller_info = []

        for device in devices:
            # Look for gateway or controller device types
            device_type = device.get('type', '')
            if device_type in ['udm', 'uxg', 'ugw', 'usg']:
                # Extract system stats from device
                sys_stats = device.get('sys_stats', {})
                system_stats = device.get('system-stats', {})

                # Extract CPU and memory (convert from string if needed)
                cpu_str = system_stats.get('cpu', sys_stats.get('cpu', '0'))
                mem_str = system_stats.get('mem', sys_stats.get('mem', '0'))
                uptime_val = device.get('uptime', 0)

                try:
                    cpu = float(cpu_str) if isinstance(cpu_str, str) else cpu_str
                except (ValueError, TypeError):
                    cpu = 0.0

                try:
                    mem = float(mem_str) if isinstance(mem_str, str) else mem_str
                except (ValueError, TypeError):
                    mem = 0.0

                info = {
                    'hostname': device.get('name', device.get('hostname', 'Controller')),
                    'model': device.get('model', 'Unknown'),
                    'version': device.get('version', 'N/A'),
                    'cpu': cpu,
                    'mem': mem,
                    'uptime': uptime_val,
                }

                # Try to get load averages (they're strings too!)
                loadavg_1_str = sys_stats.get('loadavg_1', '0')
                loadavg_5_str = sys_stats.get('loadavg_5', '0')
                loadavg_15_str = sys_stats.get('loadavg_15', '0')

                try:
                    info['loadavg_1'] = float(loadavg_1_str) if isinstance(loadavg_1_str, str) else loadavg_1_str
                except (ValueError, TypeError):
                    info['loadavg_1'] = 0.0

                try:
                    info['loadavg_5'] = float(loadavg_5_str) if isinstance(loadavg_5_str, str) else loadavg_5_str
                except (ValueError, TypeError):
                    info['loadavg_5'] = 0.0

                try:
                    info['loadavg_15'] = float(loadavg_15_str) if isinstance(loadavg_15_str, str) else loadavg_15_str
                except (ValueError, TypeError):
                    info['loadavg_15'] = 0.0

                # Get temperatures if available
                temps = []
                if 'temperatures' in device:
                    temps = device['temperatures']
                elif 'temperature' in sys_stats:
                    temps = [{'name': 'CPU', 'value': sys_stats['temperature']}]
                info['temperatures'] = temps

                controller_info.append(info)
                print(f"  ✓ Retrieved system info from {info['hostname']}")

        # If no controller device found, try the sysinfo endpoint
        if not controller_info:
            sysinfo_url = f"{self.base_url}/proxy/network/api/s/{self.site}/stat/sysinfo"
            try:
                response = self.session.get(sysinfo_url)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('meta', {}).get('rc') == 'ok':
                        controller_info = data.get('data', [])
                        if controller_info:
                            print(f"  ✓ Retrieved system info from sysinfo endpoint")
            except Exception as e:
                print(f"  ✗ Error from sysinfo endpoint: {e}")

        if not controller_info:
            print(f"  ⚠ No system info available")

        return controller_info

    def get_port_stats(self):
        """Fetch port statistics for all devices."""
        # Get devices with port table included
        devices_url = f"{self.base_url}/proxy/network/api/s/{self.site}/stat/device"

        print(f"\nFetching port statistics...")
        print(f"  URL: {devices_url}")
        try:
            response = self.session.get(devices_url)
            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                if data.get('meta', {}).get('rc') == 'ok':
                    devices = data.get('data', [])
                    print(f"  ✓ Retrieved port stats for {len(devices)} devices")
                    return devices
                else:
                    print(f"  ✗ API error: {data}")
                    return []
            else:
                print(f"  ✗ HTTP {response.status_code}: {response.text[:200]}")
                return []
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def get_wan_stats(self):
        """Fetch WAN statistics."""
        # WAN stats are typically part of device stats for USG/UDM
        devices_url = f"{self.base_url}/proxy/network/api/s/{self.site}/stat/device"

        print(f"\nFetching WAN statistics...")
        try:
            response = self.session.get(devices_url)

            if response.status_code == 200:
                data = response.json()
                if data.get('meta', {}).get('rc') == 'ok':
                    devices = data.get('data', [])
                    # Filter for gateway devices that have WAN interfaces
                    # Check for devices with gateway types AND wan1 interface
                    gateways = [d for d in devices
                               if d.get('type') in ['ugw', 'udm', 'uxg', 'usg']
                               and (d.get('wan1') or d.get('wan2'))]
                    print(f"  ✓ Retrieved WAN stats for {len(gateways)} gateway(s)")
                    return gateways
                else:
                    return []
            else:
                return []
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def get_network_stats(self):
        """Fetch network statistics (firewall, NAT, VPN)."""
        # Try to get statistics from the device
        stats_url = f"{self.base_url}/proxy/network/api/s/{self.site}/stat/sta"

        print(f"\nFetching network statistics...")
        try:
            response = self.session.get(stats_url)

            if response.status_code == 200:
                data = response.json()
                if data.get('meta', {}).get('rc') == 'ok':
                    print(f"  ✓ Retrieved network statistics")
                    return data.get('data', [])
            return []
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def logout(self):
        """Logout from controller."""
        logout_url = f"{self.base_url}/api/logout"
        try:
            self.session.post(logout_url)
            print("\n✓ Logged out")
        except:
            pass

    def format_event(self, event):
        """Format an event for display."""
        timestamp_ms = event.get('time', 0)
        if timestamp_ms:
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000)
        else:
            timestamp = 'Unknown time'

        event_type = event.get('key', 'unknown')
        msg = event.get('msg', '')

        return f"[{timestamp}] {event_type}: {msg}"

    def format_alarm(self, alarm):
        """Format an alarm for display."""
        timestamp_ms = alarm.get('datetime', 0)
        try:
            if timestamp_ms and isinstance(timestamp_ms, (int, float)):
                timestamp = datetime.fromtimestamp(timestamp_ms / 1000)
            else:
                timestamp = 'Unknown time'
        except:
            timestamp = 'Unknown time'

        alarm_type = alarm.get('key', 'unknown')
        msg = alarm.get('msg', '')

        return f"[{timestamp}] ALARM - {alarm_type}: {msg}"


def load_config(config_file='.config'):
    """Load configuration from config file."""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), config_file)

    if not os.path.exists(config_path):
        return {}

    try:
        config.read(config_path)
        if 'unifi' in config:
            cfg = config['unifi']
            return {
                'local_host': cfg.get('local_host'),
                'local_port': cfg.getint('local_port', 443),
                'local_username': cfg.get('local_username'),
                'local_password': cfg.get('local_password'),
                'site': cfg.get('site', 'default'),
                'verify_ssl_local': cfg.getboolean('verify_ssl_local', False)
            }
    except Exception as e:
        print(f"Warning: Error loading config file: {e}")

    return {}


def main():
    # Load config
    config = load_config()

    parser = argparse.ArgumentParser(
        description='Pull logs from local UniFi Controller'
    )
    parser.add_argument('--host', help='Controller hostname or IP')
    parser.add_argument('--username', help='Admin username')
    parser.add_argument('--password', help='Admin password')
    parser.add_argument('--port', type=int, help='Controller port (default: 443)')
    parser.add_argument('--site', help='Site name (default: default)')
    parser.add_argument('--limit', type=int, default=100, help='Number of logs to retrieve (default: 100)')
    parser.add_argument('--type', choices=['events', 'alarms', 'both'], default='both',
                       help='Type of logs to retrieve (default: both)')
    parser.add_argument('--output', help='Output file (JSON format)')

    args = parser.parse_args()

    # Use command-line args or config
    host = args.host or config.get('local_host')
    username = args.username or config.get('local_username')
    password = args.password or config.get('local_password')
    port = args.port or config.get('local_port', 443)
    site = args.site or config.get('site', 'default')
    verify_ssl = config.get('verify_ssl_local', False)

    # Validate
    if not host:
        parser.error('--host is required (or set local_host in .config)')
    if not username or not password:
        parser.error('--username and --password are required (or set in .config)')

    # Connect to controller
    controller = LocalUniFiController(
        host=host,
        username=username,
        password=password,
        port=port,
        site=site,
        verify_ssl=verify_ssl
    )

    # Login
    if not controller.login():
        sys.exit(1)

    try:
        results = {}

        # Fetch events
        if args.type in ['events', 'both']:
            events = controller.get_events(limit=args.limit)
            results['events'] = events

            if events:
                print("\nRecent Events:")
                print("-" * 80)
                for event in events[:10]:
                    print(controller.format_event(event))
                if len(events) > 10:
                    print(f"... and {len(events) - 10} more events")

        # Fetch alarms
        if args.type in ['alarms', 'both']:
            alarms = controller.get_alarms(limit=args.limit)
            results['alarms'] = alarms

            if alarms:
                print("\nRecent Alarms:")
                print("-" * 80)
                for alarm in alarms[:10]:
                    print(controller.format_alarm(alarm))
                if len(alarms) > 10:
                    print(f"... and {len(alarms) - 10} more alarms")

        # Save to file if requested
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n✓ Logs saved to {args.output}")

    finally:
        controller.logout()


if __name__ == '__main__':
    main()
