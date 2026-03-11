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

try:
    import matplotlib
except ImportError:
    install("matplotlib"); import matplotlib

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, io, base64
from datetime import datetime

try:
    from google.colab import output
    EN_COLAB = True
except ImportError:
    EN_COLAB = False

EN_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
LARGO_DATA = [
    {"tk": "SAN.MC", "cant": 6149, "cp": 2.43,  "div": 0.24, "bb": 2.6},
    {"tk": "ITX.MC", "cant": 520,  "cp": 19.20, "div": 1.90, "bb": 0.0},
    {"tk": "LOG.MC", "cant": 1070, "cp": 16.89, "div": 2.10, "bb": 0.0},
]

TOKEN           = os.environ.get("TELEGRAM_TOKEN",   "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4")
CHAT_ID         = os.environ.get("TELEGRAM_CHAT_ID", "8351044609")
BONO_REF_FALLBACK = 3.40   # usado si la descarga falla
ENVIAR_TELEGRAM = True

# =============================================================================
# BONO DE REFERENCIA AUTOMÁTICO — Bono español 10 años
# Intenta múltiples tickers en orden. Si todos fallan, usa BONO_REF_FALLBACK.
# Nunca lanza excepción — el monitor siempre continúa.
# =============================================================================
BONO_TICKERS = [
    ("ES10YT=RR", "Bono ES10Y (Reuters)"),
    ("^TNX",      "T-Note 10Y USA (proxy)"),
]
BONO_MIN, BONO_MAX = 0.1, 15.0  # rango válido — fuera = dato corrupto

def obtener_bono_ref():
    """
    Descarga el tipo del bono de referencia con múltiples fallbacks.
    Devuelve: (valor: float, live: bool, fuente: str, avisos: list[str])
    Nunca lanza excepción.
    """
    avisos = []

    for ticker, nombre in BONO_TICKERS:
        try:
            hist = yf.Ticker(ticker).history(period="5d", timeout=10)

            if hist is None or hist.empty:
                msg = f"[bono] {nombre} ({ticker}): historial vacío."
                print(msg); avisos.append(msg)
                continue

            serie = hist["Close"].dropna()
            if serie.empty:
                msg = f"[bono] {nombre} ({ticker}): Close vacío tras dropna."
                print(msg); avisos.append(msg)
                continue

            valor = round(float(serie.iloc[-1]), 2)

            if not (BONO_MIN <= valor <= BONO_MAX):
                msg = (f"[bono] {nombre} ({ticker}): valor {valor}% fuera de rango "
                       f"[{BONO_MIN}–{BONO_MAX}%] — descartado.")
                print(msg); avisos.append(msg)
                continue

            print(f"[bono] OK — {nombre}: {valor}%")
            return valor, True, nombre, avisos

        except Exception as e:
            msg = f"[bono] {nombre} ({ticker}): {type(e).__name__} — {e}"
            print(msg); avisos.append(msg)

    # Todos los tickers fallaron — usar hardcodeado
    msg = (f"[bono] AVISO: todos los tickers fallaron. "
           f"Usando fallback hardcodeado: {BONO_REF_FALLBACK}%")
    print(msg); avisos.append(msg)
    return BONO_REF_FALLBACK, False, "Fallback hardcodeado", avisos

CARPETA   = "largo"
RUTA_HTML = os.path.join(CARPETA, "Monitor_Largo.html")

# =============================================================================
# 2. DETECCIÓN DE ENTORNO
# =============================================================================
def detectar_entorno():
    try:
        import google.colab  # noqa
        return "colab"
    except ImportError:
        pass
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "github"
    return "local"

ENTORNO = detectar_entorno()
print(f"[setup] Entorno: {ENTORNO}")

# =============================================================================
# 3. HELPERS HTML
# =============================================================================
def badge(texto, color):
    return (
        f"<span style='background:{color}33;color:{color};"
        f"padding:3px 10px;border-radius:8px;font-size:0.8rem;font-weight:bold;'>"
        f"{texto}</span>"
    )

def color_gap(v):
    if v >= 1:   return "#2ecc71"
    if v >= 0:   return "#f39c12"
    return "#e74c3c"

def color_pnl(v):
    return "#2ecc71" if v >= 0 else "#e74c3c"

def estado_semaforo(gap, pa, sma100):
    if pa > sma100 and gap >= 0:
        return "OK",   "#2ecc71", "Precio sobre SMA100 y GAP positivo"
    elif gap < 0:
        return "CARO", "#e74c3c", "Rendimiento por debajo del bono de referencia"
    else:
        return "AIRE", "#f39c12", "GAP positivo pero precio bajo SMA100"

