@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No existe .venv.
    echo Ejecuta install.bat antes de iniciar la aplicacion.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto error

echo.
echo Generador DOCX pericial
echo Abre en el navegador:
echo http://127.0.0.1:8000
echo.

uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
if errorlevel 1 goto error
exit /b 0

:error
echo.
echo Ocurrio un error al ejecutar la aplicacion.
pause
exit /b 1
