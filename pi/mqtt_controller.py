"""
MQTT Controller — manages a mosquitto broker for ESP32 MQTT client testing.

Used by the portal to start/stop a local MQTT broker accessible to devices
on the workbench WiFi AP.
"""

import logging
import os
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MQTT_PORT = 1883
WORK_DIR = "/tmp/mqtt-tester"
MOSQUITTO_CONF = os.path.join(WORK_DIR, "mosquitto.conf")
MOSQUITTO_LOG = os.path.join(WORK_DIR, "mosquitto.log")

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_active = False
_proc = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_work_dir():
    os.makedirs(WORK_DIR, exist_ok=True)


def _kill_proc(proc, timeout=5.0):
    """Terminate a subprocess, SIGKILL if it won't die."""
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        return
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass


def _kill_existing():
    """Kill any existing mosquitto process (best effort)."""
    try:
        subprocess.run(
            ["pkill", "-f", "mosquitto"],
            capture_output=True, timeout=5, check=False,
        )
        time.sleep(0.3)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start():
    """Start the mosquitto MQTT broker. Returns dict with port."""
    global _active, _proc

    with _lock:
        if _active and _proc is not None and _proc.poll() is None:
            return {"port": MQTT_PORT}

        _ensure_work_dir()
        _kill_existing()

        # Write mosquitto config — open broker, no auth, listen on all interfaces
        conf_lines = [
            f"listener {MQTT_PORT}",
            "allow_anonymous true",
            f"log_dest file {MOSQUITTO_LOG}",
            "log_type all",
        ]
        with open(MOSQUITTO_CONF, "w") as f:
            f.write("\n".join(conf_lines) + "\n")

        # Start mosquitto
        _proc = subprocess.Popen(
            ["mosquitto", "-c", MOSQUITTO_CONF],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )

        # Wait for it to initialise
        time.sleep(1.0)
        if _proc.poll() is not None:
            out = _proc.stdout.read().decode(errors="replace")
            _active = False
            raise RuntimeError(f"mosquitto failed to start: {out[:500]}")

        _active = True
        logger.info("MQTT broker started on port %d", MQTT_PORT)
        return {"port": MQTT_PORT}


def stop():
    """Stop the mosquitto broker."""
    global _active, _proc

    with _lock:
        _kill_proc(_proc)
        _proc = None
        _active = False
        logger.info("MQTT broker stopped")


def status():
    """Return broker status dict."""
    global _active

    with _lock:
        running = _active and _proc is not None and _proc.poll() is None
        # If process died unexpectedly, update state
        if _active and not running:
            _active = False
        return {
            "running": running,
            "port": MQTT_PORT if running else None,
        }
