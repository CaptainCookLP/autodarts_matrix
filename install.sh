#!/bin/bash
set -e

# Install required packages
sudo apt-get update
sudo apt-get install -y git python3-dev python3-pip python3-venv python3-pillow

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
