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
# Para produccion: DRY_RUN = False · HORAS_LOOKBACK = 26
# Para pruebas:    DRY_RUN = True  · HORAS_LOOKBACK = 240
# =============================================================================

TOKEN           = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID         = "8351044609"
ENVIAR_TELEGRAM = True
DRY_RUN         = False    # ← Cambiar a False en produccion
HORAS_LOOKBACK  = 26    # ← Cambiar a 26 en produccion

CARPETA      = "noticias"
RUTA_VISTOS  = os.path.join(CARPETA, "noticias_vistas.json")

SEC_HEADERS = {
    "User-Agent":      "Portfolio Monitor monitor@portfolio.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept":          "application/atom+xml,application/xml,text/xml",
    "Host":            "www.sec.gov",
}

# =============================================================================
# SECCION 2 — TICKERS CONFIG
# Keywords calibradas en sesion de pruebas 14/03/2026.
# Para añadir STZ o RI.PA: descomentar plantilla y rellenar con tesis del ticker.
# =============================================================================

TICKERS_CONFIG = {

    "GLNG": {
        "nombre":         "Golar LNG",
        "activo":         True,
        "precio_entrada": 46.25,
        "moneda":         "USD",
        "sec_cik":        "0001166663",  # SEC EDGAR funciona en GitHub Actions, no en Colab

        # Queries Google News — tan especificos como sea posible
        "gnews_queries": [
            "Golar LNG contract",
            "Golar LNG FLNG",
            "Hilli Episeyo",
            "SESA Argentina LNG",
            "Gimi BP GTA",
            "GLNG stock",
        ],

        # ── CAT 1 · INVALIDACION DE TESIS ─────────────────────────────────
        # Derivadas de los hitos 7, 8, 9 de la tesis GLNG.
        # Cada tupla: TODOS los terminos deben aparecer en el titular.
        # Si cualquier tupla hace match → alerta inmediata a cualquier hora.
        "keywords_cat1": [
            # Hito 7 — Hilli / Perenco
            ("hilli",   "terminat"),
            ("hilli",   "cancel"),
            ("hilli",   "renegotiat"),
            ("hilli",   "breach"),
            ("perenco", "terminat"),
            ("perenco", "cancel"),
            ("perenco", "contract", "end"),
            # Hito 8 — MKII Argentina / SESA
            ("sesa",      "cancel"),
            ("sesa",      "terminat"),
            ("mkii",      "cancel"),
            ("mkii",      "terminat"),
            ("argentina", "flng",  "cancel"),
            ("golar",     "argentina", "cancel"),
            # Hito 9 — Dilucion de capital
            ("golar",  "shares offered"),
            ("golar",  "equity offering"),
            ("golar",  "dilut"),
            ("glng",   "dilut"),
            ("golar",  "secondary offering"),
            # Fuerza mayor sobre activos core
            ("golar",  "force majeure"),
            ("gimi",   "terminat"),
            ("gimi",   "cancel"),
        ],

        # ── CAT 2 · CATALIZADOR ───────────────────────────────────────────
        # Eventos que activan o aceleran la tesis.
        # Derivadas de condiciones de ampliacion de posicion en la tesis.
        "keywords_cat2": [
            # LNG precio alto — cada $1 = ~$100M EBITDA adicional
            ("lng",           "price",   "high"),
            ("lng",           "price",   "rise"),
            ("european gas",  "high"),
            ("jkm",           "high"),
            ("ttf",           "high"),
            # Hormuz / Iran / disrupciones oferta LNG
            ("hormuz",        "lng"),
            ("iran",          "lng"),
            ("iran",          "energy"),       # calibrado: "Iran War Spurs Power Crisis"
            ("ormuz",         "lng"),
            ("qatar",         "lng",    "halt"),
            ("qatar",         "lng",    "stop"),
            ("energy stock",  "iran"),          # añadido en calibracion 14/03/2026
            # Argentina / SESA — noticias positivas del deal MKII
            ("argentina",     "lng",    "contract"),
            ("argentina",     "lng",    "export"),
            ("argentina",     "flng"),
            ("sesa",          "lng"),
            ("sesa",          "contract"),
            ("sesa",          "offtake"),
            ("sesa",          "signs"),
            # Competidores validando mercado FLNG — señal positiva sectorial
            ("southern energy", "flng"),
            ("flng",          "fid"),
            ("flng",          "charter"),
            # Gimi primer cargamento
            ("gimi",          "first cargo"),
            ("gimi",          "operational"),
            ("gimi",          "commercial"),
            # Nuevos contratos Golar
            ("golar",         "new contract"),
            ("golar",         "loi"),
            ("golar",         "letter of intent"),
            ("golar",         "award"),
            ("golar",         "upside"),
            ("glng",          "entry"),
            # Bull case / tesis positiva
            ("golar",         "bull",   "case"),
            ("golar",         "bull",   "change"),
            ("glng",          "could",  "change"),
        ],

        # ── CAT 3 · CONFIRMACION ──────────────────────────────────────────
        # Hitos de seguimiento que confirman que la tesis avanza.
        # No cambian la decision pero actualizan el JSON de hitos.
        "keywords_cat3": [
            # Earnings / resultados
            ("golar",  "earnings"),
            ("golar",  "results"),
            ("golar",  "beat"),
            ("glng",   "results"),
            ("golar",  "ebitda"),
            ("golar",  "fcf"),
            # Dividendo
            ("golar",  "dividend"),
            ("glng",   "dividend"),
            # Analistas positivos
            ("golar",  "conviction"),
            ("golar",  "upgrade"),
            ("golar",  "price target"),
            ("golar",  "buy"),
            # Hilli produccion normal
            ("hilli",  "cargo"),
            ("hilli",  "production"),
            ("hilli",  "uptime"),
            # Inversores institucionales — seguimiento posiciones
            ("golar",  "position"),
            ("glng",   "position"),
            ("golar",  "investor"),
            ("golar",  "million"),       # "Has $X Million Position in Golar"
            # Movimiento precio con contexto
            ("golar",  "lng",    "stock"),
            ("glng",   "stock"),
            ("glng",   "down",   "today"),
            ("glng",   "movement"),
            ("glng",   "signal"),
            # Ratings tecnicos
            ("golar",  "rating"),
            ("glng",   "rating"),
            ("glng",   "setup"),
        ],

        "macro_config": None,
    },

    # ── PLANTILLA STZ (pendiente — descomentar cuando se facilite la tesis) ──
    # "STZ": {
    #     "nombre":         "Constellation Brands",
    #     "activo":         False,
    #     "precio_entrada": 149.50,
    #     "moneda":         "USD",
    #     "sec_cik":        "0000016160",
    #     "gnews_queries":  ["Constellation Brands beer", "STZ stock", "Corona beer tariff"],
    #     "keywords_cat1": [
    #         ("usmca",         "tariff",   "beer"),
    #         ("mexico",        "beer",     "tariff"),
    #         ("constellation", "guidance", "cut"),
    #         ("constellation", "lowered"),
    #     ],
    #     "keywords_cat2": [
    #         ("construction",  "employment"),
    #         ("constellation", "guidance",  "raise"),
    #         ("beer",          "volume",    "growth"),
    #         ("hispanic",      "employment"),
    #     ],
    #     "keywords_cat3": [
    #         ("constellation", "earnings"),
    #         ("stz",           "dividend"),
    #         ("corona",        "market share"),
    #         ("constellation", "beat"),
    #     ],
    #     "macro_config": {
    #         "tipo":                "bls",
    #         "serie":               "CES2000000001",
    #         "umbral_alerta_baja":  8100000,
    #         "umbral_catalizador":  8280000,
    #         "descripcion":         "BLS Construction Employment — indicador adelantado STZ"
    #     },
    # },

    # ── PLANTILLA RI.PA (pendiente — descomentar cuando se facilite la tesis) ──
    # "RIPA": {
    #     "nombre":         "Pernod Ricard",
    #     "activo":         False,
    #     "precio_entrada": 66.50,
    #     "moneda":         "EUR",
    #     "sec_cik":        None,
    #     "gnews_queries":  ["Pernod Ricard China", "Pernod Ricard earnings", "Martell cognac"],
    #     "keywords_cat1": [
    #         ("pernod", "dividend", "cut"),
    #         ("pernod", "dividend", "reduce"),
    #         ("pernod", "fcf",      "decline"),
    #     ],
    #     "keywords_cat2": [
    #         ("china",  "spirits",  "recovery"),
    #         ("mofcom", "cognac"),
    #         ("india",  "whisky",   "tariff"),
    #         ("pernod", "organic",  "growth"),
    #     ],
    #     "keywords_cat3": [
    #         ("pernod", "earnings"),
    #         ("pernod", "dividend", "confirm"),
    #         ("pernod", "india",    "growth"),
    #         ("pernod", "beat"),
    #     ],
    #     "macro_config": None,
    # },
}


