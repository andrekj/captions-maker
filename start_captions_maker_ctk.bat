@echo off
rem Prefer Hermes venv python, fallback to python on PATH.
set "APP_DIR=%~dp0"
set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if exist "%PY%" goto run
set "PY=python"
:run
cd /d "%APP_DIR%"
"%PY%" "%APP_DIR%captions_maker_ctk.py"
