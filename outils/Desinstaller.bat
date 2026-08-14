@echo off
rem Retire GeoCairn, en laissant les traces de l'utilisateur intactes.
title Desinstallation de GeoCairn
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1" -Desinstaller
pause
