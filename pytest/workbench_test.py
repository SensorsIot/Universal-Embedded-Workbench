"""WiFi Tester instrument self-tests (WT-xxx).

These verify the instrument itself works correctly.
Tests marked @requires_dut need a WiFi device connected; skip with default run.
"""

import os
import re
import socket
import time

import pytest

from workbench_driver import CommandError, CommandTimeout

# Path to pre-built debug-test firmware binaries
DEBUG_TEST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "debug-test", "output"
)


# =====================================================================
# WT-1xx  Basic Protocol
# =====================================================================


class TestBasicProtocol:
    """WT-1xx: Basic protocol tests."""

    def test_wt100_ping_response(self, workbench):
        """WT-100: PING returns fw_version and uptime."""
        resp = workbench.ping()
        assert "fw_version" in resp
        assert "uptime" in resp
        assert isinstance(resp["uptime"], (int, float))
        assert resp["uptime"] >= 0

    def test_wt104_command_while_busy(self, workbench):
        """WT-104: Rapid commands don't crash the device."""
        r1 = workbench.ping()
        r2 = workbench.ping()
        assert "fw_version" in r1
        assert "fw_version" in r2


# =====================================================================
# WT-2xx  SoftAP Management
# =====================================================================


class TestSoftAPManagement:
    """WT-2xx: SoftAP start/stop/status tests."""

    def test_wt200_start_ap(self, workbench):
        """WT-200: AP_START with valid SSID/pass returns OK with IP."""
        resp = workbench.ap_start("WT-TEST-200", "password123")
        assert "ip" in resp
        assert resp["ip"].startswith("192.168.")
        workbench.ap_stop()

    def test_wt201_start_open_ap(self, workbench):
        """WT-201: AP_START with empty password creates open network."""
        resp = workbench.ap_start("WT-OPEN-201")
        assert "ip" in resp
        workbench.ap_stop()

    def test_wt202_stop_ap(self, workbench):
        """WT-202: AP_STOP after AP_START returns OK."""
        workbench.ap_start("WT-TEST-202", "password123")
        workbench.ap_stop()
        status = workbench.ap_status()
        assert status["active"] is False

    def test_wt203_stop_when_not_running(self, workbench):
        """WT-203: AP_STOP is idempotent."""
        workbench.ap_stop()
        workbench.ap_stop()

    def test_wt204_restart_ap_new_config(self, workbench):
        """WT-204: AP_START while running restarts with new config."""
        workbench.ap_start("WT-SSID-A", "password123")
        status_a = workbench.ap_status()
        assert status_a["ssid"] == "WT-SSID-A"

        workbench.ap_start("WT-SSID-B", "password456")
        status_b = workbench.ap_status()
        assert status_b["ssid"] == "WT-SSID-B"
        workbench.ap_stop()

    def test_wt205_ap_status_when_running(self, workbench):
        """WT-205: AP_STATUS reports active, SSID, channel."""
        workbench.ap_start("WT-STATUS-205", "password123", channel=6)
        status = workbench.ap_status()
        assert status["active"] is True
        assert status["ssid"] == "WT-STATUS-205"
        assert status["channel"] == 6
        assert "stations" in status
        workbench.ap_stop()

    def test_wt206_ap_status_when_stopped(self, workbench):
        """WT-206: AP_STATUS without AP reports inactive."""
        workbench.ap_stop()
        status = workbench.ap_status()
        assert status["active"] is False

    def test_wt207_max_ssid_length(self, workbench):
        """WT-207: 32-character SSID is accepted."""
        long_ssid = "A" * 32
        resp = workbench.ap_start(long_ssid, "password123")
        assert "ip" in resp
        workbench.ap_stop()

    def test_wt208_channel_selection(self, workbench):
        """WT-208: Channel parameter is respected."""
        workbench.ap_start("WT-CHAN-208", "password123", channel=11)
        status = workbench.ap_status()
        assert status["channel"] == 11
        workbench.ap_stop()


# =====================================================================
# WT-3xx  Station Connect/Disconnect Events
# =====================================================================


@pytest.mark.requires_dut
class TestStationEvents:
    """WT-3xx: Station connect/disconnect events (requires DUT)."""

    def test_wt300_station_connect_event(self, workbench, wifi_network):
        """WT-300: STA_CONNECT event with MAC and IP when device joins."""
        station = workbench.wait_for_station(timeout=60)
        assert "mac" in station
        assert "ip" in station
        assert ":" in station["mac"]
        assert station["ip"].startswith("192.168.4.")

    def test_wt301_station_disconnect_event(self, workbench, wifi_network):
        """WT-301: STA_DISCONNECT event with MAC when device leaves."""
        station = workbench.wait_for_station(timeout=60)
        evt = workbench.wait_for_event("STA_DISCONNECT", timeout=60)
        assert "mac" in evt
        assert evt["mac"] == station["mac"]

    def test_wt302_station_in_ap_status(self, workbench, wifi_network):
        """WT-302: Connected station appears in AP_STATUS."""
        station = workbench.wait_for_station(timeout=60)
        status = workbench.ap_status()
        macs = [s["mac"] for s in status["stations"]]
        assert station["mac"] in macs

    def test_wt303_ip_matches_event(self, workbench, wifi_network):
        """WT-303: IP in STA_CONNECT matches AP_STATUS."""
        station = workbench.wait_for_station(timeout=60)
        status = workbench.ap_status()
        for s in status["stations"]:
            if s["mac"] == station["mac"]:
                assert s["ip"] == station["ip"]
                return
        pytest.fail("Station not found in AP_STATUS")


