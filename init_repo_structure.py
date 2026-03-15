"""
# =============================================================================
# init_repo_structure.py
# =============================================================================
# Nombre:       Inicializador de estructura de repositorio
# Entorno:      Ejecución local · Google Colab · GitHub Actions
# Versión:      v1.0 — 2026-03-15 — Generado con Claude Sonnet 4.6
# Revisado:     no revisado
# Objetivo:     Genera la estructura de directorios y ficheros base definida
#               en system_prompt_implicito_v3.0 a partir de un nombre de repo
#               hardcodeado. Input: REPO_NOMBRE. Output: árbol de carpetas
#               y ficheros stub listos para usar.
# MODO:         Sin Telegram — script de utilidad puntual
# Dependencias: Sin dependencias externas — stdlib pura
# Configuración:
#   Variable         Tipo   Default              Descripción
#   REPO_NOMBRE      str    'ControlesFinancieros' Nombre del repositorio raíz
#   BASE_DIR         Path   Path.cwd()           Directorio donde crear el repo
#   PROYECTO         str    'monitor'            Nombre del proyecto (prefijo ficheros)
# Rutas:
#   {BASE_DIR}/{REPO_NOMBRE}/   Raíz del repositorio generado
# Salida esperada:
#   [OK] Estructura creada en: /ruta/al/repo
#   [OK] X directorios · Y ficheros generados
# Limitaciones:
#   · No inicializa git — solo crea la estructura de ficheros
#   · No sube a GitHub — requiere git init + push manual
#   · Si el directorio ya existe, no sobreescribe ficheros existentes
# =============================================================================
#
# Cambios:
#   v1.0 — 2026-03-15 — Versión inicial según system_prompt_implicito_v3.0
# =============================================================================
"""

import os
from pathlib import Path
from datetime import datetime, timezone


# =============================================================================
# CONFIGURACIÓN — todas las variables parametrizables aquí, fuera de funciones
# =============================================================================

# DISEÑO INTENCIONADO — nombre del repo hardcodeado.
# Este script es de utilidad puntual — no requiere parametrización externa.
# ESCENARIO B: el repo ya existe y el script se ejecuta desde dentro de él.
# Ejecutar desde la raíz de ControlesFinancieros/ para que la estructura
# se cree en el lugar correcto sin generar una subcarpeta adicional.
REPO_NOMBRE = "ControlesFinancieros"  # solo informativo — para nombres de ficheros y mensajes

# Directorio base = directorio actual (raíz del repo ya clonado)
BASE_DIR    = Path(".")

# El repo raíz ES el directorio actual — no crear subcarpeta adicional
REPO_DIR_OVERRIDE = Path(".")  # usado en crear_estructura() en lugar de base_dir/repo_nombre

# Nombre del proyecto — se usa como prefijo en nombres de ficheros de output
PROYECTO    = "monitor"

# Fecha de creación para los stubs
FECHA_HOY   = datetime.now(timezone.utc).strftime("%Y-%m-%d")


# =============================================================================
# ESTRUCTURA — definición completa según system_prompt_implicito_v3.0
# Formato: lista de rutas relativas al repo raíz
# Las rutas que terminan en / son directorios vacíos (se crea .gitkeep)
# Las demás son ficheros con contenido stub
# =============================================================================

