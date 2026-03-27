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
# ENTORNO      Google Colab (auditoría) · GitHub Actions (producción)
# VERSIÓN      1.1 · 2026-03-27 · Claude Sonnet 4.6 · Revisado: no revisado
#              Cambios v1.1: paso a producción — DRY_RUN=False, HORAS_LOOKBACK=26
#              Cambios v1.0: script inicial — monitor de condición de entrada
#              COPX basada en precio del cobre HG=F (COMEX $/lb → $/t).
#              TODOs SMART:
#                - H2 (déficit ICSG): actualizar manualmente en junio y
#                  diciembre 2026. Fuente: ICSG Copper Bulletin.
#                  Campo: hitos[id=2].estado
#                - INV-2 (superávit ICSG > 200kt): misma fuente y frecuencia.
#                  Campo: hitos[id=5].estado
# MODO         DRY_RUN=True · HORAS_LOOKBACK=720
#              Regla: auditoría por defecto siempre. Paso a producción requiere
#              OK explícito del humano. Cambiar DRY_RUN=False / HORAS_LOOKBACK=26
#              únicamente tras revisión y confirmación manual.
# DEPENDENCIAS yfinance (auto-install) · requests (auto-install) · pandas ·
#              matplotlib · stdlib: os, io, base64, json, datetime
# =============================================================================

# =============================================================================
# CONFIGURACIÓN — EDITAR AQUÍ
# =============================================================================

# --- Flags de auditoría ---
# Regla: DRY_RUN=True por defecto. Nunca cambiar sin OK explícito del humano.
DRY_RUN        = False  # True=auditoría (Telegram desactivado) | False=producción
HORAS_LOOKBACK = 26     # 720h=auditoría | 26h=producción

# --- Credenciales Telegram (hardcoded hasta orden «versión no refinable») ---
TOKEN   = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID = "8351044609"

# --- Parámetros de tesis ---
# Condición de entrada: cobre HG=F > umbral durante 2 cierres semanales consecutivos
COBRE_UMBRAL_LB    = 5.6699   # $12.500/t ÷ 2204.62 = $5.6699/lb — umbral de entrada
COBRE_UMBRAL_T     = 12500.0  # USD/t — referencia legible en mensajes
COBRE_UMBRAL_INV1  = 4535.0   # $10.000/t — umbral invalidación INV-1
COBRE_DIAS_INV1    = 30       # Días consecutivos bajo umbral para activar INV-1

# --- Parámetros operativos COPX ---
STOP_COPX          = 67.00    # Stop loss — soporte técnico previo al ATH
TP_PARCIAL_MIN     = 88.00    # TP parcial 50% — resistencia previa
TP_PARCIAL_MAX     = 90.00    # TP parcial 50% — resistencia previa
SIZING_PCT_CAPITAL = 1.0      # 1% del capital disponible

# --- Validación cruzada HG=F / COPX ---
# Si HG=F cae > umbral en una sesión pero COPX no cae proporcionalmente,
# el dato se marca como sospechoso (probable rollover) y no activa señales.
ROLLOVER_UMBRAL_PCT = 3.0     # Caída > 3% en HG=F sin correlación en COPX

# --- Rutas ---
CARPETA   = "copx"
RUTA_JSON = os.path.join(CARPETA, "hitos_estado.json")
RUTA_HIST = os.path.join(CARPETA, "hitos_historial.json")
RUTA_HTML = os.path.join(CARPETA, "Monitor_COPX.html")
GITHUB_JSON_URL = (
    "https://raw.githubusercontent.com/JanCasasSala/ControlesFinancieros"
    "/main/copx/hitos_estado.json"
)

# --- IDs de hitos de invalidación ---
IDS_INVALIDACION = {4, 5, 6}

# =============================================================================
# HITOS — CATÁLOGO
#   Hitos manuales (2, 5): ICSG semestral — actualizar en junio y diciembre
#   Hitos automáticos (1, 4, 6): calculados en ejecución vía yfinance
#   Hitos de invalidación (4, 5, 6):
#     None  = vigente (tesis intacta) — correcto por defecto
#     False = INVALIDADO — genera alerta máxima
# =============================================================================
HITOS_DEFAULT = [
    {
        "id": 1,
        "hito": "H1 — Cobre > $12.500/t · 2 cierres semanales consecutivos",
        "detalle": (
            "Condición de entrada: HG=F > $5.6699/lb ($12.500/t) en 2 cierres semanales "
            "consecutivos. Simultáneamente señal de entrada y primera validación de tesis. "
            "Si no se activa en Q2 2026: revisar horizonte temporal. "
            "Seguimiento automático vía yfinance HG=F."
        ),
        "estado": None, "fecha": None, "critico": True, "categoria": "Entrada"
    },
    {
        "id": 2,
        "hito": "H2 — Déficit ICSG 2026 ≥ 300.000 toneladas",
        "detalle": (
            "Verificar en ICSG Copper Bulletin (junio y diciembre 2026): déficit real "
            "≥ 300kt en acumulado del año. Si déficit real < 200kt: reducir posición "
            "al 50% y revisar horizonte. Actualización manual semestral."
        ),
        "estado": None, "fecha": None, "critico": True, "categoria": "Fundamental"
    },
    {
        "id": 3,
        "hito": "H3 — COPX supera retorno cobre LME en ventana 30 días",
        "detalle": (
            "COPX debe superar el retorno de HG=F en ventana móvil de 30 días. "
            "Confirma que el leverage operativo de las mineras funciona. "
            "Si COPX no supera a HG=F durante 60 días: evaluar rotación a CPER "
            "(exposición directa al metal). Seguimiento automático."
        ),
        "estado": None, "fecha": None, "critico": True, "categoria": "Vehículo"
    },
    # --- Hitos de invalidación ---
    # IMPORTANTE: estado=None significa VIGENTE (tesis intacta).
    # Cambiar a False ÚNICAMENTE si el evento negativo se confirma con fuente primaria.
    {
        "id": 4,
        "hito": "INV-1 — Cobre no cae < $10.000/t más de 30 días",
        "detalle": (
            "INVALIDACIÓN si: cobre < $10.000/t ($4.535/lb) durante > 30 días consecutivos. "
            "El déficit estructural no está siendo reflejado en precio. "
            "Revisar posición en 48h. Seguimiento automático vía yfinance HG=F."
        ),
        "estado": None, "fecha": None, "critico": True, "categoria": "Invalidacion"
    },
    {
        "id": 5,
        "hito": "INV-2 — ICSG no publica superávit real > 200kt",
        "detalle": (
            "INVALIDACIÓN si: ICSG Copper Bulletin publica superávit real > 200kt. "
            "La tesis del déficit queda falsificada con dato primario. "
            "Salida en la semana de publicación. Actualización manual semestral."
        ),
        "estado": None, "fecha": None, "critico": True, "categoria": "Invalidacion"
    },
    {
        "id": 6,
        "hito": "INV-3 — COPX no queda 60 días consecutivos por debajo de HG=F",
        "detalle": (
            "INVALIDACIÓN si: COPX no supera el retorno de HG=F durante 60 días "
            "consecutivos. El leverage operativo del ETF no funciona — el vehículo "
            "no es adecuado para capturar la tesis. Evaluar rotación a CPER. "
            "Seguimiento automático."
        ),
        "estado": None, "fecha": None, "critico": True, "categoria": "Invalidacion"
    },
]


