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
#                            auto_adjust=True en yf.download (FutureWarning resuelto)
#              Cambios v1.0: script inicial — vigilancia de condiciones de
#              entrada para AEM (sin posición abierta) y hitos de tesis.
#              TODOs SMART:
#                - H1 (earnings 30-abr-2026): actualizar manualmente estado
#                  tras SEC Form 6-K. EPS >= $2.50 Y AISC <= $1.100/oz.
#                - INV-2 (AISC > $1.300 dos trimestres): actualizar tras
#                  cada 6-K trimestral. Fuente: SEC EDGAR.
#                - INV-3 (evento jurisdicción): monitorización manual.
# MODO         DRY_RUN=True · HORAS_LOOKBACK=720
#              Regla: auditoría por defecto siempre. Paso a producción
#              requiere OK explícito del humano. Cambiar DRY_RUN=False y
#              HORAS_LOOKBACK=26 únicamente tras revisión y confirmación.
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

# --- Condición A — entrada por soporte (PREFERIDA · R/R 5.25:1) ---
ZONA_A_MIN       = 174.00   # Límite inferior zona entrada A
ZONA_A_MAX       = 178.00   # Límite superior zona entrada A
STOP_A           = 168.00   # Stop loss condición A
TP_PARCIAL_A     = 218.00   # TP parcial 50% condición A (punto medio $216-$220)
ATR_REFERENCIA   = 11.00    # ATR(14) diario · fuente: tesis 27-mar-2026
                             # Actualizar si cambia materialmente

# --- Condición B — entrada por ruptura ---
NIVEL_RUPTURA_B  = 200.77   # Cierre semanal requerido para activar condición B
ZONA_B_MIN       = 201.00   # Límite inferior zona entrada B
ZONA_B_MAX       = 205.00   # Límite superior zona entrada B
STOP_B           = 174.00   # Stop loss condición B

# --- Parámetros de tesis ---
ORO_UMBRAL_H2    = 4800.00  # H2: oro > $4.800 en 2 cierres semanales consecutivos
ORO_UMBRAL_INV1  = 3500.00  # INV-1: oro < $3.500 más de 30 días consecutivos
VENTAJA_AEM_GDX  = 5.0      # H3: AEM supera GDX en > 5pp · ventana 30 días
ORO_DIAS_INV1    = 30       # Días consecutivos bajo umbral para activar INV-1

# --- Rutas ---
CARPETA   = "aem"
RUTA_JSON = os.path.join(CARPETA, "hitos_estado.json")
RUTA_HIST = os.path.join(CARPETA, "hitos_historial.json")
RUTA_HTML = os.path.join(CARPETA, "Monitor_AEM.html")
GITHUB_JSON_URL = (
    "https://raw.githubusercontent.com/JanCasasSala/ControlesFinancieros"
    "/main/aem/hitos_estado.json"
)

# --- IDs de hitos de invalidación ---
IDS_INVALIDACION = {4, 5, 6}

