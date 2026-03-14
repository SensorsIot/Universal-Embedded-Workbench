"""
WiFi Traffic Sniffer -- DNS + TLS SNI passive capture with IP geolocation.

Captures DNS queries from dnsmasq logs and TLS SNI hostnames from raw
packet capture on the AP interface.  Resolves destination IPs to countries
via ip-api.com and flags traffic to suspicious countries.
"""

import json
import logging
import os
import re
import socket
import struct
import threading
import time
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Suspicious country codes (ISO 3166-1 alpha-2)
SUSPICIOUS_COUNTRIES = {"CN", "RU", "IR", "KP"}

# ---------------------------------------------------------------------------
# Module state (lock-protected)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_running = False
_interface = "wlan0"
_log_path = "/tmp/wifi-tester/dns.log"

_traffic: dict[str, dict] = {}    # domain -> traffic entry
_clients: dict[str, dict] = {}    # client_ip -> client info
_geo_cache: dict[str, dict] = {}  # ip -> geo info from ip-api.com

_threads: list[threading.Thread] = []
_raw_sock = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _record_traffic(domain, client_ip, server_ips=None):
    """Record a domain access from a client."""
    domain = domain.lower().strip(".")
    if not domain:
        return

    with _lock:
        if domain not in _traffic:
            _traffic[domain] = {
                "domain": domain,
                "ips": set(),
                "country": "",
                "countryCode": "",
                "org": "",
                "flagged": False,
                "count": 0,
                "last_seen": "",
                "clients": set(),
            }
        entry = _traffic[domain]
        entry["count"] += 1
        entry["last_seen"] = _now_iso()
        if client_ip:
            entry["clients"].add(client_ip)
        if server_ips:
            entry["ips"].update(server_ips)

        # Update client tracking
        if client_ip and not client_ip.startswith("127."):
            if client_ip not in _clients:
                _clients[client_ip] = {
                    "ip": client_ip,
                    "domains": set(),
                }
            _clients[client_ip]["domains"].add(domain)


# ---------------------------------------------------------------------------
# Thread 1: DNS Log Parser
# ---------------------------------------------------------------------------

def _dns_log_thread():
    """Tail the dnsmasq DNS log and extract queries."""
    logger.info("DNS log parser started: %s", _log_path)

    # Wait for log file to appear
    while _running and not os.path.exists(_log_path):
        time.sleep(0.5)

    if not _running:
        return

    with open(_log_path) as f:
        # Seek to end -- only capture new queries
        f.seek(0, 2)

        while _running:
            line = f.readline()
            if not line:
                time.sleep(0.3)
                continue

            # dnsmasq log: "... query[A] example.com from 192.168.4.5"
            m = re.search(r'query\[A+\]\s+(\S+)\s+from\s+(\S+)', line)
            if m:
                domain = m.group(1)
                client_ip = m.group(2)
                if domain and not domain.endswith(".local"):
                    _record_traffic(domain, client_ip)

    logger.info("DNS log parser stopped")


# ---------------------------------------------------------------------------
# Thread 2: TLS SNI Extractor
# ---------------------------------------------------------------------------

