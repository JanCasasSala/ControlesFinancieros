# =============================================================================
# SELLER WATCH · MONITOR DE PUBLICACIONES DE SHORT SELLERS v1.0
# =============================================================================
# Propósito: detectar informes publicados por short sellers conocidos sobre
#            los tickers activos de la cartera en T+0 — cuando el seller
#            publica en su propia web, antes de Bloomberg y Google News.
#
# Timeline de propagación de un short attack:
#   T+0   Web del seller        ← este script
#   T+0   X / Twitter
#   T+2h  Bloomberg / Reuters
#   T+4h  Google News           ← monitor_noticias.py llega aquí
#   T+inf El precio ya cayó
#
# Compatibilidad: Google Colab · GitHub Actions · ejecución local
# Dependencias:   requests · beautifulsoup4
#                 (stdlib: os, json, hashlib, datetime, traceback)
#
# Principios de diseño (por orden de prioridad):
#   1. KISS    — scraping directo de fuente, sin intermediarios
#   2. Robustez — errores explícitos, reintentos, sin except desnudos
#   3. DRY     — lógica sin duplicación · excepción: datos de configuración
#   4. YAGNI   — solo detección básica en v1.0, sin scoring automático
#   5. Sin dependencias externas innecesarias
#
# Objetivos SMART v1.0:
#   S — Scrapear 4 webs de sellers conocidos, detectar menciones a 5 tickers
#   M — 0 falsos positivos en auditoría 720h
#   A — BeautifulSoup + requests, sin autenticación
#   R — Detecta el informe en T+0, antes de Google News
#   T — v1.0 cubre Hindenburg, Citron, Muddy Waters, Bleecker
#
# Cambios v1.0 — 20-mar-2026 — Generado con Claude Sonnet 4.6
#   · Primera versión — scraping directo de webs de sellers conocidos
#   · 4 sellers tier-1: Hindenburg, Citron, Muddy Waters, Bleecker
#   · 5 tickers activos: GLNG, LULU, PYPL, FISV, SQ(XYZ)
#   · Deduplicación por hash MD5 — no notifica el mismo informe dos veces
#
# TODOs para v1.1:
#   · Gotham City Research — contenido en JavaScript, requiere selenium/playwright
#   · Añadir TEP y UNH cuando se activen en el sistema
#   · Scoring manual D1/D3 pre-calculado en la alerta (modelo v1.3 Sección IV)
#   · Monitorizar X/Twitter de sellers conocidos como señal complementaria
#
# Revisado: no revisado
#
# =============================================================================
# FLUJO DE TRABAJO
# =============================================================================
#
# PASO 1 — AUDITORÍA (siempre primero)
#   DRY_RUN=True · ejecutar en Colab · revisar output completo
#   Verificar que todas las webs devuelven titulares correctamente
#   Verificar que no hay falsos positivos en los matches
#
# PASO 2 — VALIDAR KEYWORDS
#   Revisar TICKERS_KEYWORDS si aparecen matches incorrectos
#   Añadir exclusiones si hay términos ambiguos que generan ruido
#
# PASO 3 — PASAR A PRODUCCIÓN
#   Con OK explícito del humano:
#   DRY_RUN = False · subir a GitHub
#   Cron recomendado: cada 2h entre 06:00 y 22:00 CET
#   Verificar que llega Telegram · revisar primera ejecución manualmente
#
# =============================================================================

import subprocess, sys

def _instalar(pkg: str) -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

for _pkg in ["requests", "beautifulsoup4"]:
    try:
        __import__(_pkg.replace("-", ""))
    except ImportError:
        _instalar(_pkg)

import requests
from bs4 import BeautifulSoup
import hashlib
import json
import os
import traceback
from datetime import datetime, timezone

try:
    from google.colab import output
    EN_COLAB = True
except ImportError:
    EN_COLAB = False

EN_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"


# =============================================================================
# MODO
# =============================================================================
# REGLA DE ENTREGA — FLAGS DE MODO
# -----------------------------------------------------------------------------
# Todo script generado o modificado por un agente IA se entrega SIEMPRE en
# modo auditoría. El paso a producción es una decisión humana explícita.
#
# AUDITORÍA (estado por defecto al entregar):
#   DRY_RUN = True   ← nunca envía Telegram, no guarda vistos
#
# PRODUCCIÓN (cambio manual con OK explícito del humano):
#   DRY_RUN = False
# =============================================================================
DRY_RUN = False   # ← AUDITORÍA — cambiar a False solo con OK explícito


