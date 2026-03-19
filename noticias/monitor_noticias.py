# =============================================================================
# MONITOR NOTICIAS v6.14
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
# Cambios v6.14 — 19-mar-2026 — Generado con Claude Sonnet 4.6
#   · LULU keywords_cat1: validadas ("lulu","tariff") y ("lululemon","softer","2026")
#     Auditoría 720h confirmó señal real en ambas — eliminado flag "pendiente validación"
#     ("lulu","tariff") → "LULU Q4 Deep Dive: Tariffs..." capturado correctamente
#     ("lululemon","softer","2026") → "Lululemon forecasts softer 2026..." capturado correctamente
#   · LULU keywords_cat3: añadidas ("lululemon","founder","board") y ("lululemon","boardroom")
#     Auditoría 720h detectó falsos negativos:
#     "founder Wilson backs director exit, presses for board overhaul" → ruido (debería CAT3)
#     "founder escalates boardroom feud" → ruido (debería CAT3)
#     Causa: usan "founder" sin "fight/war/activism" y "boardroom" en lugar de "board"
#   · GLNG gnews_queries: eliminadas "Hilli Episeyo" y "Gimi BP GTA"
#     0 resultados en auditoría 720h — criterio de eliminación: 3 ejecuciones consecutivas con 0
#     Libera 2 slots — cobertura Hilli sigue activa via keywords_cat1/cat2/cat3 existentes
#   · PYPL: sin cambios — eco de 12 noticias Stripe/PayPal es comportamiento correcto
#     Mismo evento republicado en 12 medios, distintos titulares → no deduplicable por hash
#     En producción (26h lookback) el eco será de 1-2 noticias, no 12
#
# Cambios v6.13 — 19-mar-2026 — Generado con Claude Sonnet 4.6
#   · PYPL manos_fuertes: reconstruida desde 13F Q4 2025
#     Elliott disuelto ago-2023 confirmado · Starboard/ValueAct sin posición confirmada
#     Third Point sin posición en 13F 2024-2025
#     Lista actualizada: Vanguard, BlackRock, State Street, Capital Research, Norges Bank
#     Interpretación: ausencia de activistas no es señal negativa — tesis es contrarian.
#     El umbral $100M actúa como detector de cualquier activista nuevo que entre.
#     Próxima revisión recomendada: post-earnings 5-may-2026
#   · SQ gnews_queries: añadida "ARK Invest Block XYZ"
#     ARK redujo XYZ -$30M en Q4 2025 (confirmado) — gap de cobertura cerrado
#     Nota: 9 queries (una sobre el límite recomendado de 8). Candidata a eliminar
#     si "Afterpay BNPL regulation" sigue con 0 resultados en auditoría.
#   · LULU keywords_cat1: añadidas ("lulu","tariff") y ("lululemon","softer","2026")
#     Pendiente validación en auditoría 720h antes de confirmar señal/ruido
#   · clasificar(): eliminado código muerto — bloque duplicado inalcanzable tras return
#     No afectaba al comportamiento (CAT3 ya se evaluaba antes) pero generaba confusión
#
# Cambios v6.12 — 19-mar-2026 — Generado con Claude Sonnet 4.6
#   · SQ keywords_cat3: eliminado ("dorsey","block","strategy") y ("dorsey","block","ai")
#   · LULU keywords_cat1: añadidas keywords para análisis negativos post-earnings
#   · FISV Visa/Fiserv partnership: ya cae a ruido correctamente, sin cambios.
#   · keywords_cat1: eliminado ("ticker", "sec", "filing") en LULU, PYPL, FISV, SQ
#   · clasificar_manos_fuertes: corrección de falso positivo crítico con "vest"
#
# Cambios v6.9 — 18-mar-2026 — Generado con Claude Sonnet 4.6
#   · clasificar_manos_fuertes: filtro explícito de ventas rutinarias de insiders
#
# Cambios v6.8 — 18-mar-2026 — Generado con Claude Sonnet 4.6
#   · TICKERS_CONFIG: añadidos PYPL, FISV y SQ (portfolio fintech US)
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
#      CADENCIA OBLIGATORIA: trimestral — los 13F se publican 45 días después
#      del cierre de trimestre. Validar antes de cada earnings crítico.
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

