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
STOP_LOSS       = 41.40
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
        filas += (
            "<tr>"
            "<td style='text-align:center;font-weight:bold;color:" + color_e + ";'>" + icono + "</td>"
            "<td><span style='font-weight:bold;color:#e0e0e0;'>" + h["hito"] + "</span>" + critico_tag + "<br>"
            "<small style='color:#666;'>" + h["detalle"] + "</small></td>"
            "<td style='text-align:center;'><span style='background:" + cat_color + "22;color:" + cat_color + ";"
            "padding:2px 8px;border-radius:6px;font-size:0.75rem;'>" + h["categoria"] + "</span></td>"
            "<td style='text-align:center;color:" + color_e + ";font-weight:bold;font-size:0.8rem;'>" + label_e + "</td>"
            "<td style='color:#555;font-size:0.8rem;text-align:center;'>" + fecha_str + "</td>"
            "</tr>"
        )
    return filas


def render_log(cambios, historial):
    if cambios:
        filas_rec = ""
        for c in cambios:
            color = "#2ecc71" if c["estado_act"] == "cumplido" else "#3498db" if c["estado_act"] == "seguimiento" else "#e74c3c"
            filas_rec += (
                "<tr style='background:#2ecc7111;'>"
                "<td style='color:#2ecc71;font-weight:bold;font-size:0.8rem;'>NUEVO</td>"
                "<td style='font-weight:bold;'>" + c["hito"] + ("  [CRITICO]" if c["critico"] else "") + "</td>"
                "<td style='color:#888;font-size:0.82rem;'>" + c["estado_ant"].upper() + " &rarr; "
                "<span style='color:" + color + ";font-weight:bold;'>" + c["estado_act"].upper() + "</span></td>"
                "</tr>"
            )
    else:
        filas_rec = "<tr><td colspan='3' style='color:#2ecc71;text-align:center;padding:12px;'>Sin cambios en esta ejecucion</td></tr>"

    filas_hist = ""
    entradas = [e for e in reversed(historial) if e.get("cambios_count", 0) > 0][:10]
    if entradas:
        for entrada in entradas:
            for d in entrada.get("detalle", []):
                color = "#2ecc71" if d["estado_nuevo"] == "cumplido" else "#3498db" if d["estado_nuevo"] == "seguimiento" else "#888"
                filas_hist += (
                    "<tr>"
                    "<td style='color:#555;font-size:0.78rem;'>" + entrada["fecha"] + "</td>"
                    "<td style='color:#aaa;font-size:0.82rem;'>" + d["hito"] + "</td>"
                    "<td style='color:#555;font-size:0.78rem;'>" + d["estado_anterior"].upper() + " &rarr; "
                    "<span style='color:" + color + ";'>" + d["estado_nuevo"].upper() + "</span></td>"
                    "</tr>"
                )
    else:
        filas_hist = "<tr><td colspan='3' style='color:#555;text-align:center;padding:12px;'>Sin historial previo</td></tr>"

    return filas_rec, filas_hist