ESTRUCTURA = {

    # ── Workflows GitHub Actions ───────────────────────────────────────────
    ".github/workflows/cron.yml": """\
name: {proyecto} — Ejecución automática

on:
  schedule:
    # Ejecución diaria principal — 07:00 CET (06:00 UTC)
    - cron: '0 6 * * *'
  workflow_dispatch:  # Permite ejecución manual desde GitHub Actions

jobs:
  ejecutar:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repositorio
        uses: actions/checkout@v4

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Instalar dependencias
        run: pip install feedparser requests

      - name: Ejecutar script principal
        run: python scripts/{proyecto}_main.py

      # Commit automático de output/ tras cada ejecución
      # El versionado de resultados lo gestiona Git — no el nombre del fichero
      - name: Commit output
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add output/
          git diff --staged --quiet || git commit -m "auto: output {fecha_hoy} [skip ci]"
          git push
""",

    # ── Mapeos — datos de referencia versionados ───────────────────────────
    # telegram_config.json — única excepción al no-hardcoding
    # El repo es público — decisión consciente asumiendo riesgo aceptable
    "mapeos/telegram_config.json": '{{\n  "_comentario": "Único fichero con datos sensibles permitido según system_prompt_implicito_v3. Repo público — riesgo aceptado conscientemente.",\n  "bot_token":   "REEMPLAZAR_CON_TOKEN_REAL",\n  "chat_id":     "REEMPLAZAR_CON_CHAT_ID_REAL"\n}}',

    # BASE_RAW — URL base del repo para construir URLs de mapeos
    "mapeos/base_raw.json": '{{\n  "_comentario": "URL base raw de GitHub. Todas las URLs de mapeos se construyen a partir de esta.",\n  "base_raw": "https://raw.githubusercontent.com/USUARIO/{repo}/main"\n}}',

    # ── Scripts principales ────────────────────────────────────────────────
    "scripts/{proyecto}_main.py": """\
\"\"\"
# =============================================================================
# {proyecto}_main.py — [Describir qué hace y qué problema resuelve]
# =============================================================================
# Entorno:      Repo GitHub · MODO produccion/auditoria · Python 3.10+ · Ubuntu
# Versión:      v1.0 — {fecha_hoy} — Generado con Claude Sonnet 4.6
# Revisado:     no revisado
# Objetivo:     [Input] → [Output]
# MODO:         produccion → Telegram activo / auditoria → Telegram desactivado
# Dependencias: Sin dependencias externas — stdlib pura
# Configuración:
#   Variable    Tipo   Default         Descripción
#   MODO        str    'auditoria'     Controla Telegram, rutas y logs
#   PROYECTO    str    '{proyecto}'    Prefijo para nombres de ficheros
# Mapeos:
#   Fichero                  URL raw GitHub                    Contenido
#   telegram_config.json     {{BASE_RAW}}/mapeos/telegram...   Token y chat_id
#   base_raw.json            {{BASE_RAW}}/mapeos/base_raw...   URL base repo
# Rutas:
#   output/raw/    Datos sin procesar — {proyecto}_raw.json
#   output/clean/  Datos transformados — {proyecto}_clean.csv
#   output/logs/   Logs con timestamp — {proyecto}_log.txt
# Salida esperada:
#   [OK] Registros procesados: N
# Limitaciones:
#   · [Añadir limitaciones conocidas]
# =============================================================================
#
# Cambios:
#   v1.0 — {fecha_hoy} — Versión inicial
# =============================================================================
\"\"\"

import os
import json
import logging
import traceback
import time
import random
from pathlib import Path
from datetime import datetime, timezone

# =============================================================================
# ENTORNO
# =============================================================================
try:
    from google.colab import output
    EN_COLAB = True
except ImportError:
    EN_COLAB = False

EN_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

# =============================================================================
# VERSIÓN
# =============================================================================
SCRIPT_VERSION  = "1.0"
SCRIPT_FECHA    = "{fecha_hoy}"
SCRIPT_MODELO   = "Claude Sonnet 4.6"

# =============================================================================
# MODO
# =============================================================================
# 'auditoria'  → Telegram desactivado · rutas Colab · log solo consola
# 'produccion' → Telegram activo · rutas repo · log en fichero
MODO = 'auditoria'  # ← cambiar a 'produccion' antes de subir a GitHub

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
PROYECTO = '{proyecto}'

BASE_RAW = "https://raw.githubusercontent.com/USUARIO/{repo}/main"

MAPEOS = {{
    "telegram": BASE_RAW + "/mapeos/telegram_config.json",
    "base_raw": BASE_RAW + "/mapeos/base_raw.json",
}}

# =============================================================================
# REINTENTOS — PERFILES_FUENTE
# =============================================================================
PERFILES_FUENTE = {{
    "telegram": {{"max_reintentos": 5, "timeout": 5,  "pausa_base": 0.0}},
    "github":   {{"max_reintentos": 3, "timeout": 10, "pausa_base": 0.0}},
    "bls":      {{"max_reintentos": 3, "timeout": 10, "pausa_base": 1.0}},
    "sec":      {{"max_reintentos": 3, "timeout": 15, "pausa_base": 0.5}},
    "gnews":    {{"max_reintentos": 2, "timeout": 8,  "pausa_base": 0.5}},
}}

# =============================================================================
# RUTAS — adaptadas por MODO
# =============================================================================
if MODO == 'auditoria' and EN_COLAB:
    REPO_DIR  = Path("/content/drive/MyDrive/{repo}")
else:
    REPO_DIR  = Path(".")

LOG_DIR   = REPO_DIR / "output" / "logs"
RAW_DIR   = REPO_DIR / "output" / "raw"
CLEAN_DIR = REPO_DIR / "output" / "clean"

# LOG_DIR se crea siempre primero
LOG_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE   = LOG_DIR   / f"{{PROYECTO}}_log.txt"
RAW_FILE   = RAW_DIR   / f"{{PROYECTO}}_raw.json"
CLEAN_FILE = CLEAN_DIR / f"{{PROYECTO}}_clean.csv"

# =============================================================================
# LOGGING
# =============================================================================
def setup_logging() -> logging.Logger:
    \"\"\"Configura logging a consola siempre y a fichero en producción.\"\"\"
    fmt = "[%(asctime)s UTC] [%(levelname)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    handlers = [logging.StreamHandler()]
    if MODO == 'produccion':
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format=fmt, datefmt=datefmt,
                        handlers=handlers)
    logger = logging.getLogger(PROYECTO)
    return logger

log = setup_logging()

# =============================================================================
# VALIDACIONES
# =============================================================================
def validar_configuracion() -> None:
    \"\"\"Valida tipos, rangos y existencia de rutas antes de ejecutar nada.\"\"\"
    assert MODO in ('produccion', 'auditoria'), f"[CONFIG] MODO inválido: {{MODO}}"
    assert isinstance(PROYECTO, str) and PROYECTO, "[CONFIG] PROYECTO debe ser str no vacío"
    log.info(f"Configuración validada — MODO={{MODO}} · v{{SCRIPT_VERSION}}")

# =============================================================================
# REINTENTOS — función base stdlib pura
# =============================================================================
def con_reintento(func, fuente: str, *args, **kwargs):
    \"\"\"
    Ejecuta func con backoff exponencial + jitter según PERFILES_FUENTE.
    Distingue errores recuperables (red, timeout) de no recuperables (400, 401).
    \"\"\"
    import requests
    perfil = PERFILES_FUENTE.get(fuente, {{"max_reintentos": 3, "timeout": 10, "pausa_base": 1.0}})
    max_r  = perfil["max_reintentos"]
    pausa  = perfil["pausa_base"]

    for intento in range(1, max_r + 1):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.HTTPError as e:
            codigo = e.response.status_code if e.response else 0
            if codigo in (400, 401, 403):
                log.error(f"[ERROR] HTTP {{codigo}} en {{fuente}} — no recuperable. Abortando.")
                raise
            if codigo == 429:
                espera = 60 + random.uniform(0, 10)
                log.warning(f"[WARN] HTTP 429 en {{fuente}} — rate limit. Esperando {{espera:.0f}}s")
                time.sleep(espera)
                continue
            log.warning(f"[WARN] HTTP {{codigo}} en {{fuente}} — reintentando ({{intento}}/{{max_r}})")
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                OSError) as e:
            log.warning(f"[WARN] Error de red en {{fuente}} ({{intento}}/{{max_r}}): {{e}}")
        except KeyboardInterrupt:
            raise  # siempre propagar

        if intento < max_r:
            espera = pausa * (2 ** (intento - 1)) + random.uniform(0, 0.5)
            log.warning(f"[WARN] Reintentando en {{espera:.1f}}s...")
            time.sleep(espera)

    log.error(f"[FATAL] Agotados {{max_r}} reintentos en {{fuente}}. Abortando.")
    raise RuntimeError(f"Agotados reintentos en {{fuente}}")

# =============================================================================
# MAPEOS — descarga con reintento — fallo es fatal
# =============================================================================
def cargar_mapeos() -> dict:
    \"\"\"Descarga mapeos desde GitHub raw. Fallo aborta antes de ejecutar.\"\"\"
    import requests
    config = {{}}
    for nombre, url in MAPEOS.items():
        try:
            resp = con_reintento(
                lambda u=url: requests.get(u, timeout=PERFILES_FUENTE["github"]["timeout"]),
                fuente="github"
            )
            resp.raise_for_status()
            config[nombre] = resp.json()
            log.info(f"[OK] Mapeo cargado: {{nombre}}")
        except Exception as e:
            log.error(f"[FATAL] No se pudo cargar mapeo '{{nombre}}': {{e}}")
            raise  # fallo en mapeo es fatal — abortar
    return config

# =============================================================================
# FUNCIONES CORE — una función = una responsabilidad
# =============================================================================
def ejecutar_logica_principal(config: dict) -> dict:
    \"\"\"
    Lógica principal del script. Sustituir con implementación real.
    Returns: dict con resultados procesados
    \"\"\"
    log.info("[INFO] Ejecutando lógica principal...")
    # TODO: implementar
    return {{"registros": 0, "errores": 0}}

# =============================================================================
# NOTIFICACIÓN TELEGRAM — condicionada por MODO
# =============================================================================
def notificar_telegram(mensaje: str, config: dict) -> None:
    \"\"\"
    Envía mensaje a Telegram. Solo activo en MODO produccion.
    Si falla, registra en log — nunca es fallo fatal.
    \"\"\"
    import requests
    if MODO != 'produccion':
        log.info("[INFO] Telegram desactivado en MODO auditoria")
        return
    try:
        token   = config.get("telegram", {{}}).get("bot_token", "")
        chat_id = config.get("telegram", {{}}).get("chat_id", "")
        if not token or not chat_id or "REEMPLAZAR" in token:
            log.warning("[WARN] telegram_config.json sin configurar — notificación omitida")
            return
        url = f"https://api.telegram.org/bot{{token}}/sendMessage"
        con_reintento(
            lambda: requests.post(url, data={{"chat_id": chat_id, "text": mensaje[:4000]}},
                                  timeout=PERFILES_FUENTE["telegram"]["timeout"]),
            fuente="telegram"
        )
        log.info("[OK] Notificación Telegram enviada")
    except Exception as e:
        log.error(f"[ERROR] Telegram falló: {{e}} — continuando (fallback a log)")

# =============================================================================
# EJECUCIÓN
# =============================================================================
if __name__ == "__main__":
    try:
        log.info(f"{'='*50}")
        log.info(f"{PROYECTO} v{SCRIPT_VERSION} · MODO={MODO} · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        log.info(f"{'='*50}")

        validar_configuracion()
        config    = cargar_mapeos()
        resultado = ejecutar_logica_principal(config)

        resumen = (
            f"[{PROYECTO.upper()}] — {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')} | "
            f"■ OK | Registros: {resultado.get('registros', 0)}"
        )
        log.info(resumen)
        notificar_telegram(resumen, config)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        log.error(f"[FATAL] Excepción no controlada: {{e}}")
        log.error(tb)
        try:
            notificar_telegram(
                f"[{PROYECTO.upper()}] ■ ERROR\\n{str(e)[:300]}\\n"
                f"Revisar logs: output/logs/{PROYECTO}_log.txt",
                {{}}
            )
        except Exception:
            pass
        raise
""",

    # ── Output — ficheros con nombre fijo (sin timestamp) ──────────────────
    "output/raw/.gitkeep":   "",
    "output/clean/.gitkeep": "",
    "output/logs/.gitkeep":  "",

    # ── Docs ───────────────────────────────────────────────────────────────
    "docs/manual_operativa.html": """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Manual Operativa — {repo}</title>
</head>
<body>
<h1>Manual Operativa — {repo}</h1>
<p>Generado: {fecha_hoy}</p>
<p>Completar con la documentación operativa del proyecto.</p>
</body>
</html>
""",

    # ── README ─────────────────────────────────────────────────────────────
    "README.md": """\
# {repo}

Generado con `init_repo_structure.py` — {fecha_hoy}  
Estructura según `system_prompt_implicito_v3.0`

## Estructura

```
.github/workflows/cron.yml   — Schedule de ejecución automática
mapeos/                      — Datos de referencia y configuración versionados
scripts/                     — Scripts principales
output/raw/                  — Datos sin procesar (sobrescrito en cada ejecución)
output/clean/                — Datos transformados
output/logs/                 — Logs con timestamp
docs/manual_operativa.html   — Manual de operativa
```

## Configuración inicial

1. Editar `mapeos/telegram_config.json` con token y chat_id reales
2. Editar `mapeos/base_raw.json` con tu usuario de GitHub
3. Implementar lógica en `scripts/{proyecto}_main.py`
4. Cambiar `MODO = 'produccion'` antes de subir a GitHub
5. Activar el workflow desde GitHub Actions → Run workflow
""",

    # ── .gitignore ─────────────────────────────────────────────────────────
    ".gitignore": """\
__pycache__/
*.pyc
*.pyo
.DS_Store
.env
*.egg-info/
dist/
build/
.ipynb_checkpoints/
""",
}


