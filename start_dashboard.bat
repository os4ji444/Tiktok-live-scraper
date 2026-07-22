@echo off
rem Starts the TikTok Live Finder dashboard hidden in the background.
rem Open http://localhost:8321 on this PC, or http://<pc-ip>:8321 on your phone.
cd /d "%~dp0"
start "" pythonw dashboard.py
echo Dashboard started in the background on port 8321.
timeout /t 3 >nul
