#!/bin/bash

# Update and install system dependencies if needed
if command -v apt-get &> /dev/null; then
    apt-get update
    apt-get install -y build-essential cmake libboost-dev libboost-system-dev libboost-filesystem-dev libboost-thread-dev libssl-dev pkg-config || echo "System packages installation failed, continuing..."
fi

# Upgrade pip
pip install --upgrade pip

# Install core requirements first
echo "Installing core requirements..."
pip install -r requirements.txt

# Try to install optional dependencies (libtorrent)
echo "Attempting to install optional dependencies..."
pip install libtorrent==2.0.11 || \
pip install python-libtorrent==2.0.9 || \
pip install python-libtorrent || \
pip install libtorrent || \
echo "Warning: Could not install libtorrent. Torrent downloads will be disabled."

echo "Build completed successfully!"
