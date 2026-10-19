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
- installs Python dependencies
- installs udev rules (including disabling USB autosuspend for the cooler)
- installs the `ocypus-control` command into `/usr/local/bin`
- installs the systemd service
- enables automatic startup

Re-run `sudo ./install.sh` to update an existing installation: it copies the new
files and restarts the service.

---

## Manual

```bash
pip install hidapi psutil

sudo cp ocypus-control.py /usr/local/bin/
sudo chmod +x /usr/local/bin/ocypus-control.py

sudo groupadd --system ocypus
sudo useradd --system --gid ocypus --no-create-home --shell /usr/sbin/nologin ocypus

sudo cp udev/99-ocypus-a40.rules /etc/udev/rules.d/

sudo udevadm control --reload-rules
sudo udevadm trigger
```

> **Note**
> The bundled systemd unit expects the script in `/opt/ocypus-a40-lcd` with a
> virtualenv (`/opt/ocypus-a40-lcd/.venv/bin/python`). Use `install.sh` for the
> service, or adjust `ExecStart` in `systemd/ocypus-lcd.service` to your paths.

---

# Usage

After `install.sh` the CLI is available as `ocypus-control` (a launcher that uses
the virtualenv).

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

Fahrenheit

```bash
ocypus-control on -u f
```

Refresh every 2 seconds

```bash
ocypus-control on -r 2
```

Re-initialise the display every 15 seconds (default: 30, `0` disables)

```bash
ocypus-control on --reinit 15
```

The LCD is only written when the displayed value changes, plus a keepalive every
10 seconds, so idle USB traffic stays low.

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
  it dark.
- If writing to the HID device fails (USB reset or unplug), the process exits and
  systemd restarts it (`Restart=always`, `RestartSec=5`).

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

---

### Module 'hid' has no attribute 'device'

You installed the wrong package.

```bash
pip uninstall hid

pip install hidapi
```

---

### Wrong temperature

Verify the selected sensor

```bash
python3 -c "import psutil; print(psutil.sensors_temperatures())"
```

---

### After suspend the LCD is blank

The service re-initialises the display every 30 seconds and restarts itself if the
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

- `Send failed` — the HID handle is dead; the service restarts itself.
- `Sensor '...' not found` — wrong sensor name; list them with `ocypus-control sensors`.
- No errors at all — the firmware blanked the display; it is re-initialised every
  30 seconds (`--reinit`).

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