# =============================================================================
# HITOS — CATÁLOGO
#   Hitos manuales (1, 5, 6): estado actualizado a mano en hitos_estado.json
#   Hitos automáticos (4): calculados en ejecución vía yfinance
#   Hitos de invalidación (4, 5, 6):
#     None  = vigente (tesis intacta) — correcto por defecto
#     False = INVALIDADO — genera alerta máxima
# =============================================================================
HITOS_DEFAULT = [
    {
        "id": 1,
        "hito": "H1 — Earnings Q1 2026 · EPS y AISC",
        "detalle": (
            "Verificar en SEC Form 6-K (30-abr-2026): EPS >= $2.50 Y AISC <= $1.100/oz. "
            "Si AISC > $1.150/oz por primera vez en tres años: revisar posición en 48h. "
            "Actualización manual tras publicación."
        ),
        "estado": None, "fecha": None, "critico": True, "categoria": "Financiero"
    },
    {
        "id": 4,
        "hito": "INV-1 — Oro no cae < $3.500/oz más de 30 días",
        "detalle": (
            "INVALIDACIÓN si: oro spot < $3.500/oz durante > 30 días consecutivos. "
            "A ese nivel margen AEM cae a ~$2.430/oz. "
            "Seguimiento automático vía yfinance GC=F."
        ),
        "estado": None, "fecha": None, "critico": True, "categoria": "Invalidacion"
    },
    {
        "id": 5,
        "hito": "INV-2 — AISC no supera $1.300/oz en dos trimestres consecutivos",
        "detalle": (
            "INVALIDACIÓN si: AISC > $1.300/oz en dos 6-K consecutivos. "
            "Rompe historial de ejecución de tres años. "
            "Si se activa: salir en 48h. Actualización manual tras cada 6-K."
        ),
        "estado": None, "fecha": None, "critico": True, "categoria": "Invalidacion"
    },
    {
        "id": 6,
        "hito": "INV-3 — Sin evento operativo jurisdicción Tier-1 > 10% producción",
        "detalle": (
            "INVALIDACIÓN si: huelga, accidente o cierre en mina canadiense, australiana "
            "o finlandesa con impacto > 10% producción anual. "
            "Elimina ventaja de jurisdicción sobre GDX. Monitorización manual."
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
    """Detecta cambios de estado en hitos manuales respecto al historial."""
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
    print("[INFO] Historial guardado. Cambios detectados: " + str(len(cambios)))


# =============================================================================
# HELPERS HTML
# =============================================================================
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
# LÓGICA DE CONDICIONES DE ENTRADA
# =============================================================================
def evaluar_condicion_a(
    aem_act: float,
    aem_open: float,
    aem_low: float,
    vol_hoy: float,
    vol_med20: float
) -> tuple:
    """
    Evalúa Condición A en dos niveles.

    Nivel 1: precio en zona $174-$178.
    Nivel 2: zona + volumen > media 20D + cierre > apertura + mecha inferior > 1x ATR.
    El nivel 2 no es señal de entrada — es alerta de «mirar ahora».

    Returns:
        (nivel: int, descripcion: str)  nivel = 0 | 1 | 2
    """
    en_zona    = ZONA_A_MIN <= aem_act <= ZONA_A_MAX
    vol_fuerte = vol_hoy > vol_med20
    vela_alza  = aem_act > aem_open
    mecha_inf  = (min(aem_open, aem_act) - aem_low) > ATR_REFERENCIA

    if en_zona and vol_fuerte and vela_alza and mecha_inf:
        return 2, "SEÑAL A — zona + volumen + vela de reversión · REVISAR AHORA"
    elif en_zona:
        return 1, "ZONA A ACTIVA — precio en $174-$178 · verificar vela y volumen"
    else:
        return 0, "Condición A inactiva"


def evaluar_condicion_b(
    aem_cierre_semanal: float,
    vol_semanal: float,
    vol_med20_semanal: float
) -> tuple:
    """
    Evalúa Condición B.

    Activación: cierre semanal > $200.77 con volumen > media 20 sesiones.

    Returns:
        (activa: bool, descripcion: str)
    """
    ruptura    = aem_cierre_semanal > NIVEL_RUPTURA_B
    vol_fuerte = vol_semanal > vol_med20_semanal

    if ruptura and vol_fuerte:
        return True, (
            "CONDICIÓN B ACTIVADA — cierre semanal $"
            + str(round(aem_cierre_semanal, 2))
            + " > $200.77 con volumen"
        )
    elif ruptura:
        return False, "Ruptura sin volumen — cierre > $200.77 pero volumen insuficiente"
    else:
        return False, "Condición B inactiva"


def evaluar_inv1_automatica(oro_serie: pd.Series, fecha_now: str) -> tuple:
    """
    Evalúa INV-1 automáticamente.

    INV-1 se activa si oro < $3.500 durante > 30 días consecutivos.

    Returns:
        (dias_bajo_umbral: int, invalidada: bool)
    """
    bajo_umbral = oro_serie < ORO_UMBRAL_INV1
    # Contar días consecutivos recientes bajo umbral
    dias = 0
    for val in reversed(bajo_umbral.tolist()):
        if val:
            dias += 1
        else:
            break
    return dias, dias > ORO_DIAS_INV1


def evaluar_h2_automatico(oro_serie_semanal: pd.Series) -> tuple:
    """
    Evalúa H2 automáticamente.

    H2 se activa si oro > $4.800 en 2 cierres semanales consecutivos.

    Returns:
        (activo: bool, descripcion: str)
    """
    ultimos = oro_serie_semanal.tail(2)
    if len(ultimos) < 2:
        return False, "H2 — datos insuficientes"
    ambos_sobre = (ultimos > ORO_UMBRAL_H2).all()
    oro_actual  = float(oro_serie_semanal.iloc[-1])
    if ambos_sobre:
        return True, (
            "H2 ACTIVO — oro > $4.800 en 2 cierres semanales consecutivos · $"
            + str(round(oro_actual, 0))
        )
    else:
        return False, (
            "H2 inactivo — oro $" + str(round(oro_actual, 0))
            + " · umbral $" + str(int(ORO_UMBRAL_H2))
        )


def evaluar_h3_automatico(aem_serie: pd.Series, gdx_serie: pd.Series) -> tuple:
    """
    Evalúa H3 automáticamente.

    H3: retorno AEM supera a GDX en > 5pp en ventana móvil de 30 días.

    Returns:
        (spread_pp: float, confirmado: bool, descripcion: str)
    """
    ventana = 30
    if len(aem_serie) < ventana or len(gdx_serie) < ventana:
        return 0.0, False, "H3 — datos insuficientes para ventana 30 días"

    ret_aem = ((aem_serie.iloc[-1] / aem_serie.iloc[-ventana]) - 1) * 100
    ret_gdx = ((gdx_serie.iloc[-1] / gdx_serie.iloc[-ventana]) - 1) * 100
    spread  = ret_aem - ret_gdx
    confirmado = spread > VENTAJA_AEM_GDX

    desc = (
        "H3 — AEM " + ("+" if ret_aem >= 0 else "") + str(round(ret_aem, 1)) + "% "
        "vs GDX " + ("+" if ret_gdx >= 0 else "") + str(round(ret_gdx, 1)) + "% "
        "· spread " + ("+" if spread >= 0 else "") + str(round(spread, 1)) + "pp "
        + ("· CONFIRMADO" if confirmado else "· por debajo umbral +5pp")
    )
    return round(spread, 1), confirmado, desc


def render_hitos(hitos: list) -> str:
    """Genera filas HTML para tabla de hitos."""
    cat_colors = {
        "Financiero":   "#2ecc71",
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
            "<td style='color:#555;font-size:0.8rem;text-align:center;'>" + fecha_str + "</td>"
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
          <p style='color:#f39c12;font-weight:bold;margin-bottom:8px;'>Sin posición abierta — esperando señal</p>
          <p style='color:#aaa;font-size:0.85rem;margin-bottom:8px;'>
            El script vigila dos condiciones de entrada. No se entra entre $178 y $200.77 sin señal técnica clara.
          </p>
          <table style='width:100%;font-size:0.82rem;color:#aaa;'>
            <tr>
              <td style='padding:6px 12px 6px 0;color:#2ecc71;font-weight:bold;vertical-align:top;'>COND. A ⭐</td>
              <td>Precio en $174-$178 + vela de reversión + volumen > media 20D.<br>
                  Stop $168 · TP parcial 50% en $216-$220 · Trailing EMA20 semanal.</td>
            </tr>
            <tr>
              <td style='padding:6px 12px 6px 0;color:#3498db;font-weight:bold;vertical-align:top;'>COND. B</td>
              <td>Cierre semanal > $200.77 con volumen confirmado.<br>
                  Stop $174 · Sin TP parcial · Trailing EMA20 semanal.</td>
            </tr>
          </table>
        </div>

        <div style='background:#0d1f2d;border-radius:10px;padding:18px;margin-bottom:14px;'>
          <p style='color:#00d4ff;font-weight:bold;margin-bottom:8px;'>Alertas Telegram — qué significan</p>
          <table style='width:100%;font-size:0.82rem;'>
            <tr><td style='color:#f39c12;font-weight:bold;padding:3px 12px 3px 0;'>ZONA A ACTIVA</td>
                <td style='color:#aaa;'>Precio entró en $174-$178. Abrir broker y revisar vela y volumen.</td></tr>
            <tr><td style='color:#2ecc71;font-weight:bold;padding:3px 12px 3px 0;'>SEÑAL A</td>
                <td style='color:#aaa;'>Zona + volumen + vela detectados. Revisar para posible entrada.</td></tr>
            <tr><td style='color:#3498db;font-weight:bold;padding:3px 12px 3px 0;'>CONDICIÓN B</td>
                <td style='color:#aaa;'>Cierre semanal > $200.77 con volumen. Evaluar entrada $201-$205.</td></tr>
            <tr><td style='color:#ff4444;font-weight:bold;padding:3px 12px 3px 0;'>INVALIDACIÓN</td>
                <td style='color:#aaa;'>Hito de tesis invalidado. No abrir posición.</td></tr>
          </table>
        </div>

        <div style='background:#0d1f2d;border-radius:10px;padding:18px;margin-bottom:14px;'>
          <p style='color:#00d4ff;font-weight:bold;margin-bottom:8px;'>Hitos manuales — cómo actualizar</p>
          <ol style='color:#aaa;font-size:0.85rem;padding-left:18px;margin:0;'>
            <li style='margin-bottom:6px;'>Recibes el 6-K de AEM o una noticia material.</li>
            <li style='margin-bottom:6px;'>Abres <code>aem/hitos_estado.json</code>, cambias estado y fecha, commit.</li>
            <li style='margin-bottom:6px;'>Ejecutas en Colab o esperas GitHub Actions.</li>
            <li>Si el cambio es hito 4, 5 o 6 a False — alerta máxima. No abrir posición.</li>
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
def monitor_aem_v1():
    """
    Monitor de condiciones de entrada AEM.
    Vigila Condición A (soporte $174-$178) y Condición B (ruptura $200.77).
    Evalúa hitos de tesis automáticos y manuales.
    Genera HTML de seguimiento y notifica por Telegram si DRY_RUN=False.
    """
    try:
        fecha_now = datetime.now().strftime("%d/%m/%Y %H:%M")

        # --- Hitos e historial ---
        hitos     = cargar_hitos()
        historial = cargar_historial()
        cambios   = detectar_cambios(hitos, historial)
        guardar_historial(historial, hitos, cambios, fecha_now)

        invalidaciones_activas = [
            c for c in cambios
            if c.get("es_invalidacion") and c["estado_act"] == "pendiente"
        ]
        invalidaciones_historicas = [
            h for h in hitos
            if h["id"] in IDS_INVALIDACION and h["estado"] is False
        ]

        # --- Datos de mercado ---
        print("[INFO] Descargando datos de mercado...")
        tickers = ["AEM", "GC=F", "GDX"]
        datos   = yf.download(tickers, period="90d", progress=False, auto_adjust=True)

        aem_serie  = get_close(datos, "AEM").ffill().bfill()
        oro_serie  = get_close(datos, "GC=F").ffill().bfill()
        gdx_serie  = get_close(datos, "GDX").ffill().bfill()
        vol_serie  = get_volume(datos, "AEM").ffill().bfill()
        open_serie = get_open(datos, "AEM").ffill().bfill()
        low_serie  = get_low(datos, "AEM").ffill().bfill()

        aem_act    = float(aem_serie.iloc[-1])
        oro_act    = float(oro_serie.iloc[-1])
        gdx_act    = float(gdx_serie.iloc[-1])
        vol_hoy    = float(vol_serie.iloc[-1])
        vol_med20  = float(vol_serie.rolling(window=20).mean().iloc[-1])
        aem_open   = float(open_serie.iloc[-1])
        aem_low    = float(low_serie.iloc[-1])
        sma20_val  = float(aem_serie.rolling(window=20).mean().iloc[-1])
        vol_fuerte = vol_hoy > vol_med20

        print("[INFO] AEM: $" + str(round(aem_act, 2)))
        print("[INFO] Oro: $" + str(round(oro_act, 0)))
        print("[INFO] GDX: $" + str(round(gdx_act, 2)))

        # --- Datos semanales para Condición B y H2 ---
        datos_w        = yf.download(["AEM", "GC=F"], period="180d", interval="1wk", progress=False, auto_adjust=True)
        aem_w_serie    = get_close(datos_w, "AEM").ffill().bfill()
        oro_w_serie    = get_close(datos_w, "GC=F").ffill().bfill()
        vol_w_serie    = get_volume(datos_w, "AEM").ffill().bfill()
        aem_w_act      = float(aem_w_serie.iloc[-1])
        vol_w_hoy      = float(vol_w_serie.iloc[-1])
        vol_w_med20    = float(vol_w_serie.rolling(window=20).mean().iloc[-1])

        # --- Evaluar condiciones de entrada ---
        nivel_a, desc_a = evaluar_condicion_a(
            aem_act, aem_open, aem_low, vol_hoy, vol_med20
        )
        cond_b_activa, desc_b = evaluar_condicion_b(
            aem_w_act, vol_w_hoy, vol_w_med20
        )

        # --- Evaluar hitos automáticos ---
        dias_inv1, inv1_auto = evaluar_inv1_automatica(oro_serie, fecha_now)
        h2_activo, desc_h2   = evaluar_h2_automatico(oro_w_serie)
        spread_h3, h3_ok, desc_h3 = evaluar_h3_automatico(aem_serie, gdx_serie)

        # Actualizar estado INV-1 en hitos si se activa automáticamente
        for h in hitos:
            if h["id"] == 4 and inv1_auto and h["estado"] is None:
                h["estado"] = False
                h["fecha"]  = fecha_now
                print("[WARN] INV-1 activada automáticamente: oro < $3.500 durante "
                      + str(dias_inv1) + " días.")

        # --- Zona muerta: precio entre $178 y $200.77 ---
        en_zona_muerta = ZONA_A_MAX < aem_act < NIVEL_RUPTURA_B

        # --- Estado del monitor ---
        if invalidaciones_historicas:
            estado       = "TESIS COMPROMETIDA — NO ABRIR POSICIÓN"
            estado_color = "#ff4444"
            estado_desc  = "Uno o más hitos de invalidación confirmados."
        elif cond_b_activa:
            estado       = "CONDICIÓN B ACTIVADA — EVALUAR ENTRADA $201-$205"
            estado_color = "#3498db"
            estado_desc  = desc_b
        elif nivel_a == 2:
            estado       = "SEÑAL A — REVISAR AHORA"
            estado_color = "#2ecc71"
            estado_desc  = desc_a
        elif nivel_a == 1:
            estado       = "ZONA A ACTIVA — VIGILANCIA"
            estado_color = "#f39c12"
            estado_desc  = desc_a
        elif en_zona_muerta:
            estado       = "ZONA MUERTA — SIN ACCIÓN"
            estado_color = "#888888"
            estado_desc  = "Precio entre $178 y $200.77 sin señal. No se entra."
        else:
            estado       = "ESPERANDO — SIN CONDICIÓN ACTIVA"
            estado_color = "#555555"
            estado_desc  = "Ninguna condición de entrada activa. Seguimiento pasivo."

        # --- Gráfico ---
        print("[INFO] Generando gráfico...")
        plot_data         = aem_serie.tail(30).to_frame(name="AEM")
        plot_data["GDX"]  = gdx_serie.tail(30).values
        plot_data["ORO"]  = oro_serie.tail(30).values
        relativa          = (plot_data / plot_data.iloc[0]) * 100
        sma20_rel         = (aem_serie.rolling(window=20).mean().tail(30) /
                             float(aem_serie.tail(30).iloc[0])) * 100

        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
        ax.plot(relativa["AEM"], label="MI SEGUIMIENTO: AEM",
                color="#00d4ff", linewidth=3.0, zorder=4)
        ax.plot(sma20_rel,       label="SOPORTE: SMA20",
                color="#ff4d4d",  linestyle="--", linewidth=1.8)
        ax.plot(relativa["GDX"], label="BENCHMARK: GDX",
                color="#ff9f43",  linewidth=1.5, alpha=0.7)
        ax.plot(relativa["ORO"], label="MOTOR: Oro spot (GC=F)",
                color="#2ecc71",  linewidth=1.5, alpha=0.7)

        # Marcar zona de entrada A
        base_val = float(aem_serie.tail(30).iloc[0])
        ax.axhspan(
            (ZONA_A_MIN / base_val) * 100,
            (ZONA_A_MAX / base_val) * 100,
            alpha=0.08, color="#2ecc71", label="Zona entrada A"
        )
        ax.axhline(
            (NIVEL_RUPTURA_B / base_val) * 100,
            color="#3498db", linestyle=":", linewidth=1.2, alpha=0.6,
            label="Nivel ruptura B $200.77"
        )

        ax.set_title("Fuerza Relativa AEM vs GDX vs Oro — Últimas 30 sesiones",
                     color="#00d4ff", fontsize=13, pad=12)
        ax.legend(loc="upper left", facecolor="#1e1e1e", fontsize=9)
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
        vol_badge  = badge("ALTO", "#2ecc71")  if vol_fuerte   else badge("BAJO",  "#e74c3c")
        sma_badge  = (badge("ENCIMA SMA20", "#2ecc71") if aem_act >= sma20_val
                      else badge("DEBAJO SMA20", "#3498db"))
        oro_badge  = (badge("FUERTE", "#2ecc71") if oro_act > ORO_UMBRAL_H2
                      else badge("CORRECCIÓN", "#e67e22") if oro_act > ORO_UMBRAL_INV1
                      else badge("ZONA RIESGO", "#e74c3c"))
        h3_badge   = badge("+"+str(spread_h3)+"pp", "#2ecc71") if h3_ok else badge(str(spread_h3)+"pp", "#e74c3c")
        entorno    = "Google Colab" if EN_COLAB else "GitHub Actions" if EN_GITHUB else "Local"
        modo_badge = badge("AUDITORÍA", "#f39c12") if DRY_RUN else badge("PRODUCCIÓN", "#2ecc71")

        # --- Banners de alerta ---
        alerta_invalidacion = ""
        if invalidaciones_activas:
            nombres = ", ".join([c["hito"] for c in invalidaciones_activas])
            alerta_invalidacion = (
                "<div style='background:#ff444422;border-left:4px solid #ff4444;"
                "border-radius:8px;padding:14px 20px;margin-bottom:20px;'>"
                "<span style='color:#ff4444;font-size:1.1rem;font-weight:bold;'>"
                "ALERTA MÁXIMA — INVALIDACIÓN DE TESIS</span><br>"
                "<span style='color:#ff9999;font-size:0.88rem;'>" + nombres + "</span><br>"
                "<span style='color:#aaa;font-size:0.82rem;'>"
                "No abrir posición en AEM.</span></div>"
            )
        elif invalidaciones_historicas:
            nombres = ", ".join([h["hito"] for h in invalidaciones_historicas])
            alerta_invalidacion = (
                "<div style='background:#ff444411;border-left:4px solid #ff4444;"
                "border-radius:8px;padding:14px 20px;margin-bottom:20px;'>"
                "<span style='color:#ff4444;font-weight:bold;'>"
                "TESIS COMPROMETIDA</span><br>"
                "<span style='color:#aaa;font-size:0.82rem;'>" + nombres + "</span></div>"
            )

        alerta_condicion = ""
        if not invalidaciones_historicas:
            if nivel_a == 2:
                alerta_condicion = (
                    "<div style='background:#2ecc7122;border-left:4px solid #2ecc71;"
                    "border-radius:8px;padding:14px 20px;margin-bottom:20px;'>"
                    "<span style='color:#2ecc71;font-size:1.1rem;font-weight:bold;'>"
                    "SEÑAL A DETECTADA — REVISAR AHORA</span><br>"
                    "<span style='color:#aaa;font-size:0.85rem;'>"
                    "Zona + volumen + vela de reversión. Abrir broker y confirmar entrada.</span></div>"
                )
            elif nivel_a == 1:
                alerta_condicion = (
                    "<div style='background:#f39c1222;border-left:4px solid #f39c12;"
                    "border-radius:8px;padding:14px 20px;margin-bottom:20px;'>"
                    "<span style='color:#f39c12;font-size:1rem;font-weight:bold;'>"
                    "ZONA A ACTIVA — VIGILANCIA</span><br>"
                    "<span style='color:#aaa;font-size:0.85rem;'>"
                    "Precio en $174-$178. Verificar vela de reversión y volumen.</span></div>"
                )
            elif cond_b_activa:
                alerta_condicion = (
                    "<div style='background:#3498db22;border-left:4px solid #3498db;"
                    "border-radius:8px;padding:14px 20px;margin-bottom:20px;'>"
                    "<span style='color:#3498db;font-size:1rem;font-weight:bold;'>"
                    "CONDICIÓN B ACTIVADA</span><br>"
                    "<span style='color:#aaa;font-size:0.85rem;'>" + desc_b + "</span></div>"
                )

        # --- Mapa de niveles ---
        niveles_html = ""
        for lbl, precio, accion, c in [
            ("Ruptura B",     NIVEL_RUPTURA_B, "Cierre semanal con volumen — evaluar entrada $201-$205", "#3498db"),
            ("Zona A máx.",   ZONA_A_MAX,      "Límite superior zona entrada A",                         "#2ecc71"),
            ("Zona A mín.",   ZONA_A_MIN,      "Límite inferior zona entrada A · stop $168",              "#2ecc71"),
            ("Stop A",        STOP_A,          "Stop loss condición A",                                   "#e74c3c"),
            ("Stop B",        STOP_B,          "Stop loss condición B",                                   "#e74c3c"),
            ("TP parcial A",  TP_PARCIAL_A,    "Take profit parcial 50% condición A",                    "#f39c12"),
        ]:
            activo     = abs(aem_act - precio) < ATR_REFERENCIA
            dist_val   = ("+" if aem_act >= precio else "") + str(round(aem_act - precio, 2))
            dist_color = "#2ecc71" if aem_act >= precio else "#3498db"
            row_bg     = "background:#ffffff08;" if activo else ""
            niveles_html += (
                "<tr style='" + row_bg + "'>"
                "<td style='color:" + c + ";font-weight:bold;'>" + lbl + "</td>"
                "<td><code>$" + str(precio) + "</code></td>"
                "<td style='color:#aaa;font-size:0.85rem;'>" + accion + "</td>"
                "<td style='color:" + dist_color + ";font-size:0.85rem;'>" + dist_val + "</td>"
                "</tr>"
            )

        # --- Filas hitos ---
        filas_tg = render_hitos(hitos)

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
            "h5{color:#f39c12;text-transform:uppercase;font-size:0.85rem;"
            "letter-spacing:1.5px;margin-bottom:15px;}"
            "th{color:#555;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;"
            "border-bottom:1px solid #2a2a2a !important;}"
            "td{vertical-align:middle !important;border-bottom:1px solid #1a1a1a !important;"
            "padding:11px 8px !important;}"
            "code{background:#2a2a2a;color:#f39c12;padding:2px 6px;border-radius:4px;"
            "font-size:0.8rem;}"
            ".price{font-size:2.8rem;font-weight:800;color:#f39c12;line-height:1;}"
            ".estado-box{background:" + estado_color + "18;border-left:4px solid "
            + estado_color + ";border-radius:8px;padding:14px 18px;}"
            "</style></head><body>"
            "<div class='container' style='max-width:960px;'>"

            # Header
            "<div class='d-flex justify-content-between align-items-center mb-3'>"
            "<div><h2 style='color:#f39c12;margin:0;'>Monitor AEM — Condiciones de Entrada</h2>"
            "<small style='color:#555;'>NYSE: AEM · v1.0 · "
            + entorno + " · " + fecha_now + " · " + "</small>"
            + modo_badge +
            "</div>"
            "<div style='text-align:right;'>"
            "<div class='price'>$" + str(round(aem_act, 2)) + "</div>"
            "<small style='color:#555;'>Precio actual · sin posición abierta</small>"
            "</div></div>"

            # Badge estado
            "<div style='background:" + estado_color + "18;border-left:4px solid "
            + estado_color + ";border-radius:8px;padding:14px 18px;margin-bottom:20px;'>"
            "<div style='color:" + estado_color + ";font-size:1rem;font-weight:bold;"
            "margin-bottom:4px;'>" + estado + "</div>"
            "<div style='color:#aaa;font-size:0.82rem;'>" + estado_desc + "</div></div>"

            + alerta_invalidacion
            + alerta_condicion +

            # Métricas de mercado
            "<div class='card'><h5>Métricas de Mercado</h5>"
            "<table class='table table-dark mb-0'>"
            "<thead><tr><th>Indicador</th><th>Valor</th><th>Estado</th>"
            "<th>Referencia</th></tr></thead><tbody>"
            + fila_metrica("Precio AEM",
                           "$" + str(round(aem_act, 2)),
                           sma_badge,
                           "SMA20: $" + str(round(sma20_val, 2)))
            + fila_metrica("Motor · Oro spot (GC=F)",
                           "$" + str(round(oro_act, 0)),
                           oro_badge,
                           "H2: >$4.800 · INV-1: <$3.500")
            + fila_metrica("Benchmark · GDX",
                           "$" + str(round(gdx_act, 2)),
                           h3_badge,
                           "H3: AEM vs GDX 30D >" + str(VENTAJA_AEM_GDX) + "pp")
            + fila_metrica("Volumen AEM",
                           str(int(vol_hoy)),
                           vol_badge,
                           "Media 20D: " + str(int(vol_med20)))
            + fila_metrica("INV-1 · Días oro < $3.500",
                           str(dias_inv1) + " días",
                           badge("ACTIVA", "#ff4444") if inv1_auto else badge("OK", "#2ecc71"),
                           "Umbral: " + str(ORO_DIAS_INV1) + " días consecutivos")
            + "</tbody></table></div>"

            # Condiciones de entrada
            "<div class='card'><h5>Condiciones de Entrada</h5>"
            "<table class='table table-dark mb-0'>"
            "<thead><tr><th>Condición</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>"
            "<tr>"
            "<td style='color:#2ecc71;font-weight:bold;'>A ⭐ Soporte<br>"
            "<small style='color:#555;'>$174-$178 · R/R 5.25:1</small></td>"
            "<td>" + (badge("SEÑAL", "#2ecc71") if nivel_a == 2
                      else badge("EN ZONA", "#f39c12") if nivel_a == 1
                      else badge("INACTIVA", "#555")) + "</td>"
            "<td style='color:#aaa;font-size:0.85rem;'>" + desc_a + "</td>"
            "</tr>"
            "<tr>"
            "<td style='color:#3498db;font-weight:bold;'>B Ruptura<br>"
            "<small style='color:#555;'>$201-$205 · cierre semanal</small></td>"
            "<td>" + (badge("ACTIVA", "#3498db") if cond_b_activa
                      else badge("INACTIVA", "#555")) + "</td>"
            "<td style='color:#aaa;font-size:0.85rem;'>" + desc_b + "</td>"
            "</tr>"
            "<tr>"
            "<td style='color:#888;font-weight:bold;'>Zona muerta</td>"
            "<td>" + (badge("ACTIVA", "#888") if en_zona_muerta
                      else badge("NO", "#555")) + "</td>"
            "<td style='color:#aaa;font-size:0.85rem;'>$178 – $200.77 · sin señal · no entrar</td>"
            "</tr>"
            "</tbody></table></div>"

            # Hitos de tesis
            "<div class='card'><h5>Hitos de Tesis</h5>"
            "<p style='color:#666;font-size:0.78rem;margin-bottom:6px;'>"
            "Hitos INVALIDACIÓN en estado VIGENTE confirman que la tesis está intacta. "
            "H2 y H3 se calculan automáticamente. H1, INV-2, INV-3 requieren actualización manual.</p>"
            "<table class='table table-dark mb-0'>"
            "<thead><tr>"
            "<th style='width:40px;text-align:center;'>-</th>"
            "<th>Hito</th>"
            "<th style='width:110px;text-align:center;'>Categoría</th>"
            "<th style='width:130px;text-align:center;'>Estado</th>"
            "<th style='width:100px;text-align:center;'>Fecha</th>"
            "</tr></thead>"
            "<tbody>" + filas_tg + "</tbody></table>"
            # H2 y H3 como filas adicionales automáticas
            "<p style='color:#555;font-size:0.78rem;margin-top:10px;margin-bottom:4px;'>"
            "Hitos automáticos (calculados en esta ejecución):</p>"
            "<table class='table table-dark mb-0'><tbody>"
            "<tr><td style='color:#aaa;font-size:0.82rem;'>"
            + badge("H2", "#2ecc71" if h2_activo else "#555") +
            " " + desc_h2 + "</td></tr>"
            "<tr><td style='color:#aaa;font-size:0.82rem;'>"
            + badge("H3", "#2ecc71" if h3_ok else "#e74c3c") +
            " " + desc_h3 + "</td></tr>"
            "</tbody></table></div>"

            # Gráfico
            "<div class='card text-center'>"
            "<h5>Fuerza Relativa — Últimas 30 Sesiones</h5>"
            "<img src='data:image/png;base64," + img_b64
            + "' class='img-fluid' style='border-radius:10px;'>"
            "<p style='color:#555;font-size:0.75rem;margin-top:10px;margin-bottom:0;'>"
            "Base 100 = inicio del periodo. Banda verde = zona entrada A. "
            "Línea azul punteada = nivel ruptura B.</p></div>"

            # Mapa de niveles
            "<div class='card'><h5>Mapa de Niveles</h5>"
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

            if invalidaciones_activas:
                header_tg = (
                    "ALERTA MAXIMA — INVALIDACION DE TESIS\n"
                    "==================================================\n"
                    + "\n".join(["INVALIDADO: " + c["hito"] for c in invalidaciones_activas])
                    + "\n==================================================\n"
                    "NO ABRIR POSICION EN AEM\n"
                    "==================================================\n\n"
                )
            elif nivel_a == 2:
                header_tg = (
                    "SEÑAL A DETECTADA — REVISAR AHORA\n"
                    "==================================================\n"
                    "Zona $174-$178 + volumen + vela de reversión.\n"
                    "Abrir broker y confirmar entrada.\n"
                    "==================================================\n\n"
                )
            elif nivel_a == 1:
                header_tg = (
                    "ZONA A ACTIVA — VIGILANCIA\n"
                    "==================================================\n"
                    "Precio en $174-$178. Verificar vela y volumen.\n"
                    "==================================================\n\n"
                )
            elif cond_b_activa:
                header_tg = (
                    "CONDICION B ACTIVADA\n"
                    "==================================================\n"
                    + desc_b + "\n"
                    "Evaluar entrada $201-$205. Stop $174.\n"
                    "==================================================\n\n"
                )
            else:
                header_tg = ""

            resumen = (
                header_tg
                + "MONITOR AEM V1.0\n"
                "==================================================\n"
                "PRECIO AEM: $" + str(round(aem_act, 2)) + "\n"
                "ORO SPOT:   $" + str(round(oro_act, 0)) + "\n"
                "GDX:        $" + str(round(gdx_act, 2)) + "\n"
                "VOLUMEN:    " + ("ALTO" if vol_fuerte else "BAJO") + "\n"
                "SMA20:      $" + str(round(sma20_val, 2))
                + " (" + ("ENCIMA" if aem_act >= sma20_val else "DEBAJO") + ")\n"
                "==================================================\n"
                "ESTADO: " + estado + "\n\n"
                "CONDICION A: " + ["INACTIVA", "EN ZONA", "SEÑAL"][nivel_a] + "\n"
                + desc_a + "\n\n"
                "CONDICION B: " + ("ACTIVA" if cond_b_activa else "INACTIVA") + "\n"
                + desc_b + "\n\n"
                "HITOS AUTOMATICOS:\n"
                + desc_h2 + "\n"
                + desc_h3 + "\n"
                "==================================================\n"
                "HITOS MANUALES:\n"
                + "\n".join([
                    ("VIGENTE " if (h["id"] in IDS_INVALIDACION and h["estado"] is None)
                     else "INVALID " if (h["id"] in IDS_INVALIDACION and h["estado"] is False)
                     else "OK      " if h["estado"] is True
                     else "...     ")
                    + ("INV " if h["id"] in IDS_INVALIDACION else "    ")
                    + h["hito"]
                    for h in hitos
                ])
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
                              "caption": "Monitor AEM V1.0 — " + fecha_now},
                        files={"document": (RUTA_HTML, f, "text/html")},
                        timeout=15
                    )
                print("[OK] Enviado a Telegram.")
            except Exception as e:
                print("[WARN] Fallo Telegram: " + str(e) + " — continuando sin error fatal.")
        else:
            print("[INFO] DRY_RUN=True — Telegram desactivado.")
            print("[INFO] Resumen que se enviaría:\n" + "="*50)
            print("ESTADO: " + estado)
            print("COND. A: " + ["INACTIVA", "EN ZONA", "SEÑAL"][nivel_a])
            print("COND. B: " + ("ACTIVA" if cond_b_activa else "INACTIVA"))
            print("H2: " + desc_h2)
            print("H3: " + desc_h3)
            print("="*50)

        return html

    except Exception as e:
        msg = "[FATAL] Monitor AEM V1.0: " + str(type(e).__name__) + " — " + str(e)
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


# --- Helpers de extracción de datos ---
def get_close(datos: pd.DataFrame, ticker: str) -> pd.Series:
    """Extrae serie de cierres."""
    try:
        return (datos['Close'][ticker]
                if isinstance(datos.columns, pd.MultiIndex)
                else datos['Close'])
    except KeyError:
        raise ValueError("[ERROR] No se pudo obtener Close para " + ticker)

def get_volume(datos: pd.DataFrame, ticker: str) -> pd.Series:
    """Extrae serie de volumen."""
    try:
        return (datos['Volume'][ticker]
                if isinstance(datos.columns, pd.MultiIndex)
                else datos['Volume'])
    except KeyError:
        raise ValueError("[ERROR] No se pudo obtener Volume para " + ticker)

def get_open(datos: pd.DataFrame, ticker: str) -> pd.Series:
    """Extrae serie de aperturas."""
    try:
        return (datos['Open'][ticker]
                if isinstance(datos.columns, pd.MultiIndex)
                else datos['Open'])
    except KeyError:
        raise ValueError("[ERROR] No se pudo obtener Open para " + ticker)

def get_low(datos: pd.DataFrame, ticker: str) -> pd.Series:
    """Extrae serie de mínimos."""
    try:
        return (datos['Low'][ticker]
                if isinstance(datos.columns, pd.MultiIndex)
                else datos['Low'])
    except KeyError:
        raise ValueError("[ERROR] No se pudo obtener Low para " + ticker)


# =============================================================================
# EJECUCIÓN
# =============================================================================
resultado = monitor_aem_v1()
