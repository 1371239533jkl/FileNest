@echo off
rem 冻结 Python sidecar（onedir），产物：desktop\packaging\dist\filenest-service\
for %%i in ("%~dp0..\..") do set ROOT=%%~fi
cd /d "%ROOT%"
"%ROOT%\.venv\Scripts\pyinstaller.exe" --noconfirm --onedir --name filenest-service ^
  --distpath "%ROOT%\desktop\packaging\dist" --workpath "%ROOT%\desktop\packaging\build" ^
  --specpath "%ROOT%\desktop\packaging" --collect-submodules uvicorn ^
  --exclude-module PyQt6 --add-data "%ROOT%\webapp;webapp" "%ROOT%\server.py"
