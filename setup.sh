#!/bin/sh
# Name: setup.sh
# Quick Desc: This script creates a virtual environment folder and installs dependencies
# Author: w1l238
# Project Link: https://github.com/w1l238/CLI-Spotify-Downloader
# Note: Run this at the root folder of the project! (i.e. in the folder 'CLI-Spotify-Downloader')


# Create a virtual environment folder named "venv" if not exists
if [ ! -d "venv" ]; then
  python3 -m venv venv
  echo "[venv] Virtual environment created."
else
  echo "[venv] Virtual environment already exists."
fi

# Activate the virtual environment and install packages
. venv/bin/activate

# Install the required packages
echo "[pip] Upgrading pip..."
pip install --upgrade pip
echo "[requirements] Installing CLI requirements... "
pip install -r requirements.txt # Install CLI requirements


# Download ffmpeg using spotdl
spotdl --download-ffmpeg

# TODO:
# - Move ffmpeg to the venv bin (scripts for windows). 
#   Since spotdl puts ffmpeg to user's default path. 

# Echo statements during process
# echo "Finding ffmpeg in default path..."
# echo "Moving ffmpeg from default path to virtual environment..."

# Echo that packages are installed
echo "Packages installed inside the virtual environment."