TOKEN           = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID         = "8351044609"
ENVIAR_TELEGRAM = True
# =============================================================================
# REGLA DE ENTREGA — FLAGS DE MODO
# -----------------------------------------------------------------------------
# Todo script generado o modificado por un agente IA se entrega SIEMPRE en
# modo auditoría. El paso a producción es una decisión humana explícita.
#
# AUDITORÍA (estado por defecto al entregar):
#   DRY_RUN        = True   ← nunca envía Telegram, no guarda vistos
#   HORAS_LOOKBACK = 720    ← 30 días — para calibrar y validar keywords
#
# PRODUCCIÓN (cambio manual antes de subir a GitHub):
#   DRY_RUN        = False
#   HORAS_LOOKBACK = 26     ← ventana de 26h — una ejecución diaria
# =============================================================================
DRY_RUN         = True   # ← AUDITORÍA — cambiar a False solo para producción
HORAS_LOOKBACK  = 720    # ← AUDITORÍA — cambiar a 26 solo para producción
MUESTRA_RUIDO   = 3

CARPETA     = "noticias"
RUTA_VISTOS = os.path.join(CARPETA, "noticias_vistas.json")

SEC_HEADERS = {
    "User-Agent":      "Portfolio Monitor monitor@portfolio.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept":          "application/atom+xml,application/xml,text/xml",
    "Host":            "www.sec.gov",
}


# =============================================================================
# SECCIÓN 2 — TICKERS CONFIG
# =============================================================================

