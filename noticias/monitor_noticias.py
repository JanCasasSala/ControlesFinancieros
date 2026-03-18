# =============================================================================
# MONITOR NOTICIAS v6.8
# =============================================================================
# Propósito: monitorización automática de noticias relevantes para tickers
#            del portfolio. Clasifica, filtra y envía alertas por Telegram.
#
# Compatibilidad: Google Colab · GitHub Actions · ejecución local
# Dependencias:   feedparser · requests (stdlib: hashlib, json, os, traceback)
# Principios de diseño (por orden de prioridad):
#   1. Robustez    — fallos silenciosos notificados, siempre llega algo a Telegram
#   2. Escalable   — añadir tickers solo requiere editar TICKERS_CONFIG, no el código
#   3. Sin dependencias externas — no requiere .env, secrets, APIs de pago ni BD
#
# Cambios v6.12 — 19-mar-2026 — Generado con Claude Sonnet 4.6
#   · SQ keywords_cat3: eliminado ("dorsey","block","strategy") y ("dorsey","block","ai")
#     Capturaban layoffs/IA operativos que no afectan a EPS ni Afterpay.
#     Cobertura de Dorsey se mantiene en CAT1 (resign) y CAT2 (efficiency concreta).
#   · LULU keywords_cat1: añadidas keywords para análisis negativos post-earnings
#     ("tariff"), ("margin","pressure"), ("muted","outlook/growth"), ("softer/weaker","outlook")
#     Criterio: op-eds con deterioro de márgenes o outlook débil → CAT1 por robustez.
#   · FISV Visa/Fiserv partnership: ya cae a ruido correctamente, sin cambios.
#   · keywords_cat1: eliminado ("ticker", "sec", "filing") en LULU, PYPL, FISV, SQ
#     Problema: los 8-K genéricos de SEC EDGAR generaban 10 falsos positivos CAT1
#     por ticker y ejecución. Auditoría manual de 30 filings confirmó que el 100%
#     de los eventos de invalidación real ya están cubiertos por keywords específicas
#     existentes + cobertura paralela de Google News.
#     Criterio: un 8-K sin cobertura de prensa paralela es por definición rutinario.
#     Se mantiene ("ticker", "sec", "investigation") en CAT1 — esa sí discrimina.
#     DRY_RUN=True · HORAS_LOOKBACK=720 para validar en Colab antes de producción.
#   · clasificar_manos_fuertes: corrección de falso positivo crítico
#     Problema: "vest" como subcadena bloqueaba titulares con "investor" e
#     "investment" (contienen "vest" embebido). Consecuencia: 5 noticias de
#     Jana Partners en FISV caían a ruido en lugar de CAT4.
#     Solución: sustituir el check de subcadena por check de palabra completa
#     usando split() para los términos ambiguos cortos ("vest", "post", "says").
#     Términos largo como "vesting", "layoffs", "workforce" no tienen este
#     problema y se mantienen como subcadena.
#     También eliminado "pushes" de exclusiones: "Fiserv stock pushes for changes"
#     es exactamente una noticia de mano fuerte relevante, no ruido operativo.
#
# Cambios v6.9 — 18-mar-2026 — Generado con Claude Sonnet 4.6
#   · clasificar_manos_fuertes: filtro explícito de ventas rutinarias de insiders
#     Problema identificado en auditoría: Dorsey generaba 10+ noticias en CAT4
#     por noticias sobre layoffs y declaraciones de IA, no por movimientos reales
#     de acciones. Causa raíz: el match era por nombre ("dorsey") en titulares
#     que no son Form 4 de acciones sino noticias operativas sobre su gestión.
#     Solución 1: añadir filtro de exclusión de keywords rutinarias (RSU, tax
#     withholding, 10b5-1, layoff, AI, jobs) antes de clasificar como CAT4.
#     Solución 2: subir umbral de Dorsey en SQ a $5M para ignorar ventas pequeñas
#     de RSU tax withholding y solo capturar ventas discrecionales significativas.
#     Criterio de señal real para insider: venta >10% de posición propia en
#     mercado abierto (open market), no bajo plan 10b5-1 y no por RSU withholding.
#
# Cambios v6.8 — 18-mar-2026 — Generado con Claude Sonnet 4.6
#   · TICKERS_CONFIG: añadidos PYPL, FISV y SQ (portfolio fintech US)
#     Keywords derivadas de análisis de tesis de inversión con horizonte 3-5 años.
#     Condición de salida única por ticker según framework de análisis:
#       PYPL: branded checkout TPV negativo 2T + CEO sin plan concreto
#       FISV: Financial Solutions sin crecimiento orgánico en H2 2026
#       SQ:   EPS miss >15% + riesgo crediticio Borrow supera targets
#     Manos fuertes: SEC EDGAR Form 13F — última actualización 18-mar-2026
#     Auditoría recomendada: DRY_RUN=True · HORAS_LOOKBACK=720 para calibrar
#     ruido antes de pasar a producción con los tres tickers nuevos.
#
# Cambios v6.7 — 18-mar-2026 — Generado con Claude Sonnet 4.6
#   · render_noticia: añadido enlace archive.ph como fallback de paywall
#     Motivo: artículos de pago (Business Times, FT, WSJ) piden email/suscripción
#     al hacer click desde Telegram. archive.ph guarda copias públicas de ~70%.
#     Formato en mensaje: URL original + "archivo: archive.ph/newest/URL"
#     Solo se añade para URLs HTTP/HTTPS — no para SEC EDGAR (ya son públicas).
#
# =============================================================================
# FLUJO DE TRABAJO ESTÁNDAR — seguir este orden en cada sesión de mantenimiento
# =============================================================================
#
# PASO 1 — ACTUALIZAR LIBRERÍAS DE DATOS POR TICKER (hacer siempre primero)
#   Para cada ticker activo, verificar y actualizar si han cambiado:
#   a) manos_fuertes: buscar en SEC EDGAR Form 13F los últimos trimestres
#      https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F
#      Añadir fondos nuevos con >1% del float o movimientos >$50M.
#      Eliminar fondos que hayan salido completamente.
#   b) gnews_queries: revisar si las queries devuelven resultados relevantes
#      en auditoría. Eliminar queries con 0 resultados consistentes.
#   c) sec_cik: verificar que el CIK sigue siendo correcto en EDGAR.
#
# PASO 2 — AUDITORÍA DE KEYWORDS (cuando hay ruido elevado o falsos negativos)
#   Ejecutar con DRY_RUN=True · HORAS_LOOKBACK=720
#   Revisar sección RUIDO FILTRADO: ¿hay noticias relevantes mal clasificadas?
#   Revisar CAT2/CAT3: ¿hay falsos positivos que deberían ser ruido?
#   Ajustar keywords_cat* según hallazgos. Re-ejecutar para validar.
#
# PASO 3 — ACTIVAR NUEVO TICKER
#   1. Copiar bloque de plantilla al final de TICKERS_CONFIG
#   2. Rellenar: nombre, sec_cik, gnews_queries, keywords, manos_fuertes
#   3. Cambiar "activo": True
#   4. Ejecutar auditoría (Paso 2) para validar keywords
#   5. Pasar a producción cuando el ruido sea <20% del total
#
# PASO 4 — PASAR A PRODUCCIÓN
#   DRY_RUN = False · HORAS_LOOKBACK = 26
#   Subir a GitHub: monitor_noticias.py + hitos_estado.json
#   Verificar que llega Telegram al ejecutar workflow manualmente
#
# =============================================================================

import subprocess, sys

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

for pkg, imp in [("feedparser", "feedparser"), ("requests", "requests")]:
    try:
        __import__(imp)
    except ImportError:
        install(pkg)

import feedparser
import requests
import hashlib
import json
import os
import traceback
from datetime import datetime, timezone, timedelta

try:
    from google.colab import output
    EN_COLAB = True
except ImportError:
    EN_COLAB = False

EN_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"


# =============================================================================
# SECCIÓN 1 — CONFIGURACIÓN GLOBAL
# =============================================================================
# DRY_RUN = True  → auditoría: imprime todo, muestra ruido completo,
#                   no envía Telegram, no guarda vistos.
#                   Usar con HORAS_LOOKBACK=720 para refinamiento de keywords.
# DRY_RUN = False → producción: envía Telegram, guarda vistos,
#                   muestra solo MUESTRA_RUIDO titulares de ruido.
#                   Usar con HORAS_LOOKBACK=26.
#
# DISEÑO INTENCIONADO — TOKEN y CHAT_ID hardcodeados en texto plano.
# Prioridad: compatibilidad total con Google Colab sin dependencias de entorno.
# En GitHub Actions podrían leerse de secrets, pero se prioriza portabilidad.
# Este diseño es forzado para no generar dependencias externas de entorno
# (os.getenv, secrets, .env files, etc). No cambiar sin evaluar impacto en Colab.
# =============================================================================

TOKEN           = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID         = "8351044609"
ENVIAR_TELEGRAM = True
DRY_RUN         = False # ← True = auditoría · False = producción
HORAS_LOOKBACK  = 26    # ← 720 para refinamiento · 26 para producción
MUESTRA_RUIDO   = 3     # Titulares de ruido visibles en producción

CARPETA     = "noticias"
RUTA_VISTOS = os.path.join(CARPETA, "noticias_vistas.json")

# Headers para SEC EDGAR — identificar el bot correctamente evita bloqueos
SEC_HEADERS = {
    "User-Agent":      "Portfolio Monitor monitor@portfolio.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept":          "application/atom+xml,application/xml,text/xml",
    "Host":            "www.sec.gov",
}


# =============================================================================
# SECCIÓN 2 — TICKERS CONFIG
# =============================================================================
# Estructura de cada ticker:
#
#   nombre            str   — nombre completo para mensajes
#   activo            bool  — False = ignorado en ejecución
#   precio_entrada    float — precio medio de entrada en cartera
#   moneda            str   — USD / EUR
#   sec_cik           str   — CIK de SEC EDGAR (None si no cotiza en USA)
#
#   gnews_queries     list  — queries de Google News RSS
#                             · Máximo 8 queries por ticker (coste HTTP)
#                             · Eliminar queries con 0 resultados en auditoría
#                             · Preferir términos específicos sobre genéricos
#
#   keywords_cat1     list  — INVALIDACIÓN DE TESIS: noticias que requieren
#                             revisar la posición en <48h. Ser conservador:
#                             mejor un falso positivo que perder una señal real.
#   keywords_cat1_hitos dict — mapeo keyword → (id_hito, descripcion, accion)
#
#   keywords_cat2     list  — CATALIZADORES: noticias que pueden acelerar
#                             la tesis o justificar ampliar posición.
#   keywords_cat2_hitos dict
#
#   keywords_cat3     list  — CONFIRMACIÓN: earnings, dividendos, upgrades.
#                             Seguimiento del estado de la tesis.
#   keywords_cat3_hitos dict
#
#   manos_fuertes     dict  — LISTA BLANCA de fondos institucionales relevantes.
#                             PASO 1 DEL FLUJO: actualizar cada trimestre con
#                             datos de SEC EDGAR Form 13F.
#                             Formato: clave → (nombre_completo, umbral_usd, razon)
#                             umbral_usd=0 significa que cualquier movimiento es
#                             relevante independientemente del tamaño.
#
#   manos_fuertes_umbral_usd int — umbral mínimo en USD para fondos NO en lista
#                             blanca. Captura entradas nuevas significativas de
#                             fondos desconocidos sin generar ruido de posiciones
#                             menores. Recomendado: 50_000_000 (50M USD).
#
#   macro_config      dict  — configuración de fuentes macro (BLS, etc.)
#                             None si no aplica para este ticker.
#
# ESTRUCTURA keywords_cat_hitos:
#   clave  = tupla de keywords (igual que en keywords_cat*)
#   valor  = (id_hito, descripcion_hito, accion_sugerida)
#   id_hito = None si es solo seguimiento sin acción requerida en JSON
# =============================================================================