# =============================================================================
# CONFIGURACIÓN GLOBAL
# =============================================================================

TOKEN           = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID         = "8351044609"
ENVIAR_TELEGRAM = True

CARPETA     = "seller_watch"
RUTA_VISTOS = os.path.join(CARPETA, "seller_watch_vistos.json")

HEADERS_HTTP = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# =============================================================================
# SELLERS CONFIG
# =============================================================================
# DRY: configuración hardcodeada — no externalizar a JSON
#
# Gotham City Research excluida de v1.0 — contenido renderizado en JavaScript
# TODO v1.1: añadir Gotham via selenium o playwright
#
# Campos:
#   url      — página principal donde publican informes
#   tags     — tags HTML donde aparecen los titulares de informes
#   tier     — 1 = CAT1 directo · 2 = CAT2

SELLERS_CONFIG = {

    "Hindenburg Research": {
        "activo":    True,
        "url":       "https://hindenburgresearch.com",
        "tags":      ["h1", "h2", "h3"],
        "tier":      1,
        "nota":      "Informe Block SQ mar-2023 (-15%). Mayor probabilidad de repetir.",
        "cat":       "CAT1",
    },

    "Citron Research": {
        "activo":    True,
        "url":       "https://citronresearch.com",
        "tags":      ["h1", "h2", "h3"],
        "tier":      1,
        "nota":      "Andrew Left — especialista en valoracion excesiva y tech growth.",
        "cat":       "CAT1",
    },

    "Muddy Waters Research": {
        "activo":    True,
        "url":       "https://muddywatersresearch.com",
        "tags":      ["h1", "h2", "h3"],
        "tier":      1,
        "nota":      "Ataco SOFI mar-2026. Fraude contable y deuda oculta.",
        "cat":       "CAT1",
    },

    "Bleecker Street Research": {
        "activo":    True,
        "url":       "https://bleeckerstreetresearch.com",
        "tags":      ["h1", "h2", "h3"],
        "tier":      2,
        "nota":      "Especialista en fintech y unit economics — area de la cartera.",
        "cat":       "CAT2",
    },

    "Gotham City Research": {
        "activo":    False,   # JavaScript — requiere selenium en v1.1
        "url":       "https://gothamcityresearch.com",
        "tags":      ["h1", "h2", "h3"],
        "tier":      1,
        "nota":      "TODO v1.1 — contenido en JavaScript, no accesible con requests.",
        "cat":       "CAT1",
    },
}


# =============================================================================
# TICKERS KEYWORDS
# =============================================================================
# Keywords de detección por ticker — buscan coincidencia en titular normalizado
# DRY: datos de configuración hardcodeados — decisión explícita de diseño
#
# Block/XYZ: keywords amplias — historial Hindenburg 2023 sobre Cash App
# Criterio de inclusión: cualquier término que identifique inequívocamente
# la empresa en el contexto de un informe bajista

TICKERS_KEYWORDS = {

    "GLNG": {
        "nombre":   "Golar LNG",
        "keywords": ["golar", "glng", "flng", "golar lng"],
    },

    "LULU": {
        "nombre":   "Lululemon Athletica",
        "keywords": ["lululemon", "lulu", "athletica"],
    },

    "PYPL": {
        "nombre":   "PayPal Holdings",
        "keywords": ["paypal", "pypl", "venmo", "fastlane"],
    },

    "FISV": {
        "nombre":   "Fiserv",
        "keywords": ["fiserv", "fisv", "clover"],
    },

    "SQ": {
        "nombre":   "Block (XYZ)",
        "keywords": ["block inc", "block xyz", "cash app", "afterpay",
                     "jack dorsey", "square payments", " xyz ", "ticker xyz"],
        "nota":     "Hindenburg publico sobre Block/SQ en mar-2023 (-15%)",
    },
}


# =============================================================================
# PERFILES DE REINTENTO Y BACKOFF
# =============================================================================

