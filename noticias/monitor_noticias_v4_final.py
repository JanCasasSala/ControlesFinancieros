import subprocess, sys

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

for pkg, imp in [("feedparser","feedparser"),("requests","requests"),("beautifulsoup4","bs4")]:
    try:
        __import__(imp)
    except ImportError:
        install(pkg)

import feedparser
import requests
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

try:
    from google.colab import output
    EN_COLAB = True
except ImportError:
    EN_COLAB = False

EN_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

# =============================================================================
# SECCION 1 — CONFIGURACION
# -----------------------------------------------------------------------------
# DRY_RUN = True  → modo auditoría: imprime todo, muestra ruido completo,
#                   no envía Telegram, no guarda vistos.
#                   Usar para refinamiento de keywords (HORAS_LOOKBACK = 720).
# DRY_RUN = False → modo producción: envía Telegram, guarda vistos,
#                   solo muestra 3 titulares de ruido como muestra.
#                   Usar con HORAS_LOOKBACK = 26.
# =============================================================================

TOKEN           = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID         = "8351044609"
ENVIAR_TELEGRAM = True
DRY_RUN         = True    # ← True = auditoría · False = producción
HORAS_LOOKBACK  = 240     # ← 720 para refinamiento · 26 para producción
MUESTRA_RUIDO   = 3       # Titulares de ruido visibles en producción

CARPETA     = "noticias"
RUTA_VISTOS = os.path.join(CARPETA, "noticias_vistas.json")

SEC_HEADERS = {
    "User-Agent":      "Portfolio Monitor monitor@portfolio.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept":          "application/atom+xml,application/xml,text/xml",
    "Host":            "www.sec.gov",
}

# =============================================================================
# SECCION 2 — TICKERS CONFIG
# -----------------------------------------------------------------------------
# Para añadir un ticker nuevo:
#   1. Copiar un bloque completo
#   2. Rellenar con las keywords derivadas de la tesis de inversión
#   3. Cambiar "activo": True
#
# Estructura de keywords_cat_hitos:
#   clave  = tupla de keywords (igual que en keywords_cat3)
#   valor  = (id_hito, descripcion_hito, accion_sugerida)
#   id_hito = None si es solo seguimiento sin acción requerida
# =============================================================================

