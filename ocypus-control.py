#!/usr/bin/env python3
"""
ocypus-control.py
---------------------------------
Ocypus Iota A40 LCD driver (Linux)

Protocol:
  - Init: Feature Report ID=0x07, byte1=0xFD
  - Temperature: Feature Report ID=0x07, bytes1-2=0xFF 0xFF,
                 byte4=tens, byte5=ones, byte7=0x00 (Celsius) or 0x01 (Fahrenheit)
  - Interface: 1 (use -i to change)
"""

import argparse
import math
import os
import sys
import threading
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


def env_float(name: str, default: float) -> float:
    """Read a float from the environment, falling back to default on bad input."""
    try:
        value = float(os.environ[name])
    except (KeyError, ValueError):
        return default
    if not math.isfinite(value):
        print(f"Ignoring non-finite {name}={os.environ[name]!r}", file=sys.stderr)
        return default
    return value


def display_value(temp_celsius: float, unit: str) -> Optional[int]:
    """Return the integer shown on the two-digit display, or None if not finite."""
    value = temp_celsius * 9 / 5 + 32 if unit == 'f' else temp_celsius
    if not math.isfinite(value):
        return None
    return max(0, min(99, int(round(value))))


DEFAULT_SENSOR = os.environ.get("OCYPUS_SENSOR", "coretemp")
DEFAULT_REFRESH = env_float("OCYPUS_RATE", 1.0)
REINIT_INTERVAL = env_float("OCYPUS_REINIT", 30.0)
KEEPALIVE_INTERVAL = 10.0
RECONNECT_MIN = 1.0
RECONNECT_MAX = 30.0
FALLBACK_SENSORS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")


class OcypusController:
    def __init__(self):
        self.device = None
        self.reinit_interval = REINIT_INTERVAL
        self.last_init = 0.0

    def open(self, interface: int = DEFAULT_INTERFACE, path: Optional[str] = None) -> bool:
        self.close()
        try:
            devices = hid.enumerate(VID, PID)
        except Exception as e:
            print(f"Device enumeration failed: {e}", file=sys.stderr)
            return False
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
        dev = None
        try:
            dev = hid.device()
            dev.open_path(dev_path.encode())
        except Exception as e:
            if dev is not None:
                try:
                    dev.close()
                except Exception:
                    pass
            print(f"Failed to open {dev_path}: {e}", file=sys.stderr)
            return False
        self.device = dev
        if not self.init_display():
            self.close()
            return False
        print(f"Connected to interface {info.get('interface_number')} ({dev_path})", file=sys.stderr)
        return True

    def _send(self, report) -> bool:
        if not self.device:
            return False
        try:
            written = self.device.send_feature_report(report)
        except Exception as e:
            print(f"Send error: {e}", file=sys.stderr)
            return False
        # hidapi returns the number of bytes written; a short write means the
        # handle is dead even though no exception was raised.
        if isinstance(written, int) and written < REPORT_LENGTH:
            print(f"Short write: {written}/{REPORT_LENGTH} bytes", file=sys.stderr)
            return False
        return True

    def init_display(self) -> bool:
        """Send the init command (0xFD), used on connect and to wake a blank display."""
        report = [REPORT_ID, 0xFD] + [0] * (REPORT_LENGTH - 2)
        if not self._send(report):
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
        value = display_value(temp_celsius, unit)
        if value is None:
            return False
        tens, ones = divmod(value, 10)
        report = [REPORT_ID] + [0] * (REPORT_LENGTH - 1)
        report[1] = 0xFF
        report[2] = 0xFF
        report[4] = tens
        report[5] = ones
        report[7] = 0x01 if unit == 'f' else 0x00
        return self._send(report)


_sensors_error = None


def get_sensors():
    global _sensors_error
    try:
        sensors = psutil.sensors_temperatures()
    except Exception as e:
        # hwmon can vanish temporarily (suspend, renumbering); log the transition only
        message = str(e)
        if message != _sensors_error:
            print(f"sensors_temperatures() failed: {message}", file=sys.stderr)
            _sensors_error = message
        return None
    _sensors_error = None
    return sensors


def pick_sensor(sensors, requested, label=None, active=None, fallback=True):
    """Return (name, entry, value) of the first readable sensor.

    The active sensor is preferred, so the driver does not flap between sensors.
    If none of the entries has a usable value, name is the first group that
    exists and value is None.
    """
    names = []
    if active:
        names.append(active)
    names.append(requested)
    if fallback:
        names.extend(FALLBACK_SENSORS)

    seen = set()
    first_seen = None
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        group = sensors.get(name) if sensors else None
        if not group:
            continue
        if first_seen is None:
            first_seen = name
        for entry in group:
            if label and entry.label != label:
                continue
            try:
                value = float(entry.current)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                return name, entry, value
    return first_seen, None, None


