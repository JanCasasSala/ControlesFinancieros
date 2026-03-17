# =============================================================================
# ENTORNO
# Plataforma : GitHub Actions (produccion) / Google Colab (auditoria)
# Python     : 3.10+
# OS         : Ubuntu 22.04 (GitHub) / Colab runtime (auditoria)
# Repo       : https://github.com/JanCasasSala/ControlesFinancieros
# Encoding   : UTF-8
# Timezone   : UTC
# =============================================================================

# =============================================================================
# VERSIÓN
# Script   : monitor_largo_v2.py — Monitor de Cartera Largo (SAN/ITX/LOG)
# Versión  : v2.0 — 2026-03-17
# Generado : Claude Sonnet 4.6
# Revisado : pendiente
# Cambios  :
#   v1.0 — 2026-03-?? — Versión inicial operativa
#   v2.0 — 2026-03-17 — Refactorización contra directrices v3.0:
#                        estructura obligatoria, MODO automático por entorno,
#                        con_reintento() con backoff, logs con niveles UTC,
#                        type hints, docstrings, tres hitos nuevos
#                        (LOG-DIV id11, SAN-FCF id12, MACRO-BONO id13)
# =============================================================================

# =============================================================================
# MODO
# Detectado automáticamente:
#   GITHUB_ACTIONS=true  → 'produccion' (GitHub Actions)
#   en otro caso         → 'auditoria'  (Google Colab / local)
# Produccion : Telegram activo, log en consola + fichero
# Auditoria  : Telegram desactivado, log solo consola
# =============================================================================
import os

MODO = 'produccion' if os.environ.get("GITHUB_ACTIONS") == "true" else 'auditoria'

# =============================================================================
# DEPENDENCIAS
# EXCEPCIÓN justificada:
#   yfinance   — única fuente viable de precios y financials sin API key
#   requests   — llamadas Telegram API
#   matplotlib — generación de gráficos embebidos en HTML
#   pandas     — manipulación de series temporales de precios
# Instalación automática si no están presentes (compatibilidad Colab).
# =============================================================================
import subprocess, sys

def _instalar(pkg: str) -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

try:
    import yfinance as yf
except ImportError:
    _instalar("yfinance"); import yfinance as yf

try:
    import requests
except ImportError:
    _instalar("requests"); import requests

try:
    import matplotlib
except ImportError:
    _instalar("matplotlib"); import matplotlib

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# =============================================================================
# CONFIGURACIÓN
# Todas las variables parametrizables en un único lugar.
# Nunca dentro de funciones.
# =============================================================================
LARGO_DATA = [
    {"tk": "SAN.MC", "cant": 6149, "cp": 2.43,  "div": 0.24, "bb": 2.6},
    {"tk": "ITX.MC", "cant": 520,  "cp": 19.20, "div": 1.90, "bb": 0.0},
    {"tk": "LOG.MC", "cant": 1070, "cp": 16.89, "div": 2.10, "bb": 0.0},
]

# Telegram
# TODO (Fase 5): migrar a /mapeos/telegram_config.json cuando esté en el repo.
# En producción leer desde GitHub Secrets; en auditoria desde variable de entorno.
TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8351044609")

# Bono de referencia
BONO_REF_FALLBACK = 3.40
BONO_TICKERS = [
    ("ES10YT=RR", "Bono ES10Y (Reuters)"),
    ("^TNX",      "T-Note 10Y USA (proxy)"),
]
BONO_MIN, BONO_MAX = 0.1, 15.0

# Hito MACRO-BONO
# Umbral derivado del Y-TOT de ITX (~3.65%) con margen de 0.35pp.
# A 4.0% el GAP de ITX cae a ~0.3pp — zona de alerta real.
# Modificar aquí si cambia el perfil de yields de la cartera.
MACRO_BONO_UMBRAL = 4.0   # %
MACRO_BONO_DIAS   = 40    # días de cotización ~ 2 meses naturales

# Rutas
CARPETA    = "largo"
RUTA_HTML  = os.path.join(CARPETA, "Monitor_Largo.html")
RUTA_HITOS = os.path.join(CARPETA, "hitos_largo.json")

# =============================================================================
# REINTENTOS
# PERFILES_FUENTE — única fuente de verdad para parámetros de backoff.
# (max_reintentos, timeout_seg, pausa_base_seg)
# =============================================================================
PERFILES_FUENTE: dict[str, tuple[int, int, float]] = {
    "yfinance" : (3, 15, 1.0),
    "telegram" : (5,  5, 0.0),
    "bono"     : (3, 10, 1.0),
}

# =============================================================================
# MAPEOS
# BASE_RAW: URL base del repositorio. Todas las URLs de mapeos se construyen
# a partir de ella. Hoy solo documentado — se activará cuando el token
# Telegram migre a /mapeos/telegram_config.json (Fase 5 pendiente).
# =============================================================================
BASE_RAW = "https://raw.githubusercontent.com/JanCasasSala/ControlesFinancieros/main"
# MAPEOS = {
#     "telegram": f"{BASE_RAW}/mapeos/telegram_config.json",
# }

# =============================================================================
# RUTAS
# LOG_DIR siempre primero. Rutas adaptadas por MODO.
# =============================================================================
import io, base64, json, time, random, logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

if MODO == 'produccion':
    LOG_DIR    = Path("output/logs")
    OUTPUT_RAW = Path("output/raw")
else:
    LOG_DIR    = Path("/tmp/largo/logs")
    OUTPUT_RAW = Path("/tmp/largo/raw")

LOG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_RAW.mkdir(parents=True, exist_ok=True)

RUTA_LOG = LOG_DIR / "monitor_largo_log.txt"

# =============================================================================
# VALIDACIONES
# =============================================================================
assert isinstance(LARGO_DATA, list) and len(LARGO_DATA) > 0, \
    "[CONFIG] LARGO_DATA vacío"
assert MODO in ('produccion', 'auditoria'), \
    f"[CONFIG] MODO inválido: {MODO}"
assert 0.0 < BONO_REF_FALLBACK < BONO_MAX, \
    f"[CONFIG] BONO_REF_FALLBACK fuera de rango: {BONO_REF_FALLBACK}"
assert 0.0 < MACRO_BONO_UMBRAL < BONO_MAX, \
    f"[CONFIG] MACRO_BONO_UMBRAL fuera de rango: {MACRO_BONO_UMBRAL}"

# =============================================================================
# DETECCIÓN DE ENTORNO
# =============================================================================
def detectar_entorno() -> str:
    try:
        import google.colab  # noqa
        return "colab"
    except ImportError:
        pass
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "github"
    return "local"

ENTORNO = detectar_entorno()

