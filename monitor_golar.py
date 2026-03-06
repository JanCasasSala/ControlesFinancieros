import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
import os # Import the os module for path operations

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

# --- CONFIGURACIÓN DE TELEGRAM (Opcional) ---
TELEGRAM_TOKEN = ""   
TELEGRAM_CHAT_ID = ""  

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
    """Envío de texto y adjunto de imagen del gráfico al móvil"""
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            # 1. Enviar el informe de texto
            url_txt = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
            requests.post(url_txt, data=payload, timeout=10)
            
            # 2. Enviar el gráfico si existe el archivo
            if ruta_grafico and os.path.exists(ruta_grafico):
                url_img = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
                with open(ruta_grafico, 'rb') as foto:
                    files = {'photo': foto}
                    data = {'chat_id': TELEGRAM_CHAT_ID}
                    requests.post(url_img, data=data, files=files, timeout=15)
                print("✅ Gráfico enviado con éxito a Telegram.")
        except Exception as e:
            print(f"⚠️ Error enviando a Telegram: {e}")

def monitor_tesis_pro():
    try:
        # 1. OBTENCIÓN DE DATOS (Meticulosidad en la descarga)
        glng_ticker = yf.Ticker("GLNG")
        glng_actual = glng_ticker.fast_info['last_price']
        
        hist_data = yf.download(["GLNG", "LNGX", "JKM=F"], period="45d", progress=False)['Close']
        if hist_data.empty: raise ValueError("Error: Datos históricos no disponibles.")

        sma_30 = hist_data['GLNG'].rolling(window=30).mean().iloc[-1].item()
        
        feeds = yf.download(["EURUSD=X"], period="1d", interval="1m", progress=False)['Close']
        eur_usd = feeds.dropna().iloc[-1].item() if not feeds.empty else 1.05
        
        jkm_actual = hist_data['JKM=F'].dropna().iloc[-1].item()
        lngx_actual = hist_data['LNGX'].dropna().iloc[-1].item()

    except Exception as e:
        print(f"🔴 ERROR CRÍTICO: {e}")
        return

    # 2. CÁLCULOS DE POSICIÓN
    inv_eur = cartera_total_eur * posicion_pct
    acciones = round((inv_eur * eur_usd) / precio_entrada_usd)
    pnl_eur = (acciones * (glng_actual - precio_entrada_usd)) / eur_usd
    rendimiento_glng = (glng_actual / precio_entrada_usd - 1) * 100

    print(f"--- REVISIÓN DETALLADA DE TESIS (GLNG) ---")
    print(f"COTIZACIÓN ACTUAL: ${glng_actual:.2f} | JKM: ${jkm_actual:.2f} | ETF LNGX: ${lngx_actual:.2f}")
    print(f"ESTADO CUENTA: {acciones} títulos | P&L: {pnl_eur:+.2f}€ | Rendimiento: {rendimiento_glng:+.2f}%")
    print("-" * 70)

    # 3. ESCENARIOS DE ACTUACIÓN CON REPORTE DE PRECIO ACTUAL
    msg_telegram = f"📊 *MONITOR GLNG*\nPrecio Actual: ${glng_actual:.2f}\nPNL: {pnl_eur:+.2f}€\n"
    
    if glng_actual >= objetivo_final_usd:
        salida_texto = (f"🎯 ESCENARIO: OBJETIVO FINAL ALCANZADO\n"
                        f"   Cotización Actual: ${glng_actual:.2f} >= Objetivo: ${objetivo_final_usd:.2f}\n"
                        f">>> ACCIÓN: VENDER TODO (Valor intrínseco completado).")
        msg_telegram += f"🎯 *OBJETIVO ALCANZADO*: VENDER TODO."

    elif glng_actual >= stop_loss_profit_usd:
        msg_harvest = f"🛡️ ESCENARIO: FASE DE COSECHA (SMA 30: ${sma_30:.2f})"
        if glng_actual < sma_30:
            salida_texto = (f"{msg_harvest}\n"
                            f"   Cotización Actual: ${glng_actual:.2f} < Soporte SMA 30: ${sma_30:.2f}\n"
                            f">>> ACCIÓN: VENDER (Rotura de tendencia confirmada).")
            msg_telegram += f"🛡️ *COSECHA - VENDER*: Rotura SMA 30."
        else:
            salida_texto = (f"{msg_harvest}\n"
                            f"   Cotización Actual: ${glng_actual:.2f} >= Soporte SMA 30: ${sma_30:.2f}\n"
                            f">>> ACCIÓN: MANTENER (La tendencia sigue alcista).")
            msg_telegram += f"🛡️ *COSECHA - MANTENER*: Sobre SMA 30."

    elif glng_actual <= stop_loss_usd:
        salida_texto = (f"🚨 ESCENARIO: STOP LOSS\n"
                        f"   Cotización Actual: ${glng_actual:.2f} <= Límite Stop: ${stop_loss_usd:.2f}\n"
                        f">>> ACCIÓN: VENDER TODO (Protección de capital).")
        msg_telegram += f"🚨 *STOP LOSS*: ${glng_actual:.2f}. VENDER."

    elif glng_actual >= punto_doblar_usd:
        msg_ampliar = f"🚀 ESCENARIO: SEÑAL DE AMPLIACIÓN (Doblar al 2%)"
        if jkm_actual > umbral_jkm_extra:
            salida_texto = (f"{msg_ampliar}\n"
                            f"   Cotización Actual: ${glng_actual:.2f} | Molécula JKM: ${jkm_actual:.2f}\n"
                            f">>> ACCIÓN: DOBLAR. Invertir otros {cartera_total_eur*0.01:,.0f}€.")
            msg_telegram += f"🚀 *AMPLIAR AL 2%*: Gas validado (${jkm_actual:.2f})."
        else:
            salida_texto = (f"{msg_ampliar}\n"
                            f"   Cotización Actual: ${glng_actual:.2f} | Molécula JKM: ${jkm_actual:.2f} (Baja)\n"
                            f">>> ACCIÓN: MANTENER 1%. Falta soporte fundamental del gas.")
            msg_telegram += "🟡 *MANTENER 1%*: Gas débil."

    else:
        dist_stop = glng_actual - stop_loss_usd
        dist_profit = stop_loss_profit_usd - glng_actual
        salida_texto = (f"🟢 ESCENARIO: MANTENER POSICIÓN ACTUAL\n"
                        f"   Cotización Actual:    ${glng_actual:.2f}\n"
                        f"   Margen a Stop Loss:   ${dist_stop:.2f} (Soporte: ${stop_loss_usd:.2f})\n"
                        f"   Margen a Stop Profit: ${dist_profit:.2f} (Activación: ${stop_loss_profit_usd:.2f})\n"
                        f">>> ACCIÓN: MANTENER. Tesis en curso sin cambios.")
        msg_telegram += f"🟢 *MANTENER*: Zona segura (Profit a ${dist_profit:.2f})."

    # Impresión y envío
    print(salida_texto)
    enviar_alerta_telegram(msg_telegram, ruta_grafico='grafico_golar.png')

    # 4. GRÁFICO DE FUERZA RELATIVA (Base 100)
    print("\nGenerando comparativa visual (Base 100)...")
    plot_data = hist_data.tail(30).dropna()
    relativa = (plot_data / plot_data.iloc[0]) * 100
    
    plt.figure(figsize=(12, 6))
    plt.plot(relativa['GLNG'], label='Golar LNG (GLNG)', color='#1f77b4', linewidth=2.5)
    plt.plot(relativa['LNGX'], label='Sector Gas (ETF LNGX)', color='#7f7f7f', linestyle='--')
    plt.plot(relativa['JKM=F'], label='Molécula Gas (JKM)', color='#2ca02c', alpha=0.6)
    plt.axhline(100, color='black', linewidth=0.8)
    plt.title('Monitor de Fuerza Relativa (Últimos 30 días)')
    plt.legend(loc='upper left'); plt.grid(True, alpha=0.2); plt.show()

if __name__ == "__main__":
    monitor_tesis_pro()
