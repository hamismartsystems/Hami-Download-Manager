@echo off
REM ============================================================
REM  HAMI Download Manager (HDM) 2.1.5 — build app + installer
REM  Needs: Python 3.10+ (Add to PATH) + Inno Setup 6 (optional)
REM  Output: dist\HDM-2.1.5\HDM-2.1.5.exe  + installer\HDM-2.1.5-Setup.exe
REM ============================================================
cd /d "%~dp0"
set VERSION=2.1.5

echo [1/3] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
  echo  ERROR: Python not found in PATH. Install Python 3.10+ and add to PATH.
  pause
  exit /b 1
)

echo [1/3] Installing deps...
python -m pip install --upgrade pyinstaller pillow PyQt6 requests >nul 2>&1

echo.
echo [2/3] Building HDM %VERSION%...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

REM try main spec
pyinstaller hdm.spec --noconfirm --clean
if exist "dist\HDM-%VERSION%\HDM-%VERSION%.exe" goto ok
if exist "dist\HDM-%VERSION%.exe" goto ok

echo  Main spec failed, trying simple spec...
pyinstaller hdm_simple.spec --noconfirm --clean
if exist "dist\HDM-%VERSION%\HDM-%VERSION%.exe" goto ok
if exist "dist\HDM-%VERSION%.exe" goto ok

echo  BUILD FAILED at line check - dist not found
echo  Check hdm.spec, version_info.txt, and that PyQt6 is installed
pause
exit /b 1

:ok
echo       dist\HDM-%VERSION%\HDM-%VERSION%.exe  OK
if exist "dist\HDM-%VERSION%.exe" echo       dist\HDM-%VERSION%.exe single file OK

echo.
echo [3/3] Building installer (if Inno installed)...
if exist build_installer.bat call build_installer.bat

echo.
echo  DONE! EXE is in dist folder.
pause