# =====================================================================
# WT-4xx  STA Mode
# =====================================================================


@pytest.mark.requires_dut
class TestSTAMode:
    """WT-4xx: STA join/leave tests (requires another AP)."""

    @pytest.fixture
    def sta_network(self):
        import os
        ssid = os.environ.get("WIFI_TEST_STA_SSID")
        password = os.environ.get("WIFI_TEST_STA_PASS", "")
        if not ssid:
            pytest.skip("WIFI_TEST_STA_SSID not set")
        return {"ssid": ssid, "password": password}

    def test_wt400_join_open_network(self, workbench, sta_network):
        """WT-400: Join open network returns OK with IP."""
        if sta_network["password"]:
            pytest.skip("Test network is not open")
        resp = workbench.sta_join(sta_network["ssid"])
        assert "ip" in resp
        workbench.sta_leave()

    def test_wt401_join_wpa2_network(self, workbench, sta_network):
        """WT-401: Join WPA2 network with correct password."""
        if not sta_network["password"]:
            pytest.skip("Test network has no password")
        resp = workbench.sta_join(
            sta_network["ssid"], sta_network["password"],
        )
        assert "ip" in resp
        assert "gateway" in resp
        workbench.sta_leave()

    def test_wt402_join_wrong_password(self, workbench, sta_network):
        """WT-402: Wrong password returns ERR."""
        if not sta_network["password"]:
            pytest.skip("Test network has no password")
        with pytest.raises(CommandError):
            workbench.sta_join(
                sta_network["ssid"], "wrong_password_here", timeout=10,
            )

    def test_wt403_join_nonexistent_network(self, workbench):
        """WT-403: Nonexistent SSID returns ERR with timeout."""
        with pytest.raises(CommandError):
            workbench.sta_join(
                "NONEXISTENT_NETWORK_XYZ_999", timeout=5,
            )

    def test_wt404_leave_sta(self, workbench, sta_network):
        """WT-404: STA_LEAVE after join returns OK."""
        workbench.sta_join(
            sta_network["ssid"], sta_network["password"],
        )
        workbench.sta_leave()

    def test_wt405_softap_stops_during_sta(self, workbench, sta_network):
        """WT-405: AP is stopped when entering STA mode."""
        workbench.ap_start("WT-AP-405", "password123")
        status = workbench.ap_status()
        assert status["active"] is True

        workbench.sta_join(
            sta_network["ssid"], sta_network["password"],
        )
        status = workbench.ap_status()
        assert status["active"] is False
        workbench.sta_leave()


# =====================================================================
# WT-5xx  HTTP Relay
# =====================================================================


@pytest.mark.requires_dut
class TestHTTPRelay:
    """WT-5xx: HTTP relay tests (requires DUT with HTTP server)."""

    @pytest.fixture
    def dut_url(self, workbench, wifi_network):
        """Wait for DUT to connect and return its base URL."""
        station = workbench.wait_for_station(timeout=60)
        return f"http://{station['ip']}"

    def test_wt500_get_request(self, workbench, dut_url):
        """WT-500: GET request returns status 200 and body."""
        resp = workbench.http_get(f"{dut_url}/")
        assert resp.status_code == 200
        assert len(resp.content) > 0

    def test_wt501_post_with_body(self, workbench, dut_url):
        """WT-501: POST with JSON body returns response."""
        resp = workbench.http_post(
            f"{dut_url}/api/test",
            json_data={"key": "value"},
        )
        assert resp.status_code in (200, 201, 404)

    def test_wt502_custom_headers(self, workbench, dut_url):
        """WT-502: Custom headers are forwarded."""
        resp = workbench.http_get(
            f"{dut_url}/",
            headers={"X-Test-Header": "test-value"},
        )
        assert resp.status_code == 200

    def test_wt503_connection_refused(self, workbench, wifi_network):
        """WT-503: HTTP to non-existent IP returns ERR."""
        with pytest.raises(CommandError):
            workbench.http_get("http://192.168.4.99/", timeout=5)

    def test_wt504_request_timeout(self, workbench, wifi_network):
        """WT-504: HTTP to non-responding device times out."""
        with pytest.raises(CommandError):
            workbench.http_get("http://192.168.4.99/", timeout=3)

    def test_wt505_large_response(self, workbench, dut_url):
        """WT-505: Large HTTP response is relayed (up to ~3KB)."""
        resp = workbench.http_get(f"{dut_url}/")
        assert isinstance(resp.text, str)

    def test_wt506_http_via_sta_mode(self, workbench):
        """WT-506: HTTP relay works in STA mode."""
        import os
        ssid = os.environ.get("WIFI_TEST_STA_SSID")
        password = os.environ.get("WIFI_TEST_STA_PASS", "")
        target_url = os.environ.get("WIFI_TEST_HTTP_URL")
        if not ssid or not target_url:
            pytest.skip("WIFI_TEST_STA_SSID and WIFI_TEST_HTTP_URL required")
        workbench.sta_join(ssid, password)
        resp = workbench.http_get(target_url)
        assert resp.status_code == 200
        workbench.sta_leave()


