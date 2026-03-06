import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
import os

"""
===============================================================================
ESTRATEGIA DE INVERSIÓN: GOLAR LNG (GLNG) - MONITOR DE TESIS Y CONTROL
===============================================================================
MANUAL OPERATIVO:
1. RUTINA: Ejecutar los viernes antes del cierre de NY (21:00h España).
2. GESTIÓN: Si el script ordena 'DOBLAR', cambiar posicion_pct de 0.01 a 0.02.
3. COSECHA: Solo vender si el precio rompe la SMA 30 tras alcanzar los $55.50.
===============================================================================
"""

# --- CONFIGURACIÓN DE TELEGRAM ---
TELEGRAM_TOKEN = "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4"   
TELEGRAM_CHAT_ID = "8351044609"  

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

def enviar_alerta_telegram(mensaje, ruta_grafico=None):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url_base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
            # 1. Enviar el informe de texto
            requests.post(f"{url_base}/sendMessage", 
                          data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}, 
                          timeout=10)
            
            # 2. Enviar el gráfico si existe
            if ruta_grafico and os.path.exists(ruta_grafico):
                with open(ruta_grafico, 'rb') as foto:
                    requests.post(f"{url_base}/sendPhoto", 
                                  data={"chat_id": TELEGRAM_CHAT_ID}, 
                                  files={'photo': foto}, 
                                  timeout=15)
                print("✅ Gráfico enviado con éxito a Telegram.")
        except Exception as e:
            print(f"⚠️ Error enviando a Telegram: {e}")

def monitor_tesis_pro():
    try:
        glng_ticker = yf.Ticker("GLNG")
        glng_actual = glng_ticker.fast_info['last_price']
        hist_data = yf.download(["GLNG", "LNGX", "JKM=F"], period="45d", progress=False)['Close']
        sma_30 = hist_data['GLNG'].rolling(window=30).mean().iloc[-1].item()
        eur_usd = yf.download("EURUSD=X", period="1d", progress=False)['Close'].iloc[-1].item()
        jkm_actual = hist_data['JKM=F'].dropna().iloc[-1].item()
        lngx_actual = hist_data['LNGX'].dropna().iloc[-1].item()
    except Exception as e:
        print(f"🔴 ERROR CRÍTICO: {e}"); return

    inv_eur = cartera_total_eur * posicion_pct
    acciones = round((inv_eur * eur_usd) / precio_entrada_usd)
    pnl_eur = (acciones * (glng_actual - precio_entrada_usd)) / eur_usd

    # 1. GENERACIÓN DEL GRÁFICO (AHORA SE HACE PRIMERO)
    print("\nGenerando comparativa visual...")
    plot_data = hist_data.tail(30).dropna()
    relativa = (plot_data / plot_data.iloc[0]) * 100
    plt.figure(figsize=(12, 6))
    plt.plot(relativa['GLNG'], label='GLNG', color='#1f77b4', linewidth=2.5)
    plt.plot(relativa['LNGX'], label='Sector', color='#7f7f7f', linestyle='--')
    plt.axhline(100, color='black', linewidth=0.8)
    plt.title('Fuerza Relativa (Últimos 30 días)')
    plt.legend(loc='upper left')
    plt.savefig('grafico_golar.png', bbox_inches='tight') # <--- GUARDAR EN DISCO
    plt.close() # Cerrar proceso de imagen

    # 2. ESCENARIOS DE ACTUACIÓN
    msg_telegram = f"📊 *MONITOR GLNG*\nPrecio Actual: ${glng_actual:.2f}\nPNL: {pnl_eur:+.2f}€\n"
    
    if glng_actual >= objetivo_final_usd:
        res = "🎯 OBJETIVO ALCANZADO. VENDER."; msg_telegram += res
    elif glng_actual >= stop_loss_profit_usd:
        msg_h = f"🛡️ FASE DE COSECHA (SMA 30: ${sma_30:.2f})"
        res = f"{msg_h}\n>>> ACCIÓN: VENDER" if glng_actual < sma_30 else f"{msg_h}\n>>> ACCIÓN: MANTENER"
        msg_telegram += res
    elif glng_actual <= stop_loss_usd:
        res = "🚨 STOP LOSS. VENDER."; msg_telegram += res
    elif glng_actual >= punto_doblar_usd and jkm_actual > umbral_jkm_extra:
        res = "🚀 AMPLIACIÓN (2%). COMPRAR."; msg_telegram += res
    else:
        dist_p = stop_loss_profit_usd - glng_actual
        res = f"🟢 MANTENER. Zona segura (Profit a ${dist_p:.2f})"; msg_telegram += res

    # 3. ENVÍO FINAL
    print(res)
    enviar_alerta_telegram(msg_telegram, ruta_grafico='grafico_golar.png')

if __name__ == "__main__":
    monitor_tesis_pro()
