@echo off
REM ==========================================================================
REM  TikTok Live Finder - ONLINE (phone) launcher
REM  Double-click this on a Windows PC/RDP. It:
REM    1. installs the Python packages,
REM    2. downloads cloudflared (a free tunnel) if needed,
REM    3. starts the dashboard,
REM    4. prints a public https link you open on your PHONE.
REM  Keep this window open while you use the dashboard.
REM ==========================================================================
setlocal
cd /d "%~dp0"

echo ==========================================================
echo   TikTok Live Finder - putting your dashboard online
echo ==========================================================
echo.

REM --- 1. Python packages ------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python is not installed. Get it from https://www.python.org/downloads/
  echo     During install, TICK "Add python.exe to PATH", then run this again.
  pause
  exit /b 1
)
echo Installing Python packages (first run only, ~1 min)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM --- 2. cloudflared tunnel --------------------------------------------
if not exist cloudflared.exe (
  echo Downloading the tunnel tool (cloudflared)...
  powershell -Command "try { Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe' } catch { exit 1 }"
  if not exist cloudflared.exe (
    echo [!] Could not download cloudflared. Check the RDP's internet and retry.
    pause
    exit /b 1
  )
)

REM --- 3. start the dashboard (own window, minimized) -------------------
echo Starting the dashboard...
start "TikTok Dashboard" /min python dashboard.py
timeout /t 6 /nobreak >nul

REM --- 4. open the public tunnel ---------------------------------------
echo.
echo ==========================================================
echo   YOUR PHONE LINK is printed below in a moment.
echo   Look for a line like:  https://something.trycloudflare.com
echo   Open THAT on your phone. Keep this window open.
echo ==========================================================
echo.
cloudflared.exe tunnel --url http://localhost:8321