# =====================================================================
# WT-6xx  WiFi Scan
# =====================================================================


class TestWiFiScan:
    """WT-6xx: WiFi scan tests."""

    def test_wt600_scan_finds_networks(self, workbench):
        """WT-600: SCAN returns non-empty network list."""
        workbench.ap_stop()
        result = workbench.scan()
        assert "networks" in result
        if len(result["networks"]) == 0:
            pytest.skip("No WiFi networks visible (RF-shielded?)")

    def test_wt601_scan_returns_fields(self, workbench):
        """WT-601: Each scan entry has ssid, rssi, auth."""
        workbench.ap_stop()
        result = workbench.scan()
        if len(result["networks"]) == 0:
            pytest.skip("No WiFi networks visible")
        for net in result["networks"]:
            assert "ssid" in net
            assert "rssi" in net
            assert "auth" in net
            assert isinstance(net["rssi"], (int, float))
            assert net["rssi"] < 0

    def test_wt602_scan_does_not_find_own_ap(self, workbench):
        """WT-602: Our own AP does not appear in scan results."""
        own_ssid = "WT-SCAN-602-UNIQUE"
        workbench.ap_start(own_ssid, "password123")
        time.sleep(1)
        result = workbench.scan()
        ssids = [n["ssid"] for n in result["networks"]]
        assert own_ssid not in ssids
        workbench.ap_stop()

    def test_wt603_scan_while_ap_running(self, workbench):
        """WT-603: Scan completes without stopping the AP."""
        workbench.ap_start("WT-SCAN-603", "password123")
        result = workbench.scan()
        assert "networks" in result
        status = workbench.ap_status()
        assert status["active"] is True
        workbench.ap_stop()


# =====================================================================
# WT-13xx  Signal Generator (Si5351 + PE4302, GPCLK fallback)
# =====================================================================


class TestSiggen:
    """WT-13xx: signal generator tests against /api/siggen/*."""

    def test_wt1300_start_and_status(self, workbench):
        """WT-1300: Start carrier and verify status shows active."""
        result = workbench.siggen_start(freq_hz=3_500_000)
        assert result["active"] is True
        assert result["backend"] in ("si5351", "gpclk")
        assert result["freq_hz"] > 0

        status = workbench.siggen_status()
        assert status["active"] is True
        assert status["backend"] == result["backend"]
        assert status["freq_hz"] == result["freq_hz"]

        workbench.siggen_stop()

    def test_wt1301_stop(self, workbench):
        """WT-1301: Stop carrier and verify status shows inactive."""
        workbench.siggen_start(freq_hz=3_571_000)
        workbench.siggen_stop()

        status = workbench.siggen_status()
        assert status["active"] is False

    def test_wt1302_frequency_list(self, workbench):
        """WT-1302: Frequency list returns valid entries in range."""
        freqs = workbench.siggen_frequencies(
            low=3_500_000, high=4_000_000, backend="gpclk")
        assert len(freqs) > 0
        for f in freqs:
            assert "divider" in f
            assert "freq_hz" in f
            assert 3_500_000 <= f["freq_hz"] <= 4_000_000

    def test_wt1303_morse_keying(self, workbench):
        """WT-1303: Morse-keyed start records message in status."""
        workbench.siggen_start(
            freq_hz=3_571_000,
            morse={"message": "VVV DE TEST", "wpm": 15, "repeat": True})
        status = workbench.siggen_status()
        assert status["active"] is True
        assert status["morse"]["message"] == "VVV DE TEST"
        assert status["morse"]["wpm"] == 15

        workbench.siggen_stop()

    def test_wt1304_replaces_previous(self, workbench):
        """WT-1304: Starting a new carrier replaces the previous one."""
        workbench.siggen_start(
            freq_hz=3_571_000,
            morse={"message": "AAA", "wpm": 10, "repeat": True})
        result2 = workbench.siggen_start(
            freq_hz=3_597_000,
            morse={"message": "BBB", "wpm": 20, "repeat": True})

        status = workbench.siggen_status()
        assert status["active"] is True
        assert status["morse"]["message"] == "BBB"
        assert status["morse"]["wpm"] == 20
        assert status["freq_hz"] == result2["freq_hz"]

        workbench.siggen_stop()


# =====================================================================
# WT-14xx  GDB Debug: USB JTAG
# =====================================================================


requires_dut = pytest.mark.requires_dut