def fila_estrategia(tk, precio, y_tot, y_cst, gap, estado, color_est, tooltip):
    return (
        "<tr>"
        f"<td style='font-family:monospace;font-weight:700;color:#e0e0e0;'>{tk}</td>"
        f"<td style='font-family:monospace;'>{precio}</td>"
        f"<td style='color:{color_gap(y_tot - BONO_REF)};font-weight:bold;'>{y_tot:.1f}%</td>"
        f"<td style='color:#aaa;'>{y_cst:.1f}%</td>"
        f"<td style='color:{color_gap(gap)};font-weight:bold;'>{gap:+.1f}%</td>"
        f"<td title='{tooltip}'>{badge(estado, color_est)}</td>"
        "</tr>"
    )

def fila_patrimonio(tk, coste, mercado, dif, pnl_pct):
    return (
        "<tr>"
        f"<td style='font-family:monospace;font-weight:700;color:#e0e0e0;'>{tk}</td>"
        f"<td style='font-family:monospace;color:#aaa;'>{int(coste):,}€</td>"
        f"<td style='font-family:monospace;font-weight:bold;color:#e0e0e0;'>{int(mercado):,}€</td>"
        f"<td style='color:{color_pnl(dif)};font-weight:bold;'>{dif:+,.0f}€</td>"
        f"<td style='color:{color_pnl(pnl_pct)};font-weight:bold;'>{pnl_pct:+.1f}%</td>"
        "</tr>"
    )

# =============================================================================
# 4. HITOS T-G
# Modelo mixto: automáticos (yfinance) + manuales (JSON)
# JSON: largo/hitos_largo.json  —  misma estructura que Golar
# =============================================================================
RUTA_HITOS = os.path.join(CARPETA, "hitos_largo.json")

HITOS_DEFAULT = [
    # ── MANUALES (auto: false — el script no los sobreescribe) ──
    {"id": 1,  "tk": "SAN", "hito": "Ratio CET1 >= 12%",
     "detalle": "Capital regulatorio tier 1 en earnings. Fuente: informe trimestral.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": False},
    {"id": 2,  "tk": "LOG", "hito": "Ocupacion naves >= 95%",
     "detalle": "Tasa de ocupacion del portfolio logistico. Fuente: suplemento operativo.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Operativo",  "auto": False},
    {"id": 3,  "tk": "ITX", "hito": "Expansion internacional sin deterioro de margenes",
     "detalle": "Nuevas aperturas netas positivas con margen EBIT estable o creciente.",
     "estado": False, "fecha": None, "critico": False, "categoria": "Estrategico","auto": False},
    # ── AUTOMÁTICOS (auto: true — el script los sobreescribe cada ejecución) ──
    {"id": 4,  "tk": "SAN", "hito": "Dividendo sostenible (payout <= 80% y FCF cubre div total)",
     "detalle": "Calculado automaticamente: payout ratio y cobertura FCF vs dividendo total posicion.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Capital",    "auto": True},
    {"id": 5,  "tk": "ITX", "hito": "Dividendo sostenible (payout <= 80% y FCF cubre div total)",
     "detalle": "Calculado automaticamente: payout ratio y cobertura FCF vs dividendo total posicion.",
     "estado": False, "fecha": None, "critico": False, "categoria": "Capital",    "auto": True},
    {"id": 6,  "tk": "LOG", "hito": "Dividendo sostenible (payout <= 80% y FCF cubre div total)",
     "detalle": "Calculado automaticamente: payout ratio y cobertura FCF vs dividendo total posicion.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Capital",    "auto": True},
    {"id": 7,  "tk": "SAN", "hito": "FCF por accion creciente YoY",
     "detalle": "Calculado automaticamente: FCF/accion año actual vs año anterior.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": True},
    {"id": 8,  "tk": "ITX", "hito": "FCF por accion creciente YoY",
     "detalle": "Calculado automaticamente: FCF/accion año actual vs año anterior.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": True},
    {"id": 9,  "tk": "LOG", "hito": "FCF por accion creciente YoY",
     "detalle": "Calculado automaticamente: FCF/accion año actual vs año anterior.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": True},
    {"id": 10, "tk": "ITX", "hito": "Margenes estables o crecientes (bruto y operativo)",
     "detalle": "Calculado automaticamente: margen bruto y operativo vs año anterior.",
     "estado": False, "fecha": None, "critico": True,  "categoria": "Financiero", "auto": True},
]

import json

def cargar_hitos():
    """Carga hitos desde JSON local. Si no existe, usa defaults y lo crea."""
    if os.path.exists(RUTA_HITOS):
        try:
            with open(RUTA_HITOS, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"[hitos] Cargados {len(data['hitos'])} hitos desde {RUTA_HITOS}")
                return data["hitos"]
        except Exception as e:
            print(f"[hitos] Error leyendo JSON: {e} — usando defaults")
    print("[hitos] JSON no encontrado — usando defaults")
    return [h.copy() for h in HITOS_DEFAULT]