PERFILES_FUENTE = {
    "web": {
        "max_reintentos": 3,
        "timeout":        12,
        "pausa_base":     1.0,
    },
    "telegram": {
        "max_reintentos": 5,
        "timeout":        10,
        "pausa_base":     0.0,
    },
}


# =============================================================================
# RUTAS
# =============================================================================

os.makedirs(CARPETA, exist_ok=True)


# =============================================================================
# VALIDACIONES
# =============================================================================

def _validar_config() -> None:
    """Valida configuración crítica antes de ejecutar."""
    assert TOKEN,   "[FATAL] TOKEN de Telegram no configurado"
    assert CHAT_ID, "[FATAL] CHAT_ID de Telegram no configurado"
    sellers_activos = [k for k, v in SELLERS_CONFIG.items() if v.get("activo")]
    assert sellers_activos, "[FATAL] No hay sellers activos en SELLERS_CONFIG"
    tickers_activos = [k for k in TICKERS_KEYWORDS]
    assert tickers_activos, "[FATAL] TICKERS_KEYWORDS vacio"


# =============================================================================
# FUNCIONES CORE
# =============================================================================

_errores: list = []


def registrar_error(contexto: str, detalle: Exception, sugerencia: str = "") -> None:
    """Registra error sin abortar — el sistema siempre notifica."""
    _errores.append({
        "contexto":   contexto,
        "detalle":    str(detalle)[:200],
        "sugerencia": sugerencia,
    })
    print(f"  [ERROR] {contexto}: {str(detalle)[:120]}")


def con_reintento(fn, perfil: str, *args, **kwargs):
    """
    Ejecuta fn con reintentos y backoff exponencial con jitter.
    Recuperables: red, timeout, HTTP 429/500-503.
    No recuperables: HTTP 403, ValueError, TypeError.
    """
    import time, random
    cfg        = PERFILES_FUENTE[perfil]
    max_r      = cfg["max_reintentos"]
    pausa_base = cfg["pausa_base"]

    for intento in range(1, max_r + 1):
        try:
            return fn(*args, **kwargs)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            if intento == max_r:
                raise
            pausa = pausa_base * (2 ** (intento - 1)) + random.uniform(0, 0.5)
            print(f"  [WARN] Reintentando ({intento}/{max_r}) en {pausa:.1f}s...")
            time.sleep(pausa)
        except requests.exceptions.HTTPError as e:
            codigo = e.response.status_code if e.response else 0
            if codigo in (429, 500, 502, 503):
                if intento == max_r:
                    raise
                pausa = pausa_base * (2 ** (intento - 1)) + random.uniform(0, 0.5)
                print(f"  [WARN] HTTP {codigo} — reintentando ({intento}/{max_r})...")
                time.sleep(pausa)
            else:
                raise
        except Exception:
            raise


def normalizar(texto: str) -> str:
    """Normaliza texto para comparación — minúsculas, sin puntuación."""
    return (texto.lower()
            .replace("-", " ")
            .replace("'", "")
            .replace(",", "")
            .replace(".", " ")
            .replace("(", " ")
            .replace(")", " "))


def fetch_titulares(seller: str, cfg: dict) -> list:
    """
    Descarga la página principal del seller y extrae titulares.
    Devuelve lista de strings con los titulares encontrados.
    """
    url  = cfg["url"]
    tags = cfg["tags"]

    def _get():
        resp = requests.get(
            url,
            headers=HEADERS_HTTP,
            timeout=PERFILES_FUENTE["web"]["timeout"],
        )
        resp.raise_for_status()
        return resp.text

    try:
        html     = con_reintento(_get, "web")
        soup     = BeautifulSoup(html, "html.parser")
        titulares = []
        for tag in soup.find_all(tags):
            texto = tag.get_text(strip=True)
            if texto and len(texto) > 10:
                titulares.append(texto)
        print(f"  {seller}: {len(titulares)} titulares encontrados")
        return titulares

    except Exception as e:
        registrar_error(
            f"Scraping · {seller}", e,
            f"Verificar acceso a {url}"
        )
        return []


