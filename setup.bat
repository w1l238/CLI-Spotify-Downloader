@echo off
REM Name: setup.bat
REM Quick Desc: This script creates a virtual environment folder and installs dependencies for Windows.
REM Author: w1l238
REM Project Link: https://github.com/w1l238/CLI-Spotify-Downloader
REM Note: Run this at the root folder of the project! (i.e. in the folder 'CLI-Spotify-Downloader')


REM Check for python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH. Please install Python and try again.
    pause
    exit /b 1
)

REM Create a virtual environment folder named "venv" if not exists
if not exist "venv" (
  echo [venv] Creating virtual environment...
  python -m venv venv
  echo [venv] Virtual environment created.
) else (
  echo [venv] Virtual environment already exists.
)

REM Activate the virtual environment and install packages
call "venv\Scripts\activate.bat"

REM Install Default CLI requirements
echo [pip] Upgrading pip...
python -m pip install --upgrade pip
echo [requirements] Installing CLI requirements...
pip install -r requirements.txt


REM Download ffmpeg using spotdl
echo [ffmpeg] Downloading ffmpeg...
spotdl --download-ffmpeg

echo [ffmpeg] Moving ffmpeg from default path to virtual environment...
move /Y "%USERPROFILE%\.spotdl\ffmpeg.exe" "venv\Scripts\"

echo.
echo Setup complete. Packages installed inside the virtual environment.
echo To activate the environment, run: venv\Scripts\activate.bat
pause
