@echo off
REM --- Compile installer — version agnostic ---
cd /d "%~dp0"
set VERSION=2.1.5

REM Find built exe (supports both onedir and onefile)
set FOUND=
if exist "dist\HDM-%VERSION%\HDM-%VERSION%.exe" set FOUND=dist\HDM-%VERSION%\HDM-%VERSION%.exe
if exist "dist\HDM-%VERSION%.exe" set FOUND=dist\HDM-%VERSION%.exe
REM fallback: any HDM-*.exe in dist
if not defined FOUND (
  for /d %%D in (dist\HDM-*) do (
    if exist "%%D\HDM-*.exe" set FOUND=%%D\HDM-*.exe
  )
)
if not defined FOUND (
  if exist "dist\HDM-*.exe" set FOUND=dist\HDM-*.exe
)

if not defined FOUND (
  echo.
  echo  ERROR: built EXE not found in dist\
  echo  Expected: dist\HDM-%VERSION%\HDM-%VERSION%.exe
  echo  Run build_windows.bat first.
  echo.
  pause
  exit /b 1
)

echo Found: %FOUND%

set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 5\ISCC.exe"

if not defined ISCC (
  echo.
  echo  Inno Setup not found. Download: https://jrsoftware.org/isdl.php
  echo  Then run this file again.
  echo.
  pause
  exit /b 1
)

echo Compiling installer with: %ISCC%
"%ISCC%" hdm_setup.iss
if errorlevel 1 goto :err

echo.
echo BUILD OK -> installer\HDM-%VERSION%-Setup.exe
dir installer\HDM-%VERSION%-Setup.exe 2>nul
dir installer\*.exe 2>nul
goto :end

:err
echo.
echo COMPILE FAILED

:end
pause
