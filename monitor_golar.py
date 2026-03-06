import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
import os

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
            url_base = f"https://api.telegram.org{TELEGRAM_TOKEN}"
            requests.post(f"{url_base}/sendMessage", 
                          data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}, 
                          timeout=10)
            if ruta_grafico and os.path.exists(ruta_grafico):
                with open(ruta_grafico, 'rb') as foto:
                    requests.post(f"{url_base}/sendPhoto", 
                                  data={"chat_id": TELEGRAM_CHAT_ID}, 
                                  files={'photo': foto}, 
                                  timeout=15)
        except Exception as e:
            print(f"⚠️ Error Telegram: {e}")

def monitor_tesis_pro():
    try:
        # 1. DESCARGA DE DATOS
        tickers = ["GLNG", "LNGX", "JKM=F", "EURUSD=X"]
        df_raw = yf.download(tickers, period="60d", progress=False)['Close'].ffill()
        
        if df_raw['GLNG'].empty:
            raise ValueError("Datos no disponibles")

        glng_actual = df_raw['GLNG'].iloc[-1]
        jkm_actual = df_raw['JKM=F'].iloc[-1]
        lngx_actual = df_raw['LNGX'].iloc[-1]
        eur_usd = df_raw['EURUSD=X'].iloc[-1]
        
        sma_30_serie = df_raw['GLNG'].rolling(window=30).mean()
        sma_30_valor = sma_30_serie.iloc[-1]

        # 2. CÁLCULOS FINANCIEROS (USD % - CORREGIDO SEGÚN SOLICITUD)
        pnl_pct_usd = ((glng_actual - precio_entrada_usd) / precio_entrada_usd) * 100

        # 3. ESCENARIO
        if jkm_actual > umbral_jkm_extra and glng_actual > precio_entrada_usd:
            escenario_texto = "🌬️ *VIENTO DE COLA*: Todo sube. Motor y precio acompañan."
        elif jkm_actual > umbral_jkm_extra and glng_actual <= precio_entrada_usd:
            escenario_texto = "🛡️ *EL REFUGIO*: Sector sufre pero la molécula es cara."
        elif jkm_actual <= umbral_jkm_extra and glng_actual > precio_entrada_usd:
            escenario_texto = "⚠️ *LA TRAMPA*: Subida por inercia. Motor (JKM) débil."
        else:
            escenario_texto = "📉 *ZONA NEUTRA*: Esperando catalizadores."

        # 4. ESTADO OPERATIVO
        if glng_actual >= objetivo_final_usd:
            res = "🎯 *OBJETIVO ALCANZADO*. VENDER."
        elif glng_actual >= stop_loss_profit_usd:
            res = f"🛡️ *COSECHA* (SMA30: ${sma_30_valor:.2f})\n>>> {'VENDER' if glng_actual < sma_30_valor else 'MANTENER'}"
        elif glng_actual <= stop_loss_usd:
            res = "🚨 *STOP LOSS*. VENDER."
        elif glng_actual >= punto_doblar_usd and jkm_actual > umbral_jkm_extra:
            res = "🚀 *AMPLIACIÓN AL 2%*. COMPRAR."
        else:
            res = f"🟢 *MANTENER*. Stop: ${glng_actual - stop_loss_usd:.2f} | Profit: ${stop_loss_profit_usd - glng_actual:.2f}"

        # 5. GRÁFICO (RESTAURADO A TU VERSIÓN ANTERIOR)
        ruta_grafico = 'grafico_golar.png'
        sma_30_full = df_raw['GLNG'].rolling(window=30).mean()
        plot_data = df_raw.tail(30)
        
        if plot_data.empty or plot_data.shape[0] < 2:
            print("⚠️ Advertencia: Datos insuficientes para generar el gráfico.")
            ruta_grafico = None
        else:
            plot_data_filled = plot_data.fillna(method='ffill').fillna(method='bfill')
            base_price = plot_data_filled['GLNG'].iloc[0]
            if base_price == 0:
                ruta_grafico = None
            else:
                relativa = (plot_data_filled / plot_data_filled.iloc[0]) * 100
                sma_30_relativa = (sma_30_full.loc[plot_data.index] / base_price) * 100

                plt.figure(figsize=(12, 8))
                plt.plot(relativa['GLNG'], label='MI POSICIÓN: Golar LNG', color='#007bff', linewidth=3.5)
                plt.plot(sma_30_relativa, label='SOPORTE: Media 30 ses.', color='#17a2b8', linestyle=':', linewidth=2.5)
                plt.plot(relativa['LNGX'], label='SENTIMIENTO: ETF Gas', color='#ff7f0e', linewidth=2, linestyle='--')
                plt.plot(relativa['JKM=F'], label='MOTOR: Gas JKM', color='#28a745', linewidth=2, alpha=0.7)
                plt.axhline(100, color='#dc3545', linestyle='-', linewidth=1, alpha=0.5)
                plt.title(f'MONITOR DE FUERZA RELATIVA Y TENDENCIA (${glng_actual:.2f})', fontsize=16, fontweight='bold', pad=20)
                plt.legend(loc='upper left', frameon=True, shadow=True)
                plt.grid(True, alpha=0.2)
                plt.tight_layout()
                plt.savefig(ruta_grafico, dpi=130)
                plt.close()
        
        # 6. INFORME FINAL (CON EJECUCIÓN ACTUALIZADA)
        informe = (
            f"📊 *Monitor Semanal GLNG* (Obj: $68)\n"
            f"------------------------------------\n"
            f"💎 *EJECUCIÓN (GLNG):* ${glng_actual:.2f} ({pnl_pct_usd:+.2f}%)\n"
            f"🔥 *MOTOR (JKM):* ${jkm_actual:.2f} (Ref: ${umbral_jkm_extra})\n"
            f"📈 *SENTIMIENTO (LNGX):* ${lngx_actual:.2f}\n"
            f"------------------------------------\n"
            f"📢 *ESCENARIO:* {escenario_texto}\n\n"
            f"✅ *ESTADO:* {res}\n"
            f"------------------------------------\n"
            f"📌 *PROTOCOLO DE ACTUACIÓN*:\n"
            f"1. *STOP*: Vender si toca ${stop_loss_usd}.\n"
            f"2. *DOBLAR*: Compra +1% si >${punto_doblar_usd} y JKM >${umbral_jkm_extra}.\n"
            f"3. *COSECHA*: Si >${stop_loss_profit_usd}, vender bajo SMA 30."
        )

        enviar_alerta_telegram(informe, ruta_grafico)

    except Exception as e:
        print(f"🔴 ERROR CRÍTICO: {e}")

if __name__ == "__main__":
    monitor_tesis_pro()
