# Installation Guide

This guide covers installing the ESP32 Wireless Sensor Platform server on a Raspberry Pi or any Linux server.

## Quick Install (Recommended)

For a completely automated installation with all dependencies, firewall, and systemd service:

```bash
curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/wireless-esp32-sensor-platform/main/install.sh | sudo bash
```

Or download and run:

```bash
wget https://raw.githubusercontent.com/YOUR_USERNAME/wireless-esp32-sensor-platform/main/install.sh
chmod +x install.sh
sudo ./install.sh
```

## What the Installer Does

1. ✅ Detects your operating system (Debian/Ubuntu/Raspbian/Raspberry Pi OS)
2. ✅ Installs system dependencies (Python 3.8+, pip, git, sqlite3, etc.)
3. ✅ Creates a dedicated service user (`esp32sensor`)
4. ✅ Clones/updates the repository to `/opt/esp32-sensor`
5. ✅ Sets up Python virtual environment
6. ✅ Installs Python dependencies (Flask, etc.)
7. ✅ Creates data directories with proper permissions
8. ✅ Configures UFW firewall (ports 5000 TCP, 9999 UDP)
9. ✅ Creates systemd service for auto-start on boot
10. ✅ Configures log rotation
11. ✅ Starts the service

## Requirements

- **Operating System**: Debian, Ubuntu, Raspbian, or Raspberry Pi OS
- **RAM**: Minimum 512MB (1GB+ recommended for high-speed operation)
- **Disk Space**: 15GB+ recommended (for 24-hour database retention at 32kHz)
- **Python**: 3.8 or higher (automatically installed)
- **Privileges**: Root/sudo access

## Manual Installation

If you prefer to install manually:

### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git sqlite3 curl wget
```

### 2. Create Service User

```bash
sudo useradd --system --no-create-home --shell /bin/false esp32sensor
```

### 3. Clone Repository

```bash
sudo mkdir -p /opt
sudo git clone https://github.com/YOUR_USERNAME/wireless-esp32-sensor-platform.git /opt/esp32-sensor
sudo chown -R esp32sensor:esp32sensor /opt/esp32-sensor
```

### 4. Setup Python Environment

```bash
cd /opt/esp32-sensor/server
sudo -u esp32sensor python3 -m venv venv
sudo -u esp32sensor venv/bin/pip install -r requirements.txt
```

### 5. Create Data Directories

```bash
sudo mkdir -p /opt/esp32-sensor/server/data
sudo mkdir -p /opt/esp32-sensor/server/logs
sudo mkdir -p /var/log/esp32-sensor-server
sudo chown -R esp32sensor:esp32sensor /opt/esp32-sensor/server/data
sudo chown -R esp32sensor:esp32sensor /opt/esp32-sensor/server/logs
sudo chown -R esp32sensor:esp32sensor /var/log/esp32-sensor-server
```

### 6. Create Systemd Service

Create `/etc/systemd/system/esp32-sensor-server.service`:

```ini
[Unit]
Description=ESP32 Wireless Sensor Platform Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=esp32sensor
Group=esp32sensor
WorkingDirectory=/opt/esp32-sensor/server
Environment="PATH=/opt/esp32-sensor/server/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="FLASK_HOST=0.0.0.0"
Environment="FLASK_PORT=5000"
ExecStart=/opt/esp32-sensor/server/venv/bin/python app.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/esp32-sensor-server/output.log
StandardError=append:/var/log/esp32-sensor-server/error.log

[Install]
WantedBy=multi-user.target
```

### 7. Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable esp32-sensor-server
sudo systemctl start esp32-sensor-server
sudo systemctl status esp32-sensor-server
```

## Updating

To update an existing installation:

```bash
sudo ./install.sh
```

The installer will detect the existing installation and ask if you want to update. It will:
1. Update the installer script itself
2. Pull latest code from repository
3. Update Python dependencies
4. Restart the service

## Uninstalling

To completely remove the installation:

```bash
sudo ./install.sh --uninstall
```

You'll be asked if you want to delete data files.

## Service Management

