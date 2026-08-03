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
- installs udev rules
- installs the systemd service
- enables automatic startup

---

## Manual

```bash
pip install hidapi psutil

sudo cp ocypus-control.py /usr/local/bin/
sudo chmod +x /usr/local/bin/ocypus-control.py

sudo useradd --system --no-create-home --shell /usr/sbin/nologin ocypus

sudo cp udev/99-ocypus-a40.rules /etc/udev/rules.d/

sudo udevadm control --reload
sudo udevadm trigger
```

---

# Usage

Show available sensors

```bash
ocypus-control.py sensors
```

Automatic sensor detection

```bash
ocypus-control.py on
```

Specific sensor

```bash
ocypus-control.py on -s coretemp
```

Fahrenheit

```bash
ocypus-control.py on -u f
```

Refresh every 2 seconds

```bash
ocypus-control.py on -r 2
```

Turn LCD off

```bash
ocypus-control.py off
```

---

# Running as a Service

Install:

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

Verify the udev rule is installed and reload it.

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

Restart

```bash
sudo systemctl restart ocypus-lcd.service
```

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
