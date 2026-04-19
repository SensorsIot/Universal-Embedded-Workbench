#!/bin/bash
# Install RFC2217 Portal on Raspberry Pi
#
# Usage:
#   sudo bash install.sh              # full install (first time)
#   sudo bash install.sh --update     # update scripts only (no system changes)
#
# See pi/README.md for the full SD card rebuild procedure.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UPDATE_ONLY=false
if [ "$1" = "--update" ]; then
    UPDATE_ONLY=true
fi

echo "=== Installing RFC2217 Portal ==="

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
if [ "$UPDATE_ONLY" = false ]; then
    echo "Installing system packages..."
    apt-get update -qq
    apt-get install -y \
        python3-serial python3-pip python3-libgpiod \
        hostapd dnsmasq-base \
        mosquitto mosquitto-clients \
        curl iptables \
        bluetooth bluez

    # Python packages not available via apt
    pip3 install esptool bleak smbus2 --break-system-packages 2>/dev/null || true

    # Enable I2C for Si5351 signal generator
    if command -v raspi-config >/dev/null 2>&1; then
        raspi-config nonint do_i2c 0 2>/dev/null || true
    fi

    # OpenOCD for ESP32 (GDB debug support)
    if ! command -v openocd-esp32 >/dev/null 2>&1; then
        echo "Installing openocd-esp32..."
        ARCH=$(uname -m)
        case "$ARCH" in
            aarch64) OCD_ARCH="arm64" ;;
            armv7l|armv6l) OCD_ARCH="armhf" ;;
            x86_64) OCD_ARCH="amd64" ;;
            *) echo "WARNING: unsupported arch $ARCH for openocd-esp32, skipping"; OCD_ARCH="" ;;
        esac
        if [ -n "$OCD_ARCH" ]; then
            OCD_VER="v0.12.0-esp32-20260304"
            OCD_URL="https://github.com/espressif/openocd-esp32/releases/download/${OCD_VER}/openocd-esp32-linux-${OCD_ARCH}-0.12.0-esp32-20260304.tar.gz"
            wget -q "$OCD_URL" -O /tmp/openocd-esp32.tar.gz
            tar xzf /tmp/openocd-esp32.tar.gz -C /tmp/
            cp /tmp/openocd-esp32/bin/openocd /usr/local/bin/openocd-esp32
            mkdir -p /usr/local/share/openocd-esp32
            cp -r /tmp/openocd-esp32/share/openocd/scripts /usr/local/share/openocd-esp32/scripts
            rm -rf /tmp/openocd-esp32 /tmp/openocd-esp32.tar.gz
            echo "openocd-esp32 installed: $(openocd-esp32 --version 2>&1 | head -1)"
        fi
    else
        echo "openocd-esp32 already installed, skipping..."
    fi
fi

# ---------------------------------------------------------------------------
# 2. Disable services we manage dynamically
# ---------------------------------------------------------------------------
if [ "$UPDATE_ONLY" = false ]; then
    echo "Configuring managed services..."
    systemctl disable --now hostapd 2>/dev/null || true
    systemctl mask hostapd 2>/dev/null || true
    systemctl disable --now dnsmasq 2>/dev/null || true
    systemctl disable --now mosquitto 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 3. Create directories
# ---------------------------------------------------------------------------
echo "Creating directories..."
mkdir -p /etc/rfc2217
mkdir -p /var/lib/rfc2217/firmware
mkdir -p /tmp/wifi-tester