def _extract_sni(payload):
    """Extract SNI hostname from a TLS ClientHello payload.

    Returns hostname string or None.
    """
    try:
        # TLS record header: type(1) + version(2) + length(2)
        if len(payload) < 5 or payload[0] != 0x16:
            return None

        # Handshake header: type(1) + length(3)
        pos = 5
        if pos >= len(payload) or payload[pos] != 0x01:
            return None
        pos += 4  # skip type + 3-byte length

        # ClientHello: version(2) + random(32)
        pos += 2 + 32
        if pos >= len(payload):
            return None

        # Session ID
        sid_len = payload[pos]
        pos += 1 + sid_len
        if pos + 2 > len(payload):
            return None

        # Cipher suites
        cs_len = struct.unpack("!H", payload[pos:pos + 2])[0]
        pos += 2 + cs_len
        if pos >= len(payload):
            return None

        # Compression methods
        cm_len = payload[pos]
        pos += 1 + cm_len
        if pos + 2 > len(payload):
            return None

        # Extensions
        ext_len = struct.unpack("!H", payload[pos:pos + 2])[0]
        pos += 2
        ext_end = pos + ext_len

        while pos + 4 <= ext_end and pos + 4 <= len(payload):
            ext_type = struct.unpack("!H", payload[pos:pos + 2])[0]
            ext_data_len = struct.unpack("!H", payload[pos + 2:pos + 4])[0]
            pos += 4

            if ext_type == 0x0000:  # SNI
                if pos + 5 <= len(payload):
                    # SNI list: length(2) + type(1) + name_length(2) + name
                    name_type = payload[pos + 2]
                    name_len = struct.unpack("!H", payload[pos + 3:pos + 5])[0]
                    if name_type == 0 and pos + 5 + name_len <= len(payload):
                        return payload[pos + 5:pos + 5 + name_len].decode(
                            "ascii", errors="replace"
                        )
                return None

            pos += ext_data_len

        return None
    except Exception:
        return None


def _sni_capture_thread():
    """Capture TLS ClientHello packets and extract SNI hostnames."""
    global _raw_sock

    logger.info("SNI capture started on %s", _interface)

    try:
        ETH_P_ALL = 0x0003
        _raw_sock = socket.socket(
            socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL)
        )
        _raw_sock.bind((_interface, 0))
        _raw_sock.settimeout(1.0)
    except Exception as e:
        logger.error("Cannot open raw socket on %s: %s", _interface, e)
        return

    while _running:
        try:
            data = _raw_sock.recv(65535)
        except socket.timeout:
            continue
        except Exception:
            if _running:
                logger.warning("Raw socket recv error", exc_info=True)
            break

        # Ethernet header: dst(6) + src(6) + ethertype(2)
        if len(data) < 14:
            continue
        ethertype = struct.unpack("!H", data[12:14])[0]
        if ethertype != 0x0800:  # Not IPv4
            continue

        # IPv4 header
        ip_start = 14
        if len(data) < ip_start + 20:
            continue
        ihl = (data[ip_start] & 0x0F) * 4
        protocol = data[ip_start + 9]
        if protocol != 6:  # Not TCP
            continue

        src_ip = socket.inet_ntoa(data[ip_start + 12:ip_start + 16])
        dst_ip = socket.inet_ntoa(data[ip_start + 16:ip_start + 20])

        # TCP header
        tcp_start = ip_start + ihl
        if len(data) < tcp_start + 20:
            continue
        dst_port = struct.unpack("!H", data[tcp_start + 2:tcp_start + 4])[0]
        if dst_port != 443:
            continue

        tcp_data_offset = ((data[tcp_start + 12] >> 4) & 0x0F) * 4
        payload_start = tcp_start + tcp_data_offset
        if payload_start >= len(data):
            continue

        payload = data[payload_start:]
        sni = _extract_sni(payload)
        if sni:
            _record_traffic(sni, src_ip, server_ips={dst_ip})

    # Clean up
    if _raw_sock:
        try:
            _raw_sock.close()
        except Exception:
            pass
        _raw_sock = None

    logger.info("SNI capture stopped")


# ---------------------------------------------------------------------------
# Thread 3: IP Geolocation Resolver
# ---------------------------------------------------------------------------

def _resolve_domain_ips(domain):
    """Resolve a domain to IPv4 addresses via DNS."""
    try:
        results = socket.getaddrinfo(domain, None, socket.AF_INET)
        return {r[4][0] for r in results}
    except Exception:
        return set()


