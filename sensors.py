"""Drivers for the docking-station weather sensors on the shared RS485 Modbus bus.

All devices: 9600 baud 8N1. Wiring: red=VCC, black=GND, yellow=485-A, green=485-B.

| Sensor             | Addr | Registers (function 0x03)                                   | Source            |
|--------------------|------|-------------------------------------------------------------|-------------------|
| Rain/snow          | 1    | 0x0000: 0x000A dry, 0x000B rain/snow                        | datasheet         |
| Wind speed         | 3    | 0x0000: speed x0.1 m/s                                      | label + observed  |
| Wind direction     | 4    | 0x0000: angle x0.1 deg, 0x0001: 8-sector index 0=N..7=NW    | observed          |
| Temp/humidity      | 2    | 0x0000: RH x0.1 %, 0x0001: temperature x0.1 degC (signed)   | observed          |

Temp/humidity config: 0x0100 = Modbus address (factory default 1, changed to 2 so it
doesn't clash with the rain sensor; takes effect after a power cycle), 0x0101 = baud code
(2 = 9600). Only change an address with that device alone on the bus.

Scalings marked "observed"/"typical" were not taken from a datasheet; verify them
(blow on the cups, turn the vane to north, compare temperature with a thermometer).
"""
from modbus_rtu import to_signed

DIRECTIONS_8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class RainSensor:
    name = "rain"
    REG_STATUS, REG_HEAT_START, REG_HEAT_STOP = 0x0000, 0x006B, 0x006C
    DRY, RAIN = 0x000A, 0x000B

    def __init__(self, bus, addr=1):
        self.bus, self.addr = bus, addr

    def read(self):
        raw = self.bus.read_registers(self.addr, self.REG_STATUS)[0]
        raining = {self.RAIN: True, self.DRY: False}.get(raw)
        return {"raining": raining, "rain_raw": raw}

    def read_config(self):
        start = to_signed(self.bus.read_registers(self.addr, self.REG_HEAT_START)[0]) / 10
        stop = to_signed(self.bus.read_registers(self.addr, self.REG_HEAT_STOP)[0]) / 10
        return {"heat_start_c": start, "heat_stop_c": stop}

    @staticmethod
    def format(d):
        if d["raining"] is None:
            return f"rain=UNKNOWN(raw={d['rain_raw']:#06x})"
        return "rain=RAIN/SNOW" if d["raining"] else "rain=DRY"


class WindSpeedSensor:
    name = "wind_speed"
    SCALE = 0.1  # m/s per count

    def __init__(self, bus, addr=3):
        self.bus, self.addr = bus, addr

    def read(self):
        raw = self.bus.read_registers(self.addr, 0x0000)[0]
        return {"wind_speed_ms": round(raw * self.SCALE, 2), "wind_speed_raw": raw}

    @staticmethod
    def format(d):
        return f"wind_speed={d['wind_speed_ms']:5.1f} m/s"


class WindDirectionSensor:
    name = "wind_direction"

    def __init__(self, bus, addr=4):
        self.bus, self.addr = bus, addr

    def read(self):
        angle_raw, sector = self.bus.read_registers(self.addr, 0x0000, 2)
        return {
            "wind_dir_deg": angle_raw / 10,
            "wind_dir": DIRECTIONS_8[sector] if sector < 8 else f"?{sector}",
            "wind_dir_sector": sector,
        }

    @staticmethod
    def format(d):
        return f"wind_dir={d['wind_dir']:>2} ({d['wind_dir_deg']:5.1f} deg)"


class TempHumiditySensor:
    name = "temp_humidity"

    def __init__(self, bus, addr=2):
        self.bus, self.addr = bus, addr

    def read(self):
        rh_raw, t_raw = self.bus.read_registers(self.addr, 0x0000, 2)
        return {"humidity_pct": rh_raw / 10, "temperature_c": to_signed(t_raw) / 10}

    @staticmethod
    def format(d):
        return f"temp={d['temperature_c']:5.1f} C  RH={d['humidity_pct']:5.1f} %"
