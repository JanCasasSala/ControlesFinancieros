import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import requests
import io
from tabulate import tabulate

# =============================================================================
# 1. CONFIGURACIÓN ESTRATÉGICA Y TELEGRAM
# =============================================================================
TOKEN = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID = "8351044609"

def enviar_a_telegram(mensaje, imagen=None):
    url_base = f"https://api.telegram.org/bot{TOKEN}"
    try:
        if imagen:
            requests.post(f"{url_base}/sendPhoto", data={"chat_id": CHAT_ID, "caption": mensaje, "parse_mode": "Markdown"}, files={"photo": imagen})
        else:
            requests.post(f"{url_base}/sendMessage", data={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})
    except Exception as e: print(f"❌ Error Telegram: {e}")

def ejecutar_monitor_v1_growth():
    # TESIS TRIMESTRAL (Incluyendo Gartner y FactSet)
    TESIS_QUARTERLY = {
        "ADBE": {"nrr": 111.0, "mgn": 89.3, "t_g": 0, "color": "#2ecc71"},
        "IT":   {"nrr": 105.0, "mgn": 68.0, "t_g": 0, "color": "#9b59b6"}, # Gartner
        "FDS":  {"nrr": 101.0, "mgn": 53.0, "t_g": 0, "color": "#34495e"}, # FactSet
        "CRM":  {"nrr": 108.5, "mgn": 76.5, "t_g": 0, "color": "#3498db"},
        "PYPL": {"nrr": 98.2,  "mgn": 41.5, "t_g": 1, "color": "#e67e22"}
    }

    tickers = list(TESIS_QUARTERLY.keys())
    data_points = []

    print("🚀 Sincronizando métricas...")
    
    for tk in tickers:
        try:
            asset = yf.Ticker(tk)
            info = asset.info
            
            price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
            bpa = info.get('trailingEps', 0)
            fcf_total = info.get('freeCashflow', 0)
            shares = info.get('sharesOutstanding') or 1
            sbc_total = info.get('stockBasedCompensation', 0)
            
            fcf_per_share = fcf_total / shares
            sbc_intensity = (sbc_total / fcf_total * 100) if fcf_total > 0 else 0
            fcf_yield = (fcf_per_share / price * 100) if price > 0 else 0
            
            nrr = TESIS_QUARTERLY[tk]["nrr"]
            diag = []
            if nrr < 100: diag.append(f"⚠️ NRR {nrr}%")
            else: diag.append(f"✅ NRR {nrr}%")
            if sbc_intensity > 20: diag.append(f"🚨 Dilución ({sbc_intensity:.1f}%)")
            if fcf_per_share > bpa: diag.append("💎 Caja > BPA")

            data_points.append({
                "TKR": tk, "PRECIO": f"${price:.2f}", "NRR": nrr, 
                "FCF/ACC": f"${fcf_per_share:.2f}", "BPA": f"${bpa:.2f}",
                "SBC/FCF": f"{sbc_intensity:.1f}%", "YIELD": fcf_yield,
                "STATUS": "🟢 OK" if nrr >= 100 and sbc_intensity <= 20 else "⚠️ VIGIL.",
                "T-G": f"{TESIS_QUARTERLY[tk]['t_g']}/4",
                "DIAGNÓSTICO": " | ".join(diag), "color": TESIS_QUARTERLY[tk]["color"]
            })
        except Exception as e: print(f"❌ Error en {tk}: {e}")

    # =============================================================================
    # 2. GENERACIÓN VISUAL
    # =============================================================================
    plt.figure(figsize=(10, 6))
    ax = plt.gca()
    ax.add_patch(patches.Rectangle((100, 0), 20, 20, color='green', alpha=0.05))
    ax.add_patch(patches.Rectangle((85, 0), 15, 20, color='blue', alpha=0.05))
    ax.add_patch(patches.Rectangle((100, 20), 20, 20, color='orange', alpha=0.05))
    ax.add_patch(patches.Rectangle((85, 20), 15, 20, color='red', alpha=0.05))

    for p in data_points:
        sbc_val = float(p["SBC/FCF"].replace('%',''))
        plt.scatter(p["NRR"], sbc_val, s=p["YIELD"]*300, 
                    color=p["color"], alpha=0.7, edgecolors='black', linewidth=1.5)
        plt.text(p["NRR"], sbc_val + 1.2, p["TKR"], fontweight='bold', ha='center', fontsize=10)

    plt.xlim(85, 120); plt.ylim(0, 40)
    plt.axvline(100, color='red', linestyle='--', linewidth=2, alpha=0.4)
    plt.axhline(20, color='grey', linestyle='--', linewidth=2, alpha=0.4)
    plt.title("MAPA DE DECISIÓN: CLUSTER 2 (GROWTH)\n(Burbuja grande = Mayor FCF Yield)", pad=20, fontsize=13)
    plt.grid(True, linestyle=':', alpha=0.4)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)

    # =============================================================================
    # 3. OUTPUT TABULAR Y ENVÍO (Incluye Glosario en pie)
    # =============================================================================
    df = pd.DataFrame(data_points)
    tabla_txt = tabulate(df[["TKR", "PRECIO", "NRR", "FCF/ACC", "BPA", "SBC/FCF", "STATUS", "T-G"]], 
                         headers='keys', tablefmt='simple', showindex=False)
    
    notas_txt = "\n".join([f"• *{r['TKR']}*: {r['DIAGNÓSTICO']}" for _, r in df.iterrows()])
    
    glosario_txt = (
        "\n" + "="*30 +
        "\n📖 *Glosario:*"
        "\n• *NRR*:  Retencion Ingresos Netos  "
        "\n•         Ing.Recurrentes Clientes  "  
        "\n•         >100% IA Ok. <100% Alerta."
        "\n• *FCF/ACC*: Caja Real (Anti-dilución)."
        "\n• *SBC % FCF*: Pago en acciones. >20% Alerta."
        "\n• *T-GRACIA*: Plazo 4 trimestres antes de salir."
        "\n" + "="*30
    )

    mensaje_final = f"🛡️ *Cluster 2 Growth*\n\n```\n{tabla_txt}\n```\n📝 *Diagnostico:*\n{notas_txt}\n{glosario_txt}"

    enviar_a_telegram(mensaje_final, buf)
    print("✅ Reporte enviado con Gartner, FactSet y Glosario.")

if __name__ == "__main__":
    ejecutar_monitor_v1_growth()