def _geo_resolver_thread():
    """Periodically resolve IPs to countries via ip-api.com batch API."""
    logger.info("Geo resolver started")

    while _running:
        time.sleep(5)
        if not _running:
            break

        # Resolve domains that have no IPs yet
        with _lock:
            domains_without_ips = [
                d for d, e in _traffic.items() if not e["ips"]
            ]

        for domain in domains_without_ips[:20]:
            if not _running:
                break
            ips = _resolve_domain_ips(domain)
            if ips:
                with _lock:
                    if domain in _traffic:
                        _traffic[domain]["ips"].update(ips)

        # Collect uncached IPs
        uncached_ips = []
        with _lock:
            for entry in _traffic.values():
                for ip in entry["ips"]:
                    if ip not in _geo_cache and ip not in uncached_ips:
                        uncached_ips.append(ip)

        if not uncached_ips:
            continue

        # Batch query ip-api.com (max 100 per request)
        batch = uncached_ips[:100]
        try:
            payload = json.dumps(
                [{"query": ip, "fields": "status,country,countryCode,org,query"}
                 for ip in batch]
            ).encode()
            req = urllib.request.Request(
                "http://ip-api.com/batch",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                results = json.loads(resp.read())
        except Exception as e:
            logger.warning("ip-api.com batch query failed: %s", e)
            continue

        # Cache results and update traffic entries
        with _lock:
            for r in results:
                if r.get("status") != "success":
                    continue
                ip = r["query"]
                _geo_cache[ip] = {
                    "country": r.get("country", ""),
                    "countryCode": r.get("countryCode", ""),
                    "org": r.get("org", ""),
                }

            for entry in _traffic.values():
                if entry["country"]:
                    continue  # Already resolved
                for ip in entry["ips"]:
                    geo = _geo_cache.get(ip)
                    if geo:
                        entry["country"] = geo["country"]
                        entry["countryCode"] = geo["countryCode"]
                        entry["org"] = geo["org"]
                        entry["flagged"] = geo["countryCode"] in SUSPICIOUS_COUNTRIES
                        break

    logger.info("Geo resolver stopped")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start(interface="wlan0", log_path="/tmp/wifi-tester/dns.log"):
    """Start all capture threads."""
    global _running, _interface, _log_path

    if _running:
        return

    _interface = interface
    _log_path = log_path
    _running = True

    threads = [
        threading.Thread(target=_dns_log_thread, daemon=True, name="sniffer-dns"),
        threading.Thread(target=_sni_capture_thread, daemon=True, name="sniffer-sni"),
        threading.Thread(target=_geo_resolver_thread, daemon=True, name="sniffer-geo"),
    ]

    for t in threads:
        t.start()

    _threads.clear()
    _threads.extend(threads)

    logger.info("Sniffer started on %s", interface)


def stop():
    """Stop all capture threads."""
    global _running, _raw_sock

    _running = False

    # Close raw socket to unblock recv
    if _raw_sock:
        try:
            _raw_sock.close()
        except Exception:
            pass
        _raw_sock = None

    # Wait for threads to finish
    for t in _threads:
        t.join(timeout=5)
    _threads.clear()

    logger.info("Sniffer stopped")


def get_traffic() -> list[dict]:
    """Return all traffic entries sorted by last_seen (most recent first)."""
    with _lock:
        entries = []
        for entry in _traffic.values():
            entries.append({
                "domain": entry["domain"],
                "ips": sorted(entry["ips"]),
                "country": entry["country"],
                "countryCode": entry["countryCode"],
                "org": entry["org"],
                "flagged": entry["flagged"],
                "count": entry["count"],
                "last_seen": entry["last_seen"],
                "clients": sorted(entry["clients"]),
            })
        entries.sort(key=lambda e: e["last_seen"], reverse=True)
        return entries


def get_summary() -> dict:
    """Return aggregated stats."""
    with _lock:
        total = len(_traffic)
        flagged = sum(1 for e in _traffic.values() if e["flagged"])
        total_connections = sum(e["count"] for e in _traffic.values())
        clients = len(_clients)
        flagged_countries = set()
        for e in _traffic.values():
            if e["flagged"] and e["countryCode"]:
                flagged_countries.add(e["countryCode"])
        return {
            "total_domains": total,
            "flagged_domains": flagged,
            "total_connections": total_connections,
            "clients": clients,
            "flagged_countries": sorted(flagged_countries),
        }


def clear():
    """Reset all traffic data."""
    with _lock:
        _traffic.clear()
        _clients.clear()
        # Keep geo cache for efficiency


def is_running() -> bool:
    """Return whether sniffer is active."""
    return _running