TICKERS_CONFIG = {

    "GLNG": {
        "nombre":         "Golar LNG",
        "activo":         True,
        "precio_entrada": 46.25,
        "moneda":         "USD",
        "sec_cik":        "0001166663",

        # Queries Google News — revisadas en auditoría 15-mar-2026
        # · "Hilli Episeyo" y "Gimi BP GTA" devuelven 0 — mantener por si
        #   hay noticias operativas futuras (baja frecuencia esperada)
        "gnews_queries": [
            "Golar LNG contract",
            "Golar LNG FLNG",
            "Hilli Episeyo",
            "SESA Argentina LNG",
            "Gimi BP GTA",
            "GLNG stock",
        ],

        # ── CAT 1 · INVALIDACIÓN DE TESIS ────────────────────────────────
        # Criterio: cualquier noticia que amenace los contratos take-or-pay
        # o la estructura de capital de GLNG requiere revisión inmediata.
        # Ser conservador: mejor revisar de más que perder una señal real.
        "keywords_cat1": [
            ("hilli",     "terminat"),
            ("hilli",     "cancel"),
            ("hilli",     "renegotiat"),
            ("hilli",     "breach"),
            ("perenco",   "terminat"),
            ("perenco",   "cancel"),
            ("perenco",   "contract", "end"),
            ("sesa",      "cancel"),
            ("sesa",      "terminat"),
            ("mkii",      "cancel"),
            ("mkii",      "terminat"),
            ("argentina", "flng",   "cancel"),
            ("golar",     "argentina", "cancel"),
            ("golar",     "shares offered"),
            ("golar",     "equity offering"),
            ("golar",     "dilut"),
            ("glng",      "dilut"),
            ("golar",     "secondary offering"),
            ("golar",     "force majeure"),
            ("gimi",      "terminat"),
            ("gimi",      "cancel"),
        ],

        "keywords_cat1_hitos": {
            ("hilli",     "terminat"):           (7, "Hilli — Contrato Perenco vigente",  "estado:false"),
            ("hilli",     "cancel"):             (7, "Hilli — Contrato Perenco vigente",  "estado:false"),
            ("hilli",     "renegotiat"):         (7, "Hilli — Contrato Perenco vigente",  "estado:false"),
            ("hilli",     "breach"):             (7, "Hilli — Contrato Perenco vigente",  "estado:false"),
            ("perenco",   "terminat"):           (7, "Hilli — Contrato Perenco vigente",  "estado:false"),
            ("perenco",   "cancel"):             (7, "Hilli — Contrato Perenco vigente",  "estado:false"),
            ("perenco",   "contract", "end"):    (7, "Hilli — Contrato Perenco vigente",  "estado:false"),
            ("sesa",      "cancel"):             (8, "MKII Argentina — Deal 20 anos",     "estado:false"),
            ("sesa",      "terminat"):           (8, "MKII Argentina — Deal 20 anos",     "estado:false"),
            ("mkii",      "cancel"):             (8, "MKII Argentina — Deal 20 anos",     "estado:false"),
            ("mkii",      "terminat"):           (8, "MKII Argentina — Deal 20 anos",     "estado:false"),
            ("argentina", "flng",   "cancel"):   (8, "MKII Argentina — Deal 20 anos",     "estado:false"),
            ("golar",     "argentina", "cancel"):(8, "MKII Argentina — Deal 20 anos",     "estado:false"),
            ("golar",     "shares offered"):     (9, "Sin dilucion capital >10%",         "estado:false"),
            ("golar",     "equity offering"):    (9, "Sin dilucion capital >10%",         "estado:false"),
            ("golar",     "dilut"):              (9, "Sin dilucion capital >10%",         "estado:false"),
            ("glng",      "dilut"):              (9, "Sin dilucion capital >10%",         "estado:false"),
            ("golar",     "secondary offering"): (9, "Sin dilucion capital >10%",         "estado:false"),
            ("golar",     "force majeure"):      (7, "Hilli — Contrato Perenco vigente",  "estado:false — verificar cual activo"),
            ("gimi",      "terminat"):           (1, "Gimi — Operacion comercial plena",  "estado:false"),
            ("gimi",      "cancel"):             (1, "Gimi — Operacion comercial plena",  "estado:false"),
        },

        # ── CAT 2 · CATALIZADORES ─────────────────────────────────────────
        # Criterio: noticias que pueden acelerar la tesis o justificar
        # ampliar posición. Incluye macro LNG, contratos nuevos y FLNG.
        # Añadido en v6: cuarta unidad FLNG — catalizador pendiente clave.
        "keywords_cat2": [
            ("lng",           "price",   "high"),
            ("lng",           "price",   "rise"),
            ("european gas",  "high"),
            ("jkm",           "high"),
            ("ttf",           "high"),
            ("hormuz",        "lng"),
            ("iran",          "lng"),
            ("iran",          "energy"),
            ("ormuz",         "lng"),
            ("qatar",         "lng",   "halt"),
            ("qatar",         "lng",   "stop"),
            ("energy stock",  "iran"),
            ("argentina",     "lng",   "contract"),
            ("argentina",     "lng",   "export"),
            ("argentina",     "flng"),
            ("sesa",          "lng"),
            ("sesa",          "contract"),
            ("sesa",          "offtake"),
            ("sesa",          "signs"),
            ("southern energy", "flng"),
            # v6.3 — SEFE es el comprador del contrato Argentina LNG
            # "Germany's SEFE nails down 8-year LNG offtake" caía a ruido
            ("sefe",          "lng"),
            ("sefe",          "argentina"),
            ("flng",          "fid"),
            ("flng",          "charter"),
            ("gimi",          "first cargo"),
            ("gimi",          "operational"),
            ("gimi",          "commercial"),
            ("golar",         "new contract"),
            ("golar",         "loi"),
            ("golar",         "letter of intent"),
            ("golar",         "award"),
            ("golar",         "upside"),
            ("glng",          "entry"),
            ("golar",         "bull",  "case"),
            ("golar",         "bull",  "change"),
            ("glng",          "could", "change"),
            # v6 — cuarta unidad FLNG: catalizador pendiente de FID
            # Captura noticias sobre decisión de inversión o contrato de la 4ª unidad
            ("golar",         "fourth", "flng"),
            ("golar",         "fourth", "unit"),
            ("golar",         "4th",    "flng"),
        ],

        "keywords_cat2_hitos": {
            ("gimi",  "first cargo"):         (1, "Gimi — Operacion comercial plena",          "Confirmar y actualizar hito 1 a true"),
            ("gimi",  "operational"):         (1, "Gimi — Operacion comercial plena",          "Confirmar y actualizar hito 1 a true"),
            ("gimi",  "commercial"):          (1, "Gimi — Operacion comercial plena",          "Confirmar y actualizar hito 1 a true"),
            ("sesa",  "contract"):            (3, "MKII Argentina — Construccion on-schedule", "Confirmar progreso — actualizar hito 3"),
            ("sesa",  "offtake"):             (3, "MKII Argentina — Construccion on-schedule", "Confirmar progreso — actualizar hito 3"),
            ("sesa",  "signs"):               (3, "MKII Argentina — Construccion on-schedule", "Confirmar progreso — actualizar hito 3"),
            # v6.3
            ("sefe",  "lng"):                 (3, "MKII Argentina — Construccion on-schedule", "SEFE es comprador Argentina LNG — confirmar relación con MKII/Golar"),
            ("sefe",  "argentina"):           (3, "MKII Argentina — Construccion on-schedule", "SEFE es comprador Argentina LNG — confirmar relación con MKII/Golar"),
            ("argentina", "lng", "contract"): (3, "MKII Argentina — Construccion on-schedule", "Confirmar progreso — actualizar hito 3"),
            ("argentina", "flng"):            (3, "MKII Argentina — Construccion on-schedule", "Confirmar progreso — actualizar hito 3"),
            ("iran",  "energy"):              (None, "Catalizador macro LNG — Hormuz/Iran",    "Evaluar ampliacion tramo 2 en $41-43"),
            ("iran",  "lng"):                 (None, "Catalizador macro LNG — Hormuz/Iran",    "Evaluar ampliacion tramo 2 en $41-43"),
            ("hormuz","lng"):                 (None, "Catalizador macro LNG — Hormuz",         "Evaluar ampliacion tramo 2 en $41-43"),
            ("energy stock", "iran"):         (None, "Catalizador macro LNG — Iran",           "Evaluar ampliacion tramo 2 en $41-43"),
            ("flng",  "fid"):                 (None, "Mercado FLNG validado — competidor",     "Seguimiento — refuerza tesis"),
            ("flng",  "charter"):             (None, "Mercado FLNG validado — competidor",     "Seguimiento — refuerza tesis"),
            ("golar", "bull",  "change"):     (None, "Bull case Golar actualizado",            "Leer — puede afectar precio objetivo"),
            ("glng",  "could", "change"):     (None, "Bull case Golar actualizado",            "Leer — puede afectar precio objetivo"),
            # v6
            ("golar", "fourth", "flng"):      (None, "4a unidad FLNG — decision pendiente",    "Leer — si FID confirmado actualizar tesis"),
            ("golar", "fourth", "unit"):      (None, "4a unidad FLNG — decision pendiente",    "Leer — si FID confirmado actualizar tesis"),
            ("golar", "4th",    "flng"):      (None, "4a unidad FLNG — decision pendiente",    "Leer — si FID confirmado actualizar tesis"),
        },

        # ── CAT 3 · CONFIRMACIÓN ──────────────────────────────────────────
        # Criterio: earnings, dividendos, upgrades de analistas y movimientos
        # de precio con causa identificada. Seguimiento del estado de la tesis.
        #
        # ELIMINADAS en v6 por generar ruido sin valor operativo:
        #   ("golar", "million")   — capturaba cualquier mención de dinero
        #   ("golar", "position")  — demasiado genérico
        #   ("glng",  "position")  — demasiado genérico
        #   ("glng",  "movement")  — ruido cuantitativo puro
        #   ("glng",  "signal")    — ruido cuantitativo puro
        #
        # AÑADIDAS en v6 desde auditoría 15-mar-2026:
        #   ("golar", "margin")         — análisis fundamental relevante
        #   ("glng",  "trading down")   — movimiento precio con causa
        #   ("glng",  "falling")        — movimiento precio con causa
        #
        # REFINADAS en v6.1:
        #   ("golar", "buy") → ("golar", "buy", "rating") + ("golar", "buy", "upgrade")
        #     Motivo: "buy" genérico capturaba compras institucionales que deben ir a CAT4.
        #     Solo nos interesa "buy" como rating de analista, no como verbo de compra.
        #
        #   ("golar", "investor") → ("golar", "investor", "day") + ("golar", "investor", "presenta")
        #     Motivo: "investor" genérico capturaba posiciones de fondos pequeños irrelevantes.
        #     Por diseño: fondos relevantes → CAT4 · fondos irrelevantes → RUIDO.
        #     Solo nos interesa "investor" en contexto de evento corporativo (Investor Day).
        "keywords_cat3": [
            ("golar",  "earnings"),
            ("golar",  "results"),
            # v6.1 — refinado: "beat" sola captura "MarketBeat" en títulos institucionales
            # Añadida tercera keyword para anclar a contexto de resultados financieros
            ("golar", "beat",  "earnings"),
            ("golar", "beat",  "forecast"),
            ("golar", "beat",  "estimate"),
            ("golar", "beat",  "guidance"),
            ("glng",   "results"),
            ("golar",  "ebitda"),
            ("golar",  "fcf"),
            ("golar",  "dividend"),
            ("glng",   "dividend"),
            ("golar",  "conviction"),
            ("golar",  "upgrade"),
            ("golar",  "price target"),
            # v6.1 — refinado: solo rating de analista, no compra institucional
            ("golar",  "buy", "rating"),
            ("golar",  "buy", "upgrade"),
            ("hilli",  "cargo"),
            ("hilli",  "production"),
            ("hilli",  "uptime"),
            # v6.1 — refinado: solo evento corporativo, no posición de fondo
            ("golar",  "investor", "day"),
            ("golar",  "investor", "presenta"),
            # ("golar", "lng", "stock") — eliminada en v6.1: capturaba $GLNG al final
            # de títulos institucionales (Aventail, Clearline). Movimientos de precio
            # ya cubiertos por ("glng","down","today"), ("glng","trading down"), ("glng","falling")
            # ("glng", "stock") — eliminada por el mismo motivo
            ("glng",   "down", "today"),
            ("golar",  "rating"),
            ("glng",   "rating"),
            ("glng",   "setup"),
            # v6
            ("golar",  "margin"),
            ("glng",   "trading down"),
            ("glng",   "falling"),
        ],

        "keywords_cat3_hitos": {
            ("golar", "earnings"):           (2, "FCF guidance 2025 confirmado",       "Leer earnings — actualizar hito 2 si FCF >400M"),
            ("golar", "results"):            (2, "FCF guidance 2025 confirmado",       "Leer results — actualizar hito 2 si FCF >400M"),
            # v6.1 — beat refinado: evita match con "MarketBeat" en títulos institucionales
            ("golar", "beat",  "earnings"):  (2, "FCF guidance 2025 confirmado",       "Leer — si supera earnings actualizar hito 2"),
            ("golar", "beat",  "forecast"):  (2, "FCF guidance 2025 confirmado",       "Leer — si supera forecast actualizar hito 2"),
            ("golar", "beat",  "estimate"):  (2, "FCF guidance 2025 confirmado",       "Leer — si supera estimate actualizar hito 2"),
            ("golar", "beat",  "guidance"):  (2, "FCF guidance 2025 confirmado",       "Leer — si supera guidance actualizar hito 2"),
            ("glng",  "results"):            (2, "FCF guidance 2025 confirmado",       "Leer results — actualizar hito 2 si FCF >400M"),
            ("golar", "ebitda"):             (2, "FCF guidance 2025 confirmado",       "Leer — actualizar hito 2 si datos confirman"),
            ("golar", "fcf"):                (2, "FCF guidance 2025 confirmado",       "Leer — actualizar hito 2 si FCF >400M"),
            ("golar", "dividend"):           (4, "Dividendo o buybacks iniciado",      "Actualizar hito 4 → estado:true · fecha:hoy"),
            ("glng",  "dividend"):           (4, "Dividendo o buybacks iniciado",      "Actualizar hito 4 → estado:true · fecha:hoy"),
            ("hilli", "cargo"):              (7, "Hilli — Contrato Perenco vigente",   "Confirma vigencia — hito 7 sigue en null"),
            ("hilli", "production"):         (7, "Hilli — Contrato Perenco vigente",   "Confirma vigencia — hito 7 sigue en null"),
            ("hilli", "uptime"):             (7, "Hilli — Contrato Perenco vigente",   "Confirma vigencia — hito 7 sigue en null"),
            ("golar", "conviction"):         (None, "Analista confirma conviction",    "Sin accion requerida"),
            ("golar", "upgrade"):            (None, "Upgrade analista",                "Sin accion requerida"),
            ("golar", "price target"):       (None, "Cambio precio objetivo",          "Sin accion requerida"),
            # v6.1
            ("golar", "buy", "rating"):      (None, "Rating Buy de analista",          "Sin accion requerida"),
            ("golar", "buy", "upgrade"):     (None, "Upgrade a Buy de analista",       "Sin accion requerida"),
            ("golar", "investor", "day"):    (None, "Investor Day corporativo",        "Leer — puede incluir guidance nuevo"),
            ("golar", "investor", "presenta"):(None,"Presentacion a inversores",       "Leer — puede incluir guidance nuevo"),
            # ("golar", "lng", "stock") — eliminada en v6.1
            # ("glng",  "stock")        — eliminada en v6.1
            ("glng",  "down", "today"):      (None, "Caida precio hoy — leer causa",   "Leer — verificar si hay noticia detras"),
            ("glng",  "rating"):             (None, "Rating tecnico",                  "Sin accion requerida"),
            ("glng",  "setup"):              (None, "Setup tecnico",                   "Sin accion requerida"),
            # v6
            ("golar", "margin"):             (None, "Analisis margen fundamental",     "Leer — puede afectar tesis FCF"),
            ("glng",  "trading down"):       (None, "Caida precio — leer causa",       "Leer — verificar si hay noticia detras"),
            ("glng",  "falling"):            (None, "Caida precio — leer causa",       "Leer — verificar si hay noticia detras"),
        },

        # ── CAT 4 · MANOS FUERTES ─────────────────────────────────────────
        # PASO 1 DEL FLUJO — actualizar cada trimestre con Form 13F de SEC EDGAR.
        # URL de consulta: https://www.sec.gov/cgi-bin/browse-edgar
        #                  ?action=getcompany&type=13F&dateb=&owner=include&count=10
        #
        # Criterios de inclusión en lista blanca:
        #   · Posición >1% del float (significativa para el precio)
        #   · Movimiento reciente >$50M (señal de convicción)
        #   · Insider (cualquier tamaño — siempre relevante)
        #
        # Última actualización: 15-mar-2026
        # Fuente: SEC EDGAR Form 13F + MarketBeat institutional ownership
        #
        # Formato: "clave_busqueda": (nombre_completo, umbral_usd, razon)
        #   umbral_usd = 0   → cualquier movimiento es relevante
        #   umbral_usd = N   → solo notificar si posición supera N USD
        "manos_fuertes": {
            "rubric":        ("Rubric Capital Management",  0,          "Mayor accionista ~9% · $378M"),
            "pointstate":    ("PointState Capital",         0,          "Aumento 19% Q4 2025 · $146M"),
            "t. rowe":       ("T. Rowe Price",              0,          "Entrada masiva +253% Q4 2025 · $85M"),
            "cartenna":      ("Cartenna Capital",           0,          "Top 10 accionista · $77M"),
            "morgan stanley":("Morgan Stanley",             50_000_000, "Institucional sistémico · $78M"),
        },

        # Umbral para fondos NO en lista blanca.
        # Captura entradas nuevas significativas sin ruido de posiciones menores.
        # Fondos como Aventail ($3.15M) o Clearline ($5M) quedan filtrados.
        "manos_fuertes_umbral_usd": 50_000_000,

        "macro_config": None,
    },


    # =========================================================================
    # LULU — Lululemon Athletica
    # =========================================================================
    # Tesis: "Riesgo asimétrico con catalizador incierto y ventana temporal
    #         definida" — elaborada 18-mar-2026 · precio entrada $159.27
    #
    # DISEÑO DELIBERADO — solo 3 alertas (principio francotirador):
    #   La tesis depende de UN evento binario con fecha aproximada conocida:
    #   la junta de accionistas 2026 y la campaña de Chip Wilson sobre el board.
    #   Las métricas continuas (Google Trends, app rankings, wallet share) son
    #   instrumentos de diagnóstico — no son accionables en el horizonte de la
    #   tesis y generarían ruido que compite con las señales que importan.
    #
    # ALERTA 1 — CAT1: catalizador binario Wilson/board
    #   Si Wilson gana asientos → rerating potencial violento al alza
    #   Si Wilson pierde/retira → caso base declive gestionado $145-165
    #
    # ALERTA 2 — CAT1: invalidación del suelo financiero
    #   Margen bruto <52%, comp. sales <-5% dos trimestres, caja <$800M
    #   Si se activa → asimetría de la tesis se deteriora
    #
    # ALERTA 3 — CAT2/CAT3: confirmación de recuperación
    #   Comp. sales Américas >+2% por primera vez, nuevo CEO externo turnaround,
    #   precio sostenido >$280 durante 10 días
    #
    # CONDICIÓN DE CIERRE AUTOMÁTICO:
    #   Precio >$280 sostenido 10d → tesis realizada
    #   Precio <$120 con Alerta 2 activa → tesis invalidada
    #   24 meses sin Alerta 1 (antes del 18-mar-2028) → ventana cerrada
    #
    # manos_fuertes: Chip Wilson como insider prioritario (cualquier movimiento)
    # sec_cik: LULU cotiza NASDAQ — CIK 0001397187
    # macro_config: None — la tesis no depende de macro sectorial
    # =========================================================================
    "LULU": {
        "nombre":         "Lululemon Athletica",
        "activo":         True,
        "precio_entrada": 159.27,
        "moneda":         "USD",
        "sec_cik":        "0001397187",

        # Queries Google News — diseñadas para cubrir las 3 alertas:
        # · Wilson/board (catalizador binario, prioridad absoluta)
        # · Earnings/margen/comp sales (invalidación del suelo)
        # · Turnaround/CEO/recuperación (confirmación de tesis)
        # · Competidores clave (Alo, Vuori) — solo para señales de cuota
        # Máximo 8 queries — sin queries genéricas de precio o sector
        "gnews_queries": [
            "Chip Wilson lululemon",
            "lululemon board directors 2026",
            "lululemon proxy shareholder",
            "lululemon earnings comparable sales",
            "lululemon CEO turnaround",
            "lululemon Americas recovery",
            "Alo Yoga lululemon",
            "Vuori lululemon",
        ],

        # ── CAT 1 · INVALIDACIÓN DE TESIS ────────────────────────────────
        # Alerta 1a — Catalizador binario negativo: Wilson pierde/retira
        # Alerta 1b — Suelo financiero roto: margen, ventas, caja
        # Ser conservador: mejor revisar de más que perder señal real.
        "keywords_cat1": [
            # Wilson/board — señal negativa (catalizador no materializado)
            ("wilson",       "withdraw"),
            ("wilson",       "drops",       "bid"),
            ("wilson",       "loses",       "vote"),
            ("wilson",       "settlement",  "lululemon"),
            ("lululemon",    "proxy",       "defeat"),
            ("lululemon",    "board",       "rejects",  "wilson"),
            # Suelo financiero — invalidación de tesis
            ("lululemon",    "gross margin",  "decline"),
            ("lululemon",    "margin",        "below"),
            ("lululemon",    "comparable",    "decline",  "fifth"),
            ("lululemon",    "comparable",    "decline",  "sixth"),
            ("lululemon",    "comparable",    "decline",  "seventh"),
            ("lululemon",    "guidance",      "cut"),
            ("lululemon",    "guidance",      "lower"),
            ("lululemon",    "guidance",      "weak"),
            ("lululemon",    "weak",          "guidance"),
            ("lululemon",    "outlook",       "disappoint"),
            ("lululemon",    "outlook",       "weak"),
            ("lululemon",    "cash",          "burn"),
            # Amenaza competitiva estructural
            ("lululemon",    "market share",  "loss"),
            ("lululemon",    "closing",       "stores"),
            # v6.12 — análisis negativos post-earnings
            # Criterio: títulos de opinión que mencionan deterioro de márgenes,
            # presión arancelaria o outlook débil son CAT1 aunque sean op-eds.
            # Preferir falso positivo a perder señal — principio de robustez.
            ("lululemon",    "tariff"),
            ("lululemon",    "margin",        "pressure"),
            ("lululemon",    "muted",         "outlook"),
            ("lululemon",    "muted",         "growth"),
            ("lululemon",    "softer",        "outlook"),
            ("lululemon",    "weaker",        "outlook"),
            # v6.11 — ELIMINADO: ("lululemon", "sec", "filing") generaba 10 falsos
            # positivos CAT1 por ejecución. Auditoría de 30 8-K confirmó que todos
            # los eventos reales de invalidación (earnings, board, guidance) ya están
            # cubiertos por keywords específicas + Google News. Un 8-K genérico sin
            # cobertura de prensa paralela es por definición un filing rutinario.
        ],

        "keywords_cat1_hitos": {
            ("wilson",       "withdraw"):                    (1, "Wilson/board — catalizador binario",     "estado:false — Wilson retirado"),
            ("wilson",       "drops",      "bid"):           (1, "Wilson/board — catalizador binario",     "estado:false — Wilson retirado"),
            ("wilson",       "loses",      "vote"):          (1, "Wilson/board — catalizador binario",     "estado:false — Wilson pierde votación"),
            ("wilson",       "settlement", "lululemon"):     (1, "Wilson/board — catalizador binario",     "Leer — evaluar si acuerdo incluye cambios reales"),
            ("lululemon",    "proxy",      "defeat"):        (1, "Wilson/board — catalizador binario",     "estado:false — proxy battle perdido"),
            ("lululemon",    "board",      "rejects", "wilson"): (1, "Wilson/board — catalizador binario", "estado:false — board rechaza candidatos"),
            ("lululemon",    "gross margin", "decline"):     (2, "Suelo financiero — margen bruto",        "Verificar si cae bajo 52% — estado:false si confirma"),
            ("lululemon",    "margin",     "below"):         (2, "Suelo financiero — margen bruto",        "Verificar nivel exacto — umbral crítico 52%"),
            ("lululemon",    "guidance",   "cut"):           (2, "Suelo financiero — guidance",            "estado:false si BPA forward cae bajo $9"),
            ("lululemon",    "guidance",   "lower"):         (2, "Suelo financiero — guidance",            "Verificar magnitud — umbral crítico $9 BPA"),
            ("lululemon",    "guidance",   "weak"):          (2, "Suelo financiero — guidance",            "Verificar magnitud — umbral crítico $9 BPA"),
            ("lululemon",    "weak",       "guidance"):      (2, "Suelo financiero — guidance",            "Verificar magnitud — umbral crítico $9 BPA"),
            ("lululemon",    "outlook",    "disappoint"):    (2, "Suelo financiero — outlook",             "Leer — evaluar si cambia BPA forward bajo $9"),
            ("lululemon",    "outlook",    "weak"):          (2, "Suelo financiero — outlook",             "Leer — evaluar si cambia BPA forward bajo $9"),
            ("lululemon",    "cash",       "burn"):          (2, "Suelo financiero — caja",                "estado:false si caja cae bajo $800M"),
            ("lululemon",    "market share", "loss"):        (2, "Suelo financiero — cuota",               "Leer — verificar si dato cuantificado"),
            ("lululemon",    "comparable", "decline", "fifth"):  (2, "Suelo financiero — comp sales",     "7mo trimestre negativo — revisar tesis"),
            ("lululemon",    "comparable", "decline", "sixth"):  (2, "Suelo financiero — comp sales",     "8vo trimestre negativo — revisar tesis"),
            ("lululemon",    "comparable", "decline", "seventh"): (2, "Suelo financiero — comp sales",    "9no trimestre negativo — tesis en riesgo"),
            ("lululemon",    "closing",    "stores"):        (2, "Suelo financiero — red DTC",             "Verificar escala — cierre masivo invalida tesis DTC"),
            # v6.12 — análisis negativos post-earnings
            ("lululemon",    "tariff"):                        (2, "Suelo financiero — presión arancelaria",  "Cuantificar impacto en margen bruto — umbral crítico 52%"),
            ("lululemon",    "margin",     "pressure"):        (2, "Suelo financiero — margen bajo presión",  "Verificar si dato es nuevo o referencia a Q4 — umbral 52%"),
            ("lululemon",    "muted",      "outlook"):         (2, "Suelo financiero — outlook débil",        "Leer — evaluar si cambia BPA forward bajo $9"),
            ("lululemon",    "muted",      "growth"):          (2, "Suelo financiero — crecimiento débil",    "Leer — verificar si es guidance nueva o análisis de consenso"),
            ("lululemon",    "softer",     "outlook"):         (2, "Suelo financiero — outlook suavizado",    "Leer — evaluar magnitud vs umbral $9 BPA"),
            ("lululemon",    "weaker",     "outlook"):         (2, "Suelo financiero — outlook débil",        "Leer — evaluar si cambia BPA forward bajo $9"),
            # v6.11 — eliminado: ("lululemon", "sec", "filing") → ver keywords_cat1
        },

        # ── CAT 2 · CATALIZADORES ─────────────────────────────────────────
        # Alerta 1 positiva: Wilson gana asientos en el board
        # Eventos que aceleran la tesis o justifican ampliar posición
        "keywords_cat2": [
            # Wilson/board — señal positiva (catalizador materializado)
            ("wilson",       "wins",       "board"),
            ("wilson",       "elected",    "director"),
            ("wilson",       "board",      "seat"),
            ("lululemon",    "new",        "director",  "wilson"),
            ("lululemon",    "board",      "change"),
            # Nuevo CEO con perfil turnaround
            # v6.4: refinado para evitar match con "CEO search drags on" y "CEO void"
            # Esos titulares deben ir a CAT2 hito 1 (board) o CAT3 hito 1 (CEO search)
            # Solo capturar aquí cuando hay nombramiento explícito
            ("lululemon",    "appoints",   "ceo"),
            ("lululemon",    "names",      "ceo"),
            ("lululemon",    "hires",      "ceo"),
            ("lululemon",    "new",        "ceo",        "named"),
            ("lululemon",    "new",        "ceo",        "appoint"),
            # Cambios de board — cualquier director nuevo es señal
            # v6.3: añadido tras auditoría — "Chip Bergh Joins lululemon Board" caía a ruido
            ("lululemon",    "joins",      "board"),
            ("lululemon",    "new",        "director"),
            ("lululemon",    "tapped",     "board"),
            ("lululemon",    "board",      "appoints"),
            # Activismo institucional externo
            # v6.3: añadido tras auditoría — "activist investor eyeing turnaround" caía a ruido
            ("lululemon",    "activist",   "investor"),
            ("lululemon",    "activist",   "turnaround"),
            # Recuperación de Américas
            ("lululemon",    "americas",   "growth"),
            ("lululemon",    "comparable", "positive"),
            ("lululemon",    "same store", "growth"),
            # Catalizadores de producto/marca
            ("lululemon",    "footwear",   "launch"),
            ("lululemon",    "gen z",      "brand"),
            ("lululemon",    "strategic",  "review"),
            ("lululemon",    "buyback",    "accelerat"),
        ],

        "keywords_cat2_hitos": {
            ("wilson",       "wins",      "board"):          (1, "Wilson/board — catalizador binario",     "estado:true — Wilson gana asientos · evaluar rerating"),
            ("wilson",       "elected",   "director"):       (1, "Wilson/board — catalizador binario",     "estado:true — Wilson elegido director"),
            ("wilson",       "board",     "seat"):           (1, "Wilson/board — catalizador binario",     "Confirmar número de asientos — actualizar hito 1"),
            ("lululemon",    "new",       "director", "wilson"): (1, "Wilson/board — catalizador binario", "estado:true — confirmar con fuente primaria"),
            ("lululemon",    "board",     "change"):         (1, "Wilson/board — catalizador binario",     "Leer — evaluar si el cambio incluye mandato claro"),
            # v6.4 — CEO nombramiento explícito
            ("lululemon",    "appoints",  "ceo"):            (3, "Nuevo CEO externo con mandato turnaround", "Confirmar perfil — interno vs externo es clave"),
            ("lululemon",    "names",     "ceo"):             (3, "Nuevo CEO externo con mandato turnaround", "Confirmar perfil — interno vs externo es clave"),
            ("lululemon",    "hires",     "ceo"):             (3, "Nuevo CEO externo con mandato turnaround", "Confirmar perfil — interno vs externo es clave"),
            ("lululemon",    "new",       "ceo",    "named"): (3, "Nuevo CEO externo con mandato turnaround", "Confirmar perfil — interno vs externo es clave"),
            ("lululemon",    "new",       "ceo",   "appoint"): (3, "Nuevo CEO externo con mandato turnaround", "Confirmar perfil — interno vs externo es clave"),
            # v6.3 — board changes
            ("lululemon",    "joins",     "board"):          (1, "Wilson/board — cambio composición",       "Leer — evaluar si el nuevo director es candidato Wilson o del board actual"),
            ("lululemon",    "new",       "director"):       (1, "Wilson/board — cambio composición",       "Leer — evaluar alineación con tesis catalizador"),
            ("lululemon",    "tapped",    "board"):          (1, "Wilson/board — cambio composición",       "Leer — evaluar si es candidato Wilson o del board actual"),
            ("lululemon",    "board",     "appoints"):       (1, "Wilson/board — cambio composición",       "Leer — evaluar alineación con tesis catalizador"),
            # v6.3 — activismo institucional
            ("lululemon",    "activist",  "investor"):       (None, "Activismo institucional externo",      "Leer — identificar inversor y demandas — puede reforzar tesis Wilson"),
            ("lululemon",    "activist",  "turnaround"):     (None, "Activismo institucional externo",      "Leer — identificar inversor y demandas"),
            ("lululemon",    "americas",  "growth"):         (4, "Comp. sales Américas positivas >+2%",     "Confirmar magnitud — umbral catalizador es +2%"),
            ("lululemon",    "comparable","positive"):       (4, "Comp. sales Américas positivas >+2%",     "Primer trimestre positivo — posible punto de giro"),
            ("lululemon",    "same store","growth"):         (4, "Comp. sales Américas positivas >+2%",     "Confirmar magnitud — umbral catalizador es +2%"),
            ("lululemon",    "footwear",  "launch"):         (None, "Catalizador producto — footwear",      "Leer — evaluar si genera heat orgánico Gen Z"),
            ("lululemon",    "gen z",     "brand"):          (None, "Catalizador marca — Gen Z",            "Leer — señal de recuperación cultural"),
            ("lululemon",    "strategic", "review"):         (None, "Revisión estratégica corporativa",     "Leer — puede incluir cambios de modelo o M&A"),
            ("lululemon",    "buyback",   "accelerat"):      (None, "Buyback acelerado",                    "Señal de confianza del management — sin acción requerida"),
        },

        # ── CAT 3 · CONFIRMACIÓN ──────────────────────────────────────────
        # Earnings, márgenes, dividendos — seguimiento del estado de la tesis.
        # No cambian ninguna decisión pero actualizan convicción y estado del JSON.
        "keywords_cat3": [
            ("lululemon",    "earnings"),
            ("lululemon",    "results"),
            ("lululemon",    "beat",       "earnings"),
            ("lululemon",    "beat",       "estimate"),
            ("lululemon",    "ebitda"),
            ("lululemon",    "gross margin"),
            ("lululemon",    "comparable", "sales"),
            ("lululemon",    "americas",   "revenue"),
            ("lululemon",    "china",      "growth"),
            ("lululemon",    "upgrade"),
            ("lululemon",    "price target"),
            ("lululemon",    "buy",        "rating"),
            ("lulu",         "dividend"),
            ("lululemon",    "shareholder", "meeting"),
            ("lululemon",    "annual",      "meeting"),
            # Chip Wilson — movimientos sin llegar a CAT1/CAT2
            ("wilson",       "lululemon",   "stake"),
            ("wilson",       "lululemon",   "letter"),
            ("chip wilson",  "lululemon"),
            # v6.3 — cobertura proxy fight que caía a ruido en auditoría
            # "Lululemon Scrambles to Revive Yoga Pants Empire Amid Fight With Founder"
            # "Inside Lululemon's founder's war with the board"
            # "Lululemon Founder Ups Activism, Calling Board's Response 'Weak'"
            # "Lululemon founder says board's response 'weak and insufficient'"
            ("lululemon",    "founder",     "war"),
            ("lululemon",    "founder",     "fight"),
            ("lululemon",    "founder",     "activism"),
            # v6.4: añadidas para capturar "founder challenges board" y "founder poses questions"
            ("lululemon",    "founder",     "challenge"),
            ("lululemon",    "founder",     "question"),
            ("lululemon",    "board",       "weak"),
            ("lululemon",    "response",    "weak"),
            ("lululemon",    "response",    "insufficient"),
            ("lululemon",    "scrambles",   "revive"),
            ("lululemon",    "proxy",       "fight"),
            ("lululemon",    "proxy",       "battle"),
            ("lululemon",    "ceo",         "void"),
            ("lululemon",    "ceo",         "vacancy"),
            ("lululemon",    "ceo",         "search"),
            # v6.5: "Wilson puts lululemon CEO candidates on notice" caía a ruido
            # El titular usa "Wilson" sin "Chip" — no matchaba ("chip wilson","lululemon")
            ("wilson",       "lululemon",   "notice"),
            ("wilson",       "lululemon",   "ceo"),
            ("wilson",       "lululemon",   "candidate"),
        ],

        "keywords_cat3_hitos": {
            # ── HITO 1 · Wilson/board — PRIMERO en el dict (mayor prioridad de match)
            # v6.4: movidos al inicio para evitar que ("lululemon","earnings") gane
            # en titulares como "Wilson Takes Shots Ahead of Earnings" o
            # "founder challenges board ahead of earnings call".
            # encontrar_hito() devuelve el PRIMER match — el orden es crítico.
            ("chip wilson",  "lululemon"):             (1, "Wilson/board — mención general",           "Leer — cualquier movimiento de Wilson es relevante"),
            ("wilson",       "lululemon",   "stake"):  (1, "Wilson/board — movimiento insider",        "Verificar dirección — compra refuerza presión · venta debilita"),
            ("wilson",       "lululemon",   "letter"): (1, "Wilson/board — comunicación pública",      "Leer carta — puede incluir demandas concretas al board"),
            ("lululemon",    "founder",     "war"):    (1, "Wilson/board — proxy fight activo",        "Leer — seguimiento campaña Wilson"),
            ("lululemon",    "founder",     "fight"):  (1, "Wilson/board — proxy fight activo",        "Leer — seguimiento campaña Wilson"),
            ("lululemon",    "founder",     "activism"): (1, "Wilson/board — proxy fight activo",      "Leer — seguimiento campaña Wilson"),
            ("lululemon",    "founder",     "challenge"): (1, "Wilson/board — proxy fight activo",     "Leer — founder desafiando board"),
            ("lululemon",    "founder",     "question"): (1, "Wilson/board — proxy fight activo",      "Leer — founder cuestionando liderazgo"),
            ("lululemon",    "board",       "weak"):   (1, "Wilson/board — respuesta board débil",     "Leer — respuesta débil del board refuerza posición Wilson"),
            ("lululemon",    "response",    "weak"):   (1, "Wilson/board — respuesta board débil",     "Leer — respuesta débil del board refuerza posición Wilson"),
            ("lululemon",    "response",    "insufficient"): (1, "Wilson/board — respuesta insuficiente", "Leer — puede escalar la presión"),
            ("lululemon",    "scrambles",   "revive"): (1, "Wilson/board — contexto proxy fight",      "Leer — narrativa de declive que refuerza argumentos Wilson"),
            ("lululemon",    "proxy",       "fight"):  (1, "Wilson/board — proxy fight activo",        "Leer — seguimiento estado de la campaña"),
            ("lululemon",    "proxy",       "battle"): (1, "Wilson/board — proxy fight activo",        "Leer — seguimiento estado de la campaña"),
            ("lululemon",    "ceo",         "void"):   (1, "Wilson/board — vacío de liderazgo",        "Leer — presión adicional sobre board por CEO search"),
            ("lululemon",    "ceo",         "vacancy"): (1, "Wilson/board — vacío de liderazgo",       "Leer — presión adicional sobre board por CEO search"),
            ("lululemon",    "ceo",         "search"): (1, "Wilson/board — CEO search activo",         "Leer — cualquier avance en el CEO search es relevante para la tesis"),
            # v6.5 — Wilson sin "Chip" en titular
            ("wilson",       "lululemon",   "notice"):    (1, "Wilson/board — aviso público",           "Leer — Wilson poniendo a alguien on notice es señal de escalada"),
            ("wilson",       "lululemon",   "ceo"):       (1, "Wilson/board — Wilson y CEO search",     "Leer — Wilson involucrándose en CEO search es catalizador potencial"),
            ("wilson",       "lululemon",   "candidate"): (1, "Wilson/board — candidatos CEO",          "Leer — Wilson evaluando candidatos es señal de influencia creciente"),
            ("lululemon",    "shareholder", "meeting"): (1, "Wilson/board — junta accionistas",        "Anotar fecha y agenda — hito 1 depende de este evento"),
            ("lululemon",    "annual",      "meeting"): (1, "Wilson/board — junta accionistas",        "Anotar fecha y agenda — hito 1 depende de este evento"),
            # ── HITO 2 · Suelo financiero
            ("lululemon",    "gross margin"):          (2, "Suelo financiero — margen bruto",          "Confirmar nivel — umbral crítico 52%"),
            # ── HITO 4 · Comp. sales
            ("lululemon",    "comparable", "sales"):   (4, "Comp. sales Américas — seguimiento",       "Anotar valor exacto — umbral catalizador +2%"),
            ("lululemon",    "americas",   "revenue"): (4, "Comp. sales Américas — seguimiento",       "Anotar evolución — indicador de recuperación"),
            # ── HITO 5 · Earnings — AL FINAL, después de Wilson/board
            # Titulares con "earnings" que también mencionan Wilson/board
            # ya habrán matchado arriba. Solo llegan aquí los earnings puros.
            ("lululemon",    "earnings"):              (5, "Earnings Q — revisión trimestral",         "Extraer: comp sales Américas, margen bruto, guidance"),
            ("lululemon",    "results"):               (5, "Earnings Q — revisión trimestral",         "Extraer: comp sales Américas, margen bruto, guidance"),
            ("lululemon",    "beat",   "earnings"):    (5, "Earnings Q — revisión trimestral",         "Beat confirmado — verificar si mejora guidance"),
            ("lululemon",    "beat",   "estimate"):    (5, "Earnings Q — revisión trimestral",         "Beat confirmado — verificar si mejora guidance"),
            ("lululemon",    "ebitda"):                (5, "Earnings Q — revisión trimestral",         "Leer — umbral vigilancia EBITDA margin 28%"),
            # ── HITO 6 · China
            ("lululemon",    "china",      "growth"):  (6, "China — motor de crecimiento",             "Confirmar si sigue >+15% — palanca de mix"),
            # ── Sin hito — analistas
            ("lululemon",    "upgrade"):               (None, "Upgrade analista",                      "Sin acción requerida"),
            ("lululemon",    "price target"):          (None, "Cambio precio objetivo",                "Sin acción requerida"),
            ("lululemon",    "buy",   "rating"):       (None, "Rating Buy de analista",                "Sin acción requerida"),
            ("lulu",         "dividend"):              (None, "Dividendo — LULU no paga actualmente",  "Si anuncia dividendo → señal de madurez · leer"),
        },

        # ── CAT 4 · MANOS FUERTES ─────────────────────────────────────────
        # Última actualización: 18-mar-2026
        # Fuente: MarketBeat institutional ownership + SEC EDGAR Form 13F
        #
        # PASO 1 DEL FLUJO — actualizar cada trimestre con Form 13F de SEC EDGAR.
        # URL: https://www.sec.gov/cgi-bin/browse-edgar
        #      ?action=getcompany&type=13F&CIK=0001397187
        #
        # DISEÑO DELIBERADO v6.3: Chip Wilson eliminado de esta lista.
        # Wilson es activismo del fundador — no es movimiento de fondo institucional.
        # CAT4 es para compras/ventas de fondos. Wilson se cubre desde CAT3 hito 1
        # con keywords específicas de proxy fight y campaña de board.
        # Mantener Wilson aquí generaba 11 noticias en CAT4 que pertenecen a CAT3.
        "manos_fuertes": {
            "blackrock":     ("BlackRock",                       50_000_000, "Mayor institucional pasivo ~9% float"),
            "vanguard":      ("Vanguard Group",                  50_000_000, "Institucional pasivo ~8% float"),
            "fidelity":      ("Fidelity Investments",            50_000_000, "Institucional activo — seguimiento"),
        },

        # Umbral para fondos NO en lista blanca.
        "manos_fuertes_umbral_usd": 50_000_000,

        "macro_config": None,
    },


    # ── PLANTILLA STZ (pendiente activación) ─────────────────────────────
    # Activar cuando se complete el manual operativo de Spirits (Fase 2).
    # manos_fuertes: buscar en EDGAR Form 13F antes de activar.
    # "STZ": {
    #     "nombre": "Constellation Brands", "activo": False,
    #     "precio_entrada": 149.50, "moneda": "USD",
    #     "sec_cik": "0000016160",
    #     "gnews_queries": ["Constellation Brands beer", "STZ stock", "Corona beer tariff"],
    #     "keywords_cat1": [("usmca","tariff","beer"),("constellation","guidance","cut")],
    #     "keywords_cat1_hitos": {},
    #     "keywords_cat2": [("construction","employment"),("constellation","guidance","raise")],
    #     "keywords_cat2_hitos": {},
    #     "keywords_cat3": [("constellation","earnings"),("stz","dividend")],
    #     "keywords_cat3_hitos": {},
    #     "manos_fuertes": {},          # ← rellenar con Form 13F antes de activar
    #     "manos_fuertes_umbral_usd": 50_000_000,
    #     "macro_config": {"tipo":"bls","serie":"CES2000000001",
    #                      "umbral_alerta_baja":8100000,"umbral_catalizador":8280000,
    #                      "descripcion":"BLS Construction Employment"},
    # },

    # ── PLANTILLA RI.PA (pendiente activación) ────────────────────────────
    # Activar cuando se complete el manual operativo de Spirits (Fase 2).
    # manos_fuertes: buscar Amundi, AXA, BNP en EDGAR/Euronext antes de activar.
    # "RIPA": {
    #     "nombre": "Pernod Ricard", "activo": False,
    #     "precio_entrada": 66.50, "moneda": "EUR", "sec_cik": None,
    #     "gnews_queries": ["Pernod Ricard China", "Pernod Ricard earnings", "Martell cognac"],
    #     "keywords_cat1": [("pernod","dividend","cut"),("pernod","fcf","decline")],
    #     "keywords_cat1_hitos": {},
    #     "keywords_cat2": [("china","spirits","recovery"),("india","whisky","tariff")],
    #     "keywords_cat2_hitos": {},
    #     "keywords_cat3": [("pernod","earnings"),("pernod","dividend","confirm")],
    #     "keywords_cat3_hitos": {},
    #     "manos_fuertes": {},          # ← rellenar con datos Euronext antes de activar
    #     "manos_fuertes_umbral_usd": 30_000_000,  # umbral menor por capitalización EUR
    #     "macro_config": None,
    # },


    # =========================================================================
    # PYPL — PayPal Holdings
    # =========================================================================
    # Tesis: "Narrativa rota vs números sólidos" — deep value contrarian.
    # ROIC 23,6% · EV/FCF 7x · Shareholder yield ~28% · valor intrínseco ~$94
    # Precio entrada: $53,31 · Peso cartera: 4,65% · Horizonte: 3-5 años
    #
    # DISEÑO DE KEYWORDS — tres pilares de la tesis:
    #   Pilar 1 (CRÍTICO): Branded checkout — el producto core y su erosión.
    #                      Si cae en términos absolutos 2 trimestres = salida.
    #   Pilar 2 (ALTO):    CEO Enrique Lores — plan estratégico y ejecución.
    #                      Si no reinstura guidance en mayo = señal de alerta.
    #   Pilar 3 (MEDIO):   Venmo + BNPL + PYUSD — diversificación compensatoria.
    #                      Si crece >10% cada uno = confirma tesis alternativa.
    #
    # CONDICIÓN DE SALIDA ÚNICA (ambas simultáneas):
    #   Branded checkout TPV negativo dos trimestres consecutivos
    #   AND Lores sin guidance multianual ni plan concreto en earnings 5-may.
    #   Una sola no es suficiente para salir.
    #
    # CATALIZADOR DE RE-RATING:
    #   Branded checkout vuelve a +4% cualquier trimestre → re-rating 8x→16x
    #   Rumor M&A Stripe se confirma → floor implícito en precio
    #
    # RUIDO A IGNORAR:
    #   Demanda colectiva abril 2026 (habitual tras earnings miss)
    #   Rumor Stripe M&A sin confirmar
    #   Bajadas precio objetivo Goldman/Rothschild (reacción al precio, no análisis)
    #
    # Earnings crítico: 5 mayo 2026 (Q1 2026)
    # manos_fuertes: Form 13F actualizado 18-mar-2026
    # sec_cik: 0001410247
    # =========================================================================
    "PYPL": {
        "nombre":         "PayPal Holdings",
        "activo":         True,
        "precio_entrada": 53.31,
        "moneda":         "USD",
        "sec_cik":        "0001410247",

        # Queries Google News — máximo 8, diseñadas por pilar de tesis
        # · Pilares 1+2: branded checkout, Fastlane, CEO Lores
        # · Pilar 3: Venmo, BNPL, PYUSD, agentic commerce
        # · Gestión de riesgo: demanda, Apple Pay competencia
        "gnews_queries": [
            "PayPal branded checkout transaction margin",
            "PayPal Fastlane checkout",
            "PayPal CEO Lores strategy",
            "PayPal Venmo monetization",
            "PayPal BNPL buy now pay later",
            "PYPL stock earnings",
            "PayPal Apple Pay competition",
            "PayPal Stripe acquisition",
        ],

        # ── CAT 1 · INVALIDACIÓN DE TESIS ────────────────────────────────
        # Condición de salida: branded checkout negativo + CEO sin plan.
        # Se incluyen ambas señales — la salida requiere las dos simultáneas.
        # Señales de moat roto estructural: no ruido temporal.
        "keywords_cat1": [
            # Pilar 1 — Branded checkout en deterioro estructural
            ("paypal",   "branded",     "decline"),
            ("paypal",   "branded",     "negative"),
            ("paypal",   "checkout",    "losing",   "share"),
            ("paypal",   "checkout",    "market share", "loss"),
            ("paypal",   "transaction", "margin",   "decline"),
            ("paypal",   "transaction", "margin",   "negative"),
            ("paypal",   "take rate",   "drop"),
            # Pilar 2 — CEO sin plan / gestión del declive
            ("paypal",   "lores",       "no guidance"),
            ("paypal",   "withdraws",   "guidance"),
            ("paypal",   "guidance",    "withdrawn"),
            ("paypal",   "ceo",         "resign"),
            ("paypal",   "ceo",         "departs"),
            # Riesgo legal material — no la demanda colectiva habitual
            ("paypal",   "sec",         "investigation"),
            # v6.11 — ELIMINADO: ("paypal", "sec", "filing") → ver nota LULU
            ("paypal",   "doj",         "investigation"),
            # Moat estructural roto
            ("paypal",   "apple pay",   "surpass"),
            ("paypal",   "losing",      "merchants"),
            ("paypal",   "merchant",    "migration"),
        ],

        "keywords_cat1_hitos": {
            ("paypal",   "branded",     "decline"):           (1, "Branded checkout — deterioro estructural",   "Verificar si es 2do trimestre consecutivo — umbral de salida"),
            ("paypal",   "branded",     "negative"):          (1, "Branded checkout — crecimiento negativo",    "Si 2T consecutivos negativos + Lores sin plan → SALIR"),
            ("paypal",   "checkout",    "losing",  "share"):  (1, "Branded checkout — pérdida cuota",          "Cuantificar magnitud — umbral crítico es tendencia sostenida"),
            ("paypal",   "checkout",    "market share", "loss"): (1, "Branded checkout — pérdida cuota mercado", "Buscar dato cuantificado — revisar fuente primaria"),
            ("paypal",   "transaction", "margin",  "decline"): (2, "Transaction Margin — caída valor absoluto", "Verificar si es ex-interés y si es 2T consecutivos"),
            ("paypal",   "transaction", "margin",  "negative"): (2, "Transaction Margin — negativo",            "Si 2T consecutivos → activar protocolo salida"),
            ("paypal",   "take rate",   "drop"):               (2, "Take Rate — caída brusca",                  "Verificar bps — umbral alerta >15bps en un trimestre"),
            ("paypal",   "lores",       "no guidance"):        (3, "CEO Lores — sin guidance multianual",       "Si coincide con branded checkout negativo → SALIR"),
            ("paypal",   "withdraws",   "guidance"):           (3, "CEO Lores — guidance retirada definitiva",  "Evaluar contexto — ya ocurrió en Q4 2025"),
            ("paypal",   "guidance",    "withdrawn"):          (3, "CEO Lores — guidance retirada",             "Confirmar si es nueva retirada o referencia a Q4 2025"),
            ("paypal",   "ceo",         "resign"):             (None, "CEO Lores — salida inesperada",          "Cuarto cambio de CEO en 3 años — revisar tesis de gestión"),
            ("paypal",   "ceo",         "departs"):            (None, "CEO Lores — salida inesperada",          "Cuarto cambio de CEO en 3 años — revisar tesis de gestión"),
            ("paypal",   "sec",         "investigation"):      (None, "SEC EDGAR — investigación regulatoria",  "Leer filing completo — puede ser material o rutinario"),
            # v6.11 — eliminado: ("paypal", "sec", "filing") → ver keywords_cat1
            ("paypal",   "doj",         "investigation"):      (None, "DOJ — investigación",                    "Revisar alcance — puede ser material para la tesis"),
            ("paypal",   "apple pay",   "surpass"):            (1, "Apple Pay supera PayPal checkout",          "Dato cuantificado de cuota — confirmar fuente primaria"),
            ("paypal",   "losing",      "merchants"):          (1, "Merchants abandonando PayPal",              "Cuantificar escala — pérdida masiva invalida moat"),
            ("paypal",   "merchant",    "migration"):          (1, "Migración comerciantes a competidor",       "Identificar destino — Stripe/Adyen implica pérdida estructural"),
        },

        # ── CAT 2 · CATALIZADORES ─────────────────────────────────────────
        # Eventos que activan o aceleran la tesis.
        # Re-rating desde 8x requiere: branded checkout >+4% O M&A confirmado
        # O Venmo/BNPL/PYUSD superando umbrales que compensan el checkout.
        "keywords_cat2": [
            # Branded checkout recuperación — catalizador principal
            ("paypal",   "branded",     "accelerat"),
            ("paypal",   "branded",     "growth",   "accelerat"),
            ("paypal",   "checkout",    "growth",   "positive"),
            ("fastlane", "paypal",      "growth"),
            ("fastlane", "paypal",      "traction"),
            ("paypal",   "fastlane",    "merchant"),
            ("paypal",   "fastlane",    "expand"),
            # M&A — Stripe o cualquier adquirente
            ("paypal",   "acquisition"),
            ("paypal",   "acquire"),
            ("stripe",   "paypal",      "deal"),
            ("stripe",   "paypal",      "merger"),
            ("stripe",   "paypal",      "acqui"),
            # PYUSD — stablecoin como upside sorpresa
            ("pyusd",    "volume"),
            ("pyusd",    "adoption"),
            ("paypal",   "stablecoin",  "growth"),
            # Agentic commerce — AI payments
            ("paypal",   "openai",      "payment"),
            ("paypal",   "ai",          "checkout"),
            ("paypal",   "agentic",     "commerce"),
            # Venmo supera umbrales
            ("venmo",    "revenue",     "growth"),
            ("venmo",    "monetiz"),
            # BNPL aceleración
            ("paypal",   "bnpl",        "growth"),
            ("paypal",   "buy now",     "accelerat"),
        ],

        "keywords_cat2_hitos": {
            ("paypal",   "branded",     "accelerat"):          (1, "Branded checkout — aceleración",           "Confirmar tasa de crecimiento — umbral re-rating es +4%"),
            ("paypal",   "branded",     "growth",  "accelerat"): (1, "Branded checkout — crecimiento acelerado", "Actualizar convicción — si >+4% evaluar ampliar posición"),
            ("paypal",   "checkout",    "growth",  "positive"): (1, "Branded checkout — crecimiento positivo",  "Primer trimestre positivo sostenido — punto de inflexión"),
            ("fastlane", "paypal",      "growth"):              (1, "Fastlane — tracción comercial",            "Confirmar TPV Fastlane — si >$5B trimestral es material"),
            ("fastlane", "paypal",      "traction"):            (1, "Fastlane — adopción por comerciantes",     "Leer — número de merchants integrados es el dato clave"),
            ("paypal",   "fastlane",    "merchant"):            (1, "Fastlane — expansión red de comerciantes", "Cuantificar cobertura — si >10k merchants es catalizador"),
            ("paypal",   "fastlane",    "expand"):              (1, "Fastlane — expansión geográfica o vertical", "Confirmar mercados — US primero, luego Europa"),
            ("paypal",   "acquisition"):                        (None, "M&A — PYPL como objetivo o adquirente", "Identificar si es compra de PYPL o por PYPL — ambos son relevantes"),
            ("stripe",   "paypal",      "deal"):                (None, "Stripe/PYPL — deal confirmado",         "Si se confirma → floor implícito en precio · evaluar posición"),
            ("stripe",   "paypal",      "merger"):              (None, "Stripe/PYPL — fusión",                  "Si se confirma → re-rating inmediato · leer términos"),
            ("stripe",   "paypal",      "acqui"):               (None, "Stripe/PYPL — adquisición",             "Confirmar con fuente primaria — Bloomberg reportó rumor"),
            ("pyusd",    "volume"):                             (None, "PYUSD — volumen stablecoin",             "Umbral relevancia: >$5B en circulación · hoy embrionario"),
            ("pyusd",    "adoption"):                           (None, "PYUSD — adopción",                      "Seguimiento — upside sorpresa si escala en 2026-27"),
            ("paypal",   "stablecoin",  "growth"):              (None, "PYUSD — crecimiento",                   "Leer — si supera $5B en circulación actualizar tesis"),
            ("paypal",   "openai",      "payment"):             (None, "Agentic commerce — OpenAI",              "Leer — si hay revenue real en 2026 cambia la tesis"),
            ("paypal",   "agentic",     "commerce"):            (None, "Agentic commerce — pagos por agentes IA", "Leer — primer revenue real confirma optionality"),
            ("venmo",    "revenue",     "growth"):              (None, "Venmo — crecimiento revenue",            "Umbral: >+15% YoY · ya va a +20% · confirmar tendencia"),
            ("venmo",    "monetiz"):                            (None, "Venmo — monetización nueva feature",     "Leer — cualquier nueva palanca de ingresos de Venmo"),
            ("paypal",   "bnpl",        "growth"):              (None, "BNPL — aceleración TPV",                 "Umbral relevancia: >+20% YoY · ya en $40B"),
        },

        # ── CAT 3 · CONFIRMACIÓN ──────────────────────────────────────────
        # Earnings, upgrades, buybacks — seguimiento del estado de la tesis.
        # La métrica más importante por trimestre:
        #   · Transaction Margin Dollars ex-interés (valor absoluto, no %)
        #   · Branded checkout growth (aunque sea +1%, la dirección importa)
        #   · Ritmo de recompras (confirmación de $6B/año)
        "keywords_cat3": [
            ("paypal",   "earnings"),
            ("paypal",   "results"),
            ("paypal",   "beat",        "earnings"),
            ("paypal",   "beat",        "estimate"),
            ("pypl",     "earnings"),
            ("paypal",   "ebitda"),
            ("paypal",   "transaction", "margin"),
            ("paypal",   "upgrade"),
            ("paypal",   "price target"),
            ("paypal",   "buy",         "rating"),
            ("paypal",   "buyback"),
            ("paypal",   "repurchase"),
            ("pypl",     "buyback"),
            ("paypal",   "dividend"),
            ("paypal",   "fcf"),
            ("paypal",   "free cash flow"),
            ("paypal",   "guidance",    "raise"),
            ("paypal",   "guidance",    "increase"),
            # CEO Lores — declaraciones y plan estratégico
            ("lores",    "paypal",      "strategy"),
            ("lores",    "paypal",      "plan"),
            ("lores",    "paypal",      "guidance"),
            # Movimientos de precio con causa identificada
            ("pypl",     "down",        "today"),
            ("pypl",     "falling"),
            ("pypl",     "rally"),
        ],

        "keywords_cat3_hitos": {
            ("paypal",   "earnings"):               (1, "Earnings Q — revisión trimestral",         "Extraer: branded checkout growth, TM dollars ex-interés, guidance"),
            ("paypal",   "results"):                (1, "Earnings Q — revisión trimestral",         "Extraer: branded checkout growth, TM dollars ex-interés, guidance"),
            ("paypal",   "beat",   "earnings"):     (1, "Earnings Q — beat confirmado",             "Verificar si mejora guidance multianual"),
            ("paypal",   "beat",   "estimate"):     (1, "Earnings Q — beat estimaciones",           "Verificar magnitud y si incluye branded checkout positivo"),
            ("pypl",     "earnings"):               (1, "Earnings Q — revisión trimestral",         "Extraer métricas clave del pilar 1"),
            ("paypal",   "ebitda"):                 (1, "EBITDA — seguimiento margen",              "Umbral vigilancia: mantener >25%"),
            ("paypal",   "transaction", "margin"):  (2, "Transaction Margin — seguimiento",         "Dato más crítico: valor absoluto ex-interés · dirección importa más que nivel"),
            ("paypal",   "upgrade"):                (None, "Upgrade analista",                      "Sin acción requerida"),
            ("paypal",   "price target"):           (None, "Cambio precio objetivo",                "Sin acción requerida"),
            ("paypal",   "buy",    "rating"):       (None, "Rating Buy de analista",                "Sin acción requerida"),
            ("paypal",   "buyback"):                (3, "Buyback — confirmación ritmo $6B/año",     "Verificar trimestre — si <$1,5B en el trimestre es señal de compresión"),
            ("paypal",   "repurchase"):             (3, "Recompra — seguimiento programa",          "Confirmar pace anualizado — umbral relevante $6B"),
            ("pypl",     "buyback"):                (3, "Buyback PYPL — seguimiento",               "Mismo umbral: $1,5B/trimestre mínimo"),
            ("paypal",   "fcf"):                    (3, "FCF — seguimiento generación caja",        "Umbral: >$1,5B por trimestre · anualizado >$6B"),
            ("paypal",   "free cash flow"):         (3, "FCF — seguimiento",                       "Umbral anual: >$6B — base de la tesis"),
            ("paypal",   "guidance",  "raise"):     (1, "Guidance — elevada",                      "Señal positiva fuerte — evaluar ampliar posición"),
            ("paypal",   "guidance",  "increase"):  (1, "Guidance — aumentada",                    "Leer — confirmar si incluye branded checkout o solo EPS"),
            ("lores",    "paypal",    "strategy"):  (None, "CEO Lores — declaración estratégica",   "Leer completo — buscando plan concreto con métricas"),
            ("lores",    "paypal",    "plan"):       (None, "CEO Lores — plan de negocio",           "Buscando: ¿hay números concretos o solo narrativa?"),
            ("lores",    "paypal",    "guidance"):   (None, "CEO Lores — guidance",                  "Si reinstura guidance multianual → catalizador de re-rating"),
            ("pypl",     "down",      "today"):      (None, "Caída precio hoy — verificar causa",    "Leer — si no hay noticia detrás puede ser macro irrelevante"),
            ("pypl",     "falling"):                 (None, "Caída precio — verificar causa",        "Leer — verificar si hay evento fundamental detrás"),
            ("pypl",     "rally"):                   (None, "Subida precio — verificar causa",       "Leer — si hay catalizador fundamental actualizar convicción"),
        },

        # ── CAT 4 · MANOS FUERTES ─────────────────────────────────────────
        # Última actualización: 18-mar-2026
        # Fuente: SEC EDGAR Form 13F + MarketBeat institutional ownership
        # URL consulta: https://www.sec.gov/cgi-bin/browse-edgar
        #               ?action=getcompany&type=13F&CIK=0001410247
        #
        # PASO 1 DEL FLUJO — actualizar con Form 13F cada trimestre.
        # Criterio inclusión lista blanca: >1% float o movimiento >$100M reciente.
        # PYPL market cap ~$46B — umbral general $100M (~0,2% float).
        "manos_fuertes": {
            "vanguard":      ("Vanguard Group",         100_000_000, "Mayor institucional pasivo ~8% float"),
            "blackrock":     ("BlackRock",              100_000_000, "Institucional pasivo ~7% float"),
            "elliot":        ("Elliott Management",       0,          "Activista conocido — cualquier movimiento"),
            "starboard":     ("Starboard Value",          0,          "Activista — cualquier movimiento relevante"),
            "valueact":      ("ValueAct Capital",         0,          "Activista especialista tech — cualquier movimiento"),
            "jana":          ("Jana Partners",            0,          "Activista — en FISV · vigilar si entra en PYPL"),
        },

        "manos_fuertes_umbral_usd": 100_000_000,

        "macro_config": None,
    },


    # =========================================================================
    # FISV — Fiserv
    # =========================================================================
    # Tesis: "Value defensivo con suelo en core bancario" — caída 75% desde máximos.
    # ROIC 8,7% · FCF $5B · Shareholder yield ~13% · Deuda $23,7B · FV ~$167
    # Precio entrada: $66,95 · Peso cartera: 1,87% · Horizonte: 3-5 años
    #
    # DISEÑO DE KEYWORDS — dos pilares de la tesis:
    #   Pilar 1 (SUELO): Core bancario (Financial Solutions) — coste cambio extremo.
    #                    Si pierde contratos sistémicos el suelo desaparece.
    #   Pilar 2 (CRECIMIENTO): Clover — $3,3B revenue +23% · low double digits 2026.
    #                    Si se desacelera a <10% la tesis de crecimiento se rompe.
    #
    # CONDICIÓN DE SALIDA ÚNICA:
    #   Financial Solutions no crece orgánicamente en H2 2026 después de que
    #   la dirección lo prometió explícitamente.
    #   Earnings crítico: agosto 2026 (Q2) — NO mayo.
    #
    # ACTIVISMO JANA: constructivo mientras apoye a CEO Lyons.
    #   Si Jana cambia de posición respecto a Lyons → revisar tesis de gestión.
    #
    # manos_fuertes: Form 13F actualizado 18-mar-2026
    # sec_cik: 0000798354
    # =========================================================================
    "FISV": {
        "nombre":         "Fiserv",
        "activo":         True,
        "precio_entrada": 66.95,
        "moneda":         "USD",
        "sec_cik":        "0000798354",

        # Queries Google News — diseñadas por pilar de tesis
        # · Pilar 1: core bancario, contratos bank, coste de cambio
        # · Pilar 2: Clover growth, TPV pymes
        # · Activismo: Jana Partners + CEO Lyons
        # · Competencia cloud-native: Thought Machine, Mambu
        "gnews_queries": [
            "Fiserv Financial Solutions banking contract",
            "Fiserv Clover revenue growth",
            "Fiserv Jana Partners Lyons",
            "FISV stock earnings results",
            "Fiserv core banking",
            "Thought Machine Mambu bank contract",
            "Fiserv FIUSD stablecoin",
            "Fiserv merchant acquiring",
        ],

        # ── CAT 1 · INVALIDACIÓN DE TESIS ────────────────────────────────
        # Condición de salida: Financial Solutions sin crecimiento en H2 2026.
        # Señales adicionales: pérdida de contrato bancario sistémico,
        # deuda fuera de control, Jana contra Lyons.
        "keywords_cat1": [
            # Core bancario — pérdida de contratos (suelo desaparece)
            ("fiserv",   "bank",        "contract",   "loss"),
            ("fiserv",   "bank",        "loses",      "contract"),
            ("fiserv",   "loses",       "bank"),
            ("fiserv",   "bank",        "switch"),
            ("fiserv",   "bank",        "migrat",     "away"),
            ("fiserv",   "core",        "banking",    "loses"),
            # Financial Solutions en declive confirmado
            ("fiserv",   "financial solutions", "decline"),
            ("fiserv",   "financial solutions", "negative"),
            ("financial solutions", "fiserv",   "miss"),
            # Deuda — riesgo si WACC sube o FCF se comprime
            ("fiserv",   "debt",        "covenant"),
            ("fiserv",   "downgrade",   "credit"),
            ("fiserv",   "debt",        "refinanc",   "risk"),
            # Jana contra Lyons — cambio de posición activista
            ("jana",     "fiserv",      "lyons",      "replace"),
            ("jana",     "fiserv",      "ceo",        "change"),
            ("jana",     "fiserv",      "management", "change"),
            # Competencia cloud-native ganando contratos sistémicos
            ("thought machine",  "wins",    "bank"),
            ("mambu",            "wins",    "bank",    "fiserv"),
            ("temenos",          "replace", "fiserv"),
            # SEC EDGAR
            # v6.11 — ELIMINADO: ("fiserv", "sec", "filing") → ver nota LULU
            ("fiserv",   "sec",         "investigation"),
        ],

        "keywords_cat1_hitos": {
            ("fiserv",   "bank",        "contract",   "loss"):   (1, "Core bancario — pérdida contrato",         "Identificar banco y tamaño — >$100M revenue = suelo en riesgo"),
            ("fiserv",   "bank",        "loses",      "contract"): (1, "Core bancario — pérdida contrato",       "Confirmar con SEC filing — si es banco sistémico revisar tesis"),
            ("fiserv",   "loses",       "bank"):                  (1, "Core bancario — banco abandona Fiserv",   "Identificar banco — cualquier top-20 US invalida suelo de la tesis"),
            ("fiserv",   "bank",        "switch"):                (1, "Core bancario — migración a competidor",  "Leer fuente primaria — cuantificar revenue en riesgo"),
            ("fiserv",   "bank",        "migrat",     "away"):    (1, "Core bancario — migración",               "Confirmar magnitud — umbral crítico top-20 US bank"),
            ("fiserv",   "core",        "banking",    "loses"):   (1, "Core bancario — pérdida segmento",        "Revisar tesis — suelo depende de retención de contratos"),
            ("fiserv",   "financial solutions", "decline"):       (2, "Financial Solutions — declive confirmado", "Verificar si es H2 2026 — timing prometido por Lyons"),
            ("fiserv",   "financial solutions", "negative"):      (2, "Financial Solutions — negativo",           "Si es H2 2026 → CONDICIÓN DE SALIDA activada"),
            ("financial solutions", "fiserv",   "miss"):          (2, "Financial Solutions — miss expectativas", "Verificar vs guidance Lyons — si miss en H2 → salir"),
            ("fiserv",   "debt",        "covenant"):              (None, "Deuda — covenant breach",               "URGENTE — leer filing completo · puede ser no-evento técnico"),
            ("fiserv",   "downgrade",   "credit"):                (None, "Rating crediticio — downgrade",         "Verificar agencia y magnitud — afecta WACC y spread"),
            ("jana",     "fiserv",      "lyons",      "replace"): (None, "Jana — cambio posición sobre Lyons",    "Si Jana pide reemplazar Lyons → revisar tesis de gestión"),
            ("jana",     "fiserv",      "ceo",        "change"):  (None, "Jana — CEO change demand",              "Leer — Jana apoyaba a Lyons · cambio sería señal negativa"),
            ("thought machine", "wins", "bank"):                  (None, "Cloud-native — gana contrato bancario", "Identificar banco — si es top-20 US acelera amenaza estructural"),
            ("mambu",    "wins",        "bank",       "fiserv"):  (None, "Mambu reemplaza Fiserv",                "Confirmar con fuente primaria — cuantificar revenue en riesgo"),
            ("temenos",  "replace",     "fiserv"):                (None, "Temenos reemplaza Fiserv",              "Confirmar banco — horizonte competitivo 7-10 años no 3-5"),
            # v6.11 — eliminado: ("fiserv", "sec", "filing") → ver keywords_cat1
            ("fiserv",   "sec",         "investigation"):         (None, "SEC — investigación regulatoria",       "Leer alcance — puede ser material o rutinario"),
        },

        # ── CAT 2 · CATALIZADORES ─────────────────────────────────────────
        # Re-rating desde 8x requiere: Financial Solutions vuelve a crecer
        # Y Clover mantiene double digit growth Y métricas limpias.
        "keywords_cat2": [
            # Financial Solutions recuperación — catalizador principal
            ("fiserv",   "financial solutions", "growth"),
            ("fiserv",   "financial solutions", "recover"),
            ("fiserv",   "financial solutions", "positive"),
            ("fiserv",   "banking",     "win",   "contract"),
            ("fiserv",   "bank",        "new",   "contract"),
            ("fiserv",   "wins",        "bank",  "deal"),
            # Clover aceleración
            ("clover",   "fiserv",      "growth",    "accelerat"),
            ("clover",   "revenue",     "beat"),
            ("clover",   "merchant",    "expand"),
            ("clover",   "smb",         "growth"),
            # FIUSD stablecoin — upside sorpresa potencial
            ("fiusd",    "fiserv"),
            ("fiserv",   "stablecoin",  "launch"),
            ("fiserv",   "stablecoin",  "bank"),
            # Jana como catalizador positivo
            ("jana",     "fiserv",      "metrics"),
            ("jana",     "fiserv",      "transparency"),
            ("jana",     "fiserv",      "value"),
            # Deuda — reducción acelera re-rating
            ("fiserv",   "debt",        "reduc"),
            ("fiserv",   "deleverag"),
        ],

        "keywords_cat2_hitos": {
            ("fiserv",   "financial solutions", "growth"):         (1, "Financial Solutions — crecimiento orgánico", "Dato más importante — confirmar es orgánico no inorgánico"),
            ("fiserv",   "financial solutions", "recover"):        (1, "Financial Solutions — recuperación",         "Confirmar trimestre — H2 2026 es cuando Lyons prometió"),
            ("fiserv",   "financial solutions", "positive"):       (1, "Financial Solutions — positivo",             "Primer trimestre positivo — actualizar convicción"),
            ("fiserv",   "banking",     "win",   "contract"):      (1, "Core bancario — nuevo contrato",             "Identificar banco — cualquier top-20 US es señal fuerte"),
            ("fiserv",   "bank",        "new",   "contract"):      (1, "Core bancario — contrato nuevo",             "Cuantificar revenue potencial — confirmar con IR"),
            ("fiserv",   "wins",        "bank",  "deal"):          (1, "Core bancario — deal ganado",                "Confirmar con fuente primaria — leer IR release"),
            ("clover",   "fiserv",      "growth",  "accelerat"):   (2, "Clover — aceleración del crecimiento",       "Umbral: >+23% YoY que es el baseline 2025"),
            ("clover",   "revenue",     "beat"):                   (2, "Clover — revenue beat",                      "Confirmar magnitud — baseline $3,3B · guía double digits 2026"),
            ("clover",   "merchant",    "expand"):                 (2, "Clover — expansión red de merchants",        "Leer — cobertura SMB es el moat de Clover"),
            ("fiusd",    "fiserv"):                                 (None, "FIUSD stablecoin — seguimiento",          "Leer — si hay adopción bancaria real cambia la tesis upside"),
            ("fiserv",   "stablecoin",  "launch"):                  (None, "Fiserv stablecoin — lanzamiento",         "Leer — FIUSD para bancos puede ser catalizador diferenciador"),
            ("jana",     "fiserv",      "metrics"):                 (None, "Jana — transparencia métricas",           "Jana presionando por métricas limpias — constructivo para la tesis"),
            ("jana",     "fiserv",      "value"):                   (None, "Jana — tesis de valor",                   "Leer declaraciones — puede incluir precio objetivo o plan"),
            ("fiserv",   "debt",        "reduc"):                   (None, "Deuda — reducción",                       "Cada punto de reducción amplía el spread ROIC-WACC"),
            ("fiserv",   "deleverag"):                              (None, "Deleveraging — reducción deuda",           "Seguimiento — de 3x hacia 2x EBITDA amplía upside"),
        },

        # ── CAT 3 · CONFIRMACIÓN ──────────────────────────────────────────
        # Earnings, Clover TPV, dividendos — seguimiento del estado de la tesis.
        # Métrica más importante: Clover revenue growth y Financial Solutions trend.
        "keywords_cat3": [
            ("fiserv",   "earnings"),
            ("fiserv",   "results"),
            ("fiserv",   "beat",        "earnings"),
            ("fisv",     "earnings"),
            ("fiserv",   "ebitda"),
            ("fiserv",   "fcf"),
            ("fiserv",   "free cash flow"),
            ("clover",   "fiserv",      "revenue"),
            ("clover",   "fiserv",      "tpv"),
            ("clover",   "payments",    "volume"),
            ("fiserv",   "upgrade"),
            ("fiserv",   "price target"),
            ("fiserv",   "buy",         "rating"),
            ("fiserv",   "dividend"),
            ("fiserv",   "buyback"),
            ("fiserv",   "repurchase"),
            # Jana — declaraciones operativas (no cambio posición)
            ("jana",     "fiserv",      "support"),
            ("jana",     "fiserv",      "lyons"),
            # CEO Lyons — declaraciones estratégicas
            ("lyons",    "fiserv",      "guidance"),
            ("lyons",    "fiserv",      "outlook"),
            # Movimientos precio
            ("fisv",     "down",        "today"),
            ("fisv",     "falling"),
            ("fiserv",   "rally"),
        ],

        "keywords_cat3_hitos": {
            ("fiserv",   "earnings"):                (1, "Earnings Q — revisión trimestral",          "Extraer: Financial Solutions trend, Clover growth, guidance H2"),
            ("fiserv",   "results"):                 (1, "Earnings Q — revisión trimestral",          "Dato más importante: ¿cuándo Lyons confirma H2 crecimiento?"),
            ("fiserv",   "beat",   "earnings"):      (1, "Earnings Q — beat confirmado",              "Confirmar si Financial Solutions incluido en beat"),
            ("fisv",     "earnings"):                (1, "Earnings Q — revisión",                     "Extraer métricas clave de los dos pilares"),
            ("fiserv",   "ebitda"):                  (1, "EBITDA — seguimiento margen",               "Umbral vigilancia: >30% margen operativo en Q4 2026"),
            ("fiserv",   "fcf"):                     (1, "FCF — seguimiento generación caja",         "Umbral: >$1,25B trimestral · anualizado >$5B"),
            ("fiserv",   "free cash flow"):          (1, "FCF — seguimiento",                        "Umbral anual: >$5B — base de la tesis"),
            ("clover",   "fiserv",   "revenue"):     (2, "Clover — revenue trimestral",               "Confirmar pace vs baseline $3,3B anual · guía low double digits"),
            ("clover",   "fiserv",   "tpv"):         (2, "Clover — volumen de pagos",                 "Indicador adelantado de revenue futuro"),
            ("clover",   "payments", "volume"):      (2, "Clover — volumen pagos",                    "Seguimiento — cobertura SMB es el moat"),
            ("fiserv",   "upgrade"):                 (None, "Upgrade analista",                       "Sin acción requerida"),
            ("fiserv",   "price target"):            (None, "Cambio precio objetivo",                 "Sin acción requerida — consenso ~$84"),
            ("fiserv",   "buy",     "rating"):       (None, "Rating Buy de analista",                 "Sin acción requerida"),
            ("fiserv",   "dividend"):                (None, "Dividendo — Fiserv paga dividendo",      "Confirmar mantenimiento — señal de FCF saludable"),
            ("fiserv",   "buyback"):                 (None, "Buyback — seguimiento ritmo",            "Confirmar pace — $2,2B en Q1 2025 es el baseline"),
            ("jana",     "fiserv",   "support"):     (None, "Jana — apoya gestión",                   "Constructivo mientras apoyen a Lyons"),
            ("jana",     "fiserv",   "lyons"):       (None, "Jana — mención CEO Lyons",               "Leer tono — apoyo o crítica determina catalizador vs riesgo"),
            ("lyons",    "fiserv",   "guidance"):    (None, "CEO Lyons — guidance",                   "Buscando: confirmación del crecimiento H2 en Financial Solutions"),
            ("lyons",    "fiserv",   "outlook"):     (None, "CEO Lyons — outlook",                    "Leer — cualquier mención a Financial Solutions H2 es clave"),
            ("fisv",     "down",     "today"):       (None, "Caída precio hoy — verificar causa",     "Leer — si no hay noticia puede ser macro irrelevante"),
            ("fiserv",   "rally"):                   (None, "Subida precio — verificar causa",        "Leer — si hay catalizador fundamental actualizar convicción"),
        },

        # ── CAT 4 · MANOS FUERTES ─────────────────────────────────────────
        # Última actualización: 18-mar-2026
        # Fuente: SEC EDGAR Form 13F
        # URL consulta: https://www.sec.gov/cgi-bin/browse-edgar
        #               ?action=getcompany&type=13F&CIK=0000798354
        #
        # PASO 1 DEL FLUJO — actualizar con Form 13F cada trimestre.
        # FISV market cap ~$35B — umbral general $75M (~0,2% float).
        "manos_fuertes": {
            "jana":          ("Jana Partners",          0,           "Activista — apoya CEO Lyons · cualquier movimiento"),
            "vanguard":      ("Vanguard Group",         75_000_000,  "Mayor institucional pasivo ~8% float"),
            "blackrock":     ("BlackRock",              75_000_000,  "Institucional pasivo ~7% float"),
            "fidelity":      ("Fidelity Investments",   75_000_000,  "Institucional activo — seguimiento"),
            "berkshire":     ("Berkshire Hathaway",     0,           "Si entra Buffett en FISV es señal fortísima"),
        },

        "manos_fuertes_umbral_usd": 75_000_000,

        "macro_config": None,
    },


    # =========================================================================
    # SQ — Block (XYZ)
    # =========================================================================
    # Tesis: "Punto de inflexión — modo inversión a modo generación de caja"
    # EPS Q4 +38% · Rule of 40 superada · Afterpay estabilizado · $9B buyback
    # Precio entrada: $55,24 · Peso cartera: 2,68% · Horizonte: 3-5 años
    #
    # NATURALEZA DIFERENTE a PYPL y FISV:
    #   No es value con narrativa rota — es crecimiento en transición hacia caja.
    #   El ROIC está por debajo del WACC HOY. La tesis es que eso cambia en 2026-27.
    #   El marco de análisis es: EPS growth + Rule of 40 + Afterpay risk control.
    #
    # DISEÑO DE KEYWORDS — tres vectores:
    #   Vector 1 (RIESGO): Afterpay + crédito. Si explota, la tesis se rompe.
    #   Vector 2 (TESIS):  EPS guidance + Rule of 40. Confirmación del punto inflexión.
    #   Vector 3 (UPSIDE): Cash App closed loop + ARPU. El activo infravalorado.
    #
    # CONDICIÓN DE SALIDA ÚNICA (ambas simultáneas):
    #   EPS miss >15% sobre guía propia en H1 2026
    #   AND riesgo de pérdida crediticia Borrow supera targets comunicados.
    #   Una sola no es suficiente — Block ya demostró recuperarse de un trimestre débil.
    #
    # RUIDO A IGNORAR:
    #   Volatilidad contable del BTC en balance (no afecta al negocio operativo)
    #   Investigación fiscal sobre Afterpay hasta que haya resolución concreta
    #   Cambio de nombre a XYZ (irrelevante para la tesis)
    #
    # Earnings crítico: mayo 2026 (Q1) — confirmar EPS $3,66 guidance
    # manos_fuertes: Form 13F actualizado 18-mar-2026
    # sec_cik: 0001512673
    # =========================================================================
    "SQ": {
        "nombre":         "Block (XYZ)",
        "activo":         True,
        "precio_entrada": 55.24,
        "moneda":         "USD",
        "sec_cik":        "0001512673",

        # Queries Google News — diseñadas por vector de tesis
        # · Vector 1: Afterpay delinquency, BNPL credit risk
        # · Vector 2: EPS guidance, Rule of 40, earnings
        # · Vector 3: Cash App ARPU, Square GPV, closed loop
        # · Dorsey — CEO y visión estratégica (IA, Bitcoin, recortes)
        "gnews_queries": [
            "Block Afterpay delinquency credit loss",
            "Block SQ earnings EPS guidance",
            "Cash App revenue ARPU growth",
            "Square GPV merchant growth",
            "Jack Dorsey Block strategy AI",
            "SQ XYZ stock results",
            "Block buyback repurchase",
            "Afterpay BNPL regulation",
        ],

        # ── CAT 1 · INVALIDACIÓN DE TESIS ────────────────────────────────
        # Condición de salida: EPS miss >15% + Afterpay supera targets.
        # Riesgo crediticio Afterpay es el más sistémico para la tesis.
        "keywords_cat1": [
            # Afterpay — riesgo crediticio (vector 1)
            ("afterpay",   "delinquency",  "rise"),
            ("afterpay",   "delinquency",  "above",  "target"),
            ("afterpay",   "credit loss",  "exceed"),
            ("afterpay",   "charge-off",   "rise"),
            ("block",      "borrow",       "loss",    "target"),
            ("block",      "credit",       "loss",    "exceed"),
            ("afterpay",   "default",      "rate",    "high"),
            # Afterpay — regulatorio (riesgo concreto con fiscales estatales)
            ("afterpay",   "regulat",      "action"),
            ("afterpay",   "state",        "attorney", "general"),
            ("afterpay",   "settlement",   "million"),
            ("block",      "afterpay",     "regulat",  "fine"),
            # EPS miss severo — vector 2
            ("block",      "eps",          "miss",    "guidance"),
            ("block",      "misses",       "guidance"),
            ("sq",         "guidance",     "cut"),
            ("block",      "guidance",     "lower"),
            ("block",      "rule of 40",   "miss"),
            # CEO Dorsey — riesgo gestión
            ("dorsey",     "block",        "resign"),
            ("dorsey",     "leaves",       "block"),
            # BTC — si genera pérdida contable material (no el precio en sí)
            ("block",      "bitcoin",      "impairment"),
            ("block",      "btc",          "writedown"),
            # SEC EDGAR
            # v6.11 — ELIMINADO: ("block", "sec", "filing") → ver nota LULU
            ("block",      "sec",          "investigation"),
        ],

        "keywords_cat1_hitos": {
            ("afterpay",   "delinquency",  "rise"):            (1, "Afterpay — morosidad en aumento",           "Cuantificar — umbral crítico: superar targets comunicados en Investor Day"),
            ("afterpay",   "delinquency",  "above",  "target"): (1, "Afterpay — morosidad supera target",       "CONDICIÓN DE SALIDA PARCIAL — verificar si EPS también falla"),
            ("afterpay",   "credit loss",  "exceed"):           (1, "Afterpay — pérdida crediticia excede target", "Verificar cohort data — Investor Day: todos los cohorts 2026 en target"),
            ("afterpay",   "charge-off",   "rise"):             (1, "Afterpay — charge-offs en aumento",         "Cuantificar vs baseline — umbral: superar targets comunicados"),
            ("block",      "borrow",       "loss",    "target"): (1, "Borrow — pérdida supera target",           "Verificar dato exacto — mismo umbral que Afterpay"),
            ("block",      "credit",       "loss",    "exceed"): (1, "Block — pérdida crediticia excede",        "Confirmar si es Afterpay, Borrow o Cash App — distinguir fuentes"),
            ("afterpay",   "default",      "rate",    "high"):   (1, "Afterpay — tasa de default elevada",       "Comparar con dato base Q4 2025 — dirección más importante que nivel"),
            ("afterpay",   "regulat",      "action"):            (None, "Afterpay — acción regulatoria",         "Leer alcance — varios fiscales estatales investigando · hasta ahora ruido"),
            ("afterpay",   "state",        "attorney", "general"): (None, "Afterpay — AG estatal",              "Identificar estado y demanda — cuantificar exposición potencial"),
            ("afterpay",   "settlement",   "million"):           (None, "Afterpay — acuerdo judicial",           "Leer monto — si >$500M puede impactar FCF material"),
            ("block",      "afterpay",     "regulat",  "fine"):  (None, "Block Afterpay — multa regulatoria",    "Cuantificar — si >$500M impacta FCF 2026 guidance"),
            ("block",      "eps",          "miss",    "guidance"): (2, "EPS — miss vs guidance propia",          "Cuantificar magnitud — umbral salida es >15% vs propia guía"),
            ("block",      "misses",       "guidance"):           (2, "EPS — miss guidance",                     "Si >15% Y Afterpay supera targets → CONDICIÓN DE SALIDA"),
            ("sq",         "guidance",     "cut"):                (2, "Guidance — recortada",                    "Cuantificar vs $3,66 EPS 2026 — si >15% abajo evaluar salida"),
            ("block",      "guidance",     "lower"):              (2, "Guidance — rebajada",                     "Mismo umbral — $3,66 EPS 2026 es el baseline"),
            ("block",      "rule of 40",   "miss"):               (2, "Rule of 40 — no se cumple",               "Rule of 40 superada en Q4 fue señal clave — si falla revisar tesis"),
            ("dorsey",     "block",        "resign"):             (None, "Dorsey — salida inesperada",            "Dorsey ES la tesis estratégica de IA + Bitcoin — leer contexto"),
            ("block",      "bitcoin",      "impairment"):         (None, "BTC — impairment contable",             "Impacta P&L pero no FCF operativo — aclarar al mercado si genera ruido"),
            ("block",      "btc",          "writedown"):          (None, "BTC — writedown",                      "Mismo caso — ruido contable vs cash operativo"),
            # v6.11 — eliminado: ("block", "sec", "filing") → ver keywords_cat1
            ("block",      "sec",          "investigation"):      (None, "SEC — investigación",                  "Leer alcance — puede ser material o rutinario"),
        },

        # ── CAT 2 · CATALIZADORES ─────────────────────────────────────────
        # El catalizador principal: EPS supera $3,66 guidance en cualquier trimestre
        # Y Cash App ARPU crece doble dígito.
        # Si ocurren juntos, el WACC empieza a comprimirse (beta baja).
        "keywords_cat2": [
            # EPS beat + Rule of 40 — vector 2
            ("block",      "beats",        "guidance"),
            ("block",      "eps",          "beat"),
            ("block",      "raises",       "guidance"),
            ("block",      "guidance",     "raise"),
            ("block",      "rule of 40",   "sustain"),
            ("block",      "rule of 40",   "exceed"),
            # Cash App ARPU + closed loop — vector 3
            ("cash app",   "arpu",         "growth"),
            ("cash app",   "revenue",      "accelerat"),
            ("cash app",   "monetiz"),
            ("block",      "closed loop",  "revenue"),
            ("cash app",   "square",       "integrat"),
            # Buyback ejecución — señal de confianza
            ("block",      "buyback",      "execut"),
            ("block",      "repurchase",   "accelerat"),
            ("sq",         "buyback",      "billion"),
            # Afterpay — estabilización confirmada
            ("afterpay",   "delinquency",  "stable"),
            ("afterpay",   "credit",       "improv"),
            ("afterpay",   "loss",         "below",  "target"),
            # Dorsey IA + reducción costes
            ("block",      "ai",           "cost",   "reduc"),
            ("dorsey",     "ai",           "block",  "efficiency"),
            ("block",      "headcount",    "reduc"),
        ],

        "keywords_cat2_hitos": {
            ("block",      "beats",        "guidance"):            (1, "EPS — beat vs guidance propia",          "Confirmar magnitud vs $3,66 · si >$4,00 en cualquier trimestre → ampliar"),
            ("block",      "eps",          "beat"):                (1, "EPS — beat estimaciones",                "Verificar vs guidance propia además de vs consenso"),
            ("block",      "raises",       "guidance"):            (1, "Guidance — elevada",                     "Actualizar baseline — si 2026 sube a >$4,00 cambia el multiple"),
            ("block",      "guidance",     "raise"):               (1, "Guidance — raise",                       "Cuantificar — nuevo EPS guidance 2026 es el dato clave"),
            ("block",      "rule of 40",   "sustain"):             (1, "Rule of 40 — sostenida",                 "Segundo trimestre consecutivo confirma el punto de inflexión"),
            ("block",      "rule of 40",   "exceed"):              (1, "Rule of 40 — superada significativamente", "Leer — magnitud importa · primer trimestre fue ajustado"),
            ("cash app",   "arpu",         "growth"):              (2, "Cash App — ARPU en crecimiento",         "Umbral catalizador: doble dígito YoY · confirmar dato exacto"),
            ("cash app",   "revenue",      "accelerat"):           (2, "Cash App — aceleración revenue",         "Señal de monetización del closed loop — leer breakdown"),
            ("cash app",   "monetiz"):                              (2, "Cash App — nueva feature monetizada",    "Leer — cualquier nueva palanca de ingresos del closed loop"),
            ("block",      "closed loop",  "revenue"):             (2, "Closed loop — generando revenue",        "El activo más infravalorado — si cuantifican revenue es señal fuerte"),
            ("afterpay",   "delinquency",  "stable"):              (None, "Afterpay — morosidad estable",        "Confirmación de que el riesgo crediticio está controlado"),
            ("afterpay",   "credit",       "improv"):              (None, "Afterpay — mejora crediticia",        "Señal positiva — cohorts 2026 ya estaban en target en feb 2026"),
            ("afterpay",   "loss",         "below",  "target"):    (None, "Afterpay — por debajo de target",     "Confirmación explícita de control crediticio — actualizar convicción"),
            ("block",      "buyback",      "execut"):              (None, "Buyback — ejecución real",            "Confirmar cuánto de los $9B autorizados se está ejecutando"),
            ("block",      "repurchase",   "accelerat"):           (None, "Recompra acelerada",                  "Señal de confianza management — actualizar shareholder yield"),
            ("dorsey",     "ai",           "block",  "efficiency"): (None, "Dorsey — IA para eficiencia",        "Recorte 10K→6K empleados apuesta IA — leer avances concretos"),
        },

        # ── CAT 3 · CONFIRMACIÓN ──────────────────────────────────────────
        # Earnings, GPV, Cash App — seguimiento del estado de la tesis.
        # Métrica más importante por trimestre: EPS vs guidance + Afterpay cohorts.
        "keywords_cat3": [
            ("block",      "earnings"),
            ("block",      "results"),
            ("sq",         "earnings"),
            ("block",      "beat",         "earnings"),
            ("block",      "beat",         "estimate"),
            ("block",      "ebitda"),
            ("block",      "gross profit"),
            ("cash app",   "revenue"),
            ("cash app",   "users"),
            ("square",     "gpv"),
            ("square",     "gross payment"),
            ("block",      "upgrade"),
            ("block",      "price target"),
            ("sq",         "buy",          "rating"),
            ("block",      "bitcoin",      "holdings"),
            ("block",      "btc",          "balance"),
            # Dorsey — visión estratégica
            # v6.12 — ELIMINADO: ("dorsey","block","strategy") y ("dorsey","block","ai")
            # Capturaban noticias operativas de layoffs/IA que no afectan a EPS ni
            # Afterpay. Cobertura real de Dorsey queda en:
            #   CAT1: ("dorsey","block","resign") — salida CEO
            #   CAT2: ("dorsey","ai","block","efficiency") — eficiencia concreta
            # Movimientos precio
            ("sq",         "down",         "today"),
            ("sq",         "falling"),
            ("sq",         "rally"),
        ],

        "keywords_cat3_hitos": {
            ("block",      "earnings"):                  (1, "Earnings Q — revisión trimestral",        "Extraer: EPS vs $3,66 guidance, Afterpay cohort data, Cash App ARPU"),
            ("block",      "results"):                   (1, "Earnings Q — revisión trimestral",        "Métricas clave: EPS, Rule of 40, Afterpay credit loss vs target"),
            ("sq",         "earnings"):                  (1, "Earnings Q — revisión",                  "Mismas métricas — EPS y Afterpay son los dos pilares de decisión"),
            ("block",      "beat",   "earnings"):        (1, "Earnings Q — beat",                      "Confirmar vs guidance propia $3,66 · no solo vs consenso"),
            ("block",      "beat",   "estimate"):        (1, "Earnings Q — beat estimaciones",         "Verificar si incluye beat en EPS guidance propia"),
            ("block",      "ebitda"):                    (1, "EBITDA — seguimiento margen",             "Umbral vigilancia: margen operativo >26% (guía 2026)"),
            ("block",      "gross profit"):              (1, "Gross profit — seguimiento",              "Umbral: >$2,9B trimestral · guía 2026 $11,98B anual"),
            ("cash app",   "revenue"):                   (2, "Cash App — revenue trimestral",           "Indicador más importante del closed loop · cuantificar YoY"),
            ("cash app",   "users"):                     (2, "Cash App — usuarios activos",             "Si ARPU crece con usuarios estables es monetización real"),
            ("square",     "gpv"):                       (None, "Square — volumen pagos",               "Umbral: mid single digits growth — si acelera a >10% es señal"),
            ("block",      "upgrade"):                   (None, "Upgrade analista",                     "Sin acción requerida"),
            ("block",      "price target"):              (None, "Cambio precio objetivo",               "Sin acción requerida"),
            ("block",      "bitcoin",   "holdings"):     (None, "BTC — tenencias en balance",           "Dato contable — no afecta tesis operativa"),
            ("block",      "btc",       "balance"):      (None, "BTC — balance sheet",                  "Ruido contable — separar de FCF operativo al leer"),
            # v6.12 — eliminado: ("dorsey","block","strategy") y ("dorsey","block","ai")
            ("sq",         "down",      "today"):        (None, "Caída precio hoy — verificar causa",   "Leer — BTC puede causar caídas sin fundamento operativo"),
            ("sq",         "falling"):                   (None, "Caída precio — verificar causa",       "Distinguir si es BTC/macro vs noticia operativa real"),
            ("sq",         "rally"):                     (None, "Subida precio — verificar causa",      "Leer — si hay catalizador operativo actualizar convicción"),
        },

        # ── CAT 4 · MANOS FUERTES ─────────────────────────────────────────
        # Última actualización: 18-mar-2026
        # Fuente: SEC EDGAR Form 13F
        # URL consulta: https://www.sec.gov/cgi-bin/browse-edgar
        #               ?action=getcompany&type=13F&CIK=0001512673
        #
        # PASO 1 DEL FLUJO — actualizar con Form 13F cada trimestre.
        # SQ market cap ~$35B — umbral general $75M (~0,2% float).
        # Beta 2,67 — movimientos institucionales de convicción son más relevantes
        # que en tickers con beta menor.
        #
        # DISEÑO DELIBERADO v6.9 — Dorsey con umbral $5M y exclusiones rutinarias:
        # Block tiene una cultura de compensación en acciones muy intensa.
        # Los ejecutivos venden CONSTANTEMENTE por tres razones NO señalizadoras:
        #   1. RSU tax withholding: venta automática al vest para pagar impuestos.
        #      Forma: "automatically sold to satisfy tax withholding". No es señal.
        #   2. Plan 10b5-1: venta programada meses antes. No es señal.
        #   3. Ejercicio de opciones: conversión de derivado a acción. No es señal.
        # La única señal real es: venta discrecional en mercado abierto >10%
        # de la posición total del insider, SIN plan 10b5-1 previo.
        # Dorsey tiene ~40M acciones (~$2.2B). Una venta de señal sería >$220M.
        # Las noticias sobre layoffs/IA que mencionan "Dorsey" NO son Form 4.
        # El filtro de exclusión en clasificar_manos_fuertes resuelve el ruido.
        "manos_fuertes": {
            "ark":           ("ARK Investment",          0,           "Cathie Wood — cualquier movimiento es señal"),
            "vanguard":      ("Vanguard Group",          75_000_000,  "Institucional pasivo — seguimiento"),
            "blackrock":     ("BlackRock",               75_000_000,  "Institucional pasivo — seguimiento"),
            "dorsey":        ("Jack Dorsey",             5_000_000,   "CEO insider — solo ventas discrecionales >$5M · excluir RSU/10b5-1"),
        },

        "manos_fuertes_umbral_usd": 75_000_000,

        "macro_config": None,
    },
}