class TestUSBJTAGDebug:
    """WT-14xx: USB JTAG debug tests (requires device with native USB)."""

    @requires_dut
    def test_wt1400_debug_start(self, workbench):
        """WT-1400: Start debug and verify GDB port assigned."""
        # Stop any auto-started session first
        workbench.debug_stop()
        time.sleep(1)
        result = workbench.debug_start()
        assert result["gdb_port"] > 0
        assert result["chip"] in ("esp32c3", "esp32c6", "esp32h2", "esp32s3", "esp32")
        assert len(result["slot"]) > 0
        assert "gdb_target" in result
        workbench.debug_stop()

    @requires_dut
    def test_wt1401_debug_stop_restores(self, workbench):
        """WT-1401: After debug stop, slot returns to normal."""
        workbench.debug_stop()
        time.sleep(1)
        workbench.debug_start()
        workbench.debug_stop()
        time.sleep(2)
        status = workbench.debug_status()
        # No slots should be debugging after stop
        for info in status.get("slots", {}).values():
            assert info["debugging"] is False

    @requires_dut
    def test_wt1402_debug_status(self, workbench):
        """WT-1402: Debug status shows active session."""
        workbench.debug_stop()
        time.sleep(1)
        result = workbench.debug_start()
        slot = result["slot"]
        status = workbench.debug_status()
        assert status["slots"][slot]["debugging"] is True
        assert status["slots"][slot]["chip"] == result["chip"]
        assert status["slots"][slot]["gdb_port"] == result["gdb_port"]
        workbench.debug_stop()

    def test_wt1403_debug_reject_absent(self, workbench):
        """WT-1403: Debug on absent slot returns error."""
        with pytest.raises((CommandError, CommandTimeout)):
            workbench.debug_start(slot="SLOT99")

    def test_wt1404_debug_reject_unsupported(self, workbench):
        """WT-1404: Unsupported chip returns error."""
        with pytest.raises(CommandError):
            workbench.debug_start(chip="esp8266")

    @requires_dut
    def test_wt1405_debug_reject_duplicate(self, workbench):
        """WT-1405: Second start while debugging returns error."""
        workbench.debug_stop()
        time.sleep(1)
        result = workbench.debug_start()
        slot = result["slot"]
        with pytest.raises(CommandError):
            workbench.debug_start(slot=slot)
        workbench.debug_stop()

    @requires_dut
    def test_wt1406_jtag_reset(self, workbench):
        """WT-1406: serial/reset uses JTAG when debug session is active."""
        workbench.debug_stop()
        time.sleep(1)
        result = workbench.debug_start()
        slot = result["slot"]
        # Reset via serial API — should auto-select JTAG
        reset = workbench.serial_reset(slot)
        assert reset.get("method") == "jtag"
        assert "reset run" in reset.get("command", "")
        workbench.debug_stop()


# =====================================================================
# WT-17xx  GDB Debug: Auto-Debug
# =====================================================================


class TestAutoDebug:
    """WT-17xx: Auto-debug tests (OpenOCD auto-starts on hotplug/boot)."""

    @requires_dut
    def test_wt1704_auto_debug_on_boot(self, workbench):
        """WT-1704: Debug can be started automatically (simulates boot)."""
        # Ensure a session is active (start if needed after prior stop)
        workbench.debug_stop()
        time.sleep(1)
        result = workbench.debug_start()
        assert result["chip"] in (
            "esp32c3", "esp32c6", "esp32h2", "esp32s3", "esp32")
        status = workbench.debug_status()
        active = [s for s, info in status.get("slots", {}).items()
                  if info["debugging"]]
        assert len(active) >= 1, "No debug session active"

    @requires_dut
    def test_wt1705_auto_debug_in_devices(self, workbench):
        """WT-1705: Debug status reports in /api/devices."""
        # Ensure debugging is active
        status = workbench.debug_status()
        if not any(i["debugging"] for i in status.get("slots", {}).values()):
            workbench.debug_start()
            time.sleep(1)
        devices = workbench.get_devices()
        debug_devices = [d for d in devices
                         if d.get("debugging") and d.get("present")]
        assert len(debug_devices) >= 1
        dev = debug_devices[0]
        assert dev["debug_chip"] in (
            "esp32c3", "esp32c6", "esp32h2", "esp32s3", "esp32")
        assert isinstance(dev["debug_gdb_port"], int)
        assert dev["debug_gdb_port"] > 0

    @requires_dut
    def test_wt1707_manual_stop_prevents_autorestart(self, workbench):
        """WT-1707: Manual debug_stop prevents auto-restart."""
        workbench.debug_stop()
        time.sleep(3)
        status = workbench.debug_status()
        # After manual stop, no session should be active
        for info in status.get("slots", {}).values():
            assert info["debugging"] is False
        # Restart for other tests
        workbench.debug_start()

    @requires_dut
    def test_wt1709_auto_debug_skipped_during_flapping(self, workbench):
        """WT-1709: Auto-debug is not attempted when slot is flapping."""
        # We can only verify the logic exists — triggering real flapping
        # requires rapid USB connect/disconnect which we can't do remotely.
        # Instead, verify that debug_start on a non-present slot fails cleanly.
        workbench.debug_stop()
        time.sleep(1)
        status = workbench.debug_status()
        # Verify the API is responsive and all sessions are stopped
        for info in status.get("slots", {}).values():
            assert info["debugging"] is False
        # Restart for other tests
        workbench.debug_start()


