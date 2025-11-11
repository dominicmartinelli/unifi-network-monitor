#!/usr/bin/env python3
"""
UniFi Log Viewer - Interactive TUI using curses
"""

import curses
import threading
import time
from datetime import datetime
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
            self.status_message = f"Last refresh: {self.last_refresh.strftime('%H:%M:%S')}"
        except Exception as e:
            self.status_message = f"Error fetching data: {str(e)}"

    def draw_menu(self):
        """Draw main menu."""
        height, width = self.stdscr.getmaxyx()

        # Title
        title = "UniFi Network Monitor"
        self.stdscr.addstr(1, (width - len(title)) // 2, title,
                          curses.color_pair(1) | curses.A_BOLD)

        # Menu options - organized into sections
        menu_items = [
            ("1", "Site Status & Health", f"({len(self.site_health)} subsystems)"),
            ("2", "Controller Resources", "(CPU, Memory, Load)"),
            ("3", "WAN & Network Stats", "(Throughput, Latency)"),
            ("", "─" * 30, ""),  # Divider
            ("4", "Events Log", f"({len(self.events)} events)"),
            ("5", "Alarms Log", f"({len(self.alarms)} alarms)"),
            ("", "─" * 30, ""),  # Divider
            ("6", "Device Inventory", f"({len(self.devices)} devices)"),
            ("7", "Client Activity", f"({len(self.clients)} clients)"),
            ("8", "Switch Ports & Traffic", ""),
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

    def draw_alarms(self):
        """Draw alarms list."""
        height, width = self.stdscr.getmaxyx()

        # Header
        header = f"Alarms Log ({len(self.alarms)} total)"
        self.stdscr.addstr(1, 2, header, curses.color_pair(3) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        # Alarms list
        list_height = height - 6
        start_y = 3

        for i in range(list_height):
            idx = i + self.scroll_offset
            if idx >= len(self.alarms):
                break

            alarm = self.alarms[idx]

            # Format alarm - try multiple timestamp fields
            timestamp = '??:??:??'
            for field in ['datetime', 'time', 'timestamp', 'epoch']:
                timestamp_ms = alarm.get(field)
                if timestamp_ms:
                    try:
                        # Handle both milliseconds and seconds
                        if isinstance(timestamp_ms, str):
                            timestamp_ms = int(timestamp_ms)

                        if isinstance(timestamp_ms, (int, float)):
                            # If value is too large, it's in milliseconds
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

            line = f"{timestamp} {alarm_type[:15]:<15} {msg}"

            # Highlight selected and use red color
            if i == self.selected_index:
                attr = curses.color_pair(5)
            else:
                attr = curses.color_pair(3)

            try:
                self.stdscr.addstr(start_y + i, 2, line[:width - 4], attr)
            except:
                pass

    def draw_device_inventory(self):
        """Draw enhanced device inventory with MACs, IPs, and adoption state."""
        height, width = self.stdscr.getmaxyx()

        # Header
        header = f"Device Inventory ({len(self.devices)} total)"
        self.stdscr.addstr(1, 2, header, curses.color_pair(6) | curses.A_BOLD)
        self.stdscr.addstr(2, 2, "─" * (width - 4))

        # Column headers
        col_header = f"{'Name':<18} {'Model':<12} {'IP':<15} {'MAC':<17} {'Status':<10} {'Uptime':<10}"
        self.stdscr.addstr(3, 2, col_header, curses.A_BOLD | curses.A_UNDERLINE)

        # Devices list
        list_height = height - 7
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
            uptime = device.get('uptime', 0)

            # Format uptime
            if uptime:
                hours = uptime // 3600
                minutes = (uptime % 3600) // 60
                if hours > 24:
                    days = hours // 24
                    uptime_str = f"{days}d {hours % 24}h"
                else:
                    uptime_str = f"{hours}h {minutes}m"
            else:
                uptime_str = "N/A"

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

            line = f"{name:<18} {model:<12} {ip:<15} {mac:<17} {status:<10} {uptime_str:<10}"

            # Highlight selected
            if i == self.selected_index:
                attr = curses.color_pair(5)
            else:
                attr = status_color

            try:
                self.stdscr.addstr(start_y + i, 2, line[:width - 4], attr)
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

                # WAN status
                wan_ip = gateway.get('wan1', {}).get('ip', 'N/A')
                wan_status = "Connected" if wan_ip != 'N/A' else "Disconnected"
                status_color = curses.color_pair(2) if wan_ip != 'N/A' else curses.color_pair(3)
                self.stdscr.addstr(y + 1, 4, f"WAN IP:     {wan_ip}", status_color)

                # Throughput
                tx_bytes = gateway.get('tx_bytes', 0)
                rx_bytes = gateway.get('rx_bytes', 0)
                self.stdscr.addstr(y + 2, 4, f"TX Total:   {self.format_bytes(tx_bytes)}", curses.A_NORMAL)
                self.stdscr.addstr(y + 3, 4, f"RX Total:   {self.format_bytes(rx_bytes)}", curses.A_NORMAL)

                # Throughput rates (bytes per second)
                tx_bytes_r = gateway.get('tx_bytes-r', 0)
                rx_bytes_r = gateway.get('rx_bytes-r', 0)
                self.stdscr.addstr(y + 4, 4, f"TX Rate:    {self.format_bytes(tx_bytes_r)}/s", curses.color_pair(4))
                self.stdscr.addstr(y + 5, 4, f"RX Rate:    {self.format_bytes(rx_bytes_r)}/s", curses.color_pair(4))

                # Latency
                latency = gateway.get('latency', 0)
                latency_color = self.get_latency_color(latency)
                self.stdscr.addstr(y + 6, 4, f"Latency:    {latency} ms", latency_color)

                # Uptime
                uptime = gateway.get('uptime', 0)
                uptime_str = self.format_uptime(uptime)
                self.stdscr.addstr(y + 7, 4, f"Uptime:     {uptime_str}", curses.A_NORMAL)

                # Connections
                num_sta = gateway.get('num_sta', 0)
                self.stdscr.addstr(y + 8, 4, f"Clients:    {num_sta}", curses.A_NORMAL)
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
        return f"{b}B"

    def format_uptime(self, seconds):
        """Format uptime seconds to human readable."""
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        return f"{days}d {hours}h {minutes}m"

    def draw_status_bar(self):
        """Draw status bar at bottom."""
        height, width = self.stdscr.getmaxyx()

        # Status message
        status = self.status_message[:width - 4]
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
        elif self.current_view == "devices":
            self.draw_device_inventory()
        elif self.current_view == "clients":
            self.draw_clients()
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
                self.selected_index = min(9, self.selected_index + 1)
            elif key in [curses.KEY_ENTER, 10, 13]:
                self.handle_menu_selection()
            elif key == ord('1'):
                self.selected_index = 0
                self.handle_menu_selection()
            elif key == ord('2'):
                self.selected_index = 1
                self.handle_menu_selection()
            elif key == ord('3'):
                self.selected_index = 2
                self.handle_menu_selection()
            elif key == ord('4'):
                self.selected_index = 3
                self.handle_menu_selection()
            elif key == ord('5'):
                self.selected_index = 4
                self.handle_menu_selection()
            elif key == ord('6'):
                self.selected_index = 5
                self.handle_menu_selection()
            elif key == ord('7'):
                self.selected_index = 6
                self.handle_menu_selection()
            elif key == ord('8'):
                self.selected_index = 7
                self.handle_menu_selection()
            elif key in [ord('r'), ord('R')]:
                self.selected_index = 8
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
                    max_items = len(self.alarms)
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
                    max_items = len(self.alarms)
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
            elif key in [ord('r'), ord('R')]:
                self.fetch_data()
            elif key in [ord('q'), ord('Q')]:
                self.running = False

    def handle_menu_selection(self):
        """Handle menu item selection."""
        if self.selected_index == 0:  # Site Status
            self.current_view = "site_status"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 1:  # Controller Resources
            self.current_view = "controller"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 2:  # WAN & Network Stats
            self.current_view = "wan_network"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 3:  # Events
            self.current_view = "events"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 4:  # Alarms
            self.current_view = "alarms"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 5:  # Device Inventory
            self.current_view = "devices"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 6:  # Clients
            self.current_view = "clients"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 7:  # Switch Ports
            self.current_view = "ports"
            self.selected_index = 0
            self.scroll_offset = 0
            self.filter_text = ""
        elif self.selected_index == 8:  # Refresh
            self.fetch_data()
        elif self.selected_index == 9:  # Quit
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