def guardar_hitos(hitos):
    """Persiste hitos en JSON. Nunca lanza excepción."""
    try:
        os.makedirs(CARPETA, exist_ok=True)
        with open(RUTA_HITOS, "w", encoding="utf-8") as f:
            json.dump({"hitos": hitos}, f, ensure_ascii=False, indent=2)
        print(f"[hitos] Guardados en {RUTA_HITOS}")
    except Exception as e:
        print(f"[hitos] Error guardando JSON: {e}")


def _safe_float(val, fallback=None):
    """Convierte a float de forma segura."""
    try:
        v = float(val)
        return v if pd.notna(v) else fallback
    except Exception:
        return fallback


def calcular_hitos_auto(hitos, fecha_now):
    """
    Sobreescribe el estado de los hitos con auto=True usando yfinance.
    Los hitos manuales (auto=False) no se tocan.
    Nunca lanza excepción — si un dato falla, el hito queda en False con nota.
    """
    avisos = []

    for item in LARGO_DATA:
        tk     = item["tk"]
        tk_lbl = tk[:3]
        cant   = item["cant"]

        try:
            asset = yf.Ticker(tk)

            # ── Financials ──
            fin = asset.financials          # anual, columnas = fechas desc
            cf  = asset.cashflow            # anual
            info = asset.info or {}

            # Helper: extraer fila de financials de forma segura
            def get_row(df, posibles_labels):
                if df is None or df.empty:
                    return None
                for lbl in posibles_labels:
                    if lbl in df.index:
                        return df.loc[lbl]
                    # fuzzy case-insensitive
                    for idx in df.index:
                        if idx.lower() == lbl.lower():
                            return df.loc[idx]
                return None

            # ── HITO: Dividendo sostenible ──
            div_anual   = item["div"] * cant          # dividendo total posición
            shares      = _safe_float(info.get("sharesOutstanding"))
            net_income  = None
            fcf_val     = _safe_float(info.get("freeCashflow"))

            # Payout ratio
            ni_row = get_row(fin, ["Net Income", "Net Income Common Stockholders"])
            if ni_row is not None and len(ni_row) > 0:
                net_income = _safe_float(ni_row.iloc[0])

            # FCF desde cashflow si info no lo tiene
            if fcf_val is None or fcf_val == 0:
                ocf_row   = get_row(cf, ["Operating Cash Flow",
                                         "Cash Flow From Continuing Operating Activities"])
                capex_row = get_row(cf, ["Capital Expenditure", "Purchase Of PPE"])
                if ocf_row is not None and capex_row is not None:
                    ocf   = _safe_float(ocf_row.iloc[0], 0)
                    capex = _safe_float(capex_row.iloc[0], 0)
                    fcf_val = ocf - abs(capex)

            div_total_empresa = (item["div"] * _safe_float(shares, 0)) if shares else None
            payout_ok   = False
            fcf_cubre   = False
            payout_str  = "N/D"
            fcf_str     = "N/D"

            if net_income and net_income > 0 and div_total_empresa:
                payout = (div_total_empresa / net_income) * 100
                payout_ok  = payout <= 80
                payout_str = f"{payout:.0f}%"

            if fcf_val and fcf_val > 0:
                fcf_cubre = fcf_val >= div_anual
                fcf_str   = f"FCF {fcf_val/1e6:.0f}M vs div {div_anual:.0f}€"

            div_ok = payout_ok and fcf_cubre
            div_detalle = f"Payout {payout_str} | {fcf_str}"

            for h in hitos:
                if h["auto"] and h["tk"] == tk_lbl and "Dividendo" in h["hito"]:
                    h["estado"] = div_ok
                    h["fecha"]  = fecha_now
                    h["detalle_auto"] = div_detalle
                    avisos.append(f"[hitos-auto] {tk_lbl} Dividendo: {div_detalle} → {'OK' if div_ok else 'KO'}")

            # ── HITO: FCF por acción creciente YoY ──
            fcf_row = get_row(cf, ["Free Cash Flow",
                                   "Operating Cash Flow"])  # fallback OCF
            fcf_ok      = False
            fcf_yoy_str = "N/D"

            if fcf_row is not None and len(fcf_row) >= 2 and shares and shares > 0:
                fcf_act = _safe_float(fcf_row.iloc[0])
                fcf_ant = _safe_float(fcf_row.iloc[1])
                if fcf_act is not None and fcf_ant is not None and fcf_ant != 0:
                    fcf_ps_act = fcf_act / shares
                    fcf_ps_ant = fcf_ant / shares
                    fcf_ok      = fcf_ps_act > fcf_ps_ant
                    cambio      = ((fcf_ps_act - fcf_ps_ant) / abs(fcf_ps_ant)) * 100
                    fcf_yoy_str = f"{fcf_ps_act:.2f} vs {fcf_ps_ant:.2f} ({cambio:+.1f}%)"

            for h in hitos:
                if h["auto"] and h["tk"] == tk_lbl and "FCF" in h["hito"]:
                    h["estado"] = fcf_ok
                    h["fecha"]  = fecha_now
                    h["detalle_auto"] = f"FCF/acc YoY: {fcf_yoy_str}"
                    avisos.append(f"[hitos-auto] {tk_lbl} FCF/acc: {fcf_yoy_str} → {'OK' if fcf_ok else 'KO'}")

            # ── HITO: Márgenes ITX (solo Inditex) ──
            if tk_lbl == "ITX":
                rev_row  = get_row(fin, ["Total Revenue", "Operating Revenue"])
                gp_row   = get_row(fin, ["Gross Profit"])
                ebit_row = get_row(fin, ["Operating Income", "EBIT"])

                mg_ok       = False
                mo_ok       = False
                margenes_str = "N/D"

                if (rev_row is not None and gp_row is not None and
                        len(rev_row) >= 2 and len(gp_row) >= 2):
                    rev_act = _safe_float(rev_row.iloc[0])
                    rev_ant = _safe_float(rev_row.iloc[1])
                    gp_act  = _safe_float(gp_row.iloc[0])
                    gp_ant  = _safe_float(gp_row.iloc[1])
                    if all(v and v > 0 for v in [rev_act, rev_ant, gp_act, gp_ant]):
                        mg_act = (gp_act / rev_act) * 100
                        mg_ant = (gp_ant / rev_ant) * 100
                        mg_ok  = mg_act >= mg_ant - 0.5   # tolerancia 0.5pp
                        margenes_str = f"Bruto {mg_act:.1f}% vs {mg_ant:.1f}%"

                if (ebit_row is not None and rev_row is not None and
                        len(ebit_row) >= 2):
                    ebit_act = _safe_float(ebit_row.iloc[0])
                    ebit_ant = _safe_float(ebit_row.iloc[1])
                    rev_act  = _safe_float(rev_row.iloc[0])
                    rev_ant  = _safe_float(rev_row.iloc[1])
                    if all(v and v > 0 for v in [ebit_act, ebit_ant, rev_act, rev_ant]):
                        mo_act = (ebit_act / rev_act) * 100
                        mo_ant = (ebit_ant / rev_ant) * 100
                        mo_ok  = mo_act >= mo_ant - 0.5
                        margenes_str += f" | Operativo {mo_act:.1f}% vs {mo_ant:.1f}%"

                margenes_ok = mg_ok and mo_ok

                for h in hitos:
                    if h["auto"] and h["tk"] == "ITX" and "Margen" in h["hito"]:
                        h["estado"] = margenes_ok
                        h["fecha"]  = fecha_now
                        h["detalle_auto"] = margenes_str
                        avisos.append(f"[hitos-auto] ITX Márgenes: {margenes_str} → {'OK' if margenes_ok else 'KO'}")

        except Exception as e:
            msg = f"[hitos-auto] Error procesando {tk}: {type(e).__name__} — {e}"
            print(msg); avisos.append(msg)
            # Los hitos del ticker quedan con su estado previo — no se tocan

    return hitos, avisos