TICKERS_CONFIG = {

    "GLNG": {
        "nombre":         "Golar LNG",
        "activo":         True,
        "precio_entrada": 46.25,
        "moneda":         "USD",
        "sec_cik":        "0001166663",

        # v6.14 — eliminadas "Hilli Episeyo" y "Gimi BP GTA" (0 resultados en auditoría 720h)
        # Cobertura de Hilli y Gimi se mantiene via keywords_cat1/cat2/cat3 existentes
        "gnews_queries": [
            "Golar LNG contract",
            "Golar LNG FLNG",
            "SESA Argentina LNG",
            "GLNG stock",
        ],

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
            ("golar", "fourth", "flng"):      (None, "4a unidad FLNG — decision pendiente",    "Leer — si FID confirmado actualizar tesis"),
            ("golar", "fourth", "unit"):      (None, "4a unidad FLNG — decision pendiente",    "Leer — si FID confirmado actualizar tesis"),
            ("golar", "4th",    "flng"):      (None, "4a unidad FLNG — decision pendiente",    "Leer — si FID confirmado actualizar tesis"),
        },

        "keywords_cat3": [
            ("golar",  "earnings"),
            ("golar",  "results"),
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
            ("golar",  "buy", "rating"),
            ("golar",  "buy", "upgrade"),
            ("hilli",  "cargo"),
            ("hilli",  "production"),
            ("hilli",  "uptime"),
            ("golar",  "investor", "day"),
            ("golar",  "investor", "presenta"),
            ("glng",   "down", "today"),
            ("golar",  "rating"),
            ("glng",   "rating"),
            ("glng",   "setup"),
            ("golar",  "margin"),
            ("glng",   "trading down"),
            ("glng",   "falling"),
        ],

        "keywords_cat3_hitos": {
            ("golar", "earnings"):           (2, "FCF guidance 2025 confirmado",       "Leer earnings — actualizar hito 2 si FCF >400M"),
            ("golar", "results"):            (2, "FCF guidance 2025 confirmado",       "Leer results — actualizar hito 2 si FCF >400M"),
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
            ("golar", "buy", "rating"):      (None, "Rating Buy de analista",          "Sin accion requerida"),
            ("golar", "buy", "upgrade"):     (None, "Upgrade a Buy de analista",       "Sin accion requerida"),
            ("golar", "investor", "day"):    (None, "Investor Day corporativo",        "Leer — puede incluir guidance nuevo"),
            ("golar", "investor", "presenta"):(None,"Presentacion a inversores",       "Leer — puede incluir guidance nuevo"),
            ("glng",  "down", "today"):      (None, "Caida precio hoy — leer causa",   "Leer — verificar si hay noticia detras"),
            ("glng",  "rating"):             (None, "Rating tecnico",                  "Sin accion requerida"),
            ("glng",  "setup"):              (None, "Setup tecnico",                   "Sin accion requerida"),
            ("golar", "margin"):             (None, "Analisis margen fundamental",     "Leer — puede afectar tesis FCF"),
            ("glng",  "trading down"):       (None, "Caida precio — leer causa",       "Leer — verificar si hay noticia detras"),
            ("glng",  "falling"):            (None, "Caida precio — leer causa",       "Leer — verificar si hay noticia detras"),
        },

        "manos_fuertes": {
            "rubric":        ("Rubric Capital Management",  0,          "Mayor accionista ~9% · $378M"),
            "pointstate":    ("PointState Capital",         0,          "Aumento 19% Q4 2025 · $146M"),
            "t. rowe":       ("T. Rowe Price",              0,          "Entrada masiva +253% Q4 2025 · $85M"),
            "cartenna":      ("Cartenna Capital",           0,          "Top 10 accionista · $77M"),
            "morgan stanley":("Morgan Stanley",             50_000_000, "Institucional sistémico · $78M"),
        },

        "manos_fuertes_umbral_usd": 50_000_000,
        "macro_config": None,
    },


    # =========================================================================
    # LULU — Lululemon Athletica
    # =========================================================================
    "LULU": {
        "nombre":         "Lululemon Athletica",
        "activo":         True,
        "precio_entrada": 159.27,
        "moneda":         "USD",
        "sec_cik":        "0001397187",

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

        "keywords_cat1": [
            ("wilson",       "withdraw"),
            ("wilson",       "drops",       "bid"),
            ("wilson",       "loses",       "vote"),
            ("wilson",       "settlement",  "lululemon"),
            ("lululemon",    "proxy",       "defeat"),
            ("lululemon",    "board",       "rejects",  "wilson"),
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
            ("lululemon",    "market share",  "loss"),
            ("lululemon",    "closing",       "stores"),
            ("lululemon",    "tariff"),
            ("lululemon",    "margin",        "pressure"),
            ("lululemon",    "muted",         "outlook"),
            ("lululemon",    "muted",         "growth"),
            ("lululemon",    "softer",        "outlook"),
            ("lululemon",    "weaker",        "outlook"),
            # v6.14 — validadas en auditoría 720h · señal real confirmada
            ("lulu",         "tariff"),           # "LULU Q4 Deep Dive: Tariffs..." ✓
            ("lululemon",    "softer",  "2026"),   # "Lululemon forecasts softer 2026..." ✓
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
            ("lululemon",    "tariff"):                        (2, "Suelo financiero — presión arancelaria",  "Cuantificar impacto en margen bruto — umbral crítico 52%"),
            ("lululemon",    "margin",     "pressure"):        (2, "Suelo financiero — margen bajo presión",  "Verificar si dato es nuevo o referencia a Q4 — umbral 52%"),
            ("lululemon",    "muted",      "outlook"):         (2, "Suelo financiero — outlook débil",        "Leer — evaluar si cambia BPA forward bajo $9"),
            ("lululemon",    "muted",      "growth"):          (2, "Suelo financiero — crecimiento débil",    "Leer — verificar si es guidance nueva o análisis de consenso"),
            ("lululemon",    "softer",     "outlook"):         (2, "Suelo financiero — outlook suavizado",    "Leer — evaluar magnitud vs umbral $9 BPA"),
            ("lululemon",    "weaker",     "outlook"):         (2, "Suelo financiero — outlook débil",        "Leer — evaluar si cambia BPA forward bajo $9"),
            # v6.14 — validadas en auditoría 720h
            ("lulu",         "tariff"):                        (2, "Suelo financiero — presión arancelaria (LULU)",  "Cuantificar impacto en margen bruto — umbral crítico 52%"),
            ("lululemon",    "softer",     "2026"):            (2, "Suelo financiero — outlook 2026 débil",          "Leer — evaluar magnitud vs umbral $9 BPA"),
        },

        "keywords_cat2": [
            ("wilson",       "wins",       "board"),
            ("wilson",       "elected",    "director"),
            ("wilson",       "board",      "seat"),
            ("lululemon",    "new",        "director",  "wilson"),
            ("lululemon",    "board",      "change"),
            ("lululemon",    "appoints",   "ceo"),
            ("lululemon",    "names",      "ceo"),
            ("lululemon",    "hires",      "ceo"),
            ("lululemon",    "new",        "ceo",        "named"),
            ("lululemon",    "new",        "ceo",        "appoint"),
            ("lululemon",    "joins",      "board"),
            ("lululemon",    "new",        "director"),
            ("lululemon",    "tapped",     "board"),
            ("lululemon",    "board",      "appoints"),
            ("lululemon",    "activist",   "investor"),
            ("lululemon",    "activist",   "turnaround"),
            ("lululemon",    "americas",   "growth"),
            ("lululemon",    "comparable", "positive"),
            ("lululemon",    "same store", "growth"),
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
            ("lululemon",    "appoints",  "ceo"):            (3, "Nuevo CEO externo con mandato turnaround", "Confirmar perfil — interno vs externo es clave"),
            ("lululemon",    "names",     "ceo"):             (3, "Nuevo CEO externo con mandato turnaround", "Confirmar perfil — interno vs externo es clave"),
            ("lululemon",    "hires",     "ceo"):             (3, "Nuevo CEO externo con mandato turnaround", "Confirmar perfil — interno vs externo es clave"),
            ("lululemon",    "new",       "ceo",    "named"): (3, "Nuevo CEO externo con mandato turnaround", "Confirmar perfil — interno vs externo es clave"),
            ("lululemon",    "new",       "ceo",   "appoint"): (3, "Nuevo CEO externo con mandato turnaround", "Confirmar perfil — interno vs externo es clave"),
            ("lululemon",    "joins",     "board"):          (1, "Wilson/board — cambio composición",       "Leer — evaluar si el nuevo director es candidato Wilson o del board actual"),
            ("lululemon",    "new",       "director"):       (1, "Wilson/board — cambio composición",       "Leer — evaluar alineación con tesis catalizador"),
            ("lululemon",    "tapped",    "board"):          (1, "Wilson/board — cambio composición",       "Leer — evaluar si es candidato Wilson o del board actual"),
            ("lululemon",    "board",     "appoints"):       (1, "Wilson/board — cambio composición",       "Leer — evaluar alineación con tesis catalizador"),
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
            ("wilson",       "lululemon",   "stake"),
            ("wilson",       "lululemon",   "letter"),
            ("chip wilson",  "lululemon"),
            ("lululemon",    "founder",     "war"),
            ("lululemon",    "founder",     "fight"),
            ("lululemon",    "founder",     "activism"),
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
            ("wilson",       "lululemon",   "notice"),
            ("wilson",       "lululemon",   "ceo"),
            ("wilson",       "lululemon",   "candidate"),
            # v6.14 — falsos negativos detectados en auditoría 720h
            # "founder Wilson backs director exit, presses for board overhaul" → caía a ruido
            # "founder escalates boardroom feud" → caía a ruido
            ("lululemon",    "founder",     "board"),     # "founder presses for board overhaul"
            ("lululemon",    "boardroom"),                 # "founder escalates boardroom feud"
        ],

        "keywords_cat3_hitos": {
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
            ("wilson",       "lululemon",   "notice"):    (1, "Wilson/board — aviso público",           "Leer — Wilson poniendo a alguien on notice es señal de escalada"),
            ("wilson",       "lululemon",   "ceo"):       (1, "Wilson/board — Wilson y CEO search",     "Leer — Wilson involucrándose en CEO search es catalizador potencial"),
            ("wilson",       "lululemon",   "candidate"): (1, "Wilson/board — candidatos CEO",          "Leer — Wilson evaluando candidatos es señal de influencia creciente"),
            # v6.14 — nuevas keywords para falsos negativos detectados en auditoría
            ("lululemon",    "founder",     "board"):     (1, "Wilson/board — founder vs board",        "Leer — founder presionando sobre composición del board"),
            ("lululemon",    "boardroom"):                 (1, "Wilson/board — conflicto boardroom",     "Leer — seguimiento escalada del proxy fight"),
            ("lululemon",    "shareholder", "meeting"): (1, "Wilson/board — junta accionistas",        "Anotar fecha y agenda — hito 1 depende de este evento"),
            ("lululemon",    "annual",      "meeting"): (1, "Wilson/board — junta accionistas",        "Anotar fecha y agenda — hito 1 depende de este evento"),
            ("lululemon",    "gross margin"):          (2, "Suelo financiero — margen bruto",          "Confirmar nivel — umbral crítico 52%"),
            ("lululemon",    "comparable", "sales"):   (4, "Comp. sales Américas — seguimiento",       "Anotar valor exacto — umbral catalizador +2%"),
            ("lululemon",    "americas",   "revenue"): (4, "Comp. sales Américas — seguimiento",       "Anotar evolución — indicador de recuperación"),
            ("lululemon",    "earnings"):              (5, "Earnings Q — revisión trimestral",         "Extraer: comp sales Américas, margen bruto, guidance"),
            ("lululemon",    "results"):               (5, "Earnings Q — revisión trimestral",         "Extraer: comp sales Américas, margen bruto, guidance"),
            ("lululemon",    "beat",   "earnings"):    (5, "Earnings Q — revisión trimestral",         "Beat confirmado — verificar si mejora guidance"),
            ("lululemon",    "beat",   "estimate"):    (5, "Earnings Q — revisión trimestral",         "Beat confirmado — verificar si mejora guidance"),
            ("lululemon",    "ebitda"):                (5, "Earnings Q — revisión trimestral",         "Leer — umbral vigilancia EBITDA margin 28%"),
            ("lululemon",    "china",      "growth"):  (6, "China — motor de crecimiento",             "Confirmar si sigue >+15% — palanca de mix"),
            ("lululemon",    "upgrade"):               (None, "Upgrade analista",                      "Sin acción requerida"),
            ("lululemon",    "price target"):          (None, "Cambio precio objetivo",                "Sin acción requerida"),
            ("lululemon",    "buy",   "rating"):       (None, "Rating Buy de analista",                "Sin acción requerida"),
            ("lulu",         "dividend"):              (None, "Dividendo — LULU no paga actualmente",  "Si anuncia dividendo → señal de madurez · leer"),
        },

        "manos_fuertes": {
            "blackrock":     ("BlackRock",                       50_000_000, "Mayor institucional pasivo ~9% float"),
            "vanguard":      ("Vanguard Group",                  50_000_000, "Institucional pasivo ~8% float"),
            "fidelity":      ("Fidelity Investments",            50_000_000, "Institucional activo — seguimiento"),
        },

        "manos_fuertes_umbral_usd": 50_000_000,
        "macro_config": None,
    },


    # =========================================================================
    # PYPL — PayPal Holdings
    # =========================================================================
    "PYPL": {
        "nombre":         "PayPal Holdings",
        "activo":         True,
        "precio_entrada": 53.31,
        "moneda":         "USD",
        "sec_cik":        "0001410247",

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

        "keywords_cat1": [
            ("paypal",   "branded",     "decline"),
            ("paypal",   "branded",     "negative"),
            ("paypal",   "checkout",    "losing",   "share"),
            ("paypal",   "checkout",    "market share", "loss"),
            ("paypal",   "transaction", "margin",   "decline"),
            ("paypal",   "transaction", "margin",   "negative"),
            ("paypal",   "take rate",   "drop"),
            ("paypal",   "lores",       "no guidance"),
            ("paypal",   "withdraws",   "guidance"),
            ("paypal",   "guidance",    "withdrawn"),
            ("paypal",   "ceo",         "resign"),
            ("paypal",   "ceo",         "departs"),
            ("paypal",   "sec",         "investigation"),
            ("paypal",   "doj",         "investigation"),
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
            ("paypal",   "doj",         "investigation"):      (None, "DOJ — investigación",                    "Revisar alcance — puede ser material para la tesis"),
            ("paypal",   "apple pay",   "surpass"):            (1, "Apple Pay supera PayPal checkout",          "Dato cuantificado de cuota — confirmar fuente primaria"),
            ("paypal",   "losing",      "merchants"):          (1, "Merchants abandonando PayPal",              "Cuantificar escala — pérdida masiva invalida moat"),
            ("paypal",   "merchant",    "migration"):          (1, "Migración comerciantes a competidor",       "Identificar destino — Stripe/Adyen implica pérdida estructural"),
        },

        "keywords_cat2": [
            ("paypal",   "branded",     "accelerat"),
            ("paypal",   "branded",     "growth",   "accelerat"),
            ("paypal",   "checkout",    "growth",   "positive"),
            ("fastlane", "paypal",      "growth"),
            ("fastlane", "paypal",      "traction"),
            ("paypal",   "fastlane",    "merchant"),
            ("paypal",   "fastlane",    "expand"),
            ("paypal",   "acquisition"),
            ("paypal",   "acquire"),
            ("stripe",   "paypal",      "deal"),
            ("stripe",   "paypal",      "merger"),
            ("stripe",   "paypal",      "acqui"),
            ("pyusd",    "volume"),
            ("pyusd",    "adoption"),
            ("paypal",   "stablecoin",  "growth"),
            ("paypal",   "openai",      "payment"),
            ("paypal",   "ai",          "checkout"),
            ("paypal",   "agentic",     "commerce"),
            ("venmo",    "revenue",     "growth"),
            ("venmo",    "monetiz"),
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
            ("lores",    "paypal",      "strategy"),
            ("lores",    "paypal",      "plan"),
            ("lores",    "paypal",      "guidance"),
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
        # v6.13 — Reconstruida desde 13F Q4 2025 · 19-mar-2026
        # ELIMINADOS: Elliott (salió ago-2023 confirmado), Starboard (sin posición
        # en 13F 2024-2025), ValueAct (sin posición confirmada), Jana (sin posición
        # en PYPL), Third Point/Dan Loeb (sin posición en 13F 2024-2025).
        # AÑADIDOS: State Street, Capital Research Global, Norges Bank.
        # Norges Bank: mayor comprador neto Q4 2025 (+16M shares) — señal relevante.
        #
        # INTERPRETACIÓN DE LA AUSENCIA DE ACTIVISTAS:
        # No es señal negativa — la tesis es contrarian precisamente porque el mercado
        # no la ve. Si hubiera activista, el precio ya reflejaría parte de la presión.
        # El umbral $100M actúa como detector automático de cualquier activista nuevo.
        # Si Elliott u otro fondo entra con $200M+ en 13F → el umbral lo captura.
        #
        # Próxima revisión: post-earnings 5-may-2026
        # URL EDGAR: https://www.sec.gov/cgi-bin/browse-edgar
        #            ?action=getcompany&type=13F&CIK=0001410247
        "manos_fuertes": {
            "vanguard":        ("Vanguard Group",           100_000_000, "Mayor institucional ~9.3% float · Q4 2025 90M shares"),
            "blackrock":       ("BlackRock",                100_000_000, "Institucional ~7.5% float · Q4 2025 72M shares"),
            "state street":    ("State Street Corp",         75_000_000, "Institucional ~4.4% float · Q4 2025 42M shares"),
            "capital research":("Capital Research Global",   75_000_000, "Institucional activo · Q4 2025 27M shares"),
            "norges":          ("Norges Bank",               50_000_000, "Banco central noruego · mayor comprador Q4 2025 +16M shares"),
        },

        "manos_fuertes_umbral_usd": 100_000_000,
        "macro_config": None,
    },


    # =========================================================================
    # FISV — Fiserv
    # =========================================================================
    "FISV": {
        "nombre":         "Fiserv",
        "activo":         True,
        "precio_entrada": 66.95,
        "moneda":         "USD",
        "sec_cik":        "0000798354",

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

        "keywords_cat1": [
            ("fiserv",   "bank",        "contract",   "loss"),
            ("fiserv",   "bank",        "loses",      "contract"),
            ("fiserv",   "loses",       "bank"),
            ("fiserv",   "bank",        "switch"),
            ("fiserv",   "bank",        "migrat",     "away"),
            ("fiserv",   "core",        "banking",    "loses"),
            ("fiserv",   "financial solutions", "decline"),
            ("fiserv",   "financial solutions", "negative"),
            ("financial solutions", "fiserv",   "miss"),
            ("fiserv",   "debt",        "covenant"),
            ("fiserv",   "downgrade",   "credit"),
            ("fiserv",   "debt",        "refinanc",   "risk"),
            ("jana",     "fiserv",      "lyons",      "replace"),
            ("jana",     "fiserv",      "ceo",        "change"),
            ("jana",     "fiserv",      "management", "change"),
            ("thought machine",  "wins",    "bank"),
            ("mambu",            "wins",    "bank",    "fiserv"),
            ("temenos",          "replace", "fiserv"),
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
            ("fiserv",   "sec",         "investigation"):         (None, "SEC — investigación regulatoria",       "Leer alcance — puede ser material o rutinario"),
        },

        "keywords_cat2": [
            ("fiserv",   "financial solutions", "growth"),
            ("fiserv",   "financial solutions", "recover"),
            ("fiserv",   "financial solutions", "positive"),
            ("fiserv",   "banking",     "win",   "contract"),
            ("fiserv",   "bank",        "new",   "contract"),
            ("fiserv",   "wins",        "bank",  "deal"),
            ("clover",   "fiserv",      "growth",    "accelerat"),
            ("clover",   "revenue",     "beat"),
            ("clover",   "merchant",    "expand"),
            ("clover",   "smb",         "growth"),
            ("fiusd",    "fiserv"),
            ("fiserv",   "stablecoin",  "launch"),
            ("fiserv",   "stablecoin",  "bank"),
            ("jana",     "fiserv",      "metrics"),
            ("jana",     "fiserv",      "transparency"),
            ("jana",     "fiserv",      "value"),
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
            ("jana",     "fiserv",      "support"),
            ("jana",     "fiserv",      "lyons"),
            ("lyons",    "fiserv",      "guidance"),
            ("lyons",    "fiserv",      "outlook"),
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
    "SQ": {
        "nombre":         "Block (XYZ)",
        "activo":         True,
        "precio_entrada": 55.24,
        "moneda":         "USD",
        "sec_cik":        "0001512673",

        # v6.13 — añadida "ARK Invest Block XYZ"
        # ARK redujo XYZ -$30M en Q4 2025 (confirmado en 13F feb-2026)
        # Gap de cobertura identificado en auditoría 19-mar-2026 — cerrado.
        # Nota: 9 queries (una sobre el límite recomendado de 8).
        # Candidata a eliminar si "Afterpay BNPL regulation" sigue con 0
        # resultados en la próxima auditoría 720h.
        "gnews_queries": [
            "Block Afterpay delinquency credit loss",
            "Block SQ earnings EPS guidance",
            "Cash App revenue ARPU growth",
            "Square GPV merchant growth",
            "Jack Dorsey Block strategy AI",
            "SQ XYZ stock results",
            "Block buyback repurchase",
            "Afterpay BNPL regulation",
            "ARK Invest Block XYZ",          # v6.13 — gap de cobertura cerrado
        ],

        "keywords_cat1": [
            ("afterpay",   "delinquency",  "rise"),
            ("afterpay",   "delinquency",  "above",  "target"),
            ("afterpay",   "credit loss",  "exceed"),
            ("afterpay",   "charge-off",   "rise"),
            ("block",      "borrow",       "loss",    "target"),
            ("block",      "credit",       "loss",    "exceed"),
            ("afterpay",   "default",      "rate",    "high"),
            ("afterpay",   "regulat",      "action"),
            ("afterpay",   "state",        "attorney", "general"),
            ("afterpay",   "settlement",   "million"),
            ("block",      "afterpay",     "regulat",  "fine"),
            ("block",      "eps",          "miss",    "guidance"),
            ("block",      "misses",       "guidance"),
            ("sq",         "guidance",     "cut"),
            ("block",      "guidance",     "lower"),
            ("block",      "rule of 40",   "miss"),
            ("dorsey",     "block",        "resign"),
            ("dorsey",     "leaves",       "block"),
            ("block",      "bitcoin",      "impairment"),
            ("block",      "btc",          "writedown"),
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
            ("block",      "sec",          "investigation"):      (None, "SEC — investigación",                  "Leer alcance — puede ser material o rutinario"),
        },

        "keywords_cat2": [
            ("block",      "beats",        "guidance"),
            ("block",      "eps",          "beat"),
            ("block",      "raises",       "guidance"),
            ("block",      "guidance",     "raise"),
            ("block",      "rule of 40",   "sustain"),
            ("block",      "rule of 40",   "exceed"),
            ("cash app",   "arpu",         "growth"),
            ("cash app",   "revenue",      "accelerat"),
            ("cash app",   "monetiz"),
            ("block",      "closed loop",  "revenue"),
            ("cash app",   "square",       "integrat"),
            ("block",      "buyback",      "execut"),
            ("block",      "repurchase",   "accelerat"),
            ("sq",         "buyback",      "billion"),
            ("afterpay",   "delinquency",  "stable"),
            ("afterpay",   "credit",       "improv"),
            ("afterpay",   "loss",         "below",  "target"),
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
            ("sq",         "down",      "today"):        (None, "Caída precio hoy — verificar causa",   "Leer — BTC puede causar caídas sin fundamento operativo"),
            ("sq",         "falling"):                   (None, "Caída precio — verificar causa",       "Distinguir si es BTC/macro vs noticia operativa real"),
            ("sq",         "rally"):                     (None, "Subida precio — verificar causa",      "Leer — si hay catalizador operativo actualizar convicción"),
        },

        "manos_fuertes": {
            "ark":           ("ARK Investment",          0,           "Cathie Wood — cualquier movimiento es señal · redujo -$30M Q4 2025"),
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

_errores = []


def registrar_error(contexto, detalle, sugerencia=""):
    _errores.append({
        "contexto":   contexto,
        "detalle":    str(detalle)[:200],
        "sugerencia": sugerencia,
    })
    print("  [ERROR] " + contexto + ": " + str(detalle)[:120])


def enviar_telegram_directo(texto, token=None, chat_id=None):
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

_url_cache = {}


def resolver_url(url_google, timeout=8):
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
        tracking_params = {"utm_source", "utm_medium", "utm_campaign",
                           "utm_term", "utm_content", "ref", "src"}
        if "?" in url_final:
            base, qs = url_final.split("?", 1)
            params_limpios = [p for p in qs.split("&")
                              if p.split("=")[0] not in tracking_params]
            url_final = base + ("?" + "&".join(params_limpios) if params_limpios else "")
        if "news.google.com" in url_final:
            _url_cache[url_google] = url_google
            return url_google
        _url_cache[url_google] = url_final
        return url_final
    except Exception as e:
        registrar_error(
            "resolver_url", e,
            "Comprobar conectividad en GitHub Actions."
        )
        _url_cache[url_google] = url_google
        return url_google


def fetch_sec_8k(cik, horas=None, nombre_empresa=None):
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
                if nombre_empresa and titulo.strip().lower().startswith("8-k"):
                    titulo = nombre_empresa + " 8-K SEC filing - " + titulo.strip()
                resultados.append({
                    "titulo":    titulo,
                    "enlace":    entry.link,
                    "fecha_pub": fecha,
                    "fuente":    "SEC EDGAR 8-K",
                    "ticker":    None,
                })
    except Exception as e:
        registrar_error(
            "SEC EDGAR · CIK " + cik, e,
            "Verificar CIK en TICKERS_CONFIG."
        )
    return resultados


def fetch_google_news(query, horas=None):
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
                "Puede ser bloqueo temporal o query demasiado especifica."
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
        registrar_error("Google News · '" + query + "'", e,
                        "Comprobar conectividad.")
    return resultados


def fetch_macro_bls(config):
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
            raise Exception("BLS API status: " + data.get("status", "desconocido"))
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
        registrar_error("BLS API · serie " + serie, e,
                        "Verificar: https://api.bls.gov/publicAPI/v1/timeseries/data/" + serie)
        return None


# =============================================================================
# SECCIÓN 5 — CLASIFICADOR
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
    tn = normalizar(titulo)
    for tupla, hito_info in hitos_dict.items():
        if all(k.lower() in tn for k in tupla):
            return hito_info
    return (None, "Sin hito asignado", "Sin accion requerida")


def extraer_millones_usd(titulo):
    tn    = normalizar(titulo)
    words = tn.split()
    for i, w in enumerate(words):
        if w.startswith("$"):
            num_str = w[1:].replace("m", "").replace("b", "")
            try:
                num = float(num_str)
                siguiente = words[i + 1] if i + 1 < len(words) else ""
                if "billion" in siguiente or w.endswith("b"):
                    return num * 1_000_000_000
                return num * 1_000_000
            except ValueError:
                continue
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
    manos        = config.get("manos_fuertes", {})
    umbral       = config.get("manos_fuertes_umbral_usd", 50_000_000)
    tn           = normalizar(titulo)

    EXCLUSIONES_SUBCADENA = (
        "rsu", "restricted stock", "tax withhold", "withholding",
        "10b5", "10b5-1", "trading plan", "vesting",
        "option exercise", "option ex", "derivative",
        "layoff", "layoffs", "cuts job", "job cut", "workforce",
        "thousands of job", "hundreds of job", "cut staff", "slashes staff",
        "ai strategy", "ai tool", "embrace ai", "ai model",
        "apocalypse", "debate", "warns", "warning",
        "praises", "argues", "suggests",
        "interview", "tweet", "statement",
        "pushes smaller", "pushes leaner", "pushes flatter", "pushes ai",
        "embraces ai", "leans on ai",
    )
    EXCLUSIONES_PALABRA = ("vest", "post", "says", "fears")

    palabras_tn = set(tn.split())

    if (any(excl in tn for excl in EXCLUSIONES_SUBCADENA) or
            any(excl in palabras_tn for excl in EXCLUSIONES_PALABRA)):
        return (False, "", "")

    for clave, (nombre, umbral_fondo, razon) in manos.items():
        if clave.lower() in tn:
            cantidad = extraer_millones_usd(titulo)
            if umbral_fondo == 0 or cantidad >= umbral_fondo:
                return (
                    True,
                    "Mano fuerte: " + nombre + " — " + razon,
                    "Verificar direccion del movimiento (compra/venta) y magnitud"
                )

    cantidad = extraer_millones_usd(titulo)
    if cantidad >= umbral:
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

    CAT4 evalúa ANTES que CAT3 — una compra de mano fuerte es más accionable
    que una confirmación de tesis.

    v6.13: eliminado bloque de código muerto que aparecía tras el return final.
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


# =============================================================================
# SECCIÓN 6 — DEDUPLICACIÓN
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
    L = []
    L.append("TICKER: " + n["ticker"])
    L.append(n["titulo"][:120])
    L.append("Fuente: " + n["fuente"] + " · " + hace(n["fecha_pub"]))
    enlace = n["enlace"]
    L.append("-> " + enlace)
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
    L.append("MONITOR NOTICIAS v6.14 · " + fecha_now)
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
        L.append("Sistema: OK · v6.14 · " + fecha_now)

    return "\n".join(L)


# =============================================================================
# SECCIÓN 8 — MAIN
# =============================================================================

def monitor_noticias():
    fecha_now      = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
    modo_auditoria = DRY_RUN

    print("=" * 50)
    print("MONITOR NOTICIAS v6.14 · " + fecha_now)
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
                registrar_error("Telegram — alerta Cat.1 no enviada", e,
                                "Verificar TOKEN y CHAT_ID.")

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
            registrar_error("Telegram — mensaje diario no enviado", e,
                            "Verificar TOKEN y CHAT_ID.")
            try:
                requests.post(url_tg + "sendMessage",
                              data={"chat_id": CHAT_ID,
                                    "text": "MONITOR v6.14 ERROR — mensaje no enviado. "
                                            "Revisar logs GitHub Actions."},
                              timeout=15)
            except Exception:
                pass

    elif DRY_RUN:
        print("\n[AUDITORIA — Telegram no enviado]")
        print("Para produccion: DRY_RUN=False · HORAS_LOOKBACK=26")

    return mensaje


# =============================================================================
# EJECUCIÓN
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
            "MONITOR v6.14 — EXCEPCION TOTAL\n" +
            "=" * 30 + "\n" +
            str(e)[:300] + "\n" +
            "=" * 30 + "\n" +
            "Accion: GitHub Actions → pestaña Actions → ultimo run → ver logs.\n"
        )
        enviar_telegram_directo(msg_error)
