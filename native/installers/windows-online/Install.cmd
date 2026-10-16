@echo off
if not exist "%~dp0Install Flapart.exe" (
  echo This source candidate has not been compiled into a release installer yet.
  echo Download the qualified Windows installer from https://flaptown.com/flapsoft/
  pause
  exit /b 1
)
start "" "%~dp0Install Flapart.exe"
