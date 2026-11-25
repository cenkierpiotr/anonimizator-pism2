@echo off
rem Lokalizacja instalacji aplikacji (ustawiana przez instalator; fallback gdy uruchomiono skrypt z poziomu drzewa repo).
set "APPDIR=%LOCALAPPDATA%\Programy\Anonimizator Pism"
if not exist "%APPDIR%\app\server.py" set "APPDIR=%~dp0"
if not exist "%APPDIR%\.venv\Scripts\pythonw.exe" set "APPDIR=%~dp0"

rem Usu polskie znaki z echo (plik batch ma byc kompatybilny z strona kodowa CP852).
cd /d "%APPDIR%"
start "" /B ".venv\Scripts\pythonw.exe" "app\server.py" --port 4578
