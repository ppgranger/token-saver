@echo off
:: Token-Saver CLI wrapper for Windows
set "SCRIPT_DIR=%~dp0"
set "REPO_DIR=%SCRIPT_DIR%.."
python "%REPO_DIR%\bin\token-saver" %*