TICKERS_CONFIG = {

    "GLNG": {
        "nombre":         "Golar LNG",
        "activo":         True,
        "precio_entrada": 46.25,
        "moneda":         "USD",
        "sec_cik":        "0001166663",

        "gnews_queries": [
            "Golar LNG contract",
            "Golar LNG FLNG",
            "Hilli Episeyo",
            "SESA Argentina LNG",
            "Gimi BP GTA",
            "GLNG stock",
        ],

        # ── CAT 1 · INVALIDACION DE TESIS ────────────────────────────────
        # Cada tupla lleva hito asignado para que el mensaje diga
        # exactamente qué hito cambiar a false en el JSON.
        "keywords_cat1": [
            ("hilli",   "terminat"),
            ("hilli",   "cancel"),
            ("hilli",   "renegotiat"),
            ("hilli",   "breach"),
            ("perenco", "terminat"),
            ("perenco", "cancel"),
            ("perenco", "contract", "end"),
            ("sesa",    "cancel"),
            ("sesa",    "terminat"),
            ("mkii",    "cancel"),
            ("mkii",    "terminat"),
            ("argentina", "flng",  "cancel"),
            ("golar",   "argentina", "cancel"),
            ("golar",   "shares offered"),
            ("golar",   "equity offering"),
            ("golar",   "dilut"),
            ("glng",    "dilut"),
            ("golar",   "secondary offering"),
            ("golar",   "force majeure"),
            ("gimi",    "terminat"),
            ("gimi",    "cancel"),
        ],

        # Mapeo Cat.1 keywords → hito de invalidación
        "keywords_cat1_hitos": {
            ("hilli",   "terminat"):          (7, "Hilli — Contrato Perenco vigente",    "estado:false"),
            ("hilli",   "cancel"):            (7, "Hilli — Contrato Perenco vigente",    "estado:false"),
            ("hilli",   "renegotiat"):        (7, "Hilli — Contrato Perenco vigente",    "estado:false"),
            ("hilli",   "breach"):            (7, "Hilli — Contrato Perenco vigente",    "estado:false"),
            ("perenco", "terminat"):          (7, "Hilli — Contrato Perenco vigente",    "estado:false"),
            ("perenco", "cancel"):            (7, "Hilli — Contrato Perenco vigente",    "estado:false"),
            ("perenco", "contract", "end"):   (7, "Hilli — Contrato Perenco vigente",    "estado:false"),
            ("sesa",    "cancel"):            (8, "MKII Argentina — Deal 20 anos",       "estado:false"),
            ("sesa",    "terminat"):          (8, "MKII Argentina — Deal 20 anos",       "estado:false"),
            ("mkii",    "cancel"):            (8, "MKII Argentina — Deal 20 anos",       "estado:false"),
            ("mkii",    "terminat"):          (8, "MKII Argentina — Deal 20 anos",       "estado:false"),
            ("argentina", "flng", "cancel"):  (8, "MKII Argentina — Deal 20 anos",       "estado:false"),
            ("golar",   "argentina", "cancel"):(8,"MKII Argentina — Deal 20 anos",       "estado:false"),
            ("golar",   "shares offered"):    (9, "Sin dilucion capital >10%",           "estado:false"),
            ("golar",   "equity offering"):   (9, "Sin dilucion capital >10%",           "estado:false"),
            ("golar",   "dilut"):             (9, "Sin dilucion capital >10%",           "estado:false"),
            ("glng",    "dilut"):             (9, "Sin dilucion capital >10%",           "estado:false"),
            ("golar",   "secondary offering"):(9, "Sin dilucion capital >10%",           "estado:false"),
            ("golar",   "force majeure"):     (7, "Hilli — Contrato Perenco vigente",    "estado:false — verificar cual activo"),
            ("gimi",    "terminat"):          (1, "Gimi — Operacion comercial plena",    "estado:false"),
            ("gimi",    "cancel"):            (1, "Gimi — Operacion comercial plena",    "estado:false"),
        },

        # ── CAT 2 · CATALIZADOR ───────────────────────────────────────────
        "keywords_cat2": [
            ("lng",          "price",   "high"),
            ("lng",          "price",   "rise"),
            ("european gas", "high"),
            ("jkm",          "high"),
            ("ttf",          "high"),
            ("hormuz",       "lng"),
            ("iran",         "lng"),
            ("iran",         "energy"),
            ("ormuz",        "lng"),
            ("qatar",        "lng",   "halt"),
            ("qatar",        "lng",   "stop"),
            ("energy stock", "iran"),
            ("argentina",    "lng",   "contract"),
            ("argentina",    "lng",   "export"),
            ("argentina",    "flng"),
            ("sesa",         "lng"),
            ("sesa",         "contract"),
            ("sesa",         "offtake"),
            ("sesa",         "signs"),
            ("southern energy", "flng"),
            ("flng",         "fid"),
            ("flng",         "charter"),
            ("gimi",         "first cargo"),
            ("gimi",         "operational"),
            ("gimi",         "commercial"),
            ("golar",        "new contract"),
            ("golar",        "loi"),
            ("golar",        "letter of intent"),
            ("golar",        "award"),
            ("golar",        "upside"),
            ("glng",         "entry"),
            ("golar",        "bull",  "case"),
            ("golar",        "bull",  "change"),
            ("glng",         "could", "change"),
        ],

        # Mapeo Cat.2 keywords → catalizador y acción
        "keywords_cat2_hitos": {
            ("gimi",  "first cargo"):      (1, "Gimi — Operacion comercial plena",       "Confirmar y actualizar hito 1 a true"),
            ("gimi",  "operational"):      (1, "Gimi — Operacion comercial plena",       "Confirmar y actualizar hito 1 a true"),
            ("gimi",  "commercial"):       (1, "Gimi — Operacion comercial plena",       "Confirmar y actualizar hito 1 a true"),
            ("sesa",  "contract"):         (3, "MKII Argentina — Construccion on-schedule", "Confirmar progreso — actualizar hito 3"),
            ("sesa",  "offtake"):          (3, "MKII Argentina — Construccion on-schedule", "Confirmar progreso — actualizar hito 3"),
            ("sesa",  "signs"):            (3, "MKII Argentina — Construccion on-schedule", "Confirmar progreso — actualizar hito 3"),
            ("argentina", "lng", "contract"): (3, "MKII Argentina — Construccion on-schedule", "Confirmar progreso — actualizar hito 3"),
            ("argentina", "flng"):         (3, "MKII Argentina — Construccion on-schedule", "Confirmar progreso — actualizar hito 3"),
            ("iran",  "energy"):           (None, "Catalizador macro LNG — Hormuz/Iran", "Evaluar ampliacion tramo 2 en $41-43"),
            ("iran",  "lng"):              (None, "Catalizador macro LNG — Hormuz/Iran", "Evaluar ampliacion tramo 2 en $41-43"),
            ("hormuz","lng"):              (None, "Catalizador macro LNG — Hormuz",      "Evaluar ampliacion tramo 2 en $41-43"),
            ("energy stock", "iran"):      (None, "Catalizador macro LNG — Iran",        "Evaluar ampliacion tramo 2 en $41-43"),
            ("flng",  "fid"):              (None, "Mercado FLNG validado — competidor",  "Seguimiento — refuerza tesis"),
            ("flng",  "charter"):          (None, "Mercado FLNG validado — competidor",  "Seguimiento — refuerza tesis"),
            ("golar", "bull",  "change"):  (None, "Bull case Golar actualizado",         "Leer — puede afectar precio objetivo"),
            ("glng",  "could", "change"):  (None, "Bull case Golar actualizado",         "Leer — puede afectar precio objetivo"),
        },

        # ── CAT 3 · CONFIRMACION ──────────────────────────────────────────
        "keywords_cat3": [
            ("golar",  "earnings"),
            ("golar",  "results"),
            ("golar",  "beat"),
            ("glng",   "results"),
            ("golar",  "ebitda"),
            ("golar",  "fcf"),
            ("golar",  "dividend"),
            ("glng",   "dividend"),
            ("golar",  "conviction"),
            ("golar",  "upgrade"),
            ("golar",  "price target"),
            ("golar",  "buy"),
            ("hilli",  "cargo"),
            ("hilli",  "production"),
            ("hilli",  "uptime"),
            ("golar",  "position"),
            ("glng",   "position"),
            ("golar",  "investor"),
            ("golar",  "million"),
            ("golar",  "lng",  "stock"),
            ("glng",   "stock"),
            ("glng",   "down", "today"),
            ("glng",   "movement"),
            ("glng",   "signal"),
            ("golar",  "rating"),
            ("glng",   "rating"),
            ("glng",   "setup"),
        ],

        # Mapeo Cat.3 keywords → hito y acción exacta
        "keywords_cat3_hitos": {
            ("golar", "earnings"):    (2, "FCF guidance 2025 confirmado",        "Leer earnings — actualizar hito 2 si FCF >400M"),
            ("golar", "results"):     (2, "FCF guidance 2025 confirmado",        "Leer results — actualizar hito 2 si FCF >400M"),
            ("golar", "beat"):        (2, "FCF guidance 2025 confirmado",        "Leer — si bat guidance actualizar hito 2"),
            ("glng",  "results"):     (2, "FCF guidance 2025 confirmado",        "Leer results — actualizar hito 2 si FCF >400M"),
            ("golar", "ebitda"):      (2, "FCF guidance 2025 confirmado",        "Leer — actualizar hito 2 si datos confirman"),
            ("golar", "fcf"):         (2, "FCF guidance 2025 confirmado",        "Leer — actualizar hito 2 si FCF >400M"),
            ("golar", "dividend"):    (4, "Dividendo o buybacks iniciado",       "Actualizar hito 4 → estado:true · fecha:hoy"),
            ("glng",  "dividend"):    (4, "Dividendo o buybacks iniciado",       "Actualizar hito 4 → estado:true · fecha:hoy"),
            ("hilli", "cargo"):       (7, "Hilli — Contrato Perenco vigente",    "Confirma vigencia — hito 7 sigue en null"),
            ("hilli", "production"):  (7, "Hilli — Contrato Perenco vigente",    "Confirma vigencia — hito 7 sigue en null"),
            ("hilli", "uptime"):      (7, "Hilli — Contrato Perenco vigente",    "Confirma vigencia — hito 7 sigue en null"),
            ("golar", "conviction"):  (None, "Analistaconfirma conviction — seguimiento", "Sin accion requerida"),
            ("golar", "upgrade"):     (None, "Upgrade analistaroista — seguimiento",       "Sin accion requerida"),
            ("golar", "price target"):(None, "Cambio precio objetivo — seguimiento",       "Sin accion requerida"),
            ("golar", "investor"):    (None, "Posicion institucional — seguimiento",        "Sin accion requerida"),
            ("golar", "million"):     (None, "Posicion institucional — seguimiento",        "Sin accion requerida"),
            ("golar", "lng", "stock"):(None, "Movimiento precio — seguimiento",             "Sin accion requerida"),
            ("glng",  "stock"):       (None, "Movimiento precio — seguimiento",             "Sin accion requerida"),
            ("glng",  "down", "today"):(None,"Caida precio hoy — leer causa",               "Leer — verificar si hay noticia detras"),
            ("glng",  "movement"):    (None, "Señal cuantitativa — seguimiento",            "Sin accion requerida"),
            ("glng",  "signal"):      (None, "Señal cuantitativa — seguimiento",            "Sin accion requerida"),
            ("golar", "rating"):      (None, "Rating tecnico — seguimiento",                "Sin accion requerida"),
            ("glng",  "setup"):       (None, "Setup tecnico — seguimiento",                 "Sin accion requerida"),
        },

        "macro_config": None,
    },

    # ── PLANTILLA STZ (pendiente) ─────────────────────────────────────────
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
    #     "macro_config": {"tipo":"bls","serie":"CES2000000001",
    #                      "umbral_alerta_baja":8100000,"umbral_catalizador":8280000,
    #                      "descripcion":"BLS Construction Employment"},
    # },

    # ── PLANTILLA RI.PA (pendiente) ───────────────────────────────────────
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
    #     "macro_config": None,
    # },
}