# =============================================================================
# HITOS DEFAULT
# Fuente de verdad para inicializar hitos_largo.json si no existe.
# IDs 1-10: hitos existentes. IDs 11-13: nuevos (v2.0).
# =============================================================================
HITOS_DEFAULT: list[dict] = [
    # ── MANUALES ──────────────────────────────────────────────────────────────
    {"id": 1,  "tk": "SAN",   "hito": "Ratio CET1 >= 12%",
     "detalle": "Capital regulatorio tier 1 en earnings. Fuente: informe trimestral.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": False},
    {"id": 2,  "tk": "LOG",   "hito": "Ocupacion naves >= 95%",
     "detalle": "Tasa de ocupacion del portfolio logistico. Fuente: suplemento operativo.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Operativo",  "auto": False},
    {"id": 3,  "tk": "ITX",   "hito": "Expansion internacional sin deterioro de margenes",
     "detalle": "Nuevas aperturas netas positivas con margen EBIT estable o creciente.",
     "estado": False, "fecha": None, "critico": False, "categoria": "Estrategico","auto": False},
    {"id": 11, "tk": "LOG",   "hito": "Diversificacion no-tabaco: FCF crece >= 2pp/año",
     "detalle": "El % de FCF procedente de segmentos no-tabaco debe crecer al menos 2pp/año. "
                "Sin este umbral la diversificacion es narrativa sin verificacion. "
                "Fuente: suplemento operativo semestral de Logista.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Estrategico","auto": False},
    # ── AUTOMÁTICOS ───────────────────────────────────────────────────────────
    {"id": 4,  "tk": "SAN",   "hito": "Dividendo sostenible (payout <= 80% y FCF cubre div total)",
     "detalle": "Calculado automaticamente: payout ratio y cobertura FCF vs dividendo total posicion.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Capital",    "auto": True},
    {"id": 5,  "tk": "ITX",   "hito": "Dividendo sostenible (payout <= 80% y FCF cubre div total)",
     "detalle": "Calculado automaticamente: payout ratio y cobertura FCF vs dividendo total posicion.",
     "estado": False, "fecha": None, "critico": False, "categoria": "Capital",    "auto": True},
    {"id": 6,  "tk": "LOG",   "hito": "Dividendo sostenible (payout <= 80% y FCF cubre div total)",
     "detalle": "Calculado automaticamente: payout ratio y cobertura FCF vs dividendo total posicion.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Capital",    "auto": True},
    {"id": 7,  "tk": "SAN",   "hito": "FCF por accion creciente YoY",
     "detalle": "Calculado automaticamente: FCF/accion año actual vs año anterior.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": True},
    {"id": 8,  "tk": "ITX",   "hito": "FCF por accion creciente YoY",
     "detalle": "Calculado automaticamente: FCF/accion año actual vs año anterior.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": True},
    {"id": 9,  "tk": "LOG",   "hito": "FCF por accion creciente YoY",
     "detalle": "Calculado automaticamente: FCF/accion año actual vs año anterior.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": True},
    {"id": 10, "tk": "ITX",   "hito": "Margenes estables o crecientes (bruto y operativo)",
     "detalle": "Calculado automaticamente: margen bruto y operativo vs año anterior.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": True},
    {"id": 12, "tk": "SAN",   "hito": "Tendencia FCF/accion: no 3 ejercicios consecutivos decrecientes",
     "detalle": "Si FCF/accion lleva 3 ejercicios consecutivos decreciendo: deterioro "
                "aunque el payout sea <= 80%. Fuente: yfinance financials anuales.",
     "estado": None, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": True},
    {"id": 13, "tk": "MACRO", "hito": "ES10Y < 4.0% sostenido (trigger de revision de sizing)",
     "detalle": "Si el bono ES10Y supera el 4.0% durante 40+ dias de cotizacion (~2 meses), "
                "revisar sizing de toda la cartera. No es condicion de salida. "
                "Al revisar: comparar Y-CST de cada posicion vs bono — "
                "un Y-CST alto (ej. ITX 9.9%) es argumento para no reducir "
                "aunque el Y-TOT este ajustado.",
     "estado": None, "fecha": None, "critico": True,  "categoria": "Macro",      "auto": True},
]

# =============================================================================
# FUNCIONES CORE — LOGS
# =============================================================================

def _configurar_logger() -> logging.Logger:
    """
    Configura el logger del monitor.
    Producción : consola + fichero (RUTA_LOG).
    Auditoría  : solo consola.
    Formato    : [YYYY-MM-DD HH:MM:SS UTC] [NIVEL] mensaje
    """
    fmt = logging.Formatter(
        fmt="[%(asctime)s UTC] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt.converter = time.gmtime

    logger = logging.getLogger("monitor_largo")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if MODO == 'produccion':
        fh = logging.FileHandler(RUTA_LOG, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger

def _log_ok(logger: logging.Logger, msg: str) -> None:
    logger.info("[OK] " + msg)

def _log_warn(logger: logging.Logger, msg: str) -> None:
    logger.warning("[WARN] " + msg)

def _log_fatal(logger: logging.Logger, msg: str) -> None:
    logger.critical("[FATAL] " + msg)

# =============================================================================
# FUNCIONES CORE — REINTENTOS
# =============================================================================

def con_reintento(
    fn: Callable[[], Any],
    perfil: str,
    logger: logging.Logger,
    descripcion: str = "",
) -> Any:
    """
    Ejecuta fn() con backoff exponencial + jitter según PERFILES_FUENTE.

    Args:
        fn          : callable sin argumentos que realiza la operación
        perfil      : clave en PERFILES_FUENTE ('yfinance', 'telegram', 'bono')
        logger      : logger activo
        descripcion : texto para los logs

    Returns:
        Resultado de fn() si tiene éxito.

    Raises:
        RuntimeError : si se agotan todos los reintentos.
        ValueError / TypeError : errores no recuperables — propaga inmediatamente.
    """
    max_r, _, pausa_base = PERFILES_FUENTE[perfil]
    ultimo_error: Exception = RuntimeError("sin intentos")

    for intento in range(1, max_r + 1):
        try:
            resultado = fn()
            if intento > 1:
                _log_ok(logger, f"{descripcion} — ok en intento {intento}/{max_r}")
            return resultado

        except KeyboardInterrupt:
            raise

        except (ValueError, TypeError) as e:
            _log_fatal(logger, f"{descripcion} — error no recuperable: {e}")
            raise

        except Exception as e:
            ultimo_error = e
            if intento < max_r:
                pausa = pausa_base * (2 ** (intento - 1)) + random.uniform(0, 0.5)
                _log_warn(
                    logger,
                    f"{descripcion} — reintentando ({intento}/{max_r}) "
                    f"en {pausa:.1f}s — {type(e).__name__}: {e}",
                )
                time.sleep(pausa)
            else:
                _log_fatal(
                    logger,
                    f"{descripcion} — agotados {max_r} reintentos. "
                    f"Último error: {type(e).__name__}: {e}",
                )

    raise RuntimeError(
        f"con_reintento: agotados {max_r} reintentos en '{descripcion}'"
    ) from ultimo_error

# =============================================================================
# FUNCIONES CORE — BONO
# =============================================================================

def obtener_bono_ref(logger: logging.Logger) -> tuple[float, bool, str, list[str]]:
    """
    Descarga el tipo del bono de referencia con múltiples fallbacks.

    Returns:
        (valor, live, fuente, avisos)
        live=False indica que se usó el fallback hardcodeado.
    """
    avisos: list[str] = []

    for ticker, nombre in BONO_TICKERS:
        try:
            hist = con_reintento(
                fn=lambda t=ticker: yf.Ticker(t).history(period="5d", timeout=10),
                perfil="bono",
                logger=logger,
                descripcion=f"bono {nombre} ({ticker})",
            )

            if hist is None or hist.empty:
                msg = f"bono {nombre} ({ticker}): historial vacío"
                logger.warning("[WARN] " + msg); avisos.append(msg)
                continue

            serie = hist["Close"].dropna()
            if serie.empty:
                msg = f"bono {nombre} ({ticker}): Close vacío tras dropna"
                logger.warning("[WARN] " + msg); avisos.append(msg)
                continue

            valor = round(float(serie.iloc[-1]), 2)

            if not (BONO_MIN <= valor <= BONO_MAX):
                msg = (f"bono {nombre} ({ticker}): valor {valor}% fuera de rango "
                       f"[{BONO_MIN}–{BONO_MAX}%] — descartado")
                logger.warning("[WARN] " + msg); avisos.append(msg)
                continue

            _log_ok(logger, f"bono — {nombre}: {valor}%")
            return valor, True, nombre, avisos

        except RuntimeError as e:
            msg = f"bono {nombre} ({ticker}): reintentos agotados — {e}"
            logger.error("[ERROR] " + msg); avisos.append(msg)

    msg = (f"todos los tickers de bono fallaron. "
           f"Usando fallback hardcodeado: {BONO_REF_FALLBACK}%")
    logger.warning("[WARN] " + msg); avisos.append(msg)
    return BONO_REF_FALLBACK, False, "Fallback hardcodeado", avisos

# =============================================================================
# FUNCIONES CORE — HITOS
# =============================================================================

def cargar_hitos(logger: logging.Logger) -> list[dict]:
    """
    Carga hitos desde JSON local.
    Si no existe o falla la lectura, usa HITOS_DEFAULT y lo crea.
    """
    if os.path.exists(RUTA_HITOS):
        try:
            with open(RUTA_HITOS, "r", encoding="utf-8") as f:
                data = json.load(f)
                _log_ok(logger, f"hitos — cargados {len(data['hitos'])} desde {RUTA_HITOS}")
                return data["hitos"]
        except Exception as e:
            logger.error(f"[ERROR] hitos — error leyendo JSON: {e} — usando defaults")
    logger.info("[INFO] hitos — JSON no encontrado — usando defaults")
    return [h.copy() for h in HITOS_DEFAULT]


def guardar_hitos(hitos: list[dict], logger: logging.Logger) -> None:
    """
    Persiste hitos en JSON local.
    Nunca lanza excepción — fallo se registra en log.
    """
    try:
        os.makedirs(CARPETA, exist_ok=True)
        with open(RUTA_HITOS, "w", encoding="utf-8") as f:
            json.dump({"hitos": hitos}, f, ensure_ascii=False, indent=2)
        _log_ok(logger, f"hitos — guardados en {RUTA_HITOS}")
    except Exception as e:
        logger.error(f"[ERROR] hitos — error guardando JSON: {e}")


def _safe_float(val: Any, fallback: float | None = None) -> float | None:
    """Convierte val a float de forma segura. Devuelve fallback si falla."""
    try:
        v = float(val)
        return v if pd.notna(v) else fallback
    except Exception:
        return fallback


def calcular_hito_macro_bono(
    hitos: list[dict],
    fecha_now: str,
    bono_ref: float,
    bono_live: bool,
    logger: logging.Logger,
) -> list[str]:
    """
    Evalúa el hito MACRO-BONO (id 13): ES10Y sostenido > MACRO_BONO_UMBRAL.

    Lógica:
    - bono_live=False → estado=None (SEGUIMIENTO) — dato no fiable.
    - bono_ref <= umbral → estado=True (OK).
    - bono_ref > umbral → verifica MACRO_BONO_DIAS días en histórico 3 meses:
        - >= MACRO_BONO_DIAS → estado=False (REVISAR SIZING)
        - <  MACRO_BONO_DIAS → estado=None (VIGILAR)
    - Al activarse incluye recordatorio de revisar Y-CST por posición.

    Returns:
        Lista de avisos.
    """
    avisos: list[str] = []

    if not bono_live:
        for h in hitos:
            if h["auto"] and h["tk"] == "MACRO" and h["id"] == 13:
                h["estado"] = None
                h["fecha"]  = fecha_now
                h["detalle_auto"] = "Dato de bono no disponible (fallback) — en seguimiento"
        avisos.append("[hitos-auto] MACRO-BONO: dato fallback — SEGUIMIENTO")
        return avisos

    if bono_ref <= MACRO_BONO_UMBRAL:
        for h in hitos:
            if h["auto"] and h["tk"] == "MACRO" and h["id"] == 13:
                h["estado"] = True
                h["fecha"]  = fecha_now
                h["detalle_auto"] = (
                    f"ES10Y {bono_ref:.2f}% — por debajo del umbral {MACRO_BONO_UMBRAL}%"
                )
        avisos.append(
            f"[hitos-auto] MACRO-BONO: {bono_ref:.2f}% <= {MACRO_BONO_UMBRAL}% — OK"
        )
        return avisos

    # Bono > umbral — verificar sostenibilidad
    try:
        hist = con_reintento(
            fn=lambda: yf.Ticker("ES10YT=RR").history(period="3mo", timeout=10),
            perfil="bono",
            logger=logger,
            descripcion="MACRO-BONO histórico 3 meses",
        )

        if hist is not None and not hist.empty:
            serie             = hist["Close"].dropna()
            dias_sobre_umbral = int((serie > MACRO_BONO_UMBRAL).sum())
            sostenido         = dias_sobre_umbral >= MACRO_BONO_DIAS

            if sostenido:
                estado  = False
                detalle = (
                    f"ES10Y {bono_ref:.2f}% > {MACRO_BONO_UMBRAL}% — "
                    f"{dias_sobre_umbral} días sobre umbral — "
                    f"⚠ REVISAR SIZING. "
                    f"Recordatorio: comparar Y-CST de cada posición vs bono antes de reducir."
                )
            else:
                estado  = None
                detalle = (
                    f"ES10Y {bono_ref:.2f}% > {MACRO_BONO_UMBRAL}% — "
                    f"{dias_sobre_umbral}/{MACRO_BONO_DIAS} días sobre umbral — vigilando"
                )
        else:
            estado  = None
            detalle = (
                f"ES10Y {bono_ref:.2f}% > {MACRO_BONO_UMBRAL}% "
                f"pero sin histórico — en seguimiento"
            )

    except RuntimeError:
        estado  = None
        detalle = (
            f"ES10Y {bono_ref:.2f}% > {MACRO_BONO_UMBRAL}% — "
            f"error descargando histórico — en seguimiento"
        )

    for h in hitos:
        if h["auto"] and h["tk"] == "MACRO" and h["id"] == 13:
            h["estado"] = estado
            h["fecha"]  = fecha_now
            h["detalle_auto"] = detalle
    avisos.append(f"[hitos-auto] MACRO-BONO: {detalle}")
    return avisos


def calcular_hitos_auto(
    hitos: list[dict],
    fecha_now: str,
    logger: logging.Logger,
    bono_ref: float = 0.0,
    bono_live: bool = False,
) -> tuple[list[dict], list[str]]:
    """
    Sobreescribe el estado de los hitos con auto=True usando yfinance.
    Los hitos manuales (auto=False) no se tocan.
    Si un ticker falla, sus hitos quedan con el estado previo — nunca aborta.

    Args:
        hitos     : lista de hitos cargada desde JSON
        fecha_now : timestamp de la ejecución actual
        logger    : logger activo
        bono_ref  : tipo del bono de referencia (para hito MACRO-BONO)
        bono_live : True si el dato del bono es real (no fallback)

    Returns:
        (hitos actualizados, lista de avisos)
    """
    avisos: list[str] = []

    for item in LARGO_DATA:
        tk     = item["tk"]
        tk_lbl = tk[:3]
        cant   = item["cant"]

        try:
            asset = con_reintento(
                fn=lambda t=tk: yf.Ticker(t),
                perfil="yfinance",
                logger=logger,
                descripcion=f"yfinance Ticker {tk}",
            )

            fin  = asset.financials
            cf   = asset.cashflow
            info = asset.info or {}

            def get_row(df: Any, posibles_labels: list[str]) -> Any:
                if df is None or df.empty:
                    return None
                for lbl in posibles_labels:
                    if lbl in df.index:
                        return df.loc[lbl]
                    for idx in df.index:
                        if idx.lower() == lbl.lower():
                            return df.loc[idx]
                return None

            shares  = _safe_float(info.get("sharesOutstanding"))
            fcf_val = _safe_float(info.get("freeCashflow"))

            # ── Dividendo sostenible (ids 4, 5, 6) ───────────────────────────
            div_anual  = item["div"] * cant
            net_income = None

            ni_row = get_row(fin, ["Net Income", "Net Income Common Stockholders"])
            if ni_row is not None and len(ni_row) > 0:
                net_income = _safe_float(ni_row.iloc[0])

            if fcf_val is None or fcf_val == 0:
                ocf_row   = get_row(cf, ["Operating Cash Flow",
                                         "Cash Flow From Continuing Operating Activities"])
                capex_row = get_row(cf, ["Capital Expenditure", "Purchase Of PPE"])
                if ocf_row is not None and capex_row is not None:
                    ocf     = _safe_float(ocf_row.iloc[0], 0)
                    capex   = _safe_float(capex_row.iloc[0], 0)
                    fcf_val = ocf - abs(capex)  # type: ignore[operator]

            div_total_empresa = (item["div"] * _safe_float(shares, 0)) if shares else None
            payout_ok, fcf_cubre       = False, False
            payout_str, fcf_str        = "N/D", "N/D"

            if net_income and net_income > 0 and div_total_empresa:
                payout     = (div_total_empresa / net_income) * 100
                payout_ok  = payout <= 80
                payout_str = f"{payout:.0f}%"

            if fcf_val and fcf_val > 0:
                fcf_cubre = fcf_val >= div_anual
                fcf_str   = f"FCF {fcf_val/1e6:.0f}M vs div {div_anual:.0f}€"

            div_ok      = payout_ok and fcf_cubre
            div_detalle = f"Payout {payout_str} | {fcf_str}"

            for h in hitos:
                if h["auto"] and h["tk"] == tk_lbl and "Dividendo" in h["hito"]:
                    h["estado"] = div_ok
                    h["fecha"]  = fecha_now
                    h["detalle_auto"] = div_detalle
            avisos.append(
                f"[hitos-auto] {tk_lbl} Dividendo: {div_detalle} → {'OK' if div_ok else 'KO'}"
            )

            # ── FCF por acción YoY (ids 7, 8, 9) ─────────────────────────────
            fcf_row     = get_row(cf, ["Free Cash Flow", "Operating Cash Flow"])
            fcf_ok      = False
            fcf_yoy_str = "N/D"

            if fcf_row is not None and len(fcf_row) >= 2 and shares and shares > 0:
                fcf_act = _safe_float(fcf_row.iloc[0])
                fcf_ant = _safe_float(fcf_row.iloc[1])
                if fcf_act is not None and fcf_ant is not None and fcf_ant != 0:
                    fcf_ps_act  = fcf_act / shares
                    fcf_ps_ant  = fcf_ant / shares
                    fcf_ok      = fcf_ps_act > fcf_ps_ant
                    cambio      = ((fcf_ps_act - fcf_ps_ant) / abs(fcf_ps_ant)) * 100
                    fcf_yoy_str = f"{fcf_ps_act:.2f} vs {fcf_ps_ant:.2f} ({cambio:+.1f}%)"

            for h in hitos:
                if h["auto"] and h["tk"] == tk_lbl and "FCF" in h["hito"] and h["id"] in [7, 8, 9]:
                    h["estado"] = fcf_ok
                    h["fecha"]  = fecha_now
                    h["detalle_auto"] = f"FCF/acc YoY: {fcf_yoy_str}"
            avisos.append(
                f"[hitos-auto] {tk_lbl} FCF/acc YoY: {fcf_yoy_str} → {'OK' if fcf_ok else 'KO'}"
            )

            # ── Tendencia FCF/acción SAN — 3 ejercicios consecutivos (id 12) ─
            if tk_lbl == "SAN":
                fcf_tend_ok  : bool | None = False
                fcf_tend_str = "N/D"

                fcf_row_tend = get_row(cf, ["Free Cash Flow", "Operating Cash Flow"])
                if fcf_row_tend is not None and len(fcf_row_tend) >= 4 and shares and shares > 0:
                    fcf_ps = [
                        _safe_float(fcf_row_tend.iloc[i]) / shares  # type: ignore[operator]
                        for i in range(4)
                        if _safe_float(fcf_row_tend.iloc[i]) is not None
                    ]
                    if len(fcf_ps) >= 4:
                        tres_decrecientes = (
                            fcf_ps[0] < fcf_ps[1] and
                            fcf_ps[1] < fcf_ps[2] and
                            fcf_ps[2] < fcf_ps[3]
                        )
                        fcf_tend_ok  = not tres_decrecientes
                        vals = " → ".join(f"{v:.2f}" for v in reversed(fcf_ps))
                        fcf_tend_str = (
                            f"FCF/acc 4 años: {vals} "
                            f"{'⚠ 3 dec. consec.' if tres_decrecientes else '✓ sin deterioro sostenido'}"
                        )
                elif fcf_row_tend is not None and len(fcf_row_tend) >= 2:
                    fcf_tend_ok  = None  # SEGUIMIENTO — datos insuficientes
                    fcf_tend_str = (
                        f"Datos insuficientes para 3 ejercicios "
                        f"({len(fcf_row_tend)} disponibles) — en seguimiento"
                    )

                for h in hitos:
                    if h["auto"] and h["tk"] == "SAN" and h["id"] == 12:
                        h["estado"] = fcf_tend_ok
                        h["fecha"]  = fecha_now
                        h["detalle_auto"] = fcf_tend_str
                estado_str = 'OK' if fcf_tend_ok is True else ('VIGILAR' if fcf_tend_ok is None else 'KO')
                avisos.append(f"[hitos-auto] SAN FCF-tendencia: {fcf_tend_str} → {estado_str}")

            # ── Márgenes ITX (id 10) ──────────────────────────────────────────
            if tk_lbl == "ITX":
                rev_row  = get_row(fin, ["Total Revenue", "Operating Revenue"])
                gp_row   = get_row(fin, ["Gross Profit"])
                ebit_row = get_row(fin, ["Operating Income", "EBIT"])

                mg_ok, mo_ok = False, False
                margenes_str = "N/D"

                if (rev_row is not None and gp_row is not None and
                        len(rev_row) >= 2 and len(gp_row) >= 2):
                    rev_act = _safe_float(rev_row.iloc[0])
                    rev_ant = _safe_float(rev_row.iloc[1])
                    gp_act  = _safe_float(gp_row.iloc[0])
                    gp_ant  = _safe_float(gp_row.iloc[1])
                    if all(v and v > 0 for v in [rev_act, rev_ant, gp_act, gp_ant]):
                        mg_act       = (gp_act / rev_act) * 100  # type: ignore[operator]
                        mg_ant       = (gp_ant / rev_ant) * 100  # type: ignore[operator]
                        mg_ok        = mg_act >= mg_ant - 0.5
                        margenes_str = f"Bruto {mg_act:.1f}% vs {mg_ant:.1f}%"

                if (ebit_row is not None and rev_row is not None and
                        len(ebit_row) >= 2):
                    ebit_act = _safe_float(ebit_row.iloc[0])
                    ebit_ant = _safe_float(ebit_row.iloc[1])
                    rev_act  = _safe_float(rev_row.iloc[0])
                    rev_ant  = _safe_float(rev_row.iloc[1])
                    if all(v and v > 0 for v in [ebit_act, ebit_ant, rev_act, rev_ant]):
                        mo_act        = (ebit_act / rev_act) * 100  # type: ignore[operator]
                        mo_ant        = (ebit_ant / rev_ant) * 100  # type: ignore[operator]
                        mo_ok         = mo_act >= mo_ant - 0.5
                        margenes_str += f" | Operativo {mo_act:.1f}% vs {mo_ant:.1f}%"

                margenes_ok = mg_ok and mo_ok
                for h in hitos:
                    if h["auto"] and h["tk"] == "ITX" and h["id"] == 10:
                        h["estado"] = margenes_ok
                        h["fecha"]  = fecha_now
                        h["detalle_auto"] = margenes_str
                avisos.append(
                    f"[hitos-auto] ITX Márgenes: {margenes_str} → {'OK' if margenes_ok else 'KO'}"
                )

        except RuntimeError as e:
            msg = f"hitos-auto {tk}: reintentos agotados — {e}"
            logger.error("[ERROR] " + msg); avisos.append(msg)

        except Exception as e:
            msg = f"hitos-auto {tk}: {type(e).__name__} — {e}"
            logger.error("[ERROR] " + msg); avisos.append(msg)

    # ── Hito macro bono (fuera del loop de tickers) ───────────────────────────
    avisos += calcular_hito_macro_bono(hitos, fecha_now, bono_ref, bono_live, logger)

    return hitos, avisos


def calcular_conviccion(hitos: list[dict]) -> tuple[float, str, str]:
    """
    Score ponderado de convicción. Críticos pesan doble.
    Si 3+ críticos en PENDIENTE simultáneamente, score máximo = 35%.

    Returns:
        (score_pct, label, color_hex)
    """
    total = sum(2 if h["critico"] else 1 for h in hitos)
    if total == 0:
        return 0.0, "SIN DATOS", "#888888"

    ok  = sum((2 if h["critico"] else 1)       for h in hitos if h["estado"] is True)
    seg = sum((2 if h["critico"] else 1) * 0.5 for h in hitos if h["estado"] is None)
    score = ((ok + seg) / total) * 100

    criticos_pend = len([h for h in hitos if h["critico"] and h["estado"] is False])
    if criticos_pend >= 3:
        score = min(score, 35.0)

    if score >= 70:   return score, "ALTA CONVICCION",                 "#2ecc71"
    elif score >= 40: return score, "CONVICCION MEDIA",                "#f39c12"
    else:             return score, "CONVICCION BAJA — Revisar tesis", "#e74c3c"

# =============================================================================
# FUNCIONES CORE — HELPERS HTML
# =============================================================================

def badge(texto: str, color: str) -> str:
    """Genera un badge HTML con color de fondo semitransparente."""
    return (
        f"<span style='background:{color}33;color:{color};"
        f"padding:3px 10px;border-radius:8px;font-size:0.8rem;font-weight:bold;'>"
        f"{texto}</span>"
    )

def color_gap(v: float) -> str:
    """Devuelve color hex según el valor del GAP."""
    if v >= 1:  return "#2ecc71"
    if v >= 0:  return "#f39c12"
    return "#e74c3c"

def color_pnl(v: float) -> str:
    """Devuelve verde o rojo según el signo del P&L."""
    return "#2ecc71" if v >= 0 else "#e74c3c"

def estado_semaforo(gap: float, pa: float, sma100: float) -> tuple[str, str, str]:
    """
    Calcula el estado del semáforo (OK / AIRE / CARO).

    Returns:
        (estado, color_hex, tooltip)
    """
    if pa > sma100 and gap >= 0:
        return "OK",   "#2ecc71", "Precio sobre SMA100 y GAP positivo"
    elif gap < 0:
        return "CARO", "#e74c3c", "Rendimiento por debajo del bono de referencia"
    else:
        return "AIRE", "#f39c12", "GAP positivo pero precio bajo SMA100"

def fila_estrategia(
    tk: str, precio: str, y_tot: float, y_cst: float,
    gap: float, estado: str, color_est: str, tooltip: str,
    bono_ref: float = 0,
) -> str:
    """Genera una fila HTML para la tabla de estrategia de cosecha."""
    return (
        "<tr>"
        f"<td style='font-family:monospace;font-weight:700;color:#e0e0e0;'>{tk}</td>"
        f"<td style='font-family:monospace;'>{precio}</td>"
        f"<td style='color:{color_gap(y_tot - bono_ref)};font-weight:bold;'>{y_tot:.1f}%</td>"
        f"<td style='color:#aaa;'>{y_cst:.1f}%</td>"
        f"<td style='color:{color_gap(gap)};font-weight:bold;'>{gap:+.1f}%</td>"
        f"<td title='{tooltip}'>{badge(estado, color_est)}</td>"
        "</tr>"
    )

def fila_patrimonio(
    tk: str, coste: float, mercado: float, dif: float, pnl_pct: float,
) -> str:
    """Genera una fila HTML para la tabla de patrimonio."""
    return (
        "<tr>"
        f"<td style='font-family:monospace;font-weight:700;color:#e0e0e0;'>{tk}</td>"
        f"<td style='font-family:monospace;color:#aaa;'>{int(coste):,}€</td>"
        f"<td style='font-family:monospace;font-weight:bold;color:#e0e0e0;'>{int(mercado):,}€</td>"
        f"<td style='color:{color_pnl(dif)};font-weight:bold;'>{dif:+,.0f}€</td>"
        f"<td style='color:{color_pnl(pnl_pct)};font-weight:bold;'>{pnl_pct:+.1f}%</td>"
        "</tr>"
    )

def render_hitos_html(hitos: list[dict]) -> str:
    """Genera las filas HTML de la tabla de hitos para el informe."""
    cat_colors: dict[str, str] = {
        "Financiero":  "#2ecc71",
        "Operativo":   "#00d4ff",
        "Estrategico": "#9b59b6",
        "Capital":     "#f39c12",
        "Riesgo":      "#e74c3c",
        "Macro":       "#e67e22",
    }
    filas = ""
    for h in hitos:
        if h["estado"] is True:
            icono, color_e, label_e = "✓",   "#2ecc71", "CUMPLIDO"
        elif h["estado"] is False:
            icono, color_e, label_e = "✕",   "#e74c3c", "PENDIENTE"
        else:
            icono, color_e, label_e = "···", "#3498db", "SEGUIMIENTO"

        critico_tag = (
            "<span style='background:#e74c3c33;color:#e74c3c;"
            "padding:1px 6px;border-radius:4px;font-size:0.7rem;margin-left:6px;'>CRITICO</span>"
            if h["critico"] else ""
        )
        auto_tag = (
            "<span style='background:#3498db22;color:#3498db;"
            "padding:1px 6px;border-radius:4px;font-size:0.65rem;margin-left:4px;'>AUTO</span>"
            if h.get("auto") else ""
        )
        cat_color = cat_colors.get(h["categoria"], "#888")
        fecha_str = h.get("fecha") or "—"
        detalle   = h.get("detalle_auto") or h.get("detalle", "")

        filas += (
            "<tr>"
            f"<td style='font-family:monospace;font-weight:700;color:#aaa;text-align:center;'>"
            f"{h['tk']}</td>"
            f"<td style='text-align:center;font-weight:bold;color:{color_e};'>{icono}</td>"
            f"<td><span style='font-weight:600;color:#e0e0e0;'>{h['hito']}</span>"
            f"{critico_tag}{auto_tag}<br>"
            f"<small style='color:#555;'>{detalle}</small></td>"
            f"<td style='text-align:center;'>"
            f"<span style='background:{cat_color}22;color:{cat_color};"
            f"padding:2px 8px;border-radius:6px;font-size:0.75rem;'>{h['categoria']}</span></td>"
            f"<td style='text-align:center;color:{color_e};font-weight:bold;font-size:0.8rem;'>"
            f"{label_e}</td>"
            f"<td style='color:#555;font-size:0.78rem;text-align:center;'>{fecha_str}</td>"
            "</tr>"
        )
    return filas

# =============================================================================
# FUNCIONES NOTIFICACIÓN
# =============================================================================

def enviar_telegram(
    token: str,
    chat_id: str,
    texto: str,
    ruta_html: str,
    fecha_now: str,
    logger: logging.Logger,
) -> None:
    """
    Envía resumen de texto y HTML adjunto por Telegram.
    Solo activa en MODO='produccion'. Si falla, registra en log — nunca aborta.
    """
    if MODO != 'produccion':
        logger.info("[INFO] Telegram desactivado en modo auditoria")
        return

    url_base = f"https://api.telegram.org/bot{token}"

    try:
        con_reintento(
            fn=lambda: requests.post(
                f"{url_base}/sendMessage",
                data={"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"},
                timeout=5,
            ),
            perfil="telegram",
            logger=logger,
            descripcion="telegram sendMessage",
        )
        _log_ok(logger, "telegram — mensaje enviado")
    except Exception as e:
        logger.error(f"[ERROR] telegram sendMessage falló tras reintentos: {e}")

    try:
        with open(ruta_html, "rb") as f:
            con_reintento(
                fn=lambda: requests.post(
                    f"{url_base}/sendDocument",
                    data={"chat_id": chat_id,
                          "caption": f"Monitor Largo v2.0 — {fecha_now}"},
                    files={"document": (ruta_html, f, "text/html")},
                    timeout=15,
                ),
                perfil="telegram",
                logger=logger,
                descripcion="telegram sendDocument",
            )
        _log_ok(logger, "telegram — HTML enviado")
    except Exception as e:
        logger.error(f"[ERROR] telegram sendDocument falló tras reintentos: {e}")

# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

def monitor_largo_v2() -> str | None:
    """
    Función principal del monitor de Cartera Largo.
    Orquesta descarga, cálculo, generación HTML, persistencia y notificación.

    Returns:
        HTML generado como string, o None si hay error fatal.
    """
    logger = _configurar_logger()
    logger.info(f"[INFO] Monitor Largo v2.0 arrancando — MODO: {MODO} — ENTORNO: {ENTORNO}")

    try:
        fecha_now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")

        # ── Bono de referencia ────────────────────────────────────────────────
        BONO_REF, bono_live, bono_fuente, _ = obtener_bono_ref(logger)

        # ── Descarga de precios ───────────────────────────────────────────────
        logger.info("[INFO] Descargando precios de mercado...")
        tickers = [item["tk"] for item in LARGO_DATA]

        df_raw = con_reintento(
            fn=lambda: yf.download(tickers, period="250d", progress=False, auto_adjust=True),
            perfil="yfinance",
            logger=logger,
            descripcion="yf.download cartera largo",
        )
        df_prices = df_raw["Close"].ffill()
        _log_ok(logger, f"precios descargados — {len(df_prices)} sesiones")

        # ── Hitos ─────────────────────────────────────────────────────────────
        logger.info("[INFO] Calculando hitos automáticos...")
        hitos = cargar_hitos(logger)
        hitos, hitos_avisos = calcular_hitos_auto(
            hitos, fecha_now, logger,
            bono_ref=BONO_REF,
            bono_live=bono_live,
        )
        guardar_hitos(hitos, logger)
        for av in hitos_avisos:
            logger.info(f"[INFO] {av}")

        score_conv, label_conv, color_conv = calcular_conviccion(hitos)
        hitos_ok   = sum(1 for h in hitos if h["estado"] is True)
        hitos_seg  = sum(1 for h in hitos if h["estado"] is None)
        hitos_pend = sum(1 for h in hitos if h["estado"] is False)
        filas_hitos = render_hitos_html(hitos)

        # ── Cálculos por ticker ───────────────────────────────────────────────
        rows_estr: list[dict] = []
        rows_patr: list[dict] = []
        plot_items: list[dict] = []
        t_inv, t_mkt = 0.0, 0.0

        for item in LARGO_DATA:
            tk  = item["tk"]
            pa  = float(df_prices[tk].iloc[-1])
            ic  = item["cant"] * item["cp"]
            ia  = item["cant"] * pa
            t_inv += ic
            t_mkt += ia

            y_mkt = (item["div"] / pa) * 100
            y_tot = y_mkt + item["bb"]
            y_cst = (item["div"] / item["cp"]) * 100
            gap   = y_tot - BONO_REF

            sma100 = float(df_prices[tk].rolling(100).mean().iloc[-1])
            estado, color_est, tooltip = estado_semaforo(gap, pa, sma100)

            dif     = ia - ic
            pnl_pct = ((ia - ic) / ic) * 100

            rows_estr.append({
                "tk": tk[:3], "precio": f"{pa:.2f}", "y_tot": y_tot,
                "y_cst": y_cst, "gap": gap, "estado": estado,
                "color_est": color_est, "tooltip": tooltip,
            })
            rows_patr.append({
                "tk": tk[:3], "ic": ic, "ia": ia,
                "dif": dif, "pnl_pct": pnl_pct,
            })
            plot_items.append({
                "tk": tk[:3], "gap": gap,
                "pnl": pnl_pct, "peso": ia / t_mkt,
            })
            logger.info(
                f"[INFO] {tk[:3]}: {pa:.2f}€ | Y-TOT {y_tot:.1f}% | "
                f"GAP {gap:+.1f}% | {estado}"
            )

        # ── Gráficos ──────────────────────────────────────────────────────────
        logger.info("[INFO] Generando gráficos...")
        plt.style.use("dark_background")
        fig, axes = plt.subplots(1, 2, figsize=(14, 6), facecolor="#121212")
        colores_tk = {"SAN": "#e74c3c", "ITX": "#3498db", "LOG": "#2ecc71"}

        ax1 = axes[0]
        ax1.set_facecolor("#1e1e1e")
        hist_90 = df_prices.tail(90)
        norm = (hist_90 / hist_90.iloc[0]) * 100
        for item in LARGO_DATA:
            tk  = item["tk"]
            lbl = tk[:3]
            ax1.plot(norm.index, norm[tk], label=lbl,
                     color=colores_tk.get(lbl, "#aaa"), linewidth=2.2)
        ax1.axhline(100, color="#555", linestyle="--", linewidth=1, alpha=0.6)
        ax1.set_title("Evolución 90 días (base 100)", color="#00d4ff", fontsize=12, pad=10)
        ax1.legend(facecolor="#1e1e1e", fontsize=9)
        ax1.grid(alpha=0.07)
        ax1.tick_params(colors="#888")
        for spine in ax1.spines.values():
            spine.set_edgecolor("#333")

        ax2 = axes[1]
        ax2.set_facecolor("#1e1e1e")
        for d in plot_items:
            color = "#27ae60" if d["gap"] >= 0 else "#e67e22"
            ax2.scatter(d["gap"], d["pnl"], s=d["peso"] * 12000,
                        alpha=0.75, color=color, edgecolors="white", linewidth=1.5)
            ax2.text(d["gap"], d["pnl"], f"{d['tk']}\n{d['gap']:+.1f}%",
                     ha="center", va="center",
                     fontweight="bold", color="white", fontsize=9)
        ax2.axvline(0, color="#e74c3c", linestyle="--", alpha=0.6, linewidth=1.2)
        ax2.set_xlabel("GAP vs Bono (pp)", color="#888", fontsize=9)
        ax2.set_ylabel("P&L posición (%)", color="#888", fontsize=9)
        ax2.set_title("Radar de Cosecha: GAP vs P&L", color="#00d4ff", fontsize=12, pad=10)
        ax2.grid(alpha=0.07)
        ax2.tick_params(colors="#888")
        for spine in ax2.spines.values():
            spine.set_edgecolor("#333")

        fig.suptitle(f"Monitor Largo V2.0  |  {fecha_now}",
                     color="#e0e0e0", fontsize=13, fontweight="bold", y=1.01)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", facecolor="#121212", bbox_inches="tight", dpi=150)
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode()
        plt.close(fig)
        _log_ok(logger, "gráficos generados")

        # ── Filas HTML ────────────────────────────────────────────────────────
        filas_estr = "".join(
            fila_estrategia(r["tk"], r["precio"], r["y_tot"], r["y_cst"],
                            r["gap"], r["estado"], r["color_est"], r["tooltip"], BONO_REF)
            for r in rows_estr
        )
        filas_patr = "".join(
            fila_patrimonio(r["tk"], r["ic"], r["ia"], r["dif"], r["pnl_pct"])
            for r in rows_patr
        )

        dif_total   = t_mkt - t_inv
        pnl_total   = ((t_mkt - t_inv) / t_inv) * 100
        color_total = color_pnl(dif_total)

        yield_pond = sum(
            r["y_tot"] * (rows_patr[i]["ia"] / t_mkt)
            for i, r in enumerate(rows_estr)
        )
        gap_pond = yield_pond - BONO_REF

        entorno_badge = {
            "colab":  ("<span style='background:#f0883e22;color:#f0883e;"
                       "padding:2px 10px;border-radius:20px;font-size:0.72rem;font-weight:600;'>"
                       "Google Colab</span>"),
            "github": ("<span style='background:#3fb95022;color:#3fb950;"
                       "padding:2px 10px;border-radius:20px;font-size:0.72rem;font-weight:600;'>"
                       "GitHub Actions</span>"),
            "local":  ("<span style='background:#58a6ff22;color:#58a6ff;"
                       "padding:2px 10px;border-radius:20px;font-size:0.72rem;font-weight:600;'>"
                       "Local</span>"),
        }.get(ENTORNO, "")

        # ── HTML ──────────────────────────────────────────────────────────────
        html = f"""<!DOCTYPE html>
<html lang='es'>
<head>
  <meta charset='UTF-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1.0'>
  <title>Monitor Largo V2.0</title>
  <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
  <style>
    body {{ background:#121212;color:#e0e0e0;padding:25px;font-family:'Segoe UI',sans-serif; }}
    .card {{ background:#1e1e1e;border-radius:15px;padding:22px;margin-bottom:20px;border:none; }}
    h5 {{ color:#00d4ff;text-transform:uppercase;font-size:0.85rem;letter-spacing:1.5px;margin-bottom:15px; }}
    th {{ color:#555;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #2a2a2a !important; }}
    td {{ vertical-align:middle !important;border-bottom:1px solid #1a1a1a !important;padding:11px 8px !important; }}
    code {{ background:#2a2a2a;color:#00d4ff;padding:2px 6px;border-radius:4px;font-size:0.8rem; }}
    .kpi-box {{ background:#161616;border-radius:10px;padding:14px 18px;text-align:center; }}
    .kpi-val {{ font-size:1.6rem;font-weight:800;line-height:1; }}
    .kpi-lbl {{ font-size:0.68rem;color:#555;text-transform:uppercase;letter-spacing:1px;margin-top:5px; }}
    .leyenda-box {{ background:#161616;border-left:3px solid #00d4ff;border-radius:0 8px 8px 0;padding:12px 16px;font-size:0.82rem;color:#888;line-height:1.7; }}
  </style>
</head>
<body>
<div class='container' style='max-width:960px;'>

  <div class='d-flex justify-content-between align-items-center mb-4'>
    <div>
      <h2 style='color:#00d4ff;margin:0;'>Monitor Largo</h2>
      <small style='color:#555;'>V2.0 &nbsp;·&nbsp; {entorno_badge} &nbsp;·&nbsp; {fecha_now}</small>
    </div>
    <div style='text-align:right;'>
      <div style='font-size:2rem;font-weight:800;color:#00d4ff;'>{int(t_mkt):,}€</div>
      <div style='font-size:1rem;font-weight:700;color:{color_total};'>{dif_total:+,.0f}€ &nbsp;({pnl_total:+.1f}%)</div>
      <div style='font-size:0.7rem;color:#555;margin-top:4px;'>Bono ref: {BONO_REF}% &nbsp;·&nbsp; {bono_fuente}</div>
    </div>
  </div>

  <div class='card'>
    <div class='row g-3'>
      <div class='col-md-3'><div class='kpi-box'>
        <div class='kpi-val' style='color:#00d4ff;'>{int(t_inv):,}€</div>
        <div class='kpi-lbl'>Capital invertido</div>
      </div></div>
      <div class='col-md-3'><div class='kpi-box'>
        <div class='kpi-val' style='color:{color_pnl(yield_pond - BONO_REF)};'>{yield_pond:.1f}%</div>
        <div class='kpi-lbl'>Yield pond. total</div>
      </div></div>
      <div class='col-md-3'><div class='kpi-box'>
        <div class='kpi-val' style='color:{color_gap(gap_pond)};'>{gap_pond:+.1f}%</div>
        <div class='kpi-lbl'>GAP pond. vs bono</div>
      </div></div>
      <div class='col-md-3'><div class='kpi-box'>
        <div class='kpi-val' style='color:#888;'>{BONO_REF:.2f}%</div>
        <div class='kpi-lbl'>Bono referencia</div>
      </div></div>
    </div>
  </div>

  <div class='card'>
    <h5>Bloque 1 — Estrategia de Cosecha</h5>
    <p style='color:#666;font-size:0.78rem;margin-bottom:12px;'>
      Rentabilidad total (dividendo + buybacks) comparada con el bono de referencia ({BONO_REF}%).
      &nbsp;·&nbsp;<span style='color:{"#2ecc71" if bono_live else "#e67e22"};font-size:0.75rem;'>
      {"● " + bono_fuente if bono_live else bono_fuente}</span>
    </p>
    {"" if bono_live else "<div style='background:#e67e2218;border-left:3px solid #e67e22;border-radius:0 8px 8px 0;padding:10px 16px;margin-bottom:12px;font-size:0.8rem;color:#e67e22;'><strong>⚠ Bono con dato de fallback</strong> — no se pudo descargar el tipo real.</div>"}
    <table class='table table-dark mb-0'>
      <thead><tr>
        <th>Ticker</th><th>Precio</th>
        <th title='Yield sobre precio de mercado + buybacks'>Y-TOT</th>
        <th title='Yield sobre precio de coste'>Y-CST</th>
        <th title='Diferencia vs bono de referencia'>GAP</th>
        <th>Estado</th>
      </tr></thead>
      <tbody>{filas_estr}</tbody>
    </table>
    <div class='leyenda-box mt-3'>
      <strong style='color:#aaa;'>Guía:</strong>
      <code>Y-TOT</code> rendimiento sobre precio actual (div + BB) &nbsp;·&nbsp;
      <code>Y-CST</code> rendimiento sobre precio de coste &nbsp;·&nbsp;
      <code>GAP</code> diferencia vs Bono {BONO_REF}% &nbsp;·&nbsp;
      {badge("OK", "#2ecc71")} precio sobre SMA100 y GAP ≥ 0 &nbsp;·&nbsp;
      {badge("AIRE", "#f39c12")} GAP positivo pero precio bajo SMA100 &nbsp;·&nbsp;
      {badge("CARO", "#e74c3c")} rendimiento inferior al bono
    </div>
  </div>

  <div class='card'>
    <h5>Bloque 2 — Patrimonio</h5>
    <table class='table table-dark mb-0'>
      <thead><tr>
        <th>Ticker</th><th>Coste total</th><th>Mercado actual</th>
        <th>Diferencia €</th><th>P&amp;L %</th>
      </tr></thead>
      <tbody>
        {filas_patr}
        <tr style='border-top:2px solid #333;'>
          <td style='color:#00d4ff;font-weight:700;font-family:monospace;'>TOTAL</td>
          <td style='font-family:monospace;color:#aaa;'>{int(t_inv):,}€</td>
          <td style='font-family:monospace;font-weight:700;color:#e0e0e0;'>{int(t_mkt):,}€</td>
          <td style='color:{color_total};font-weight:700;'>{dif_total:+,.0f}€</td>
          <td style='color:{color_total};font-weight:700;'>{pnl_total:+.1f}%</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class='card'>
    <h5>Bloque 3 — Hitos T-G y Convicción</h5>
    <div class='row g-3 mb-3'>
      <div class='col-md-4'>
        <div style='background:#161616;border-radius:10px;padding:14px 18px;border-left:4px solid {color_conv};'>
          <div style='color:{color_conv};font-size:1rem;font-weight:bold;margin-bottom:4px;'>{label_conv}</div>
          <div style='color:#aaa;font-size:0.82rem;'>✓ {hitos_ok} &nbsp;·&nbsp; ··· {hitos_seg} &nbsp;·&nbsp; ✕ {hitos_pend}</div>
          <div style='background:#2a2a2a;border-radius:5px;height:8px;margin-top:8px;'>
            <div style='width:{round(score_conv)}%;height:8px;border-radius:5px;background:{color_conv};'></div>
          </div>
          <small style='color:#555;'>{round(score_conv)}% hitos validados</small>
        </div>
      </div>
      <div class='col-md-8'>
        <div style='background:#161616;border-radius:10px;padding:12px 16px;font-size:0.78rem;color:#666;line-height:1.8;'>
          <strong style='color:#aaa;'>Cómo se calcula:</strong>
          Hitos CRÍTICO pesan doble. SEGUIMIENTO aporta 50%.
          Si 3+ críticos en PENDIENTE, score máximo = 35%.
          &nbsp;·&nbsp;
          <span style='background:#3498db22;color:#3498db;padding:1px 6px;border-radius:4px;font-size:0.65rem;'>AUTO</span>
          calculado automáticamente cada ejecución.
        </div>
      </div>
    </div>
    <table class='table table-dark mb-0'>
      <thead><tr>
        <th style='width:50px;text-align:center;'>TKR</th>
        <th style='width:35px;text-align:center;'>Est.</th>
        <th>Hito</th>
        <th style='width:110px;text-align:center;'>Categoría</th>
        <th style='width:110px;text-align:center;'>Estado</th>
        <th style='width:100px;text-align:center;'>Fecha</th>
      </tr></thead>
      <tbody>{filas_hitos}</tbody>
    </table>
  </div>

  <div class='card text-center'>
    <h5>Bloque 4 — Gráficos</h5>
    <img src='data:image/png;base64,{img_b64}'
         style='width:100%;border-radius:10px;display:block;'>
    <p style='color:#555;font-size:0.75rem;margin-top:10px;margin-bottom:0;'>
      Izquierda: evolución normalizada 90 días (base 100). &nbsp;·&nbsp;
      Derecha: radar de cosecha — tamaño burbuja = peso en cartera.
    </p>
  </div>

  <div class='card'>
    <h5>Glosario</h5>
    <table class='table table-dark mb-0' style='font-size:0.82rem;'>
      <thead><tr>
        <th style='width:120px;'>Métrica</th><th>Definición</th>
        <th style='width:200px;'>Interpretación</th>
      </tr></thead>
      <tbody>
        <tr><td><code>Y-TOT</code></td>
          <td style='color:#aaa;'>Yield total sobre precio de mercado. Incluye dividendo estimado y rendimiento equivalente de buybacks.</td>
          <td style='color:#aaa;font-size:0.78rem;'>Mayor = la posición paga más sobre su precio actual.</td></tr>
        <tr style='background:#1a1a1a;'><td><code>Y-CST</code></td>
          <td style='color:#aaa;'>Yield sobre precio de coste. Mide el rendimiento real sobre el capital comprometido.</td>
          <td style='color:#aaa;font-size:0.78rem;'>Crece conforme el precio sube. Argumento para mantener ante compresión de GAP.</td></tr>
        <tr><td><code>GAP</code></td>
          <td style='color:#aaa;'>Diferencia entre Y-TOT y el bono de referencia ({BONO_REF}%).</td>
          <td style='color:#2ecc71;font-size:0.78rem;'>Positivo = la acción bate al bono. &nbsp;<span style='color:#e74c3c;'>Negativo = el bono es más rentable.</span></td></tr>
        <tr style='background:#1a1a1a;'><td><code>BB</code></td>
          <td style='color:#aaa;'>Rendimiento equivalente de buybacks sumado al dividendo para calcular Y-TOT.</td>
          <td style='color:#aaa;font-size:0.78rem;'>Relevante en SAN.</td></tr>
        <tr><td><code>SMA100</code></td>
          <td style='color:#aaa;'>Media móvil simple de 100 sesiones. Filtro técnico de tendencia.</td>
          <td style='color:#aaa;font-size:0.78rem;'>Precio sobre SMA100 + GAP positivo = semáforo verde.</td></tr>
      </tbody>
    </table>
  </div>

</div>
</body>
</html>"""

        # ── Guardar HTML ──────────────────────────────────────────────────────
        os.makedirs(CARPETA, exist_ok=True)
        with open(RUTA_HTML, "w", encoding="utf-8") as f:
            f.write(html)
        _log_ok(logger, f"HTML guardado en {RUTA_HTML}")

        # ── Colab: mostrar inline ─────────────────────────────────────────────
        if ENTORNO == "colab":
            from IPython.display import display, HTML as IPY_HTML
            display(IPY_HTML(html))
            _log_ok(logger, "HTML renderizado inline en Colab")

        # ── Resumen Telegram ──────────────────────────────────────────────────
        lineas_estr = "\n".join(
            f"{'✅' if r['estado']=='OK' else '⚠️' if r['estado']=='CARO' else '🟡'}  "
            f"{r['tk']}  {r['precio']}€  Y-TOT {r['y_tot']:.1f}%  GAP {r['gap']:+.1f}%"
            for r in rows_estr
        )
        lineas_patr = "\n".join(
            f"{r['tk']}  {int(r['ic']):,}€ → {int(r['ia']):,}€  ({r['pnl_pct']:+.1f}%)"
            for r in rows_patr
        )
        resumen = (
            f"🛡️ *MONITOR LARGO V2.0*\n"
            f"{'='*30}\n"
            f"💼 *ESTRATEGIA DE COSECHA*\n"
            f"Bono ref: {BONO_REF}%  ({bono_fuente})\n"
            + ("⚠️ _Bono con fallback — revisar conectividad_\n" if not bono_live else "")
            + f"{lineas_estr}\n\n"
            f"Yield pond: {yield_pond:.1f}%  |  GAP pond: {gap_pond:+.1f}%\n"
            f"{'='*30}\n"
            f"💰 *PATRIMONIO*\n"
            f"{lineas_patr}\n"
            f"{'─'*30}\n"
            f"TOTAL: {int(t_inv):,}€ → {int(t_mkt):,}€  ({pnl_total:+.1f}%)\n"
            f"{'='*30}\n"
            f"🎯 *CONVICCION T-G*\n"
            f"{label_conv}  ({round(score_conv)}%)\n"
            f"✓ {hitos_ok}  |  ··· {hitos_seg}  |  ✕ {hitos_pend}\n"
            f"{'='*30}\n"
            f"🕐 {fecha_now}"
        )

        enviar_telegram(TOKEN, CHAT_ID, resumen, RUTA_HTML, fecha_now, logger)
        _log_ok(logger, "Monitor Largo v2.0 completado")
        return html

    except Exception as e:
        msg = f"error fatal en monitor_largo_v2: {type(e).__name__}: {e}"
        try:
            logger.critical(f"[FATAL] {msg}")
        except Exception:
            print(f"[FATAL] {msg}")
        if MODO == 'produccion':
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    data={"chat_id": CHAT_ID,
                          "text": f"[FATAL] Monitor Largo v2.0: {e}"},
                    timeout=10,
                )
            except Exception:
                pass
        return None


# =============================================================================
if __name__ == "__main__":
    monitor_largo_v2()
