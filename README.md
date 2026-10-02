# Weather Station Sensors (Drone Docking Station)

Python tools for reading the docking station's weather sensors over a single RS485 bus
using Modbus RTU through a USB–RS485 adapter.

| Sensor | Modbus address | Measures |
|---|---|---|
| Capacitive rain/snow sensor | 1 | Rain/snow present or not |
| Air temperature & humidity transmitter | 2 | Temperature (°C), relative humidity (%RH) |
| Wind speed sensor (cup anemometer) | 3 | Wind speed (m/s, 0–30) |
| Wind direction sensor (vane) | 4 | Direction (8 sectors) and angle (°) |

Example output:

```
Bus /dev/ttyUSB0 @ 9600 baud: rain@1, wind_speed@3, wind_direction@4, temp_humidity@2
  rain heater: on below 5.0 C, off above 30.0 C
Polling... Ctrl+C to stop.

2026-10-02T15:57:46  rain=DRY  |  wind_speed=  0.0 m/s  |  wind_dir= E ( 96.6 deg)  |  temp= 32.3 C  RH= 65.4 %
```

---

## Contents

- [Hardware](#hardware)
- [Wiring](#wiring)
- [Installation](#installation)
- [Usage](#usage)
- [Sensor register reference](#sensor-register-reference)
- [Project structure](#project-structure)
- [Using the drivers from your own code](#using-the-drivers-from-your-own-code)
- [Adding a new sensor](#adding-a-new-sensor)
- [Changing a sensor's Modbus address](#changing-a-sensors-modbus-address)
- [Troubleshooting](#troubleshooting)
- [Verification status](#verification-status)

---

## Hardware

- **USB–RS485 adapter**: FTDI FT232R based (`0403:6001`), shows up as `/dev/ttyUSB0`.
  Note: although it may be sold as "USB-CAN", this adapter and these sensors speak
  **RS485 Modbus RTU**, not CAN.
- **Bus settings** (all four sensors): 9600 baud, 8 data bits, no parity, 1 stop bit (8N1).
- **Power**:
  - Rain/snow sensor: 12–24 V DC
  - Temperature/humidity transmitter: 12–24 V DC
  - Wind speed and wind direction sensors: 5–24 V DC

  Use a single **12–24 V DC** supply for all sensors. 5 V is not enough for the rain and
  temperature sensors; they stay silent on the bus.

## Wiring

All sensors share the same two RS485 data lines (a multi-drop bus). Connect every
sensor's A to the adapter's **A+** and every B to the adapter's **B−**.

| Wire colour | Function | Connect to |
|---|---|---|
| Red | Power + (VCC) | +12–24 V DC |
| Black | Power − (GND) | Supply GND |
| Yellow | RS485 A | Adapter **A+** |
| Green | RS485 B | Adapter **B−** |

```
            +12..24V ──┬──────────┬──────────┬──────────┐
                 GND ──┼──┬───────┼──┬───────┼──┬───────┼──┐
                       │  │       │  │       │  │       │  │
                     [Rain]    [Temp/RH]  [Wind spd] [Wind dir]
                      addr 1    addr 2     addr 3     addr 4
                       │  │       │  │       │  │       │  │
USB-RS485  A+ ─────────┴──┼───────┴──┼───────┴──┼───────┴  │
adapter    B− ────────────┴──────────┴──────────┴──────────┘
```

Rain sensor mounting: keep the sensing face tilted about **15°** from horizontal so water
and snow run off.

## Installation

Requires Python 3.8+ and `pyserial`.

```bash
git clone git@github.com:onlinecodewithme/weather_station_sensors.git
cd weather_station_sensors
pip install -r requirements.txt
```

Serial port permission: your user must be in the `dialout` group:

```bash
sudo usermod -aG dialout $USER   # then log out and back in
```

## Usage

### Read all sensors: `weather_station.py`

```bash
python3 weather_station.py                                  # all sensors, every 1 s
python3 weather_station.py --once                           # single reading, then exit
python3 weather_station.py --interval 5                     # every 5 s
python3 weather_station.py --csv weather_log.csv            # also append to CSV
python3 weather_station.py --sensors wind_speed,wind_direction   # subset only
```

| Option | Default | Description |
|---|---|---|
| `--port` | `/dev/ttyUSB0` | Serial device of the USB–RS485 adapter |
| `--baud` | `9600` | Bus baud rate |
| `--sensors` | all | Comma list: `rain`, `wind_speed`, `wind_direction`, `temp_humidity` |
| `--rain-addr` | `1` | Rain sensor address |
| `--temp-addr` | `2` | Temperature/humidity sensor address |
| `--wind-speed-addr` | `3` | Wind speed sensor address |
| `--wind-dir-addr` | `4` | Wind direction sensor address |
| `--interval` | `1.0` | Seconds between polls |
| `--csv` | none | Append readings to this CSV file (header written if new) |
| `--once` | off | Read once and exit |

If a sensor doesn't respond, its field shows `ERR`, the error goes to stderr, and the other
sensors keep updating.

**CSV columns:** `timestamp, raining, rain_raw, wind_speed_ms, wind_speed_raw, wind_dir,
wind_dir_deg, wind_dir_sector, temperature_c, humidity_pct`

### Find devices on the bus: `find_devices.py`

A read-only scan of Modbus addresses. Use it after wiring changes or when a sensor goes missing.

```bash
python3 find_devices.py                      # 9600 and 4800 baud, addresses 1–247
python3 find_devices.py --baud 9600 --last 10
```

### Rain sensor only: `rain_sensor.py`

A standalone rain/snow reader with change detection (`<-- changed`) and CSV logging.

```bash
python3 rain_sensor.py
python3 rain_sensor.py --csv rain_log.csv
```

## Sensor register reference

All reads use Modbus function `0x03` (read holding registers). Values are 16-bit, big-endian.

### Rain/snow sensor: address 1

| Register | Content | Access | Decoding |
|---|---|---|---|
| `0x0000` | Rain/snow status | R | `0x000A` = dry, `0x000B` = rain/snow |
| `0x0030` | Device address | R/W | 1–253 |
| `0x0031` | Baud rate | R/W | Value ÷ 10 per datasheet (e.g. `1920` = 19200). This unit reads `38400` while running at 9600, so don't rely on it |
| `0x006B` | Heater start temperature | R/W | Signed, 0.1 °C (heater on below this). This unit: 5.0 °C |
| `0x006C` | Heater stop temperature | R/W | Signed, 0.1 °C (heater off above this). This unit: 30.0 °C |

Between the two heater temperatures, the heater runs only while it is raining.

### Temperature & humidity transmitter: address 2

| Register | Content | Access | Decoding |
|---|---|---|---|
| `0x0000` | Relative humidity | R | ÷ 10 → %RH |
| `0x0001` | Temperature | R | Signed, ÷ 10 → °C |
| `0x0100` | Device address | R/W | Factory default 1; **set to 2** on this station. Takes effect after a power cycle |
| `0x0101` | Baud rate code | R/W | `2` = 9600 |

This sensor returns junk, not an error, for registers it doesn't implement.

### Wind speed sensor: address 3

| Register | Content | Access | Decoding |
|---|---|---|---|
| `0x0000` | Wind speed | R | ÷ 10 → m/s (range 0–30 m/s) |

### Wind direction sensor: address 4

| Register | Content | Access | Decoding |
|---|---|---|---|
| `0x0000` | Angle | R | ÷ 10 → degrees (0–360) |
| `0x0001` | Sector (8 directions) | R | `0`=N, `1`=NE, `2`=E, `3`=SE, `4`=S, `5`=SW, `6`=W, `7`=NW |

The angle is measured relative to the sensor's north marking. Align that marking with true
north when mounting.

## Project structure

```
.
├── modbus_rtu.py       # Modbus RTU master: CRC, read/write registers, retries, frame gaps
├── sensors.py          # One driver class per sensor (addresses, scaling, decoding)
├── weather_station.py  # CLI: polls all sensors, prints and logs to CSV
├── find_devices.py     # CLI: read-only bus scanner
├── rain_sensor.py      # CLI: standalone rain sensor reader (self-contained)
└── requirements.txt
```

## Using the drivers from your own code

```python
from modbus_rtu import ModbusRTU, ModbusError
from sensors import RainSensor, TempHumiditySensor, WindSpeedSensor, WindDirectionSensor

bus = ModbusRTU("/dev/ttyUSB0", 9600)
rain = RainSensor(bus, addr=1)
temp = TempHumiditySensor(bus, addr=2)
speed = WindSpeedSensor(bus, addr=3)
direction = WindDirectionSensor(bus, addr=4)

try:
    print(rain.read())       # {'raining': False, 'rain_raw': 10}
    print(temp.read())       # {'humidity_pct': 65.4, 'temperature_c': 32.3}
    print(speed.read())      # {'wind_speed_ms': 0.0, 'wind_speed_raw': 0}
    print(direction.read())  # {'wind_dir_deg': 96.6, 'wind_dir': 'E', 'wind_dir_sector': 2}
except ModbusError as e:
    print("sensor error:", e)
finally:
    bus.close()
```

`ModbusRTU` is not thread-safe. Use one instance per serial port, from one thread.

## Adding a new sensor

1. **Check its default address first.** Many sensors ship at address 1, which is already
   taken by the rain sensor. Two devices with the same address make one of them invisible.
2. Connect it **alone** on the bus and run `python3 find_devices.py` to find its address and baud rate.
3. If needed, change its address (see below) to a free one (e.g. 5).
4. Add a class to `sensors.py` with `name`, `read()` returning a dict, and `format()`.
   Then register it in `weather_station.py` (`ALL`, `factories`, `CSV_FIELDS`, and an
   address option).

## Changing a sensor's Modbus address

Only do this with the **target sensor alone on the bus**; a write to a shared address
changes every device that answers it. Check the register in the sensor's manual first.

```python
from modbus_rtu import ModbusRTU
bus = ModbusRTU("/dev/ttyUSB0", 9600)
print(bus.read_registers(1, 0x0100, 1))   # confirm current value (should be the current address)
bus.write_register(1, 0x0100, 2)          # temp/humidity sensor: address register 0x0100
bus.close()
# Power-cycle the sensor, then: python3 find_devices.py --baud 9600 --last 10
```

Address registers on this station: rain sensor `0x0030`, temperature/humidity `0x0100`.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Permission denied: '/dev/ttyUSB0'` | Add your user to `dialout` (see Installation) |
| No port `/dev/ttyUSB0` | Check `lsusb` for `0403:6001`, re-plug the adapter, or pass `--port` |
| One sensor shows `ERR`, others fine | That sensor's power (rain and temp need ≥ 12 V), A/B wiring, or address |
| Sensor never found by `find_devices.py` | Swap its A/B wires; check supply voltage at the sensor; test it alone on the bus |
| A newly added sensor is invisible | Address clash: it shares an address with another device. Isolate it and change its address |
| `CRC mismatch` / garbled replies | Two devices on one address, a loose A/B connection, or a long bus without termination (add a 120 Ω resistor between A and B at the far end) |
| Occasional single timeouts | Normal on RS485; the driver retries twice automatically |
| Wind direction is offset | The sensor's north marking isn't aligned with true north |

## Verification status

| Item | Source | Status |
|---|---|---|
| Rain status codes, heater registers | Manufacturer datasheet | Confirmed (dry and wet both observed) |
| Temp/humidity ÷ 10 scaling | Typical for this sensor family; readings plausible (32 °C, 65 %RH) | Compare once against a reference thermometer/hygrometer |
| Temp/humidity address register `0x0100` | Found on the device; address change to 2 confirmed | Confirmed |
| Wind speed ÷ 10 scaling | Typical for this sensor family | Not yet checked under wind; compare with a handheld anemometer |
| Wind direction angle ÷ 10 and sector index | Angle and sector agree in two positions (26.7° → NE, 96° → E) | Check N/S/W positions |
