import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
from tabulate import tabulate

# =============================================================================
# CONFIGURACIÓN ESTABLE (AUTOCONTENIDO)
# =============================================================================
NUCLEO_DATA = [
    {"tk": "SAN.MC", "cant": 6149, "cp": 2.43, "div": 0.24, "bb": 2.6}, 
    {"tk": "ITX.MC", "cant": 520,  "cp": 19.20, "div": 1.90, "bb": 0.0}, 
    {"tk": "LOG.MC", "cant": 1070, "cp": 16.89, "div": 2.10, "bb": 0.0}
]

TOKEN = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID = "8351044609"
BONO_REF = 3.40 

def ejecutar_monitor():
    try:
        # 2. DESCARGA DE DATOS
        tickers = [item["tk"] for item in NUCLEO_DATA]
        df_raw = yf.download(tickers, period="250d", progress=False, auto_adjust=True)
        df_prices = df_raw['Close'].ffill()

        data_estr, data_patr, plot_data = [], [], []
        t_inv, t_mkt = 0, 0

        # 3. CÁLCULOS
        for item in NUCLEO_DATA:
            pa = df_prices[item["tk"]].iloc[-1]
            ic, ia = item["cant"] * item["cp"], item["cant"] * pa
            t_inv += ic; t_mkt += ia
            
            y_mkt = (item["div"] / pa) * 100
            y_tot = y_mkt + item["bb"]
            y_cst = (item["div"] / item["cp"]) * 100
            gap = y_tot - BONO_REF
            
            sma_100 = df_prices[item["tk"]].rolling(100).mean().iloc[-1]
            est = "🟢" if pa > sma_100 and gap >= 0 else "⚠️" if gap < 0 else "🟡"
            
            data_estr.append([item["tk"][:3], f"{pa:.2f}", f"{y_tot:.1f}%", f"{y_cst:.1f}%", f"{gap:+.1f}%", est])
            data_patr.append([item["tk"][:3], f"{int(ic):,}", f"{int(ia):,}", f"{ia-ic:+,.0f}", f"{((ia-ic)/ic)*100:.1f}%"])
            plot_data.append({"tk": item["tk"][:3], "gap": gap, "pnl": ((ia-ic)/ic)*100, "peso": (ia/t_mkt)})

        # 4. TABLAS Y LEYENDA
        tabla_e = tabulate(data_estr, headers=["TKR", "PRECIO", "Y-TOT", "Y-CST", "GAP", "ST"], tablefmt="simple")
        tabla_p = tabulate(data_patr, headers=["TKR", "COST", "MKT", "DIF €", "%P&L"], tablefmt="simple")

        leyenda = (f"💡 *GUÍA:* `Y-TOT`: Sueldo mercado | `Y-CST`: Sueldo s/compra.\n"
                   f"GAP: vs Bono {BONO_REF}%. | EST: 🟢 OK | 🟡 AIRE | ⚠️ COS (Caro).")

        informe = (f"🛡️ *NÚCLEO: ESTRATEGIA*\n```\n{tabla_e}```\n{leyenda}\n\n"
                   f"💰 *NÚCLEO: PATRIMONIO*\n```\n{tabla_p}\n"
                   f"{'-'*35}\nTOT: {int(t_inv):,}€ | {int(t_mkt):,}€ | {t_mkt-t_inv:+,.0f}€\n```")

        # 5. GRÁFICO (BURBUJAS GIGANTES)
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(10, 6), facecolor='#1e1e1e')
        ax.set_facecolor('#1e1e1e')
        for d in plot_data:
            color = "#27ae60" if d["gap"] >= 0 else "#e67e22"
            ax.scatter(d["gap"], d["pnl"], s=d["peso"]*15000, alpha=0.7, color=color, edgecolors='white', linewidth=1.5)
            ax.text(d["gap"], d["pnl"], f"{d['tk']}\n{d['gap']:+.1f}%", ha='center', va='center', fontweight='bold', color='white', fontsize=9)

        ax.axvline(0, color="#e74c3c", linestyle='--', alpha=0.6)
        ax.set_title("RADAR DE COSECHA: PESO vs GAP vs ÉXITO", pad=20, fontsize=14)
        plt.savefig("radar_plot.png", bbox_inches='tight')

        # 6. ENVÍO A TELEGRAM
        url_base = f"https://api.telegram.org/bot{TOKEN}"
        requests.post(f"{url_base}/sendMessage", data={"chat_id": CHAT_ID, "text": informe, "parse_mode": "Markdown"})
        with open("radar_plot.png", 'rb') as f:
            requests.post(f"{url_base}/sendPhoto", data={"chat_id": CHAT_ID}, files={"photo": f})

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    ejecutar_monitor()