# =============================================================================
# FUNCIONES CORE
# =============================================================================

def crear_estructura(repo_nombre: str, base_dir: Path, proyecto: str) -> tuple:
    """
    Crea la estructura de directorios y ficheros stub.
    Escenario B: usa REPO_DIR_OVERRIDE (directorio actual = raíz del repo)
    en lugar de crear base_dir/repo_nombre para evitar subcarpeta adicional.
    No sobreescribe ficheros existentes.
    Returns: (n_dirs_creados, n_ficheros_creados, omitidos)
    """
    repo_dir   = REPO_DIR_OVERRIDE  # Escenario B — directorio actual
    n_dirs      = 0
    n_ficheros  = 0
    omitidos    = 0

    print(f"[INFO] Creando estructura en: {repo_dir}")

    for ruta_rel, contenido in ESTRUCTURA.items():
        # Sustituir placeholders en rutas y contenido con replace() simple
        # Evita conflictos con llaves {} en código Python al usar .format()
        ruta_rel = ruta_rel.replace("{proyecto}", proyecto).replace("{repo}", repo_nombre)

        if contenido:
            contenido = (contenido
                .replace("{proyecto}", proyecto)
                .replace("{repo}", repo_nombre)
                .replace("{fecha_hoy}", FECHA_HOY)
            )

        ruta_abs = repo_dir / ruta_rel

        # Crear directorio padre si no existe
        ruta_abs.parent.mkdir(parents=True, exist_ok=True)
        n_dirs += 1

        # No sobreescribir ficheros existentes
        if ruta_abs.exists():
            print(f"  [SKIP] Ya existe: {ruta_rel}")
            omitidos += 1
            continue

        # Crear fichero
        ruta_abs.write_text(contenido, encoding="utf-8")
        print(f"  [OK]   {ruta_rel}")
        n_ficheros += 1

    return n_dirs, n_ficheros, omitidos


