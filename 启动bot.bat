@echo off
rem py-clash-bot launcher: adds MuMu adb to PATH, then starts the bot GUI
rem Usage: start normally by double-clicking, or pass --start to auto-start the bot
set "PATH=D:\Program Files\Netease\MuMu Player 12\shell;%PATH%"
cd /d "%~dp0py-clash-bot"
".venv\Scripts\python.exe" -m pyclashbot %*
pause