# =============================================================================
# SECCIÓN 3 — NOTIFICACIÓN DE ERRORES
# =============================================================================
# Principio: ningún fallo es silencioso. Todo error llega a Telegram con
# contexto suficiente para diagnosticar y resolver sin acceder a los logs.
# "Sin noticias" también se notifica — el silencio no es una opción válida.
#
# _errores acumula durante la ejecución y se vuelca al pie del mensaje diario.
# En caso de excepción total, se envía un mensaje de emergencia independiente.
# =============================================================================

_errores = []


def registrar_error(contexto, detalle, sugerencia=""):
    """
    Acumula un error para incluirlo en el mensaje Telegram final.
    No interrumpe la ejecución — el script continúa con los datos disponibles.
    """
    _errores.append({
        "contexto":   contexto,
        "detalle":    str(detalle)[:200],
        "sugerencia": sugerencia,
    })
    print("  [ERROR] " + contexto + ": " + str(detalle)[:120])


def enviar_telegram_directo(texto, token=None, chat_id=None):
    """
    Envío mínimo a Telegram sin depender del flujo principal.
    Usado exclusivamente para alertas de error y excepciones totales.
    No registra errores propios para evitar recursión.
    """
    t = token or TOKEN
    c = chat_id or CHAT_ID
    try:
        requests.post(
            "https://api.telegram.org/bot" + t + "/sendMessage",
            data={"chat_id": c, "text": texto[:4000]},
            timeout=15,
        )
    except Exception as e:
        print("  [CRITICO] No se pudo enviar Telegram de error: " + str(e))