```bash
# Check status
sudo systemctl status esp32-sensor-server

# Start service
sudo systemctl start esp32-sensor-server

# Stop service
sudo systemctl stop esp32-sensor-server

# Restart service
sudo systemctl restart esp32-sensor-server

# View logs (live)
sudo journalctl -u esp32-sensor-server -f

# View last 100 lines of logs
sudo journalctl -u esp32-sensor-server -n 100
```

## Configuration

### Environment Variables

Edit `/etc/systemd/system/esp32-sensor-server.service`:

```ini
Environment="FLASK_HOST=0.0.0.0"          # Listen on all interfaces
Environment="FLASK_PORT=5000"              # HTTP API port
Environment="FLASK_DEBUG=False"            # Debug mode (use True for development)
```

After editing, reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart esp32-sensor-server
```

### Database Retention

Edit `/opt/esp32-sensor/server/app.py`:

```python
DB_RETENTION_HOURS = 24  # Keep last 24 hours (default)
```

### UDP Port

The UDP receiver listens on port 9999 by default. To change:

```python
UDP_PORT = 9999  # Change in app.py
```

## Firewall Configuration

### UFW (Ubuntu/Debian)

```bash
sudo ufw allow 5000/tcp comment "ESP32 Sensor HTTP API"
sudo ufw allow 9999/udp comment "ESP32 Sensor UDP Data"
```

### iptables

```bash
sudo iptables -A INPUT -p tcp --dport 5000 -j ACCEPT
sudo iptables -A INPUT -p udp --dport 9999 -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

## Accessing the Server

After installation, the server is accessible at:

- **Web Dashboard**: `http://YOUR_PI_IP:5000`
- **API Endpoint**: `http://YOUR_PI_IP:5000/api/stats`
- **UDP Receiver**: `YOUR_PI_IP:9999`

Find your Raspberry Pi's IP address:

```bash
hostname -I
```

## Troubleshooting

### Service Won't Start

Check logs:
```bash
sudo journalctl -u esp32-sensor-server -n 50
```

Check service status:
```bash
sudo systemctl status esp32-sensor-server
```

### Port Already in Use

Find what's using the port:
```bash
sudo netstat -tulpn | grep 5000
sudo netstat -tulpn | grep 9999
```

### Permission Denied Errors

Fix ownership:
```bash
sudo chown -R esp32sensor:esp32sensor /opt/esp32-sensor/server/data
sudo chown -R esp32sensor:esp32sensor /var/log/esp32-sensor-server
```

### Database Issues

Check database permissions:
```bash
ls -la /opt/esp32-sensor/server/data/
```

Reset database:
```bash
sudo systemctl stop esp32-sensor-server
sudo rm /opt/esp32-sensor/server/data/accelerometer.db*
sudo systemctl start esp32-sensor-server
```

### Check UDP Reception

Test UDP port is listening:
```bash
sudo netstat -ulpn | grep 9999
```

### Low Memory

Monitor memory usage:
```bash
free -h
htop
```

Reduce database retention:
```python
DB_RETENTION_HOURS = 1  # Keep only last hour
```

## Performance Tuning

### For High-Speed Data (32 kHz)

1. **Increase swap** (Raspberry Pi):
```bash
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Set CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

2. **Optimize SQLite**:
Already configured in app.py with WAL mode and batched writes.

3. **Monitor performance**:
```bash
# CPU usage
top -p $(pgrep -f "python app.py")

# Disk I/O
sudo iotop -p $(pgrep -f "python app.py")
```

## Security Recommendations

1. **Change default ports** if exposed to internet
2. **Use reverse proxy** (nginx) with SSL for production
3. **Enable UFW firewall**
4. **Regular updates**: `sudo apt-get update && sudo apt-get upgrade`
5. **Monitor logs**: `sudo journalctl -u esp32-sensor-server -f`

## Support

For issues, please check:
1. Service logs: `sudo journalctl -u esp32-sensor-server -f`
2. System logs: `dmesg | tail -50`
3. Disk space: `df -h`
4. Memory: `free -h`

## License

This project is licensed under the MIT License - see the LICENSE file for details.