# =============================================================================
# SECCION 3 — FETCHERS
# =============================================================================

def resolver_url(url_google, timeout=8):
    """
    Resuelve la URL real detras del enlace de Google News RSS.
    Los enlaces google.com/rss/articles/CBM... son tokens internos
    que dan error 400 al abrirlos directamente en el navegador.
    """
    if not url_google or "news.google.com" not in url_google:
        return url_google
    try:
        resp = requests.get(
            url_google,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        url_final = resp.url
        # Limpiar parametros de tracking
        if "?" in url_final:
            url_final = url_final.split("?")[0]
        return url_final
    except Exception:
        return url_google  # fallback: URL original


def fetch_sec_8k(cik, horas=None):
    """
    SEC EDGAR RSS. Funciona en GitHub Actions.
    En Colab puede devolver 0 por bloqueo de IP de Google Cloud.
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
                    "enlace":    entry.link,  # SEC no necesita resolver — URL directa
                    "fecha_pub": fecha,
                    "fuente":    "SEC EDGAR 8-K",
                    "ticker":    None,
                })
    except Exception as e:
        print("    Error SEC EDGAR (" + cik + "): " + str(e))
    return resultados


def fetch_google_news(query, horas=None):
    """Google News RSS con resolución de URLs reales."""
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
        limite = datetime.now(timezone.utc) - timedelta(hours=horas)
        for entry in feed.entries[:15]:
            try:
                fecha = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                fecha = datetime.now(timezone.utc)
            if fecha >= limite:
                url_raw = getattr(entry, "link", "")
                url_real = resolver_url(url_raw)
                resultados.append({
                    "titulo":    entry.title,
                    "enlace":    url_real,
                    "fecha_pub": fecha,
                    "fuente":    "Google News",
                    "ticker":    None,
                })
    except Exception as e:
        print("    Error Google News ('" + query + "'): " + str(e))
    return resultados


def fetch_macro_bls(config):
    """BLS scraping — solo el primer viernes de cada mes."""
    if config is None or config.get("tipo") != "bls":
        return None
    hoy = datetime.now()
    if hoy.weekday() != 4 or hoy.day > 7:
        return None
    try:
        url = "https://www.bls.gov/news.release/empsit.nr0.htm"
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        texto = soup.get_text()
        lineas = [l.strip() for l in texto.split("\n")
                  if "construction" in l.lower() and len(l.strip()) > 10]
        return {
            "descripcion":       config.get("descripcion", "BLS dato macro"),
            "lineas_relevantes": lineas[:3],
            "url":               url,
            "umbral_baja":       config.get("umbral_alerta_baja"),
            "umbral_cat":        config.get("umbral_catalizador"),
        }
    except Exception as e:
        print("    Error BLS: " + str(e))
        return None


# =============================================================================
# SECCION 4 — CLASIFICADOR CON HITO ASIGNADO
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
    Retorna (id_hito, descripcion, accion) o (None, "Sin hito", "Sin accion").
    """
    tn = normalizar(titulo)
    for tupla, hito_info in hitos_dict.items():
        if all(k.lower() in tn for k in tupla):
            return hito_info
    return (None, "Sin hito asignado", "Sin accion requerida")


def clasificar(titulo, config):
    """
    Clasifica y devuelve (categoria, id_hito, descripcion_hito, accion_hito).
    Cat1 > Cat2 > Cat3 > ruido.
    """
    if match_keywords(titulo, config["keywords_cat1"]):
        hito = encontrar_hito(titulo, config.get("keywords_cat1_hitos", {}))
        return ("cat1",) + hito

    if match_keywords(titulo, config["keywords_cat2"]):
        hito = encontrar_hito(titulo, config.get("keywords_cat2_hitos", {}))
        return ("cat2",) + hito

    if match_keywords(titulo, config["keywords_cat3"]):
        hito = encontrar_hito(titulo, config.get("keywords_cat3_hitos", {}))
        return ("cat3",) + hito

    return ("ruido", None, "", "")


# =============================================================================
# SECCION 5 — DEDUPLICACION
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


def hash_n(titulo):
    return hashlib.md5(titulo.lower().encode()).hexdigest()[:12]


# =============================================================================
# SECCION 6 — RENDER TELEGRAM
# =============================================================================

def hace(fecha_pub):
    diff = datetime.now(timezone.utc) - fecha_pub
    h = int(diff.total_seconds() / 3600)
    if h == 0:
        return "hace " + str(int(diff.total_seconds() / 60)) + "min"
    elif h < 24:
        return "hace " + str(h) + "h"
    else:
        return "hace " + str(int(h / 24)) + "d"


def render_noticia(n, accion_default):
    """Renderiza una noticia individual con hito asignado."""
    L = []
    L.append("TICKER: " + n["ticker"])
    L.append(n["titulo"][:120])
    L.append("Fuente: " + n["fuente"] + " · " + hace(n["fecha_pub"]))
    L.append("-> " + n["enlace"][:100])

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
    L.append("MONITOR NOTICIAS v4 · " + fecha_now)
    L.append("Tickers: " + " · ".join(tickers))
    if modo_auditoria:
        L.append("MODO: AUDITORIA · HORAS=" + str(HORAS_LOOKBACK))
    L.append("=" * 38)

    tiene = False

    # CAT 1 — siempre primero
    if noticias_por_cat.get("cat1"):
        tiene = True
        L.append("")
        L.append("ALERTA INVALIDACION [" + str(len(noticias_por_cat["cat1"])) + "]")
        L.append("-" * 30)
        for n in noticias_por_cat["cat1"]:
            L.append(render_noticia(n, "Revisar posicion en 48h"))

    # CAT 2
    if noticias_por_cat.get("cat2"):
        tiene = True
        L.append("")
        L.append("CATALIZADOR [" + str(len(noticias_por_cat["cat2"])) + "]")
        L.append("-" * 30)
        for n in noticias_por_cat["cat2"]:
            L.append(render_noticia(n, "Evaluar ampliar posicion"))

    # CAT 3
    if noticias_por_cat.get("cat3"):
        tiene = True
        L.append("")
        L.append("CONFIRMACION [" + str(len(noticias_por_cat["cat3"])) + "]")
        L.append("-" * 30)
        for n in noticias_por_cat["cat3"]:
            L.append(render_noticia(n, "Revisar y actualizar JSON si procede"))

    if not tiene:
        L.append("")
        L.append("Sin noticias relevantes.")
        L.append("Tesis intacta. Sin accion requerida.")
        L.append("")

    # RUIDO — completo en auditoría, muestra de 3 en producción
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

    if modo_auditoria:
        L.append("")
        L.append("FIN AUDITORIA — Para produccion:")
        L.append("DRY_RUN=False · HORAS_LOOKBACK=26")
    else:
        L.append("")
        L.append("Proxima ejecucion: manana 07:00 CET")

    return "\n".join(L)


# =============================================================================
# SECCION 7 — MAIN
# =============================================================================

def monitor_noticias():
    fecha_now     = datetime.now().strftime("%d/%m/%Y %H:%M")
    modo_auditoria = DRY_RUN

    print("=" * 50)
    print("MONITOR NOTICIAS v4 · " + fecha_now)
    print("DRY_RUN=" + str(DRY_RUN) +
          " · HORAS_LOOKBACK=" + str(HORAS_LOOKBACK) +
          " · MODO=" + ("AUDITORIA" if modo_auditoria else "PRODUCCION"))
    print("=" * 50)

    os.makedirs(CARPETA, exist_ok=True)
    vistos = cargar_vistos()

    tickers_activos = {k: v for k, v in TICKERS_CONFIG.items()
                       if v.get("activo", False)}
    print("Tickers activos: " + ", ".join(tickers_activos.keys()))

    noticias_por_cat = {"cat1": [], "cat2": [], "cat3": []}
    ruido_items      = []
    nuevos_vistos    = set()

    for ticker, config in tickers_activos.items():
        print("\n--- " + ticker + " · " + config["nombre"] + " ---")
        todas = []

        # SEC EDGAR
        if config.get("sec_cik"):
            print("  Fetching SEC EDGAR...")
            sec = fetch_sec_8k(config["sec_cik"])
            print("  SEC dentro de lookback: " + str(len(sec)))
            todas.extend(sec)

        # Google News
        for query in config.get("gnews_queries", []):
            gn = fetch_google_news(query)
            print("  Google News '" + query + "': " + str(len(gn)))
            todas.extend(gn)

        # Macro BLS
        macro = fetch_macro_bls(config.get("macro_config"))
        if macro:
            print("  BLS: " + str(macro["lineas_relevantes"][:1]))

        print("  Total antes de deduplicar: " + str(len(todas)))

        for n in todas:
            h = hash_n(n["titulo"])
            if h in vistos:
                continue
            nuevos_vistos.add(h)
            n["ticker"] = ticker

            cat, id_hito, desc_hito, accion_hito = clasificar(n["titulo"], config)
            n["id_hito"]    = id_hito
            n["desc_hito"]  = desc_hito
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

    # Resumen
    print("\n" + "=" * 50)
    print("RESUMEN CLASIFICACION:")
    print("  Cat.1 Invalidacion : " + str(len(noticias_por_cat["cat1"])))
    print("  Cat.2 Catalizador  : " + str(len(noticias_por_cat["cat2"])))
    print("  Cat.3 Confirmacion : " + str(len(noticias_por_cat["cat3"])))
    print("  Ruido filtrado     : " + str(len(ruido_items)))
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
        modo_auditoria
    )

    print("\n--- MENSAJE TELEGRAM ---")
    print(mensaje)
    print("------------------------")

    # Enviar Telegram solo en produccion
    if not DRY_RUN and ENVIAR_TELEGRAM:
        url_tg = "https://api.telegram.org/bot" + TOKEN + "/"

        # Alerta inmediata si Cat.1
        if noticias_por_cat["cat1"]:
            alerta = (
                "ALERTA MAXIMA — INVALIDACION DE TESIS\n" +
                "=" * 38 + "\n" +
                "\n".join([
                    n["ticker"] + " [Hito " + str(n.get("id_hito","?")) + "]: " + n["titulo"]
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
                print("Error alerta: " + str(e))

        # Mensaje consolidado diario
        try:
            chunks = [mensaje[i:i+3900] for i in range(0, len(mensaje), 3900)]
            for i, c in enumerate(chunks):
                sfx = ("\n[" + str(i+1) + "/" + str(len(chunks)) + "]"
                       if len(chunks) > 1 else "")
                requests.post(url_tg + "sendMessage",
                              data={"chat_id": CHAT_ID, "text": c + sfx},
                              timeout=15)
            print("Mensaje diario enviado.")
        except Exception as e:
            print("Error mensaje: " + str(e))

    elif DRY_RUN:
        print("\n[AUDITORIA — Telegram no enviado]")
        print("Para produccion: DRY_RUN=False · HORAS_LOOKBACK=26")

    return mensaje


# =============================================================================
# EJECUCION
# =============================================================================
resultado = monitor_noticias()
