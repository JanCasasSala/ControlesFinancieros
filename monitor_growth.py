import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
import io
import base64

# =============================================================================
# VERSIÓN 1.6
# Fix #12: Capitalización 'Repurchase Of Capital Stock'
# Fix #13: Sistema de advertencias por métrica no encontrada
# Fix #14: Búsqueda fuzzy case-insensitive
# Fix #15: Glosario detallado 6 métricas
# Fix #16: Validación temporal trimestres — evita solapamiento (bug Gartner -198%)
# Fix #17: Glosario — nueva fila 'Acreción + NRR < 100%' con alerta combinada
# =============================================================================

TOKEN = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID = "8351044609"

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


def color_sbc(v: float) -> str:
    return '#ff4d4d' if v > 20 else '#2ecc71'


def color_nrr(v: float) -> str:
    return '#ff4d4d' if v < 100 else '#2ecc71'


def get_annual_sum(cf: pd.DataFrame, labels: list, metric_name: str, warnings: list, tk: str):
    # Búsqueda exacta
    for label in labels:
        if label in cf.index:
            row = cf.loc[label].dropna()
            if not row.empty:
                cols = row.index[:4]

                # Fix #16: validar que los 4 trimestres no cubran más de 13 meses
                if len(cols) >= 2:
                    span = (cols[0] - cols[min(3, len(cols) - 1)]).days
                    if span > 400:
                        warnings.append({
                            "tk": tk, "metric": metric_name,
                            "msg": f"Solapamiento temporal detectado ({span} días entre T1 y T4). Usando solo 2 trimestres para evitar duplicación.",
                            "level": "warning"
                        })
                        cols = cols[:2]

                return float(row[cols].sum()), label

    # Búsqueda fuzzy case-insensitive
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
                        warnings.append({
                            "tk": tk, "metric": metric_name,
                            "msg": f"Fuzzy + solapamiento ({span} días). Usando 2 trimestres.",
                            "level": "warning"
                        })
                        cols = cols[:2]
                warnings.append({
                    "tk": tk, "metric": metric_name,
                    "msg": f"Etiqueta fuzzy usada: '{match}' (buscada: '{label}')",
                    "level": "info"
                })
                return float(row[cols].sum()), match

    # No encontrado
    warnings.append({
        "tk": tk, "metric": metric_name,
        "msg": f"No encontrada. Etiquetas probadas: {labels}",
        "level": "warning"
    })
    return 0.0, None