# =============================================================================
# HITOS E HISTORIAL
# =============================================================================
def cargar_hitos() -> list:
    """Carga hitos desde archivo local, GitHub o defaults — en ese orden."""
    if os.path.exists(RUTA_JSON):
        with open(RUTA_JSON, "r", encoding="utf-8") as f:
            print("[INFO] Hitos cargados desde archivo local.")
            return json.load(f)["hitos"]
    try:
        resp = requests.get(GITHUB_JSON_URL, timeout=10)
        if resp.status_code == 200:
            print("[INFO] Hitos cargados desde GitHub.")
            return resp.json()["hitos"]
    except Exception as e:
        print("[WARN] No se pudo cargar desde GitHub: " + str(e))
    print("[INFO] Usando hitos por defecto.")
    return HITOS_DEFAULT


def cargar_historial() -> list:
    """Carga historial de cambios."""
    if os.path.exists(RUTA_HIST):
        with open(RUTA_HIST, "r", encoding="utf-8") as f:
            return json.load(f).get("cambios", [])
    return []


def detectar_cambios(hitos: list, historial: list) -> list:
    """Detecta cambios de estado en hitos respecto al historial."""
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
                "es_invalidacion": h["id"] in IDS_INVALIDACION,
            })
    return cambios


def guardar_historial(historial: list, hitos: list, cambios: list, fecha: str) -> None:
    """Persiste historial en disco."""
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
    print("[INFO] Historial guardado. Cambios: " + str(len(cambios)))


# =============================================================================
# HELPERS
# =============================================================================
def get_close(datos: pd.DataFrame, ticker: str) -> pd.Series:
    """Extrae serie de cierres de un DataFrame de yfinance."""
    try:
        return (datos['Close'][ticker]
                if isinstance(datos.columns, pd.MultiIndex)
                else datos['Close'])
    except KeyError:
        raise ValueError("[ERROR] No se pudo obtener Close para " + ticker)


def get_volume(datos: pd.DataFrame, ticker: str) -> pd.Series:
    """Extrae serie de volumen de un DataFrame de yfinance."""
    try:
        return (datos['Volume'][ticker]
                if isinstance(datos.columns, pd.MultiIndex)
                else datos['Volume'])
    except KeyError:
        raise ValueError("[ERROR] No se pudo obtener Volume para " + ticker)


def lb_a_tonelada(precio_lb: float) -> float:
    """Convierte precio USD/lb a USD/t métricas."""
    return round(precio_lb * 2204.62, 0)


def badge(texto: str, color: str) -> str:
    """Badge HTML coloreado."""
    return (
        "<span style='background:" + color + "33;color:" + color + ";"
        "padding:3px 10px;border-radius:8px;font-size:0.8rem;font-weight:bold;'>"
        + texto + "</span>"
    )


def fila_metrica(label: str, valor: str, badge_html: str = "", extra: str = "") -> str:
    """Fila HTML para tabla de métricas."""
    return (
        "<tr>"
        "<td style='color:#888;font-size:0.82rem;text-transform:uppercase;"
        "letter-spacing:0.5px;'>" + label + "</td>"
        "<td style='font-weight:bold;font-size:1rem;'>" + valor + "</td>"
        "<td>" + badge_html + "</td>"
        "<td style='color:#666;font-size:0.78rem;'>" + extra + "</td>"
        "</tr>"
    )


# =============================================================================
# LÓGICA DE CONDICIÓN DE ENTRADA Y HITOS AUTOMÁTICOS
# =============================================================================
def validar_dato_hgf(
    hgf_cambio_pct: float,
    copx_cambio_pct: float
) -> bool:
    """
    Valida que el dato de HG=F no sea un artefacto de rollover.

    Si HG=F cae > ROLLOVER_UMBRAL_PCT pero COPX no cae en proporción similar,
    el dato se considera sospechoso. Retorna False si el dato es sospechoso.
    """
    caida_hgf  = hgf_cambio_pct < -ROLLOVER_UMBRAL_PCT
    copx_ok    = copx_cambio_pct > (hgf_cambio_pct * 0.5)
    if caida_hgf and copx_ok:
        return False  # Sospecha de rollover
    return True


def evaluar_condicion_entrada(
    hgf_w_serie: pd.Series,
    dato_valido: bool
) -> tuple:
    """
    Evalúa la condición de entrada H1.

    Activación: HG=F > $5.6699/lb ($12.500/t) en 2 cierres semanales consecutivos.
    Si el dato de esta semana es sospechoso (rollover), se usa solo el histórico.

    Returns:
        (semanas_sobre_umbral: int, activa: bool, descripcion: str)
    """
    if not dato_valido:
        return 0, False, "Dato HG=F sospechoso esta semana (posible rollover) — sin cambio de estado"

    ultimas = hgf_w_serie.tail(2)
    sobre   = (ultimas > COBRE_UMBRAL_LB)
    semanas = int(sobre.sum())
    precio_actual_t = lb_a_tonelada(float(hgf_w_serie.iloc[-1]))
    precio_anterior_t = lb_a_tonelada(float(hgf_w_serie.iloc[-2])) if len(hgf_w_serie) >= 2 else 0.0

    if semanas == 2:
        return 2, True, (
            "ENTRADA ACTIVADA — 2 cierres semanales > $"
            + str(int(COBRE_UMBRAL_T)) + "/t\n"
            "  Semana -1: $" + str(precio_anterior_t) + "/t\n"
            "  Semana -0: $" + str(precio_actual_t) + "/t"
        )
    elif semanas == 1:
        return 1, False, (
            "SEMANA 1 DE 2 — cobre $" + str(precio_actual_t) + "/t > umbral $"
            + str(int(COBRE_UMBRAL_T)) + "/t\n"
            "  Falta 1 cierre semanal más para confirmar entrada"
        )
    else:
        return 0, False, (
            "Condición inactiva — cobre $" + str(precio_actual_t)
            + "/t · umbral $" + str(int(COBRE_UMBRAL_T)) + "/t"
        )


