@echo off
rem Installe Carto pour l'utilisateur courant, sans droits administrateur.
title Installation de Carto
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1"
if errorlevel 1 (
    echo.
    echo L'installation a echoue.
    pause
)
