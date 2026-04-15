@echo off
:: start_frontend.bat
:: Streamlit frontend'i .venv ile başlatır.

echo [F1 Strategy Wall] Frontend baslatiliyor...
echo Dashboard: http://localhost:8501
echo.

cd /d "%~dp0"
.venv\Scripts\streamlit.exe run frontend/app.py --server.port 8501 --server.headless false
pause