def evaluar_inv1_automatica(hgf_diario: pd.Series) -> tuple:
    """
    Evalúa INV-1 automáticamente.

    INV-1: cobre < $10.000/t ($4.535/lb) durante > 30 días consecutivos.

    Returns:
        (dias_bajo_umbral: int, invalidada: bool)
    """
    umbral_lb  = COBRE_UMBRAL_INV1 / 2204.62
    bajo       = hgf_diario < umbral_lb
    dias = 0
    for val in reversed(bajo.tolist()):
        if val:
            dias += 1
        else:
            break
    return dias, dias > COBRE_DIAS_INV1


def evaluar_h3_e_inv3(
    copx_serie: pd.Series,
    hgf_serie: pd.Series
) -> tuple:
    """
    Evalúa H3 (leverage operativo) e INV-3 (60 días sin superar metal).

    H3: COPX supera retorno HG=F en ventana 30 días.
    INV-3: COPX no supera HG=F durante 60 días consecutivos.

    Returns:
        (spread_30d: float, h3_ok: bool, dias_sin_superar: int, inv3_activa: bool, desc: str)
    """
    ventana_h3  = 30
    ventana_inv = 60

    if len(copx_serie) < ventana_inv or len(hgf_serie) < ventana_inv:
        return 0.0, False, 0, False, "Datos insuficientes para ventana 60 días"

    # H3 — ventana 30 días
    ret_copx_30 = ((copx_serie.iloc[-1] / copx_serie.iloc[-ventana_h3]) - 1) * 100
    ret_hgf_30  = ((hgf_serie.iloc[-1]  / hgf_serie.iloc[-ventana_h3])  - 1) * 100
    spread_30   = round(ret_copx_30 - ret_hgf_30, 1)
    h3_ok       = spread_30 > 0

    # INV-3 — contar días consecutivos recientes donde COPX no supera HG=F
    copx_ret_diario = copx_serie.pct_change().fillna(0)
    hgf_ret_diario  = hgf_serie.pct_change().fillna(0)
    copx_supera     = copx_ret_diario > hgf_ret_diario

    dias_sin = 0
    for val in reversed(copx_supera.tolist()):
        if not val:
            dias_sin += 1
        else:
            break
    inv3_activa = dias_sin >= ventana_inv

    desc = (
        "H3 — COPX " + ("+" if ret_copx_30 >= 0 else "") + str(round(ret_copx_30, 1)) + "% "
        "vs Cobre " + ("+" if ret_hgf_30 >= 0 else "") + str(round(ret_hgf_30, 1)) + "% "
        "· spread " + ("+" if spread_30 >= 0 else "") + str(spread_30) + "pp (30D) "
        + ("· LEVERAGE OK" if h3_ok else "· LEVERAGE NO CONFIRMADO")
        + " · " + str(dias_sin) + " días sin superar metal"
    )
    return spread_30, h3_ok, dias_sin, inv3_activa, desc


def render_hitos(hitos: list) -> str:
    """Genera filas HTML para tabla de hitos."""
    cat_colors = {
        "Entrada":      "#00d4ff",
        "Fundamental":  "#2ecc71",
        "Vehículo":     "#ff9f43",
        "Invalidacion": "#ff4444",
    }
    filas = ""
    for h in hitos:
        es_inv = h["id"] in IDS_INVALIDACION

        if es_inv:
            if h["estado"] is None:
                icono, color_e, label_e = "OK",  "#2ecc71", "VIGENTE"
            elif h["estado"] is False:
                icono, color_e, label_e = "!!!", "#ff4444", "INVALIDADO"
            else:
                icono, color_e, label_e = "OK",  "#2ecc71", "CONFIRMADO"
        else:
            if h["estado"] is True:
                icono, color_e, label_e = "OK",  "#2ecc71", "CUMPLIDO"
            elif h["estado"] is False:
                icono, color_e, label_e = "X",   "#e74c3c", "PENDIENTE"
            else:
                icono, color_e, label_e = "...", "#3498db", "PENDIENTE"

        inv_tag = (
            "<span style='background:#ff444433;color:#ff4444;"
            "padding:1px 6px;border-radius:4px;font-size:0.7rem;margin-left:6px;'>"
            "INVALIDACION</span>" if es_inv else ""
        )
        cat_color = cat_colors.get(h["categoria"], "#888")
        fecha_str = h.get("fecha") or "-"
        row_bg    = "background:#ff444411;" if (es_inv and h["estado"] is False) else ""

        filas += (
            "<tr style='" + row_bg + "'>"
            "<td style='text-align:center;font-weight:bold;color:" + color_e + ";'>"
            + icono + "</td>"
            "<td><span style='font-weight:bold;color:#e0e0e0;'>" + h["hito"] + "</span>"
            + inv_tag +
            "<br><small style='color:#666;'>" + h["detalle"] + "</small></td>"
            "<td style='text-align:center;'>"
            "<span style='background:" + cat_color + "22;color:" + cat_color + ";"
            "padding:2px 8px;border-radius:6px;font-size:0.75rem;'>"
            + h["categoria"] + "</span></td>"
            "<td style='text-align:center;color:" + color_e + ";font-weight:bold;"
            "font-size:0.8rem;'>" + label_e + "</td>"
            "<td style='color:#555;font-size:0.8rem;text-align:center;'>"
            + fecha_str + "</td>"
            "</tr>"
        )
    return filas