# =============================================================================
# SECCION 3 — FETCHERS
# =============================================================================

def fetch_sec_8k(cik, horas=HORAS_LOOKBACK):
    """
    SEC EDGAR RSS. Requiere requests + headers correctos.
    Funciona en GitHub Actions. En Colab puede devolver 0 por bloqueo de IP.
    """
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
                    "enlace":    entry.link,
                    "fecha_pub": fecha,
                    "fuente":    "SEC EDGAR 8-K",
                    "ticker":    None,
                })
    except Exception as e:
        print("    Error SEC EDGAR (" + cik + "): " + str(e))
    return resultados


def fetch_google_news(query, horas=HORAS_LOOKBACK):
    """Google News RSS. Sin autenticacion. Funciona en Colab y GitHub Actions."""
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
                resultados.append({
                    "titulo":    entry.title,
                    "enlace":    getattr(entry, "link", ""),
                    "fecha_pub": fecha,
                    "fuente":    "Google News",
                    "ticker":    None,
                })
    except Exception as e:
        print("    Error Google News ('" + query + "'): " + str(e))
    return resultados


def fetch_macro_bls(config):
    """BLS scraping — solo el primer viernes de cada mes. Solo relevante para STZ."""
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
# SECCION 4 — CLASIFICADOR
# =============================================================================

