# Debug Test Firmware

Minimal ESP-IDF firmware for verifying remote GDB debugging on the workbench. Prints a counter to serial and exposes a `debug_loop()` function with a global `loop_counter` variable for GDB breakpoint and variable inspection testing.

## What It Does

1. Prints `DEBUG_TEST_READY` on boot
2. Increments `volatile int loop_counter` every 500ms
3. Prints `LOOP: <n>` each iteration
4. Toggles an LED each iteration
5. `debug_loop()` is marked `noinline` so GDB can set breakpoints on it

## Building

Requires ESP-IDF v5.4+. Build for each target:

```bash
source ~/esp/esp-idf/export.sh

for target in esp32c3 esp32c6 esp32h2 esp32s3 esp32; do
    rm -rf build sdkconfig

    if [ "$target" = "esp32" ]; then
        echo "CONFIG_ESP_CONSOLE_UART_DEFAULT=y" > sdkconfig.defaults
    else
        echo "CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y" > sdkconfig.defaults
    fi
    echo "CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y" >> sdkconfig.defaults
    echo "CONFIG_COMPILER_OPTIMIZATION_DEBUG=y" >> sdkconfig.defaults

    idf.py set-target "$target"
    idf.py build

    mkdir -p "output/$target"
    cp build/bootloader/bootloader.bin "output/$target/"
    cp build/partition_table/partition-table.bin "output/$target/"
    cp build/debug-test.bin "output/$target/"
    cp build/debug-test.elf "output/$target/"
done
```

## Pre-built Binaries

Pre-built binaries are in `output/<target>/` for all 5 chip variants:

| Target | Architecture | Console | LED GPIO |
|--------|-------------|---------|----------|
| esp32c3 | RISC-V | USB Serial JTAG | 8 |
| esp32c6 | RISC-V | USB Serial JTAG | 8 |
| esp32h2 | RISC-V | USB Serial JTAG | 8 |
| esp32s3 | Xtensa | USB Serial JTAG | 2 |
| esp32 | Xtensa | UART | 2 |

Each target directory contains:
- `bootloader.bin` — bootloader
- `partition-table.bin` — partition table
- `debug-test.bin` — application
- `debug-test.elf` — ELF with debug symbols (for GDB)

## Flashing

The workbench auto-assigns serial ports. Query `/api/devices` to find the port, then flash:

```bash
# Find the auto-assigned port
PORT=$(curl -s http://esp32-workbench.local:8080/api/devices | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(next(s['url'] for s in d['slots'] if s.get('present')))")

# Flash (example: C6)
esptool --chip esp32c6 --port "$PORT" \
  --before=default-reset --after=watchdog-reset \
  write-flash --flash-mode dio --flash-size 4MB \
  0x0000 output/esp32c6/bootloader.bin \
  0x8000 output/esp32c6/partition-table.bin \
  0x10000 output/esp32c6/debug-test.bin
```

## End-to-End Debug Test

After flashing, verify the full debug chain:

```bash
# 1. Check firmware running (serial)
curl -s -X POST http://esp32-workbench.local:8080/api/serial/monitor \
  -H "Content-Type: application/json" \
  -d '{"slot":"AUTO-1","pattern":"LOOP:","timeout":5}'
# Expected: {"ok":true,"matched":true,"line":"LOOP: 42"}

# 2. Check debug auto-started
curl -s http://esp32-workbench.local:8080/api/devices | \
  python3 -c "import json,sys; d=json.load(sys.stdin); s=next(x for x in d['slots'] if x.get('present')); print(f'chip={s.get(\"debug_chip\")}, gdb=:{s.get(\"debug_gdb_port\")}')"
# Expected: chip=esp32c6, gdb=:3333

# 3. Connect GDB (RISC-V example)
riscv32-esp-elf-gdb output/esp32c6/debug-test.elf \
  -ex "target extended-remote esp32-workbench.local:3333" \
  -ex "monitor reset halt" \
  -ex "break debug_loop" \
  -ex "continue" \
  -ex "print loop_counter" \
  -ex "step" \
  -ex "print loop_counter"
```

### Expected GDB Output

```
Breakpoint 1, debug_loop () at main.c:18
18          loop_counter++;
$1 = 42
19          printf("LOOP: %d\n", loop_counter);
$2 = 43
```

## GDB Toolchains

| Chip | GDB Binary |
|------|-----------|
| ESP32-C3, C6, H2 | `riscv32-esp-elf-gdb` |
| ESP32-S3, ESP32 | `xtensa-esp32s3-elf-gdb` / `xtensa-esp32-elf-gdb` |
