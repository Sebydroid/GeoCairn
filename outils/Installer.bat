@echo off
rem Installe GeoCairn pour l'utilisateur courant, sans droits administrateur.
title Installation de GeoCairn
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1"
if errorlevel 1 (
    echo.
    echo L'installation a echoue.
    pause
)
