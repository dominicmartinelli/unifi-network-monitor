#!/usr/bin/env python3
"""
UniFi Log Viewer - Interactive TUI using curses
"""

import curses
import threading
import time
import sqlite3
import os
from datetime import datetime, timedelta
from unifi_logs_simple import LocalUniFiController, load_config


class UniFiTUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.current_view = "menu"
        self.selected_index = 0
        self.scroll_offset = 0
        self.events = []
        self.alarms = []
        self.devices = []
        self.clients = []
        self.site_health = []
        self.system_info = []
        self.wan_stats = []
        self.port_stats = []
        self.last_refresh = None
        self.controller = None
        self.running = True
        self.status_message = "Loading..."
        self.filter_text = ""
        self.filter_mode = False

        # Bandwidth tracking
        self.bandwidth_time_mode = "realtime"  # realtime, 10min, 1hour
        self.bandwidth_history = []  # List of (timestamp, client_bandwidth_dict)

        # SQLite database path (if using background collector)
        self.db_path = 'unifi_stats.db'
        self.use_database = os.path.exists(self.db_path)

        # Initialize curses
        curses.curs_set(0)  # Hide cursor
        stdscr.clear()
        stdscr.refresh()

        # Initialize colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)    # Title
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)   # Success
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)     # Error/Alarm
        curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Warning
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLUE)    # Selected
        curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # Device

    def connect_controller(self):
        """Connect to UniFi controller."""
        config = load_config()

        self.status_message = "Connecting to controller..."
        self.draw()

        try:
            self.controller = LocalUniFiController(
                host=config.get('local_host'),
                username=config.get('local_username'),
                password=config.get('local_password'),
                port=config.get('local_port', 443),
                site=config.get('site', 'default'),
                verify_ssl=config.get('verify_ssl_local', False)
            )

            if self.controller.login():
                self.status_message = "Connected to controller"
                self.fetch_data()
            else:
                self.status_message = "Failed to connect"
        except Exception as e:
            self.status_message = f"Error: {str(e)}"

    def fetch_data(self):
        """Fetch all data from controller."""
        if not self.controller:
            return

        self.status_message = "Fetching data..."
        self.draw()

        try:
            self.events = self.controller.get_events(limit=200)
            self.alarms = self.controller.get_alarms(limit=100)
            self.devices = self.controller.get_devices()
            self.clients = self.controller.get_clients()
            self.site_health = self.controller.get_site_health()
            self.system_info = self.controller.get_system_info()
            self.wan_stats = self.controller.get_wan_stats()
            self.port_stats = self.controller.get_port_stats()
            self.last_refresh = datetime.now()

            # Store bandwidth snapshot for historical tracking
            self._store_bandwidth_snapshot()

            self.status_message = f"Last refresh: {self.last_refresh.strftime('%H:%M:%S')}"
        except Exception as e:
            self.status_message = f"Error fetching data: {str(e)}"

    def _store_bandwidth_snapshot(self):
        """Store current bandwidth data with timestamp."""
        current_time = time.time()

        # Create snapshot of current client bandwidth
        snapshot = {}
        for client in self.clients:
            mac = client.get('mac')
            if mac:
                snapshot[mac] = {
                    'hostname': client.get('hostname', client.get('name', '')),
                    'ip': client.get('ip', ''),
                    'tx_bytes': client.get('tx_bytes', 0),
                    'rx_bytes': client.get('rx_bytes', 0),
                    'wired_tx_bytes': client.get('wired_tx_bytes', 0),
                    'wired_rx_bytes': client.get('wired_rx_bytes', 0),
                }

        # Add snapshot to history
        self.bandwidth_history.append((current_time, snapshot))

        # Clean up old snapshots (keep last 1 hour)
        one_hour_ago = current_time - 3600
        self.bandwidth_history = [(ts, data) for ts, data in self.bandwidth_history if ts >= one_hour_ago]

    def _get_bandwidth_for_period(self, client_mac):
        """Calculate total bandwidth for a client over the selected time period."""
        if self.bandwidth_time_mode == "realtime":
            # Return current rates
            client = next((c for c in self.clients if c.get('mac') == client_mac), None)
            if client:
                tx = client.get('tx_bytes-r', 0) + client.get('wired-tx_bytes-r', 0)
                rx = client.get('rx_bytes-r', 0) + client.get('wired-rx_bytes-r', 0)
                return tx, rx
            return 0, 0

        # Calculate historical bandwidth
        current_time = time.time()
        if self.bandwidth_time_mode == "10min":
            period_start = current_time - 600  # 10 minutes
        else:  # 1hour
            period_start = current_time - 3600  # 1 hour

        # Find first and last snapshot in period
        period_snapshots = [(ts, data) for ts, data in self.bandwidth_history if ts >= period_start]

        if len(period_snapshots) < 2:
            return 0, 0

        first_time, first_data = period_snapshots[0]
        last_time, last_data = period_snapshots[-1]

        if client_mac not in first_data or client_mac not in last_data:
            return 0, 0

        # Calculate difference in bytes
        duration = last_time - first_time
        if duration == 0:
            return 0, 0

        first = first_data[client_mac]
        last = last_data[client_mac]

        tx_diff = (last['tx_bytes'] - first['tx_bytes']) + (last['wired_tx_bytes'] - first['wired_tx_bytes'])
        rx_diff = (last['rx_bytes'] - first['rx_bytes']) + (last['wired_rx_bytes'] - first['wired_rx_bytes'])

        # Convert to bytes per second (average rate over period)
        tx_rate = tx_diff / duration if duration > 0 else 0
        rx_rate = rx_diff / duration if duration > 0 else 0

        return max(0, tx_rate), max(0, rx_rate)

    def _get_historical_wan_stats(self, hours=24, max_points=50):
        """Get WAN statistics from SQLite database for sparklines."""
        if not self.use_database:
            return []

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get data points from last N hours
            cutoff_time = int(time.time()) - (hours * 3600)

            cursor.execute('''
                SELECT timestamp, tx_rate, rx_rate, latency
                FROM wan_stats
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            ''', (cutoff_time,))

            rows = cursor.fetchall()
            conn.close()

            # Downsample if we have too many points
            if len(rows) > max_points:
                step = len(rows) // max_points
                rows = rows[::step]

            return rows
        except Exception as e:
            return []

    def _get_historical_client_bandwidth(self, mac, hours=24, max_points=50):
        """Get client bandwidth history from SQLite database."""
        if not self.use_database:
            return []

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cutoff_time = int(time.time()) - (hours * 3600)

            cursor.execute('''
                SELECT timestamp, tx_rate, rx_rate
                FROM client_bandwidth
                WHERE mac = ? AND timestamp >= ?
                ORDER BY timestamp ASC
            ''', (mac, cutoff_time))

            rows = cursor.fetchall()
            conn.close()

            # Downsample if needed
            if len(rows) > max_points:
                step = len(rows) // max_points
                rows = rows[::step]

            return rows
        except Exception as e:
            return []

    def _get_historical_device_health(self, device_mac, hours=24, max_points=50):
        """Get device health history from SQLite database."""
        if not self.use_database:
            return []

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cutoff_time = int(time.time()) - (hours * 3600)

            cursor.execute('''
                SELECT timestamp, cpu_usage, mem_usage, temperature
                FROM device_health
                WHERE device_mac = ? AND timestamp >= ?
                ORDER BY timestamp ASC
            ''', (device_mac, cutoff_time))

            rows = cursor.fetchall()
            conn.close()

            # Downsample if needed
            if len(rows) > max_points:
                step = len(rows) // max_points
                rows = rows[::step]

            return rows
        except Exception as e:
            return []

    def _create_sparkline(self, values, width=20, height=3):
        """
        Create ASCII sparkline from values.

        Returns a list of strings representing the sparkline.
        Uses block characters for better resolution.
        """
        if not values or len(values) < 2:
            return [' ' * width for _ in range(height)]

        # Blocks for different heights (8 levels)
        blocks = [' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']

        # Normalize values to fit in width
        if len(values) > width:
            step = len(values) / width
            normalized = []
            for i in range(width):
                idx = int(i * step)
                normalized.append(values[idx])
            values = normalized
        elif len(values) < width:
            # Pad with the last value
            values = values + [values[-1]] * (width - len(values))

        # Find min and max
        min_val = min(values)
        max_val = max(values)

        if max_val == min_val:
            # All values are the same
            mid_block = blocks[4]
            return [' ' * width for _ in range(height - 1)] + [mid_block * width]

        # Scale values to block height
        scaled = []
        for v in values:
            normalized = (v - min_val) / (max_val - min_val)
            block_idx = int(normalized * (len(blocks) - 1))
            scaled.append(blocks[block_idx])

        # For single-line sparkline, just return one line
        if height == 1:
            return [''.join(scaled)]

        # For multi-line, distribute vertically
        lines = []
        levels_per_line = (len(blocks) - 1) / height

        for line_idx in range(height):
            line_min = int(line_idx * levels_per_line)
            line_max = int((line_idx + 1) * levels_per_line)
            line_chars = []

            for v in values:
                normalized = (v - min_val) / (max_val - min_val)
                level = int(normalized * (len(blocks) - 1))

                # Show block if level falls in this line's range
                if line_min <= level < line_max:
                    line_chars.append(blocks[level - line_min + 1])
                elif level >= line_max:
                    line_chars.append(blocks[-1])
                else:
                    line_chars.append(' ')

            lines.append(''.join(line_chars))

        return list(reversed(lines))  # Top to bottom

    def draw_menu(self):
        """Draw main menu."""
        height, width = self.stdscr.getmaxyx()

        # Title
        title = "UniFi Network Monitor"
        self.stdscr.addstr(1, (width - len(title)) // 2, title,
                          curses.color_pair(1) | curses.A_BOLD)

        # Menu options - organized into sections
        # Count security alarms
        security_count = sum(1 for alarm in self.alarms if self._is_security_alarm(alarm.get('key', '')))

        menu_items = [
            ("0", "Dashboard", "(At-a-Glance Overview)"),
            ("", "─" * 30, ""),  # Divider
            ("1", "Site Status & Health", f"({len(self.site_health)} subsystems)"),
            ("2", "Controller Resources", "(CPU, Memory, Load)"),
            ("3", "WAN & Network Stats", "(Throughput, Latency)"),
            ("", "─" * 30, ""),  # Divider
            ("4", "Events Log", f"({len(self.events)} events)"),
            ("5", "Alarms (Recent)", "(Past 3 days)"),
            ("6", "Security Alerts", f"({security_count} total)"),
            ("", "─" * 30, ""),  # Divider
            ("7", "Device Inventory", f"({len(self.devices)} devices)"),
            ("8", "Client Activity", f"({len(self.clients)} clients)"),
            ("9", "Top Bandwidth Users", "(Real-time Traffic)"),
            ("", "─" * 30, ""),  # Divider
            ("R", "Refresh Data", ""),
            ("Q", "Quit", "")
        ]

        start_y = 3
        menu_index = 0
        for i, (key, label, info) in enumerate(menu_items):
            y = start_y + i

            # Skip highlighting for dividers
            if not key:
                self.stdscr.addstr(y, (width - len(label)) // 2, label, curses.A_DIM)
                continue

            # Highlight selected item
            if menu_index == self.selected_index:
                attr = curses.color_pair(5) | curses.A_BOLD
            else:
                attr = curses.A_NORMAL

            menu_text = f"[{key}] {label}"
            if info:
                menu_text += f" {info}"

            x = (width - len(menu_text)) // 2
            try:
                self.stdscr.addstr(y, x, menu_text, attr)
            except:
                pass

            menu_index += 1

    def draw_events(self):
        """Draw events list."""
        height, width = self.stdscr.getmaxyx()

        # Header
        header = f"Events Log ({len(self.events)} total)"
        self.stdscr.addstr(1, 2, header, curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        # Filter info
        if self.filter_text:
            filter_info = f"Filter: '{self.filter_text}' (F to clear)"
            self.stdscr.addstr(3, 2, filter_info, curses.color_pair(4))

        # Events list
        list_height = height - (7 if self.filter_text else 6)
        start_y = 4 if self.filter_text else 3

        # Apply filter
        filtered_events = self.events
        if self.filter_text:
            filtered_events = [e for e in self.events
                             if self.filter_text.lower() in str(e.get('key', '')).lower()
                             or self.filter_text.lower() in str(e.get('msg', '')).lower()]

        for i in range(list_height):
            idx = i + self.scroll_offset
            if idx >= len(filtered_events):
                break

            event = filtered_events[idx]

            # Format event
            timestamp_ms = event.get('time', 0)
            if timestamp_ms:
                timestamp = datetime.fromtimestamp(timestamp_ms / 1000).strftime('%H:%M:%S')
            else:
                timestamp = '??:??:??'

            event_type = event.get('key', 'unknown')
            msg = event.get('msg', '')[:width - 20]

            line = f"{timestamp} {event_type[:15]:<15} {msg}"

            # Highlight selected
            if i == self.selected_index:
                attr = curses.color_pair(5)
            else:
                attr = curses.A_NORMAL

            try:
                self.stdscr.addstr(start_y + i, 2, line[:width - 4], attr)
            except:
                pass

        # Scrollbar indicator
        if len(self.events) > list_height:
            scroll_pct = self.scroll_offset / (len(self.events) - list_height)
            scroll_pos = int(scroll_pct * list_height)
            try:
                self.stdscr.addstr(start_y + scroll_pos, width - 2, "█", curses.color_pair(4))
            except:
                pass

    def _is_security_alarm(self, alarm_key):
        """Check if alarm is security-related."""
        SECURITY_ALARM_TYPES = {
            # Authentication & Access
            'EVT_AD_LOGIN_FAIL', 'EVT_ADMIN_LOGIN_FAIL',
            'unauthorized_access', 'EVT_WG_Unauthorized',
            # Intrusion Detection
            'EVT_IPS_IpsAlert', 'EVT_IPS_IdsAlert',
            'EVT_GW_Firewall',
            # Rogue Devices
            'rogue_ap', 'EVT_SW_Rogue', 'EVT_AP_Rogue',
            # Suspicious Activity
            'EVT_AP_Detected_Rogue_AP', 'EVT_SW_Possible_Rogue'
        }
        return any(sec_type in alarm_key for sec_type in SECURITY_ALARM_TYPES)

    def _get_alarm_time(self, alarm):
        """Extract timestamp from alarm."""
        for field in ['datetime', 'time', 'timestamp', 'epoch']:
            timestamp_ms = alarm.get(field)
            if timestamp_ms:
                try:
                    if isinstance(timestamp_ms, str):
                        # Skip ISO format strings like "2025-10-28T04:27:51Z"
                        if 'T' in timestamp_ms or '-' in timestamp_ms:
                            continue
                        timestamp_ms = int(timestamp_ms)
                    if isinstance(timestamp_ms, (int, float)):
                        # Convert to seconds
                        if timestamp_ms > 10000000000:
                            return timestamp_ms / 1000
                        else:
                            return timestamp_ms
                except:
                    continue
        return None

    def draw_alarms(self):
        """Draw recent alarms list (past 3 days only)."""
        height, width = self.stdscr.getmaxyx()

        # Filter for recent alarms only
        three_days_ago = time.time() - (3 * 24 * 60 * 60)
        recent_alarms = []

        for alarm in self.alarms:
            alarm_time = self._get_alarm_time(alarm)
            if alarm_time and alarm_time >= three_days_ago:
                recent_alarms.append(alarm)

        # Header
        header = f"Recent Alarms (Past 3 Days) - {len(recent_alarms)} total"
        self.stdscr.addstr(1, 2, header, curses.color_pair(3) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        # Show message if no recent alarms
        if len(recent_alarms) == 0:
            self.stdscr.addstr(4, 2, "No alarms in the past 3 days", curses.color_pair(2))
            return

        # Alarms list
        list_height = height - 6
        start_y = 3

        for i in range(list_height):
            idx = i + self.scroll_offset
            if idx >= len(recent_alarms):
                break

            alarm = recent_alarms[idx]
            timestamp, alarm_type, msg = self._format_alarm(alarm, width)
            line = f"{timestamp} {alarm_type[:15]:<15} {msg}"

            attr = curses.color_pair(5) if i == self.selected_index else curses.color_pair(3)
            try:
                self.stdscr.addstr(start_y + i, 2, line[:width - 4], attr)
            except:
                pass

    def draw_security_alerts(self):
        """Draw security alerts (all time)."""
        height, width = self.stdscr.getmaxyx()

        # Filter for security alarms
        security_alarms = [alarm for alarm in self.alarms if self._is_security_alarm(alarm.get('key', ''))]

        # Header
        header = f"Security Alerts (All Time) - {len(security_alarms)} total"
        self.stdscr.addstr(1, 2, header, curses.color_pair(3) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        # Show message if no security alarms
        if len(security_alarms) == 0:
            self.stdscr.addstr(4, 2, "No security alerts found", curses.color_pair(2))
            return

        # Alarms list
        list_height = height - 6
        start_y = 3

        for i in range(list_height):
            idx = i + self.scroll_offset
            if idx >= len(security_alarms):
                break

            alarm = security_alarms[idx]
            timestamp, alarm_type, msg = self._format_alarm(alarm, width)
            line = f"{timestamp} {alarm_type[:15]:<15} {msg}"

            # Highlight selected, otherwise bold red for security
            if i == self.selected_index:
                attr = curses.color_pair(5)
            else:
                attr = curses.color_pair(3) | curses.A_BOLD

            try:
                self.stdscr.addstr(start_y + i, 2, line[:width - 4], attr)
            except:
                pass

    def _format_alarm(self, alarm, width):
        """Helper to format alarm data."""
        timestamp = '??:??:??'
        for field in ['datetime', 'time', 'timestamp', 'epoch']:
            timestamp_ms = alarm.get(field)
            if timestamp_ms:
                try:
                    if isinstance(timestamp_ms, str):
                        timestamp_ms = int(timestamp_ms)
                    if isinstance(timestamp_ms, (int, float)):
                        if timestamp_ms > 10000000000:
                            ts = datetime.fromtimestamp(timestamp_ms / 1000)
                        else:
                            ts = datetime.fromtimestamp(timestamp_ms)
                        timestamp = ts.strftime('%Y-%m-%d %H:%M:%S')
                        break
                except:
                    continue

        alarm_type = alarm.get('key', 'unknown')
        msg = alarm.get('msg', '')[:width - 35]

        return timestamp, alarm_type, msg

    def draw_device_inventory(self):
        """Draw enhanced device inventory with MACs, IPs, and adoption state."""
        height, width = self.stdscr.getmaxyx()

        # Header
        header = f"Device Inventory ({len(self.devices)} total)"
        self.stdscr.addstr(1, 2, header, curses.color_pair(6) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        # Column headers
        col_header = f"{'Name':<18} {'Model':<12} {'IP':<15} {'MAC':<17} {'Status':<10} {'CPU%':<6} {'Mem%':<6}"
        self.stdscr.addstr(3, 2, col_header, curses.A_BOLD | curses.A_UNDERLINE)

        # Devices list - reduce height if showing detail panel
        detail_height = 10 if self.use_database and self.devices else 0
        list_height = height - 7 - detail_height
        start_y = 4

        for i in range(list_height):
            idx = i + self.scroll_offset
            if idx >= len(self.devices):
                break

            device = self.devices[idx]

            # Format device info
            name = device.get('name', 'Unknown')[:18]
            model = device.get('model', 'Unknown')[:12]
            ip = device.get('ip', 'N/A')[:15]
            mac = device.get('mac', 'N/A')[:17]
            state = device.get('state', 0)
            adopted = device.get('adopted', False)

            # Get system stats
            sys_stats = device.get('sys_stats', {}) or device.get('system-stats', {})
            cpu_raw = sys_stats.get('cpu', 0) if sys_stats else 0
            mem_raw = sys_stats.get('mem', 0) if sys_stats else 0

            # Convert to float, handling string values
            try:
                cpu = float(cpu_raw) if cpu_raw else 0
                cpu_str = f"{cpu:>4.0f}%" if cpu else " N/A"
            except (ValueError, TypeError):
                cpu = 0
                cpu_str = " N/A"

            try:
                mem = float(mem_raw) if mem_raw else 0
                mem_str = f"{mem:>4.0f}%" if mem else " N/A"
            except (ValueError, TypeError):
                mem = 0
                mem_str = " N/A"

            # Status indicator
            if state == 1 and adopted:
                status = "✓ Online"
                status_color = curses.color_pair(2)
            elif adopted:
                status = "✗ Offline"
                status_color = curses.color_pair(3)
            else:
                status = "⚠ Pending"
                status_color = curses.color_pair(4)

            line = f"{name:<18} {model:<12} {ip:<15} {mac:<17} {status:<10} {cpu_str:<6} {mem_str:<6}"

            # Highlight selected
            if i == self.selected_index:
                attr = curses.color_pair(5)
            else:
                attr = status_color

            try:
                self.stdscr.addstr(start_y + i, 2, line[:width - 4], attr)
            except:
                pass

        # Show detail panel for selected device with sparklines
        if self.use_database and self.devices and self.selected_index < len(self.devices):
            selected_device = self.devices[min(self.selected_index + self.scroll_offset, len(self.devices) - 1)]
            device_mac = selected_device.get('mac')

            if device_mac:
                detail_y = start_y + list_height + 1
                self.stdscr.addstr(detail_y, 2, "═" * (width - 4), curses.A_DIM)
                detail_y += 1

                device_name = selected_device.get('name', 'Unknown')
                self.stdscr.addstr(detail_y, 2, f"24h History: {device_name}", curses.color_pair(1) | curses.A_BOLD)
                detail_y += 1

                device_history = self._get_historical_device_health(device_mac, hours=24, max_points=50)
                if device_history and len(device_history) > 2:
                    # CPU sparkline
                    cpu_values = [row[1] for row in device_history if row[1] is not None]
                    if cpu_values:
                        sparkline_cpu = self._create_sparkline(cpu_values, width=min(50, width - 20), height=1)
                        avg_cpu = sum(cpu_values) / len(cpu_values)
                        max_cpu = max(cpu_values)
                        self.stdscr.addstr(detail_y, 4, f"CPU: {sparkline_cpu[0]}  Avg: {avg_cpu:.0f}%  Peak: {max_cpu:.0f}%",
                                         curses.color_pair(2) if max_cpu < 70 else curses.color_pair(4))
                        detail_y += 1

                    # Memory sparkline
                    mem_values = [row[2] for row in device_history if row[2] is not None]
                    if mem_values:
                        sparkline_mem = self._create_sparkline(mem_values, width=min(50, width - 20), height=1)
                        avg_mem = sum(mem_values) / len(mem_values)
                        max_mem = max(mem_values)
                        self.stdscr.addstr(detail_y, 4, f"MEM: {sparkline_mem[0]}  Avg: {avg_mem:.0f}%  Peak: {max_mem:.0f}%",
                                         curses.color_pair(2) if max_mem < 80 else curses.color_pair(4))
                        detail_y += 1

                    # Temperature sparkline
                    temp_values = [row[3] for row in device_history if row[3] is not None and row[3] > 0]
                    if temp_values:
                        sparkline_temp = self._create_sparkline(temp_values, width=min(50, width - 20), height=1)
                        avg_temp = sum(temp_values) / len(temp_values)
                        max_temp = max(temp_values)
                        self.stdscr.addstr(detail_y, 4, f"TMP: {sparkline_temp[0]}  Avg: {avg_temp:.0f}°C  Peak: {max_temp:.0f}°C",
                                         curses.color_pair(2) if max_temp < 70 else curses.color_pair(3))
                        detail_y += 1
                else:
                    self.stdscr.addstr(detail_y, 4, "Run background collector for 24h trending data", curses.A_DIM)
                    detail_y += 1

    def draw_top_bandwidth(self):
        """Draw top bandwidth consumers."""
        height, width = self.stdscr.getmaxyx()

        # Header with time mode
        mode_labels = {
            "realtime": "Real-Time",
            "10min": "Last 10 Minutes",
            "1hour": "Last Hour"
        }
        mode_label = mode_labels.get(self.bandwidth_time_mode, "Real-Time")
        header = f"Top Bandwidth Consumers - {mode_label}"
        self.stdscr.addstr(1, 2, header, curses.color_pair(1) | curses.A_BOLD)

        # Instructions
        instructions = "(T to toggle time period)"
        self.stdscr.addstr(1, width - len(instructions) - 2, instructions, curses.color_pair(4) | curses.A_DIM)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        # Column headers
        col_header = f"{'#':<3} {'Hostname':<20} {'IP':<15} {'Download':<11} {'Upload':<11} {'Total':<11}"
        self.stdscr.addstr(3, 2, col_header, curses.A_BOLD | curses.A_UNDERLINE)

        list_height = height - 7
        start_y = 4

        # Check if we have enough historical data
        if self.bandwidth_time_mode != "realtime" and len(self.bandwidth_history) < 2:
            msg = "Collecting historical data... Please wait a few refresh cycles."
            self.stdscr.addstr(5, 2, msg, curses.color_pair(4))
            msg2 = f"(Currently have {len(self.bandwidth_history)} snapshot(s), need at least 2)"
            self.stdscr.addstr(6, 2, msg2, curses.color_pair(4) | curses.A_DIM)
            return

        # Build client list with bandwidth for selected period
        client_bandwidth = []
        for client in self.clients:
            mac = client.get('mac')
            if not mac:
                continue

            tx, rx = self._get_bandwidth_for_period(mac)
            total = tx + rx

            client_bandwidth.append({
                'client': client,
                'mac': mac,
                'tx': tx,
                'rx': rx,
                'total': total
            })

        # Sort by total bandwidth
        client_bandwidth.sort(key=lambda x: x['total'], reverse=True)

        # Display top consumers
        for i in range(min(list_height, len(client_bandwidth))):
            idx = i + self.scroll_offset
            if idx >= len(client_bandwidth):
                break

            data = client_bandwidth[idx]
            client = data['client']

            # Format client info - hostname + MAC if no hostname
            hostname = client.get('hostname', client.get('name', ''))
            mac = data['mac']

            if hostname:
                # Show hostname, truncate if needed
                client_name = hostname[:20]
            else:
                # No hostname, show MAC
                client_name = f"[{mac[:17]}]" if mac else "Unknown"
                client_name = client_name[:20]

            # IP address
            ip = client.get('ip', 'N/A')[:15]

            # Get bandwidth rates
            tx_bytes_r = data['tx']
            rx_bytes_r = data['rx']
            total_rate = data['total']

            # Format rates using the format_bytes method (returns KB, MB, GB)
            download_str = f"{self.format_bytes(rx_bytes_r)}/s"
            upload_str = f"{self.format_bytes(tx_bytes_r)}/s"
            total_str = f"{self.format_bytes(total_rate)}/s"

            # Rank
            rank = f"{idx + 1}."

            line = f"{rank:<3} {client_name:<20} {ip:<15} {download_str:<11} {upload_str:<11} {total_str:<11}"

            # Color based on total bandwidth usage
            if total_rate > 10 * 1024**2:  # > 10 Mbps
                attr = curses.color_pair(3)  # Red - heavy usage
            elif total_rate > 1 * 1024**2:  # > 1 Mbps
                attr = curses.color_pair(4)  # Yellow - moderate usage
            elif total_rate > 0:
                attr = curses.color_pair(2)  # Green - light usage
            else:
                attr = curses.A_DIM  # Dim - no activity

            # Highlight selected
            if i == self.selected_index:
                attr = curses.color_pair(5)

            try:
                self.stdscr.addstr(start_y + i, 2, line[:width - 4], attr)
            except:
                pass

        # Summary at bottom
        total_download = sum(c.get('rx_bytes-r', 0) for c in self.clients)
        total_upload = sum(c.get('tx_bytes-r', 0) for c in self.clients)

        summary_y = height - 2
        summary = f"Total Network: ↓ {self.format_bytes(total_download)}/s  ↑ {self.format_bytes(total_upload)}/s"
        try:
            self.stdscr.addstr(summary_y, 2, summary, curses.color_pair(1) | curses.A_BOLD)
        except:
            pass

    def draw_clients(self):
        """Draw enhanced client activity list with AP/port info."""
        height, width = self.stdscr.getmaxyx()

        # Header
        header = f"Client Activity ({len(self.clients)} total)"
        self.stdscr.addstr(1, 2, header, curses.color_pair(6) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        # Column headers
        if self.filter_text:
            filter_info = f"Filter: '{self.filter_text}' (F to clear)"
            self.stdscr.addstr(3, 2, filter_info, curses.color_pair(4))
            col_y = 4
        else:
            col_y = 3

        col_header = f"{'Client':<16} {'IP':<15} {'AP/Switch':<15} {'Signal':<8} {'TX/RX':<18}"
        self.stdscr.addstr(col_y, 2, col_header, curses.A_BOLD | curses.A_UNDERLINE)

        # Clients list
        list_height = height - (8 if self.filter_text else 7)
        start_y = col_y + 1

        # Apply filter
        filtered_clients = self.clients
        if self.filter_text:
            filtered_clients = [c for c in self.clients
                              if self.filter_text.lower() in str(c.get('hostname', '')).lower()
                              or self.filter_text.lower() in str(c.get('mac', '')).lower()
                              or self.filter_text.lower() in str(c.get('ip', '')).lower()]

        for i in range(list_height):
            idx = i + self.scroll_offset
            if idx >= len(filtered_clients):
                break

            client = filtered_clients[idx]

            # Format client info
            hostname = client.get('hostname', client.get('name', ''))[:16]
            if not hostname:
                hostname = client.get('mac', 'Unknown')[:16]

            ip = client.get('ip', 'N/A')[:15]

            # Get connected AP or switch info
            ap_mac = client.get('ap_mac', '')
            sw_mac = client.get('sw_mac', '')

            # Find device name from MAC
            connected_to = 'Unknown'
            if ap_mac:
                for device in self.devices:
                    if device.get('mac') == ap_mac:
                        connected_to = device.get('name', 'AP')[:15]
                        break
            elif sw_mac:
                for device in self.devices:
                    if device.get('mac') == sw_mac:
                        port = client.get('sw_port', '?')
                        connected_to = f"{device.get('name', 'SW')[:10]}:{port}"[:15]
                        break

            # Signal or connection info
            is_wired = client.get('is_wired', False)
            if is_wired:
                signal_str = "Wired"
                attr = curses.color_pair(2)
            else:
                signal = client.get('signal', client.get('rssi', 0))
                signal_str = f"{signal}dBm" if signal else "N/A"

                # Color based on signal strength
                if signal > -50:
                    attr = curses.color_pair(2)  # Good signal
                elif signal > -70:
                    attr = curses.color_pair(4)  # Medium signal
                else:
                    attr = curses.color_pair(3)  # Poor signal

            # Throughput rates (real-time, bytes per second)
            tx_bytes_r = client.get('tx_bytes-r', 0)
            rx_bytes_r = client.get('rx_bytes-r', 0)

            tx_str = self.format_bytes(tx_bytes_r)
            rx_str = self.format_bytes(rx_bytes_r)
            throughput_str = f"{tx_str:>8}/{rx_str:<8}"

            line = f"{hostname:<16} {ip:<15} {connected_to:<15} {signal_str:<8} {throughput_str:<18}"

            # Highlight selected
            if i == self.selected_index:
                attr = curses.color_pair(5)

            try:
                self.stdscr.addstr(start_y + i, 2, line[:width - 4], attr)
            except:
                pass

    def draw_dashboard(self):
        """Draw comprehensive dashboard with all key metrics."""
        height, width = self.stdscr.getmaxyx()

        # Header
        title = "Network Dashboard"
        self.stdscr.addstr(1, (width - len(title)) // 2, title,
                          curses.color_pair(1) | curses.A_BOLD)

        y = 3

        # ═══ Overall Health Summary ═══
        devices_online = sum(1 for d in self.devices if d.get('state') == 1)
        devices_total = len(self.devices)
        health_pct = int((devices_online / devices_total * 100)) if devices_total > 0 else 0

        health_bar = self.draw_bar(health_pct, 20)
        health_color = self.get_usage_color(100 - health_pct)  # Inverted - higher is better

        self.stdscr.addstr(y, 2, "Network Health:", curses.A_BOLD)
        self.stdscr.addstr(y, 20, f"{health_pct}/100 ", health_color)
        self.stdscr.addstr(y, 30, health_bar, health_color)
        y += 2

        # ═══ Quick Stats ═══
        col1_x = 2
        col2_x = 40

        self.stdscr.addstr(y, col1_x, "Devices:", curses.A_BOLD)
        device_str = f"{devices_online}/{devices_total} online"
        device_color = curses.color_pair(2) if devices_online == devices_total else curses.color_pair(4)
        self.stdscr.addstr(y, col1_x + 12, device_str, device_color)

        self.stdscr.addstr(y, col2_x, "Clients:", curses.A_BOLD)
        self.stdscr.addstr(y, col2_x + 12, f"{len(self.clients)} active", curses.color_pair(2))
        y += 1

        self.stdscr.addstr(y, col1_x, "Alarms:", curses.A_BOLD)
        alarm_count = len(self.alarms)
        alarm_color = curses.color_pair(3) if alarm_count > 0 else curses.color_pair(2)
        self.stdscr.addstr(y, col1_x + 12, f"{alarm_count} active", alarm_color)

        self.stdscr.addstr(y, col2_x, "Events:", curses.A_BOLD)
        self.stdscr.addstr(y, col2_x + 12, f"{len(self.events)} recent", curses.A_NORMAL)
        y += 2

        # ═══ WAN Status ═══
        self.stdscr.addstr(y, 2, "═" * (width - 4), curses.A_DIM)
        y += 1
        self.stdscr.addstr(y, 2, "WAN Status", curses.color_pair(1) | curses.A_BOLD)
        y += 1

        if self.wan_stats:
            gateway = self.wan_stats[0]
            uplink = gateway.get('uplink', {})

            wan_ip = gateway.get('wan1', {}).get('ip', 'N/A')
            if wan_ip == 'N/A':
                wan_ip = uplink.get('ip', 'N/A')

            # Get WAN data from uplink for UDM devices
            latency = uplink.get('latency', gateway.get('latency', 0))
            tx_bytes_r = uplink.get('tx_bytes-r', gateway.get('tx_bytes-r', 0))
            rx_bytes_r = uplink.get('rx_bytes-r', gateway.get('rx_bytes-r', 0))

            wan_color = curses.color_pair(2) if wan_ip != 'N/A' else curses.color_pair(3)
            self.stdscr.addstr(y, col1_x, f"IP: {wan_ip}", wan_color)

            latency_color = self.get_latency_color(latency)
            self.stdscr.addstr(y, col2_x, f"Latency: {latency}ms", latency_color)
            y += 1

            self.stdscr.addstr(y, col1_x, f"↓ {self.format_bytes(rx_bytes_r)}/s", curses.color_pair(4))
            self.stdscr.addstr(y, col2_x, f"↑ {self.format_bytes(tx_bytes_r)}/s", curses.color_pair(4))
            y += 1

            # Add sparklines if database is available
            if self.use_database and y < height - 20:
                wan_history = self._get_historical_wan_stats(hours=24, max_points=40)
                if wan_history and len(wan_history) > 2:
                    # Extract download rates
                    rx_rates = [row[2] for row in wan_history]  # rx_rate column
                    sparkline = self._create_sparkline(rx_rates, width=40, height=1)
                    self.stdscr.addstr(y, col1_x, f"24h ↓: {sparkline[0]}", curses.color_pair(2) | curses.A_DIM)
                    y += 1

            y += 1
        else:
            self.stdscr.addstr(y, col1_x, "No WAN data available", curses.A_DIM)
            y += 2

        # ═══ Controller Resources ═══
        self.stdscr.addstr(y, 2, "═" * (width - 4), curses.A_DIM)
        y += 1
        self.stdscr.addstr(y, 2, "Controller Resources", curses.color_pair(1) | curses.A_BOLD)
        y += 1

        if self.system_info:
            sysinfo = self.system_info[0]
            cpu = sysinfo.get('cpu', 0)
            mem = sysinfo.get('mem', 0)

            cpu_bar = self.draw_bar(cpu, 15)
            cpu_color = self.get_usage_color(cpu)
            self.stdscr.addstr(y, col1_x, f"CPU:  {cpu:>5.1f}% ", curses.A_NORMAL)
            self.stdscr.addstr(y, col1_x + 14, cpu_bar, cpu_color)

            mem_bar = self.draw_bar(mem, 15)
            mem_color = self.get_usage_color(mem)
            self.stdscr.addstr(y, col2_x, f"MEM:  {mem:>5.1f}% ", curses.A_NORMAL)
            self.stdscr.addstr(y, col2_x + 14, mem_bar, mem_color)
            y += 1

            loadavg = f"{sysinfo.get('loadavg_1', 0):.2f}, {sysinfo.get('loadavg_5', 0):.2f}, {sysinfo.get('loadavg_15', 0):.2f}"
            self.stdscr.addstr(y, col1_x, f"Load: {loadavg}", curses.A_NORMAL)

            uptime_str = self.format_uptime(sysinfo.get('uptime', 0))
            self.stdscr.addstr(y, col2_x, f"Uptime: {uptime_str}", curses.A_NORMAL)
            y += 2
        else:
            self.stdscr.addstr(y, col1_x, "No system info available", curses.A_DIM)
            y += 2

        # ═══ Top 5 Bandwidth Consumers ═══
        self.stdscr.addstr(y, 2, "═" * (width - 4), curses.A_DIM)
        y += 1
        self.stdscr.addstr(y, 2, "Top 5 Bandwidth Users", curses.color_pair(1) | curses.A_BOLD)
        y += 1

        # Sort by total bandwidth (wireless + wired)
        def get_total_bw(c):
            return (c.get('tx_bytes-r', 0) + c.get('rx_bytes-r', 0) +
                    c.get('wired-tx_bytes-r', 0) + c.get('wired-rx_bytes-r', 0))

        clients_sorted = sorted(self.clients, key=get_total_bw, reverse=True)

        for i, client in enumerate(clients_sorted[:5]):
            hostname = client.get('hostname', client.get('name', ''))
            mac = client.get('mac', '')
            ip = client.get('ip', 'N/A')

            # Create unique display name
            if hostname:
                # Check if hostname is duplicated in list
                hostname_count = sum(1 for c in clients_sorted[:5] if c.get('hostname', c.get('name', '')) == hostname)
                if hostname_count > 1:
                    # Add last octet of IP to differentiate
                    display_name = f"{hostname[:15]} ({ip.split('.')[-1]})"
                else:
                    display_name = hostname[:20]
            else:
                display_name = f"[{mac[:17]}]"

            # Get bandwidth - use wired fields for wired devices, wireless for WiFi
            rx = client.get('rx_bytes-r', 0) + client.get('wired-rx_bytes-r', 0)
            tx = client.get('tx_bytes-r', 0) + client.get('wired-tx_bytes-r', 0)
            total = rx + tx

            if total > 0:
                rate_str = f"↓{self.format_bytes(rx)}/s ↑{self.format_bytes(tx)}/s"
                self.stdscr.addstr(y, col1_x, f"{i+1}. {display_name}", curses.A_NORMAL)

                # Color based on rate
                if total > 10 * 1024**2:
                    rate_color = curses.color_pair(3)
                elif total > 1 * 1024**2:
                    rate_color = curses.color_pair(4)
                else:
                    rate_color = curses.color_pair(2)

                self.stdscr.addstr(y, col2_x, rate_str, rate_color)
                y += 1

        if not any(c.get('tx_bytes-r', 0) + c.get('rx_bytes-r', 0) > 0 for c in clients_sorted[:5]):
            self.stdscr.addstr(y, col1_x, "No active traffic", curses.A_DIM)
            y += 1

        y += 1

        # ═══ Recent Issues ═══
        if y < height - 8:
            self.stdscr.addstr(y, 2, "═" * (width - 4), curses.A_DIM)
            y += 1
            self.stdscr.addstr(y, 2, "Recent Issues", curses.color_pair(1) | curses.A_BOLD)
            y += 1

            issues_shown = 0
            # Show offline devices
            for device in self.devices:
                if device.get('state') != 1 and issues_shown < 3:
                    name = device.get('name', 'Unknown')[:30]
                    self.stdscr.addstr(y, col1_x, f"⚠ Device offline: {name}", curses.color_pair(3))
                    y += 1
                    issues_shown += 1

            # Show recent alarms
            for alarm in self.alarms[:3-issues_shown]:
                if issues_shown >= 3:
                    break
                alarm_type = alarm.get('key', 'unknown')[:30]
                self.stdscr.addstr(y, col1_x, f"⚠ {alarm_type}", curses.color_pair(4))
                y += 1
                issues_shown += 1

            if issues_shown == 0:
                self.stdscr.addstr(y, col1_x, "✓ No issues detected", curses.color_pair(2))

    def draw_site_status(self):
        """Draw site status and health."""
        height, width = self.stdscr.getmaxyx()

        # Header
        header = "Site Status & Health"
        self.stdscr.addstr(1, 2, header, curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        # Summary stats
        num_devices = len(self.devices)
        num_clients = len(self.clients)
        devices_online = sum(1 for d in self.devices if d.get('state') == 1)

        summary_y = 3
        self.stdscr.addstr(summary_y, 2, f"Devices: {devices_online}/{num_devices} online", curses.color_pair(2))
        self.stdscr.addstr(summary_y, 35, f"Active Clients: {num_clients}", curses.color_pair(2))

        # Subsystem health
        self.stdscr.addstr(5, 2, "Subsystem Status:", curses.A_BOLD)

        list_height = height - 9
        start_y = 6

        for i in range(min(list_height, len(self.site_health))):
            idx = i + self.scroll_offset
            if idx >= len(self.site_health):
                break

            subsystem = self.site_health[idx]

            # Format subsystem info
            name = subsystem.get('subsystem', 'Unknown').upper()
            status = subsystem.get('status', 'unknown')
            num_user = subsystem.get('num_user', 0)
            num_guest = subsystem.get('num_guest', 0)
            num_iot = subsystem.get('num_iot', 0)

            # Determine color based on status
            if status == 'ok':
                status_str = "✓ OK"
                color = curses.color_pair(2)
            elif status == 'warning':
                status_str = "⚠ WARNING"
                color = curses.color_pair(4)
            else:
                status_str = "✗ ERROR"
                color = curses.color_pair(3)

            # Build info line
            info_parts = []
            if num_user:
                info_parts.append(f"Users: {num_user}")
            if num_guest:
                info_parts.append(f"Guests: {num_guest}")
            if num_iot:
                info_parts.append(f"IoT: {num_iot}")
            info_str = "  ".join(info_parts) if info_parts else ""

            line = f"{name:<8} {status_str:<12} {info_str}"

            try:
                self.stdscr.addstr(start_y + i, 4, line[:width - 6], color)
            except:
                pass

    def draw_controller_resources(self):
        """Draw controller CPU, memory, and load."""
        height, width = self.stdscr.getmaxyx()

        # Header
        header = "Controller Resources"
        self.stdscr.addstr(1, 2, header, curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        start_y = 4

        if self.system_info:
            for i, sysinfo in enumerate(self.system_info[:5]):
                y = start_y + i * 8

                # Device name/model
                hostname = sysinfo.get('hostname', 'Controller')
                self.stdscr.addstr(y, 2, f"Device: {hostname}", curses.A_BOLD)

                # CPU usage
                cpu = sysinfo.get('cpu', 0)
                cpu_bar = self.draw_bar(cpu, 30)
                cpu_color = self.get_usage_color(cpu)
                self.stdscr.addstr(y + 1, 4, f"CPU:    {cpu:>5.1f}% ", curses.A_NORMAL)
                self.stdscr.addstr(y + 1, 20, cpu_bar, cpu_color)

                # Memory usage
                mem = sysinfo.get('mem', 0)
                mem_bar = self.draw_bar(mem, 30)
                mem_color = self.get_usage_color(mem)
                self.stdscr.addstr(y + 2, 4, f"Memory: {mem:>5.1f}% ", curses.A_NORMAL)
                self.stdscr.addstr(y + 2, 20, mem_bar, mem_color)

                # Load averages
                loadavg_1 = sysinfo.get('loadavg_1', 0)
                loadavg_5 = sysinfo.get('loadavg_5', 0)
                loadavg_15 = sysinfo.get('loadavg_15', 0)
                self.stdscr.addstr(y + 3, 4, f"Load:   {loadavg_1:.2f}, {loadavg_5:.2f}, {loadavg_15:.2f}", curses.A_NORMAL)

                # Uptime
                uptime = sysinfo.get('uptime', 0)
                days = uptime // 86400
                hours = (uptime % 86400) // 3600
                minutes = (uptime % 3600) // 60
                uptime_str = f"{days}d {hours}h {minutes}m"
                self.stdscr.addstr(y + 4, 4, f"Uptime: {uptime_str}", curses.A_NORMAL)

                # Temperature (if available)
                temps = sysinfo.get('temperatures', [])
                if temps:
                    temp_strs = [f"{t.get('name', 'CPU')}: {t.get('value', 0):.1f}°C" for t in temps[:3]]
                    self.stdscr.addstr(y + 5, 4, f"Temps:  {', '.join(temp_strs)}", curses.A_NORMAL)
        else:
            self.stdscr.addstr(start_y, 2, "No system information available", curses.A_DIM)

    def draw_wan_network_stats(self):
        """Draw WAN and network statistics."""
        height, width = self.stdscr.getmaxyx()

        # Header
        header = "WAN & Network Statistics"
        self.stdscr.addstr(1, 2, header, curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        start_y = 4

        if self.wan_stats:
            for i, gateway in enumerate(self.wan_stats):
                y = start_y + i * 12

                # Gateway name
                name = gateway.get('name', 'Gateway')
                model = gateway.get('model', 'Unknown')
                self.stdscr.addstr(y, 2, f"{name} ({model})", curses.A_BOLD)

                # For UDM/gateway devices, WAN data is in the uplink field
                uplink = gateway.get('uplink', {})

                # WAN status
                wan_ip = gateway.get('wan1', {}).get('ip', 'N/A')
                if wan_ip == 'N/A':
                    # Fallback to uplink IP if wan1 not available
                    wan_ip = uplink.get('ip', 'N/A')
                wan_status = "Connected" if wan_ip != 'N/A' else "Disconnected"
                status_color = curses.color_pair(2) if wan_ip != 'N/A' else curses.color_pair(3)
                self.stdscr.addstr(y + 1, 4, f"WAN IP:     {wan_ip}", status_color)

                # Throughput - get from uplink for UDM devices
                tx_bytes = uplink.get('tx_bytes', gateway.get('tx_bytes', 0))
                rx_bytes = uplink.get('rx_bytes', gateway.get('rx_bytes', 0))
                self.stdscr.addstr(y + 2, 4, f"TX Total:   {self.format_bytes(tx_bytes)}", curses.A_NORMAL)
                self.stdscr.addstr(y + 3, 4, f"RX Total:   {self.format_bytes(rx_bytes)}", curses.A_NORMAL)

                # Throughput rates (bytes per second) - get from uplink for UDM devices
                tx_bytes_r = uplink.get('tx_bytes-r', gateway.get('tx_bytes-r', 0))
                rx_bytes_r = uplink.get('rx_bytes-r', gateway.get('rx_bytes-r', 0))
                self.stdscr.addstr(y + 4, 4, f"TX Rate:    {self.format_bytes(tx_bytes_r)}/s", curses.color_pair(4))
                self.stdscr.addstr(y + 5, 4, f"RX Rate:    {self.format_bytes(rx_bytes_r)}/s", curses.color_pair(4))

                # Latency - get from uplink for UDM devices
                latency = uplink.get('latency', gateway.get('latency', 0))
                latency_color = self.get_latency_color(latency)
                self.stdscr.addstr(y + 6, 4, f"Latency:    {latency} ms", latency_color)

                # Historical sparklines (24-hour trends)
                current_y = y + 7
                if self.use_database and y < height - 15:
                    wan_history = self._get_historical_wan_stats(hours=24, max_points=50)
                    if wan_history and len(wan_history) > 2:
                        self.stdscr.addstr(current_y, 4, "24h History:", curses.color_pair(1))
                        current_y += 1

                        # Download sparkline
                        rx_rates = [row[2] for row in wan_history]
                        sparkline_rx = self._create_sparkline(rx_rates, width=min(60, width - 20), height=1)
                        self.stdscr.addstr(current_y, 4, f"  ↓ RX: {sparkline_rx[0]}", curses.color_pair(2))
                        current_y += 1

                        # Upload sparkline
                        tx_rates = [row[1] for row in wan_history]
                        sparkline_tx = self._create_sparkline(tx_rates, width=min(60, width - 20), height=1)
                        self.stdscr.addstr(current_y, 4, f"  ↑ TX: {sparkline_tx[0]}", curses.color_pair(4))
                        current_y += 1

                        # Latency sparkline
                        latencies = [row[3] for row in wan_history if row[3] > 0]
                        if latencies:
                            sparkline_lat = self._create_sparkline(latencies, width=min(60, width - 20), height=1)
                            self.stdscr.addstr(current_y, 4, f"  ⏱ Lat: {sparkline_lat[0]}", curses.color_pair(6))
                            current_y += 1

                        # Stats summary
                        avg_rx = sum(rx_rates) / len(rx_rates)
                        max_rx = max(rx_rates)
                        avg_tx = sum(tx_rates) / len(tx_rates)
                        max_tx = max(tx_rates)
                        self.stdscr.addstr(current_y, 4,
                            f"  Avg: ↓{self.format_bytes(avg_rx)}/s ↑{self.format_bytes(avg_tx)}/s  " +
                            f"Peak: ↓{self.format_bytes(max_rx)}/s ↑{self.format_bytes(max_tx)}/s",
                            curses.A_DIM)
                        current_y += 1
                    else:
                        self.stdscr.addstr(current_y, 4, "24h History: Run collector to see trends", curses.A_DIM)
                        current_y += 1

                # Uptime
                uptime = gateway.get('uptime', 0)
                uptime_str = self.format_uptime(uptime)
                self.stdscr.addstr(current_y, 4, f"Uptime:     {uptime_str}", curses.A_NORMAL)
                current_y += 1

                # Connections
                num_sta = gateway.get('num_sta', 0)
                self.stdscr.addstr(current_y, 4, f"Clients:    {num_sta}", curses.A_NORMAL)
        else:
            self.stdscr.addstr(start_y, 2, "No WAN statistics available", curses.A_DIM)

    def draw_port_stats(self):
        """Draw switch port statistics."""
        height, width = self.stdscr.getmaxyx()

        # Header
        header = "Switch Ports & Traffic"
        self.stdscr.addstr(1, 2, header, curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        # Column headers
        col_header = f"{'Device':<15} {'Port':<6} {'Status':<8} {'Speed':<8} {'TX':<10} {'RX':<10}"
        self.stdscr.addstr(3, 2, col_header, curses.A_BOLD | curses.A_UNDERLINE)

        list_height = height - 7
        start_y = 4

        # Collect all ports from all devices (switches, routers, etc)
        all_ports = []
        for device in self.port_stats:
            # Include switches and gateway devices that have ports
            device_type = device.get('type', '')
            if device_type not in ['usw', 'switch', 'udm', 'uxg', 'ugw', 'usg']:
                continue

            # Check if device has ports
            port_table = device.get('port_table', [])
            if not port_table:
                continue

            device_name = device.get('name', 'Unknown')[:15]

            for port in port_table:
                if not port.get('port_idx'):  # Skip invalid ports
                    continue

                all_ports.append({
                    'device': device_name,
                    'port': port
                })

        # Display ports
        for i in range(min(list_height, len(all_ports))):
            idx = i + self.scroll_offset
            if idx >= len(all_ports):
                break

            item = all_ports[idx]
            device_name = item['device']
            port = item['port']

            port_idx = port.get('port_idx', '?')
            port_name = port.get('name', f"Port {port_idx}")[:6]

            # Status
            up = port.get('up', False)
            status = "Up" if up else "Down"
            status_color = curses.color_pair(2) if up else curses.color_pair(3)

            # Speed
            speed = port.get('speed', 0)
            speed_str = f"{speed}M" if speed else "N/A"

            # Traffic
            tx_bytes = port.get('tx_bytes', 0)
            rx_bytes = port.get('rx_bytes', 0)
            tx_str = self.format_bytes(tx_bytes)[:10]
            rx_str = self.format_bytes(rx_bytes)[:10]

            line = f"{device_name:<15} {port_name:<6} {status:<8} {speed_str:<8} {tx_str:<10} {rx_str:<10}"

            try:
                self.stdscr.addstr(start_y + i, 2, line[:width - 4], status_color if idx == self.selected_index else curses.A_NORMAL)
            except:
                pass

    def draw_bar(self, percentage, width):
        """Draw a progress bar."""
        filled = int((percentage / 100) * width)
        bar = "█" * filled + "░" * (width - filled)
        return bar

    def get_usage_color(self, percentage):
        """Get color based on usage percentage."""
        if percentage < 60:
            return curses.color_pair(2)  # Green
        elif percentage < 80:
            return curses.color_pair(4)  # Yellow
        else:
            return curses.color_pair(3)  # Red

    def get_latency_color(self, latency):
        """Get color based on latency."""
        if latency < 50:
            return curses.color_pair(2)  # Green
        elif latency < 100:
            return curses.color_pair(4)  # Yellow
        else:
            return curses.color_pair(3)  # Red

    def format_bytes(self, b):
        """Format bytes to human readable."""
        if b > 1024**3:
            return f"{b/1024**3:.1f}GB"
        elif b > 1024**2:
            return f"{b/1024**2:.1f}MB"
        elif b > 1024:
            return f"{b/1024:.1f}KB"
        elif b > 0:
            return f"{int(b)}B"
        return "0B"

    def format_uptime(self, seconds):
        """Format uptime seconds to human readable."""
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        return f"{days}d {hours}h {minutes}m"

    def draw_status_bar(self):
        """Draw status bar at bottom."""
        height, width = self.stdscr.getmaxyx()

        # Status message with database indicator
        db_indicator = " [DB✓]" if self.use_database else ""
        status = (self.status_message + db_indicator)[:width - 4]
        try:
            self.stdscr.addstr(height - 2, 2, status, curses.color_pair(2))
        except:
            pass

        # Keyboard shortcuts
        if self.current_view == "menu":
            shortcuts = "↑/↓: Navigate | Enter/Number: Select | Q: Quit"
        else:
            shortcuts = "↑/↓: Scroll | R: Refresh | ESC: Menu | Q: Quit"

        try:
            self.stdscr.addstr(height - 1, 2, shortcuts[:width - 4], curses.A_DIM)
        except:
            pass

    def draw(self):
        """Main draw function."""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()

        # Draw border
        try:
            self.stdscr.border()
        except:
            pass

        # Draw current view
        if self.current_view == "menu":
            self.draw_menu()
        elif self.current_view == "dashboard":
            self.draw_dashboard()
        elif self.current_view == "site_status":
            self.draw_site_status()
        elif self.current_view == "controller":
            self.draw_controller_resources()
        elif self.current_view == "wan_network":
            self.draw_wan_network_stats()
        elif self.current_view == "events":
            self.draw_events()
        elif self.current_view == "alarms":
            self.draw_alarms()
        elif self.current_view == "security_alerts":
            self.draw_security_alerts()
        elif self.current_view == "devices":
            self.draw_device_inventory()
        elif self.current_view == "clients":
            self.draw_clients()
        elif self.current_view == "top_bandwidth":
            self.draw_top_bandwidth()
        elif self.current_view == "ports":
            self.draw_port_stats()

        # Always draw status bar
        self.draw_status_bar()

        self.stdscr.refresh()

    def handle_input(self):
        """Handle keyboard input."""
        try:
            key = self.stdscr.getch()
        except:
            return

        height, width = self.stdscr.getmaxyx()
        list_height = height - 6

        if self.current_view == "menu":
            # Menu navigation
            if key == curses.KEY_UP:
                self.selected_index = max(0, self.selected_index - 1)
            elif key == curses.KEY_DOWN:
                self.selected_index = min(11, self.selected_index + 1)
            elif key in [curses.KEY_ENTER, 10, 13]:
                self.handle_menu_selection()
            elif key == ord('0'):
                self.selected_index = 0
                self.handle_menu_selection()
            elif key == ord('1'):
                self.selected_index = 1
                self.handle_menu_selection()
            elif key == ord('2'):
                self.selected_index = 2
                self.handle_menu_selection()
            elif key == ord('3'):
                self.selected_index = 3
                self.handle_menu_selection()
            elif key == ord('4'):
                self.selected_index = 4
                self.handle_menu_selection()
            elif key == ord('5'):
                self.selected_index = 5
                self.handle_menu_selection()
            elif key == ord('6'):
                self.selected_index = 6
                self.handle_menu_selection()
            elif key == ord('7'):
                self.selected_index = 7
                self.handle_menu_selection()
            elif key == ord('8'):
                self.selected_index = 8
                self.handle_menu_selection()
            elif key == ord('9'):
                self.selected_index = 9
                self.handle_menu_selection()
            elif key in [ord('r'), ord('R')]:
                self.selected_index = 10
                self.handle_menu_selection()
            elif key in [ord('q'), ord('Q')]:
                self.running = False

        else:  # List views
            # Filter mode - capture text input
            if self.filter_mode:
                if key == 27:  # ESC - exit filter mode
                    self.filter_mode = False
                    curses.curs_set(0)
                elif key in [curses.KEY_ENTER, 10, 13]:  # Enter - apply filter
                    self.filter_mode = False
                    curses.curs_set(0)
                    self.scroll_offset = 0
                    self.selected_index = 0
                elif key in [curses.KEY_BACKSPACE, 127, 8]:  # Backspace
                    self.filter_text = self.filter_text[:-1]
                elif 32 <= key <= 126:  # Printable characters
                    self.filter_text += chr(key)
                return

            # List navigation
            if key == curses.KEY_UP:
                self.selected_index = max(0, self.selected_index - 1)
                if self.selected_index < self.scroll_offset:
                    self.scroll_offset = self.selected_index
            elif key == curses.KEY_DOWN:
                # Determine max items based on current view
                if self.current_view == "events":
                    max_items = len(self.events)
                elif self.current_view == "alarms":
                    # Count recent alarms
                    three_days_ago = time.time() - (3 * 24 * 60 * 60)
                    max_items = sum(1 for alarm in self.alarms if self._get_alarm_time(alarm) and self._get_alarm_time(alarm) >= three_days_ago)
                elif self.current_view == "security_alerts":
                    max_items = sum(1 for alarm in self.alarms if self._is_security_alarm(alarm.get('key', '')))
                elif self.current_view == "devices":
                    max_items = len(self.devices)
                elif self.current_view == "clients":
                    max_items = len(self.clients)
                elif self.current_view == "top_bandwidth":
                    max_items = len(self.clients)
                elif self.current_view == "site_status":
                    max_items = len(self.site_health)
                elif self.current_view == "ports":
                    # Count all ports from all devices (switches, routers, etc)
                    max_items = sum(len(d.get('port_table', [])) for d in self.port_stats
                                   if d.get('type') in ['usw', 'switch', 'udm', 'uxg', 'ugw', 'usg'] and d.get('port_table'))
                else:
                    max_items = 1  # For views that don't scroll

                if max_items > 0:
                    self.selected_index = min(max_items - 1, self.selected_index + 1)
                    if self.selected_index >= self.scroll_offset + list_height:
                        self.scroll_offset = self.selected_index - list_height + 1
            elif key == curses.KEY_PPAGE:  # Page Up
                self.scroll_offset = max(0, self.scroll_offset - list_height)
                self.selected_index = self.scroll_offset
            elif key == curses.KEY_NPAGE:  # Page Down
                # Determine max items based on current view
                if self.current_view == "events":
                    max_items = len(self.events)
                elif self.current_view == "alarms":
                    # Count recent alarms
                    three_days_ago = time.time() - (3 * 24 * 60 * 60)
                    max_items = sum(1 for alarm in self.alarms if self._get_alarm_time(alarm) and self._get_alarm_time(alarm) >= three_days_ago)
                elif self.current_view == "security_alerts":
                    max_items = sum(1 for alarm in self.alarms if self._is_security_alarm(alarm.get('key', '')))
                elif self.current_view == "devices":
                    max_items = len(self.devices)
                elif self.current_view == "clients":
                    max_items = len(self.clients)
                elif self.current_view == "site_status":
                    max_items = len(self.site_health)
                elif self.current_view == "ports":
                    # Count all ports from all devices (switches, routers, etc)
                    max_items = sum(len(d.get('port_table', [])) for d in self.port_stats
                                   if d.get('type') in ['usw', 'switch', 'udm', 'uxg', 'ugw', 'usg'] and d.get('port_table'))
                else:
                    max_items = 1

                if max_items > 0:
                    self.scroll_offset = min(max(0, max_items - list_height), self.scroll_offset + list_height)
                    self.selected_index = self.scroll_offset
            elif key in [ord('f'), ord('F')]:  # Filter mode
                if self.filter_text:
                    # Clear filter
                    self.filter_text = ""
                    self.scroll_offset = 0
                    self.selected_index = 0
                else:
                    # Enter filter mode
                    self.filter_mode = True
                    curses.curs_set(1)  # Show cursor
                    self.status_message = "Enter filter text (ESC to cancel, Enter to apply)..."
            elif key == 27:  # ESC
                self.current_view = "menu"
                self.selected_index = 0
                self.scroll_offset = 0
                self.filter_text = ""
            elif key in [ord('t'), ord('T')]:
                # Toggle time period in bandwidth view
                if self.current_view == "top_bandwidth":
                    if self.bandwidth_time_mode == "realtime":
                        self.bandwidth_time_mode = "10min"
                    elif self.bandwidth_time_mode == "10min":
                        self.bandwidth_time_mode = "1hour"
                    else:
                        self.bandwidth_time_mode = "realtime"
            elif key in [ord('r'), ord('R')]:
                self.fetch_data()
            elif key in [ord('q'), ord('Q')]:
                self.running = False

    def handle_menu_selection(self):
        """Handle menu item selection."""
        if self.selected_index == 0:  # Dashboard
            self.current_view = "dashboard"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 1:  # Site Status
            self.current_view = "site_status"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 2:  # Controller Resources
            self.current_view = "controller"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 3:  # WAN & Network Stats
            self.current_view = "wan_network"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 4:  # Events
            self.current_view = "events"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 5:  # Alarms (Recent)
            self.current_view = "alarms"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 6:  # Security Alerts
            self.current_view = "security_alerts"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 7:  # Device Inventory
            self.current_view = "devices"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 8:  # Clients
            self.current_view = "clients"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 9:  # Top Bandwidth
            self.current_view = "top_bandwidth"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 10:  # Refresh
            self.fetch_data()
        elif self.selected_index == 11:  # Quit
            self.running = False

    def run(self):
        """Main application loop."""
        # Initial connection
        self.connect_controller()

        # Main loop
        self.stdscr.timeout(100)  # Non-blocking with 100ms timeout

        while self.running:
            self.draw()
            self.handle_input()
            time.sleep(0.05)

        # Cleanup
        if self.controller:
            try:
                self.controller.logout()
            except:
                pass


def main(stdscr):
    """Main entry point for curses application."""
    app = UniFiTUI(stdscr)
    app.run()


if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
