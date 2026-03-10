# =============================================================================
# MONITOR ESTRATEGICO DE CRECIMIENTO — VERSION 1.9
# Repositorio: MonitorGrowth
# =============================================================================
# Fix #12: Capitalizacion 'Repurchase Of Capital Stock'
# Fix #13: Sistema de advertencias por metrica no encontrada
# Fix #14: Busqueda fuzzy case-insensitive
# Fix #15: Glosario detallado metricas
# Fix #16: Validacion temporal trimestres (bug solapamiento Gartner)
# Fix #17: Alerta combinada NRR + Acrecion agresiva
# Fix #18: Bloque Valoracion de Mercado (P/FCF, descuento 52s, 3m)
# Fix #19: Senal cruzada Calidad/Precio
# Fix #20: Grafico P/FCF vs Descuento 52 semanas
# Fix #21: Glosario metricas de valoracion
# Fix #22: Compatibilidad total Colab + GitHub Actions + local
# Fix #23: Benchmark Nasdaq 100 (^NDX) — rendimiento relativo 12 meses
#          Tercer grafico: cada ticker vs NDX en escala normalizada (base 100)
#          Tabla de rendimiento relativo con alfa vs benchmark
#          Glosario actualizado con Rendimiento Relativo y Alfa
# =============================================================================

import sys
import os
import subprocess

# -----------------------------------------------------------------------------
# Instalacion automatica de dependencias (Fix #22)
# -----------------------------------------------------------------------------
REQUIRED_PKGS = {
    "yfinance":    "yfinance",
    "pandas":      "pandas",
    "matplotlib":  "matplotlib",
    "requests":    "requests",
}

def instalar_si_falta(pkgs):
    for import_name, pkg_name in pkgs.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"[setup] Instalando {pkg_name}...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg_name, "-q"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

instalar_si_falta(REQUIRED_PKGS)

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------
import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
import requests
import io
import base64
from datetime import datetime

# -----------------------------------------------------------------------------
# Deteccion de entorno (Fix #22)
# -----------------------------------------------------------------------------
def detectar_entorno():
    try:
        import google.colab  # noqa
        return 'colab'
    except ImportError:
        pass
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        return 'github'
    return 'local'

ENTORNO = detectar_entorno()
print(f"[setup] Entorno: {ENTORNO}")

# -----------------------------------------------------------------------------
# Credenciales — variables de entorno con fallback hardcoded
# -----------------------------------------------------------------------------
TOKEN   = os.environ.get('TELEGRAM_TOKEN',   '8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '8351044609')

# -----------------------------------------------------------------------------
# Ruta de salida HTML adaptada por entorno
# Repo : ControlesFinancieros
# Rama : growth
# HTML : Monitor_Growth.html  (raiz de la rama — sirve directo en GitHub Pages)
# -----------------------------------------------------------------------------
def ruta_html_salida():
    if ENTORNO == 'colab':
        return '/content/Monitor_Growth.html'
    if ENTORNO == 'github':
        # En GitHub Actions la rama ya es 'growth', escribimos en la raiz
        return 'Monitor_Growth.html'
    return 'Monitor_Growth.html'

RUTA_HTML = ruta_html_salida()

# -----------------------------------------------------------------------------
# Benchmark (Fix #23)
# -----------------------------------------------------------------------------
BENCHMARK_TICKER = '^NDX'
BENCHMARK_NOMBRE = 'Nasdaq 100'

# -----------------------------------------------------------------------------
# Etiquetas cash flow
# -----------------------------------------------------------------------------
LABELS = {
    "sbc": [
        'Stock Based Compensation',
        'Stock-Based Compensation',
        'Share Based Compensation',
        'Share-Based Compensation',
    ],
    "buybacks": [
        'Repurchase Of Capital Stock',
        'Repurchase of Capital Stock',
        'Common Stock Payments',
        'Common Stock Repurchase',
        'Repurchase Common Stock',
    ],
    "ocf":   ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities'],
    "capex": ['Capital Expenditure', 'Purchase Of PPE'],
}

# =============================================================================
# FUNCIONES DE COLOR Y LOGICA
# =============================================================================

def color_sbc(v):
    return '#ff4d4d' if v > 20 else '#2ecc71'

def color_nrr(v):
    return '#ff4d4d' if v < 100 else '#2ecc71'

def color_pfcf(v):
    if v <= 0:  return '#888888'
    if v < 20:  return '#2ecc71'
    if v < 35:  return '#f39c12'
    return '#ff4d4d'

def color_descuento(v):
    if v <= -30: return '#2ecc71'
    if v <= -10: return '#f39c12'
    return '#ff4d4d'

def color_alfa(v):
    """Color para alfa vs benchmark: positivo=verde, negativo=rojo."""
    if v > 5:    return '#2ecc71'
    if v > -5:   return '#f39c12'
    return '#ff4d4d'

def color_retorno(v):
    return '#2ecc71' if v >= 0 else '#ff4d4d'

def senal_cruzada(nrr, pfcf, desc_52s):
    calidad_ok = nrr >= 100
    precio_ok  = (pfcf > 0 and pfcf < 30) or desc_52s <= -20
    if calidad_ok and precio_ok:
        return "Calidad + Precio",     "#2ecc7122", "#2ecc71"
    elif calidad_ok and not precio_ok:
        return "Calidad sin Precio",   "#f39c1222", "#f39c12"
    elif not calidad_ok and precio_ok:
        return "Precio sin Calidad",   "#e67e2222", "#e67e22"
    else:
        return "Ni Calidad ni Precio", "#ff4d4d22", "#ff4d4d"

# =============================================================================
# EXTRACCION DE DATOS
# =============================================================================

def get_annual_sum(cf, labels, metric_name, warnings, tk):
    """Suma anual de 4 trimestres con validacion de solapamiento (Fix #16)."""
    for label in labels:
        if label in cf.index:
            row = cf.loc[label].dropna()
            if not row.empty:
                cols = row.index[:4]
                if len(cols) >= 2:
                    span = (cols[0] - cols[min(3, len(cols) - 1)]).days
                    if span > 400:
                        warnings.append({"tk": tk, "metric": metric_name,
                            "msg": f"Solapamiento temporal ({span} dias). Usando 2 trimestres.",
                            "level": "warning"})
                        cols = cols[:2]
                return float(row[cols].sum()), label

    # Fuzzy case-insensitive
    cf_index_lower = {l.lower(): l for l in cf.index}
    for label in labels:
        match = cf_index_lower.get(label.lower())
        if match:
            row = cf.loc[match].dropna()
            if not row.empty:
                cols = row.index[:4]
                if len(cols) >= 2:
                    span = (cols[0] - cols[min(3, len(cols) - 1)]).days
                    if span > 400:
                        warnings.append({"tk": tk, "metric": metric_name,
                            "msg": f"Fuzzy + solapamiento ({span} dias). Usando 2 trimestres.",
                            "level": "warning"})
                        cols = cols[:2]
                warnings.append({"tk": tk, "metric": metric_name,
                    "msg": f"Etiqueta fuzzy: '{match}' (buscada: '{label}')",
                    "level": "info"})
                return float(row[cols].sum()), match

    warnings.append({"tk": tk, "metric": metric_name,
        "msg": f"No encontrada. Etiquetas probadas: {labels}",
        "level": "warning"})
    return 0.0, None


def get_price_stats(tk, warnings):
    """Precio actual, maximo 52s, maximo 3m y descuentos (Fix #18)."""
    try:
        hist_1y = yf.Ticker(tk).history(period="1y")
        hist_3m = yf.Ticker(tk).history(period="3mo")
        if hist_1y.empty or hist_3m.empty:
            warnings.append({"tk": tk, "metric": "Precios historicos",
                "msg": "Historial vacio.", "level": "warning"})
            return None, None, None, None
        max_52s  = float(hist_1y['High'].max())
        max_3m   = float(hist_3m['High'].max())
        precio   = float(hist_1y['Close'].iloc[-1])
        desc_52s = ((precio - max_52s) / max_52s) * 100
        desc_3m  = ((precio - max_3m)  / max_3m)  * 100
        return precio, max_52s, desc_52s, desc_3m
    except Exception as e:
        warnings.append({"tk": tk, "metric": "Precios historicos",
            "msg": str(e), "level": "warning"})
        return None, None, None, None


def get_rendimiento_relativo(tickers, benchmark_tk, warnings):
    """
    Fix #23: Descarga 12 meses de precios para cada ticker y el benchmark.
    Normaliza a base 100 desde el primer dia comun.
    Devuelve:
      - serie_norm: dict {tk: pd.Series normalizada}
      - retornos:   dict {tk: float pct retorno total 12m}
      - retorno_ndx: float retorno total NDX 12m
      - alfa:        dict {tk: float diferencia vs benchmark}
    """
    all_tks = list(tickers) + [benchmark_tk]
    raw     = {}

    for tk in all_tks:
        try:
            hist = yf.Ticker(tk).history(period="1y")['Close']
            if not hist.empty:
                raw[tk] = hist
            else:
                warnings.append({"tk": tk, "metric": "Rendimiento relativo",
                    "msg": "Historial vacio para benchmark/ticker.", "level": "warning"})
        except Exception as e:
            warnings.append({"tk": tk, "metric": "Rendimiento relativo",
                "msg": str(e), "level": "warning"})

    if benchmark_tk not in raw:
        return {}, {}, None, {}

    # Alinear fechas — solo dias con datos en todos los tickers
    df = pd.DataFrame(raw).dropna()
    if df.empty:
        return {}, {}, None, {}

    # Normalizar a base 100
    base       = df.iloc[0]
    df_norm    = (df / base) * 100

    serie_norm = {tk: df_norm[tk] for tk in df_norm.columns}

    # Retornos totales
    retorno_ndx = float((df[benchmark_tk].iloc[-1] / df[benchmark_tk].iloc[0] - 1) * 100)
    retornos    = {}
    alfa        = {}
    for tk in tickers:
        if tk in df.columns:
            r = float((df[tk].iloc[-1] / df[tk].iloc[0] - 1) * 100)
            retornos[tk] = r
            alfa[tk]     = r - retorno_ndx
        else:
            retornos[tk] = None
            alfa[tk]     = None

    return serie_norm, retornos, retorno_ndx, alfa


# =============================================================================
# TELEGRAM
# =============================================================================

def enviar_telegram(html, token, chat_id):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendDocument",
            data={
                'chat_id':    chat_id,
                'caption':    "Monitor Growth V1.9 — Calidad | Valoracion | Rendimiento vs NDX",
                'parse_mode': 'Markdown',
            },
            files={'document': ('Monitor_Growth_v1_9.html', html.encode('utf-8'), 'text/html')},
            timeout=15,
        )
        if resp.ok:
            print("[telegram] Enviado correctamente.")
        else:
            print(f"[telegram] Error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[telegram] Excepcion: {e}")


