"""GDB debug manager — OpenOCD lifecycle, chip auto-detection, probe allocation.

Manages OpenOCD processes for remote GDB debugging of ESP32 devices.
Supports three modes:
  - USB JTAG (FR-024): built-in USB-Serial/JTAG on C3/S3/C6/H2
  - Dual-USB (FR-025): S3 with both USB ports connected
  - ESP-Prog (FR-026): external FT2232H probe for all ESP32 variants
"""

import os
import signal
import socket
import subprocess
import threading
import time

# OpenOCD paths and defaults
OPENOCD_EXE = os.environ.get(
    "OPENOCD_EXE", "/usr/local/bin/openocd-esp32")
OPENOCD_SCRIPTS = os.environ.get(
    "OPENOCD_SCRIPTS", "/usr/local/share/openocd-esp32/scripts")
OPENOCD_START_TIMEOUT = 5.0

# Per-chip OpenOCD board configs (USB JTAG built-in)
BUILTIN_CONFIGS = {
    "esp32c3": "board/esp32c3-builtin.cfg",
    "esp32c6": "board/esp32c6-builtin.cfg",
    "esp32h2": "board/esp32h2-builtin.cfg",
    "esp32s3": "board/esp32s3-builtin.cfg",
}

# Per-chip OpenOCD target configs (for use with external probes)
PROBE_TARGET_CONFIGS = {
    "esp32":   "target/esp32.cfg",
    "esp32c3": "target/esp32c3.cfg",
    "esp32c6": "target/esp32c6.cfg",
    "esp32h2": "target/esp32h2.cfg",
    "esp32s2": "target/esp32s2.cfg",
    "esp32s3": "target/esp32s3.cfg",
}

# JTAG TAP ID → chip mapping (for auto-detection)
TAP_ID_MAP = {
    0x00005C25: "esp32c3",
    0x0000DC25: "esp32c6",
    0x00010C25: "esp32h2",
    0x120034E5: "esp32s3",
}

# Module state
_lock = threading.Lock()
_sessions: dict[str, dict] = {}   # slot_label → session info
_probes: dict[str, dict] = {}     # probe_label → probe state


def _is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is accepting connections."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect((host, port))
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


def _wait_for_port(port: int, timeout: float = OPENOCD_START_TIMEOUT) -> bool:
    """Poll until a TCP port is listening or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_port_listening(port):
            return True
        time.sleep(0.2)
    return False


def _kill_process(pid: int, timeout: float = 5.0):
    """Send SIGTERM and wait, then SIGKILL if needed."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)  # check if alive
            time.sleep(0.2)
        except ProcessLookupError:
            return
    # Force kill
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _unbind_ftdi_interface(bus_port: str):
    """Unbind an FTDI interface from ftdi_sio kernel driver."""
    unbind_path = "/sys/bus/usb/drivers/ftdi_sio/unbind"
    try:
        with open(unbind_path, "w") as f:
            f.write(bus_port)
    except OSError as e:
        # May already be unbound
        print(f"[debug] unbind {bus_port}: {e}", flush=True)


def _rebind_ftdi_interface(bus_port: str):
    """Rebind an FTDI interface to ftdi_sio kernel driver."""
    bind_path = "/sys/bus/usb/drivers/ftdi_sio/bind"
    try:
        with open(bind_path, "w") as f:
            f.write(bus_port)
    except OSError as e:
        print(f"[debug] rebind {bus_port}: {e}", flush=True)


# ── Public API ───────────────────────────────────────────────────────