def normalizar(texto):
    return (texto.lower()
            .replace("-", " ")
            .replace("'", "")
            .replace("\u2019", "")
            .replace(",", "")
            .replace(".", " "))


def match_keywords(titulo, keywords_list):
    """True si el titular contiene TODOS los terminos de cualquier tupla."""
    tn = normalizar(titulo)
    return any(all(k.lower() in tn for k in tupla) for tupla in keywords_list)


def clasificar(titulo, config):
    """Cat1 > Cat2 > Cat3 > ruido."""
    if match_keywords(titulo, config["keywords_cat1"]):
        return "cat1"
    if match_keywords(titulo, config["keywords_cat2"]):
        return "cat2"
    if match_keywords(titulo, config["keywords_cat3"]):
        return "cat3"
    return "ruido"


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


def render(noticias_por_cat, tickers, conteo_ruido, fecha_now):
    L = []
    L.append("MONITOR NOTICIAS · " + fecha_now)
    L.append("Tickers: " + " · ".join(tickers))
    L.append("=" * 38)

    tiene = False

    for cat, emoji, titulo_sec, accion in [
        ("cat1", "ALERTA INVALIDACION",  "ALERTA INVALIDACION", "Revisar posicion en 48h"),
        ("cat2", "CATALIZADOR",          "CATALIZADOR",         "Evaluar ampliar posicion"),
        ("cat3", "CONFIRMACION",         "CONFIRMACION",        "Actualizar hito en JSON"),
    ]:
        items = noticias_por_cat.get(cat, [])
        if not items:
            continue
        tiene = True
        L.append("")
        L.append(titulo_sec + " [" + str(len(items)) + "]")
        L.append("-" * 30)
        for n in items:
            L.append("TICKER: " + n["ticker"])
            L.append(n["titulo"][:120])
            L.append("Fuente: " + n["fuente"] + " · " + hace(n["fecha_pub"]))
            L.append("-> " + n["enlace"][:80])
            L.append("ACCION: " + accion)
            L.append("")

    if not tiene:
        L.append("")
        L.append("Sin noticias relevantes hoy.")
        L.append("Tesis intacta. Sin accion requerida.")
        L.append("")

    L.append("=" * 38)
    L.append("RUIDO FILTRADO: " + str(conteo_ruido) + " noticias")
    L.append("Proxima ejecucion: manana 07:00 CET")
    return "\n".join(L)