def wait_event(event, seconds):
    """Wait up to seconds, waking regularly so signals are handled promptly."""
    deadline = time.monotonic() + seconds
    while not event.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        event.wait(min(remaining, 0.5))
    return True


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
    on_p.add_argument('--no-fallback', action='store_true',
                      help='use only the selected sensor, without fallback')

    off_p = sub.add_parser('off', help='blank the display (not supported yet)')
    off_p.add_argument('-i', '--interface', type=int, default=DEFAULT_INTERFACE)

    args = parser.parse_args()

    if args.cmd == 'list':
        try:
            devices = hid.enumerate(VID, PID)
        except Exception as e:
            print(f"Device enumeration failed: {e}", file=sys.stderr)
            sys.exit(1)
        for d in devices:
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

    if args.cmd == 'off':
        # The blanking command is unknown and opening the device wakes the panel,
        # so report the limitation instead of pretending it worked.
        print("Turning the display off is not supported yet.", file=sys.stderr)
        sys.exit(1)

    ctrl = OcypusController()
    # on
    if not math.isfinite(args.rate) or args.rate <= 0:
        parser.error("--rate must be a finite number > 0")
    if not math.isfinite(args.reinit):
        parser.error("--reinit must be a finite number")
    ctrl.reinit_interval = args.reinit

    import signal
    stop_event = threading.Event()

    def handler(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    last_temp = None
    last_sent_int = None
    last_keepalive = 0.0
    init_mark = 0.0
    reading_ok = True
    active_sensor = args.sensor
    force_send = False

    def connect():
        delay = RECONNECT_MIN
        attempts = 0
        while not stop_event.is_set():
            if ctrl.open(interface=args.interface, path=args.path):
                if attempts:
                    print("Reconnected", file=sys.stderr, flush=True)
                return True
            attempts += 1
            print(f"Retrying in {delay:.0f}s", file=sys.stderr, flush=True)
            if wait_event(stop_event, delay):
                return False
            delay = min(delay * 2, RECONNECT_MAX)
        return False

    def reconnect():
        nonlocal last_sent_int, last_keepalive, init_mark, force_send
        ctrl.close()
        if not connect():
            return False
        # init cleared the display, so send the next value right away.
        last_sent_int = None
        last_keepalive = time.monotonic()
        init_mark = ctrl.last_init
        force_send = True
        return True

    if not connect():
        ctrl.close()
        return
    last_keepalive = time.monotonic()
    init_mark = ctrl.last_init
    print(f"Display started (sensor={args.sensor}, unit={args.unit})", file=sys.stderr)

    while not stop_event.is_set():
        # Wake a display that the firmware blanked: writes keep succeeding but nothing
        # is shown until the init command is repeated.
        if not ctrl.maybe_reinit():
            print("Init failed; reconnecting", file=sys.stderr, flush=True)
            if not reconnect():
                break
            continue
        sensors = get_sensors()
        name, sensor, temp = pick_sensor(
            sensors, args.sensor, args.label, active_sensor, not args.no_fallback
        )

        # Send only when the displayed value changes, on keepalive, or right after init
        # (init clears the screen, so the value has to be sent again).
        due = time.monotonic() - last_keepalive >= KEEPALIVE_INTERVAL
        reinit_done = ctrl.last_init > init_mark

        if temp is not None:
            if not reading_ok:
                print(f"Sensor '{name}' is back", file=sys.stderr, flush=True)
                reading_ok = True
                active_sensor = name
            elif name != active_sensor:
                print(f"Sensor '{active_sensor}' is unavailable, using '{name}'",
                      file=sys.stderr, flush=True)
                active_sensor = name
            value_int = display_value(temp, args.unit)
            changed = last_sent_int != value_int
            if changed or due or reinit_done or force_send:
                if ctrl.send_temperature(temp, args.unit):
                    last_temp = temp
                    last_sent_int = value_int
                    last_keepalive = time.monotonic()
                    init_mark = ctrl.last_init
                    force_send = False
                    if changed:
                        print(f"{sensor.label or name}: {value_int}°{args.unit.upper()}", flush=True)
                else:
                    # The HID handle is dead (USB reset/unplug, short write).
                    print("Send failed; reconnecting", file=sys.stderr, flush=True)
                    if not reconnect():
                        break
                    continue
        else:
            if reading_ok:
                if sensors is None:
                    pass  # get_sensors() already reported the error
                elif name:
                    print(f"No reading from sensor '{name}'", file=sys.stderr, flush=True)
                else:
                    print(f"Sensor '{active_sensor}' not found", file=sys.stderr, flush=True)
                reading_ok = False
            # Keep the display alive with the last known value, never 0 °C.
            if last_temp is not None and (due or reinit_done or force_send):
                if not ctrl.send_temperature(last_temp, args.unit):
                    print("Send failed; reconnecting", file=sys.stderr, flush=True)
                    if not reconnect():
                        break
                    continue
                last_sent_int = display_value(last_temp, args.unit)
                last_keepalive = time.monotonic()
                init_mark = ctrl.last_init
                force_send = False
        wait_event(stop_event, args.rate)

    ctrl.close()


if __name__ == "__main__":
    main()
