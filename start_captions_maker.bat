@echo off
rem Prefer Hermes venv python, fallback to python on PATH.
set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if exist "%PY%" goto run
set "PY=python"
:run
wscript.exe "%~dp0start_captions_maker.vbs"
exit /b 0
