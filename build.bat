@echo off
setlocal

echo.
echo  =============================================
echo   FritzBox Viewer -- Build EXE
echo  =============================================
echo.

:: Check virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo  [FEHLER] Virtuelle Umgebung nicht gefunden.
    echo  Bitte zuerst: python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

:: Install PyInstaller if not already present
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo  PyInstaller wird installiert...
    pip install pyinstaller
)

:: Clean previous build
echo  Bereinige vorherige Builds...
if exist "build" rmdir /s /q build
if exist "dist\FritzBox-Viewer" rmdir /s /q "dist\FritzBox-Viewer"

:: Build
echo  Starte Build...
echo.
pyinstaller fritzbox_viewer.spec

if errorlevel 1 (
    echo.
    echo  [FEHLER] Build fehlgeschlagen. Siehe Ausgabe oben.
    pause
    exit /b 1
)

echo.
echo  =============================================
echo   Build erfolgreich!
echo.
echo   Ausgabe: dist\FritzBox-Viewer\
echo.
echo   Zum Starten: dist\FritzBox-Viewer\FritzBox-Viewer.exe
echo  =============================================
echo.

pause