# =============================================================================
# SECCION 7 — MAIN
# =============================================================================

def monitor_noticias():
    fecha_now = datetime.now().strftime("%d/%m/%Y %H:%M")

    print("=" * 50)
    print("MONITOR NOTICIAS v3 · " + fecha_now)
    print("DRY_RUN=" + str(DRY_RUN) + " · HORAS_LOOKBACK=" + str(HORAS_LOOKBACK))
    print("=" * 50)

    os.makedirs(CARPETA, exist_ok=True)
    vistos = cargar_vistos()

    tickers_activos = {k: v for k, v in TICKERS_CONFIG.items() if v.get("activo", False)}
    print("Tickers activos: " + ", ".join(tickers_activos.keys()))

    noticias_por_cat = {"cat1": [], "cat2": [], "cat3": []}
    conteo_ruido     = 0
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
            cat = clasificar(n["titulo"], config)
            if cat == "ruido":
                conteo_ruido += 1
            else:
                noticias_por_cat[cat].append(n)
                print("  [" + cat.upper() + "] " + n["titulo"][:80])

    vistos.update(nuevos_vistos)
    if not DRY_RUN:
        guardar_vistos(vistos)

    print("\n" + "=" * 50)
    print("RESUMEN CLASIFICACION:")
    print("  Cat.1 Invalidacion : " + str(len(noticias_por_cat["cat1"])))
    print("  Cat.2 Catalizador  : " + str(len(noticias_por_cat["cat2"])))
    print("  Cat.3 Confirmacion : " + str(len(noticias_por_cat["cat3"])))
    print("  Ruido filtrado     : " + str(conteo_ruido))
    print("=" * 50)

    mensaje = render(
        noticias_por_cat,
        list(tickers_activos.keys()),
        conteo_ruido,
        fecha_now
    )

    print("\n--- MENSAJE QUE SE ENVIARIA A TELEGRAM ---")
    print(mensaje)
    print("------------------------------------------")

    if not DRY_RUN and ENVIAR_TELEGRAM:
        url_tg = "https://api.telegram.org/bot" + TOKEN + "/"

        if noticias_por_cat["cat1"]:
            alerta = (
                "ALERTA MAXIMA — INVALIDACION DE TESIS\n"
                "=" * 38 + "\n" +
                "\n".join([n["ticker"] + ": " + n["titulo"]
                           for n in noticias_por_cat["cat1"]]) +
                "\n" + "=" * 38 + "\n"
                "Revisar posiciones en las proximas 48 horas."
            )
            try:
                requests.post(url_tg + "sendMessage",
                              data={"chat_id": CHAT_ID, "text": alerta},
                              timeout=15)
                print("Alerta Cat.1 enviada.")
            except Exception as e:
                print("Error alerta: " + str(e))

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
        print("\n[DRY RUN activo — Telegram no enviado]")
        print("Para produccion: DRY_RUN = False · HORAS_LOOKBACK = 26")

    return mensaje


# =============================================================================
# EJECUCION
# =============================================================================
resultado = monitor_noticias()