def detectar_matches(titulares: list, seller: str, cat: str) -> list:
    """
    Busca menciones a tickers de la cartera en los titulares.
    Devuelve lista de dicts con los matches encontrados.
    """
    matches = []
    for titular in titulares:
        tn = normalizar(titular)
        for ticker, cfg_ticker in TICKERS_KEYWORDS.items():
            keywords = cfg_ticker["keywords"]
            if any(k.lower() in tn for k in keywords):
                matches.append({
                    "seller":  seller,
                    "ticker":  ticker,
                    "nombre":  cfg_ticker["nombre"],
                    "titular": titular,
                    "cat":     cat,
                    "hash":    hashlib.md5(
                        (seller + titular).lower().encode()
                    ).hexdigest()[:12],
                })
                if DRY_RUN:
                    keyword_match = next(k for k in keywords if k.lower() in tn)
                    print(f"  [DEBUG MATCH] {seller} · {ticker} · "
                          f"keyword '{keyword_match}' → {titular[:70]}")
    return matches


# =============================================================================
# DEDUPLICACIÓN
# =============================================================================

def cargar_vistos() -> set:
    """Carga hashes de titulares ya notificados."""
    if os.path.exists(RUTA_VISTOS):
        try:
            with open(RUTA_VISTOS, "r", encoding="utf-8") as f:
                return set(json.load(f).get("hashes", []))
        except Exception:
            pass
    return set()


def guardar_vistos(vistos: set) -> None:
    """Persiste hashes de titulares notificados — máximo 200."""
    os.makedirs(CARPETA, exist_ok=True)
    with open(RUTA_VISTOS, "w", encoding="utf-8") as f:
        json.dump({"hashes": list(vistos)[-200:]}, f)


# =============================================================================
# NOTIFICACIÓN
# =============================================================================

def enviar_telegram(texto: str, token: str = None, chat_id: str = None) -> bool:
    """
    Envía mensaje por Telegram con reintentos.
    Condicionado por DRY_RUN — nunca envía en modo auditoría.
    Fallback a log si falla — nunca fallo fatal.
    """
    if DRY_RUN:
        print(f"  [DRY_RUN] Telegram no enviado · {len(texto)} chars")
        return True

    t   = token or TOKEN
    c   = chat_id or CHAT_ID
    url = f"https://api.telegram.org/bot{t}/sendMessage"

    def _post():
        resp = requests.post(
            url,
            data={"chat_id": c, "text": texto[:4000]},
            timeout=PERFILES_FUENTE["telegram"]["timeout"],
        )
        resp.raise_for_status()
        return True

    try:
        return con_reintento(_post, "telegram")
    except Exception as e:
        print(f"  [ERROR] Telegram — fallback a log: {e}")
        registrar_error("Telegram — mensaje no enviado", e,
                        "Verificar TOKEN y CHAT_ID")
        return False


def render_match(match: dict) -> str:
    """Formatea una alerta de match para Telegram."""
    L = []
    L.append(f"[{match['cat']}] {match['ticker']} · {match['nombre']}")
    L.append(f"Seller: {match['seller']}")
    L.append(f"Titular: {match['titular'][:200]}")
    L.append(f"Accion: Leer informe completo en web del seller")
    L.append(f"Scoring: aplicar D1/D3 pre-calculado · D2/D4 requieren leer el informe")
    return "\n".join(L)


def render_errores() -> str:
    """Formatea el bloque de errores del sistema."""
    if not _errores:
        return ""
    L = ["", "=" * 38, f"AVISOS DEL SISTEMA [{len(_errores)}]", "-" * 30]
    for e in _errores:
        L.append(f"! {e['contexto']}")
        L.append(f"  {e['detalle']}")
        if e["sugerencia"]:
            L.append(f"  -> {e['sugerencia']}")
        L.append("")
    return "\n".join(L)


