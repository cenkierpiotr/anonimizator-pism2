@echo off
rem Uruchamia daemon anonimizacji (port 4578) z konsola widoczna (do diagnozy problemow).
rem Szuka instalacji aplikacji w standardowej lokalizacji, a gdy jej nie znajdzie
rem - uruchamia serwer z drzewa repo, z ktorego skrypt zostal wywolany.
set "APPDIR=%LOCALAPPDATA%\Programy\Anonimizator Pism"
if not exist "%APPDIR%\app\server.py" set "APPDIR=%~dp0"
if not exist "%APPDIR%\.venv\Scripts\python.exe" set "APPDIR=%~dp0"

cd /d "%APPDIR%"
".venv\Scripts\python.exe" "app\server.py" --port 4578 >> daemon.log 2>&1
