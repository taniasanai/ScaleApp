@echo off
rem Builds dist\ScaleApp\, the folder to copy to the business PC:
rem   ScaleApp.exe         the window, for everyday use
rem   ScaleAppConsole.exe  console version; also finds the scales (ScaleAppConsole.exe --scan)
rem   config.json          settings, edited on-site
cd /d "%~dp0"

rem openpyxl uses these only if installed; the app doesn't need them.
set EXCLUDE=--exclude-module numpy --exclude-module PIL --exclude-module pandas
rem Temporary build files go outside the project: OneDrive locks files while syncing them.
set WORK=--workpath "%TEMP%\ScaleApp-build" --specpath "%TEMP%\ScaleApp-build"

python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ScaleApp %EXCLUDE% %WORK% ^
    --distpath dist\ScaleApp scaleApp.py || exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --console --name ScaleAppConsole %EXCLUDE% %WORK% ^
    --distpath dist\ScaleApp scaleServer.py || exit /b 1

rem Never overwrite a config.json that has already been set up for the real scales.
if not exist dist\ScaleApp\config.json copy config.json dist\ScaleApp\ >nul
echo.
echo Built dist\ScaleApp\
