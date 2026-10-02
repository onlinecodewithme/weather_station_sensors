"""Minimal Modbus RTU master over a serial RS485 adapter (pyserial only)."""
import struct
import time

import serial


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


class ModbusError(Exception):
    pass


class ModbusRTU:
    """One shared bus; several slaves can be queried through the same instance."""

    def __init__(self, port="/dev/ttyUSB0", baud=9600, timeout=0.5, retries=2):
        self.ser = serial.Serial(port, baud, bytesize=8, parity="N", stopbits=1, timeout=timeout)
        self.retries = retries
        # Silent gap between frames (Modbus needs >= 3.5 chars; be generous).
        self.gap = max(0.02, 3.5 * 11 / baud)

    def close(self):
        self.ser.close()

    def read_registers(self, addr, start, count=1, func=0x03):
        last_err = None
        for _ in range(self.retries + 1):
            try:
                return self._read_once(addr, start, count, func)
            except ModbusError as e:
                last_err = e
                time.sleep(0.05)
        raise last_err

    def write_register(self, addr, reg, value):
        """Function 0x06 (write single register). The slave echoes the request on success."""
        req = bytes([addr, 0x06]) + struct.pack(">HH", reg, value)
        req += crc16(req)
        time.sleep(self.gap)
        self.ser.reset_input_buffer()
        self.ser.write(req)
        resp = self.ser.read(8)
        if len(resp) >= 5 and resp[1] == 0x86:
            raise ModbusError(f"addr {addr}: write exception code {resp[2]:#04x} (reg={reg:#06x})")
        if resp != req:
            raise ModbusError(f"addr {addr}: write not echoed: {resp.hex(' ') or 'nothing'}")

    def _read_once(self, addr, start, count, func):
        req = bytes([addr, func]) + struct.pack(">HH", start, count)
        req += crc16(req)
        time.sleep(self.gap)
        self.ser.reset_input_buffer()
        self.ser.write(req)

        expected = 5 + 2 * count
        resp = self.ser.read(expected)
        if len(resp) >= 5 and resp[0] == addr and resp[1] == func | 0x80:
            raise ModbusError(f"addr {addr}: exception code {resp[2]:#04x} (start={start:#06x}, count={count})")
        if len(resp) < expected:
            raise ModbusError(f"addr {addr}: timeout/short response: {resp.hex(' ') or 'nothing'}")
        if crc16(resp[:-2]) != resp[-2:]:
            raise ModbusError(f"addr {addr}: CRC mismatch: {resp.hex(' ')}")
        if resp[0] != addr or resp[1] != func or resp[2] != 2 * count:
            raise ModbusError(f"addr {addr}: unexpected response: {resp.hex(' ')}")
        return list(struct.unpack(f">{count}H", resp[3:3 + 2 * count]))


def to_signed(value):
    return value - 0x10000 if value & 0x8000 else value
