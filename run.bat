@echo off
chcp 65001 >nul
title Discord Message Deleter - Servidor Ativo

cd /d "%~dp0"

python -m streamlit --version >nul 2>&1
if errorlevel 1 (
echo Streamlit ou Python não encontrado. Rode install.bat primeiro.
pause
exit /b 1
)

timeout /t 5 /nobreak >nul
start "" "http://localhost:8501"

python -m streamlit run app.py --server.port=8501 --server.headless=true

pause