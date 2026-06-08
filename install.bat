@echo off
setlocal
cd /d "%~dp0"

echo Instalando Generador DOCX pericial...
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual .venv...
    python -m venv .venv
    if errorlevel 1 goto error
) else (
    echo Entorno virtual .venv ya existe.
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto error

echo Actualizando pip...
python -m pip install --upgrade pip
if errorlevel 1 goto error

echo Instalando dependencias...
pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo Instalacion completada.
echo Si aun no existe .env, copia .env.example como .env y configura tus variables.
pause
exit /b 0

:error
echo.
echo Ocurrio un error durante la instalacion.
pause
exit /b 1