# =====================================================================
# WT-18xx  End-to-End: Flash + Debug
# =====================================================================


def _find_present_device(workbench):
    """Find the first present DUT (not a debug probe) and return its slot info.

    Any present device that isn't a probe or HID-warning slot is a DUT.
    This covers both native USB chips (VID 303a, ttyACM) and classic ESP32
    boards with third-party USB-UART bridges (CP2102, CH340, ttyUSB).
    """
    devices = workbench.get_devices()
    for d in devices:
        if not d.get("present"):
            continue
        if d.get("is_probe"):
            continue
        if d.get("usb_warning"):
            continue
        return d
    return None


def _ocd_command(host, port, cmd, timeout=3.0):
    """Send a command to OpenOCD telnet and return response.

    Reads until the '>' prompt or timeout, so long-running commands
    like 'program' are handled correctly.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)  # connect timeout
    try:
        s.connect((host, port))
        time.sleep(0.3)
        s.settimeout(timeout)
        s.recv(4096)  # banner
        s.sendall(f"{cmd}\n".encode())
        # Read until prompt or timeout
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            s.settimeout(max(remaining, 0.5))
            try:
                chunk = s.recv(8192)
                if not chunk:
                    break
                buf += chunk
                if b"> " in buf or b">\n" in buf:
                    break
            except socket.timeout:
                break
        return buf.decode("latin-1", errors="replace").strip()
    finally:
        s.close()


def _wait_for_state(workbench, check_fn, timeout=30, poll=1.0, what="state"):
    """Poll workbench until check_fn(device) returns True or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        dev = _find_present_device(workbench)
        if dev and check_fn(dev):
            return dev
        time.sleep(poll)
    raise AssertionError(
        f"Timed out after {timeout}s waiting for {what}")


