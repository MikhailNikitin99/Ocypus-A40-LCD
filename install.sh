#!/bin/bash
set -euo pipefail

INSTALL_DIR="/opt/ocypus-a40-lcd"
SERVICE_NAME="ocypus-lcd"

# sys requirements
install_system_deps() {
    echo "Installing required system packages (build tools, libusb, Python headers)..."
    if command -v apt-get &>/dev/null; then
        apt-get update
        apt-get install -y --no-install-recommends \
            build-essential pkg-config libusb-1.0-0-dev python3-dev python3-venv
    elif command -v dnf &>/dev/null; then
        dnf install -y make gcc pkgconf libusb1-devel python3-devel
    elif command -v zypper &>/dev/null; then
        zypper install -y make gcc pkg-config libusb-1_0-devel python3-devel
    elif command -v pacman &>/dev/null; then
        pacman -S --needed --noconfirm base-devel libusb python
    elif command -v apk &>/dev/null; then
        apk add --no-cache build-base pkgconfig libusb-dev python3-dev
    else
        echo "ERROR: Could not detect package manager."
        echo "Please install the following packages manually:"
        echo "  - C compiler (gcc or clang)"
        echo "  - pkg-config"
        echo "  - libusb development files (libusb-1.0-0-dev or libusb1-devel)"
        echo "  - Python 3 development headers (python3-dev or python3-devel)"
        exit 1
    fi
}

# create a user
echo "Creating group and user 'ocypus'..."
getent group ocypus >/dev/null || groupadd --system ocypus
id ocypus &>/dev/null || useradd --system --gid ocypus --no-create-home --shell /usr/sbin/nologin ocypus

echo "Installing files to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp ocypus-control.py "$INSTALL_DIR/"
cp requirements.txt "$INSTALL_DIR/"
cp systemd/ocypus-lcd.service /etc/systemd/system/
cp udev/99-ocypus-a40.rules /etc/udev/rules.d/

# sys deps
install_system_deps

# Python venv + dependencies
echo "Setting up Python virtual environment..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

"$INSTALL_DIR/.venv/bin/pip" uninstall -y hid 2>/dev/null || true

# --- Udev и systemd ---
echo "Reloading udev rules..."
udevadm control --reload-rules
# Re-run the "add" rules for this device only: the autosuspend rule matches ACTION=="add"
udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor=1a2c --attr-match=idProduct=434d
udevadm trigger --subsystem-match=hidraw

echo "Enabling and restarting systemd service..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
# restart, not "enable --now": an already running service must pick up the new files
systemctl restart "$SERVICE_NAME"
echo "Done. Check status with: systemctl status $SERVICE_NAME"