def render_manual():
    return """
    <div class='card'>
      <div class='d-flex justify-content-between align-items-center'
           style='cursor:pointer;' onclick="toggleManual()">
        <h5 style='margin:0;'>Manual de Operacion</h5>
        <span id='manual-icon' style='color:#00d4ff;font-size:1.4rem;font-weight:bold;'>+</span>
      </div>
      <div id='manual-content' style='display:none;margin-top:18px;'>
        <div style='background:#0d1f2d;border-radius:10px;padding:18px;margin-bottom:14px;'>
          <p style='color:#00d4ff;font-weight:bold;margin-bottom:8px;'>Estructura de archivos</p>
          <table style='width:100%;font-size:0.82rem;color:#aaa;'>
            <tr><td style='padding:4px 12px 4px 0;color:#00d4ff;font-weight:bold;'>golar/hitos_estado.json</td>
                <td>Archivo que editas para cambiar el estado de los hitos.</td></tr>
            <tr><td style='padding:4px 12px 4px 0;color:#00d4ff;font-weight:bold;'>golar/hitos_historial.json</td>
                <td>Registro automatico de cambios. No editar.</td></tr>
            <tr><td style='padding:4px 12px 4px 0;color:#00d4ff;font-weight:bold;'>golar/monitor_golar_v5.py</td>
                <td>Script principal. Solo editar seccion 1 (configuracion).</td></tr>
          </table>
        </div>
        <div style='background:#0d1f2d;border-radius:10px;padding:18px;margin-bottom:14px;'>
          <p style='color:#00d4ff;font-weight:bold;margin-bottom:8px;'>Como actualizar un hito</p>
          <table style='width:100%;font-size:0.82rem;'>
            <thead><tr>
              <th style='color:#555;padding:4px 12px 8px 0;'>Situacion</th>
              <th style='color:#555;padding:4px 12px 8px 0;'>estado</th>
              <th style='color:#555;padding:4px 0 8px 0;'>fecha</th>
            </tr></thead>
            <tbody>
              <tr><td style='color:#aaa;padding:4px 12px 4px 0;'>No ocurrido</td>
                  <td><code>false</code></td><td><code>null</code></td></tr>
              <tr><td style='color:#aaa;padding:4px 12px 4px 0;'>Indicios sin confirmar</td>
                  <td><code>null</code></td><td><code>null</code></td></tr>
              <tr><td style='color:#aaa;padding:4px 12px 4px 0;'>Confirmado oficialmente</td>
                  <td><code>true</code></td><td><code>"DD/MM/AAAA"</code></td></tr>
            </tbody>
          </table>
        </div>
        <div style='background:#0d1f2d;border-radius:10px;padding:18px;margin-bottom:14px;'>
          <p style='color:#00d4ff;font-weight:bold;margin-bottom:8px;'>Flujo de trabajo</p>
          <ol style='color:#aaa;font-size:0.85rem;padding-left:18px;margin:0;'>
            <li style='margin-bottom:8px;'>Recibes una noticia relevante sobre Golar.</li>
            <li style='margin-bottom:8px;'>Abres <code>golar/hitos_estado.json</code> en GitHub, pulsas el lapiz, cambias estado y fecha, commit.</li>
            <li style='margin-bottom:8px;'>Ejecutas en Colab o esperas la ejecucion programada de GitHub Actions.</li>
            <li>El informe detecta el cambio y notifica por Telegram con el log de cambios.</li>
          </ol>
        </div>
        <div style='background:#0d1f2d;border-radius:10px;padding:18px;margin-bottom:14px;'>
          <p style='color:#00d4ff;font-weight:bold;margin-bottom:8px;'>Hitos criticos</p>
          <p style='color:#aaa;font-size:0.85rem;margin:0;'>
            Si 3 o mas hitos CRITICO permanecen en PENDIENTE, el score de conviccion
            se limita al 35% automaticamente — senal de revision inmediata de la tesis.
          </p>
        </div>
        <div style='background:#0d1f2d;border-radius:10px;padding:18px;'>
          <p style='color:#00d4ff;font-weight:bold;margin-bottom:8px;'>Parametros de precio</p>
          <table style='width:100%;font-size:0.82rem;'>
            <tr><td style='color:#00d4ff;font-weight:bold;padding:3px 12px 3px 0;'>PRECIO_ENTRADA</td><td style='color:#aaa;'>Precio medio de compra.</td></tr>
            <tr><td style='color:#e74c3c;font-weight:bold;padding:3px 12px 3px 0;'>STOP_LOSS</td>    <td style='color:#aaa;'>Nivel de salida obligatoria.</td></tr>
            <tr><td style='color:#f39c12;font-weight:bold;padding:3px 12px 3px 0;'>ZONA_COSECHA</td> <td style='color:#aaa;'>Inicio zona de beneficios.</td></tr>
            <tr><td style='color:#e74c3c;font-weight:bold;padding:3px 12px 3px 0;'>ZONA_VENTA</td>   <td style='color:#aaa;'>Venta activa de la posicion.</td></tr>
            <tr><td style='color:#2ecc71;font-weight:bold;padding:3px 12px 3px 0;'>OBJETIVO</td>     <td style='color:#aaa;'>Precio objetivo de la tesis.</td></tr>
          </table>
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
# 4. FUNCION PRINCIPAL
# =============================================================================
def monitor_golar_v5():
    try:
        fecha_now = datetime.now().strftime("%d/%m/%Y %H:%M")

        hitos     = cargar_hitos()
        historial = cargar_historial()
        cambios   = detectar_cambios(hitos, historial)
        guardar_historial(historial, hitos, cambios, fecha_now)

        print("Descargando datos...")
        datos      = yf.download(["GLNG", "JKM=F", "LNGX", "EURUSD=X"], period="90d", progress=False)
        glng_serie = get_close(datos, "GLNG").ffill().bfill()
        jkm_serie  = get_close(datos, "JKM=F").ffill().bfill()
        lngx_serie = get_close(datos, "LNGX").ffill().bfill()
        vol_serie  = get_volume(datos, "GLNG").ffill().bfill()

        if jkm_serie.isna().all() or (jkm_serie == 0).all():
            print("JKM=F sin datos — usando NG=F.")
            jkm_serie = get_close(yf.download(["NG=F"], period="90d", progress=False), "NG=F").ffill().bfill()
            jkm_label = "NG=F"
        else:
            jkm_label = "JKM=F"

        glng_act    = float(glng_serie.iloc[-1])
        jkm_act     = float(jkm_serie.iloc[-1])
        lngx_act    = float(lngx_serie.iloc[-1])
        sma30_serie = glng_serie.rolling(window=30).mean()
        sma30_val   = float(sma30_serie.iloc[-1])
        vol_hoy     = float(vol_serie.iloc[-1])
        vol_med     = float(vol_serie.rolling(window=10).mean().iloc[-1])
        fuerza      = vol_hoy > vol_med
        pnl         = ((glng_act - PRECIO_ENTRADA) / PRECIO_ENTRADA) * 100
        pct_prog    = min(100, max(0, (glng_act - STOP_LOSS) / (OBJETIVO - STOP_LOSS) * 100))

        print("GLNG: $" + str(round(glng_act, 2)) + " (" + ("+" if pnl >= 0 else "") + str(round(pnl, 2)) + "%)")

        if jkm_act > JKM_UMBRAL and glng_act > PRECIO_ENTRADA:
            diagnostico, diag_desc, diag_color = "VIENTO DE COLA",  "Motor (JKM) y Precio acompanan la subida.", "#2ecc71"
        elif jkm_act <= JKM_UMBRAL and glng_act > PRECIO_ENTRADA:
            diagnostico, diag_desc, diag_color = "LA TRAMPA",       "Subida por inercia. Motor debil, cuidado.", "#e67e22"
        elif jkm_act > JKM_UMBRAL and glng_act <= PRECIO_ENTRADA:
            diagnostico, diag_desc, diag_color = "EL REFUGIO",      "Sector sufre pero materia prima cara.",     "#3498db"
        else:
            diagnostico, diag_desc, diag_color = "ZONA NEUTRA",     "Sin catalizadores claros.",                 "#888888"

        if glng_act >= OBJETIVO:
            estado, estado_color, estado_desc = "OBJETIVO ALCANZADO",    "#2ecc71", "Revisar tesis de salida completa."
        elif glng_act >= ZONA_VENTA:
            estado, estado_color, estado_desc = "VENDER — COSECHA",      "#e74c3c", "Zona de beneficio superada."
        elif glng_act >= ZONA_COSECHA:
            if glng_act < sma30_val and fuerza:
                estado, estado_color, estado_desc = "VIGILAR — Reducir", "#e67e22", "Precio bajo SMA con volumen alto."
            else:
                estado, estado_color, estado_desc = "MANTENER — Zona cosecha", "#f39c12", "Seguimiento activo recomendado."
        elif glng_act <= STOP_LOSS:
            estado, estado_color, estado_desc = "STOP LOSS",             "#e74c3c", "Nivel de stop alcanzado. Salir."
        else:
            estado, estado_color, estado_desc = "MANTENER",              "#2ecc71", "Dentro del rango de tesis."

        score_conv, label_conv, color_conv = calcular_conviccion(hitos)
        hitos_ok  = sum(1 for h in hitos if h["estado"] is True)
        hitos_seg = sum(1 for h in hitos if h["estado"] is None)
        hitos_pen = sum(1 for h in hitos if h["estado"] is False)
        filas_tg  = render_hitos(hitos)
        filas_rec, filas_hist = render_log(cambios, historial)
        manual_html = render_manual()

        print("Generando grafico...")
        plot_data         = glng_serie.tail(30).to_frame(name='GLNG')
        plot_data['LNGX'] = lngx_serie.tail(30).values
        plot_data['JKM']  = jkm_serie.tail(30).values
        relativa          = (plot_data / plot_data.iloc[0]) * 100
        sma_rel           = (sma30_serie.tail(30) / float(glng_serie.tail(30).iloc[0])) * 100

        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
        ax.plot(relativa['GLNG'], label='MI POSICION: Golar LNG', color='#00d4ff', linewidth=3.0, zorder=4)
        ax.plot(sma_rel,          label='SOPORTE: Media 30 ses.', color='#ff4d4d', linestyle='--', linewidth=1.8)
        ax.plot(relativa['LNGX'], label='SENTIMIENTO: ETF Gas',   color='#ff9f43', linewidth=1.5, alpha=0.7)
        ax.plot(relativa['JKM'],  label='MOTOR: ' + jkm_label,   color='#2ecc71', linewidth=1.5, alpha=0.7)

        for i in range(1, len(relativa)):
            pg, cg = relativa['GLNG'].iloc[i-1], relativa['GLNG'].iloc[i]
            ps, cs = sma_rel.iloc[i-1], sma_rel.iloc[i]
            if not pd.isna(ps) and not pd.isna(cs) and pg > ps and cg < cs:
                ax.scatter(relativa.index[i], cg, color='#e74c3c', marker='v', s=150, zorder=5)

        ax.set_title("Fuerza Relativa — Ultimas 30 sesiones", color='#00d4ff', fontsize=13, pad=12)
        ax.legend(loc='upper left', facecolor='#1e1e1e', fontsize=9)
        ax.grid(alpha=0.08)
        ax.tick_params(colors='#888')
        for spine in ax.spines.values():
            spine.set_edgecolor('#333')

        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor='#121212', bbox_inches='tight')
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode()
        plt.close(fig)

        pnl_color = "#2ecc71" if pnl >= 0 else "#e74c3c"
        jkm_badge = badge("FUERTE", "#2ecc71") if jkm_act > JKM_UMBRAL else badge("DEBIL", "#e67e22")
        vol_badge = badge("ALTO",   "#2ecc71") if fuerza               else badge("BAJO",  "#e74c3c")
        sma_badge = badge("POR ENCIMA", "#2ecc71") if glng_act >= sma30_val else badge("POR DEBAJO", "#e74c3c")
        entorno   = "Google Colab" if EN_COLAB else "GitHub Actions" if EN_GITHUB else "Local"

        alerta_cambios = (
            "<div style='background:#2ecc7122;border-left:4px solid #2ecc71;"
            "border-radius:8px;padding:12px 18px;margin-bottom:20px;'>"
            "<span style='color:#2ecc71;font-weight:bold;'>" + str(len(cambios)) +
            " cambio(s) detectado(s) en esta ejecucion</span> — Ver Log de Cambios</div>"
        ) if cambios else ""

        niveles_html = ""
        for lbl, precio, accion, c in [
            ("Objetivo",  OBJETIVO,       "Revision completa de tesis",        "#2ecc71"),
            ("Venta",     ZONA_VENTA,     "Iniciar cosecha de beneficios",      "#e74c3c"),
            ("Cosecha",   ZONA_COSECHA,   "Vigilancia activa",                  "#f39c12"),
            ("Entrada",   PRECIO_ENTRADA, "Precio medio de entrada",            "#3498db"),
            ("Stop Loss", STOP_LOSS,      "Salida automatica",                  "#e74c3c"),
        ]:
            dist_color = "#2ecc71" if glng_act >= precio else "#e74c3c"
            dist_val   = ("+" if glng_act >= precio else "") + str(round(glng_act - precio, 2))
            niveles_html += (
                "<tr>"
                "<td style='color:" + c + ";font-weight:bold;'>" + lbl + "</td>"
                "<td><code>$" + str(precio) + "</code></td>"
                "<td style='color:#aaa;font-size:0.85rem;'>" + accion + "</td>"
                "<td style='color:" + dist_color + ";font-size:0.85rem;'>" + dist_val + "</td>"
                "</tr>"
            )

        html = (
            "<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'>"
            "<link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>"
            "<style>"
            "body{background:#121212;color:#e0e0e0;padding:25px;font-family:'Segoe UI',sans-serif;}"
            ".card{background:#1e1e1e;border-radius:15px;padding:22px;margin-bottom:20px;border:none;}"
            "h5{color:#00d4ff;text-transform:uppercase;font-size:0.85rem;letter-spacing:1.5px;margin-bottom:15px;}"
            "th{color:#555;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #2a2a2a !important;}"
            "td{vertical-align:middle !important;border-bottom:1px solid #1a1a1a !important;padding:11px 8px !important;}"
            "code{background:#2a2a2a;color:#00d4ff;padding:2px 6px;border-radius:4px;font-size:0.8rem;}"
            ".price{font-size:2.8rem;font-weight:800;color:#00d4ff;line-height:1;}"
            ".pnl{font-size:1.3rem;font-weight:700;color:" + pnl_color + ";}"
            ".estado-box{background:" + estado_color + "18;border-left:4px solid " + estado_color + ";border-radius:8px;padding:14px 18px;}"
            ".diag-box{background:" + diag_color + "18;border-left:4px solid " + diag_color + ";border-radius:8px;padding:14px 18px;}"
            ".conv-box{background:" + color_conv + "18;border-left:4px solid " + color_conv + ";border-radius:8px;padding:14px 18px;}"
            ".progress{height:10px;border-radius:5px;background:#2a2a2a;}"
            ".progress-bar{border-radius:5px;}"
            ".nivel{font-size:0.72rem;color:#555;}"
            "</style></head><body>"
            "<div class='container' style='max-width:960px;'>"

            "<div class='d-flex justify-content-between align-items-center mb-4'>"
            "<div><h2 style='color:#00d4ff;margin:0;'>Monitor Golar LNG</h2>"
            "<small style='color:#555;'>GLNG V5.0 " + entorno + " " + fecha_now + "</small></div>"
            "<div style='text-align:right;'>"
            "<div class='price'>$" + str(round(glng_act, 2)) + "</div>"
            "<div class='pnl'>" + ("+" if pnl >= 0 else "") + str(round(pnl, 2)) + "% vs entrada</div>"
            "</div></div>"

            + alerta_cambios +

            "<div class='card'><div class='row g-3'>"
            "<div class='col-md-4'><h5>Estado</h5><div class='estado-box'>"
            "<div style='color:" + estado_color + ";font-size:1rem;font-weight:bold;margin-bottom:6px;'>" + estado + "</div>"
            "<div style='color:#aaa;font-size:0.82rem;'>" + estado_desc + "</div></div></div>"
            "<div class='col-md-4'><h5>Diagnostico</h5><div class='diag-box'>"
            "<div style='color:" + diag_color + ";font-size:1rem;font-weight:bold;margin-bottom:6px;'>" + diagnostico + "</div>"
            "<div style='color:#aaa;font-size:0.82rem;'>" + diag_desc + "</div></div></div>"
            "<div class='col-md-4'><h5>Conviccion</h5><div class='conv-box'>"
            "<div style='color:" + color_conv + ";font-size:1rem;font-weight:bold;margin-bottom:6px;'>" + label_conv + "</div>"
            "<div style='color:#aaa;font-size:0.82rem;'>OK " + str(hitos_ok) + " | SEG " + str(hitos_seg) + " | PEND " + str(hitos_pen) + "</div>"
            "<div class='progress mt-2'><div class='progress-bar' style='width:" + str(round(score_conv)) + "%;background:" + color_conv + ";'></div></div>"
            "<small style='color:#555;'>" + str(round(score_conv)) + "% hitos validados</small>"
            "</div></div></div></div>"

            "<div class='card'><h5>Progreso hacia Objetivo</h5>"
            "<div class='d-flex justify-content-between mb-1'>"
            "<span class='nivel'>STOP $" + str(STOP_LOSS) + "</span>"
            "<span class='nivel'>ENTRADA $" + str(PRECIO_ENTRADA) + "</span>"
            "<span class='nivel'>COSECHA $" + str(ZONA_COSECHA) + "</span>"
            "<span class='nivel'>VENTA $" + str(ZONA_VENTA) + "</span>"
            "<span class='nivel'>OBJETIVO $" + str(OBJETIVO) + "</span>"
            "</div>"
            "<div class='progress'><div class='progress-bar' style='width:" + str(round(pct_prog, 1)) + "%;background:linear-gradient(90deg,#e74c3c,#f39c12,#2ecc71);'></div></div>"
            "<div class='text-end mt-1'><small style='color:#555;'>" + str(round(pct_prog, 1)) + "% del recorrido Stop &rarr; Objetivo</small></div></div>"

            "<div class='card'><h5>Metricas</h5>"
            "<table class='table table-dark mb-0'>"
            "<thead><tr><th>Indicador</th><th>Valor</th><th>Estado</th><th>Referencia</th></tr></thead><tbody>"
            + fila_metrica("Precio GLNG",        "$" + str(round(glng_act, 2)),  badge(("+" if pnl >= 0 else "") + str(round(pnl, 2)) + "%", pnl_color), "Entrada: $" + str(PRECIO_ENTRADA))
            + fila_metrica("Motor " + jkm_label, "$" + str(round(jkm_act, 2)),   jkm_badge, "Umbral: $" + str(JKM_UMBRAL))
            + fila_metrica("Sentimiento LNGX",   "$" + str(round(lngx_act, 2)),  badge("LNGX", "#9b59b6"), "ETF Gas Natural")
            + fila_metrica("SMA 30 ses.",        "$" + str(round(sma30_val, 2)), sma_badge, "GLNG " + ("arriba" if glng_act >= sma30_val else "abajo") + " SMA")
            + fila_metrica("Volumen GLNG",       str(int(vol_hoy)),              vol_badge, "Media 10d: " + str(int(vol_med))) +
            "</tbody></table></div>"

            "<div class='card'><h5>Hitos de Tesis T-G</h5>"
            "<p style='color:#666;font-size:0.78rem;margin-bottom:12px;'>Los hitos CRITICO son condicion necesaria para mantener la conviccion.</p>"
            "<table class='table table-dark mb-0'>"
            "<thead><tr><th style='width:40px;text-align:center;'>-</th><th>Hito</th>"
            "<th style='width:110px;text-align:center;'>Categoria</th>"
            "<th style='width:120px;text-align:center;'>Estado</th>"
            "<th style='width:100px;text-align:center;'>Fecha</th></tr></thead>"
            "<tbody>" + filas_tg + "</tbody></table></div>"

            "<div class='card'><h5>Log de Cambios</h5>"
            "<p style='color:#aaa;font-size:0.78rem;margin-bottom:6px;font-weight:bold;'>Esta ejecucion:</p>"
            "<table class='table table-dark mb-3'><thead><tr><th>Cuando</th><th>Hito</th><th>Cambio</th></tr></thead>"
            "<tbody>" + filas_rec + "</tbody></table>"
            "<p style='color:#aaa;font-size:0.78rem;margin-bottom:6px;font-weight:bold;'>Historial previo:</p>"
            "<table class='table table-dark mb-0'><thead><tr><th>Fecha</th><th>Hito</th><th>Cambio</th></tr></thead>"
            "<tbody>" + filas_hist + "</tbody></table></div>"

            "<div class='card text-center'><h5>Fuerza Relativa — Ultimas 30 Sesiones</h5>"
            "<img src='data:image/png;base64," + img_b64 + "' class='img-fluid' style='border-radius:10px;'>"
            "<p style='color:#555;font-size:0.75rem;margin-top:10px;margin-bottom:0;'>"
            "Base 100 = inicio del periodo. Triangulo rojo = cruce bajista bajo SMA30.</p></div>"

            "<div class='card'><h5>Mapa de Niveles</h5>"
            "<table class='table table-dark mb-0'>"
            "<thead><tr><th>Nivel</th><th>Precio</th><th>Accion</th><th>Distancia</th></tr></thead>"
            "<tbody>" + niveles_html + "</tbody></table></div>"

            + manual_html +
            "</div></body></html>"
        )

        os.makedirs(CARPETA, exist_ok=True)

        if EN_COLAB:
            from IPython.display import display, HTML as IPY_HTML
            display(IPY_HTML(html))
            print("HTML renderizado en Colab.")

        with open(RUTA_HTML, "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML guardado: " + RUTA_HTML)

        if ENVIAR_TELEGRAM:
            print("Enviando a Telegram...")
            url_tg = "https://api.telegram.org/bot" + TOKEN + "/"

            cambios_tg = ""
            if cambios:
                cambios_tg = "\n\nCAMBIOS EN HITOS:\n" + "\n".join([
                    ("CRITICO " if c["critico"] else "") + c["hito"] +
                    "\n  " + c["estado_ant"].upper() + " -> " + c["estado_act"].upper()
                    for c in cambios
                ])

            resumen = (
                "MONITOR GOLAR V5.0\n"
                "==========================\n"
                "PRECIO: $" + str(round(glng_act, 2)) + "  (" + ("+" if pnl >= 0 else "") + str(round(pnl, 2)) + "%)\n"
                + jkm_label + ": $" + str(round(jkm_act, 2)) + "  " + ("FUERTE" if jkm_act > JKM_UMBRAL else "DEBIL") + "\n"
                "VOLUMEN: " + ("ALTO" if fuerza else "BAJO") + "\n"
                "==========================\n"
                + diagnostico + "\n" + diag_desc + "\n\n"
                + estado + "\n" + estado_desc + "\n"
                "==========================\n"
                "CONVICCION: " + label_conv + " (" + str(round(score_conv)) + "%)\n\n"
                "HITOS T-G:\n" + "\n".join([
                    ("OK  " if h["estado"] is True else "... " if h["estado"] is None else "X   ") +
                    ("CRIT " if h["critico"] else "     ") + h["hito"]
                    for h in hitos
                ])
                + cambios_tg + "\n"
                "==========================\n"
                "OBJETIVO $" + str(OBJETIVO) + " | STOP $" + str(STOP_LOSS) + " | " + str(round(pct_prog, 1)) + "% recorrido"
            )

            requests.post(url_tg + "sendMessage",
                          data={"chat_id": CHAT_ID, "text": resumen}, timeout=15)
            with open(RUTA_HTML, "rb") as f:
                requests.post(url_tg + "sendDocument",
                              data={"chat_id": CHAT_ID, "caption": "Monitor Golar V5.0 — " + fecha_now},
                              files={"document": (RUTA_HTML, f, "text/html")}, timeout=15)
            print("Enviado a Telegram.")

        return html

    except Exception as e:
        print("Error: " + str(type(e).__name__) + " - " + str(e))
        if ENVIAR_TELEGRAM:
            try:
                requests.post(
                    "https://api.telegram.org/bot" + TOKEN + "/sendMessage",
                    data={"chat_id": CHAT_ID, "text": "Error Monitor Golar V5.0: " + str(e)},
                    timeout=15)
            except Exception:
                pass
        return None


# EJECUCION
resultado = monitor_golar_v5()
