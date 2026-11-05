@echo off
setlocal EnableExtensions

REM Launcher of Fennec Images. The thing to double-click is "Fennec Images.lnk" on the
REM desktop -- the green F -- which goes through the run_gui.vbs beside this file so no
REM console box appears. This file run on its own in a console works too, and prints there.

REM Always run from the repo root -- two folders up, this .bat living beside its run.py
cd /d "%~dp0..\.." || exit /b 1

REM Refresh the desktop shortcut (a .bat cannot carry an icon, a .lnk can).
REM Never let it stop the launch: the GUI runs whether or not the icon updated.
if exist "%CD%\scripts\make_shortcuts.vbs" (
  cscript //nologo //B "%CD%\scripts\make_shortcuts.vbs" >nul 2>&1
)

REM The repo's own venv when there is one, else the Python launcher
set "PY=%CD%\.venv\Scripts\python.exe"
if exist "%PY%" (
  "%PY%" fennec_images\gui\run.py
) else (
  py -3 fennec_images\gui\run.py
)
