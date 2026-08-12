@echo off
rem Retire Carto, en laissant les traces de l'utilisateur intactes.
title Desinstallation de Carto
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1" -Desinstaller
pause
