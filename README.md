# Generador DOCX pericial

Aplicacion web local para Windows que genera documentos Word a partir de plantillas `.docx`.

El sistema trabaja con dos flujos principales:

- **Cadena de Custodia**: genera documentos de cadena usando solo campos de texto `{{Txt_...}}`. No usa imagenes ni ZIP.
- **Informe Pericial**: genera informes usando campos de texto `{{Txt_...}}` e imagenes `{{Img_...}}` tomadas de un archivo ZIP.

La aplicacion corre localmente con FastAPI en:

```text
http://127.0.0.1:8000
```

## Funciones principales

- Usa plantillas Word `.docx` ubicadas en `templates/`.
- Carga por default `Plantilla_Cadena.docx` y `Plantilla_Informe.docx`.
- Permite subir otra plantilla `.docx` desde la interfaz.
- Detecta automaticamente placeholders `{{Txt_...}}` y `{{Img_...}}`.
- Construye formularios dinamicos desde los campos detectados.
- Permite textos normales, textos enriquecidos, fechas, horas y horarios libres.
- Mantiene un JSON interno sincronizado en segundo plano.
- Permite ver, copiar, descargar, cargar y editar el JSON desde un modal avanzado.
- Genera documentos incompletos como `parcial_<hash>.docx`.
- Genera documentos completos como `completo_<hash>.docx`.
- Guarda historial local de documentos generados.

## Plantillas incluidas

```text
templates/Plantilla_Cadena.docx
templates/Plantilla_Informe.docx
```

Ejemplos de placeholders:

```text
{{Txt_No_Carpeta}}
{{Txt_Fecha_Actual}}
{{Txt_Hora_Inicial}}
{{Img_Arribo_Domicilio}}
```

Los placeholders pueden estar en parrafos, tablas, encabezados y pies de pagina.

## Requisitos

- Windows 10 o superior.
- Python 3.11 o superior.
- Git.
- Internet solo para instalar dependencias.

Al instalar Python, marca la opcion **Add Python to PATH**.

## Instalacion rapida en Windows

```bat
install.bat
```

## Ejecucion rapida

```bat
run.bat
```

Luego abre:

```text
http://127.0.0.1:8000
```

## Configuracion

1. Copia `.env.example` como `.env`.
2. Edita las variables de usuario, correo y seguridad.
3. Genera una contrasena con:

```bat
.venv\Scripts\python.exe scripts\set_password.py
```

No subas `.env` a GitHub.

## Uso basico

1. Entra con el usuario y contrasena configurados.
2. Usa primero la pestana **Cadena de Custodia**.
3. Usa despues **Informe Pericial**.
4. En Cadena de Custodia no se usa ZIP ni imagenes.
5. En Informe Pericial puedes subir ZIP con imagenes.
6. Revisa o edita los datos desde **JSON / Datos avanzados** si hace falta.
7. Genera el Word.

## Archivos importantes

```text
app/                 Backend FastAPI
static/              Interfaz web
templates/           Plantillas DOCX
scripts/             Utilidades locales
requirements.txt     Dependencias Python
install.bat          Instalador para Windows
run.bat              Arranque local para Windows
instructions.txt     Guia paso a paso
```

## Seguridad

- No subas `.env`.
- No subas `.venv`.
- No subas historial, temporales ni documentos generados.
- El sistema esta pensado para ejecutarse localmente en Windows.
