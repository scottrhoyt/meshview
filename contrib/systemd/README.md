# Systemd Service Templates

This directory contains systemd service templates for running Meshview automatically on system boot with automatic restart on crash.

## Overview

Two services are provided:
- **meshview-db.service**: Runs `startdb.py` (database writer/MQTT subscriber)
- **meshview-web.service**: Runs `main.py` (web server)

Both services are configured to:
- Start automatically on boot
- Restart automatically if they crash (`Restart=always`)
- Wait 5 seconds before restarting (`RestartSec=5`)
- Run after network is available

The web service depends on the database service, ensuring proper startup order.

## Installation

### 1. Customize the service files

Edit both service files and replace the following placeholders:

- `/path/to/meshview` → Your actual Meshview installation directory (4 occurrences in each file)
- `yourusername` → Your Linux username

**Example:**
```ini
# Before
WorkingDirectory=/path/to/meshview
ExecStart=/path/to/meshview/env/bin/python /path/to/meshview/startdb.py --config /path/to/meshview/config.ini
User=yourusername

# After
WorkingDirectory=/home/scott/meshview
ExecStart=/home/scott/meshview/env/bin/python /home/scott/meshview/startdb.py --config /home/scott/meshview/config.ini
User=scott
```

### 2. Copy to systemd directory

Copy the customized service files to the system directory:

```bash
sudo cp meshview-db.service /etc/systemd/system/
sudo cp meshview-web.service /etc/systemd/system/
```

### 3. Reload systemd

Tell systemd to recognize the new service files:

```bash
sudo systemctl daemon-reload
```

### 4. Enable services

Enable the services to start automatically on boot:

```bash
sudo systemctl enable meshview-db
sudo systemctl enable meshview-web
```

### 5. Start services

Start the services now:

```bash
sudo systemctl start meshview-db
sudo systemctl start meshview-web
```

## Managing Services

### Check status

```bash
systemctl status meshview-db
systemctl status meshview-web
```

### View logs

```bash
# Recent logs
journalctl -u meshview-db -n 50
journalctl -u meshview-web -n 50

# Follow logs in real-time
journalctl -u meshview-db -f
journalctl -u meshview-web -f
```

### Restart services

```bash
sudo systemctl restart meshview-db
sudo systemctl restart meshview-web
```

### Stop services

```bash
sudo systemctl stop meshview-db
sudo systemctl stop meshview-web
```

### Disable autostart

```bash
sudo systemctl disable meshview-db
sudo systemctl disable meshview-web
```

## After Editing Service Files

If you modify the service files in `/etc/systemd/system/`, always reload systemd:

```bash
sudo systemctl daemon-reload
sudo systemctl restart meshview-db
sudo systemctl restart meshview-web
```

## Troubleshooting

### Service won't start

1. Check the service status for error messages:
   ```bash
   systemctl status meshview-db
   systemctl status meshview-web
   ```

2. Check the logs:
   ```bash
   journalctl -u meshview-db -n 100
   journalctl -u meshview-web -n 100
   ```

3. Verify paths in the service files are correct

4. Ensure the virtual environment exists:
   ```bash
   ls -la /path/to/meshview/env/bin/python
   ```

5. Test manually:
   ```bash
   cd /path/to/meshview
   ./env/bin/python startdb.py --config config.ini
   ```

### Service keeps restarting

Check the logs to see what's causing the crash:
```bash
journalctl -u meshview-db -f
```

Common issues:
- MQTT connection problems (check `config.ini`)
- Database connection issues
- Missing Python dependencies
- Permission issues with config files or database

### Permission denied errors

Ensure the user specified in the service file has:
- Read access to the Meshview directory
- Read access to `config.ini`
- Write access to the database file (if using SQLite)
- Write access to log directories

## Alternative: Single Process Mode

Instead of running two separate services, you can use `mvrun.py` which runs both components in a single process with threads:

Create a single service file `/etc/systemd/system/meshview.service`:

```ini
[Unit]
Description=Meshview (Unified)
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/meshview
ExecStart=/path/to/meshview/env/bin/python /path/to/meshview/mvrun.py --config /path/to/meshview/config.ini
Restart=always
RestartSec=5
User=yourusername

[Install]
WantedBy=multi-user.target
```

Then enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable meshview
sudo systemctl start meshview
```
