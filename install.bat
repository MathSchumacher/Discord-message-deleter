@echo off
chcp 65001 >nul
title Discord Message Deleter - Instalação de Dependências
cd /d "%~dp0"
echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║ 🚀 Instalador - Discord Message Deleter                   ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python não encontrado. Instale o Python 3.10+ e tente novamente.
    pause
    exit /b 1
)
echo ✓ Python detectado.

REM Atualiza pip
echo.
echo 🔄 Atualizando pip...
python -m pip install --upgrade pip

REM Instala dependências
echo.
echo 📦 Instalando dependências do requirements.txt...
pip install -r requirements.txt

if errorlevel 1 (
    echo ❌ Ocorreu um erro ao instalar dependências.
    pause
    exit /b 1
)
echo.
echo ✅ Todas as dependências foram instaladas com sucesso!

pause
exit /b 0
