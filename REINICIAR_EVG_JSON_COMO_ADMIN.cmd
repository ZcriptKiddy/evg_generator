@echo off
setlocal
fltmc >nul 2>&1
if errorlevel 1 (
  echo Solicitando permisos de administrador...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

title Reiniciar EVG_JSON puerto 8000
echo Reiniciando EVG_JSON...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Restart-EVG-JSON-8000.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: No se pudo confirmar el reinicio. Revisa logs\app.stderr.log
  pause
  exit /b 1
)

echo.
echo LISTO: el backend nuevo esta activo.
echo Ya puedes recargar la pagina con Ctrl+F5.
pause
