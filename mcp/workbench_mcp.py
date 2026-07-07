#!/usr/bin/env python3
"""MCP server for the Universal Embedded Workbench — zero dependencies.

Exposes the workbench HTTP API (http://<host>:8080/api/...) as MCP tools, so any
MCP client (Claude Code, Claude Desktop, ...) can drive the bench — SDR, signal
generator, flashing, OTA, serial, WiFi/provisioning, MQTT, BLE, GPIO, debug.

It is a thin proxy: each tool maps 1:1 to an endpoint (one SPECS row). Implemented
with the Python standard library only (stdio JSON-RPC + urllib), so it runs on any
Python 3 with no `pip install` — which is what lets it ship as a one-file .mcpb
Desktop extension.

Run (stdio):  WORKBENCH_URL=http://192.168.0.87:8080 python3 workbench_mcp.py
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("WORKBENCH_URL", "http://192.168.0.87:8080").rstrip("/")

S_INT = {"type": "integer"}
S_NUM = {"type": "number"}
S_STR = {"type": "string"}
S_BOOL = {"type": "boolean"}


def p(**props):
    return props


# name -> spec. GET => args become query params; POST => JSON body;
# UPLOAD => the multipart file endpoints (flash/ota), handled specially.
SPECS = [
    dict(name="workbench_devices", method="GET", path="/api/devices",
         desc="List USB slots and connected devices (topology, ports, chip, state)."),
    dict(name="workbench_info", method="GET", path="/api/info", desc="Workbench host/system info."),
    dict(name="workbench_log", method="GET", path="/api/log", desc="Recent activity-log entries."),

    dict(name="flash", method="UPLOAD", path="/api/flash",
         desc="Flash a board on a USB slot via local-Pi esptool (classic ESP32 behind "
              "CP2102/CH340/CH9102). Provide bins as {offset: local_path}, e.g. "
              '{"0x1000":"bootloader.bin","0x8000":"partitions.bin","0xe000":"boot_app0.bin",'
              '"0x10000":"firmware.bin"}.',
         props=p(slot=dict(**S_STR, description="Slot label e.g. SLOT3"),
                 bins={"type": "object", "description": "offset -> local .bin path",
                       "additionalProperties": S_STR},
                 chip=dict(**S_STR, default="esp32"), baud=dict(**S_STR, default="921600"),
                 erase=dict(**S_BOOL, default=False)),
         required=["slot", "bins"], timeout=240),
    dict(name="ota", method="UPLOAD", path="/api/ota",
         desc="OTA-flash a deployed (off-USB, on-LAN) board via espota relayed by the Pi. "
              "Reads firmware_path locally and uploads it.",
         props=p(target=dict(**S_STR, description="board IP or hostname"),
                 firmware_path=dict(**S_STR, description="local path to firmware .bin"),
                 port=dict(**S_INT, default=3232), auth=dict(**S_STR, default="")),
         required=["target", "firmware_path"], timeout=220),
    dict(name="firmware_list", method="GET", path="/api/firmware/list", desc="List stored firmware images."),

    dict(name="serial_reset", method="POST", path="/api/serial/reset",
         desc="Reboot the DUT on a slot (DTR/RTS) and capture boot output.",
         props=p(slot=S_STR), required=["slot"], timeout=40),
    dict(name="serial_monitor", method="POST", path="/api/serial/monitor",
         desc="Read serial for up to `timeout` s, optionally returning when `pattern` matches.",
         props=p(slot=S_STR, pattern=S_STR, timeout=dict(**S_INT, default=10)),
         required=["slot"], timeout=90),
    dict(name="serial_output", method="GET", path="/api/serial/output",
         desc="Passive read of the slot's serial buffer.",
         props=p(slot=S_STR, lines=dict(**S_INT, default=40), since=S_INT), required=["slot"]),
    dict(name="serial_recover", method="POST", path="/api/serial/recover",
         desc="Trigger manual flap recovery on a slot.", props=p(slot=S_STR), required=["slot"]),
    dict(name="serial_release", method="POST", path="/api/serial/release",
         desc="Release GPIO after flashing and reboot the slot.", props=p(slot=S_STR), required=["slot"]),

    dict(name="sdr_status", method="GET", path="/api/sdr/status", desc="RTL-SDR dongle + tool detection, active state."),
    dict(name="sdr_capture", method="POST", path="/api/sdr/capture",
         desc="Bounded rtl_433 decode window -> decoded records + signal levels.",
         props=p(freq_hz=dict(**S_INT, default=433920000), duration_s=dict(**S_INT, default=10),
                 gain=dict(**S_NUM, description="fixed tuner gain dB; omit for AGC"),
                 sample_rate=dict(**S_INT, default=250000), flex=dict(**S_STR, description="rtl_433 -X spec")),
         timeout=90),
    dict(name="sdr_analyze", method="POST", path="/api/sdr/analyze",
         desc="Bounded pulse-analyzer (-A) window -> raw pulse timing + RSSI (decode-independent).",
         props=p(freq_hz=dict(**S_INT, default=433920000), duration_s=dict(**S_INT, default=12),
                 gain=S_NUM, sample_rate=dict(**S_INT, default=250000)), timeout=90),
    dict(name="sdr_power", method="POST", path="/api/sdr/power",
         desc="Narrowband rtl_power sweep -> {peak_db, peak_freq_hz, mean_db}.",
         props=p(freq_hz=dict(**S_INT, default=433920000), duration_s=dict(**S_INT, default=5),
                 span_hz=dict(**S_INT, default=500000), bin_hz=dict(**S_INT, default=10000)), timeout=60),
    dict(name="sdr_acquire", method="POST", path="/api/sdr/acquire",
         desc="Phased guided receive: locate -> level -> decode -> classify.",
         props=p(freq_hz=dict(**S_INT, default=433920000)), timeout=120),
    dict(name="sdr_live_start", method="POST", path="/api/sdr/live/start",
         desc="Start the persistent live rtl_433 console (fast-poll ring buffer).",
         props=p(freqs={"type": "array", "items": S_INT}, mode=dict(**S_STR, description="decode|flex|analyze"),
                 gain=S_NUM, sample_rate=dict(**S_INT, default=250000), squelch=S_BOOL,
                 hop_interval=S_INT, flex=S_STR, isolate=S_BOOL)),
    dict(name="sdr_live_stop", method="POST", path="/api/sdr/live/stop", desc="Stop the live console, release the dongle."),
    dict(name="sdr_live_status", method="GET", path="/api/sdr/live/status", desc="Live console running state + config."),
    dict(name="sdr_live_poll", method="GET", path="/api/sdr/live",
         desc="Poll the live ring buffer since a sequence number.", props=p(since=dict(**S_INT, default=0))),
    dict(name="sdr_reset", method="POST", path="/api/sdr/reset", desc="USB-reset a wedged dongle."),
    dict(name="sdr_stop", method="POST", path="/api/sdr/stop", desc="Terminate an in-progress one-shot capture."),
    dict(name="sdr_log_start", method="POST", path="/api/sdr/log/start", desc="Begin recording the live stream (AI Sherlock)."),
    dict(name="sdr_log_stop", method="POST", path="/api/sdr/log/stop", desc="Stop recording; returns line count."),
    dict(name="sdr_log_get", method="GET", path="/api/sdr/log", desc="Retrieve the recorded session lines."),

    dict(name="siggen_status", method="GET", path="/api/siggen/status", desc="Signal generator backend + attenuator presence."),
    dict(name="siggen_start", method="POST", path="/api/siggen/start",
         desc="Start RF output (continuous carrier or Morse/CW).",
         props=p(freq_hz=S_INT, morse=dict(**S_STR, description="text to key (optional)"),
                 wpm=S_INT, backend=S_STR)),
    dict(name="siggen_stop", method="POST", path="/api/siggen/stop", desc="Stop RF output."),
    dict(name="siggen_freq", method="POST", path="/api/siggen/freq", desc="Retune the carrier.", props=p(freq_hz=S_INT), required=["freq_hz"]),
    dict(name="siggen_atten", method="POST", path="/api/siggen/atten", desc="Set PE4302 attenuation (dB).", props=p(db=S_NUM), required=["db"]),
    dict(name="siggen_frequencies", method="GET", path="/api/siggen/frequencies", desc="List preset frequencies."),

    dict(name="wifi_mode", method="GET", path="/api/wifi/mode", desc="Current WiFi mode."),
    dict(name="wifi_mode_set", method="POST", path="/api/wifi/mode", desc="Set WiFi mode.", props=p(mode=S_STR), required=["mode"]),
    dict(name="wifi_scan", method="GET", path="/api/wifi/scan", desc="Scan for WiFi networks."),
    dict(name="wifi_ap_start", method="POST", path="/api/wifi/ap_start",
         desc="Start a SoftAP (optionally NAT-bridged to the LAN).",
         props=p(ssid=S_STR, password=S_STR, internet=dict(**S_BOOL, default=False)), required=["ssid"]),
    dict(name="wifi_ap_stop", method="POST", path="/api/wifi/ap_stop", desc="Stop the SoftAP."),
    dict(name="wifi_ap_status", method="GET", path="/api/wifi/ap_status", desc="SoftAP state + connected stations."),
    dict(name="wifi_sta_join", method="POST", path="/api/wifi/sta_join", desc="Join a WiFi network as a station.",
         props=p(ssid=S_STR, **{"pass": S_STR}, timeout=dict(**S_INT, default=15)), required=["ssid"], timeout=40),
    dict(name="wifi_sta_leave", method="POST", path="/api/wifi/sta_leave", desc="Leave the joined network."),
    dict(name="wifi_http", method="POST", path="/api/wifi/http",
         desc="Relay an HTTP request to a device on the test network.",
         props=p(method=dict(**S_STR, default="GET"), url=S_STR, timeout=dict(**S_INT, default=10)),
         required=["url"], timeout=40),
    dict(name="wifi_ping", method="GET", path="/api/wifi/ping", desc="WiFi reachability check."),
    dict(name="enter_portal", method="POST", path="/api/enter-portal",
         desc="Provision a captive-portal DUT onto the workbench AP (WiFiManager: pass "
              "portal_ssid, ssid, password, save_path=/wifisave, field_ssid=s, field_password=p, "
              "method=POST, internet=true, extra={host,port}); or trigger the portal with {slot,resets}.",
         props=p(portal_ssid=S_STR, ssid=S_STR, password=S_STR, save_path=S_STR, field_ssid=S_STR,
                 field_password=S_STR, method=S_STR, internet=S_BOOL, extra={"type": "object"},
                 slot=S_STR, resets=S_INT), timeout=40),

    dict(name="mqtt_status", method="GET", path="/api/mqtt/status", desc="Test broker state."),
    dict(name="mqtt_start", method="POST", path="/api/mqtt/start", desc="Start the mosquitto test broker."),
    dict(name="mqtt_stop", method="POST", path="/api/mqtt/stop", desc="Stop the test broker."),

    dict(name="ble_status", method="GET", path="/api/ble/status", desc="BLE bridge state."),
    dict(name="ble_scan", method="POST", path="/api/ble/scan", desc="Scan for BLE peripherals.",
         props=p(timeout=dict(**S_INT, default=5), name_filter=S_STR), timeout=40),
    dict(name="ble_connect", method="POST", path="/api/ble/connect", desc="Connect to a BLE device.", props=p(address=S_STR), required=["address"]),
    dict(name="ble_disconnect", method="POST", path="/api/ble/disconnect", desc="Disconnect BLE."),
    dict(name="ble_write", method="POST", path="/api/ble/write", desc="Write to a GATT characteristic (hex data).",
         props=p(characteristic=S_STR, data=S_STR, response=dict(**S_BOOL, default=True)), required=["characteristic", "data"]),

    dict(name="gpio_status", method="GET", path="/api/gpio/status", desc="GPIO state."),
    dict(name="gpio_set", method="POST", path="/api/gpio/set", desc="Set a GPIO pin (value 0/1/'z').",
         props=p(pin=S_INT, value=S_STR), required=["pin", "value"]),

    dict(name="debug_status", method="GET", path="/api/debug/status", desc="Debug (OpenOCD) state."),
    dict(name="debug_probes", method="GET", path="/api/debug/probes", desc="List attached debug probes."),
    dict(name="debug_start", method="POST", path="/api/debug/start", desc="Start OpenOCD for a slot.", props=p(slot=S_STR), required=["slot"], timeout=40),
    dict(name="debug_stop", method="POST", path="/api/debug/stop", desc="Stop OpenOCD for a slot.", props=p(slot=S_STR), required=["slot"]),

    dict(name="test_progress", method="GET", path="/api/test/progress", desc="Test-session progress."),
    dict(name="human_status", method="GET", path="/api/human/status", desc="Pending operator-interaction request."),

    dict(name="proxy_start", method="POST", path="/api/start", desc="Start the RFC2217 proxy for a slot.", props=p(slot_key=S_STR, devnode=S_STR)),
    dict(name="proxy_stop", method="POST", path="/api/stop", desc="Stop the RFC2217 proxy for a slot.", props=p(slot_key=S_STR)),
]
SPEC_BY_NAME = {s["name"]: s for s in SPECS}


# ---- HTTP (urllib) ----------------------------------------------------------
def _multipart(boundary, fields, files):
    out = bytearray()
    for k, v in fields.items():
        out += ("--%s\r\n" % boundary).encode()
        out += ('Content-Disposition: form-data; name="%s"\r\n\r\n' % k).encode()
        out += ("%s\r\n" % v).encode()
    for name, fname, content in files:
        out += ("--%s\r\n" % boundary).encode()
        out += ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (name, fname)).encode()
        out += b"Content-Type: application/octet-stream\r\n\r\n"
        out += content + b"\r\n"
    out += ("--%s--\r\n" % boundary).encode()
    return bytes(out)


def _upload_parts(spec, args):
    if spec["name"] == "ota":
        with open(args["firmware_path"], "rb") as f:
            fw = f.read()
        fields = {"target": args["target"], "port": str(args.get("port", 3232))}
        if args.get("auth"):
            fields["auth"] = args["auth"]
        return fields, [("firmware", "firmware.bin", fw)]
    if spec["name"] == "flash":
        fields = {"slot": args["slot"], "chip": args.get("chip", "esp32"), "baud": args.get("baud", "921600")}
        if args.get("erase"):
            fields["erase"] = "1"
        files = []
        for offset, path in (args.get("bins") or {}).items():
            with open(path, "rb") as f:
                files.append(("bin@" + offset, os.path.basename(path), f.read()))
        return fields, files
    return {}, []


def _http(spec, args):
    url = BASE + spec["path"]
    method = spec["method"]
    to = spec.get("timeout", 30)
    if method == "GET":
        q = {k: v for k, v in args.items() if v is not None}
        if q:
            url += "?" + urllib.parse.urlencode(q)
        req = urllib.request.Request(url, method="GET")
    elif method == "POST":
        body = json.dumps({k: v for k, v in args.items() if v is not None}).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    elif method == "UPLOAD":
        fields, files = _upload_parts(spec, args)
        boundary = "----wbmcp" + os.urandom(8).hex()
        req = urllib.request.Request(url, data=_multipart(boundary, fields, files), method="POST",
                                     headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    else:
        return {"ok": False, "error": "bad method " + method}
    try:
        with urllib.request.urlopen(req, timeout=to) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        data = e.read()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    try:
        return json.loads(data)
    except ValueError:
        return {"text": data.decode("utf-8", "replace")[:4000]}


# ---- MCP stdio JSON-RPC (stdlib) --------------------------------------------
class _RpcError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def _tool_defs():
    return [{"name": s["name"],
             "description": "%s  [%s %s]" % (s["desc"], s["method"], s["path"]),
             "inputSchema": {"type": "object", "properties": s.get("props", {}), "required": s.get("required", [])}}
            for s in SPECS]


def _handle(req):
    m = req.get("method")
    if m == "initialize":
        pv = (req.get("params") or {}).get("protocolVersion") or "2025-06-18"
        return {"protocolVersion": pv, "capabilities": {"tools": {}},
                "serverInfo": {"name": "universal-embedded-workbench", "version": "1.0.0"}}
    if m == "tools/list":
        return {"tools": _tool_defs()}
    if m == "tools/call":
        params = req.get("params") or {}
        spec = SPEC_BY_NAME.get(params.get("name"))
        if not spec:
            return {"content": [{"type": "text", "text": json.dumps({"error": "unknown tool " + str(params.get('name'))})}],
                    "isError": True}
        result = _http(spec, params.get("arguments") or {})
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}
    if m == "ping":
        return {}
    raise _RpcError(-32601, "method not found: " + str(m))


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        if req.get("id") is None:  # notification (e.g. notifications/initialized) -> no reply
            continue
        try:
            resp = {"jsonrpc": "2.0", "id": req["id"], "result": _handle(req)}
        except _RpcError as e:
            resp = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": e.code, "message": e.message}}
        except Exception as e:  # noqa: BLE001
            resp = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32000, "message": "%s: %s" % (type(e).__name__, e)}}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