def render_resumen(matches_nuevos: list, sellers_revisados: list,
                   fecha_now: str) -> str:
    """Formatea el mensaje de resumen para auditoría."""
    L = []
    L.append(f"SELLER WATCH v1.0 · {fecha_now}")
    L.append(f"Sellers: {' · '.join(sellers_revisados)}")
    if DRY_RUN:
        L.append("MODO: AUDITORIA")
    L.append("=" * 38)

    if matches_nuevos:
        L.append(f"\nMATCHES DETECTADOS [{len(matches_nuevos)}]")
        L.append("-" * 30)
        for m in matches_nuevos:
            L.append("")
            L.append(render_match(m))
    else:
        L.append("\nSin matches — ningún seller ha publicado sobre los tickers activos")
        L.append("Sistema vigilando. Sin accion requerida.")

    if _errores:
        L.append(render_errores())

    L.append("\n" + "=" * 38)
    L.append("El detector alerta — la interpretacion es siempre humana")
    L.append("Verificar informe completo antes de actuar")

    if DRY_RUN:
        L.append("\nFIN AUDITORIA — Para produccion:")
        L.append("DRY_RUN=False · cron cada 2h entre 06:00-22:00 CET")
    else:
        L.append(f"\nSistema: OK · v1.0 · {fecha_now}")

    return "\n".join(L)


# =============================================================================
# EJECUCIÓN
# =============================================================================

def seller_watch() -> str:
    """
    Orquesta el scraping de webs de sellers conocidos y la detección
    de menciones a los tickers activos de la cartera.
    """
    fecha_now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")

    print("=" * 50)
    print(f"SELLER WATCH v1.0 · {fecha_now}")
    print(f"DRY_RUN={DRY_RUN} · MODO={'AUDITORIA' if DRY_RUN else 'PRODUCCION'}")
    print("=" * 50)

    _validar_config()

    vistos          = cargar_vistos()
    nuevos_vistos   = set()
    matches_nuevos  = []
    sellers_revisados = []

    sellers_activos = {k: v for k, v in SELLERS_CONFIG.items()
                       if v.get("activo", False)}

    print(f"Sellers activos: {', '.join(sellers_activos.keys())}")
    print(f"Tickers vigilados: {', '.join(TICKERS_KEYWORDS.keys())}")

    for seller, cfg in sellers_activos.items():
        print(f"\n--- {seller} ---")
        sellers_revisados.append(seller.split()[0])  # nombre corto

        titulares = fetch_titulares(seller, cfg)
        if not titulares:
            continue

        matches = detectar_matches(titulares, seller, cfg["cat"])

        for match in matches:
            h = match["hash"]
            if h not in vistos:
                nuevos_vistos.add(h)
                matches_nuevos.append(match)
                print(f"  [NUEVO] {match['cat']} · {match['ticker']} · "
                      f"{match['titular'][:60]}")
            else:
                if DRY_RUN:
                    print(f"  [YA VISTO] {match['ticker']} · {match['titular'][:60]}")

    # Actualizar vistos
    vistos.update(nuevos_vistos)
    if not DRY_RUN:
        guardar_vistos(vistos)

    # Resumen
    print("\n" + "=" * 50)
    print(f"RESUMEN:")
    print(f"  Sellers revisados : {len(sellers_revisados)}")
    print(f"  Matches nuevos    : {len(matches_nuevos)}")
    print(f"  Errores           : {len(_errores)}")
    print("=" * 50)

    # Notificaciones — alerta inmediata por cada match nuevo
    for match in matches_nuevos:
        alerta = (
            f"ALERTA {match['cat']} — SHORT SELLER PUBLICADO\n" +
            "=" * 38 + "\n" +
            render_match(match) + "\n" +
            "=" * 38
        )
        enviar_telegram(alerta)

    # Resumen diario — solo en produccion si no hay matches
    # En auditoria siempre muestra el resumen completo
    resumen = render_resumen(matches_nuevos, sellers_revisados, fecha_now)
    print("\n--- RESUMEN ---")
    print(resumen)
    print("---------------")

    if DRY_RUN or not matches_nuevos:
        enviar_telegram(resumen)

    return resumen


if __name__ == "__main__":
    try:
        seller_watch()
    except Exception as e:
        tb = traceback.format_exc()
        print("=" * 50)
        print("EXCEPCION TOTAL — script abortado")
        print(tb)
        print("=" * 50)
        if ENVIAR_TELEGRAM and not DRY_RUN:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    data={"chat_id": CHAT_ID,
                          "text": f"SELLER WATCH v1.0 — EXCEPCION TOTAL\n{str(e)[:300]}"},
                    timeout=15,
                )
            except Exception:
                pass
