#!/usr/bin/env python3
"""Capacitive rain/snow sensor reader over RS485 Modbus RTU (FTDI FT232R USB-RS485 adapter).

Wiring: red=VCC (12-24 V DC), black=GND, yellow=485-A(+), green=485-B(-).
Defaults: /dev/ttyUSB0, 9600 baud 8N1, slave address 1.

Register map (from the sensor manual):
    0x0000  rain/snow status   0x000A = dry, 0x000B = rain/snow   (read)
    0x0030  device address     1..253                              (read/write)
    0x0031  baud rate          e.g. 1920 means 19200               (read/write)
    0x006B  heater start temp  0.1 degC units (sensor heats below)  (read/write)
    0x006C  heater stop temp   0.1 degC units (sensor stops above)  (read/write)

Examples:
    python3 rain_sensor.py                       # poll status every 1 s
    python3 rain_sensor.py --csv rain_log.csv    # also log to CSV
    python3 rain_sensor.py --once                # single read, then exit
"""
import argparse
import csv
import struct
import sys
import time
from datetime import datetime

import serial

REG_STATUS = 0x0000
REG_ADDRESS = 0x0030
REG_BAUD = 0x0031
REG_HEAT_START = 0x006B
REG_HEAT_STOP = 0x006C

STATUS_DRY = 0x000A
STATUS_RAIN = 0x000B


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


class ModbusError(Exception):
    pass


class RainSensor:
    def __init__(self, port, baud=9600, addr=1, timeout=0.5):
        self.addr = addr
        self.ser = serial.Serial(port, baud, bytesize=8, parity="N", stopbits=1, timeout=timeout)

    def close(self):
        self.ser.close()

    def read_registers(self, start, count=1, func=0x03):
        req = bytes([self.addr, func]) + struct.pack(">HH", start, count)
        req += crc16(req)
        self.ser.reset_input_buffer()
        self.ser.write(req)

        expected = 5 + 2 * count
        resp = self.ser.read(expected)
        if len(resp) >= 5 and resp[1] == func | 0x80:
            raise ModbusError(f"exception code {resp[2]:#04x} (start={start:#06x}, count={count})")
        if len(resp) < expected:
            raise ModbusError(f"timeout/short response: {resp.hex(' ') or 'nothing'}")
        if crc16(resp[:-2]) != resp[-2:]:
            raise ModbusError(f"CRC mismatch: {resp.hex(' ')}")
        if resp[0] != self.addr or resp[1] != func or resp[2] != 2 * count:
            raise ModbusError(f"unexpected response: {resp.hex(' ')}")
        return list(struct.unpack(f">{count}H", resp[3:3 + 2 * count]))

    def read_status(self):
        """Return (is_raining: bool | None, raw_value). None means an unknown value."""
        raw = self.read_registers(REG_STATUS)[0]
        if raw == STATUS_RAIN:
            return True, raw
        if raw == STATUS_DRY:
            return False, raw
        return None, raw

    def read_config(self):
        address = self.read_registers(REG_ADDRESS)[0]
        baud = self.read_registers(REG_BAUD)[0]
        heat_start, heat_stop = (self.read_registers(r)[0] for r in (REG_HEAT_START, REG_HEAT_STOP))
        return {
            "address": address,
            "baud_register": baud,
            # Temperatures are signed 16-bit in 0.1 degC units.
            "heat_start_c": struct.unpack(">h", struct.pack(">H", heat_start))[0] / 10,
            "heat_stop_c": struct.unpack(">h", struct.pack(">H", heat_stop))[0] / 10,
        }


def describe(is_raining, raw):
    if is_raining is None:
        return f"UNKNOWN (raw={raw:#06x})"
    return "RAIN/SNOW" if is_raining else "DRY"


def main():
    p = argparse.ArgumentParser(description="Read RS485 Modbus rain/snow sensor")
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--addr", type=int, default=1, help="Modbus slave address")
    p.add_argument("--interval", type=float, default=1.0, help="poll period in seconds")
    p.add_argument("--csv", help="append readings to this CSV file")
    p.add_argument("--once", action="store_true", help="read once and exit")
    args = p.parse_args()

    sensor = RainSensor(args.port, args.baud, args.addr)

    try:
        cfg = sensor.read_config()
        print(f"Sensor on {args.port} @ {args.baud} baud, address {cfg['address']}, "
              f"heater on below {cfg['heat_start_c']:.1f} C / off above {cfg['heat_stop_c']:.1f} C "
              f"(baud register raw={cfg['baud_register']})")
    except ModbusError as e:
        print(f"Could not read sensor config: {e}", file=sys.stderr)

    csv_file = writer = None
    if args.csv:
        csv_file = open(args.csv, "a", newline="")
        writer = csv.writer(csv_file)
        if csv_file.tell() == 0:
            writer.writerow(["timestamp", "raining", "raw"])

    if not args.once:
        print("Polling... Ctrl+C to stop.\n")

    prev = None
    try:
        while True:
            ts = datetime.now().isoformat(timespec="seconds")
            try:
                is_raining, raw = sensor.read_status()
            except ModbusError as e:
                print(f"{ts}  ERROR: {e}", file=sys.stderr)
            else:
                changed = prev is not None and is_raining != prev
                print(f"{ts}  {describe(is_raining, raw)}{'   <-- changed' if changed else ''}", flush=True)
                prev = is_raining
                if writer:
                    writer.writerow([ts, "" if is_raining is None else int(is_raining), raw])
                    csv_file.flush()
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sensor.close()
        if csv_file:
            csv_file.close()


if __name__ == "__main__":
    main()
