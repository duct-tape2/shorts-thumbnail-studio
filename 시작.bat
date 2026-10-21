@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0ThumbnailStudio.exe" (
  echo Extract the whole ZIP first, then run this file again.
  pause
  exit /b 1
)
start "" "%~dp0ThumbnailStudio.exe" %*
