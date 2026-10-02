#!/usr/bin/env python3
"""Poll all docking-station weather sensors on the shared RS485 bus.

Examples:
    python3 weather_station.py                              # all sensors, every 1 s
    python3 weather_station.py --sensors wind_speed,wind_direction
    python3 weather_station.py --temp-addr 5                # temp/humidity sensor address
    python3 weather_station.py --csv weather_log.csv        # also log to CSV
    python3 weather_station.py --once
"""
import argparse
import csv
import sys
import time
from datetime import datetime

from modbus_rtu import ModbusError, ModbusRTU
from sensors import RainSensor, TempHumiditySensor, WindDirectionSensor, WindSpeedSensor

ALL = ["rain", "wind_speed", "wind_direction", "temp_humidity"]
CSV_FIELDS = ["timestamp", "raining", "rain_raw", "wind_speed_ms", "wind_speed_raw",
              "wind_dir", "wind_dir_deg", "wind_dir_sector", "temperature_c", "humidity_pct"]


def main():
    p = argparse.ArgumentParser(description="Read RS485 Modbus weather sensors")
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--sensors", default=",".join(ALL), help=f"comma list from {ALL}")
    p.add_argument("--rain-addr", type=int, default=1)
    p.add_argument("--wind-speed-addr", type=int, default=3)
    p.add_argument("--wind-dir-addr", type=int, default=4)
    p.add_argument("--temp-addr", type=int, default=2)
    p.add_argument("--interval", type=float, default=1.0, help="poll period in seconds")
    p.add_argument("--csv", help="append readings to this CSV file")
    p.add_argument("--once", action="store_true", help="read once and exit")
    args = p.parse_args()

    wanted = [s.strip() for s in args.sensors.split(",") if s.strip()]
    unknown = set(wanted) - set(ALL)
    if unknown:
        p.error(f"unknown sensor(s): {', '.join(sorted(unknown))}")

    bus = ModbusRTU(args.port, args.baud)
    factories = {
        "rain": lambda: RainSensor(bus, args.rain_addr),
        "wind_speed": lambda: WindSpeedSensor(bus, args.wind_speed_addr),
        "wind_direction": lambda: WindDirectionSensor(bus, args.wind_dir_addr),
        "temp_humidity": lambda: TempHumiditySensor(bus, args.temp_addr),
    }
    sensors = [factories[name]() for name in wanted]

    print(f"Bus {args.port} @ {args.baud} baud: "
          + ", ".join(f"{s.name}@{s.addr}" for s in sensors))
    for s in sensors:
        if isinstance(s, RainSensor):
            try:
                cfg = s.read_config()
                print(f"  rain heater: on below {cfg['heat_start_c']:.1f} C, off above {cfg['heat_stop_c']:.1f} C")
            except ModbusError as e:
                print(f"  rain config unavailable: {e}", file=sys.stderr)

    csv_file = writer = None
    if args.csv:
        csv_file = open(args.csv, "a", newline="")
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if csv_file.tell() == 0:
            writer.writeheader()

    if not args.once:
        print("Polling... Ctrl+C to stop.\n")

    try:
        while True:
            ts = datetime.now().isoformat(timespec="seconds")
            row = {"timestamp": ts}
            parts = []
            for s in sensors:
                try:
                    d = s.read()
                except ModbusError as e:
                    parts.append(f"{s.name}=ERR")
                    print(f"{ts}  {s.name}: {e}", file=sys.stderr)
                else:
                    row.update(d)
                    parts.append(s.format(d))
            print(f"{ts}  " + "  |  ".join(parts), flush=True)
            if writer:
                writer.writerow(row)
                csv_file.flush()
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        bus.close()
        if csv_file:
            csv_file.close()


if __name__ == "__main__":
    main()
