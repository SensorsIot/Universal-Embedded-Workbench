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
    pip3 install esptool bleak --break-system-packages 2>/dev/null || true
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
if [ ! -f /etc/rfc2217/slots.json ]; then
    echo "Installing default slot config..."
    cp "$SCRIPT_DIR/config/slots.json" /etc/rfc2217/slots.json
else
    echo "Slot config already exists, skipping..."
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
echo "  1. Discover slot keys:  rfc2217-learn-slots"
echo "  2. Edit config:         sudo nano /etc/rfc2217/slots.json"
echo "  3. Restart portal:      sudo systemctl restart rfc2217-portal"