def render_errores():
    """Genera el bloque de errores para incluir al pie del mensaje diario."""
    if not _errores:
        return ""
    L = ["", "=" * 38, "AVISOS DEL SISTEMA [" + str(len(_errores)) + "]", "-" * 30]
    for e in _errores:
        L.append("⚠ " + e["contexto"])
        L.append("  " + e["detalle"])
        if e["sugerencia"]:
            L.append("  → " + e["sugerencia"])
        L.append("")
    return "\n".join(L)


# =============================================================================
# SECCIÓN 4 — FETCHERS
# =============================================================================
# Cada fetcher es independiente y falla de forma controlada.
# Un fetcher caído registra el error pero no detiene la ejecución.
#
# Fuentes disponibles:
#   · SEC EDGAR 8-K  — filings regulatorios (funciona en GitHub, puede fallar en Colab)
#   · Google News RSS — noticias con resolución de URL real (funciona en GitHub)
#   · BLS API JSON   — dato macro mensual sin scraping HTML
# =============================================================================

# Caché en memoria para URLs de Google News.
# Evita resolver la misma URL múltiples veces cuando aparece en varias queries.
# Sin persistencia — se reconstruye en cada ejecución. Sin dependencias.
_url_cache = {}


def resolver_url(url_google, timeout=8):
    """
    Resuelve la URL real detrás del enlace de Google News RSS.
    Las URLs news.google.com/rss/articles/CBMi... son tokens internos
    que dan error 400 en navegador — expiran y requieren cookies de sesión.

    Solución: seguir el redirect HTTP en el momento de detectar la noticia.
    Funciona en GitHub Actions. En Colab puede fallar por bloqueo de IP de
    Google Cloud — en ese caso devuelve la URL original (fallback silencioso).

    Limpia solo parámetros de tracking conocidos (utm_*) — no todos los params,
    ya que algunos sitios (Reuters, FT) los necesitan para cargar el artículo.
    """
    if not url_google or "news.google.com" not in url_google:
        return url_google

    if url_google in _url_cache:
        return _url_cache[url_google]

    try:
        resp = requests.get(
            url_google,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        url_final = resp.url

        # Limpiar solo parámetros de tracking — preservar el resto
        tracking_params = {"utm_source", "utm_medium", "utm_campaign",
                           "utm_term", "utm_content", "ref", "src"}
        if "?" in url_final:
            base, qs = url_final.split("?", 1)
            params_limpios = [p for p in qs.split("&")
                              if p.split("=")[0] not in tracking_params]
            url_final = base + ("?" + "&".join(params_limpios) if params_limpios else "")

        if "news.google.com" in url_final:
            # El redirect no funcionó — devolver original
            _url_cache[url_google] = url_google
            return url_google

        _url_cache[url_google] = url_final
        return url_final

    except Exception as e:
        registrar_error(
            "resolver_url",
            e,
            "Comprobar conectividad en GitHub Actions. "
            "Si persiste, Google puede estar bloqueando el User-Agent."
        )
        _url_cache[url_google] = url_google
        return url_google


def fetch_sec_8k(cik, horas=None, nombre_empresa=None):
    """
    SEC EDGAR RSS — 8-K filings regulatorios.
    Funciona en GitHub Actions. En Colab puede devolver 0 por bloqueo de IP.
    CIK de cada ticker en TICKERS_CONFIG · sec_cik.

    nombre_empresa: si se proporciona, enriquece títulos genéricos tipo "8-K  - Current report"
    con el nombre de la empresa para que el clasificador pueda hacer match de keywords.
    Motivo v6.5: SEC devuelve títulos vacíos que caen a ruido. Un 8-K de LULU o GLNG
    es un evento material — debe clasificarse, no ignorarse.
    """
    if horas is None:
        horas = HORAS_LOOKBACK
    resultados = []
    if not cik:
        return resultados
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        "?action=getcompany&CIK=" + cik +
        "&type=8-K&dateb=&owner=include&count=10&search_text=&output=atom"
    )
    try:
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        limite = datetime.now(timezone.utc) - timedelta(hours=horas)
        print("    SEC EDGAR raw entries: " + str(len(feed.entries)))
        for entry in feed.entries:
            try:
                fecha = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                fecha = datetime.now(timezone.utc)
            if fecha >= limite:
                titulo = entry.title
                # Enriquecer títulos genéricos para que el clasificador pueda matchear
                # "8-K  - Current report" → "Lululemon 8-K SEC filing - Current report"
                if nombre_empresa and titulo.strip().lower().startswith("8-k"):
                    titulo = nombre_empresa + " 8-K SEC filing - " + titulo.strip()
                resultados.append({
                    "titulo":    titulo,
                    "enlace":    entry.link,  # SEC — URL directa, no necesita resolver
                    "fecha_pub": fecha,
                    "fuente":    "SEC EDGAR 8-K",
                    "ticker":    None,
                })
    except Exception as e:
        registrar_error(
            "SEC EDGAR · CIK " + cik,
            e,
            "Verificar CIK en TICKERS_CONFIG. "
            "SEC puede bloquear IPs de GitHub Actions esporádicamente — "
            "si persiste >2 dias revisar SEC_HEADERS."
        )
    return resultados