def calcular_conviccion(hitos):
    """Score ponderado igual que Golar. Críticos pesan doble."""
    total = sum(2 if h["critico"] else 1 for h in hitos)
    if total == 0:
        return 0, "SIN DATOS", "#888888"
    ok  = sum((2 if h["critico"] else 1)       for h in hitos if h["estado"] is True)
    seg = sum((2 if h["critico"] else 1) * 0.5 for h in hitos if h["estado"] is None)
    score = ((ok + seg) / total) * 100
    criticos_pend = len([h for h in hitos if h["critico"] and h["estado"] is False])
    if criticos_pend >= 3:
        score = min(score, 35)
    if score >= 70:   return score, "ALTA CONVICCION",                 "#2ecc71"
    elif score >= 40: return score, "CONVICCION MEDIA",                "#f39c12"
    else:             return score, "CONVICCION BAJA — Revisar tesis", "#e74c3c"


def render_hitos_html(hitos):
    """Genera filas HTML de la tabla de hitos."""
    cat_colors = {
        "Financiero":  "#2ecc71", "Operativo":  "#00d4ff",
        "Estrategico": "#9b59b6", "Capital":    "#f39c12",
        "Riesgo":      "#e74c3c",
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
        cat_color  = cat_colors.get(h["categoria"], "#888")
        fecha_str  = h.get("fecha") or "—"
        detalle    = h.get("detalle_auto") or h.get("detalle", "")

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
# 5. FUNCIÓN PRINCIPAL
# =============================================================================
def monitor_largo_v1():
    try:
        fecha_now = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Bono de referencia automático
        BONO_REF, bono_live, bono_fuente, bono_avisos = obtener_bono_ref()
        if bono_avisos:
            for av in bono_avisos:
                print(av)

        print("[largo] Descargando datos...")

        tickers = [item["tk"] for item in LARGO_DATA]
        df_raw    = yf.download(tickers, period="250d", progress=False, auto_adjust=True)
        df_prices = df_raw["Close"].ffill()

        # ── Hitos T-G ──
        print("[hitos] Calculando hitos automáticos...")
        hitos = cargar_hitos()
        hitos, hitos_avisos = calcular_hitos_auto(hitos, fecha_now)
        guardar_hitos(hitos)
        for av in hitos_avisos:
            print(av)
        score_conv, label_conv, color_conv = calcular_conviccion(hitos)
        hitos_ok   = sum(1 for h in hitos if h["estado"] is True)
        hitos_seg  = sum(1 for h in hitos if h["estado"] is None)
        hitos_pend = sum(1 for h in hitos if h["estado"] is False)
        filas_hitos = render_hitos_html(hitos)

        # ── Cálculos por ticker ──
        rows_estr  = []
        rows_patr  = []
        plot_items = []
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
                "pa": pa, "sma100": sma100,
            })
            rows_patr.append({
                "tk": tk[:3], "ic": ic, "ia": ia,
                "dif": dif, "pnl_pct": pnl_pct,
            })
            plot_items.append({
                "tk": tk[:3], "gap": gap,
                "pnl": pnl_pct, "peso": ia / t_mkt,
            })

            print(f"  {tk[:3]}: {pa:.2f}€ | Y-TOT {y_tot:.1f}% | GAP {gap:+.1f}% | {estado}")

        # ── Evolución 90 días normalizada ──
        print("[largo] Generando gráfico...")
        plt.style.use("dark_background")
        fig, axes = plt.subplots(1, 2, figsize=(14, 6), facecolor="#121212")
        colores_tk = {"SAN": "#e74c3c", "ITX": "#3498db", "LOG": "#2ecc71"}

        # Gráfico 1: Evolución normalizada
        ax1 = axes[0]
        ax1.set_facecolor("#1e1e1e")
        hist_90 = df_prices.tail(90)
        base = hist_90.iloc[0]
        norm = (hist_90 / base) * 100
        for item in LARGO_DATA:
            tk  = item["tk"]
            lbl = tk[:3]
            c   = colores_tk.get(lbl, "#aaa")
            ax1.plot(norm.index, norm[tk], label=lbl, color=c, linewidth=2.2)
        ax1.axhline(100, color="#555", linestyle="--", linewidth=1, alpha=0.6)
        ax1.set_title("Evolución 90 días (base 100)", color="#00d4ff", fontsize=12, pad=10)
        ax1.legend(facecolor="#1e1e1e", fontsize=9)
        ax1.grid(alpha=0.07)
        ax1.tick_params(colors="#888")
        for spine in ax1.spines.values():
            spine.set_edgecolor("#333")

        # Gráfico 2: Radar de cosecha (burbujas)
        ax2 = axes[1]
        ax2.set_facecolor("#1e1e1e")
        for d in plot_items:
            # Recalcular peso relativo con t_mkt ya calculado
            color = "#27ae60" if d["gap"] >= 0 else "#e67e22"
            ax2.scatter(d["gap"], d["pnl"], s=d["peso"] * 12000,
                        alpha=0.75, color=color,
                        edgecolors="white", linewidth=1.5)
            ax2.text(d["gap"], d["pnl"],
                     f"{d['tk']}\n{d['gap']:+.1f}%",
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

        fig.suptitle(
            f"Monitor Núcleo V1.0  |  {fecha_now}",
            color="#e0e0e0", fontsize=13, fontweight="bold", y=1.01
        )
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", facecolor="#121212", bbox_inches="tight", dpi=150)
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode()
        plt.close(fig)
        print("[largo] Gráfico generado.")

        # ── Filas HTML ──
        filas_estr = "".join(
            fila_estrategia(r["tk"], r["precio"], r["y_tot"], r["y_cst"],
                            r["gap"], r["estado"], r["color_est"], r["tooltip"])
            for r in rows_estr
        )
        filas_patr = "".join(
            fila_patrimonio(r["tk"], r["ic"], r["ia"], r["dif"], r["pnl_pct"])
            for r in rows_patr
        )

        # Totales patrimonio
        dif_total   = t_mkt - t_inv
        pnl_total   = ((t_mkt - t_inv) / t_inv) * 100
        color_total = color_pnl(dif_total)

        # Resumen yield medio ponderado
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

        # =====================================================================
        # HTML
        # =====================================================================
        html = f"""<!DOCTYPE html>
<html lang='es'>
<head>
  <meta charset='UTF-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1.0'>
  <title>Monitor Núcleo V1.0</title>
  <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
  <style>
    body {{
      background:#121212;color:#e0e0e0;
      padding:25px;font-family:'Segoe UI',sans-serif;
    }}
    .card {{
      background:#1e1e1e;border-radius:15px;
      padding:22px;margin-bottom:20px;border:none;
    }}
    h5 {{
      color:#00d4ff;text-transform:uppercase;
      font-size:0.85rem;letter-spacing:1.5px;margin-bottom:15px;
    }}
    th {{
      color:#555;font-size:0.72rem;text-transform:uppercase;
      letter-spacing:0.5px;border-bottom:1px solid #2a2a2a !important;
    }}
    td {{
      vertical-align:middle !important;
      border-bottom:1px solid #1a1a1a !important;
      padding:11px 8px !important;
    }}
    code {{
      background:#2a2a2a;color:#00d4ff;
      padding:2px 6px;border-radius:4px;font-size:0.8rem;
    }}
    .kpi-box {{
      background:#161616;border-radius:10px;
      padding:14px 18px;text-align:center;
    }}
    .kpi-val {{font-size:1.6rem;font-weight:800;line-height:1;}}
    .kpi-lbl {{
      font-size:0.68rem;color:#555;
      text-transform:uppercase;letter-spacing:1px;margin-top:5px;
    }}
    .leyenda-box {{
      background:#161616;border-left:3px solid #00d4ff;
      border-radius:0 8px 8px 0;padding:12px 16px;
      font-size:0.82rem;color:#888;line-height:1.7;
    }}
  </style>
</head>
<body>
<div class='container' style='max-width:960px;'>

  <!-- HEADER -->
  <div class='d-flex justify-content-between align-items-center mb-4'>
    <div>
      <h2 style='color:#00d4ff;margin:0;'>Monitor Núcleo</h2>
      <small style='color:#555;'>V1.0 &nbsp;·&nbsp; {entorno_badge} &nbsp;·&nbsp; {fecha_now}</small>
    </div>
    <div style='text-align:right;'>
      <div style='font-size:2rem;font-weight:800;color:#00d4ff;'>{int(t_mkt):,}€</div>
      <div style='font-size:1rem;font-weight:700;color:{color_total};'>{dif_total:+,.0f}€ &nbsp;({pnl_total:+.1f}%)</div>
      <div style='font-size:0.7rem;color:#555;margin-top:4px;'>Bono ref: {BONO_REF}% &nbsp;·&nbsp; {bono_fuente}</div>
    </div>
  </div>

  <!-- KPIs -->
  <div class='card'>
    <div class='row g-3'>
      <div class='col-md-3'>
        <div class='kpi-box'>
          <div class='kpi-val' style='color:#00d4ff;'>{int(t_inv):,}€</div>
          <div class='kpi-lbl'>Capital invertido</div>
        </div>
      </div>
      <div class='col-md-3'>
        <div class='kpi-box'>
          <div class='kpi-val' style='color:{color_pnl(yield_pond - BONO_REF)};'>{yield_pond:.1f}%</div>
          <div class='kpi-lbl'>Yield pond. total</div>
        </div>
      </div>
      <div class='col-md-3'>
        <div class='kpi-box'>
          <div class='kpi-val' style='color:{color_gap(gap_pond)};'>{gap_pond:+.1f}%</div>
          <div class='kpi-lbl'>GAP pond. vs bono</div>
        </div>
      </div>
      <div class='col-md-3'>
        <div class='kpi-box'>
          <div class='kpi-val' style='color:#888;'>{BONO_REF:.2f}%</div>
          <div class='kpi-lbl'>Bono referencia</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ESTRATEGIA -->
  <div class='card'>
    <h5>Bloque 1 — Estrategia de Cosecha</h5>
    <p style='color:#666;font-size:0.78rem;margin-bottom:12px;'>
      Rentabilidad total (dividendo + buybacks) comparada con el bono de referencia ({BONO_REF}%).
      GAP positivo = la posición supera al activo libre de riesgo.
      &nbsp;·&nbsp; <span style='color:{"#2ecc71" if bono_live else "#e67e22"};font-size:0.75rem;'>
      {"● " + bono_fuente : bono_fuente}</span>
    </p>
    {"" if bono_live else "<div style='background:#e67e2218;border-left:3px solid #e67e22;border-radius:0 8px 8px 0;padding:10px 16px;margin-bottom:12px;font-size:0.8rem;color:#e67e22;'><strong>⚠ Bono con dato de fallback</strong> — no se pudo descargar el tipo real. GAP calculado con " + str(BONO_REF_FALLBACK) + "% hardcodeado.</div>"}
    <table class='table table-dark mb-0'>
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Precio</th>
          <th title='Yield sobre precio de mercado + buybacks'>Y-TOT</th>
          <th title='Yield sobre precio de coste'>Y-CST</th>
          <th title='Diferencia vs bono de referencia'>GAP</th>
          <th>Estado</th>
        </tr>
      </thead>
      <tbody>{filas_estr}</tbody>
    </table>
    <div class='leyenda-box mt-3'>
      <strong style='color:#aaa;'>Guía:</strong>
      <code>Y-TOT</code> = Rendimiento sobre precio actual (div + BB) &nbsp;·&nbsp;
      <code>Y-CST</code> = Rendimiento sobre precio de coste &nbsp;·&nbsp;
      <code>GAP</code> = Diferencia vs Bono {BONO_REF}% &nbsp;·&nbsp;
      {badge("OK", "#2ecc71")} Precio sobre SMA100 y GAP ≥ 0 &nbsp;·&nbsp;
      {badge("AIRE", "#f39c12")} GAP positivo pero precio bajo SMA100 &nbsp;·&nbsp;
      {badge("CARO", "#e74c3c")} Rendimiento inferior al bono de referencia
    </div>
  </div>

  <!-- PATRIMONIO -->
  <div class='card'>
    <h5>Bloque 2 — Patrimonio</h5>
    <p style='color:#666;font-size:0.78rem;margin-bottom:12px;'>
      Evolución del capital invertido frente al valor de mercado actual.
    </p>
    <table class='table table-dark mb-0'>
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Coste total</th>
          <th>Mercado actual</th>
          <th>Diferencia €</th>
          <th>P&amp;L %</th>
        </tr>
      </thead>
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

  <!-- HITOS T-G -->
  <div class='card'>
    <h5>Bloque 3 — Hitos T-G y Convicción</h5>
    <div class='row g-3 mb-3'>
      <div class='col-md-4'>
        <div style='background:#161616;border-radius:10px;padding:14px 18px;
                    border-left:4px solid {color_conv};'>
          <div style='color:{color_conv};font-size:1rem;font-weight:bold;
                      margin-bottom:4px;'>{label_conv}</div>
          <div style='color:#aaa;font-size:0.82rem;'>
            ✓ {hitos_ok} &nbsp;·&nbsp; ··· {hitos_seg} &nbsp;·&nbsp; ✕ {hitos_pend}
          </div>
          <div style='background:#2a2a2a;border-radius:5px;height:8px;margin-top:8px;'>
            <div style='width:{round(score_conv)}%;height:8px;border-radius:5px;
                        background:{color_conv};'></div>
          </div>
          <small style='color:#555;'>{round(score_conv)}% hitos validados</small>
        </div>
      </div>
      <div class='col-md-8'>
        <div style='background:#161616;border-radius:10px;padding:12px 16px;
                    font-size:0.78rem;color:#666;line-height:1.8;'>
          <strong style='color:#aaa;'>Cómo se calcula:</strong>
          Hitos CRÍTICO pesan doble. SEGUIMIENTO aporta 50%.
          Si 3+ críticos en PENDIENTE, score máximo = 35%.
          &nbsp;·&nbsp;
          <span style='background:#3498db22;color:#3498db;padding:1px 6px;
                       border-radius:4px;font-size:0.65rem;'>AUTO</span>
          = calculado automáticamente cada ejecución.
        </div>
      </div>
    </div>
    <table class='table table-dark mb-0'>
      <thead>
        <tr>
          <th style='width:50px;text-align:center;'>TKR</th>
          <th style='width:35px;text-align:center;'>Est.</th>
          <th>Hito</th>
          <th style='width:110px;text-align:center;'>Categoría</th>
          <th style='width:110px;text-align:center;'>Estado</th>
          <th style='width:100px;text-align:center;'>Fecha</th>
        </tr>
      </thead>
      <tbody>{filas_hitos}</tbody>
    </table>
  </div>

  <!-- GRÁFICOS -->
  <div class='card text-center'>
    <h5>Bloque 4 — Gráficos</h5>
    <img src='data:image/png;base64,{img_b64}'
         style='width:100%;border-radius:10px;display:block;'>
    <p style='color:#555;font-size:0.75rem;margin-top:10px;margin-bottom:0;'>
      Izquierda: evolución normalizada 90 días (base 100). &nbsp;·&nbsp;
      Derecha: radar de cosecha — tamaño burbuja = peso en cartera.
    </p>
  </div>

  <!-- GLOSARIO -->
  <div class='card'>
    <h5>Glosario</h5>
    <table class='table table-dark mb-0' style='font-size:0.82rem;'>
      <thead>
        <tr>
          <th style='width:120px;'>Métrica</th>
          <th>Definición</th>
          <th style='width:200px;'>Interpretación</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>Y-TOT</code></td>
          <td style='color:#aaa;'>Yield total sobre precio de mercado actual. Incluye dividendo estimado y rendimiento equivalente de buybacks.</td>
          <td style='color:#aaa;font-size:0.78rem;'>Mayor = la posición paga más sobre su precio actual.</td>
        </tr>
        <tr style='background:#1a1a1a;'>
          <td><code>Y-CST</code></td>
          <td style='color:#aaa;'>Yield sobre precio de coste (precio medio de compra). Mide el rendimiento real sobre el capital comprometido.</td>
          <td style='color:#aaa;font-size:0.78rem;'>Crece conforme el precio sube — el dividendo sobre tu coste mejora.</td>
        </tr>
        <tr>
          <td><code>GAP</code></td>
          <td style='color:#aaa;'>Diferencia entre Y-TOT y el bono de referencia ({BONO_REF}%). Mide si la posición supera al activo libre de riesgo.</td>
          <td style='color:#2ecc71;font-size:0.78rem;'>Positivo = la acción bate al bono. &nbsp;<span style='color:#e74c3c;'>Negativo = el bono es más rentable.</span></td>
        </tr>
        <tr style='background:#1a1a1a;'>
          <td><code>BB</code></td>
          <td style='color:#aaa;'>Rendimiento equivalente de buybacks: recompras como % del precio de mercado, sumado al dividendo para calcular Y-TOT.</td>
          <td style='color:#aaa;font-size:0.78rem;'>Relevante en SAN — amplifica el rendimiento total más allá del dividendo explícito.</td>
        </tr>
        <tr>
          <td><code>SMA100</code></td>
          <td style='color:#aaa;'>Media móvil simple de 100 sesiones. Filtro técnico de tendencia para el estado del semáforo.</td>
          <td style='color:#aaa;font-size:0.78rem;'>Precio sobre SMA100 + GAP positivo = semáforo verde (OK).</td>
        </tr>
      </tbody>
    </table>
  </div>

</div>
</body>
</html>"""

        # ── Guardar HTML ──
        os.makedirs(CARPETA, exist_ok=True)
        with open(RUTA_HTML, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[largo] HTML guardado en {RUTA_HTML}")

        # ── Colab: mostrar inline ──
        if EN_COLAB:
            from IPython.display import display, HTML as IPY_HTML
            display(IPY_HTML(html))
            print("[colab] HTML renderizado inline.")

        # ── Telegram ──
        if ENVIAR_TELEGRAM:
            print("[largo] Enviando a Telegram...")
            url_base = f"https://api.telegram.org/bot{TOKEN}"

            # Resumen texto
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
                f"🛡️ *MONITOR NÚCLEO V1.0*\n"
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
                f"✓ {hitos_ok} cumplidos  |  ··· {hitos_seg} seguimiento  |  ✕ {hitos_pend} pendientes\n"
                f"{'='*30}\n"
                f"🕐 {fecha_now}"
            )

            requests.post(
                f"{url_base}/sendMessage",
                data={"chat_id": CHAT_ID, "text": resumen, "parse_mode": "Markdown"},
                timeout=15,
            )

            # HTML adjunto
            with open(RUTA_HTML, "rb") as f:
                requests.post(
                    f"{url_base}/sendDocument",
                    data={"chat_id": CHAT_ID, "caption": f"Monitor Núcleo V1.0 — {fecha_now}"},
                    files={"document": (RUTA_HTML, f, "text/html")},
                    timeout=15,
                )
            print("[largo] Enviado a Telegram.")

        return html

    except Exception as e:
        print(f"[error] {type(e).__name__}: {e}")
        if ENVIAR_TELEGRAM:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    data={"chat_id": CHAT_ID, "text": f"Error Monitor Núcleo V1.0: {e}"},
                    timeout=15,
                )
            except Exception:
                pass
        return None


# =============================================================================
if __name__ == "__main__":
    monitor_largo_v1()