def ejecutar_v1_6():
    TESIS_QUARTERLY = {
        "ADBE": {"nrr": 111.0, "t_g": 0, "color": "#2ecc71"},
        "IT":   {"nrr": 105.0, "t_g": 0, "color": "#9b59b6"},
        "FDS":  {"nrr": 101.0, "t_g": 0, "color": "#34495e"},
        "CRM":  {"nrr": 108.5, "t_g": 0, "color": "#3498db"},
        "PYPL": {"nrr": 98.2,  "t_g": 1, "color": "#e67e22"},
    }

    data_points = []
    all_warnings = []

    for tk, tesis in TESIS_QUARTERLY.items():
        ticker_warnings = []
        try:
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
                    ticker_warnings.append({
                        "tk": tk, "metric": "FCF",
                        "msg": "FCF calculado manualmente (OCF - CapEx).",
                        "level": "info"
                    })

            sbc_neto_valor = sbc_total - buybacks

            if fcf_total > 0:
                sbc_neto_ratio = (sbc_neto_valor / fcf_total) * 100
            elif fcf_total < 0:
                sbc_neto_ratio = -(abs(sbc_neto_valor) / abs(fcf_total)) * 100
            else:
                sbc_neto_ratio = 0.0
                ticker_warnings.append({
                    "tk": tk, "metric": "SBC_Neto/FCF",
                    "msg": "FCF = 0, ratio no calculable.",
                    "level": "warning"
                })

            shares    = float(info.get('sharesOutstanding') or 1)
            fcf_yield = ((fcf_total / shares) / price * 100) if price > 0 else 0

            # Diagnóstico — Fix #17: alerta combinada NRR < 100% + acreción agresiva
            diag = []
            if tesis["nrr"] < 100:
                diag.append("⚠️ NRR < 100%")
            else:
                diag.append("✅ NRR Sólido")

            if sbc_neto_valor < 0:
                diag.append("🔄 Acreción: Buybacks > SBC")
                # Alerta combinada: acreción agresiva con NRR débil
                if tesis["nrr"] < 100 and sbc_neto_ratio < -50:
                    diag.append("🚨 Alerta: Acreción agresiva + NRR < 100%")
            elif sbc_neto_ratio > 20:
                diag.append("🚨 Dilución Neta Alta")

            if fcf_yield > 5:
                diag.append("💎 Yield Atractivo")
            if any(w["level"] == "warning" for w in ticker_warnings):
                diag.append("⚠️ Dato incompleto")

            warn_count = len([w for w in ticker_warnings if w["level"] == "warning"])
            print(f"{tk}: SBC={sbc_total/1e9:.2f}B [{sbc_label}] | "
                  f"Buybacks={buybacks/1e9:.2f}B [{bb_label}] | "
                  f"FCF={fcf_total/1e9:.2f}B | "
                  f"SBC_Neto/FCF={sbc_neto_ratio:.1f}% | Warnings={warn_count}")

            all_warnings.extend(ticker_warnings)

            data_points.append({
                "TKR":      tk,
                "PRECIO":   f"${price:.2f}",
                "NRR":      tesis["nrr"],
                "SBC_NETO": sbc_neto_ratio,
                "YIELD":    f"{fcf_yield:.1f}%",
                "T_G":      f"{tesis['t_g']}/4",
                "DIAG":     " | ".join(diag),
                "color":    tesis["color"],
                "SBC_ABS":  f"${sbc_total/1e9:.2f}B",
                "BB_ABS":   f"${buybacks/1e9:.2f}B",
                "FCF_ABS":  f"${fcf_total/1e9:.2f}B",
                "SBC_LBL":  sbc_label or "❌ no encontrado",
                "BB_LBL":   bb_label  or "❌ no encontrado",
                "HAS_WARN": warn_count > 0,
                "NRR_RAW":  tesis["nrr"],
            })

        except Exception as e:
            print(f"Error {tk}: {type(e).__name__} - {e}")
            all_warnings.append({
                "tk": tk, "metric": "GENERAL",
                "msg": f"{type(e).__name__}: {e}",
                "level": "error"
            })

    if not data_points:
        print("No se obtuvieron datos. Abortando.")
        return

    # -------------------------------------------------------------------------
    # Gráfico
    # -------------------------------------------------------------------------
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(11, 6), dpi=200)

    sbc_vals   = [p["SBC_NETO"] for p in data_points]
    y_margin   = (max(sbc_vals) - min(sbc_vals)) * 0.25 + 8
    y_plot_min = min(sbc_vals) - y_margin
    y_plot_max = max(sbc_vals) + y_margin

    ax.axhspan(y_plot_min, 0,          alpha=0.06, color='#2ecc71')
    ax.axhspan(0,          y_plot_max, alpha=0.06, color='#ff4d4d')

    for p in data_points:
        # Alerta combinada: borde naranja en gráfico
        edge_color = '#e67e22' if (p["NRR_RAW"] < 100 and p["SBC_NETO"] < -50) else 'white'
        marker     = '*' if p["HAS_WARN"] else 'o'
        ax.scatter(p["NRR"], p["SBC_NETO"], s=700, color=p["color"],
                   alpha=0.85, edgecolors=edge_color, linewidths=2.0,
                   zorder=5, marker=marker)
        ax.text(p["NRR"], p["SBC_NETO"] + y_margin * 0.18,
                p["TKR"], fontsize=10, fontweight='bold', ha='center', color='white')

    ax.axvline(100, color='#ff4d4d', linestyle='--', alpha=0.4)
    ax.axhline(0,   color='white',   linestyle='-',  alpha=0.25)
    ax.set_ylim(y_plot_min, y_plot_max)
    ax.set_xlabel("NRR (%)", color='#aaa', fontsize=11)
    ax.set_ylabel("← Acreción  |  Dilución →\n(SBC Neto / FCF %)", color='#aaa', fontsize=10)
    ax.set_title("NRR vs Dilución Neta (anualizado, 4T)  — ★ = dato incompleto | 🟠 = alerta NRR+Acreción",
                 color='#00d4ff', fontsize=12, pad=12)
    ax.tick_params(colors='#888')

    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor='#121212', bbox_inches='tight')
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode()
    plt.close(fig)

    # -------------------------------------------------------------------------
    # HTML — tablas
    # -------------------------------------------------------------------------
    filas_m = ""
    for p in data_points:
        warn_icon   = " ⚠️" if p["HAS_WARN"] else ""
        alert_icon  = " 🚨" if (p["NRR_RAW"] < 100 and p["SBC_NETO"] < -50) else ""
        title_sbc   = "SBC:" + p["SBC_ABS"] + " [" + p["SBC_LBL"] + "] BB:" + p["BB_ABS"] + " [" + p["BB_LBL"] + "] FCF:" + p["FCF_ABS"]
        title_yield = "FCF:" + p["FCF_ABS"]
        filas_m += (
            "<tr>"
            "<td style='color:" + p["color"] + ";font-weight:bold;'>" + p["TKR"] + warn_icon + alert_icon + "</td>"
            "<td>" + p["PRECIO"] + "</td>"
            "<td style='color:" + color_nrr(p["NRR_RAW"]) + ";font-weight:bold;'>" + str(p["NRR"]) + "%</td>"
            "<td style='color:" + color_sbc(p["SBC_NETO"]) + ";font-weight:bold;' title='" + title_sbc + "'>"
            + f"{p['SBC_NETO']:.1f}%" + "</td>"
            "<td title='" + title_yield + "'>" + p["YIELD"] + "</td>"
            "<td class='text-center'>" + p["T_G"] + "</td>"
            "</tr>"
        )

    filas_d = ""
    for p in data_points:
        filas_d += (
            "<tr>"
            "<td style='background:" + p["color"] + "22;color:" + p["color"] + ";font-weight:bold;width:120px;'>" + p["TKR"] + "</td>"
            "<td>" + p["DIAG"] + "</td>"
            "<td style='color:#888;font-size:0.8rem;'>SBC " + p["SBC_ABS"] + " | BB " + p["BB_ABS"] + " | FCF " + p["FCF_ABS"] + "</td>"
            "</tr>"
        )

    icon_map  = {"warning": "⚠️", "info": "ℹ️", "error": "🚨"}
    color_map = {"warning": "#e67e22", "info": "#3498db", "error": "#ff4d4d"}
    filas_w   = ""
    if all_warnings:
        for w in all_warnings:
            ico   = icon_map.get(w["level"], "ℹ️")
            color = color_map.get(w["level"], "#888")
            filas_w += (
                "<tr>"
                "<td style='color:" + color + ";font-weight:bold;'>" + ico + " " + w["tk"] + "</td>"
                "<td style='color:#aaa;font-size:0.8rem;'>" + w["metric"] + "</td>"
                "<td style='color:#888;font-size:0.78rem;'>" + w["msg"] + "</td>"
                "</tr>"
            )
    else:
        filas_w = "<tr><td colspan='3' style='color:#2ecc71;text-align:center;'>✅ Todos los datos encontrados correctamente</td></tr>"

    # -------------------------------------------------------------------------
    # Glosario — Fix #17: nueva fila 'Acreción + NRR < 100%'
    # -------------------------------------------------------------------------
    glosario = """
      <tbody>
        <tr>
          <td><span class='g-title'>NRR</span><br><small style='color:#888;'>Net Revenue Retention</small></td>
          <td>
            Mide qué porcentaje de los ingresos de los clientes existentes se retiene y hace crecer año a año,
            incluyendo expansiones, upsells y cross-sells, pero descontando cancelaciones y downgrades.<br><br>
            <b>Fórmula:</b> <code>(Ingresos clientes año N) / (Ingresos mismos clientes año N-1) × 100</code><br><br>
            Un NRR &gt; 100% significa que la base existente crece sola, sin necesidad de nuevas adquisiciones.
            Es el indicador más fiable de la salud del producto y la fidelidad del cliente en empresas SaaS.
          </td>
          <td>
            <span style='color:#2ecc71;'>▲ &gt; 110% — Excelente. Crecimiento orgánico fuerte.</span><br><br>
            <span style='color:#f39c12;'>◆ 100–110% — Sólido. Retención saludable.</span><br><br>
            <span style='color:#ff4d4d;'>▼ &lt; 100% — Churn neto. La base se contrae.</span>
          </td>
        </tr>

        <tr style='background:#1a1a1a;'>
          <td><span class='g-title'>FCF</span><br><small style='color:#888;'>Free Cash Flow</small></td>
          <td>
            Caja real generada por el negocio tras pagar todas las operaciones e inversiones en activos físicos (CapEx).
            A diferencia del beneficio contable, no se ve distorsionado por amortizaciones ni ajustes no monetarios.<br><br>
            <b>Fórmula:</b> <code>FCF = Flujo de Caja Operativo − CapEx</code><br><br>
            Es la métrica de rentabilidad más honesta para evaluar si una empresa genera valor real,
            ya que refleja el dinero disponible para recompras, dividendos, deuda o reinversión.
          </td>
          <td>
            <span style='color:#2ecc71;'>▲ Positivo y creciente — Negocio autosuficiente.</span><br><br>
            <span style='color:#f39c12;'>◆ Positivo pero estable — Madurez sin reinversión.</span><br><br>
            <span style='color:#ff4d4d;'>▼ Negativo — Quema de caja. Requiere financiación externa.</span>
          </td>
        </tr>

        <tr>
          <td><span class='g-title'>FCF Yield</span><br><small style='color:#888;'>Rentabilidad sobre precio</small></td>
          <td>
            Indica cuánto FCF genera la empresa por cada dólar invertido a precio de mercado.
            Es el equivalente al earnings yield pero usando caja real en lugar de beneficio contable.<br><br>
            <b>Fórmula:</b> <code>(FCF / Acciones en circulación) / Precio × 100</code><br><br>
            Permite comparar la rentabilidad implícita de una acción frente a otras alternativas como bonos.
            Especialmente útil para detectar compresión de múltiplos y valoraciones exigentes.
          </td>
          <td>
            <span style='color:#2ecc71;'>▲ &gt; 5% — Valoración atractiva relativa al mercado.</span><br><br>
            <span style='color:#f39c12;'>◆ 2–5% — Razonable para empresas de calidad.</span><br><br>
            <span style='color:#ff4d4d;'>▼ &lt; 2% — Prima elevada. Poco margen de error.</span>
          </td>
        </tr>

        <tr style='background:#1a1a1a;'>
          <td><span class='g-title'>SBC</span><br><small style='color:#888;'>Stock Based Compensation</small></td>
          <td>
            Remuneración a empleados y directivos en forma de acciones u opciones en lugar de salario en efectivo.
            Aunque no supone salida de caja inmediata, diluye al accionista aumentando acciones en circulación.<br><br>
            El SBC aparece como gasto en la cuenta de resultados pero se suma de vuelta en el flujo operativo,
            lo que hace que muchas empresas presenten FCF inflado si no se ajusta correctamente.
            Un SBC elevado sin recompras equivale a pagar a los empleados con dinero del accionista.
          </td>
          <td>
            <span style='color:#2ecc71;'>▲ &lt; 10% del FCF — Dilución controlada y asumible.</span><br><br>
            <span style='color:#f39c12;'>◆ 10–20% del FCF — Moderado. Vigilar tendencia.</span><br><br>
            <span style='color:#ff4d4d;'>▼ &gt; 20% del FCF — Dilución significativa para el accionista.</span>
          </td>
        </tr>

        <tr>
          <td><span class='g-title'>Buybacks</span><br><small style='color:#888;'>Recompra de acciones propias</small></td>
          <td>
            La empresa utiliza su caja para recomprar acciones propias en el mercado, reduciéndolas de circulación.
            Aumenta el porcentaje de propiedad de cada accionista existente sin que este haga nada.<br><br>
            Es la forma más eficiente fiscalmente de retribuir al accionista frente al dividendo,
            y es especialmente potente cuando la acción cotiza por debajo de su valor intrínseco.
            En este monitor, su función principal es compensar o revertir la dilución generada por el SBC.
          </td>
          <td>
            <span style='color:#2ecc71;'>▲ Buybacks &gt; SBC — Acreción neta. El float se reduce.</span><br><br>
            <span style='color:#f39c12;'>◆ Buybacks ≈ SBC — Neutro. Solo compensa la dilución.</span><br><br>
            <span style='color:#ff4d4d;'>▼ Buybacks &lt; SBC — Dilución neta. Float creciente.</span>
          </td>
        </tr>

        <tr style='background:#1a1a1a;'>
          <td><span class='g-title'>SBC Neto / FCF</span><br><small style='color:#888;'>Dilución real ajustada</small></td>
          <td>
            Métrica central del monitor. Mide la dilución neta real del accionista después de descontar
            el efecto compensador de las recompras, expresada como porcentaje del FCF generado.<br><br>
            <b>Fórmula:</b> <code>(SBC − Buybacks) / FCF × 100</code><br><br>
            Un valor negativo significa que la empresa recompra más acciones de las que emite,
            generando acreción neta: cada acción representa una porción mayor del negocio con el tiempo.
            Es la forma más completa de medir el impacto real del SBC sobre el accionista.
          </td>
          <td>
            <span style='color:#2ecc71;'>▲ &lt; 0% — Acreción. Buybacks superan al SBC.</span><br><br>
            <span style='color:#f39c12;'>◆ 0–20% — Dilución moderada y gestionable.</span><br><br>
            <span style='color:#ff4d4d;'>▼ &gt; 20% — Dilución neta alta. Impacto relevante.</span>
          </td>
        </tr>

        <tr>
          <td>
            <span class='g-title'>Acreción + NRR &lt; 100%</span><br>
            <small style='color:#e67e22;'>⚠️ Señal de alerta combinada</small>
          </td>
          <td>
            Cuando una empresa combina acreción agresiva (SBC Neto / FCF &lt; -50%) con un NRR por debajo del 100%,
            la lectura del ratio por sí solo puede ser engañosa. Existen dos interpretaciones opuestas:<br><br>
            <b style='color:#2ecc71;'>Lectura optimista:</b> la dirección reconoce que no hay oportunidades de reinversión
            con retorno suficiente y devuelve el capital eficientemente. Si las recompras se realizan con la acción
            cotizando por debajo de su valor intrínseco, es la asignación de capital más eficiente posible
            y magnifica la participación del accionista a largo plazo.<br><br>
            <b style='color:#ff4d4d;'>Lectura pesimista:</b> el negocio no crece orgánicamente y las recompras
            masivas se usan para maquillar el EPS y disimular la debilidad operativa. Un NRR &lt; 100%
            indica que la base de clientes se contrae en valor — el crecimiento aparente en EPS viene
            de reducir el denominador, no de crear valor real. Este es el patrón histórico de empresas
            en declive estructural que usan el capital para sostener artificialmente la cotización.<br><br>
            <b>Referencia histórica:</b> IBM mantuvo durante años recompras masivas con negocio en contracción,
            generando la ilusión de crecimiento en EPS mientras el valor intrínseco se deterioraba.
            La clave diferenciadora es si el NRR muestra una tendencia de recuperación o de deterioro continuado.
          </td>
          <td>
            <span style='color:#2ecc71;'>✅ Acreción + NRR recuperándose — Señal positiva. Capital bien asignado.</span><br><br>
            <span style='color:#f39c12;'>◆ Acreción + NRR estable &lt; 100% — Vigilancia activa. Sin deterioro pero sin mejora.</span><br><br>
            <span style='color:#ff4d4d;'>🚨 Acreción agresiva + NRR en declive — Alerta máxima. Posible deterioro estructural enmascarado.</span><br><br>
            <small style='color:#888;'>En el monitor, los tickers con esta combinación aparecen marcados con 🚨 en el diagnóstico y borde naranja en el gráfico.</small>
          </td>
        </tr>

        <tr style='background:#1a1a1a;'>
          <td><span class='g-title'>T-G</span><br><small style='color:#888;'>Tesis-Goals</small></td>
          <td>
            Contador de hitos de la tesis de inversión cumplidos sobre el total definido.
            Cada inversor define sus propios criterios cualitativos o cuantitativos que debe cumplir
            la empresa para mantener la convicción en la posición (ej. expansión de márgenes,
            lanzamiento de producto, recuperación de NRR, crecimiento en nuevo segmento).<br><br>
            Funciona como semáforo de convicción: a medida que se cumplen los hitos, la tesis se valida.
            Si los hitos no se cumplen en el plazo esperado, es señal de revisión de la posición.
          </td>
          <td>
            <span style='color:#2ecc71;'>▲ 3–4 / 4 — Tesis en curso. Alta convicción.</span><br><br>
            <span style='color:#f39c12;'>◆ 2 / 4 — Tesis parcial. Seguimiento activo necesario.</span><br><br>
            <span style='color:#ff4d4d;'>▼ 0–1 / 4 — Tesis estancada. Revisar o cerrar posición.</span>
          </td>
        </tr>
      </tbody>
    """

    html = f"""<!DOCTYPE html>
<html lang='es'>
<head>
  <meta charset='UTF-8'>
  <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
  <style>
    body  {{ background:#121212; color:#e0e0e0; padding:25px; }}
    .card {{ background:#1e1e1e; border-radius:15px; padding:20px; margin-bottom:20px; border:none; }}
    h5    {{ color:#00d4ff; text-transform:uppercase; font-size:0.9rem; letter-spacing:1px; margin-bottom:15px; }}
    th    {{ color:#888; font-size:0.75rem; text-transform:uppercase; }}
    td    {{ vertical-align:middle !important; border-bottom:1px solid #2a2a2a !important; padding:12px !important; }}
    code  {{ background:#2a2a2a; color:#00d4ff; padding:2px 6px; border-radius:4px; font-size:0.8rem; }}
    .g-title        {{ color:#00d4ff; font-weight:bold; }}
    .badge-acrecion {{ background:#2ecc7133; color:#2ecc71; padding:2px 8px; border-radius:8px; font-size:0.75rem; }}
    .badge-dilucion {{ background:#ff4d4d33; color:#ff4d4d; padding:2px 8px; border-radius:8px; font-size:0.75rem; }}
  </style>
</head>
<body>
<div class='container' style='max-width:900px;'>
  <h2 class='mb-4'>🛡️ Monitor Estratégico <span style='color:#00d4ff;'>V1.6</span>
    <small style='font-size:0.6em;color:#888;'>— datos anualizados (4T) | ★ = dato incompleto | 🟠 = alerta NRR+Acreción</small>
  </h2>

  <div class='card text-center'>
    <img src='data:image/png;base64,{img_b64}' class='img-fluid' style='border-radius:10px;'>
  </div>

  <div class='card'>
    <h5>📊 Métricas Operativas</h5>
    <p style='color:#888;font-size:0.78rem;margin-bottom:10px;'>
      💡 Pasa el cursor sobre <b>SBC NETO</b> para ver valores absolutos y etiquetas usadas.
    </p>
    <table class='table table-dark mb-0'>
      <thead><tr><th>TKR</th><th>Precio</th><th>NRR</th><th>SBC NETO / FCF</th><th>FCF Yield</th><th class='text-center'>T-G</th></tr></thead>
      <tbody>{filas_m}</tbody>
    </table>
  </div>

  <div class='card'>
    <h5>📝 Diagnóstico de Tesis</h5>
    <table class='table table-dark mb-0'>
      <thead><tr><th>TKR</th><th>Diagnóstico</th><th>Valores Absolutos (TTM)</th></tr></thead>
      <tbody>{filas_d}</tbody>
    </table>
  </div>

  <div class='card'>
    <h5>🔍 Log de Calidad de Datos</h5>
    <p style='color:#888;font-size:0.78rem;margin-bottom:10px;'>
      Registro de etiquetas no encontradas, valores aproximados o errores de extracción.
    </p>
    <table class='table table-dark mb-0'>
      <thead><tr><th>Ticker</th><th>Métrica</th><th>Detalle</th></tr></thead>
      <tbody>{filas_w}</tbody>
    </table>
  </div>

  <div class='card'>
    <h5>📖 Glosario</h5>
    <table class='table table-dark mb-0' style='font-size:0.85rem;'>
      <thead>
        <tr><th style='width:180px;'>Métrica</th><th>Definición</th><th style='width:240px;'>Interpretación</th></tr>
      </thead>
      {glosario}
    </table>
  </div>

</div>
</body>
</html>"""

    resp = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendDocument",
        data={
            'chat_id': CHAT_ID,
            'caption': "📊 *Reporte V1.6 — Alerta NRR+Acreción + fix solapamiento trimestres*",
            'parse_mode': 'Markdown',
        },
        files={'document': ('Reporte_Growth_v1_6.html', html.encode('utf-8'), 'text/html')},
        timeout=15,
    )

    if resp.ok:
        print("✅ Reporte enviado correctamente.")
    else:
        print(f"❌ Error Telegram {resp.status_code}: {resp.text}")


if __name__ == "__main__":
    ejecutar_v1_6()
