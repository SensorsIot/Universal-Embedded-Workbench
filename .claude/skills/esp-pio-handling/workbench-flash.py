#!/usr/bin/env python3
"""workbench-flash: flash a PlatformIO ESP32 build to a workbench slot via POST /api/flash.

Use this when `pio run -t upload` over RFC2217 fails to enter the bootloader
("Wrong boot mode detected (0x13)") on a classic ESP32 behind a USB-serial bridge
(CP2102 / CH340 / CH9102). Those boards' external DTR/RTS auto-reset can't be driven
reliably through the RFC2217 proxy; the portal instead flashes locally on the Pi,
where the reset works natively. Native-USB C3/S3/C6/H2 chips flash fine over RFC2217
and do not need this.

Usage:
  workbench-flash.py --host workbench.local:8080 --slot SLOT3 [--env <pio_env>]
                     [--chip esp32] [--baud 460800] [--project-dir .]
"""
import argparse, glob, json, os, sys, urllib.request

# Bootloader offset: 0x0 for native-USB chips, 0x1000 for classic ESP32/ESP32-S2.
_BOOT0 = {"esp32c3", "esp32s3", "esp32c6", "esp32h2"}


def find_boot_app0():
    for pat in (
        os.path.expanduser("~/.platformio/packages/framework-arduinoespressif32*/tools/partitions/boot_app0.bin"),
        "/root/.platformio/packages/framework-arduinoespressif32*/tools/partitions/boot_app0.bin",
    ):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def multipart(fields, files, boundary="----workbenchflash"):
    body = b""
    for name, val in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                 ).encode() + str(val).encode() + b"\r\n"
    for name, (filename, content) in files.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                 f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                 ).encode() + content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, boundary


def main():
    ap = argparse.ArgumentParser(description="Flash a PlatformIO ESP32 build via the workbench /api/flash endpoint.")
    ap.add_argument("--host", required=True, help="workbench host:port, e.g. workbench.local:8080")
    ap.add_argument("--slot", required=True, help="slot label, e.g. SLOT3")
    ap.add_argument("--env", help="PlatformIO env (default: first dir under .pio/build)")
    ap.add_argument("--project-dir", default=".", help="PlatformIO project directory")
    ap.add_argument("--chip", default="esp32", help="esptool chip (default esp32)")
    ap.add_argument("--baud", default="460800")
    args = ap.parse_args()

    build_root = os.path.join(args.project_dir, ".pio", "build")
    env = args.env
    if not env:
        envs = sorted(d for d in glob.glob(os.path.join(build_root, "*")) if os.path.isdir(d))
        if not envs:
            sys.exit(f"no builds under {build_root} — run `pio run` first")
        env = os.path.basename(envs[0])
    bdir = os.path.join(build_root, env)

    boot_off = "0x0000" if args.chip in _BOOT0 else "0x1000"
    images = [(boot_off, os.path.join(bdir, "bootloader.bin")),
              ("0x8000", os.path.join(bdir, "partitions.bin"))]
    boot_app0 = find_boot_app0()
    if boot_app0:
        images.append(("0xe000", boot_app0))
    images.append(("0x10000", os.path.join(bdir, "firmware.bin")))

    files = {}
    for off, path in images:
        if not os.path.exists(path):
            sys.exit(f"missing image: {path}")
        with open(path, "rb") as f:
            files[off] = (os.path.basename(path), f.read())

    body, boundary = multipart({"slot": args.slot, "chip": args.chip, "baud": args.baud}, files)
    url = f"http://{args.host}/api/flash"
    print(f"POST {url}  slot={args.slot} env={env} chip={args.chip}  {len(files)} images "
          f"({sum(len(c) for _, c in files.values()) // 1024} KB)")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        r = json.load(resp)
    print("ok:", r.get("ok"), "| returncode:", r.get("returncode"), "| error:", r.get("error"))
    tail = (r.get("log") or "")[-800:]
    if tail:
        print("--- esptool log tail ---")
        print(tail)
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