def fetch_google_news(query, horas=None):
    """
    Google News RSS con resolución de URLs reales y caché en memoria.
    Toma los primeros 15 resultados de cada query dentro del lookback.
    """
    if horas is None:
        horas = HORAS_LOOKBACK
    resultados = []
    url = (
        "https://news.google.com/rss/search"
        "?q=" + requests.utils.quote(query) +
        "&hl=en&gl=US&ceid=US:en"
    )
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            registrar_error(
                "Google News · query vacia: '" + query + "'",
                "Feed devuelto sin entradas",
                "Puede ser bloqueo temporal o query demasiado especifica. "
                "Verificar: " + url
            )
        limite = datetime.now(timezone.utc) - timedelta(hours=horas)
        for entry in feed.entries[:15]:
            try:
                fecha = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                fecha = datetime.now(timezone.utc)
            if fecha >= limite:
                url_raw  = getattr(entry, "link", "")
                url_real = resolver_url(url_raw)
                resultados.append({
                    "titulo":    entry.title,
                    "enlace":    url_real,
                    "fecha_pub": fecha,
                    "fuente":    "Google News",
                    "ticker":    None,
                })
    except Exception as e:
        registrar_error(
            "Google News · '" + query + "'",
            e,
            "Comprobar conectividad. Si todos los feeds fallan, "
            "Google News RSS puede estar caido o bloqueando el runner."
        )
    return resultados


