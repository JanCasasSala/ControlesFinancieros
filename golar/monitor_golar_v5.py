import subprocess, sys

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

try:
    import yfinance as yf
except ImportError:
    install("yfinance"); import yfinance as yf

try:
    import requests
except ImportError:
    install("requests"); import requests

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, io, base64, json
from datetime import datetime

try:
    from google.colab import output
    EN_COLAB = True
except ImportError:
    EN_COLAB = False

EN_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

# =============================================================================
# 1. CONFIGURACION
# =============================================================================
TOKEN           = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID         = "8351044609"
PRECIO_ENTRADA  = 46.25
STOP_LOSS       = 42.10
ZONA_COSECHA    = 55.50
ZONA_VENTA      = 62.00
OBJETIVO        = 68.00
JKM_UMBRAL      = 8.00
ENVIAR_TELEGRAM = True

CARPETA   = "golar"
RUTA_JSON = os.path.join(CARPETA, "hitos_estado.json")
RUTA_HIST = os.path.join(CARPETA, "hitos_historial.json")
RUTA_HTML = os.path.join(CARPETA, "Monitor_Golar.html")

# Cambia TU_USUARIO por tu usuario real de GitHub
GITHUB_JSON_URL = "https://raw.githubusercontent.com/JanCasasSala/MonitoresFinancieros/main/golar/hitos_estado.json"

HITOS_DEFAULT = [
    {"id": 1, "hito": "Gimi — Operacion comercial plena",        "detalle": "Primera licuefaccion bajo contrato BP en Senegal.",                "estado": None,  "fecha": None, "critico": True,  "categoria": "Operativo"},
    {"id": 2, "hito": "FCF guidance 2025 confirmado",            "detalle": "FCF anual mayor de 400M confirmado en earnings.",                  "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero"},
    {"id": 3, "hito": "Contrato FLNG Mark II anunciado",         "detalle": "LOI o contrato definitivo para tercer FLNG.",                      "estado": False, "fecha": None, "critico": True,  "categoria": "Estrategico"},
    {"id": 4, "hito": "Dividendo o buybacks iniciado",           "detalle": "Board aprueba politica de retribucion al accionista.",             "estado": False, "fecha": None, "critico": False, "categoria": "Capital"},
    {"id": 5, "hito": "Refinanciacion deuda Gimi",               "detalle": "Refinanciacion reduciendo coste financiero.",                      "estado": False, "fecha": None, "critico": False, "categoria": "Financiero"},
    {"id": 6, "hito": "Estabilidad politica Senegal confirmada", "detalle": "Nuevo gobierno ratifica contrato BP sin cambios adversos.",        "estado": None,  "fecha": None, "critico": True,  "categoria": "Riesgo"},
]


# =============================================================================
# 2. HITOS E HISTORIAL
# =============================================================================
def cargar_hitos():
    if os.path.exists(RUTA_JSON):
        with open(RUTA_JSON, "r", encoding="utf-8") as f:
            print("Hitos cargados desde archivo local.")
            return json.load(f)["hitos"]
    try:
        resp = requests.get(GITHUB_JSON_URL, timeout=10)
        if resp.status_code == 200:
            print("Hitos cargados desde GitHub.")
            return resp.json()["hitos"]
    except Exception as e:
        print("No se pudo cargar desde GitHub: " + str(e))
    print("Usando hitos por defecto.")
    return HITOS_DEFAULT


def cargar_historial():
    if os.path.exists(RUTA_HIST):
        with open(RUTA_HIST, "r", encoding="utf-8") as f:
            return json.load(f).get("cambios", [])
    return []


def detectar_cambios(hitos, historial):
    def norm(e):
        if e is True:  return "cumplido"
        if e is False: return "pendiente"
        return "seguimiento"

    ultimo = {}
    for entrada in historial:
        for d in entrada.get("detalle", []):
            ultimo[d["id"]] = d["estado_nuevo"]

    cambios = []
    for h in hitos:
        ant = ultimo.get(h["id"], "PRIMERA_VEZ")
        act = norm(h["estado"])
        if ant != "PRIMERA_VEZ" and ant != act:
            cambios.append({
                "id": h["id"], "hito": h["hito"],
                "estado_ant": ant, "estado_act": act,
                "critico": h["critico"],
            })
    return cambios


