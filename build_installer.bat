@echo off
REM --- Only compile the installer (run after build_windows.bat) ---
cd /d "%~dp0"

if not exist "dist\HDM-1.0.1\HDM-1.0.1.exe" (
  echo.
  echo  ERROR: dist\HDM-1.0.1\HDM-1.0.1.exe not found.
  echo  Run build_windows.bat first.
  echo.
  pause
  exit /b 1
)

set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 5\ISCC.exe"

if not defined ISCC (
  echo.
  echo  Inno Setup not found.
  echo  Download and install: https://jrsoftware.org/isdl.php
  echo  Then run this file again.
  echo.
  pause
  exit /b 1
)

echo Compiling installer with: %ISCC%
"%ISCC%" hdm_setup.iss
if errorlevel 1 goto :err

echo.
echo BUILD OK -> installer\HDM-1.0.1-Setup.exe
dir installer\HDM-1.0.1-Setup.exe
goto :end

:err
echo.
echo COMPILE FAILED - copy the text above and send it.

:end
pause
