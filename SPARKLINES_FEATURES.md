# Historical Tracking & Sparklines

## Overview

The UniFi Monitor now includes SQLite-based historical tracking with ASCII sparkline visualizations for bandwidth, device health, and WAN statistics over 24-hour periods.

## Features Added

### 1. SQLite Database Integration

The TUI now automatically detects if the `unifi_stats.db` database exists and enables historical tracking features. When the database is available, you'll see a `[DB✓]` indicator in the status bar.

### 2. Background Collector

Run the background collector to gather statistics every 30 seconds:

```bash
# Start the collector with default settings (30s interval)
python unifi_collector.py

# Or customize the interval and database path
python unifi_collector.py --interval 60 --database /path/to/stats.db
```

The collector stores:
- **Client Bandwidth**: Per-client TX/RX bytes and rates (wireless + wired)
- **WAN Statistics**: Gateway throughput, latency, and client counts
- **Device Health**: CPU usage, memory usage, uptime, and temperature

Data is automatically cleaned up after 7 days to prevent database growth.

### 3. Sparkline Visualizations

#### Dashboard View (Option 0)
- 24-hour download trend sparkline for WAN interface
- Compact view showing recent bandwidth patterns

#### WAN & Network Stats (Option 3)
Enhanced with comprehensive 24-hour trending:
- **Download (RX) sparkline**: Visual representation of download bandwidth over 24 hours
- **Upload (TX) sparkline**: Visual representation of upload bandwidth over 24 hours
- **Latency sparkline**: Network latency trends over time
- **Statistics summary**: Shows average and peak values for all metrics

Example display:
```
24h History:
  ↓ RX: ▁▂▃▅▇██▇▅▃▂▁▂▃▄▅▆▅▄▃▂▁
  ↑ TX: ▁▁▂▃▄▅▄▃▂▂▃▄▅▆▅▄▃▂▁▁
  ⏱ Lat: ▄▄▄▅▅▄▄▄▃▃▃▃▄▄▄▃▃▃▃▃
  Avg: ↓45.2MB/s ↑12.3MB/s  Peak: ↓98.1MB/s ↑45.7MB/s
```

#### Device Inventory (Option 4)
Now shows CPU and Memory percentages in the main list, plus a detail panel for the selected device:

- **CPU usage sparkline**: 24-hour CPU utilization trend with avg/peak values
- **Memory usage sparkline**: 24-hour memory utilization trend with avg/peak values
- **Temperature sparkline**: 24-hour temperature trend with avg/peak values (when available)

The detail panel automatically displays when:
1. Database is available
2. A device is selected (highlighted)
3. Historical data exists for that device

#### Top Bandwidth Users (Option 5)
- Time period toggle (T key) now works with historical data
- 10-minute and 1-hour modes calculate from database snapshots
- More accurate bandwidth tracking over longer periods

## Sparkline Characters

The sparklines use Unicode block characters for visualization:
- ` ` (space) = No activity
- `▁` = Minimum activity (12.5%)
- `▂` = Low activity (25%)
- `▃` = Low-medium activity (37.5%)
- `▄` = Medium activity (50%)
- `▅` = Medium-high activity (62.5%)
- `▆` = High activity (75%)
- `▇` = Very high activity (87.5%)
- `█` = Maximum activity (100%)

## Color Coding

### WAN Sparklines
- **Green**: Download bandwidth
- **Yellow**: Upload bandwidth
- **Magenta**: Latency

### Device Health Sparklines
- **Green**: Normal levels (CPU < 70%, Memory < 80%, Temp < 70°C)
- **Yellow**: Elevated levels (CPU/Memory approaching limits)
- **Red**: Critical levels (Temperature > 70°C)

## Usage Tips

1. **Start the collector first**: Let it run for at least 5-10 minutes to gather initial data
2. **Wait for data accumulation**: Sparklines become more meaningful after several hours of collection
3. **Leave collector running**: For best results, run the collector continuously in the background
4. **Monitor the database**: Database indicator `[DB✓]` in status bar confirms SQLite is being used

## Running Collector as Service

### macOS (using launchd)

Create `~/Library/LaunchAgents/com.unifi.collector.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.unifi.collector</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/unifi_collector.py</string>
        <string>--interval</string>
        <string>30</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

Then load it:
```bash
launchctl load ~/Library/LaunchAgents/com.unifi.collector.plist
```

### Linux (using systemd)

Create `/etc/systemd/system/unifi-collector.service`:

```ini
[Unit]
Description=UniFi Statistics Collector
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/unifi
ExecStart=/usr/bin/python3 /path/to/unifi_collector.py --interval 30
Restart=always

[Install]
WantedBy=multi-user.target
```

Then enable and start:
```bash
sudo systemctl enable unifi-collector
sudo systemctl start unifi-collector
```

## Database Schema

The collector creates three tables:

### client_bandwidth
- Per-client bandwidth snapshots with timestamp
- Columns: timestamp, mac, hostname, ip, tx_bytes, rx_bytes, wired_tx_bytes, wired_rx_bytes, tx_rate, rx_rate, is_wired

### wan_stats
- WAN gateway statistics snapshots
- Columns: timestamp, wan_ip, tx_bytes, rx_bytes, tx_rate, rx_rate, latency, clients

### device_health
- Device health metrics snapshots
- Columns: timestamp, device_name, device_mac, device_type, state, cpu_usage, mem_usage, uptime, temperature

All timestamps are Unix epoch (seconds).

## Troubleshooting

**No sparklines showing?**
- Check that `unifi_stats.db` exists in the same directory
- Verify the collector is running and gathering data
- Look for `[DB✓]` in the status bar

**Sparklines look flat?**
- Wait for more data collection (sparklines need variation to show trends)
- Check that devices are actually active and generating traffic

**Historical bandwidth not working?**
- Ensure collector has been running for at least 10-15 minutes
- Verify database file has recent data: `sqlite3 unifi_stats.db "SELECT COUNT(*) FROM wan_stats;"`

**Database growing too large?**
- The collector auto-cleans data older than 7 days
- You can manually clean: `sqlite3 unifi_stats.db "DELETE FROM wan_stats WHERE timestamp < ..."`
