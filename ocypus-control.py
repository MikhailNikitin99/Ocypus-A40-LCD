#!/usr/bin/env python3
"""
ocypus-control.py
---------------------------------
Ocypus Iota A40 LCD driver (Linux)

Protocol:
  - Init: Feature Report ID=0x07, byte1=0xFD
  - Temperature: Feature Report ID=0x07, bytes1-2=0xFF 0xFF,
                 byte4=tens, byte5=ones, byte7=0x00 (Celsius)
  - Interface: 1 (use -i to change)
"""

import argparse
import sys
import time
from typing import Optional

import psutil
import hid
if not hasattr(hid, 'device'):
    sys.exit(
        "Error: The Python package 'hid' is installed, but it is not 'hidapi'.\n"
        "Please run: pip uninstall hid && pip install hidapi\n"
        "or re-run the installer from the repository."
    )

VID, PID = 0x1a2c, 0x434d
REPORT_ID = 0x07
REPORT_LENGTH = 65
DEFAULT_INTERFACE = 1
DEFAULT_SENSOR = "coretemp"
DEFAULT_REFRESH = 1.0
REINIT_INTERVAL = 30.0
KEEPALIVE_INTERVAL = 2.0


class OcypusController:
    def __init__(self):
        self.device = None
        self.reinit_interval = REINIT_INTERVAL
        self.last_init = 0.0

    def open(self, interface: int = DEFAULT_INTERFACE, path: Optional[str] = None) -> bool:
        devices = hid.enumerate(VID, PID)
        candidates = []
        for d in devices:
            iface = d.get('interface_number')
            p = d['path']
            if isinstance(p, bytes):
                p = p.decode()
            if iface != interface:
                continue
            if path and p != path:
                continue
            candidates.append(d)
        if not candidates:
            print(f"No device on interface {interface}", file=sys.stderr)
            return False
        info = candidates[0]
        dev_path = info['path']
        if isinstance(dev_path, bytes):
            dev_path = dev_path.decode()
        try:
            dev = hid.device()
            dev.open_path(dev_path.encode())
        except Exception as e:
            print(f"Failed to open {dev_path}: {e}", file=sys.stderr)
            return False
        self.device = dev
        if not self.init_display():
            self.close()
            return False
        print(f"Connected to interface {info.get('interface_number')} ({dev_path})", file=sys.stderr)
        return True

    def init_display(self) -> bool:
        """Send the init command (0xFD), used on connect and to wake a blank display."""
        report = [REPORT_ID, 0xFD] + [0] * (REPORT_LENGTH - 2)
        try:
            self.device.send_feature_report(report)
        except Exception as e:
            print(f"Init error: {e}", file=sys.stderr)
            return False
        self.last_init = time.monotonic()
        return True

    def maybe_reinit(self) -> bool:
        """Repeat init every reinit_interval seconds in case the firmware blanked the display."""
        if self.reinit_interval <= 0:
            return True
        if time.monotonic() - self.last_init < self.reinit_interval:
            return True
        return self.init_display()

    def close(self):
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

    def send_temperature(self, temp_celsius: float, unit: str = 'c') -> bool:
        if not self.device:
            return False
        if unit == 'f':
            temp_celsius = temp_celsius * 9 / 5 + 32
        temp = max(0, min(99, int(round(temp_celsius))))
        tens, ones = divmod(temp, 10)
        report = [REPORT_ID] + [0] * (REPORT_LENGTH - 1)
        report[1] = 0xFF
        report[2] = 0xFF
        report[4] = tens
        report[5] = ones
        report[7] = 0x00   # Celsius
        try:
            self.device.send_feature_report(report)
            return True
        except Exception as e:
            print(f"Send error: {e}", file=sys.stderr)
            return False


def get_sensors():
    try:
        return psutil.sensors_temperatures()
    except Exception as e:
        # hwmon can vanish temporarily (suspend, renumbering); don't kill the service
        print(f"sensors_temperatures() failed: {e}", file=sys.stderr)
        return None