def mostrar_en_colab(ruta):
    try:
        from IPython.display import display, FileLink
        display(FileLink(ruta, result_html_prefix="Descargar informe: "))
        print(f"[colab] HTML disponible en {ruta}")
    except Exception as e:
        print(f"[colab] {e}")


# =============================================================================
# FUNCION PRINCIPAL
# =============================================================================

def ejecutar_v1_9():

    TESIS_QUARTERLY = {
        "ADBE": {"nrr": 111.0, "t_g": 0, "color": "#2ecc71"},
        "IT":   {"nrr": 105.0, "t_g": 0, "color": "#9b59b6"},
        "FDS":  {"nrr": 101.0, "t_g": 0, "color": "#34495e"},
        "CRM":  {"nrr": 108.5, "t_g": 0, "color": "#3498db"},
        "PYPL": {"nrr": 98.2,  "t_g": 1, "color": "#e67e22"},
    }

    data_points  = []
    all_warnings = []

    # -------------------------------------------------------------------------
    # Fix #23: Descargar rendimiento relativo ANTES del bucle principal
    # -------------------------------------------------------------------------
    print("[datos] Descargando rendimiento relativo vs NDX...")
    serie_norm, retornos_12m, retorno_ndx, alfa_12m = get_rendimiento_relativo(
        list(TESIS_QUARTERLY.keys()), BENCHMARK_TICKER, all_warnings
    )

    # -------------------------------------------------------------------------
    # Bucle principal de metricas fundamentales
    # -------------------------------------------------------------------------
    for tk, tesis in TESIS_QUARTERLY.items():
        ticker_warnings = []
        try:
            print(f"[datos] Procesando {tk}...")
            asset = yf.Ticker(tk)
            cf    = asset.quarterly_cashflow
            info  = asset.info

            sbc_total, sbc_label = get_annual_sum(cf, LABELS["sbc"],     "SBC",      ticker_warnings, tk)
            bb_raw,    bb_label  = get_annual_sum(cf, LABELS["buybacks"], "Buybacks", ticker_warnings, tk)
            buybacks = abs(bb_raw)

            price     = float(info.get('currentPrice') or info.get('regularMarketPrice') or 1)
            fcf_total = float(info.get('freeCashflow') or 0)

            if fcf_total == 0:
                ocf,   _ = get_annual_sum(cf, LABELS["ocf"],   "OCF",   ticker_warnings, tk)
                capex, _ = get_annual_sum(cf, LABELS["capex"], "CapEx", ticker_warnings, tk)
                fcf_total = ocf - abs(capex)
                if fcf_total != 0:
                    ticker_warnings.append({"tk": tk, "metric": "FCF",
                        "msg": "Calculado como OCF - CapEx.", "level": "info"})

            sbc_neto_valor = sbc_total - buybacks
            if fcf_total > 0:
                sbc_neto_ratio = (sbc_neto_valor / fcf_total) * 100
            elif fcf_total < 0:
                sbc_neto_ratio = -(abs(sbc_neto_valor) / abs(fcf_total)) * 100
            else:
                sbc_neto_ratio = 0.0
                ticker_warnings.append({"tk": tk, "metric": "SBC_Neto/FCF",
                    "msg": "FCF = 0, ratio no calculable.", "level": "warning"})

            shares    = float(info.get('sharesOutstanding') or 1)
            fcf_yield = ((fcf_total / shares) / price * 100) if price > 0 else 0

            _, max_52s, desc_52s, desc_3m = get_price_stats(tk, ticker_warnings)
            pfcf = (price * shares / fcf_total) if fcf_total > 0 else 0

            desc_52s_val = desc_52s if desc_52s is not None else 0
            desc_3m_val  = desc_3m  if desc_3m  is not None else 0
            senal_label, senal_bg, senal_color = senal_cruzada(tesis["nrr"], pfcf, desc_52s_val)

            # Rendimiento relativo
            ret_12m  = retornos_12m.get(tk)
            alfa_val = alfa_12m.get(tk)

            diag = []
            if tesis["nrr"] < 100: diag.append("NRR < 100%")
            else:                   diag.append("NRR Solido")
            if sbc_neto_valor < 0:
                diag.append("Acrecion: BB > SBC")
                if tesis["nrr"] < 100 and sbc_neto_ratio < -50:
                    diag.append("ALERTA: Acrecion agresiva + NRR < 100%")
            elif sbc_neto_ratio > 20:
                diag.append("Dilucion Neta Alta")
            if fcf_yield > 5: diag.append("Yield Atractivo")
            if any(w["level"] == "warning" for w in ticker_warnings):
                diag.append("Dato incompleto")

            warn_count = len([w for w in ticker_warnings if w["level"] == "warning"])
            print(f"  {tk}: P/FCF={pfcf:.1f}x | Desc52s={desc_52s_val:.1f}% | "
                  f"Ret12m={ret_12m:.1f}% | Alfa={alfa_val:.1f}pp | "
                  f"Senal={senal_label}")

            all_warnings.extend(ticker_warnings)

            data_points.append({
                "TKR":          tk,
                "PRECIO":       f"${price:.2f}",
                "NRR":          tesis["nrr"],
                "NRR_RAW":      tesis["nrr"],
                "SBC_NETO":     sbc_neto_ratio,
                "YIELD":        f"{fcf_yield:.1f}%",
                "T_G":          f"{tesis['t_g']}/4",
                "DIAG":         " | ".join(diag),
                "color":        tesis["color"],
                "SBC_ABS":      f"${sbc_total/1e9:.2f}B",
                "BB_ABS":       f"${buybacks/1e9:.2f}B",
                "FCF_ABS":      f"${fcf_total/1e9:.2f}B",
                "SBC_LBL":      sbc_label or "no encontrado",
                "BB_LBL":       bb_label  or "no encontrado",
                "HAS_WARN":     warn_count > 0,
                "PFCF":         pfcf,
                "PFCF_STR":     f"{pfcf:.1f}x" if pfcf > 0 else "N/D",
                "DESC_52S":     desc_52s_val,
                "DESC_52S_STR": f"{desc_52s_val:.1f}%",
                "DESC_3M":      desc_3m_val,
                "DESC_3M_STR":  f"{desc_3m_val:.1f}%",
                "MAX_52S":      f"${max_52s:.2f}" if max_52s else "N/D",
                "SENAL_LABEL":  senal_label,
                "SENAL_BG":     senal_bg,
                "SENAL_COLOR":  senal_color,
                "RET_12M":      ret_12m,
                "RET_12M_STR":  f"{ret_12m:+.1f}%" if ret_12m is not None else "N/D",
                "ALFA":         alfa_val,
                "ALFA_STR":     f"{alfa_val:+.1f}pp" if alfa_val is not None else "N/D",
            })

        except Exception as e:
            print(f"[error] {tk}: {type(e).__name__} - {e}")
            all_warnings.append({"tk": tk, "metric": "GENERAL",
                "msg": f"{type(e).__name__}: {e}", "level": "error"})

    if not data_points:
        print("[error] No se obtuvieron datos. Abortando.")
        return

    # =========================================================================
    # GRAFICOS
    # Diseno: 3 graficos en layout 2+1
    #   Fila superior: [G1: NRR vs Dilucion] [G2: P/FCF vs Descuento]
    #   Fila inferior: [G3: Rendimiento relativo 12m vs NDX — ancho completo]
    # =========================================================================
    fig = plt.figure(figsize=(16, 12), dpi=160, facecolor='#0d1117')

    # Layout: 2 filas — fila superior 2 graficos, fila inferior 1 ancho completo
    gs_outer = gridspec.GridSpec(2, 1, figure=fig, hspace=0.45,
                                  height_ratios=[1, 1.1])
    gs_top   = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=gs_outer[0], wspace=0.35)

    BG_CARD  = '#161b22'
    BG_PLOT  = '#0d1117'
    COLOR_GRID = '#21262d'

    def estilizar_ax(ax, titulo, color_titulo='#00d4ff'):
        ax.set_facecolor(BG_CARD)
        ax.tick_params(colors='#8b949e', labelsize=8)
        ax.set_title(titulo, color=color_titulo, fontsize=10,
                     fontweight='bold', pad=10, loc='left')
        for spine in ax.spines.values():
            spine.set_edgecolor('#21262d')
        ax.grid(True, color=COLOR_GRID, linewidth=0.5, alpha=0.7)

    # -------------------------------------------------------------------------
    # Grafico 1: NRR vs Dilucion neta
    # -------------------------------------------------------------------------
    ax1 = fig.add_subplot(gs_top[0])
    sbc_vals   = [p["SBC_NETO"] for p in data_points]
    y_margin   = (max(sbc_vals) - min(sbc_vals)) * 0.3 + 10
    y_plot_min = min(sbc_vals) - y_margin
    y_plot_max = max(sbc_vals) + y_margin

    ax1.axhspan(y_plot_min, 0,          alpha=0.07, color='#2ecc71', zorder=0)
    ax1.axhspan(0,          y_plot_max, alpha=0.07, color='#ff4d4d', zorder=0)
    ax1.axvline(100, color='#ff4d4d', linestyle='--', alpha=0.35, linewidth=1)
    ax1.axhline(0,   color='#8b949e', linestyle='-',  alpha=0.3,  linewidth=1)

    for p in data_points:
        edge = '#e67e22' if (p["NRR_RAW"] < 100 and p["SBC_NETO"] < -50) else '#e6edf3'
        m    = '*' if p["HAS_WARN"] else 'o'
        ax1.scatter(p["NRR"], p["SBC_NETO"], s=550, color=p["color"],
                    alpha=0.9, edgecolors=edge, linewidths=1.8, zorder=5, marker=m)
        ax1.text(p["NRR"], p["SBC_NETO"] + y_margin * 0.15,
                 p["TKR"], fontsize=8.5, fontweight='bold',
                 ha='center', color='#e6edf3', zorder=6)

    ax1.set_ylim(y_plot_min, y_plot_max)
    ax1.set_xlabel("NRR (%)", color='#8b949e', fontsize=9)
    ax1.set_ylabel("SBC Neto / FCF (%)\nAcrecion  ↑  |  ↓  Dilucion",
                   color='#8b949e', fontsize=8)
    estilizar_ax(ax1, "BLOQUE 1  —  Calidad del Negocio")

    # Anotaciones zonas
    ax1.text(ax1.get_xlim()[0] + 0.5 if ax1.get_xlim() else 97,
             y_plot_max * 0.88, "DILUCION NETA",
             fontsize=7, color='#ff4d4d', alpha=0.6, va='top')
    ax1.text(ax1.get_xlim()[0] + 0.5 if ax1.get_xlim() else 97,
             y_plot_min * 0.88, "ACRECION NETA",
             fontsize=7, color='#2ecc71', alpha=0.6, va='bottom')

    # -------------------------------------------------------------------------
    # Grafico 2: P/FCF vs Descuento 52 semanas
    # -------------------------------------------------------------------------
    ax2 = fig.add_subplot(gs_top[1])
    pfcf_vals_ok = [p["PFCF"] for p in data_points if p["PFCF"] > 0]
    desc_vals    = [p["DESC_52S"] for p in data_points]

    x_min  = min(desc_vals) - 12
    x_max  = min(max(desc_vals) + 12, 5)
    y_min2 = max(0, min(pfcf_vals_ok) - 8)  if pfcf_vals_ok else 0
    y_max2 = max(pfcf_vals_ok) + 12         if pfcf_vals_ok else 60

    # Zonas cuadrante
    ax2.axvspan(x_min, -20,   alpha=0.06, color='#2ecc71', zorder=0)
    ax2.axvspan(-20,  x_max,  alpha=0.06, color='#ff4d4d', zorder=0)
    ax2.axhline(20,  color='#2ecc71', linestyle='--', alpha=0.35, linewidth=1)
    ax2.axhline(35,  color='#ff4d4d', linestyle='--', alpha=0.35, linewidth=1)
    ax2.axvline(-20, color='#2ecc71', linestyle='--', alpha=0.35, linewidth=1)

    for p in data_points:
        if p["PFCF"] <= 0:
            continue
        ax2.scatter(p["DESC_52S"], p["PFCF"], s=550, color=p["color"],
                    alpha=0.9, edgecolors='#e6edf3', linewidths=1.5, zorder=5)
        ax2.text(p["DESC_52S"],
                 p["PFCF"] + (y_max2 - y_min2) * 0.05,
                 p["TKR"], fontsize=8.5, fontweight='bold',
                 ha='center', color='#e6edf3', zorder=6)

    ax2.set_xlim(x_min, x_max)
    ax2.set_ylim(y_min2, y_max2)
    ax2.set_xlabel("Descuento vs Maximo 52 semanas (%)", color='#8b949e', fontsize=9)
    ax2.set_ylabel("P/FCF (x)", color='#8b949e', fontsize=9)
    estilizar_ax(ax2, "BLOQUE 2  —  Valoracion de Mercado", color_titulo='#a371f7')

    # Etiquetas cuadrantes
    pad_x = (x_max - x_min) * 0.03
    pad_y = (y_max2 - y_min2) * 0.04
    ax2.text(x_min + pad_x, y_max2 - pad_y, "CARO\n+ DESCUENTO",
             fontsize=6.5, color='#8b949e', va='top', linespacing=1.4)
    ax2.text(x_max - pad_x, y_max2 - pad_y, "CARO\n+ PREMIUM",
             fontsize=6.5, color='#ff7b72', va='top', ha='right', linespacing=1.4)
    ax2.text(x_min + pad_x, y_min2 + pad_y, "BARATO\n+ DESCUENTO",
             fontsize=6.5, color='#3fb950', va='bottom', linespacing=1.4)
    ax2.text(x_max - pad_x, y_min2 + pad_y, "BARATO\n+ PREMIUM",
             fontsize=6.5, color='#8b949e', va='bottom', ha='right', linespacing=1.4)

    # -------------------------------------------------------------------------
    # Grafico 3: Rendimiento relativo 12m vs NDX (Fix #23)
    # -------------------------------------------------------------------------
    ax3 = fig.add_subplot(gs_outer[1])
    estilizar_ax(ax3,
                 f"BLOQUE 3  —  Rendimiento Relativo 12 meses  vs  {BENCHMARK_NOMBRE}",
                 color_titulo='#f0883e')

    if serie_norm and BENCHMARK_TICKER in serie_norm:
        # Benchmark en primer lugar — linea blanca destacada
        ndx_serie = serie_norm[BENCHMARK_TICKER]
        ax3.plot(ndx_serie.index, ndx_serie.values,
                 color='#e6edf3', linewidth=2.2, alpha=0.9,
                 linestyle='--', zorder=4, label=BENCHMARK_NOMBRE)
        ax3.fill_between(ndx_serie.index, 100, ndx_serie.values,
                         alpha=0.04, color='#e6edf3')

        # Cada ticker
        for p in data_points:
            tk = p["TKR"]
            if tk not in serie_norm:
                continue
            serie = serie_norm[tk]
            alfa  = alfa_12m.get(tk)
            # Grosor mayor si bate al NDX
            lw    = 2.0 if (alfa is not None and alfa > 0) else 1.4
            alpha = 0.95 if (alfa is not None and alfa > 0) else 0.75
            ax3.plot(serie.index, serie.values,
                     color=p["color"], linewidth=lw, alpha=alpha,
                     zorder=5, label=f"{tk} ({p['RET_12M_STR']})")

            # Etiqueta al final de la linea
            ultimo_val = float(serie.iloc[-1])
            ax3.annotate(
                f"  {tk}",
                xy=(serie.index[-1], ultimo_val),
                fontsize=8, fontweight='bold',
                color=p["color"], va='center',
                xytext=(4, 0), textcoords='offset points'
            )

        # Linea base 100
        ax3.axhline(100, color='#30363d', linewidth=1, linestyle='-', zorder=2)
        ax3.set_ylabel("Retorno indexado (base 100)", color='#8b949e', fontsize=9)
        ax3.set_xlabel("", color='#8b949e')

        # Formato eje Y con sufijo
        ax3.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}"))

        # Leyenda elegante
        legend = ax3.legend(
            loc='upper left', fontsize=8,
            framealpha=0.15, edgecolor='#30363d',
            facecolor='#161b22', labelcolor='#e6edf3',
            handlelength=1.8, borderpad=0.8
        )

        # Banda de fechas formateada
        fecha_ini = serie_norm[BENCHMARK_TICKER].index[0].strftime('%b %Y')
        fecha_fin = serie_norm[BENCHMARK_TICKER].index[-1].strftime('%b %Y')
        ax3.set_title(
            f"BLOQUE 3  —  Rendimiento Relativo 12 meses  vs  {BENCHMARK_NOMBRE}"
            f"   |   {fecha_ini} → {fecha_fin}",
            color='#f0883e', fontsize=10, fontweight='bold', pad=10, loc='left'
        )

    else:
        ax3.text(0.5, 0.5, "Datos de rendimiento relativo no disponibles",
                 ha='center', va='center', transform=ax3.transAxes,
                 color='#8b949e', fontsize=10)

    # Titulo global
    fig.suptitle(
        f"Monitor Growth  V1.9   |   {datetime.now().strftime('%d %b %Y  %H:%M')}",
        color='#e6edf3', fontsize=13, fontweight='bold', y=0.98
    )

    # Exportar grafico
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=BG_PLOT,
                bbox_inches='tight', dpi=160)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode()
    plt.close(fig)
    print("[graficos] Generados correctamente.")

    # =========================================================================
    # HTML — TABLAS
    # =========================================================================

    # --- Bloque 1: Calidad ---
    filas_calidad = ""
    for p in data_points:
        wi  = " <sup style='color:#f0883e;font-size:0.65rem;'>(*)</sup>" if p["HAS_WARN"] else ""
        tip = ("SBC:" + p["SBC_ABS"] + " [" + p["SBC_LBL"] + "]  "
               "BB:" + p["BB_ABS"] + " [" + p["BB_LBL"] + "]  "
               "FCF:" + p["FCF_ABS"])
        filas_calidad += (
            "<tr>"
            "<td><span style='color:" + p["color"] + ";font-weight:700;font-family:monospace;'>"
            + p["TKR"] + "</span>" + wi + "</td>"
            "<td style='color:" + color_nrr(p["NRR_RAW"]) + ";font-weight:700;'>"
            + str(p["NRR"]) + "%</td>"
            "<td style='color:" + color_sbc(p["SBC_NETO"]) + ";font-weight:700;cursor:help;' title='"
            + tip + "'>" + f"{p['SBC_NETO']:.1f}%" + "</td>"
            "<td>" + p["YIELD"] + "</td>"
            "<td style='text-align:center;'>" + p["T_G"] + "</td>"
            "<td style='font-size:0.78rem;color:#8b949e;'>" + p["DIAG"] + "</td>"
            "</tr>"
        )

    # --- Bloque 2: Valoracion ---
    filas_valor = ""
    for p in data_points:
        filas_valor += (
            "<tr>"
            "<td><span style='color:" + p["color"] + ";font-weight:700;font-family:monospace;'>"
            + p["TKR"] + "</span></td>"
            "<td style='font-family:monospace;color:#e6edf3;'>" + p["PRECIO"] + "</td>"
            "<td style='color:" + color_pfcf(p["PFCF"]) + ";font-weight:700;'>"
            + p["PFCF_STR"] + "</td>"
            "<td style='color:" + color_descuento(p["DESC_52S"]) + ";font-weight:700;'>"
            + p["DESC_52S_STR"] + "</td>"
            "<td style='color:" + color_descuento(p["DESC_3M"]) + ";font-weight:700;'>"
            + p["DESC_3M_STR"] + "</td>"
            "<td style='font-size:0.78rem;color:#8b949e;'>" + p["MAX_52S"] + "</td>"
            "<td><span style='background:" + p["SENAL_BG"] + ";color:" + p["SENAL_COLOR"]
            + ";padding:3px 12px;border-radius:20px;font-size:0.72rem;font-weight:700;"
            "letter-spacing:0.3px;white-space:nowrap;'>"
            + p["SENAL_LABEL"] + "</span></td>"
            "</tr>"
        )

    # --- Bloque 3: Rendimiento relativo ---
    ret_ndx_str = f"{retorno_ndx:+.1f}%" if retorno_ndx is not None else "N/D"
    filas_relativo = ""
    for p in data_points:
        alfa_v = p["ALFA"]
        beat   = alfa_v is not None and alfa_v > 0
        icono  = "▲" if beat else ("▼" if (alfa_v is not None and alfa_v < 0) else "—")
        filas_relativo += (
            "<tr>"
            "<td><span style='color:" + p["color"] + ";font-weight:700;font-family:monospace;'>"
            + p["TKR"] + "</span></td>"
            "<td style='color:" + (color_retorno(p["RET_12M"]) if p["RET_12M"] is not None else '#888')
            + ";font-weight:700;'>" + p["RET_12M_STR"] + "</td>"
            "<td style='color:#8b949e;font-weight:600;'>" + ret_ndx_str + "</td>"
            "<td style='color:" + (color_alfa(alfa_v) if alfa_v is not None else '#888')
            + ";font-weight:700;'>" + icono + "  " + p["ALFA_STR"] + "</td>"
            "<td style='font-size:0.78rem;color:#8b949e;'>"
            + ("Bate al benchmark" if beat else ("Rezagado vs benchmark" if alfa_v is not None else "N/D"))
            + "</td>"
            "</tr>"
        )

    # --- Log de advertencias ---
    icon_map  = {"warning": "&#9888;", "info": "&#9432;", "error": "&#10007;"}
    color_map = {"warning": "#e67e22", "info": "#3498db", "error": "#ff4d4d"}
    filas_w   = ""
    if all_warnings:
        for w in all_warnings:
            ico   = icon_map.get(w["level"], "&#9432;")
            color = color_map.get(w["level"], "#888")
            filas_w += (
                "<tr>"
                "<td style='color:" + color + ";font-weight:600;'>" + ico + " " + w["tk"] + "</td>"
                "<td style='color:#8b949e;font-size:0.78rem;'>" + w["metric"] + "</td>"
                "<td style='color:#6e7681;font-size:0.76rem;'>" + w["msg"] + "</td>"
                "</tr>"
            )
    else:
        filas_w = ("<tr><td colspan='3' style='color:#3fb950;text-align:center;'>"
                   "Todos los datos encontrados correctamente</td></tr>")

    # =========================================================================
    # GLOSARIO V1.9
    # =========================================================================
    glosario = """
      <tbody>
        <tr>
          <td><span class='g-title'>NRR</span><br>
              <small class='g-sub'>Net Revenue Retention</small></td>
          <td>
            Mide que porcentaje de los ingresos de los clientes existentes se retiene y hace crecer anio a anio,
            incluyendo expansiones y upsells pero descontando cancelaciones y downgrades.<br><br>
            <b>Formula:</b> <code>(Ingresos clientes anio N) / (Ingresos mismos clientes anio N-1) x 100</code><br><br>
            NRR mayor de 100% significa que la base existente crece sola, sin necesidad de nuevas adquisiciones.
            Es el indicador mas fiable de la salud del producto y la fidelidad del cliente en negocios de suscripcion.
          </td>
          <td>
            <span class='g-verde'>Mayor de 110% — Excelente. Expansion organica fuerte.</span><br><br>
            <span class='g-amarillo'>100-110% — Solido. Retencion saludable.</span><br><br>
            <span class='g-rojo'>Menor de 100% — Churn neto. La base se contrae.</span>
          </td>
        </tr>
        <tr class='g-alt'>
          <td><span class='g-title'>FCF</span><br>
              <small class='g-sub'>Free Cash Flow</small></td>
          <td>
            Caja real generada por el negocio tras pagar operaciones e inversiones en activos fisicos.
            No se distorsiona por amortizaciones ni ajustes no monetarios.<br><br>
            <b>Formula:</b> <code>FCF = Flujo de Caja Operativo - CapEx</code><br><br>
            Es la metrica de rentabilidad mas honesta: refleja el dinero disponible para recompras,
            dividendos, reduccion de deuda o reinversion organica.
          </td>
          <td>
            <span class='g-verde'>Positivo y creciente — Negocio autosuficiente.</span><br><br>
            <span class='g-amarillo'>Positivo pero estable — Madurez sin reinversion activa.</span><br><br>
            <span class='g-rojo'>Negativo — Quema de caja. Depende de financiacion externa.</span>
          </td>
        </tr>
        <tr>
          <td><span class='g-title'>FCF Yield</span><br>
              <small class='g-sub'>Rentabilidad sobre precio</small></td>
          <td>
            Cuanto FCF genera la empresa por cada dolar invertido a precio de mercado.
            Equivalente al earnings yield pero con caja real.<br><br>
            <b>Formula:</b> <code>(FCF / Acciones en circulacion) / Precio x 100</code><br><br>
            Permite comparar la rentabilidad implicita de la accion frente a alternativas como bonos.
            Especialmente util para detectar valoraciones exigentes en empresas de alto crecimiento.
          </td>
          <td>
            <span class='g-verde'>Mayor de 5% — Valoracion atractiva respecto al mercado.</span><br><br>
            <span class='g-amarillo'>2-5% — Razonable para negocios de calidad.</span><br><br>
            <span class='g-rojo'>Menor de 2% — Prima elevada. Poco margen de error.</span>
          </td>
        </tr>
        <tr class='g-alt'>
          <td><span class='g-title'>SBC Neto / FCF</span><br>
              <small class='g-sub'>Dilucion real ajustada</small></td>
          <td>
            Metrica central del monitor. Mide la dilucion neta real del accionista despues de descontar
            el efecto compensador de las recompras.<br><br>
            <b>Formula:</b> <code>(SBC - Buybacks) / FCF x 100</code><br><br>
            Valor negativo = acrecion neta: la empresa recompra mas acciones de las que emite,
            aumentando la participacion de cada accionista existente con el tiempo.
            Valor positivo = el accionista financia el salario de los empleados con su participacion.
          </td>
          <td>
            <span class='g-verde'>Menor de 0% — Acrecion. Buybacks superan al SBC.</span><br><br>
            <span class='g-amarillo'>0-20% — Dilucion moderada y gestionable.</span><br><br>
            <span class='g-rojo'>Mayor de 20% — Dilucion neta alta. Impacto relevante.</span>
          </td>
        </tr>
        <tr>
          <td><span class='g-title'>P/FCF</span><br>
              <small class='g-sub'>Precio sobre Free Cash Flow</small></td>
          <td>
            Multiple de valoracion: cuantos anios de FCF actual paga el mercado al precio vigente.
            Equivalente al PER pero con caja real, mas resistente a la manipulacion contable.<br><br>
            <b>Formula:</b> <code>Market Cap / FCF anual</code><br><br>
            Importante: el FCF de este monitor no ajusta el SBC. Interpretarlo siempre junto
            con SBC Neto/FCF — un P/FCF bajo con SBC alto puede ser una trampa contable.
          </td>
          <td>
            <span class='g-verde'>Menor de 20x — Barato en terminos historicos para tech de calidad.</span><br><br>
            <span class='g-amarillo'>20-35x — Razonable para empresas con crecimiento sostenido.</span><br><br>
            <span class='g-rojo'>Mayor de 35x — Prima elevada. Exige ejecucion perfecta.</span>
          </td>
        </tr>
        <tr class='g-alt'>
          <td><span class='g-title'>Descuento vs Maximos</span><br>
              <small class='g-sub'>52 semanas y 3 meses</small></td>
          <td>
            Cuanto ha caido la accion desde sus maximos recientes.
            No garantiza que este barata en absoluto, pero indica que el mercado ya ha revisado
            las expectativas a la baja.<br><br>
            <b>Formula:</b> <code>(Precio actual - Maximo periodo) / Maximo periodo x 100</code><br><br>
            Combinado con P/FCF bajo y NRR solido es la senal mas robusta de oportunidad de entrada.
            Sin NRR solido, el descuento puede ser una trampa de valor.
          </td>
          <td>
            <span class='g-verde'>Menor de -30% — Gran descuento. Revision de expectativas probable.</span><br><br>
            <span class='g-amarillo'>-10% a -30% — Descuento moderado. Vigilar catalizadores.</span><br><br>
            <span class='g-rojo'>Mayor de -10% — Cerca de maximos. Prima de mercado elevada.</span>
          </td>
        </tr>
        <tr>
          <td><span class='g-title'>Senal Calidad / Precio</span><br>
              <small class='g-sub'>Cruce de ambos bloques</small></td>
          <td>
            Indicador sintetico que cruza la calidad del negocio (NRR) con el precio de mercado
            (P/FCF y descuento vs maximos). Resume en una etiqueta el estado de la oportunidad.<br><br>
            La distincion critica: <b>Calidad sin Precio</b> requiere paciencia — el negocio es excelente
            pero el precio ya descuenta mucho del futuro. <b>Precio sin Calidad</b> es la trampa de valor
            clasica — el descuento no compensa el deterioro del negocio subyacente.
          </td>
          <td>
            <span class='g-verde' style='font-weight:700;'>Calidad + Precio — Oportunidad real.</span><br><br>
            <span class='g-amarillo' style='font-weight:700;'>Calidad sin Precio — Excelente pero caro. Esperar.</span><br><br>
            <span style='color:#e67e22;font-weight:700;'>Precio sin Calidad — Trampa de valor potencial.</span><br><br>
            <span class='g-rojo' style='font-weight:700;'>Ni Calidad ni Precio — Evitar.</span>
          </td>
        </tr>
        <tr class='g-alt'>
          <td><span class='g-title'>Rendimiento Relativo</span><br>
              <small class='g-sub'>Retorno 12m vs Nasdaq 100</small></td>
          <td>
            Compara el retorno total de cada ticker en los ultimos 12 meses contra el Nasdaq 100 (^NDX),
            que es el benchmark natural para empresas tech/growth de gran y mediana capitalizacion USA.<br><br>
            Ambas series se normalizan a base 100 desde el primer dia comun del periodo,
            lo que permite ver la divergencia acumulada de forma visual e intuitiva.<br><br>
            Un ticker que bate al NDX con NRR solido y P/FCF razonable es la combinacion mas potente
            que puede mostrar el monitor.
          </td>
          <td>
            <span class='g-verde'>Retorno mayor que NDX — Alfa positivo. Bate al sector.</span><br><br>
            <span class='g-amarillo'>Retorno similar al NDX (+/- 5pp) — Comportamiento en linea con el mercado.</span><br><br>
            <span class='g-rojo'>Retorno menor que NDX — Alfa negativo. Rezagado vs sector.</span>
          </td>
        </tr>
        <tr>
          <td><span class='g-title'>Alfa vs Benchmark</span><br>
              <small class='g-sub'>Diferencial de retorno</small></td>
          <td>
            Diferencia en puntos porcentuales entre el retorno del ticker y el retorno del Nasdaq 100
            en el mismo periodo de 12 meses.<br><br>
            <b>Formula:</b> <code>Alfa = Retorno ticker 12m - Retorno NDX 12m</code><br><br>
            Alfa positivo no siempre es una senal de calidad — puede deberse a momentum especulativo.
            Alfa negativo persistente en un negocio con NRR solido puede indicar una oportunidad,
            no un deterioro: el mercado puede tardar en reconocer la calidad del negocio.
          </td>
          <td>
            <span class='g-verde'>Mayor de +5pp — Claramente por encima del sector.</span><br><br>
            <span class='g-amarillo'>-5pp a +5pp — En linea con el benchmark.</span><br><br>
            <span class='g-rojo'>Menor de -5pp — Rezagado. Revisar si es oportunidad o deterioro.</span>
          </td>
        </tr>
        <tr class='g-alt'>
          <td><span class='g-title'>T-G</span><br>
              <small class='g-sub'>Tesis-Goals</small></td>
          <td>
            Contador de hitos de la tesis de inversion cumplidos sobre el total definido.
            Cada inversor define sus propios criterios cualitativos o cuantitativos
            para mantener la conviccion en la posicion.<br><br>
            Funciona como semaforo de conviccion: si los hitos no se cumplen en el plazo esperado,
            es senal de revision de la posicion independientemente de las metricas cuantitativas.
          </td>
          <td>
            <span class='g-verde'>3-4 / 4 — Tesis en curso. Alta conviccion.</span><br><br>
            <span class='g-amarillo'>2 / 4 — Tesis parcial. Seguimiento activo necesario.</span><br><br>
            <span class='g-rojo'>0-1 / 4 — Tesis estancada. Revisar o cerrar posicion.</span>
          </td>
        </tr>
      </tbody>
    """

    # =========================================================================
    # HTML FINAL — ensamblado
    # =========================================================================
    badges = {
        'colab':  ("<span class='badge-env' style='background:#f0883e22;color:#f0883e;'>"
                   "Google Colab</span>"),
        'github': ("<span class='badge-env' style='background:#3fb95022;color:#3fb950;'>"
                   "GitHub Actions</span>"),
        'local':  ("<span class='badge-env' style='background:#58a6ff22;color:#58a6ff;'>"
                   "Local</span>"),
    }
    fecha_gen = datetime.now().strftime('%d %b %Y  %H:%M')

    html = f"""<!DOCTYPE html>
<html lang='es'>
<head>
  <meta charset='UTF-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1.0'>
  <title>Monitor Growth V1.9</title>
  <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
  <style>
    /* ---- Base ---- */
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      background: #0d1117;
      color: #e6edf3;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size: 14px;
      padding: 28px 20px;
      line-height: 1.5;
    }}
    /* ---- Header ---- */
    .header-wrap {{
      display: flex;
      align-items: baseline;
      gap: 14px;
      margin-bottom: 4px;
    }}
    .header-wrap h1 {{
      font-size: 1.55rem;
      font-weight: 700;
      margin: 0;
      color: #e6edf3;
    }}
    .header-wrap h1 span {{ color: #58a6ff; }}
    .badge-env {{
      padding: 2px 10px;
      border-radius: 20px;
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.3px;
    }}
    .subtitle {{
      color: #6e7681;
      font-size: 0.78rem;
      margin-bottom: 28px;
    }}
    /* ---- Cards ---- */
    .card-m {{
      background: #161b22;
      border-radius: 12px;
      padding: 22px 24px;
      margin-bottom: 20px;
      border: 1px solid #21262d;
    }}
    .card-m.calidad {{ border-left: 3px solid #00d4ff; }}
    .card-m.valor   {{ border-left: 3px solid #a371f7; }}
    .card-m.relativo {{ border-left: 3px solid #f0883e; }}
    .card-m.log     {{ border-left: 3px solid #30363d; }}
    .card-m.glosario {{ border-left: 3px solid #58a6ff; }}
    /* ---- Separadores de bloque ---- */
    .bloque-sep {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin: 28px 0 14px;
      color: #6e7681;
      font-size: 0.72rem;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      font-weight: 600;
    }}
    .bloque-sep::before, .bloque-sep::after {{
      content: '';
      flex: 1;
      height: 1px;
      background: #21262d;
    }}
    /* ---- Titulos de card ---- */
    .card-titulo {{
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 1.2px;
      text-transform: uppercase;
      margin-bottom: 8px;
    }}
    .card-titulo.c1 {{ color: #00d4ff; }}
    .card-titulo.c2 {{ color: #a371f7; }}
    .card-titulo.c3 {{ color: #f0883e; }}
    .card-titulo.cg {{ color: #58a6ff; }}
    .card-desc {{
      color: #6e7681;
      font-size: 0.75rem;
      margin-bottom: 14px;
    }}
    /* ---- Tablas ---- */
    table {{ width: 100%; border-collapse: collapse; }}
    thead th {{
      color: #6e7681;
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      font-weight: 600;
      padding: 8px 12px;
      border-bottom: 1px solid #21262d;
    }}
    tbody td {{
      padding: 10px 12px;
      border-bottom: 1px solid #161b22;
      vertical-align: middle;
      font-size: 0.85rem;
    }}
    tbody tr:last-child td {{ border-bottom: none; }}
    tbody tr:hover {{ background: #1c2128; transition: background 0.15s; }}
    /* ---- Glosario ---- */
    .g-title {{ color: #58a6ff; font-weight: 700; font-size: 0.88rem; }}
    .g-sub   {{ color: #6e7681; font-size: 0.72rem; }}
    .g-alt   {{ background: #1c2128 !important; }}
    .g-verde   {{ color: #3fb950; }}
    .g-amarillo {{ color: #e3b341; }}
    .g-rojo    {{ color: #f85149; }}
    code {{
      background: #1f2428;
      color: #79c0ff;
      padding: 2px 7px;
      border-radius: 5px;
      font-size: 0.78rem;
      font-family: 'SFMono-Regular', Consolas, monospace;
    }}
  </style>
</head>
<body>
<div style='max-width:980px; margin:0 auto;'>

  <!-- HEADER -->
  <div class='header-wrap'>
    <h1>Monitor Growth &nbsp;<span>V1.9</span></h1>
    {badges.get(ENTORNO, '')}
  </div>
  <p class='subtitle'>
    Datos anualizados (4T) &nbsp;&bull;&nbsp; Benchmark: {BENCHMARK_NOMBRE} (^NDX)
    &nbsp;&bull;&nbsp; Generado: {fecha_gen}
    &nbsp;&bull;&nbsp; <sup>(*)</sup> dato incompleto
  </p>

  <!-- GRAFICOS -->
  <div class='card-m' style='padding:16px;'>
    <img src='data:image/png;base64,{img_b64}'
         style='width:100%;border-radius:8px;display:block;'>
  </div>

  <!-- BLOQUE 1 -->
  <div class='bloque-sep'>Bloque 1 &mdash; Calidad del Negocio</div>
  <div class='card-m calidad'>
    <div class='card-titulo c1'>Metricas de Calidad</div>
    <p class='card-desc'>
      NRR, dilucion neta y generacion de caja. Mide la salud estructural del negocio
      con independencia del precio al que cotiza. Pasa el cursor sobre SBC NETO para ver valores absolutos.
    </p>
    <table>
      <thead><tr>
        <th>Ticker</th><th>NRR</th><th>SBC Neto / FCF</th>
        <th>FCF Yield</th><th style='text-align:center;'>T-G</th><th>Diagnostico</th>
      </tr></thead>
      <tbody>{filas_calidad}</tbody>
    </table>
  </div>

  <!-- BLOQUE 2 -->
  <div class='bloque-sep'>Bloque 2 &mdash; Valoracion de Mercado</div>
  <div class='card-m valor'>
    <div class='card-titulo c2'>Metricas de Valoracion</div>
    <p class='card-desc'>
      P/FCF y descuentos vs maximos recientes. Una empresa puede ser excelente en el Bloque 1
      y estar cara en el Bloque 2 — la senal final cruza ambas dimensiones.
    </p>
    <table>
      <thead><tr>
        <th>Ticker</th><th>Precio</th><th>P/FCF</th>
        <th>Desc. 52s</th><th>Desc. 3m</th><th>Max 52s</th><th>Senal</th>
      </tr></thead>
      <tbody>{filas_valor}</tbody>
    </table>
  </div>

  <!-- BLOQUE 3 -->
  <div class='bloque-sep'>Bloque 3 &mdash; Rendimiento Relativo vs {BENCHMARK_NOMBRE}</div>
  <div class='card-m relativo'>
    <div class='card-titulo c3'>Rendimiento 12 meses vs Nasdaq 100</div>
    <p class='card-desc'>
      Retorno total de cada ticker en los ultimos 12 meses normalizado a base 100.
      Alfa = diferencia en puntos porcentuales respecto al NDX en el mismo periodo.
    </p>
    <table>
      <thead><tr>
        <th>Ticker</th>
        <th>Retorno 12m</th>
        <th>{BENCHMARK_NOMBRE} 12m</th>
        <th>Alfa vs NDX</th>
        <th>Lectura</th>
      </tr></thead>
      <tbody>{filas_relativo}</tbody>
    </table>
  </div>

  <!-- LOG -->
  <div class='card-m log'>
    <div class='card-titulo' style='color:#6e7681;'>Log de Calidad de Datos</div>
    <table>
      <thead><tr><th>Ticker</th><th>Metrica</th><th>Detalle</th></tr></thead>
      <tbody>{filas_w}</tbody>
    </table>
  </div>

  <!-- GLOSARIO -->
  <div class='card-m glosario'>
    <div class='card-titulo cg'>Glosario V1.9</div>
    <table style='font-size:0.82rem;'>
      <thead><tr>
        <th style='width:175px;'>Metrica</th>
        <th>Definicion</th>
        <th style='width:235px;'>Interpretacion</th>
      </tr></thead>
      {glosario}
    </table>
  </div>

</div>
</body>
</html>"""

    # =========================================================================
    # SALIDA ADAPTADA POR ENTORNO (Fix #22)
    # =========================================================================
    with open(RUTA_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[html] Guardado en {RUTA_HTML}")

    # Telegram — todos los entornos
    if TOKEN and CHAT_ID:
        enviar_telegram(html, TOKEN, CHAT_ID)

    # Colab — mostrar enlace descarga
    if ENTORNO == 'colab':
        mostrar_en_colab(RUTA_HTML)


# =============================================================================
if __name__ == "__main__":
    ejecutar_v1_9()