def imprimir_arbol(repo_nombre: str, base_dir: Path) -> None:
    """Imprime el árbol de directorios generado."""
    repo_dir = REPO_DIR_OVERRIDE  # Escenario B
    print(f"\n{'='*50}")
    print(f"ÁRBOL GENERADO — {repo_dir}")
    print(f"{'='*50}")
    for ruta in sorted(repo_dir.rglob("*")):
        nivel  = len(ruta.relative_to(repo_dir).parts) - 1
        indent = "  " * nivel
        icono  = "📁" if ruta.is_dir() else "📄"
        print(f"{indent}{icono} {ruta.name}")


# =============================================================================
# EJECUCIÓN
# =============================================================================
if __name__ == "__main__":
    try:
        print("=" * 50)
        print(f"INIT REPO STRUCTURE v1.0 — {FECHA_HOY}")
        print(f"Repo:     {REPO_NOMBRE}")
        print(f"Base dir: {BASE_DIR}")
        print(f"Proyecto: {PROYECTO}")
        print("=" * 50)

        n_dirs, n_ficheros, omitidos = crear_estructura(
            REPO_NOMBRE, BASE_DIR, PROYECTO
        )

        imprimir_arbol(REPO_NOMBRE, BASE_DIR)

        print(f"\n{'='*50}")
        print(f"[OK] Estructura creada en: {REPO_DIR_OVERRIDE.resolve()}")
        print(f"[OK] {n_ficheros} ficheros creados · {omitidos} omitidos (ya existían)")
        print(f"{'='*50}")
        print("\nSiguientes pasos:")
        print(f"  1. Editar mapeos/telegram_config.json con token y chat_id reales")
        print(f"  2. Editar mapeos/base_raw.json con tu usuario de GitHub")
        print(f"  3. Implementar lógica en scripts/{PROYECTO}_main.py")
        print(f"  4. git init && git add . && git commit -m 'init: estructura base'")
        print(f"  5. git remote add origin https://github.com/USUARIO/{REPO_NOMBRE}.git")
        print(f"  6. git push -u origin main")

    except KeyboardInterrupt:
        print("\n[INFO] Interrumpido por el usuario")
    except Exception as e:
        import traceback
        print(f"\n[FATAL] Error inesperado: {e}")
        print(traceback.format_exc())
        raise