# ---------------------------------------------------------------------------
# 4. Install Python scripts
# ---------------------------------------------------------------------------
echo "Installing scripts..."
cp "$SCRIPT_DIR/portal.py"                  /usr/local/bin/rfc2217-portal
cp "$SCRIPT_DIR/plain_rfc2217_server.py"    /usr/local/bin/plain_rfc2217_server.py
cp "$SCRIPT_DIR/wifi_controller.py"         /usr/local/bin/wifi_controller.py
cp "$SCRIPT_DIR/ble_controller.py"          /usr/local/bin/ble_controller.py
cp "$SCRIPT_DIR/cw_beacon.py"              /usr/local/bin/cw_beacon.py
cp "$SCRIPT_DIR/bcm_gpio.py"                /usr/local/bin/bcm_gpio.py
cp "$SCRIPT_DIR/gpclk.py"                   /usr/local/bin/gpclk.py
cp "$SCRIPT_DIR/morse.py"                   /usr/local/bin/morse.py
cp "$SCRIPT_DIR/si5351.py"                  /usr/local/bin/si5351.py
cp "$SCRIPT_DIR/pe4302.py"                  /usr/local/bin/pe4302.py
cp "$SCRIPT_DIR/signal_generator.py"        /usr/local/bin/signal_generator.py
cp "$SCRIPT_DIR/debug_controller.py"       /usr/local/bin/debug_controller.py
cp "$SCRIPT_DIR/mqtt_controller.py"         /usr/local/bin/mqtt_controller.py
cp "$SCRIPT_DIR/sniffer.py"                 /usr/local/bin/sniffer.py
cp "$SCRIPT_DIR/rfc2217-learn-slots"        /usr/local/bin/rfc2217-learn-slots

chmod +x /usr/local/bin/rfc2217-portal
chmod +x /usr/local/bin/plain_rfc2217_server.py
chmod +x /usr/local/bin/rfc2217-learn-slots

# ---------------------------------------------------------------------------
# 5. Install helper scripts
# ---------------------------------------------------------------------------
echo "Installing helper scripts..."
cp "$SCRIPT_DIR/scripts/rfc2217-udev-notify.sh" /usr/local/bin/rfc2217-udev-notify.sh
chmod +x /usr/local/bin/rfc2217-udev-notify.sh

cp "$SCRIPT_DIR/scripts/wifi-lease-notify.sh" /usr/local/bin/wifi-lease-notify.sh
chmod +x /usr/local/bin/wifi-lease-notify.sh

# ---------------------------------------------------------------------------
# 6. Install config files (don't overwrite existing)
# ---------------------------------------------------------------------------
# No default workbench.json — the portal auto-detects Pi model and USB
# hub topology on startup. Users who want custom labels/pins can create
# /etc/rfc2217/workbench.json manually (see pi/config/examples/).
echo "Slot config: auto-detected at runtime from USB topology"

if [ ! -f /etc/rfc2217/signalgen.json ]; then
    echo "Installing default signal generator config..."
    cp "$SCRIPT_DIR/config/signalgen.json" /etc/rfc2217/signalgen.json
else
    echo "Signal generator config already exists, skipping..."
fi

# Mosquitto test broker config
if [ "$UPDATE_ONLY" = false ]; then
    echo "Installing MQTT broker config..."
    cp "$SCRIPT_DIR/config/mosquitto-test-broker.conf" /etc/mosquitto/conf.d/test-broker.conf
    # Create empty password file if it doesn't exist
    touch /etc/mosquitto/passwd
    chown mosquitto:mosquitto /etc/mosquitto/passwd
fi

# ---------------------------------------------------------------------------
# 7. Install systemd service and udev rules
# ---------------------------------------------------------------------------
echo "Installing systemd service and udev rules..."
cp "$SCRIPT_DIR/systemd/rfc2217-portal.service" /etc/systemd/system/
cp "$SCRIPT_DIR/udev/99-rfc2217-hotplug.rules" /etc/udev/rules.d/

# OpenOCD udev rules (Espressif USB JTAG + FTDI debug probes)
cat > /etc/udev/rules.d/60-openocd.rules << 'RULES'
# Espressif USB-Serial/JTAG (ESP32-C3, S3, C6, H2, etc.)
ATTRS{idVendor}=="303a", MODE="0666", GROUP="plugdev"
# FTDI devices (ESP-Prog, FT2232H, FT232H)
ATTRS{idVendor}=="0403", MODE="0666", GROUP="plugdev"
RULES

systemctl daemon-reload
udevadm control --reload-rules

# ---------------------------------------------------------------------------
# 8. Enable and start
# ---------------------------------------------------------------------------
echo "Enabling portal service..."
systemctl enable rfc2217-portal
systemctl restart rfc2217-portal

echo ""
echo "=== Installation complete ==="
echo ""
echo "Portal running at: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "Next steps:"
echo "  Slots auto-detect on boot. Plug in ESP32s and browse the portal."
echo "  Custom config (optional): sudo nano /etc/rfc2217/workbench.json"