def start(slot_label: str, slot: dict, gdb_port: int, telnet_port: int,
          chip: str | None = None, probe: str | None = None) -> dict:
    """Start OpenOCD debug session for a slot.

    Args:
        slot_label: Slot label (e.g. "SLOT1")
        slot: Slot dict from portal (must have 'present', 'state', etc.)
        gdb_port: TCP port for GDB RSP
        telnet_port: TCP port for OpenOCD telnet
        chip: Chip type (e.g. "esp32c3"). If None, must be auto-detected.
        probe: Probe label for ESP-Prog mode. If None, uses USB JTAG.

    Returns:
        Result dict with ok, gdb_port, telnet_port, chip, etc.
    """
    with _lock:
        if slot_label in _sessions:
            return {"ok": False,
                    "error": f"{slot_label} already in debug mode"}

        if not slot.get("present"):
            return {"ok": False,
                    "error": f"no device in {slot_label}"}

        # Build OpenOCD command
        cmd = [OPENOCD_EXE, "-s", OPENOCD_SCRIPTS]

        if probe:
            # ESP-Prog mode (FR-026)
            probe_info = _probes.get(probe)
            if not probe_info:
                return {"ok": False, "error": f"probe '{probe}' not found"}
            if probe_info.get("in_use"):
                return {"ok": False,
                        "error": f"probe '{probe}' already in use by "
                                 f"{probe_info.get('slot')}"}
            if not chip:
                return {"ok": False,
                        "error": "chip type required for probe mode"}
            if chip not in PROBE_TARGET_CONFIGS:
                return {"ok": False,
                        "error": f"unsupported chip '{chip}' for probe"}

            # Unbind FTDI channel A
            bus_port = probe_info.get("bus_port")
            if bus_port:
                _unbind_ftdi_interface(bus_port)

            cmd += ["-f", probe_info["interface_config"]]
            cmd += ["-f", PROBE_TARGET_CONFIGS[chip]]

            # Mark probe as in use
            probe_info["in_use"] = True
            probe_info["slot"] = slot_label
        else:
            # USB JTAG mode (FR-024/025)
            if not chip:
                return {"ok": False,
                        "error": "chip type required (esp32c3, esp32c6, "
                                 "esp32h2, esp32s3)"}
            if chip not in BUILTIN_CONFIGS:
                supported = ", ".join(sorted(BUILTIN_CONFIGS.keys()))
                return {"ok": False,
                        "error": f"chip '{chip}' has no USB JTAG — "
                                 f"supported: {supported}"}
            cmd += ["-f", BUILTIN_CONFIGS[chip]]

        cmd += ["-c", f"gdb port {gdb_port}"]
        cmd += ["-c", f"telnet port {telnet_port}"]
        cmd += ["-c", "bindto 0.0.0.0"]

        # Launch OpenOCD
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            return {"ok": False,
                    "error": f"openocd not found at {OPENOCD_EXE}"}
        except Exception as e:
            return {"ok": False, "error": f"failed to start openocd: {e}"}

        # Wait for GDB port to open
        if not _wait_for_port(gdb_port):
            # Read any output for error diagnosis
            output = ""
            try:
                proc.kill()
                output = proc.stdout.read()[:500] if proc.stdout else ""
            except Exception:
                pass
            if probe:
                _probes[probe]["in_use"] = False
                _probes[probe]["slot"] = None
            return {"ok": False,
                    "error": f"openocd failed to start: {output.strip()}"}

        _sessions[slot_label] = {
            "pid": proc.pid,
            "process": proc,
            "chip": chip,
            "gdb_port": gdb_port,
            "telnet_port": telnet_port,
            "probe": probe,
        }

        return {
            "ok": True,
            "slot": slot_label,
            "chip": chip,
            "gdb_port": gdb_port,
            "telnet_port": telnet_port,
            "probe": probe,
            "gdb_target": f"target extended-remote "
                          f"esp32-workbench.local:{gdb_port}",
        }


def stop(slot_label: str) -> dict:
    """Stop OpenOCD debug session for a slot."""
    with _lock:
        session = _sessions.pop(slot_label, None)
        if not session:
            return {"ok": True}  # idempotent

        _kill_process(session["pid"])

        # Release probe if used
        probe_label = session.get("probe")
        if probe_label and probe_label in _probes:
            _probes[probe_label]["in_use"] = False
            _probes[probe_label]["slot"] = None
            # Rebind FTDI channel A
            bus_port = _probes[probe_label].get("bus_port")
            if bus_port:
                _rebind_ftdi_interface(bus_port)

        return {"ok": True, "slot": slot_label}


def status() -> dict:
    """Return debug state for all slots."""
    with _lock:
        result = {}
        for label, session in _sessions.items():
            result[label] = {
                "debugging": True,
                "chip": session["chip"],
                "gdb_port": session["gdb_port"],
                "telnet_port": session["telnet_port"],
                "pid": session["pid"],
                "probe": session.get("probe"),
            }
        return result


def is_debugging(slot_label: str) -> bool:
    """Check if a slot is in debug mode."""
    with _lock:
        return slot_label in _sessions


def get_probes() -> list[dict]:
    """Return list of configured debug probes."""
    with _lock:
        return [
            {
                "label": label,
                "type": info.get("type", "unknown"),
                "in_use": info.get("in_use", False),
                "slot": info.get("slot"),
            }
            for label, info in _probes.items()
        ]


def load_probes(probe_configs: list[dict]):
    """Load probe configuration from slots.json."""
    with _lock:
        for cfg in probe_configs:
            label = cfg["label"]
            _probes[label] = {
                "type": cfg.get("type", "esp-prog"),
                "interface_config": cfg.get(
                    "interface_config",
                    "interface/ftdi/esp_ftdi.cfg"),
                "usb_serial": cfg.get("usb_serial"),
                "bus_port": cfg.get("bus_port"),
                "in_use": False,
                "slot": None,
            }
        if _probes:
            labels = ", ".join(_probes.keys())
            print(f"[debug] loaded {len(_probes)} probe(s): {labels}",
                  flush=True)


def shutdown():
    """Stop all debug sessions — called on portal shutdown."""
    with _lock:
        for label in list(_sessions.keys()):
            session = _sessions.pop(label)
            _kill_process(session["pid"])
            probe_label = session.get("probe")
            if probe_label and probe_label in _probes:
                _probes[probe_label]["in_use"] = False
                _probes[probe_label]["slot"] = None
