#!/bin/bash

# Install system dependencies
apt-get update
apt-get install -y build-essential cmake libboost-dev libboost-system-dev libboost-filesystem-dev libboost-thread-dev libssl-dev pkg-config

# Try to install libtorrent
pip install --upgrade pip
pip install libtorrent || pip install python-libtorrent || echo "libtorrent installation failed, continuing without it"

# Install other requirements
pip install -r requirements.txt
