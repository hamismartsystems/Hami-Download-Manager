@echo off
REM ============================================================
REM  HAMI Download Manager (HDM) 1.0.1 — build app + installer
REM  Needs: Python 3.11/3.12 (Add to PATH) + Inno Setup 6
REM  Output: installer\HDM-1.0.1-Setup.exe
REM ============================================================
cd /d "%~dp0"

echo [1/3] Installing PyInstaller...
python -m pip install --upgrade pyinstaller pillow PyQt6
if errorlevel 1 (
  echo  pip failed - check your internet connection, then run this file again.
  pause
  exit /b 1
)

echo.
echo [2/3] Building application...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
pyinstaller hdm.spec --noconfirm --clean
if not exist "dist\HDM-1.0.1\HDM-1.0.1.exe" (
  echo  Normal build failed - retrying with the simple spec (no icon)...
  pyinstaller hdm_simple.spec --noconfirm --clean
)
if not exist "dist\HDM-1.0.1\HDM-1.0.1.exe" (
  echo  BUILD FAILED - copy the text above and send it.
  pause
  exit /b 1
)
echo       dist\HDM-1.0.1\HDM-1.0.1.exe  OK

echo.
echo [3/3] Building installer...
call build_installer.bat
