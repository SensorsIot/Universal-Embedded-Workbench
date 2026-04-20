# Embedded Workbench — Raspberry Pi Setup

Raspberry Pi-based test instrument for ESP32 firmware: RFC2217 serial proxy with automatic udev hotplug, WiFi testing (AP/STA), BLE proxy, MQTT broker, GDB/JTAG debugging via OpenOCD, traffic sniffer, and RF signal generator (Si5351 + PE4302).

## SD Card Rebuild (from scratch)

Complete procedure to build a new SD card with full workbench functionality.
Tested on **Raspberry Pi Zero 2 W** (512 MB RAM).

### Step 1: Flash the OS

Flash **Raspberry Pi OS Lite (64-bit)** to the SD card using Raspberry Pi Imager.

In the imager settings:
- **Hostname:** `Serial1`
- **Enable SSH:** yes (password or key auth)
- **Username:** `pi`
- **WiFi:** configure your network (country code `CH` or as needed)
- **Locale:** set timezone as needed

### Step 2: First boot — system hardening

These changes prevent the OOM crash cycle that kills Pi Zero 2 W boards.
**Do this before installing the workbench.**

```bash
# SSH into the Pi
ssh pi@Serial1.local

# --- Reduce GPU memory (saves 48 MB on a headless Pi) ---
echo "gpu_mem=16" | sudo tee -a /boot/firmware/config.txt

# --- Add real disk swap (zram alone is not enough for 512 MB) ---
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# --- Disable unnecessary services ---
sudo systemctl disable --now ModemManager 2>/dev/null || true
sudo systemctl disable cloud-init cloud-init-local cloud-init-main \
     cloud-init-network cloud-final cloud-config 2>/dev/null || true

# --- Fix dual wpa_supplicant conflict ---
# Keep wpa_supplicant.service (used by NetworkManager), disable the
# interface-specific instance that fights over wlan0
sudo systemctl disable --now wpa_supplicant@wlan0 2>/dev/null || true

# --- Limit journal size ---
sudo mkdir -p /etc/systemd/journald.conf.d
cat <<'EOF' | sudo tee /etc/systemd/journald.conf.d/size.conf
[Journal]
SystemMaxUse=16M
EOF
sudo systemctl restart systemd-journald

# --- Reboot to apply gpu_mem ---
sudo reboot
```

After reboot, verify:
```bash
vcgencmd get_mem gpu          # should show gpu=16M
free -h                       # should show ~480 MB total + swap
```

### Step 3: Install the workbench

```bash
# Clone the repo
git clone https://github.com/SensorsIot/Universal-Embedded-Workbench.git
cd Universal-Embedded-Workbench/pi

# Install everything
sudo bash install.sh
```

### Step 4: (Optional) Pin USB slots

Slots are **auto-detected** from the Pi's USB hub topology at portal startup — no configuration is required. Skip ahead to Step 5 unless you need custom labels, fixed TCP/GDB port numbers, a GPIO probe definition, or you want to exclude ports that the hub chip reports but your board doesn't wire.

To pin the layout, plug your ESP32s in and snapshot the USB topology:

```bash
rfc2217-learn-slots
```

Then edit:
```bash
sudo nano /etc/rfc2217/workbench.json
```

Current schema (prefix-based matching — see FR-002 in the FSD):
```json
{
  "gpio_boot": 18,
  "gpio_en": 17,
  "slots": [
    {"label": "SLOT1", "usb_prefix": "0:1.1.2", "tcp_port": 4001, "gdb_port": 3333, "openocd_telnet_port": 4444},
    {"label": "SLOT2", "usb_prefix": "0:1.1.3", "tcp_port": 4002, "gdb_port": 3334, "openocd_telnet_port": 4445},
    {"label": "SLOT3", "usb_prefix": "0:1.2",   "tcp_port": 4003, "gdb_port": 3335, "openocd_telnet_port": 4446},
    {"label": "SLOT4", "usb_prefix": "0:1.3",   "tcp_port": 4004, "gdb_port": 3336, "openocd_telnet_port": 4447}
  ],
  "debug_probes": []
}
```

