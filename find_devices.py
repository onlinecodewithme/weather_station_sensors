#!/usr/bin/env python3
"""Scan the RS485 bus for Modbus RTU devices (read-only: function 0x03, register 0).

Examples:
    python3 find_devices.py                  # 9600 and 4800 baud, addresses 1-247
    python3 find_devices.py --baud 9600 --last 10
"""
import argparse

from modbus_rtu import ModbusError, ModbusRTU


def main():
    p = argparse.ArgumentParser(description="Find Modbus RTU devices on the bus")
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, nargs="*", default=[9600, 4800])
    p.add_argument("--first", type=int, default=1)
    p.add_argument("--last", type=int, default=247)
    args = p.parse_args()

    found = 0
    for baud in args.baud:
        bus = ModbusRTU(args.port, baud, timeout=0.15, retries=1)
        print(f"Scanning {args.port} @ {baud} baud, addresses {args.first}-{args.last}...")
        for addr in range(args.first, args.last + 1):
            try:
                regs = bus.read_registers(addr, 0x0000, 2)
            except ModbusError as e:
                if "nothing" not in str(e):
                    print(f"  addr {addr:3d}: garbled reply ({e}) - possible address clash")
                continue
            found += 1
            print(f"  addr {addr:3d}: regs 0x0000-0x0001 = {regs}")
        bus.close()
    print(f"Done, {found} device(s) found.")


if __name__ == "__main__":
    main()