def fetch_macro_bls(config):
    """
    BLS API JSON — primer viernes de cada mes, después de las 14:00 UTC.
    Usa la API pública gratuita de BLS en lugar de scraping HTML frágil.

    DISEÑO: API sin registro — 0 dependencias de entorno.
    Límite: 25 queries/día sin API key — suficiente para 1 query mensual por ticker.
    Formato JSON estable — no depende del layout HTML de la página BLS.

    TIMING CRÍTICO: el dato BLS se publica a las 08:30 ET (13:30 UTC).
    El cron principal corre a las 06:00 UTC — 7h antes del dato.
    El segundo cron del workflow (0 14 1-7 * 5) garantiza la ejecución
    post-publicación. Ver monitor_noticias.yml.

    Serie CES2000000001 = Construction Employment (miles de personas).
    Umbrales STZ: alerta_baja < 8.100.000 · catalizador >= 8.280.000
    """
    if config is None or config.get("tipo") != "bls":
        return None

    hoy = datetime.now(timezone.utc)
    if hoy.weekday() != 4 or hoy.day > 7:
        return None

    serie = config.get("serie", "CES2000000001")
    anio  = str(hoy.year)

    try:
        url  = "https://api.bls.gov/publicAPI/v1/timeseries/data/" + serie
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "REQUEST_SUCCEEDED":
            raise Exception("BLS API status: " + data.get("status", "desconocido") +
                            " — " + str(data.get("message", "")))

        series_data = data.get("Results", {}).get("series", [])
        if not series_data:
            raise Exception("BLS API devolvio Results vacio para serie " + serie)

        ultimo       = series_data[0].get("data", [{}])[0]
        valor_miles  = float(ultimo.get("value", 0))
        valor_total  = int(valor_miles * 1000)
        periodo      = ultimo.get("periodName", "?") + " " + ultimo.get("year", anio)
        umbral_baja  = config.get("umbral_alerta_baja")
        umbral_cat   = config.get("umbral_catalizador")

        if umbral_baja and valor_total < umbral_baja:
            nivel = "BAJO — posible invalidacion"
        elif umbral_cat and valor_total >= umbral_cat:
            nivel = "CATALIZADOR — confirma tesis"
        else:
            nivel = "NEUTRAL — dentro de rango"

        print("    BLS API · " + serie + " · " + periodo +
              " · " + str(valor_total) + " · " + nivel)

        return {
            "descripcion": config.get("descripcion", "BLS dato macro"),
            "valor":       valor_total,
            "valor_miles": valor_miles,
            "periodo":     periodo,
            "nivel":       nivel,
            "serie":       serie,
            "url":         "https://www.bls.gov/news.release/empsit.nr0.htm",
            "umbral_baja": umbral_baja,
            "umbral_cat":  umbral_cat,
        }

    except Exception as e:
        registrar_error(
            "BLS API · serie " + serie,
            e,
            "Verificar: https://api.bls.gov/publicAPI/v1/timeseries/data/" + serie +
            " — Si caida, consultar https://www.bls.gov/news.release/empsit.nr0.htm"
        )
        return None