def find_sensor(sensors, name, label=None):
    if not sensors:
        return None
    group = sensors.get(name)
    if not group:
        return None
    if label:
        for s in group:
            if s.label == label:
                return s
        return None
    return group[0]


def main():
    parser = argparse.ArgumentParser(description="Ocypus Iota A40 LCD driver")
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list', help='list devices')
    sub.add_parser('sensors', help='list available temperature sensors')

    on_p = sub.add_parser('on', help='stream temperature')
    on_p.add_argument('-u', '--unit', choices=['c', 'f'], default='c')
    on_p.add_argument('-s', '--sensor', default=DEFAULT_SENSOR)
    on_p.add_argument('-l', '--label')
    on_p.add_argument('-r', '--rate', type=float, default=DEFAULT_REFRESH)
    on_p.add_argument('-i', '--interface', type=int, default=DEFAULT_INTERFACE)
    on_p.add_argument('-p', '--path')
    on_p.add_argument('--reinit', type=float, default=REINIT_INTERVAL,
                      help='repeat the display init command every N seconds (0 disables)')

    off_p = sub.add_parser('off', help='blank display')
    off_p.add_argument('-i', '--interface', type=int, default=DEFAULT_INTERFACE)

    args = parser.parse_args()

    if args.cmd == 'list':
        for d in hid.enumerate(VID, PID):
            print(f"interface={d.get('interface_number')} path={d['path'].decode() if isinstance(d['path'], bytes) else d['path']}")
        return
    if args.cmd == 'sensors':
        sensors = get_sensors()
        if sensors is None:
            print("Could not read temperature sensors.", file=sys.stderr)
            sys.exit(1)
        for name, entries in sensors.items():
            for s in entries:
                print(f"{name}\t{s.label or '<unlabelled>'}\t{s.current:.1f}°C")
        return

    ctrl = OcypusController()
    if args.cmd == 'off':
        if ctrl.open(interface=args.interface, path=getattr(args, 'path', None)):
            ctrl.close()
            print("Display turned off.")
        else:
            sys.exit(1)
        return

    # on
    ctrl.reinit_interval = args.reinit
    if not ctrl.open(interface=args.interface, path=getattr(args, 'path', None)):
        sys.exit(1)

    import signal
    stop = False
    def handler(signum, frame):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    print(f"Display started (sensor={args.sensor}, unit={args.unit})", file=sys.stderr)
    last_temp = None
    last_keepalive = time.monotonic()
    while not stop:
        # Wake a display that the firmware blanked: writes keep succeeding but nothing
        # is shown until the init command is repeated.
        if not ctrl.maybe_reinit():
            print("\rInit failed: restarting service", file=sys.stderr, flush=True)
            ctrl.close()
            sys.exit(1)
        sensors = get_sensors()
        sensor = find_sensor(sensors, args.sensor, args.label)
        if sensor:
            try:
                temp = float(sensor.current)
            except (TypeError, ValueError):
                temp = 0.0
            if ctrl.send_temperature(temp, args.unit):
                last_temp = temp
                last_keepalive = time.monotonic()
                print(f"\r{sensor.label or args.sensor}: {temp:.1f}°{args.unit.upper()}", end='', flush=True)
            else:
                # The HID handle is dead (USB reset/unplug, short write). Exit and let
                # systemd restart us so the device is re-opened and re-initialised.
                print("\rSend failed: restarting service", file=sys.stderr, flush=True)
                ctrl.close()
                sys.exit(1)
        else:
            print(f"\rSensor '{args.sensor}' not found", end='', flush=True)
            # Keep the display alive with the last known value, never 0 °C.
            if last_temp is not None and time.monotonic() - last_keepalive > KEEPALIVE_INTERVAL:
                if not ctrl.send_temperature(last_temp, args.unit):
                    print("\rSend failed: restarting service", file=sys.stderr, flush=True)
                    ctrl.close()
                    sys.exit(1)
                last_keepalive = time.monotonic()
        time.sleep(args.rate)

    ctrl.close()
    print()


if __name__ == "__main__":
    main()