The number of slot entries depends on your Pi model: Pi Zero 2 W with external hub → 3–4; Pi 3B+ / 4B / 5 → 4. Use whatever `rfc2217-learn-slots` reports.

Restart the portal:
```bash
sudo systemctl restart rfc2217-portal
```

### Step 5: Verify

```bash
curl http://localhost:8080/api/devices   # should list all slots
curl http://localhost:8080/api/info      # portal version and host info
```

## Quick Install (existing Pi)

```bash
cd pi
sudo bash install.sh
```

## Update Scripts Only

To update the portal scripts without touching system packages or config:

```bash
sudo bash install.sh --update
```

## Architecture

One slot is auto-created per wired USB hub port on the host Pi (`SLOT1`, `SLOT2`, ..., `SLOTn`). TCP proxy ports are assigned as `4000 + slot_index`, GDB/OpenOCD as `3332 + slot_index` / `4443 + slot_index`. Example on a 4-slot host:

```
USB Hub Slots              Portal (:8080)              Clients
─────────────              ──────────────              ───────
SLOT1 (ttyACM/USB) ──► plain_rfc2217_server :4001 ◄──── esptool / pyserial
SLOT2 (ttyACM/USB) ──► plain_rfc2217_server :4002 ◄──── esptool / pyserial
SLOT3 (ttyACM/USB) ──► plain_rfc2217_server :4003 ◄──── esptool / pyserial
SLOT4 (ttyACM/USB) ──► plain_rfc2217_server :4004 ◄──── esptool / pyserial
```

## Components

| File | Installs to | Purpose |
|------|-------------|---------|
| `portal.py` | `/usr/local/bin/rfc2217-portal` | HTTP portal + proxy supervisor |
| `plain_rfc2217_server.py` | `/usr/local/bin/plain_rfc2217_server.py` | RFC2217 server (direct DTR/RTS) |
| `wifi_controller.py` | `/usr/local/bin/wifi_controller.py` | WiFi test instrument (AP/STA/scan/relay) |
| `ble_controller.py` | `/usr/local/bin/ble_controller.py` | BLE scan/connect/write proxy |
| `mqtt_controller.py` | `/usr/local/bin/mqtt_controller.py` | MQTT broker management |
| `sniffer.py` | `/usr/local/bin/sniffer.py` | DNS + TLS SNI traffic capture |
| `rfc2217-learn-slots` | `/usr/local/bin/rfc2217-learn-slots` | USB hub slot discovery |

## API

```bash
# List devices
curl http://workbench.local:8080/api/devices

# Portal info
curl http://workbench.local:8080/api/info
```

## Flashing ESP32

```bash
# ESP32-C3 (native USB, ttyACM)
python3 -m esptool --chip esp32c3 \
  --port "rfc2217://workbench.local:4001" \
  --baud 921600 \
  write-flash -z 0x0 firmware.bin

# ESP32 DevKit (UART bridge, ttyUSB)
python3 -m esptool --chip esp32 \
  --port "rfc2217://workbench.local:4001?ign_set_control" \
  --baud 921600 \
  write_flash -z 0x0 firmware.bin
```

## GPIO Wiring

| Pi GPIO (BCM) | Function | DUT Pin |
|---------------|----------|---------|
| 17 | Hardware Reset (active LOW) | EN/RST |
| 18 | Boot Mode Select (active LOW) | GPIO0 (ESP32) / GPIO9 (C3) |

## Troubleshooting

```bash
# Check portal status
sudo systemctl status rfc2217-portal

# View portal logs
sudo journalctl -u rfc2217-portal -f

# Check connected devices
ls -la /dev/ttyUSB* /dev/ttyACM*

# Check listening ports
ss -tlnp | grep -E '8080|400'

# Restart portal
sudo systemctl restart rfc2217-portal

# Check memory (important on Pi Zero 2 W)
free -h
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Connection refused on port 5000 | Portal runs on **port 8080**, not 5000 |
| Pi crashes / reboots randomly | OOM — apply Step 2 hardening, check `free -h` |
| `sudo` segfaults | SD card corruption from hard crashes — reflash |
| Timeout during flash | Try `--no-stub` flag with esptool |
| Port busy | Only one RFC2217 client can connect per slot |