# =============================================================================
# SECCIÓN 5 — CLASIFICADOR
# =============================================================================
# Prioridad de categorías: CAT1 > CAT2 > CAT3 > CAT4 > RUIDO
# Una noticia solo puede estar en una categoría — la de mayor prioridad.
#
# CAT4 manos fuertes:
#   Primero busca coincidencia en lista blanca (manos_fuertes del ticker).
#   Si no hay match en lista blanca, busca mención de cantidad en USD
#   y la compara con manos_fuertes_umbral_usd.
#   La extracción de cantidad es heurística simple — busca patrones "$NM"
#   o "N million" en el título. Sin dependencias de parsing avanzado.
# =============================================================================

def normalizar(texto):
    return (texto.lower()
            .replace("-", " ")
            .replace("\u2019", "")
            .replace("'", "")
            .replace(",", "")
            .replace(".", " "))


def match_keywords(titulo, keywords_list):
    tn = normalizar(titulo)
    return any(all(k.lower() in tn for k in tupla) for tupla in keywords_list)


def encontrar_hito(titulo, hitos_dict):
    """
    Busca qué tupla de keywords hace match y devuelve el hito asignado.
    Retorna (id_hito, descripcion, accion) o valores neutros si no hay match.
    """
    tn = normalizar(titulo)
    for tupla, hito_info in hitos_dict.items():
        if all(k.lower() in tn for k in tupla):
            return hito_info
    return (None, "Sin hito asignado", "Sin accion requerida")


def extraer_millones_usd(titulo):
    """
    Extrae una cantidad en USD del título para comparar con umbral de manos fuertes.
    Heurística simple sin regex avanzado — busca patrones comunes en titulares
    financieros: "$X.XM", "$X million", "X.X million", "X billion".
    Devuelve el valor en USD o 0 si no encuentra nada reconocible.
    """
    tn    = normalizar(titulo)
    words = tn.split()
    for i, w in enumerate(words):
        # Patrón: "$3.15" seguido de "million" o "m"
        if w.startswith("$"):
            num_str = w[1:].replace("m", "").replace("b", "")
            try:
                num = float(num_str)
                # Determinar si es millones o billones
                siguiente = words[i + 1] if i + 1 < len(words) else ""
                if "billion" in siguiente or w.endswith("b"):
                    return num * 1_000_000_000
                return num * 1_000_000
            except ValueError:
                continue
        # Patrón: número seguido de "million" o "billion"
        if i + 1 < len(words) and words[i + 1] in ("million", "billion"):
            try:
                num = float(w.replace("$", ""))
                if words[i + 1] == "billion":
                    return num * 1_000_000_000
                return num * 1_000_000
            except ValueError:
                continue
    return 0


def clasificar_manos_fuertes(titulo, config):
    """
    Clasifica una noticia como CAT4 si menciona un fondo de la lista blanca
    o si la posición supera el umbral configurado para fondos desconocidos.
    Devuelve (es_cat4, descripcion, accion) o (False, "", "") si no aplica.

    v6.9: añadido filtro de exclusión de ventas rutinarias de insiders.
    Las ventas por RSU tax withholding, planes 10b5-1 automáticos y noticias
    operativas (layoffs, IA, jobs) que mencionan el nombre del CEO no son
    señales de movimiento real de acciones — son ruido de compensación.
    Criterio de señal real: venta discrecional en mercado abierto, sin plan
    10b5-1, de un volumen significativo vs la posición total del insider.
    """
    manos        = config.get("manos_fuertes", {})
    umbral       = config.get("manos_fuertes_umbral_usd", 50_000_000)
    tn           = normalizar(titulo)

    # ── FILTRO DE EXCLUSIÓN v6.9/v6.10 ──────────────────────────────────
    # Noticias que mencionan un insider por nombre pero NO son movimientos
    # reales de acciones — son noticias operativas o ventas rutinarias.
    #
    # DISEÑO v6.10: dos listas separadas por método de match:
    #   - EXCLUSIONES_SUBCADENA: términos largos sin riesgo de falso positivo
    #     por substring. Ej: "vesting" no está en "investor".
    #   - EXCLUSIONES_PALABRA: términos cortos que requieren match de palabra
    #     completa para evitar falsos positivos. Ej: "vest" está en "investor",
    #     "post" está en "postpone", "says" está en "displays".
    EXCLUSIONES_SUBCADENA = (
        # Ventas técnicas de compensación — no discrecionales
        "rsu", "restricted stock", "tax withhold", "withholding",
        "10b5", "10b5-1", "trading plan", "vesting",
        "option exercise", "option ex", "derivative",
        # Noticias operativas sobre CEO/gestión — no Form 4
        "layoff", "layoffs", "cuts job", "job cut", "workforce",
        "thousands of job", "hundreds of job", "cut staff", "slashes staff",
        "ai strategy", "ai tool", "embrace ai", "ai model",
        "apocalypse", "debate", "warns", "warning",
        "praises", "argues", "suggests",
        "interview", "tweet", "statement",
        # Frases compuestas específicas de noticias operativas
        "pushes smaller", "pushes leaner", "pushes flatter", "pushes ai",
        "embraces ai", "leans on ai",
    )
    # Términos cortos: solo excluir si aparecen como palabra completa
    # "vest" en "investor" → NO excluir · "vest" como palabra sola → SÍ excluir
    # "says" en "displays" → NO excluir · "says" como palabra sola → SÍ excluir
    EXCLUSIONES_PALABRA = ("vest", "post", "says", "fears")

    palabras_tn = set(tn.split())

    if (any(excl in tn for excl in EXCLUSIONES_SUBCADENA) or
            any(excl in palabras_tn for excl in EXCLUSIONES_PALABRA)):
        return (False, "", "")

    # Primero: buscar coincidencia en lista blanca
    for clave, (nombre, umbral_fondo, razon) in manos.items():
        if clave.lower() in tn:
            cantidad = extraer_millones_usd(titulo)
            if umbral_fondo == 0 or cantidad >= umbral_fondo:
                return (
                    True,
                    "Mano fuerte: " + nombre + " — " + razon,
                    "Verificar direccion del movimiento (compra/venta) y magnitud"
                )

    # Segundo: fondo desconocido con posición superior al umbral general
    cantidad = extraer_millones_usd(titulo)
    if cantidad >= umbral:
        # Solo clasificar si el título sugiere una operación institucional
        indicadores = ("acquires", "buys", "sells", "reduces", "increases",
                       "stake", "holdings", "shares", "position")
        if any(ind in tn for ind in indicadores):
            return (
                True,
                "Fondo no identificado · $" + str(int(cantidad / 1_000_000)) + "M — supera umbral",
                "Identificar fondo en SEC EDGAR Form 13F — valorar añadir a lista blanca"
            )

    return (False, "", "")


