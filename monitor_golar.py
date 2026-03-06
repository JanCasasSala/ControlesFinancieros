import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
import os

# --- CONFIGURACIÓN DE TELEGRAM (RELLENAR) ---
TELEGRAM_TOKEN = "TU_TOKEN_AQUÍ"   
TELEGRAM_CHAT_ID = "TU_ID_AQUÍ"  

# --- VARIABLES DE CARTERA (300.000€) ---
cartera_total_eur = 300000
posicion_pct = 0.01  

# --- PARÁMETROS DE LA TESIS GOLAR ---
precio_entrada_usd = 46.25
stop_loss_usd = 42.10
punto_doblar_usd = 48.50
stop_loss_profit_usd = 55.50  
objetivo_final_usd = 68.00    
umbral_jkm_extra = 8.00       

def enviar_telegram(texto, ruta_foto=None):
    """Envío independiente de texto y foto para máxima fiabilidad"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    base_url = f"https://api.telegram.org{TELEGRAM_TOKEN}"
    
    # 1. Intentar enviar TEXTO siempre
    try:
        requests.post(f"{base_url}/sendMessage", 
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": texto, "parse_mode": "Markdown"}, 
                      timeout=15)
        print("✅ Texto enviado a Telegram.")
    except Exception as e:
        print(f"❌ Fallo envío texto: {e}")

    # 2. Intentar enviar FOTO solo si existe
    if ruta_foto and os.path.exists(ruta_foto):
        try:
            with open(ruta_foto, 'rb') as f:
                requests.post(f"{base_url}/sendPhoto", 
                              data={"chat_id": TELEGRAM_CHAT_ID}, 
                              files={"photo": f}, 
                              timeout=20)
            print("✅ Gráfico enviado a Telegram.")
        except Exception as e:
            print(f"❌ Fallo envío gráfico: {e}")

def monitor_tesis_pro():
    try:
        # 1. OBTENCIÓN DE DATOS
        glng_ticker = yf.Ticker("GLNG")
        glng_actual = glng_ticker.fast_info['last_price']
        
        hist_data = yf.download(["GLNG", "LNGX", "JKM=F"], period="45d", progress=False)['Close']
        sma_30 = hist_data['GLNG'].rolling(window=30).mean().iloc[-1].item()
        
        feeds = yf.download(["EURUSD=X"], period="1d", interval="1m", progress=False)['Close']
        eur_usd = feeds.dropna().iloc[-1].item() if not feeds.empty else 1.05
        jkm_actual = hist_data['JKM=F'].dropna().iloc[-1].item()

    except Exception as e:
        print(f"🔴 ERROR DATOS: {e}"); return

    # 2. CÁLCULOS
    inv_eur = cartera_total_eur * posicion_pct
    acciones = round((inv_eur * eur_usd) / precio_entrada_usd)
    pnl_eur = (acciones * (glng_actual - precio_entrada_usd)) / eur_usd

    # 3. ESCENARIOS (Meticulosidad en Márgenes)
    dist_stop = glng_actual - stop_loss_usd
    dist_profit = stop_loss_profit_usd - glng_actual
    
    if glng_actual >= objetivo_final_usd:
        res = "🎯 *OBJETIVO ALCANZADO*. VENDER."
    elif glng_actual >= stop_loss_profit_usd:
        res = f"🛡️ *COSECHA*. {'VENDER (Bajo SMA 30)' if glng_actual < sma_30 else 'MANTENER'}"
    elif glng_actual <= stop_loss_usd:
        res = "🚨 *STOP LOSS*. VENDER."
    elif glng_actual >= punto_doblar_usd and jkm_actual > umbral_jkm_extra:
        res = "🚀 *AMPLIAR AL 2%*. COMPRAR."
    else:
        res = f"🟢 *MANTENER*. Margen Stop: ${dist_stop:.2f} | Profit: ${dist_profit:.2f}"

    # 4. GENERAR GRÁFICO (ANTES del envío)
    ruta_img = "grafico_golar.png"
    try:
        plt.figure(figsize=(10, 5))
        plot_data = hist_data.tail(30).dropna()
        relativa = (plot_data / plot_data.iloc[0]) * 100
        plt.plot(relativa['GLNG'], label='GLNG', color='blue', linewidth=2)
        plt.plot(relativa['LNGX'], label='Sector', color='gray', linestyle='--')
        plt.axhline(100, color='black', linewidth=0.5)
        plt.legend(); plt.grid(True, alpha=0.3)
        plt.savefig(ruta_img, bbox_inches='tight')
        plt.close()
    except:
        ruta_img = None # Si falla el gráfico, enviamos solo texto

    # 5. INFORME FINAL
    informe = (f"📊 *MONITOR GLNG*\n"
               f"Precio: ${glng_actual:.2f}\n"
               f"JKM: ${jkm_actual:.2f}\n"
               f"PNL: {pnl_eur:+.2f}€\n\n"
               f"{res}")
    
    print(informe)
    enviar_telegram(informe, ruta_img)

if __name__ == "__main__":
    monitor_tesis_pro()
