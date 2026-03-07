import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use('Agg') # Esto evita el error en GitHub
import matplotlib.pyplot as plt
import requests

# --- CONFIGURACIÓN ---
TOKEN = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"
CHAT_ID = "8351044609"
ENTRADA = 3.85

try:
    # 1. DATOS (Usamos EXX7.DE para el sector europeo)
    tickers = ["SAN.MC", "EXX7.DE", "^IBEX"]
    df = yf.download(tickers, period="250d", progress=False, auto_adjust=True)['Close'].ffill()
    
    san = df['SAN.MC'].iloc[-1]
    sma_100 = df['SAN.MC'].rolling(window=100).mean().iloc[-1]
    sma_30 = df['SAN.MC'].rolling(window=30).mean().iloc[-1]
    
    # 2. LÓGICA DE ESTADO
    dif_10d = (df['SAN.MC'].pct_change(10).iloc[-1] - df['EXX7.DE'].pct_change(10).iloc[-1]) * 100
    
    if san > sma_30:
        res, esc = "🟢 MANTENER", "Impulso alcista fuerte."
    elif sma_100 < san <= sma_30:
        res, esc = "🟡 VIGILAR", "Corrección sana de fondo."
    else:
        res, esc = "❌ REDUCIR", "Pérdida de soporte estructural."

    # 3. GRÁFICO
    plot_data = df.tail(90)
    rel = (plot_data / plot_data.iloc[0]) * 100
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(rel['SAN.MC'], label='SANTANDER', color='red', linewidth=3)
    ax.plot(rel['EXX7.DE'], label='Sector Bancos EU', color='yellow', alpha=0.5)
    ax.axhline(100, color='white', alpha=0.2)
    ax.set_title(f"SAN: {san:.2f}€ - {res}")
    ax.legend()
    
    img = "monitor_san.png"
    plt.savefig(img)
    
    # 4. ENVÍO
    msg = f"🏦 *MONITOR SAN*\nPrecio: {san:.2f}€\nEstado: {res}\nInfo: {esc}"
    url = f"https://api.telegram.org/bot{TOKEN}/"
    requests.post(url + "sendMessage", data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    with open(img, 'rb') as f:
        requests.post(url + "sendPhoto", data={"chat_id": CHAT_ID}, files={"photo": f})

except Exception as e:
    print(f"Error: {e}")