def guardar_historial(historial, hitos, cambios, fecha):
    def norm(e):
        if e is True:  return "cumplido"
        if e is False: return "pendiente"
        return "seguimiento"

    if cambios:
        historial.append({
            "fecha": fecha, "cambios_count": len(cambios),
            "detalle": [{"id": c["id"], "hito": c["hito"],
                         "estado_nuevo": c["estado_act"],
                         "estado_anterior": c["estado_ant"]} for c in cambios]
        })
    elif not historial:
        historial.append({
            "fecha": fecha, "cambios_count": 0,
            "detalle": [{"id": h["id"], "hito": h["hito"],
                         "estado_nuevo": norm(h["estado"]),
                         "estado_anterior": "-"} for h in hitos]
        })

    os.makedirs(CARPETA, exist_ok=True)
    with open(RUTA_HIST, "w", encoding="utf-8") as f:
        json.dump({"cambios": historial}, f, ensure_ascii=False, indent=2)
    print("Historial guardado. Cambios: " + str(len(cambios)))


# =============================================================================
# 3. HELPERS
# =============================================================================
def get_close(datos, ticker):
    try:
        return datos['Close'][ticker] if isinstance(datos.columns, pd.MultiIndex) else datos['Close']
    except KeyError:
        raise ValueError("No se pudo obtener Close para " + ticker)


def get_volume(datos, ticker):
    try:
        return datos['Volume'][ticker] if isinstance(datos.columns, pd.MultiIndex) else datos['Volume']
    except KeyError:
        raise ValueError("No se pudo obtener Volume para " + ticker)


def badge(texto, color):
    return (
        "<span style='background:" + color + "33;color:" + color + ";"
        "padding:3px 10px;border-radius:8px;font-size:0.8rem;font-weight:bold;'>"
        + texto + "</span>"
    )


def fila_metrica(label, valor, badge_html="", extra=""):
    return (
        "<tr>"
        "<td style='color:#888;font-size:0.82rem;text-transform:uppercase;letter-spacing:0.5px;'>" + label + "</td>"
        "<td style='font-weight:bold;font-size:1rem;'>" + valor + "</td>"
        "<td>" + badge_html + "</td>"
        "<td style='color:#666;font-size:0.78rem;'>" + extra + "</td>"
        "</tr>"
    )


def calcular_conviccion(hitos):
    total = sum(2 if h["critico"] else 1 for h in hitos)
    ok    = sum((2 if h["critico"] else 1)       for h in hitos if h["estado"] is True)
    seg   = sum((2 if h["critico"] else 1) * 0.5 for h in hitos if h["estado"] is None)
    score = ((ok + seg) / total) * 100
    if len([h for h in hitos if h["critico"] and h["estado"] is False]) >= 3:
        score = min(score, 35)
    if score >= 70:   return score, "ALTA CONVICCION",                "#2ecc71"
    elif score >= 40: return score, "CONVICCION MEDIA",               "#f39c12"
    else:             return score, "CONVICCION BAJA — Revisar tesis", "#e74c3c"


def render_hitos(hitos):
    cat_colors = {
        "Operativo": "#00d4ff", "Financiero": "#2ecc71",
        "Estrategico": "#9b59b6", "Capital": "#f39c12", "Riesgo": "#e74c3c",
    }
    filas = ""
    for h in hitos:
        if h["estado"] is True:
            icono, color_e, label_e = "OK",  "#2ecc71", "CUMPLIDO"
        elif h["estado"] is False:
            icono, color_e, label_e = "X",   "#e74c3c", "PENDIENTE"
        else:
            icono, color_e, label_e = "...", "#3498db", "SEGUIMIENTO"

        critico_tag = (
            "<span style='background:#e74c3c33;color:#e74c3c;"
            "padding:1px 6px;border-radius:4px;font-size:0.7rem;margin-left:6px;'>CRITICO</span>"
            if h["critico"] else ""
        )
        cat_color = cat_colors.get(h["categoria"], "#888")
        fecha_str = h["fecha"] if h["fecha"] else "-"
