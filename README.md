# EVG_JSON

Aplicación web local para generar archivos JSON de entrada, informes periciales, cadenas de custodia y aportaciones a partir de plantillas DOCX.

Usa FastAPI y PaddleOCR. El servidor escucha únicamente en `127.0.0.1`.

## Requisitos

- Windows 10 u 11 de 64 bits.
- Python 3.13 de 64 bits.
- Conexión a Internet durante la instalación y la primera ejecución de OCR; PaddleOCR descarga sus modelos en `data/models/`, que se excluye del repositorio.

## Preparación inicial

Abre PowerShell en la carpeta del proyecto y ejecuta:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` para definir `APP_USER` y `APP_EMAIL`. Genera una clave de sesión y pega el resultado en `SESSION_SECRET`:

```powershell
.\.venv\Scripts\python.exe -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Genera el hash de contraseña con el asistente incluido. Pide una contraseña de al menos 16 caracteres y su confirmación; el script actualiza `.env`:

```powershell
.\.venv\Scripts\python.exe scripts\set_password.py
```

No subas `.env` ni `credenciales.txt` a GitHub. El `.gitignore` también excluye historiales y archivos de trabajo, respaldos, registros, modelos descargados y resultados locales.

## Arranque

```powershell
.\run.bat
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000).

También puedes arrancar directamente:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Estructura

- `app/`: aplicación FastAPI, autenticación y motores DOCX/OCR.
- `templates/informe/`, `templates/cadena/` y `templates/aportacion/`: plantillas usadas por la aplicación.
- `static/`: interfaz web.
- `scripts/`: utilidades de arranque y mantenimiento.
- `data/`: datos locales, historial, archivos de trabajo y modelos OCR descargados; no se versiona.
- `backups/`: copias anteriores; no se versiona.

Las plantillas usadas actualmente son `Plantilla_Informe.docx`, `Plantilla_Cadena.docx` y `Plantilla_Aportación.docx` dentro de sus respectivas carpetas. Las versiones anteriores se guardan en `backups/plantillas_descartadas/`.