def render_manual() -> str:
    """Genera sección de manual de operación."""
    return """
    <div class='card'>
      <div class='d-flex justify-content-between align-items-center'
           style='cursor:pointer;' onclick="toggleManual()">
        <h5 style='margin:0;'>Manual de Operación</h5>
        <span id='manual-icon' style='color:#00d4ff;font-size:1.4rem;font-weight:bold;'>+</span>
      </div>
      <div id='manual-content' style='display:none;margin-top:18px;'>

        <div style='background:#0d1f2d;border-radius:10px;padding:18px;margin-bottom:14px;'>
          <p style='color:#f39c12;font-weight:bold;margin-bottom:8px;'>
            Condición única de entrada — basada en el metal, no en el ETF</p>
          <p style='color:#aaa;font-size:0.85rem;margin-bottom:10px;'>
            La entrada en COPX se activa cuando el cobre confirma la recuperación, no antes.
            Entrar sin que el metal confirme es apostar por el timing técnico del ETF — no por la tesis.
          </p>
          <table style='width:100%;font-size:0.82rem;color:#aaa;'>
            <tr>
              <td style='padding:4px 12px 4px 0;color:#00d4ff;font-weight:bold;'>SEÑAL</td>
              <td>HG=F (cobre COMEX) &gt; $5.6699/lb ($12.500/t) en 2 cierres semanales consecutivos.</td>
            </tr>
            <tr>
              <td style='padding:4px 12px 4px 0;color:#2ecc71;font-weight:bold;'>ENTRADA</td>
              <td>Comprar COPX al precio de mercado cuando se confirme la segunda semana.</td>
            </tr>
            <tr>
              <td style='padding:4px 12px 4px 0;color:#e74c3c;font-weight:bold;'>STOP</td>
              <td>$67 — soporte técnico previo. Por debajo la estructura del ETF se deteriora.</td>
            </tr>
            <tr>
              <td style='padding:4px 12px 4px 0;color:#f39c12;font-weight:bold;'>TP PARCIAL</td>
              <td>$88–$90 al 50% de la posición. Mover stop al precio de entrada al activarse.</td>
            </tr>
            <tr>
              <td style='padding:4px 12px 4px 0;color:#888;font-weight:bold;'>TRAILING</td>
              <td>EMA20 semanal sobre el 50% restante. Revisión cada cierre de viernes.</td>
            </tr>
          </table>
        </div>

        <div style='background:#0d1f2d;border-radius:10px;padding:18px;margin-bottom:14px;'>
          <p style='color:#00d4ff;font-weight:bold;margin-bottom:8px;'>
            Cómo leer el gráfico adjunto</p>
          <table style='width:100%;font-size:0.82rem;'>
            <tr>
              <td style='padding:3px 12px 3px 0;'>
                <span style='color:#00d4ff;font-weight:bold;'>— COPX (cyan)</span></td>
              <td style='color:#aaa;'>El ETF que seguimos. Base 100 = inicio del periodo.</td>
            </tr>
            <tr>
              <td style='padding:3px 12px 3px 0;'>
                <span style='color:#2ecc71;font-weight:bold;'>— Cobre HG=F (verde)</span></td>
              <td style='color:#aaa;'>El motor de la tesis. COPX debe superar a este en retorno.</td>
            </tr>
            <tr>
              <td style='padding:3px 12px 3px 0;'>
                <span style='color:#ff4d4d;font-weight:bold;'>-- EMA20 (rojo punteado)</span></td>
              <td style='color:#aaa;'>Media móvil de referencia. Trailing stop cuando haya posición.</td>
            </tr>
            <tr>
              <td style='padding:3px 12px 3px 0;'>
                <span style='color:#ff9f43;font-weight:bold;'>— CPER (naranja)</span></td>
              <td style='color:#aaa;'>Benchmark: ETF de exposición directa al metal físico.
                Si COPX consistentemente no supera a CPER, el leverage operativo no funciona
                y habría que rotar a CPER.</td>
            </tr>
          </table>
          <p style='color:#555;font-size:0.8rem;margin-top:10px;'>
            Clave: COPX debe ir por encima de CPER y de HG=F en retorno relativo.
            Si no lo hace, el ETF no está cumpliendo su función de amplificador del metal.
          </p>
        </div>

        <div style='background:#0d1f2d;border-radius:10px;padding:18px;margin-bottom:14px;'>
          <p style='color:#00d4ff;font-weight:bold;margin-bottom:8px;'>
            Alertas Telegram — qué significan</p>
          <table style='width:100%;font-size:0.82rem;'>
            <tr><td style='color:#f39c12;font-weight:bold;padding:3px 12px 3px 0;'>SEMANA 1/2</td>
                <td style='color:#aaa;'>Cobre cruzó $12.500/t. Falta una semana más para confirmar entrada.</td></tr>
            <tr><td style='color:#2ecc71;font-weight:bold;padding:3px 12px 3px 0;'>ENTRADA ACTIVADA</td>
                <td style='color:#aaa;'>2 cierres semanales confirmados. Comprar COPX al precio de apertura del lunes.</td></tr>
            <tr><td style='color:#ff9f43;font-weight:bold;padding:3px 12px 3px 0;'>LEVERAGE DÉBIL</td>
                <td style='color:#aaa;'>COPX no supera al metal en retorno 30D. Vigilar — si persiste 60 días: rotar a CPER.</td></tr>
            <tr><td style='color:#ff4444;font-weight:bold;padding:3px 12px 3px 0;'>INVALIDACIÓN</td>
                <td style='color:#aaa;'>Hito de tesis comprometido. No abrir posición / revisar si está abierta.</td></tr>
          </table>
        </div>

        <div style='background:#0d1f2d;border-radius:10px;padding:18px;'>
          <p style='color:#00d4ff;font-weight:bold;margin-bottom:8px;'>
            Hitos manuales — cómo actualizar</p>
          <ol style='color:#aaa;font-size:0.85rem;padding-left:18px;margin:0;'>
            <li style='margin-bottom:6px;'>ICSG publica Copper Bulletin (junio / diciembre).</li>
            <li style='margin-bottom:6px;'>Abres <code>copx/hitos_estado.json</code>,
              actualizas H2 (id=2) o INV-2 (id=5) con estado y fecha, commit.</li>
            <li style='margin-bottom:6px;'>Ejecutas en Colab o esperas GitHub Actions.</li>
            <li>Si cambias hito 4, 5 o 6 a False — alerta máxima. Revisar posición.</li>
          </ol>
        </div>

      </div>
    </div>
    <script>
      function toggleManual() {
        var c = document.getElementById('manual-content');
        var i = document.getElementById('manual-icon');
        if (c.style.display === 'none') { c.style.display = 'block'; i.textContent = '-'; }
        else { c.style.display = 'none'; i.textContent = '+'; }
      }
    </script>
    """


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================
def monitor_copx_v1():
    """
    Monitor de condición de entrada COPX.
    Vigila: cobre HG=F > $12.500/t en 2 cierres semanales consecutivos.
    Evalúa hitos automáticos (H1, H3, INV-1, INV-3) y manuales (H2, INV-2).
    Genera HTML con gráfico COPX vs HG=F vs CPER + contexto de lectura.
    Notifica por Telegram si DRY_RUN=False.
    """
    try:
        fecha_now = datetime.now().strftime("%d/%m/%Y %H:%M")

        # --- Hitos e historial ---
        hitos     = cargar_hitos()
        historial = cargar_historial()
        cambios   = detectar_cambios(hitos, historial)

        # --- Datos de mercado diarios ---
        print("[INFO] Descargando datos diarios...")
        tickers_d = ["COPX", "HG=F", "CPER"]
        datos_d   = yf.download(tickers_d, period="90d", progress=False, auto_adjust=True)

        copx_d   = get_close(datos_d, "COPX").ffill().bfill()
        hgf_d    = get_close(datos_d, "HG=F").ffill().bfill()
        cper_d   = get_close(datos_d, "CPER").ffill().bfill()
        vol_d    = get_volume(datos_d, "COPX").ffill().bfill()

        copx_act = float(copx_d.iloc[-1])
        hgf_act  = float(hgf_d.iloc[-1])
        cper_act = float(cper_d.iloc[-1])
        vol_hoy  = float(vol_d.iloc[-1])
        vol_med20 = float(vol_d.rolling(window=20).mean().iloc[-1])
        ema20_val = float(copx_d.ewm(span=20).mean().iloc[-1])

        cobre_act_t = lb_a_tonelada(hgf_act)

        # Cambio diario para validación rollover
        hgf_cambio_pct  = float(hgf_d.pct_change().iloc[-1] * 100)
        copx_cambio_pct = float(copx_d.pct_change().iloc[-1] * 100)
        dato_hgf_valido = validar_dato_hgf(hgf_cambio_pct, copx_cambio_pct)

        if not dato_hgf_valido:
            print("[WARN] HG=F: posible dato de rollover detectado — "
                  "HG=F " + str(round(hgf_cambio_pct, 1)) + "% "
                  "vs COPX " + str(round(copx_cambio_pct, 1)) + "%")

        print("[INFO] COPX: $" + str(round(copx_act, 2)))
        print("[INFO] Cobre HG=F: $" + str(round(hgf_act, 4)) + "/lb → $"
              + str(cobre_act_t) + "/t")
        print("[INFO] CPER: $" + str(round(cper_act, 2)))

        # --- Datos semanales para condición de entrada H1 ---
        print("[INFO] Descargando datos semanales...")
        datos_w  = yf.download(["HG=F"], period="180d", interval="1wk",
                                progress=False, auto_adjust=True)
        hgf_w    = get_close(datos_w, "HG=F").ffill().bfill()

        # --- Evaluar condición de entrada H1 ---
        semanas_sobre, entrada_activa, desc_h1 = evaluar_condicion_entrada(
            hgf_w, dato_hgf_valido
        )

        # --- Evaluar hitos automáticos ---
        dias_inv1, inv1_auto           = evaluar_inv1_automatica(hgf_d)
        spread_h3, h3_ok, dias_sin_superar, inv3_auto, desc_h3 = evaluar_h3_e_inv3(
            copx_d, hgf_d
        )

        # Actualizar estados automáticos en hitos
        for h in hitos:
            if h["id"] == 4 and inv1_auto and h["estado"] is None:
                h["estado"] = False
                h["fecha"]  = fecha_now
                print("[WARN] INV-1 activada: cobre < $10.000/t durante "
                      + str(dias_inv1) + " días")
            if h["id"] == 6 and inv3_auto and h["estado"] is None:
                h["estado"] = False
                h["fecha"]  = fecha_now
                print("[WARN] INV-3 activada: COPX sin superar cobre durante "
                      + str(dias_sin_superar) + " días")

        guardar_historial(historial, hitos, cambios, fecha_now)

        invalidaciones_activas    = [c for c in cambios
                                     if c.get("es_invalidacion")
                                     and c["estado_act"] == "pendiente"]
        invalidaciones_historicas = [h for h in hitos
                                     if h["id"] in IDS_INVALIDACION
                                     and h["estado"] is False]

        # --- Estado del monitor ---
        if invalidaciones_historicas:
            estado       = "TESIS COMPROMETIDA — NO ABRIR POSICIÓN"
            estado_color = "#ff4444"
            estado_desc  = "Uno o más hitos de invalidación confirmados."
        elif entrada_activa:
            estado       = "ENTRADA ACTIVADA — COMPRAR COPX"
            estado_color = "#2ecc71"
            estado_desc  = desc_h1
        elif semanas_sobre == 1:
            estado       = "SEMANA 1/2 — VIGILANCIA ACTIVA"
            estado_color = "#f39c12"
            estado_desc  = desc_h1
        elif not h3_ok:
            estado       = "ESPERANDO — LEVERAGE DÉBIL"
            estado_color = "#ff9f43"
            estado_desc  = "Condición inactiva. " + desc_h3
        else:
            estado       = "ESPERANDO — SIN CONDICIÓN ACTIVA"
            estado_color = "#555555"
            estado_desc  = "Condición inactiva. " + desc_h3

        # --- Gráfico ---
        print("[INFO] Generando gráfico...")
        n = 60
        plot_copx = copx_d.tail(n)
        plot_hgf  = hgf_d.tail(n)
        plot_cper = cper_d.tail(n)
        ema20_ser = copx_d.ewm(span=20).mean().tail(n)

        base = plot_copx.iloc[0]
        rel_copx = (plot_copx / base) * 100
        rel_hgf  = (plot_hgf  / float(plot_hgf.iloc[0])) * 100
        rel_cper = (plot_cper / float(plot_cper.iloc[0])) * 100
        rel_ema  = (ema20_ser / base) * 100

        # Umbral de entrada en escala relativa
        umbral_hgf_rel = (COBRE_UMBRAL_LB / float(plot_hgf.iloc[0])) * 100

        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(12, 6), dpi=150)

        ax.plot(rel_copx, label="MI SEGUIMIENTO: COPX",
                color="#00d4ff", linewidth=3.0, zorder=4)
        ax.plot(rel_hgf,  label="MOTOR: Cobre HG=F",
                color="#2ecc71", linewidth=1.5, alpha=0.85)
        ax.plot(rel_ema,  label="EMA20 COPX (trailing ref.)",
                color="#ff4d4d", linestyle="--", linewidth=1.5)
        ax.plot(rel_cper, label="BENCHMARK: CPER (metal directo)",
                color="#ff9f43", linewidth=1.5, alpha=0.85)

        # Línea umbral de entrada cobre
        ax.axhline(umbral_hgf_rel, color="#2ecc71", linestyle=":",
                   linewidth=1.0, alpha=0.5,
                   label="Umbral entrada cobre $12.500/t")

        # Líneas de niveles COPX (stop y TP) en escala relativa
        ax.axhline((STOP_COPX / base) * 100,
                   color="#e74c3c", linestyle=":", linewidth=1.0, alpha=0.5,
                   label="Stop COPX $" + str(STOP_COPX))
        ax.axhline((TP_PARCIAL_MIN / base) * 100,
                   color="#f39c12", linestyle=":", linewidth=1.0, alpha=0.5,
                   label="TP parcial $" + str(TP_PARCIAL_MIN) + "-" + str(TP_PARCIAL_MAX))

        ax.set_title(
            "COPX vs Cobre (HG=F) vs CPER — Últimas 60 sesiones · Base 100",
            color="#00d4ff", fontsize=13, pad=12
        )
        ax.legend(loc="upper left", facecolor="#1e1e1e", fontsize=8)
        ax.grid(alpha=0.08)
        ax.tick_params(colors="#888")
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")

        buf = io.BytesIO()
        plt.savefig(buf, format="png", facecolor="#121212", bbox_inches="tight")
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode()
        plt.close(fig)

        # --- Badges HTML ---
        vol_badge  = badge("ALTO", "#2ecc71") if vol_hoy > vol_med20 else badge("BAJO", "#e74c3c")
        ema_badge  = (badge("ENCIMA EMA20", "#2ecc71") if copx_act >= ema20_val
                      else badge("DEBAJO EMA20", "#3498db"))
        cobre_badge = (badge("SOBRE UMBRAL", "#2ecc71") if hgf_act > COBRE_UMBRAL_LB
                       else badge("BAJO UMBRAL", "#e67e22") if hgf_act > (COBRE_UMBRAL_INV1 / 2204.62)
                       else badge("ZONA RIESGO", "#e74c3c"))
        h3_badge   = (badge("LEVERAGE OK", "#2ecc71") if h3_ok
                      else badge("LEVERAGE DÉBIL", "#ff9f43"))
        rollover_badge = badge("DATO OK", "#2ecc71") if dato_hgf_valido else badge("SOSPECHOSO", "#f39c12")
        entorno    = "Google Colab" if EN_COLAB else "GitHub Actions" if EN_GITHUB else "Local"
        modo_badge = badge("AUDITORÍA", "#f39c12") if DRY_RUN else badge("PRODUCCIÓN", "#2ecc71")

        filas_tg = render_hitos(hitos)

        # --- Banners de alerta ---
        alerta_inv = ""
        if invalidaciones_activas:
            nombres = ", ".join([c["hito"] for c in invalidaciones_activas])
            alerta_inv = (
                "<div style='background:#ff444422;border-left:4px solid #ff4444;"
                "border-radius:8px;padding:14px 20px;margin-bottom:20px;'>"
                "<span style='color:#ff4444;font-size:1.1rem;font-weight:bold;'>"
                "ALERTA MÁXIMA — INVALIDACIÓN DE TESIS</span><br>"
                "<span style='color:#ff9999;font-size:0.88rem;'>" + nombres + "</span><br>"
                "<span style='color:#aaa;font-size:0.82rem;'>"
                "No abrir posición en COPX.</span></div>"
            )
        elif invalidaciones_historicas:
            nombres = ", ".join([h["hito"] for h in invalidaciones_historicas])
            alerta_inv = (
                "<div style='background:#ff444411;border-left:4px solid #ff4444;"
                "border-radius:8px;padding:14px 20px;margin-bottom:20px;'>"
                "<span style='color:#ff4444;font-weight:bold;'>"
                "TESIS COMPROMETIDA</span><br>"
                "<span style='color:#aaa;font-size:0.82rem;'>" + nombres + "</span></div>"
            )

        alerta_entrada = ""
        if not invalidaciones_historicas:
            if entrada_activa:
                alerta_entrada = (
                    "<div style='background:#2ecc7122;border-left:4px solid #2ecc71;"
                    "border-radius:8px;padding:14px 20px;margin-bottom:20px;'>"
                    "<span style='color:#2ecc71;font-size:1.1rem;font-weight:bold;'>"
                    "ENTRADA COPX ACTIVADA</span><br>"
                    "<span style='color:#aaa;font-size:0.85rem;'>" + desc_h1 + "</span><br>"
                    "<span style='color:#2ecc71;font-size:0.85rem;font-weight:bold;'>"
                    "Acción: comprar COPX al precio de apertura del lunes. "
                    "Stop $67 · TP 50% en $88–90 · Sizing 1% capital.</span></div>"
                )
            elif semanas_sobre == 1:
                alerta_entrada = (
                    "<div style='background:#f39c1222;border-left:4px solid #f39c12;"
                    "border-radius:8px;padding:14px 20px;margin-bottom:20px;'>"
                    "<span style='color:#f39c12;font-size:1rem;font-weight:bold;'>"
                    "SEMANA 1 DE 2 — VIGILANCIA ACTIVA</span><br>"
                    "<span style='color:#aaa;font-size:0.85rem;'>" + desc_h1 + "</span><br>"
                    "<span style='color:#f39c12;font-size:0.82rem;'>"
                    "Si el cobre cierra la próxima semana sobre $12.500/t: "
                    "entrada activada.</span></div>"
                )

        # --- Mapa de niveles COPX ---
        niveles_html = ""
        for lbl, precio, accion, c in [
            ("TP parcial 50%", TP_PARCIAL_MIN, "Vender 50% — mover stop a entrada",     "#f39c12"),
            ("EMA20 actual",   ema20_val,      "Trailing stop de referencia",             "#ff4d4d"),
            ("Precio actual",  copx_act,       "COPX hoy",                               "#00d4ff"),
            ("Stop loss",      STOP_COPX,      "Salida si se activa — estructura rota",  "#e74c3c"),
        ]:
            dist   = ("+" if copx_act >= precio else "") + str(round(copx_act - precio, 2))
            dist_c = "#2ecc71" if copx_act >= precio else "#3498db"
            niveles_html += (
                "<tr><td style='color:" + c + ";font-weight:bold;'>" + lbl + "</td>"
                "<td><code>$" + str(round(precio, 2)) + "</code></td>"
                "<td style='color:#aaa;font-size:0.85rem;'>" + accion + "</td>"
                "<td style='color:" + dist_c + ";font-size:0.85rem;'>" + dist + "</td></tr>"
            )

        # --- HTML completo ---
        html = (
            "<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css'"
            " rel='stylesheet'>"
            "<style>"
            "body{background:#121212;color:#e0e0e0;padding:25px;"
            "font-family:'Segoe UI',sans-serif;}"
            ".card{background:#1e1e1e;border-radius:15px;padding:22px;"
            "margin-bottom:20px;border:none;}"
            "h5{color:#00d4ff;text-transform:uppercase;font-size:0.85rem;"
            "letter-spacing:1.5px;margin-bottom:15px;}"
            "th{color:#555;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;"
            "border-bottom:1px solid #2a2a2a !important;}"
            "td{vertical-align:middle !important;border-bottom:1px solid #1a1a1a !important;"
            "padding:11px 8px !important;}"
            "code{background:#2a2a2a;color:#00d4ff;padding:2px 6px;border-radius:4px;"
            "font-size:0.8rem;}"
            ".price{font-size:2.8rem;font-weight:800;color:#00d4ff;line-height:1;}"
            "</style></head><body>"
            "<div class='container' style='max-width:960px;'>"

            # Header
            "<div class='d-flex justify-content-between align-items-center mb-3'>"
            "<div><h2 style='color:#00d4ff;margin:0;'>Monitor COPX — Condición de Entrada</h2>"
            "<small style='color:#555;'>NYSE: COPX · Global X Copper Miners ETF · v1.0 · "
            + entorno + " · " + fecha_now + " · </small>" + modo_badge +
            "</div>"
            "<div style='text-align:right;'>"
            "<div class='price'>$" + str(round(copx_act, 2)) + "</div>"
            "<small style='color:#555;'>Precio actual COPX · sin posición abierta</small>"
            "</div></div>"

            # Estado
            "<div style='background:" + estado_color + "18;border-left:4px solid "
            + estado_color + ";border-radius:8px;padding:14px 18px;margin-bottom:20px;'>"
            "<div style='color:" + estado_color + ";font-size:1rem;font-weight:bold;"
            "margin-bottom:4px;'>" + estado + "</div>"
            "<div style='color:#aaa;font-size:0.82rem;white-space:pre-line;'>"
            + estado_desc + "</div></div>"

            + alerta_inv
            + alerta_entrada +

            # Métricas
            "<div class='card'><h5>Métricas de Mercado</h5>"
            "<table class='table table-dark mb-0'>"
            "<thead><tr><th>Indicador</th><th>Valor</th><th>Estado</th>"
            "<th>Referencia</th></tr></thead><tbody>"
            + fila_metrica("COPX",
                           "$" + str(round(copx_act, 2)),
                           ema_badge,
                           "EMA20: $" + str(round(ema20_val, 2)))
            + fila_metrica("Motor · Cobre HG=F",
                           "$" + str(round(hgf_act, 4)) + "/lb",
                           cobre_badge,
                           "$" + str(cobre_act_t) + "/t · umbral $12.500/t")
            + fila_metrica("Benchmark · CPER",
                           "$" + str(round(cper_act, 2)),
                           h3_badge,
                           "H3: COPX debe superar CPER en retorno")
            + fila_metrica("Volumen COPX",
                           str(int(vol_hoy)),
                           vol_badge,
                           "Media 20D: " + str(int(vol_med20)))
            + fila_metrica("Dato HG=F hoy",
                           str(round(hgf_cambio_pct, 1)) + "%",
                           rollover_badge,
                           "Validación anti-rollover")
            + fila_metrica("INV-1 · Días cobre < $10.000/t",
                           str(dias_inv1) + " días",
                           badge("ACTIVA", "#ff4444") if inv1_auto else badge("OK", "#2ecc71"),
                           "Umbral: " + str(COBRE_DIAS_INV1) + " días consecutivos")
            + "</tbody></table></div>"

            # Condición de entrada
            "<div class='card'><h5>Condición de Entrada</h5>"
            "<table class='table table-dark mb-0'>"
            "<thead><tr><th>Semanas sobre umbral</th><th>Estado</th>"
            "<th>Detalle</th></tr></thead><tbody>"
            "<tr>"
            "<td style='font-size:1.5rem;font-weight:bold;color:"
            + ("#2ecc71" if semanas_sobre == 2 else "#f39c12" if semanas_sobre == 1 else "#555")
            + ";'>" + str(semanas_sobre) + " / 2</td>"
            "<td>" + (badge("ACTIVADA", "#2ecc71") if entrada_activa
                      else badge("SEMANA 1", "#f39c12") if semanas_sobre == 1
                      else badge("INACTIVA", "#555")) + "</td>"
            "<td style='color:#aaa;font-size:0.85rem;white-space:pre-line;'>"
            + desc_h1 + "</td>"
            "</tr></tbody></table>"
            "<p style='color:#555;font-size:0.78rem;margin-top:10px;margin-bottom:0;'>"
            "Fuente: HG=F (futuros cobre COMEX) · conversión $/lb × 2.204,62 = $/t · "
            "Umbral $12.500/t = $5.6699/lb</p></div>"

            # Hitos
            "<div class='card'><h5>Hitos de Tesis</h5>"
            "<p style='color:#666;font-size:0.78rem;margin-bottom:6px;'>"
            "H1, H3, INV-1, INV-3 se calculan automáticamente. "
            "H2 e INV-2 requieren actualización manual (ICSG · junio y diciembre).</p>"
            "<table class='table table-dark mb-0'>"
            "<thead><tr>"
            "<th style='width:40px;text-align:center;'>-</th>"
            "<th>Hito</th>"
            "<th style='width:110px;text-align:center;'>Categoría</th>"
            "<th style='width:130px;text-align:center;'>Estado</th>"
            "<th style='width:100px;text-align:center;'>Fecha</th>"
            "</tr></thead>"
            "<tbody>" + filas_tg + "</tbody></table>"
            "<p style='color:#555;font-size:0.78rem;margin-top:10px;margin-bottom:4px;'>"
            "Hitos automáticos calculados en esta ejecución:</p>"
            "<table class='table table-dark mb-0'><tbody>"
            "<tr><td style='color:#aaa;font-size:0.82rem;'>"
            + badge("H1", "#2ecc71" if entrada_activa else "#f39c12" if semanas_sobre == 1 else "#555")
            + " " + desc_h1 + "</td></tr>"
            "<tr><td style='color:#aaa;font-size:0.82rem;'>"
            + badge("H3", "#2ecc71" if h3_ok else "#ff9f43")
            + " " + desc_h3 + "</td></tr>"
            "</tbody></table></div>"

            # Gráfico
            "<div class='card text-center'><h5>Evolución — Últimas 60 Sesiones · Base 100</h5>"
            "<img src='data:image/png;base64," + img_b64
            + "' class='img-fluid' style='border-radius:10px;'>"
            "<div style='background:#0d1f2d;border-radius:8px;padding:12px 16px;"
            "margin-top:14px;text-align:left;'>"
            "<p style='color:#888;font-size:0.78rem;margin-bottom:6px;font-weight:bold;'>"
            "CÓMO LEER ESTE GRÁFICO</p>"
            "<p style='color:#aaa;font-size:0.78rem;margin:0;line-height:1.6;'>"
            "<span style='color:#00d4ff;font-weight:bold;'>COPX (cyan)</span> "
            "— el ETF que seguimos. "
            "<span style='color:#2ecc71;font-weight:bold;'>HG=F (verde)</span> "
            "— el motor: precio del cobre COMEX. "
            "<span style='color:#ff4d4d;font-weight:bold;'>EMA20 (rojo)</span> "
            "— trailing stop de referencia cuando haya posición. "
            "<span style='color:#ff9f43;font-weight:bold;'>CPER (naranja)</span> "
            "— benchmark de exposición directa al metal físico. "
            "Si COPX va por encima de CPER y de HG=F: el leverage operativo de las mineras "
            "está funcionando y el ETF es el vehículo correcto. "
            "Si COPX queda persistentemente por debajo de CPER: evaluar rotación.</p>"
            "</div></div>"

            # Mapa de niveles
            "<div class='card'><h5>Mapa de Niveles COPX</h5>"
            "<table class='table table-dark mb-0'>"
            "<thead><tr><th>Nivel</th><th>Precio</th><th>Acción</th>"
            "<th>Distancia</th></tr></thead>"
            "<tbody>" + niveles_html + "</tbody></table></div>"

            + render_manual() +
            "</div></body></html>"
        )

        # --- Guardar HTML ---
        os.makedirs(CARPETA, exist_ok=True)
        if EN_COLAB:
            from IPython.display import display, HTML as IPY_HTML
            display(IPY_HTML(html))
            print("[INFO] HTML renderizado en Colab.")
        with open(RUTA_HTML, "w", encoding="utf-8") as f:
            f.write(html)
        print("[INFO] HTML guardado: " + RUTA_HTML)

        # --- Telegram ---
        if not DRY_RUN:
            print("[INFO] Enviando a Telegram...")
            url_tg = "https://api.telegram.org/bot" + TOKEN + "/"

            # Construir cabecera según estado
            if invalidaciones_activas:
                header_tg = (
                    "ALERTA MAXIMA — INVALIDACION DE TESIS COPX\n"
                    "==================================================\n"
                    + "\n".join(["INVALIDADO: " + c["hito"] for c in invalidaciones_activas])
                    + "\n==================================================\n"
                    "NO ABRIR POSICION EN COPX\n"
                    "==================================================\n\n"
                )
            elif entrada_activa:
                header_tg = (
                    "ENTRADA COPX ACTIVADA\n"
                    "==================================================\n"
                    + desc_h1 + "\n"
                    "==================================================\n"
                    "ACCION: comprar COPX al precio de apertura del lunes\n"
                    "Stop: $" + str(STOP_COPX)
                    + " | TP parcial 50%: $" + str(TP_PARCIAL_MIN) + "-" + str(TP_PARCIAL_MAX) + "\n"
                    "Sizing: " + str(SIZING_PCT_CAPITAL) + "% capital\n"
                    "Trailing resto: EMA20 semanal — revisar cada cierre de viernes\n"
                    "==================================================\n\n"
                )
            elif semanas_sobre == 1:
                header_tg = (
                    "SEMANA 1 DE 2 — VIGILANCIA COPX\n"
                    "==================================================\n"
                    + desc_h1 + "\n"
                    "Si el cobre cierra la proxima semana sobre $12.500/t:\n"
                    "ENTRADA ACTIVADA — comprar COPX al lunes siguiente\n"
                    "==================================================\n\n"
                )
            else:
                header_tg = ""

            resumen = (
                header_tg
                + "MONITOR COPX V1.0\n"
                "==================================================\n"
                "COPX:  $" + str(round(copx_act, 2)) + "\n"
                "COBRE: $" + str(round(hgf_act, 4)) + "/lb = $" + str(cobre_act_t) + "/t\n"
                "CPER:  $" + str(round(cper_act, 2)) + " (benchmark metal directo)\n"
                "EMA20: $" + str(round(ema20_val, 2))
                + " (" + ("ENCIMA" if copx_act >= ema20_val else "DEBAJO") + ")\n"
                "VOLUMEN: " + ("ALTO" if vol_hoy > vol_med20 else "BAJO") + "\n"
                "==================================================\n"
                "CONDICION H1: " + str(semanas_sobre) + "/2 semanas sobre $12.500/t\n"
                + desc_h1 + "\n\n"
                "H3 LEVERAGE: " + ("OK" if h3_ok else "DEBIL") + "\n"
                + desc_h3 + "\n"
                "==================================================\n"
                "HITOS:\n"
                + "\n".join([
                    ("VIGENTE " if (h["id"] in IDS_INVALIDACION and h["estado"] is None)
                     else "INVALID " if (h["id"] in IDS_INVALIDACION and h["estado"] is False)
                     else "OK      " if h["estado"] is True
                     else "...     ")
                    + ("INV " if h["id"] in IDS_INVALIDACION else "    ")
                    + h["hito"]
                    for h in hitos
                ])
                + "\n==================================================\n"
                "GRAFICO ADJUNTO: COPX (cyan) vs Cobre HG=F (verde) vs CPER (naranja)\n"
                "COPER debe superar a CPER y a HG=F en retorno para confirmar leverage.\n"
                "EMA20 (rojo) = trailing stop de referencia cuando haya posicion."
            )

            try:
                requests.post(
                    url_tg + "sendMessage",
                    data={"chat_id": CHAT_ID, "text": resumen},
                    timeout=15
                )
                with open(RUTA_HTML, "rb") as f:
                    requests.post(
                        url_tg + "sendDocument",
                        data={"chat_id": CHAT_ID,
                              "caption": "Monitor COPX V1.0 — " + fecha_now},
                        files={"document": (RUTA_HTML, f, "text/html")},
                        timeout=15
                    )
                print("[OK] Enviado a Telegram.")
            except Exception as e:
                print("[WARN] Fallo Telegram: " + str(e) + " — continuando sin error fatal.")
        else:
            print("[INFO] DRY_RUN=True — Telegram desactivado.")
            print("[INFO] Resumen que se enviaría:\n" + "=" * 50)
            print("ESTADO: " + estado)
            print("H1: " + str(semanas_sobre) + "/2 — " + desc_h1)
            print("H3: " + desc_h3)
            print("INV-1: " + str(dias_inv1) + " días · " + ("ACTIVA" if inv1_auto else "OK"))
            print("=" * 50)

        return html

    except Exception as e:
        msg = "[FATAL] Monitor COPX V1.0: " + str(type(e).__name__) + " — " + str(e)
        print(msg)
        if not DRY_RUN:
            try:
                requests.post(
                    "https://api.telegram.org/bot" + TOKEN + "/sendMessage",
                    data={"chat_id": CHAT_ID, "text": msg},
                    timeout=15
                )
            except Exception:
                pass
        return None


# =============================================================================
# EJECUCIÓN
# =============================================================================
resultado = monitor_copx_v1()
