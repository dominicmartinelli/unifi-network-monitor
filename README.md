# UniFi Network Monitor

A comprehensive terminal-based monitoring tool for Ubiquiti UniFi networks. Real-time visualization of network health, device status, client activity, and traffic statistics using a beautiful curses-based TUI.

![UniFi Network Monitor](https://img.shields.io/badge/UniFi-Network%20Monitor-blue)
![Python](https://img.shields.io/badge/python-3.7+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

### 📊 Comprehensive Monitoring Views

**0. Dashboard (At-a-Glance Overview)** 🆕
   - Real-time network summary with key metrics
   - WAN status with 24-hour sparkline trends
   - Controller resource usage (CPU, memory, load)
   - Top 5 bandwidth consumers
   - Recent network issues and alerts

**1. Site Status & Health**
   - Overview dashboard with device/client counts
   - Subsystem health status (LAN, WAN, WLAN, VPN)
   - Color-coded status indicators

**2. Controller Resources**
   - Real-time CPU and memory usage with visual progress bars
   - System load averages (1, 5, 15 minutes)
   - Uptime tracking
   - Temperature monitoring

**3. WAN & Network Statistics** 🆕
   - WAN connection status and IP address
   - Upload/download throughput (total and real-time rates)
   - Latency monitoring with color-coded indicators
   - **24-hour historical sparklines** (download, upload, latency)
   - Average and peak bandwidth statistics
   - Gateway uptime and client count

**4. Device Inventory** 🆕
   - Complete device list with MAC addresses, IPs, and CPU/Memory stats
   - Adoption state tracking and online/offline status
   - **Interactive device selection with 24-hour health sparklines**
   - CPU, memory, and temperature trends for selected device
   - Real-time performance monitoring

**5. Top Bandwidth Consumers** 🆕
   - Real-time bandwidth tracking per client
   - **Time period toggle** (T key): Real-time, 10 minutes, 1 hour
   - Ranked list with download/upload/total rates
   - Color-coded usage indicators
   - Hostname and IP display with duplicate differentiation

**6. Recent Alarms** (Past 3 Days)
   - Filtered alarms from last 3 days
   - Color-coded severity indicators
   - Timestamp and detailed alarm information

**7. Security Alerts** (All Time)
   - Dedicated security-focused alert view
   - Authentication failures and intrusion detection
   - Rogue device detection
   - Firewall and suspicious activity alerts

**8. Events Log**
   - 200 most recent network events
   - Real-time filtering and search
   - Timestamp and event type display

**9. Client Activity**
   - Connected clients with hostname/MAC
   - AP or switch port connection details
   - WiFi signal strength (RSSI) with color coding
   - Real-time throughput per client (wireless + wired)
   - Connection type detection

**10. Switch Ports & Traffic**
   - Per-port statistics for all switches and routers
   - Port status (Up/Down) with color indicators
   - Link speed display
   - Traffic totals (TX/RX) per port

### 📈 Historical Tracking & Analytics 🆕

**Background Statistics Collector**
- Continuous data collection to SQLite database
- 30-second interval sampling (configurable)
- Automatic cleanup of data older than 7 days
- Tracks client bandwidth, WAN stats, and device health

**ASCII Sparkline Visualizations**
- 24-hour trend visualization using Unicode block characters
- Download/upload bandwidth sparklines
- Latency trends over time
- Device CPU, memory, and temperature history
- Average and peak value summaries

### 🎨 User Interface

- **Color-Coded Status**: Green (good), Yellow (warning), Red (critical)
- **Visual Progress Bars**: CPU/Memory usage visualization
- **Keyboard Navigation**: Intuitive controls for all views
- **Real-Time Filtering**: Search and filter in Events and Clients views
- **Responsive Layout**: Adapts to terminal size

## Requirements

- Python 3.7 or higher
- UniFi Controller (UniFi OS / Dream Machine / Cloud Key)
- Local network access to your UniFi controller

### Python Dependencies

```bash
pip install requests urllib3
```

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/unifi-network-monitor.git
cd unifi-network-monitor
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create configuration file:
```bash
cp .config.example .config
```

4. Edit `.config` with your UniFi controller details:
```ini
[unifi]
# Local controller IP address
local_host = 192.168.1.1
local_port = 443

# Local controller authentication
local_username = your_username
local_password = your_password

# Site ID (default: default)
site = default

# SSL verification
verify_ssl_local = false
```

## Usage

### Running the TUI Application

```bash
python unifi_tui.py
```

### Background Statistics Collector (Optional)

For historical tracking and sparkline visualizations, run the background collector:

```bash
# Start with default settings (30-second interval)
python unifi_collector.py

# Or customize the interval and database location
python unifi_collector.py --interval 60 --database /path/to/stats.db
```

The collector will:
- Gather statistics every 30 seconds (configurable)
- Store data in SQLite database (`unifi_stats.db`)
- Enable 24-hour sparkline visualizations in the TUI
- Automatically clean up data older than 7 days
- Display `[DB✓]` indicator in TUI status bar when active

**Run as a service:** See `SPARKLINES_FEATURES.md` for systemd/launchd setup instructions.

### Keyboard Controls

**Menu Navigation:**
- `0-10` - Jump directly to specific view
- `↑/↓` - Navigate menu items
- `Enter` - Select menu item
- `R` - Refresh all data
- `Q` - Quit application

**List Views:**
- `↑/↓` - Scroll through items
- `PgUp/PgDn` - Page up/down
- `F` - Toggle filter mode (Events, Clients)
- `T` - Toggle time period (Top Bandwidth view: realtime/10min/1hour)
- `R` - Refresh data
- `ESC` - Return to main menu
- `Q` - Quit application

**Device Inventory:**
- `↑/↓` - Select device to view 24-hour health sparklines

**Filter Mode:**
- Type to filter results
- `Enter` - Apply filter
- `ESC` - Cancel filter
- `Backspace` - Delete character

## Configuration

### UniFi OS / Dream Machine

For UniFi OS devices (UDM, UDM Pro, Cloud Key Gen2+), the application uses the `/api/auth/login` endpoint. Ensure you have:

1. Created a local user account on your controller
2. Granted admin or read-only access as needed
3. Configured the credentials in `.config`

### Classic UniFi Controller

The application automatically detects and falls back to the classic `/api/login` endpoint if UniFi OS authentication fails.

## API Endpoints Used

The application connects to the following UniFi Controller API endpoints:

- `/api/auth/login` - Authentication (UniFi OS)
- `/proxy/network/api/s/{site}/stat/event` - Network events
- `/proxy/network/api/s/{site}/stat/alarm` - Alarms
- `/proxy/network/api/s/{site}/stat/device` - Device information
- `/proxy/network/api/s/{site}/stat/sta` - Client statistics
- `/proxy/network/api/s/{site}/stat/health` - Site health

## Troubleshooting

### Connection Issues

**"Failed to connect" error:**
- Verify your controller IP address and port
- Ensure the controller is accessible from your network
- Check username and password are correct

**SSL Certificate Errors:**
- Set `verify_ssl_local = false` in `.config` for self-signed certificates

### Data Display Issues

**Missing device information:**
- Ensure your user account has sufficient permissions
- Try refreshing data with `R` key

**Zero CPU/Memory values:**
- This is normal for devices that don't report system stats
- Gateway/controller devices should show resource usage

## Files

- `unifi_tui.py` - Main TUI application with curses interface
- `unifi_collector.py` - Background statistics collector for historical data
- `unifi_logs_simple.py` - UniFi API client library
- `debug_devices.py` - Device data structure debugging tool
- `debug_bandwidth.py` - Bandwidth calculation debugging tool
- `.config` - Configuration file (not in repo, create from example)
- `unifi_stats.db` - SQLite database (created by collector)
- `SPARKLINES_FEATURES.md` - Documentation for historical tracking features
- `README.md` - This file
- `TODO.md` - Planned features and enhancements

## Security Notes

⚠️ **Important:**
- Never commit your `.config` file with real credentials
- Use a dedicated read-only account for monitoring
- Keep your UniFi controller firmware up to date
- Use strong passwords for controller access

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - See LICENSE file for details

## Acknowledgments

- Built for Ubiquiti UniFi networks
- Uses the UniFi Controller API
- Inspired by the need for better network monitoring tools

## Support

For issues, questions, or contributions, please visit the GitHub repository.

---

**Note:** This is an unofficial tool and is not affiliated with or endorsed by Ubiquiti Networks.
