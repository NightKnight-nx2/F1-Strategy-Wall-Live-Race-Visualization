@echo off
:: start_backend.bat
:: FastAPI backend'i .venv ile başlatır.

echo [F1 Strategy Wall] Backend baslatiliyor...
echo API:  http://localhost:8000
echo Docs: http://localhost:8000/docs
echo.

cd /d "%~dp0"
.venv\Scripts\uvicorn.exe backend.main:app --reload --host 0.0.0.0 --port 8000
pause
