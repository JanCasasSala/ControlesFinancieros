import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import requests
import os

# --- FICHA TÉCNICA: VERSIÓN 3.0 (BLINDADA) ---
# Lógica: SMA 100 (Fondo) + Regla 3 Días + Diferencial Sectorial (-5%)
# Objetivo: Gestión de peso con alta tolerancia al ruido.

TELEGRAM_TOKEN = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
TELEGRAM_CHAT_ID = "8351044609"
PRECIO_ENTRADA_SAN = 3.85

def ejecutar_monitor_san():
    plt.style.use('dark_background')
    try:
        # 1. DESCARGA
        tickers = ["SAN.MC", "EXX7.DE", "^IBEX"]
        df_raw = yf.download(tickers, period="250d", progress=False, auto_adjust=True)
        df = df_raw['Close'].ffill()
        
        san = df['SAN.MC'].iloc[-1]
        sma_30 = df['SAN.MC'].rolling(window=30).mean().iloc[-1]
        sma_100_serie = df['SAN.MC'].rolling(window=100).mean()
        sma_100_v = sma_100_serie.iloc[-1]
        
        # 2. MÉTRICAS DE CONFIRMACIÓN (REGLA DE 3 DÍAS Y DIFERENCIAL)
        confirm_3d = (df['SAN.MC'].tail(3) < sma_100_serie.tail(3)).all()
        dif_10d = (df['SAN.MC'].pct_change(10).iloc[-1] - df['EXX7.DE'].pct_change(10).iloc[-1]) * 100

        # 3. LÓGICA ESTRATÉGICA (ESTABILIZADA)
        if san > sma_30:
            estado, esc = "🟢 MANTENER", "🚀 IMPULSO: Tendencia sólida."
        elif sma_100_v < san <= sma_30:
            estado, esc = "🟡 VIGILAR", "🌬️ RESPIRACIÓN: Soporte de fondo aguantando."
        else:
            # FILTRO DE PACIENCIA: Solo REDUCIR si hay 3 días de cierre bajo y debilidad real
            if confirm_3d and dif_10d < -5:
                estado, esc = "❌ REDUCIR PESO", "🚨 GIRO CONFIRMADO: Debilidad estructural profunda."
            else:
                estado, esc = "🟡 VIGILAR / RUIDO", "⚠️ RUIDO: Perdiendo SMA 100 pero alineado con Europa o sin confirmación 3d."

        # 4. GRÁFICO PROFESIONAL
        plot_data = df.tail(90)
        base_san = plot_data['SAN.MC'].iloc[0]
        rel = (plot_data / plot_data.iloc[0]) * 100
        sma_100_rel = (sma_100_serie.tail(90) / base_san) * 100
        
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(rel['SAN.MC'], label='SANTANDER', color='red', linewidth=3)
        ax.plot(rel['EXX7.DE'], label='Sector EU', color='yellow', alpha=0.5)
        ax.plot(sma_100_rel, label='Fondo (SMA 100)', color='orange', linestyle='--')
        ax.axhline(100, color='white', alpha=0.2)
        ax.set_title(f"SAN: {san:.2f}€ - {estado}", fontsize=14)
        ax.legend(loc='upper left')
        
        ruta_img = "monitor_san.png"
        plt.savefig(ruta_img)
        plt.close()

        # 5. INFORME
        informe = (f"🏦 *MONITOR ESTRATÉGICO SAN*\n"
                   f"------------------------------------\n"
                   f"💎 PRECIO: {san:.2f}€\n"
                   f"🔥 DIF. SECTORIAL: {dif_10d:+.2f}%\n"
                   f"📢 ESCENARIO: {esc}\n"
                   f"✅ ESTADO: {estado}\n"
                   f"------------------------------------\n"
                   f"📌 Filtro: Confirmación 3 días + Diferencial -5%.")
        
        url = f"https://api.telegram.org{TELEGRAM_TOKEN}/"
        requests.post(url + "sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": informe, "parse_mode": "Markdown"})
        if os.path.exists(ruta_img):
            with open(ruta_img, 'rb') as f:
                requests.post(url + "sendPhoto", data={"chat_id": TELEGRAM_CHAT_ID}, files={"photo": f})

    except Exception as e:
        print(f"🔴 Error: {e}")

if __name__ == "__main__":
    ejecutar_monitor_san()
