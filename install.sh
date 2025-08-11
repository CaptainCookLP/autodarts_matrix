#!/bin/bash
set -e

# Install required packages
sudo apt-get update
sudo apt-get install -y git python3-dev python3-pip python3-venv python3-pillow

REPO_DIR="/home/pi/autodarts_matrix"
REPO_URL="https://github.com/<your-username>/autodarts_matrix.git"

# Clone or update this repository
if [ ! -d "$REPO_DIR" ]; then
  git clone "$REPO_URL" "$REPO_DIR"
else
  git -C "$REPO_DIR" pull
fi

cd "$REPO_DIR"

# Clone or update rpi-rgb-led-matrix
if [ ! -d rpi-rgb-led-matrix ]; then
  git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
else
  (cd rpi-rgb-led-matrix && git pull)
fi

# Build and install Python bindings
(cd rpi-rgb-led-matrix/bindings/python && make build-python && sudo make install-python)

# Install Python dependencies
pip install -r requirements.txt

# Install systemd service
sudo cp autodarts_matrix.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable autodarts_matrix.service
sudo systemctl restart autodarts_matrix.service
