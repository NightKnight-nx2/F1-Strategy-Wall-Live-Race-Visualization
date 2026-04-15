@echo off
:: train_models.bat
:: ML modellerini .venv ile eğitir.
:: İlk kurulumda veya veri güncellemesinden sonra çalıştırın.

echo [F1 Strategy Wall] Model egitimi baslatiliyor...
echo NOT: FastF1 verisi indiriliyor olabilir, lutfen bekleyin.
echo.

cd /d "%~dp0"
.venv\Scripts\python.exe -m backend.models.trainer
pause