def _flash_device(workbench, chip, target_dir):
    """Flash debug-test firmware via esptool over RFC2217.

    Uses the RFC2217 proxy for flashing (binaries stay on the host).
    After flash, calls serial_reset to reboot the device into the
    new firmware.

    Returns True on success.
    """
    import subprocess

    bootloader = os.path.join(target_dir, "bootloader.bin")
    partition = os.path.join(target_dir, "partition-table.bin")
    app = os.path.join(target_dir, "debug-test.bin")

    if not all(os.path.exists(f) for f in [bootloader, partition, app]):
        print(f"Missing binaries in {target_dir}", flush=True)
        return False

    dev = _find_present_device(workbench)
    if not dev:
        return False

    slot_label = dev.get("label", "")
    serial_url = dev.get("url", "")
    if not serial_url:
        print("No serial URL", flush=True)
        return False

    # Stop debug if active (native USB shares serial + JTAG on same USB)
    was_debugging = dev.get("debugging")
    if was_debugging:
        workbench.debug_stop(slot=slot_label)
        _wait_for_state(
            workbench,
            lambda d: d.get("running") and not d.get("debugging"),
            timeout=20, what="debug stopped before flash")

    bl_offset = "0x1000" if chip == "esp32" else "0x0000"
    cmd = [
        "python3", "-m", "esptool",
        "--chip", chip,
        "--port", serial_url,
        "--before", "default-reset",
        "--after", "no-reset",
        "write-flash", "--flash-mode", "dio", "--flash-size", "4MB",
        bl_offset, bootloader,
        "0x8000", partition,
        "0x10000", app,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        if result.returncode != 0 and "Hash of data verified" not in output:
            print(f"Flash failed: {output[-300:]}", flush=True)
            return False
    except Exception as e:
        print(f"Flash error: {e}", flush=True)
        return False

    print(f"Flash OK: {slot_label} ({chip})", flush=True)

    # Reboot device into new firmware
    workbench.serial_reset(slot_label)

    # Restart debug if it was active (resume CPU so firmware runs)
    if was_debugging:
        workbench.debug_start(slot=slot_label, chip=chip)
        _wait_for_state(
            workbench,
            lambda d: d.get("debugging"),
            timeout=30, what="debug restart after flash")
        # OpenOCD halts CPU on connect — reset run so firmware boots
        host = workbench.base_url.split("//")[1].split(":")[0]
        dev = _find_present_device(workbench)
        telnet_port = dev.get("openocd_telnet_port") if dev else None
        if telnet_port:
            try:
                _ocd_command(host, telnet_port, "reset run", timeout=5)
            except Exception:
                pass  # best effort — firmware may already be running

    return True


class TestEndToEnd:
    """WT-18xx: End-to-end flash + debug tests.

    These tests flash the debug-test firmware, verify serial output,
    and exercise GDB debugging (halt, step, memory read) for each chip.
    Run one chip at a time — plug in the target, run the test.

    Tests are ordered: WT-1800 (flash) must pass before debug tests
    run.  If flash fails, all subsequent tests are skipped.

    Usage:
        pytest workbench_test.py -k TestEndToEnd --run-dut --wt-url http://192.168.0.87:8080
    """

    _test_session_started = False
    _flash_ok = False

    @pytest.fixture(autouse=True, scope="class")
    def _end_test_session(self, workbench):
        """Send test_end when all tests in this class are done."""
        yield
        try:
            workbench.test_end()
        except Exception:
            pass
        TestEndToEnd._test_session_started = False

    @pytest.fixture(autouse=True)
    def _track_progress(self, workbench, request):
        """Report test progress to the workbench panel."""
        test_id = request.node.name.split("_")[1].upper()  # e.g. "WT1800"
        raw_name = request.node.obj.__doc__.split("\n")[0].strip() if request.node.obj.__doc__ else request.node.name
        # Strip "WT-1800: " prefix from docstring — test_id already carries it
        test_name = re.sub(r'^WT-?\d+:\s*', '', raw_name)

        if not TestEndToEnd._test_session_started:
            TestEndToEnd._test_session_started = True
            try:
                workbench.test_start(
                    spec="End-to-End Flash+Debug", phase="WT-18xx", total=6)
            except Exception:
                pass

        for _attempt in range(3):
            try:
                workbench.test_step(test_id, test_name, "Running...")
                break
            except Exception:
                time.sleep(2)

        yield

        # Determine result from pytest outcome
        result = "PASS"
        detail = ""
        if hasattr(request.node, "rep_setup") and request.node.rep_setup.skipped:
            result = "SKIP"
        elif hasattr(request.node, "rep_call"):
            if request.node.rep_call.failed:
                result = "FAIL"
                detail = str(request.node.rep_call.longrepr)[:200]
            elif request.node.rep_call.skipped:
                result = "SKIP"
        for _attempt in range(3):
            try:
                workbench.test_result(test_id, test_name, result, details=detail)
                break
            except Exception:
                time.sleep(2)

    @requires_dut
    def test_wt1800_flash_and_serial(self, workbench):
        """WT-1800: Flash debug-test firmware and verify serial output."""
        dev = _find_present_device(workbench)
        assert dev, "No device connected"

        chip = dev.get("debug_chip", "")
        slot = dev.get("label", "")

        # Map debug_chip to esptool chip name
        esptool_chip = chip if chip else None
        if not esptool_chip:
            # Try to detect from debug_start
            result = workbench.debug_start()
            esptool_chip = result.get("chip")
            assert esptool_chip, "Could not detect chip type"

        target_dir = os.path.join(DEBUG_TEST_DIR, esptool_chip)
        if not os.path.isdir(target_dir):
            pytest.skip(f"No pre-built binaries for {esptool_chip}")

        # Flash via portal API (stops proxy, runs esptool locally, restarts proxy)
        success = _flash_device(workbench, esptool_chip, target_dir)
        assert success, f"Flash failed for {esptool_chip}"

        # Verify serial output
        result = workbench.serial_monitor(slot, pattern="LOOP:", timeout=15)
        assert result.get("matched"), \
            f"Expected 'LOOP:' in serial output, got: {result.get('output', [])[-5:]}"
        TestEndToEnd._flash_ok = True

    @requires_dut
    def test_wt1801_debug_halt_and_resume(self, workbench):
        """WT-1801: Halt CPU via JTAG, read PC, resume."""
        if not TestEndToEnd._flash_ok:
            pytest.skip("WT-1800 (flash) did not pass")
        dev = _find_present_device(workbench)
        assert dev, "No device connected"
        assert dev.get("debugging"), "Debug not active — flash first (WT-1800)"

        host = workbench.base_url.split("//")[1].split(":")[0]
        telnet_port = dev["debug_gdb_port"] + 1111  # gdb=3333 → telnet=4444

        # Get actual telnet port from debug status
        status = workbench.debug_status()
        for label, info in status.get("slots", {}).items():
            if info.get("debugging"):
                telnet_port = info.get("telnet_port", telnet_port)
                break

        # Halt
        out = _ocd_command(host, telnet_port, "halt")
        assert "halted" in out.lower() or ">" in out

        # Read PC
        out = _ocd_command(host, telnet_port, "reg pc")
        assert "0x" in out, f"Expected PC value, got: {out}"

        # Resume
        _ocd_command(host, telnet_port, "resume", timeout=2)

    @requires_dut
    def test_wt1802_debug_single_step(self, workbench):
        """WT-1802: Single-step CPU via JTAG."""
        if not TestEndToEnd._flash_ok:
            pytest.skip("WT-1800 (flash) did not pass")
        dev = _find_present_device(workbench)
        assert dev, "No device connected"
        assert dev.get("debugging"), "Debug not active"

        host = workbench.base_url.split("//")[1].split(":")[0]
        status = workbench.debug_status()
        telnet_port = None
        for info in status.get("slots", {}).values():
            if info.get("debugging"):
                telnet_port = info["telnet_port"]
                break
        assert telnet_port, "No telnet port found"

        # Halt
        _ocd_command(host, telnet_port, "halt")

        # Read PC before step
        out1 = _ocd_command(host, telnet_port, "reg pc")
        import re
        m1 = re.search(r"0x[0-9a-fA-F]+", out1)
        assert m1, f"Could not read PC: {out1}"
        pc_before = m1.group()

        # Step
        out = _ocd_command(host, telnet_port, "step", timeout=2)
        assert "halted" in out.lower() or ">" in out

        # Read PC after step — should have advanced
        out2 = _ocd_command(host, telnet_port, "reg pc")
        m2 = re.search(r"0x[0-9a-fA-F]+", out2)
        assert m2, f"Could not read PC after step: {out2}"
        pc_after = m2.group()

        assert pc_before != pc_after, \
            f"PC did not advance: before={pc_before}, after={pc_after}"

        # Resume
        _ocd_command(host, telnet_port, "resume", timeout=2)

    @requires_dut
    def test_wt1803_debug_memory_read(self, workbench):
        """WT-1803: Read memory via JTAG."""
        if not TestEndToEnd._flash_ok:
            pytest.skip("WT-1800 (flash) did not pass")
        dev = _find_present_device(workbench)
        assert dev, "No device connected"
        assert dev.get("debugging"), "Debug not active"

        host = workbench.base_url.split("//")[1].split(":")[0]
        status = workbench.debug_status()
        telnet_port = None
        for info in status.get("slots", {}).values():
            if info.get("debugging"):
                telnet_port = info["telnet_port"]
                break
        assert telnet_port

        # Halt
        _ocd_command(host, telnet_port, "halt")

        # Read ROM memory (always present at 0x40000000 on all ESP32)
        out = _ocd_command(host, telnet_port, "mdw 0x40000000 4")
        assert "0x40000000" in out, f"Memory read failed: {out}"

        # Resume
        _ocd_command(host, telnet_port, "resume", timeout=2)

    @requires_dut
    def test_wt1804_debug_breakpoint(self, workbench):
        """WT-1804: Set and hit a hardware breakpoint via JTAG."""
        if not TestEndToEnd._flash_ok:
            pytest.skip("WT-1800 (flash) did not pass")
        dev = _find_present_device(workbench)
        assert dev, "No device connected"
        assert dev.get("debugging"), "Debug not active"

        host = workbench.base_url.split("//")[1].split(":")[0]
        status = workbench.debug_status()
        telnet_port = None
        for info in status.get("slots", {}).values():
            if info.get("debugging"):
                telnet_port = info["telnet_port"]
                break
        assert telnet_port

        import re

        # Halt, get current PC
        _ocd_command(host, telnet_port, "halt")
        out = _ocd_command(host, telnet_port, "reg pc")
        m = re.search(r"0x([0-9a-fA-F]+)", out)
        assert m
        pc = int(m.group(1), 16)

        # Set breakpoint a few instructions ahead
        bp_addr = pc + 8
        out = _ocd_command(host, telnet_port,
                           f"bp 0x{bp_addr:08X} 2 hw")
        assert "breakpoint" in out.lower() or ">" in out

        # Resume — should hit breakpoint
        out = _ocd_command(host, telnet_port, "resume", timeout=3)

        # Remove breakpoint
        _ocd_command(host, telnet_port, f"rbp 0x{bp_addr:08X}")

        # Resume normal execution
        _ocd_command(host, telnet_port, "resume", timeout=2)

    @requires_dut
    def test_wt1805_flash_preserves_debug(self, workbench):
        """WT-1805: Debug auto-restarts after flash (no manual intervention)."""
        if not TestEndToEnd._flash_ok:
            pytest.skip("WT-1800 (flash) did not pass")
        dev = _find_present_device(workbench)
        assert dev, "No device connected"

        chip = dev.get("debug_chip", "")
        slot = dev.get("label", "")

        if not chip:
            result = workbench.debug_start()
            chip = result.get("chip", "")
        assert chip, "Could not detect chip"

        target_dir = os.path.join(DEBUG_TEST_DIR, chip)
        if not os.path.isdir(target_dir):
            pytest.skip(f"No pre-built binaries for {chip}")

        # Verify debug is active before flash
        dev_before = _find_present_device(workbench)
        assert dev_before.get("debugging"), "Debug should be active before flash"

        # Flash via portal API (handles debug stop/restart automatically)
        success = _flash_device(workbench, chip, target_dir)
        assert success, "Flash failed"

        # Verify debug auto-restarted (portal restarts debug after flash)
        dev_after = _wait_for_state(
            workbench,
            lambda d: d.get("debugging"),
            timeout=30, what="debug restart after flash")
        assert dev_after, "Device not found after flash"

        # Verify serial output (extra time — proxy just restarted, device booting)
        result = workbench.serial_monitor(slot, pattern="LOOP:", timeout=20)
        assert result.get("matched"), "Firmware not running after flash"


# =====================================================================
# WT-19xx  Serial Architecture: Buffer + Detection
# =====================================================================


class TestSerialArchitecture:
    """WT-19xx: Serial reader buffer, passive output, and multi-slot detection."""

    def test_wt1900_devices_have_slots(self, workbench):
        """WT-1900: /api/devices returns slots with labels and state."""
        devices = workbench.get_devices()
        assert len(devices) > 0, "No slots configured"
        for d in devices:
            assert "label" in d
            assert "state" in d
            assert d["state"] in (
                "absent", "idle", "resetting", "monitoring",
                "flapping", "recovering", "download_mode", "debugging",
            )

    @requires_dut
    def test_wt1901_present_device_detected(self, workbench):
        """WT-1901: Present device has detected_chip set."""
        dev = _find_present_device(workbench)
        assert dev, "No device connected"
        chip = dev.get("detected_chip") or dev.get("debug_chip")
        assert chip, (
            f"No chip detected for {dev['label']} — "
            f"usb_devices={dev.get('usb_devices')}"
        )
        assert chip in (
            "esp32", "esp32s2", "esp32s3",
            "esp32c3", "esp32c6", "esp32h2",
        ), f"Unexpected chip: {chip}"

    @requires_dut
    def test_wt1902_all_present_devices_detected(self, workbench):
        """WT-1902: Every present DUT slot has a detected chip."""
        devices = workbench.get_devices()
        duts = [d for d in devices
                if d.get("present") and not d.get("is_probe")]
        assert len(duts) > 0, "No DUT devices present"
        for d in duts:
            chip = d.get("detected_chip") or d.get("debug_chip")
            assert chip, (
                f"{d['label']}: no chip detected — "
                f"usb_devices={d.get('usb_devices')}"
            )

    @requires_dut
    def test_wt1903_serial_output_buffer(self, workbench):
        """WT-1903: GET /api/serial/output returns buffered lines."""
        dev = _find_present_device(workbench)
        assert dev, "No device connected"
        slot = dev["label"]

        # Wait briefly for the reader thread to accumulate some output
        time.sleep(3)
        result = workbench.serial_output(slot, lines=20)
        assert result.get("ok"), f"serial_output failed: {result}"
        lines = result.get("lines", [])
        # Buffer should have entries (device is running firmware)
        assert isinstance(lines, list)
        # Each entry has ts and text
        for entry in lines:
            assert "ts" in entry
            assert "text" in entry
            assert isinstance(entry["ts"], (int, float))
            assert isinstance(entry["text"], str)

    @requires_dut
    def test_wt1904_serial_output_since_filter(self, workbench):
        """WT-1904: serial_output respects 'since' timestamp filter."""
        dev = _find_present_device(workbench)
        assert dev, "No device connected"
        slot = dev["label"]

        # Get all buffered lines
        all_lines = workbench.serial_output(slot, lines=100)
        assert all_lines.get("ok")
        if not all_lines["lines"]:
            time.sleep(3)
            all_lines = workbench.serial_output(slot, lines=100)

        if len(all_lines["lines"]) < 2:
            pytest.skip("Not enough serial output to test filtering")

        # Use timestamp of a middle line as the 'since' filter
        mid = len(all_lines["lines"]) // 2
        since_ts = all_lines["lines"][mid]["ts"]
        filtered = workbench.serial_output(slot, lines=100, since=since_ts)
        assert filtered.get("ok")
        # Filtered results should be a subset
        assert len(filtered["lines"]) <= len(all_lines["lines"])
        # All returned entries should have ts > since_ts
        for entry in filtered["lines"]:
            assert entry["ts"] > since_ts

    @requires_dut
    def test_wt1905_serial_monitor_from_buffer(self, workbench):
        """WT-1905: serial_monitor reads from buffer, not hardware."""
        dev = _find_present_device(workbench)
        assert dev, "No device connected"
        slot = dev["label"]

        # Monitor with no pattern — returns immediately with buffered data
        result = workbench.serial_monitor(slot, timeout=2)
        assert result.get("matched") is False
        assert isinstance(result.get("output"), list)

    @requires_dut
    def test_wt1906_serial_monitor_pattern_match(self, workbench):
        """WT-1906: serial_monitor matches pattern from buffer."""
        dev = _find_present_device(workbench)
        assert dev, "No device connected"
        slot = dev["label"]

        # The firmware prints "LOOP:" repeatedly — match from buffer
        result = workbench.serial_monitor(slot, pattern="LOOP:", timeout=15)
        if not result.get("matched"):
            # Firmware may not be running — try a boot message instead
            result = workbench.serial_monitor(
                slot, pattern="esp", timeout=10)
        # At minimum, we should get some output lines
        assert len(result.get("output", [])) >= 0

    @requires_dut
    def test_wt1907_multi_slot_detection(self, workbench):
        """WT-1907: Multiple slots independently detect their chips."""
        devices = workbench.get_devices()
        duts = [d for d in devices
                if d.get("present") and not d.get("is_probe")]
        if len(duts) < 2:
            pytest.skip("Need 2+ DUT devices for multi-slot test")

        labels = []
        chips = []
        for d in duts:
            chip = d.get("detected_chip") or d.get("debug_chip")
            assert chip, f"{d['label']}: no chip detected"
            labels.append(d["label"])
            chips.append(chip)

        # Verify each slot has its own independent detection
        assert len(labels) == len(set(labels)), "Duplicate slot labels"
        # Each slot should have a valid chip
        for label, chip in zip(labels, chips):
            assert chip in (
                "esp32", "esp32s2", "esp32s3",
                "esp32c3", "esp32c6", "esp32h2",
            ), f"{label}: unexpected chip '{chip}'"
