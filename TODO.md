# UniFi Network Monitor - TODO List

## ✅ Completed Features

- [x] Dashboard view with at-a-glance overview
- [x] Top Bandwidth Consumers with ranking and stats
- [x] Time period toggle for bandwidth (real-time, 10min, 1hour)
- [x] Historical tracking with SQLite database
- [x] ASCII sparkline visualizations (24-hour trends)
- [x] Background statistics collector daemon
- [x] WAN bandwidth sparklines (download, upload, latency)
- [x] Device health sparklines (CPU, memory, temperature)
- [x] Security alerts filtering and dedicated view
- [x] Alarm time filtering (3-day window for recent alarms)
- [x] Bandwidth calculation fix (wireless + wired combined)
- [x] Duplicate hostname differentiation with IP octets

## 🚧 In Progress

None currently.

## 📋 Planned Features

### High Priority

#### 1. Network Health Score
**Description:** Calculate and display an overall network health score (0-100) based on multiple factors.

**Metrics to consider:**
- Device availability (% online)
- WAN latency and stability
- Client connectivity (connection failures)
- Bandwidth utilization vs capacity
- Security alerts frequency
- Device resource usage (CPU/memory)

**Display:**
- Large health score on Dashboard
- Color-coded indicator (green/yellow/red)
- Breakdown of contributing factors
- Historical trend sparkline

**Estimated effort:** Medium

---

#### 2. Smart Anomaly Detection
**Description:** Detect and alert on unusual network behavior patterns.

**Detection types:**
- Unusual bandwidth spikes (client or WAN)
- Latency degradation
- Device resource exhaustion
- Abnormal client connection patterns
- Security event clustering
- Device offline/online cycles

**Features:**
- Machine learning baseline (average ± 2σ)
- Configurable thresholds
- Real-time notifications in TUI
- Anomaly history log
- Auto-dismiss after resolution

**Estimated effort:** High

---

#### 3. ASCII Network Topology Map
**Description:** Visual representation of network topology using ASCII art.

**Structure:**
```
                [Internet]
                     |
                [Gateway/UDM]
                     |
            +--------+--------+
            |        |        |
         [Switch] [Switch]  [AP]
            |        |        |
        Clients  Clients  WiFi Clients
```

**Features:**
- Auto-generated from device data
- Link status (up/down) with colors
- Device names and types
- Client counts per device
- Interactive navigation
- Export to text file

**Estimated effort:** High

---

### Medium Priority

#### 4. Speed Test Integration
**Description:** Trigger and display speed test results from UniFi gateway.

**Features:**
- On-demand speed test execution
- View historical test results
- Comparison with ISP plan
- Scheduled automatic tests
- Graph test history over time
- Alert on significant speed drops

**API endpoints:**
- `/api/s/{site}/cmd/devmgr` - Trigger test
- `/api/s/{site}/stat/speed-test` - Get results

**Estimated effort:** Medium

---

#### 5. Interactive Device Actions
**Description:** Perform actions on network devices directly from TUI.

**Actions:**
- Restart device
- Locate device (blink LED)
- Block/unblock client
- Reconnect client (force re-auth)
- Upgrade firmware
- Provision/adopt device

**UI:**
- Action menu for selected device
- Confirmation prompts
- Progress indicators
- Result feedback

**Estimated effort:** Medium

---

#### 6. Export & Reporting
**Description:** Export network data and generate reports.

**Export formats:**
- CSV (for Excel/spreadsheet)
- JSON (for API integration)
- HTML (formatted report)
- PDF (via HTML → PDF conversion)

**Report types:**
- Network summary report
- Bandwidth usage report (by client)
- Device health report
- Security incidents report
- Custom date range selection

**Estimated effort:** Medium

---

### Lower Priority

#### 7. WiFi Signal Heatmap
**Description:** Display WiFi signal strength across access points.

**Features:**
- Per-SSID signal levels
- Per-AP coverage visualization
- Client signal distribution
- Channel utilization
- Interference detection
- ASCII-based heatmap visualization

**Display:**
```
AP: Living Room (2.4GHz - Channel 6)
Signal Distribution:
Excellent (>-50 dBm): ████████░░ 45%
Good (-50 to -67):    ██████████ 55%
Fair (-67 to -80):    ░░░░░░░░░░  0%
Poor (<-80 dBm):      ░░░░░░░░░░  0%
```

**Estimated effort:** Medium

---

#### 8. Client History & Tracking
**Description:** Track individual client connection history and patterns.

**Features:**
- Connection/disconnection events
- Roaming behavior (AP switches)
- Bandwidth usage over time
- Device fingerprinting
- First seen / last seen timestamps
- Hostname history
- Connection duration stats
- Search by MAC/hostname/IP

**Estimated effort:** High

---

#### 9. Custom Alerts Configuration
**Description:** User-configurable alert rules and thresholds.

**Configuration options:**
- Bandwidth threshold alerts
- Device offline duration alerts
- Client connection/disconnection alerts
- Security event types to monitor
- Custom regex patterns for events
- Alert notification methods (TUI only for now)

**UI:**
- Alert configuration menu
- Rule builder interface
- Test alert rules
- Enable/disable individual rules
- Alert history viewer

**Estimated effort:** High

---

## 🔮 Future Ideas (Nice to Have)

- Multi-site support (switch between UniFi sites)
- Historical comparison (compare current vs last week/month)
- Traffic flow analysis (which clients talk to which services)
- DPI (Deep Packet Inspection) statistics integration
- Port forwarding rule viewer
- Firewall rule viewer and editor
- VPN connection monitoring
- Guest portal analytics
- Wireless uplink quality monitoring
- Power over Ethernet (PoE) usage tracking
- GraphQL/REST API for external integrations
- Plugin system for custom extensions
- Mobile device detection and categorization
- Network device discovery (non-UniFi devices)
- SNMP integration for third-party devices

---

## 📝 Notes

**Development priorities:**
1. Focus on features that add immediate value to daily network monitoring
2. Maintain clean, readable code with good documentation
3. Ensure backward compatibility with existing configs
4. Test thoroughly with different UniFi controller versions
5. Keep the TUI responsive and fast (async where needed)

**Technical debt:**
- Consider refactoring large view functions into smaller components
- Add unit tests for core functionality
- Improve error handling and user feedback
- Add logging for debugging purposes
- Create a proper Python package structure

**Contributions:**
Community contributions are welcome! See the main README for contribution guidelines.

---

**Last Updated:** 2025-11-11
