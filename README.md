# Ocypus Iota A40 LCD driver for Linux

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-supported-FCC624?logo=linux&logoColor=black)
![USB HID](https://img.shields.io/badge/USB-HID-orange)
![License](https://img.shields.io/badge/License-MIT-green)

A lightweight Linux driver for the **Ocypus Iota A40** CPU cooler LCD.

It reads CPU temperature using `psutil` and displays it on the cooler's built-in USB LCD over the native HID protocol.

---

## Features

- 🌡 Display CPU temperature in Celsius or Fahrenheit
- 🧩 Compatible with any `psutil` temperature sensor (`coretemp`, `k10temp`, ...)
- 🔌 Native USB HID communication
- 🔧 Recovers from USB resets and from a blanked display automatically
- ⚙️ systemd service included
- 🐧 Linux-native implementation
- 📦 Simple installer
- 🚫 No proprietary software required

---

## Supported Hardware

| Device | Status |
|---------|:------:|
| Ocypus Iota A40 | ✅ |
| Ocypus A62 | Community support |
| Ocypus L36 | Community support |

USB Device ID

```
VID: 1A2C
PID: 434D
```

The LCD is controlled through **HID Interface 1** using **Report ID `0x07`**.

---

# Requirements

- Linux
- Python 3.9+
- `psutil`
- `hidapi`
- systemd
- udev

> **Note**
> The installer supports systemd-based distributions only. Alpine/OpenRC is not
> supported.

> **Important**
>
> Install **`hidapi`**, **NOT** the package named `hid`.

---

# Installation

## Automatic

```bash
git clone https://github.com/MikhailNikitin99/Ocypus-A40-LCD.git
cd Ocypus-A40-LCD

sudo ./install.sh
```

The installer automatically:

- creates an `ocypus` system user
- adds the invoking user to the `ocypus` group for CLI access
- installs Python dependencies from prebuilt wheels
- installs udev rules (including disabling USB autosuspend for the cooler)
- installs the `ocypus-control` command into `/usr/local/bin`
- installs the systemd service
- enables automatic startup

After the first installation, log out and back in (or run `newgrp ocypus`)
so the CLI can open the device without `sudo`. The service itself starts
immediately.

Build tools, libusb headers and Python headers are installed only if no prebuilt
wheel is available for your platform.

Re-run `sudo ./install.sh` to update an existing installation: it copies the new
files and restarts the service.

---

## Manual

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

sudo cp ocypus-control.py /usr/local/bin/
sudo chmod +x /usr/local/bin/ocypus-control.py

sudo groupadd --system ocypus 2>/dev/null || true
sudo useradd --system --gid ocypus --no-create-home --shell /usr/sbin/nologin ocypus 2>/dev/null || true
sudo usermod -aG ocypus "$USER"

sudo cp udev/99-ocypus-a40.rules /etc/udev/rules.d/

sudo udevadm control --reload-rules
sudo udevadm trigger
```

> **Note**
> On Debian/Ubuntu, install `python3-venv` first if `python3 -m venv` fails.

> **Note**
> The manual path uses the local `.venv`. Run the script with
> `.venv/bin/python /usr/local/bin/ocypus-control.py`, and log out and back in
> after `usermod` so the `ocypus` group is active.

> **Note**
> The bundled systemd unit expects the script in `/opt/ocypus-a40-lcd` with a
> virtualenv (`/opt/ocypus-a40-lcd/.venv/bin/python`). Use `install.sh` for the
> service, or adjust `ExecStart` in `systemd/ocypus-lcd.service` to your paths.

---

# Usage

After `install.sh` and a re-login (or `newgrp ocypus`), the CLI is available as
`ocypus-control` (a launcher that uses the virtualenv).

Show available sensors

```bash
ocypus-control sensors
```

Stream temperature (the sensor defaults to `coretemp`)

```bash
ocypus-control on
```

Specific sensor

```bash
ocypus-control on -s coretemp
```

If the selected sensor is unavailable, the driver falls back to `coretemp`,
`k10temp`, `zenpower`, `cpu_thermal`, and `acpitz`, and logs which one it uses.
Disable this with `--no-fallback`.

The driver stays on the first sensor that produced a reading, so it does not
flap between sensors; it switches only if that sensor becomes unreadable.

Fahrenheit

```bash
ocypus-control on -u f
```

> **Note**
> The display has two digits, so values above 99 are shown as 99. In Fahrenheit
> mode typical CPU temperatures (100 °F and above) therefore cap at 99 °F.

Refresh every 2 seconds

```bash
ocypus-control on -r 2
```

Re-initialise the display every 15 seconds (default: 30, `0` disables)

```bash
ocypus-control on --reinit 15
```

> **Note**
> With `--reinit 0` a blank display stays blank until the driver is restarted;
> the driver prints a warning when this mode is enabled.

`-p /dev/...` pins a specific device path. Do not use it with the service: after
a USB reset the path can change, and a pinned path will not reconnect.

The LCD is only written when the displayed value changes, plus a keepalive every
10 seconds (or once per poll period if `--rate` is slower than 10 seconds), so
idle USB traffic stays low.

> **Note**
> Blanking the LCD is not implemented yet: `off` reports the limitation and exits.

---

# Running as a Service

Install (the installer already does this):

```bash
sudo systemctl enable --now ocypus-lcd.service
```

Status

```bash
systemctl status ocypus-lcd.service
```

Logs

```bash
journalctl -u ocypus-lcd.service -f
```

Settings

The script reads these environment variables (the unit sets `OCYPUS_SENSOR` and
`OCYPUS_RATE` explicitly):

| Variable | Default | Meaning |
|----------|---------|---------|
| `OCYPUS_SENSOR` | `coretemp` | `psutil` sensor group |
| `OCYPUS_RATE` | `1` | sensor poll period, seconds |
| `OCYPUS_REINIT` | `30` | display re-init interval, seconds (`0` disables) |

Override them with a drop-in:

```bash
sudo systemctl edit ocypus-lcd.service

# [Service]
# Environment=OCYPUS_RATE=2
```

Recovery

- The display is re-initialised every 30 seconds, so a firmware blank does not leave
  it dark (unless re-init is disabled with `OCYPUS_REINIT=0` or `--reinit 0`).
- If writing to the HID device fails (USB reset or unplug), the driver reconnects
  in-process (1–30 s backoff), re-initialises the display and resumes updates.
  The systemd unit keeps `Restart=always` as a backstop for unexpected crashes.

---

# Protocol

Communication uses USB HID Feature Reports (65 bytes).

Initialization

```
07 FD 00 00 00 00 ...
```

Temperature update

```
07 FF FF 00 TT UU 00 00 ...
```

Where

| Byte | Meaning |
|------|---------|
| 0 | Report ID (0x07) |
| 1 | Command (0xFF) |
| 2 | Command (0xFF) |
| 3 | Reserved |
| 4 | Tens digit |
| 5 | Ones digit |
| 6 | Reserved |
| 7 | Unit (0=C, 1=F) |

---

# Troubleshooting

### No device found

Check

```bash
lsusb -d 1a2c:434d
```

---

### Permission denied

Verify the udev rule is installed and reload it:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

The device belongs to the `ocypus` group. If you use the CLI, make sure your
user is in that group and log out and back in (or run `newgrp ocypus`):

```bash
id -nG
sudo usermod -aG ocypus "$USER"
```

---

### Module 'hid' has no attribute 'device'

You installed the wrong package. Re-run the installer, or use the installer's
virtualenv if you installed manually:

```bash
sudo /opt/ocypus-a40-lcd/.venv/bin/pip uninstall -y hid hidapi
sudo /opt/ocypus-a40-lcd/.venv/bin/pip install hidapi
```

For a manual `.venv`, use `.venv/bin/pip` instead.

---

### Wrong temperature

Verify the selected sensor:

```bash
ocypus-control sensors
```

If the CLI is not available yet, use the installer's virtualenv directly:

```bash
sudo /opt/ocypus-a40-lcd/.venv/bin/python /opt/ocypus-a40-lcd/ocypus-control.py sensors
```

---

### After suspend the LCD is blank

The service re-initialises the display every 30 seconds and reconnects if the
HID handle is dead, so it normally recovers on its own. If it does not:

```bash
journalctl -u ocypus-lcd.service -n 50 --no-pager
sudo systemctl restart ocypus-lcd.service
```

---

### The display stays blank

Check the journal:

```bash
journalctl -u ocypus-lcd.service -n 50 --no-pager
```

- `Send failed` — the HID handle is dead; the driver reconnects and re-initialises
  the display automatically.
- `Sensor '...' not found` — wrong sensor name; list them with `ocypus-control sensors`.
- No errors at all — the firmware blanked the display; it is re-initialised every
  30 seconds (`--reinit`). If you set `--reinit 0`, this recovery is disabled.

---

# Acknowledgements

This project builds upon previous community work on reverse engineering Ocypus digital coolers.

Special thanks to:

- **moyunkz** — https://github.com/moyunkz/ocypus-a40-digital-linux
- **Muyoouu** — https://github.com/Muyoouu/ocypus-a62-digital-linux
- **wildanadt** — https://github.com/wildanadt/ocypus-a40-digital-linux
- **Failton** — https://github.com/Failton/ocypus-iota-l36-digital-linux

Their research, protocol analysis and Linux implementations made this project possible.

---

# License

MIT

See the **LICENSE** file.
