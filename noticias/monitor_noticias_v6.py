# =============================================================================
# MONITOR NOTICIAS v6.1
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
DRY_RUN         = True    # ← True = auditoría · False = producción
HORAS_LOOKBACK  = 720     # ← 720 para refinamiento · 26 para producción
MUESTRA_RUIDO   = 3       # Titulares de ruido visibles en producción

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


def fetch_sec_8k(cik, horas=None):
    """
    SEC EDGAR RSS — 8-K filings regulatorios.
    Funciona en GitHub Actions. En Colab puede devolver 0 por bloqueo de IP.
    CIK de cada ticker en TICKERS_CONFIG · sec_cik.
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
                resultados.append({
                    "titulo":    entry.title,
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
    """
    manos        = config.get("manos_fuertes", {})
    umbral       = config.get("manos_fuertes_umbral_usd", 50_000_000)
    tn           = normalizar(titulo)

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
    """Renderiza una noticia con hito o contexto según categoría."""
    L = []
    L.append("TICKER: " + n["ticker"])
    L.append(n["titulo"][:120])
    L.append("Fuente: " + n["fuente"] + " · " + hace(n["fecha_pub"]))
    L.append("-> " + n["enlace"])  # URL completa — sin truncar

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
    L.append("MONITOR NOTICIAS v6.1 · " + fecha_now)
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
        L.append("Sistema: OK · v6.1 · " + fecha_now)

    return "\n".join(L)


# =============================================================================
# SECCIÓN 8 — MAIN
# =============================================================================

def monitor_noticias():
    fecha_now      = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
    modo_auditoria = DRY_RUN

    print("=" * 50)
    print("MONITOR NOTICIAS v6.1 · " + fecha_now)
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
            sec = fetch_sec_8k(config["sec_cik"])
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
                                    "text": "MONITOR v6.1 ERROR — mensaje no enviado. "
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
            "MONITOR v6.1 — EXCEPCION TOTAL\n" +
            "=" * 30 + "\n" +
            str(e)[:300] + "\n" +
            "=" * 30 + "\n" +
            "Accion: GitHub Actions → pestaña Actions → ultimo run → ver logs.\n"
            "Si el runner no aparece: repositorio inactivo >60 dias sin commits "
            "desactiva el cron automaticamente."
        )
        enviar_telegram_directo(msg_error)