def clasificar(titulo, config):
    """
    Clasifica una noticia y devuelve (categoria, id_hito, descripcion, accion).
    Prioridad: CAT1 > CAT2 > CAT4 > CAT3 > ruido.

    CAT4 evalúa ANTES que CAT3 porque una compra de mano fuerte es más accionable
    que una confirmación de tesis. Sin este orden, keywords genéricas de CAT3
    como ("golar", "buy") capturarían compras institucionales antes de llegar a CAT4.

    CAT4 no usa el sistema de hitos — usa descripcion y accion directamente.

    DEBUG: en modo auditoría (DRY_RUN=True) imprime la keyword exacta que dispara
    cada CAT para facilitar el refinamiento. Eliminar cuando el clasificador esté estable.
    """
    tn = normalizar(titulo)

    if match_keywords(titulo, config["keywords_cat1"]):
        hito = encontrar_hito(titulo, config.get("keywords_cat1_hitos", {}))
        if DRY_RUN:
            for tupla in config["keywords_cat1"]:
                if all(k.lower() in tn for k in tupla):
                    print("    [DEBUG CAT1] " + str(tupla) + " → " + titulo[:70])
                    break
        return ("cat1",) + hito

    if match_keywords(titulo, config["keywords_cat2"]):
        hito = encontrar_hito(titulo, config.get("keywords_cat2_hitos", {}))
        if DRY_RUN:
            for tupla in config["keywords_cat2"]:
                if all(k.lower() in tn for k in tupla):
                    print("    [DEBUG CAT2] " + str(tupla) + " → " + titulo[:70])
                    break
        return ("cat2",) + hito

    # CAT4 antes que CAT3 — ver nota de prioridad en docstring
    es_cat4, desc, accion = clasificar_manos_fuertes(titulo, config)
    if es_cat4:
        if DRY_RUN:
            print("    [DEBUG CAT4] manos_fuertes → " + titulo[:70])
        return ("cat4", None, desc, accion)

    if match_keywords(titulo, config["keywords_cat3"]):
        hito = encontrar_hito(titulo, config.get("keywords_cat3_hitos", {}))
        if DRY_RUN:
            for tupla in config["keywords_cat3"]:
                if all(k.lower() in tn for k in tupla):
                    print("    [DEBUG CAT3] " + str(tupla) + " → " + titulo[:70])
                    break
        return ("cat3",) + hito

    return ("ruido", None, "", "")

    if match_keywords(titulo, config["keywords_cat3"]):
        hito = encontrar_hito(titulo, config.get("keywords_cat3_hitos", {}))
        return ("cat3",) + hito

    return ("ruido", None, "", "")


# =============================================================================
# SECCIÓN 6 — DEDUPLICACIÓN
# =============================================================================
# Hash por título + fuente para evitar:
#   · Que el mismo titular de dos fuentes distintas colisione (falso negativo)
#   · Que la misma noticia de la misma fuente aparezca dos veces (duplicado)
# Se persisten los últimos 500 hashes para evitar repeticiones entre ejecuciones.
# =============================================================================

def cargar_vistos():
    if os.path.exists(RUTA_VISTOS):
        try:
            with open(RUTA_VISTOS, "r", encoding="utf-8") as f:
                return set(json.load(f).get("hashes", []))
        except Exception:
            pass
    return set()


def guardar_vistos(vistos):
    os.makedirs(CARPETA, exist_ok=True)
    with open(RUTA_VISTOS, "w", encoding="utf-8") as f:
        json.dump({"hashes": list(vistos)[-500:]}, f)


def hash_n(titulo, fuente=""):
    clave = titulo.lower() + "|" + fuente.lower()
    return hashlib.md5(clave.encode()).hexdigest()[:12]


# =============================================================================
# SECCIÓN 7 — RENDER TELEGRAM
# =============================================================================
# El mensaje diario se envía siempre — "sin noticias" es información.
# Orden: CAT1 (alerta) > CAT2 (catalizador) > CAT3 (confirmacion) >
#        CAT4 (manos fuertes) > ruido > errores de sistema.
# =============================================================================

def hace(fecha_pub):
    diff = datetime.now(timezone.utc) - fecha_pub
    h    = int(diff.total_seconds() / 3600)
    if h == 0:
        return "hace " + str(int(diff.total_seconds() / 60)) + "min"
    elif h < 24:
        return "hace " + str(h) + "h"
    else:
        return "hace " + str(int(h / 24)) + "d"


def render_noticia(n, accion_default):
    """Renderiza una noticia con hito o contexto según categoría.

    v6.7: añade enlace archive.ph como fallback para artículos de pago.
    archive.ph guarda copias públicas de ~70% de artículos premium.
    Solo se añade si la fuente no es SEC EDGAR (que ya es pública).
    """
    L = []
    L.append("TICKER: " + n["ticker"])
    L.append(n["titulo"][:120])
    L.append("Fuente: " + n["fuente"] + " · " + hace(n["fecha_pub"]))
    enlace = n["enlace"]
    L.append("-> " + enlace)
    # Archive.ph fallback — solo para fuentes externas, no SEC
    if enlace.startswith("http") and "sec.gov" not in enlace and "news.google.com" not in enlace:
        L.append("   archivo: https://archive.ph/newest/" + enlace)

    id_hito   = n.get("id_hito")
    desc_hito = n.get("desc_hito", "")
    accion    = n.get("accion_hito", accion_default)

    if id_hito is not None:
        L.append("HITO: " + str(id_hito) + " — " + desc_hito)
        L.append("ACCION: " + accion)
    else:
        if desc_hito and desc_hito != "Sin hito asignado":
            L.append("CONTEXTO: " + desc_hito)
        L.append("ACCION: " + accion)
    L.append("")
    return "\n".join(L)


def render_mensaje(noticias_por_cat, tickers, ruido_items, fecha_now, modo_auditoria):
    L = []
    L.append("MONITOR NOTICIAS v6.7 · " + fecha_now)
    L.append("Tickers: " + " · ".join(tickers))
    if modo_auditoria:
        L.append("MODO: AUDITORIA · HORAS=" + str(HORAS_LOOKBACK))
    L.append("=" * 38)

    tiene = False

    if noticias_por_cat.get("cat1"):
        tiene = True
        L.append("")
        L.append("ALERTA INVALIDACION [" + str(len(noticias_por_cat["cat1"])) + "]")
        L.append("-" * 30)
        for n in noticias_por_cat["cat1"]:
            L.append(render_noticia(n, "Revisar posicion en 48h"))

    if noticias_por_cat.get("cat2"):
        tiene = True
        L.append("")
        L.append("CATALIZADOR [" + str(len(noticias_por_cat["cat2"])) + "]")
        L.append("-" * 30)
        for n in noticias_por_cat["cat2"]:
            L.append(render_noticia(n, "Evaluar ampliar posicion"))

    if noticias_por_cat.get("cat3"):
        tiene = True
        L.append("")
        L.append("CONFIRMACION [" + str(len(noticias_por_cat["cat3"])) + "]")
        L.append("-" * 30)
        for n in noticias_por_cat["cat3"]:
            L.append(render_noticia(n, "Revisar y actualizar JSON si procede"))

    if noticias_por_cat.get("cat4"):
        tiene = True
        L.append("")
        L.append("MANOS FUERTES [" + str(len(noticias_por_cat["cat4"])) + "]")
        L.append("-" * 30)
        for n in noticias_por_cat["cat4"]:
            L.append(render_noticia(n, "Verificar direccion del movimiento"))

    if not tiene:
        L.append("")
        L.append("Sin noticias relevantes.")
        L.append("Tesis intacta. Sin accion requerida.")
        L.append("")

    L.append("=" * 38)
    L.append("RUIDO FILTRADO: " + str(len(ruido_items)) + " noticias")
    if ruido_items:
        muestra = ruido_items if modo_auditoria else ruido_items[:MUESTRA_RUIDO]
        if not modo_auditoria and len(ruido_items) > MUESTRA_RUIDO:
            L.append("Muestra (" + str(MUESTRA_RUIDO) + " de " + str(len(ruido_items)) + "):")
        else:
            L.append("Titulares:")
        for r in muestra:
            L.append("  - " + r["titulo"][:90])

    if _errores:
        L.append(render_errores())

    if modo_auditoria:
        L.append("")
        L.append("FIN AUDITORIA — Para produccion:")
        L.append("DRY_RUN=False · HORAS_LOOKBACK=26")
    else:
        L.append("")
        L.append("Proxima ejecucion: manana 07:00 CET")
        L.append("Sistema: OK · v6.7 · " + fecha_now)

    return "\n".join(L)


# =============================================================================
# SECCIÓN 8 — MAIN
# =============================================================================

def monitor_noticias():
    fecha_now      = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
    modo_auditoria = DRY_RUN

    print("=" * 50)
    print("MONITOR NOTICIAS v6.7 · " + fecha_now)
    print("DRY_RUN=" + str(DRY_RUN) +
          " · HORAS_LOOKBACK=" + str(HORAS_LOOKBACK) +
          " · MODO=" + ("AUDITORIA" if modo_auditoria else "PRODUCCION"))
    print("=" * 50)

    os.makedirs(CARPETA, exist_ok=True)
    vistos = cargar_vistos()

    tickers_activos = {k: v for k, v in TICKERS_CONFIG.items()
                       if v.get("activo", False)}
    print("Tickers activos: " + ", ".join(tickers_activos.keys()))

    noticias_por_cat = {"cat1": [], "cat2": [], "cat3": [], "cat4": []}
    ruido_items      = []
    nuevos_vistos    = set()

    for ticker, config in tickers_activos.items():
        print("\n--- " + ticker + " · " + config["nombre"] + " ---")
        todas = []

        if config.get("sec_cik"):
            print("  Fetching SEC EDGAR...")
            sec = fetch_sec_8k(config["sec_cik"], nombre_empresa=config.get("nombre"))
            print("  SEC dentro de lookback: " + str(len(sec)))
            todas.extend(sec)

        for query in config.get("gnews_queries", []):
            gn = fetch_google_news(query)
            print("  Google News '" + query + "': " + str(len(gn)))
            todas.extend(gn)

        # BLS API — inyecta noticia clasificable si supera umbrales
        macro = fetch_macro_bls(config.get("macro_config"))
        if macro:
            print("  BLS: " + macro["periodo"] + " · " +
                  str(macro["valor"]) + " · " + macro["nivel"])
            valor      = macro.get("valor", 0)
            umbral_baja = macro.get("umbral_baja")
            umbral_cat  = macro.get("umbral_cat")
            if umbral_baja and valor < umbral_baja:
                todas.append({
                    "titulo":    "BLS Construction Employment " + macro["periodo"] +
                                 ": " + str(valor) + " — por debajo umbral alerta",
                    "enlace":    macro["url"],
                    "fecha_pub": datetime.now(timezone.utc),
                    "fuente":    "BLS API",
                    "ticker":    ticker,
                })
            elif umbral_cat and valor >= umbral_cat:
                todas.append({
                    "titulo":    "BLS Construction Employment " + macro["periodo"] +
                                 ": " + str(valor) + " — catalizador activado",
                    "enlace":    macro["url"],
                    "fecha_pub": datetime.now(timezone.utc),
                    "fuente":    "BLS API",
                    "ticker":    ticker,
                })

        print("  Total antes de deduplicar: " + str(len(todas)))

        for n in todas:
            h = hash_n(n["titulo"], n.get("fuente", ""))
            if h in vistos:
                continue
            nuevos_vistos.add(h)
            n["ticker"] = ticker

            cat, id_hito, desc_hito, accion_hito = clasificar(n["titulo"], config)
            n["id_hito"]     = id_hito
            n["desc_hito"]   = desc_hito
            n["accion_hito"] = accion_hito

            if cat == "ruido":
                ruido_items.append(n)
            else:
                noticias_por_cat[cat].append(n)
                hito_str = (" → Hito " + str(id_hito)) if id_hito else ""
                print("  [" + cat.upper() + hito_str + "] " + n["titulo"][:75])

    vistos.update(nuevos_vistos)
    if not DRY_RUN:
        guardar_vistos(vistos)

    print("\n" + "=" * 50)
    print("RESUMEN CLASIFICACION:")
    print("  Cat.1 Invalidacion : " + str(len(noticias_por_cat["cat1"])))
    print("  Cat.2 Catalizador  : " + str(len(noticias_por_cat["cat2"])))
    print("  Cat.3 Confirmacion : " + str(len(noticias_por_cat["cat3"])))
    print("  Cat.4 Manos fuertes: " + str(len(noticias_por_cat["cat4"])))
    print("  Ruido filtrado     : " + str(len(ruido_items)))
    print("  Errores sistema    : " + str(len(_errores)))
    print("  Cache URL hits     : " + str(len(_url_cache)))
    print("=" * 50)

    if modo_auditoria:
        print("\n--- AUDITORIA RUIDO COMPLETO ---")
        for r in ruido_items:
            print("  [RUIDO] " + r["titulo"][:90])
        print("--------------------------------")

    mensaje = render_mensaje(
        noticias_por_cat,
        list(tickers_activos.keys()),
        ruido_items,
        fecha_now,
        modo_auditoria,
    )

    print("\n--- MENSAJE TELEGRAM ---")
    print(mensaje)
    print("------------------------")

    if not DRY_RUN and ENVIAR_TELEGRAM:
        url_tg = "https://api.telegram.org/bot" + TOKEN + "/"

        # Alerta inmediata separada si hay invalidación de tesis
        if noticias_por_cat["cat1"]:
            alerta = (
                "ALERTA MAXIMA — INVALIDACION DE TESIS\n" +
                "=" * 38 + "\n" +
                "\n".join([
                    n["ticker"] + " [Hito " + str(n.get("id_hito", "?")) + "]: " + n["titulo"]
                    for n in noticias_por_cat["cat1"]
                ]) +
                "\n" + "=" * 38 + "\n"
                "Revisar posiciones en las proximas 48h."
            )
            try:
                requests.post(url_tg + "sendMessage",
                              data={"chat_id": CHAT_ID, "text": alerta},
                              timeout=15)
                print("Alerta Cat.1 enviada.")
            except Exception as e:
                registrar_error(
                    "Telegram — alerta Cat.1 no enviada",
                    e,
                    "Verificar TOKEN y CHAT_ID. Comprobar api.telegram.org."
                )

        # Mensaje diario consolidado — siempre se envía
        try:
            chunks = [mensaje[i:i+3900] for i in range(0, len(mensaje), 3900)]
            for i, c in enumerate(chunks):
                sfx = ("\n[" + str(i+1) + "/" + str(len(chunks)) + "]"
                       if len(chunks) > 1 else "")
                r = requests.post(url_tg + "sendMessage",
                                  data={"chat_id": CHAT_ID, "text": c + sfx},
                                  timeout=15)
                if r.status_code != 200:
                    raise Exception("HTTP " + str(r.status_code) + " — " + r.text[:100])
            print("Mensaje diario enviado.")
        except Exception as e:
            registrar_error(
                "Telegram — mensaje diario no enviado",
                e,
                "Verificar TOKEN y CHAT_ID. Si error 400, "
                "puede haber caracteres no permitidos en el mensaje."
            )
            # Intento de emergencia con mensaje mínimo
            try:
                requests.post(url_tg + "sendMessage",
                              data={"chat_id": CHAT_ID,
                                    "text": "MONITOR v6.7 ERROR — mensaje no enviado. "
                                            "Revisar logs GitHub Actions."},
                              timeout=15)
            except Exception:
                pass

    elif DRY_RUN:
        print("\n[AUDITORIA — Telegram no enviado]")
        print("Para produccion: DRY_RUN=False · HORAS_LOOKBACK=26")

    return mensaje


# =============================================================================
# EJECUCIÓN — con captura de excepción total
# Si el script muere antes de terminar, Telegram recibe un aviso de emergencia
# con el traceback y las instrucciones para diagnosticar el problema.
# =============================================================================
try:
    resultado = monitor_noticias()
except Exception as e:
    tb = traceback.format_exc()
    print("=" * 50)
    print("EXCEPCION TOTAL — script abortado")
    print(tb)
    print("=" * 50)
    if ENVIAR_TELEGRAM and not DRY_RUN:
        msg_error = (
            "MONITOR v6.7 — EXCEPCION TOTAL\n" +
            "=" * 30 + "\n" +
            str(e)[:300] + "\n" +
            "=" * 30 + "\n" +
            "Accion: GitHub Actions → pestaña Actions → ultimo run → ver logs.\n"
            "Si el runner no aparece: repositorio inactivo >60 dias sin commits "
            "desactiva el cron automaticamente."
        )
        enviar_telegram_directo(msg_error)
