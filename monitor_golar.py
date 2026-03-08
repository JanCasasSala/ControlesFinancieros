import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
import os

# --- 1. CONFIGURACIÓN ---
TOKEN = os.getenv("TELEGRAM_TOKEN", "8754089216:AAFlgu0R-dfxWFSXG7NBPpcWXuEmW7Jim-4")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8351044609")

def monitor_tesis_golar_pro():
    try:
        # --- 2. DESCARGA DE DATOS ---
        tickers = ["GLNG", "JKM=F", "LNGX", "EURUSD=X"]
        datos = yf.download(tickers, period="60d", progress=False)
        df_c = datos['Close'].ffill().bfill()
        df_v = datos['Volume']['GLNG'].ffill().bfill()

        # --- 3. CÁLCULO DE INDICADORES ---
        glng_act = df_c['GLNG'].iloc[-1]
        jkm_act = df_c['JKM=F'].iloc[-1]
        lngx_act = df_c['LNGX'].iloc[-1]
        
        sma30_serie = df_c['GLNG'].rolling(window=30).mean()
        sma30_val = sma30_serie.iloc[-1]
        
        vol_hoy = df_v.iloc[-1]
        vol_med = df_v.rolling(window=10).mean().iloc[-1]
        fuerza = vol_hoy > vol_med

        # --- 4. LÓGICA Y DIAGNÓSTICO (MOTOR DE DECISIÓN) ---
        precio_ent = 46.25
        pnl = ((glng_act - precio_ent) / precio_ent) * 100
        
        # Lógica de Escenario (El Diagnóstico que te interesa)
        if jkm_act > 8.00 and glng_act > precio_ent:
            diagnostico = "🌬️ *VIENTO DE COLA*: Motor (JKM) y Precio acompañan la subida."
        elif jkm_act <= 8.00 and glng_act > precio_ent:
            diagnostico = "⚠️ *LA TRAMPA*: Subida por inercia. Motor (JKM) débil, cuidado."
        elif jkm_act > 8.00 and glng_act <= precio_ent:
            diagnostico = "🛡️ *EL REFUGIO*: Sector sufre pero la materia prima es cara."
        else:
            diagnostico = "📉 *ZONA NEUTRA*: Sin catalizadores claros."

        # Estado Operativo
        if glng_act >= 68.00:
            estado = "🎯 OBJETIVO ALCANZADO"
        elif glng_act >= 55.50:
            estado = "🚨 VENDER (COSECHA)" if (glng_act < sma30_val and fuerza) else "⏳ MANTENER (RUIDO)"
        elif glng_act <= 42.10:
            estado = "🚨 STOP LOSS (VENDER)"
        else:
            estado = "🟢 MANTENER"

        # --- 5. GRÁFICO DE FUERZA RELATIVA (VERSION ELEGANTE) ---
        ruta_grafico = 'informe_golar.png'
        plot_data = df_c.tail(30)
        relativa = (plot_data / plot_data.iloc[0]) * 100
        sma_rel = (sma30_serie.tail(30) / plot_data['GLNG'].iloc[0]) * 100

        plt.figure(figsize=(12, 8))
        plt.style.use('dark_background')
        
        plt.plot(relativa['GLNG'], label='MI POSICIÓN: Golar LNG', color='#00f2ff', linewidth=3.5, zorder=4)
        plt.plot(sma_rel, label='SOPORTE: Media 30 ses.', color='#ff3131', linestyle='--', linewidth=2)
        plt.plot(relativa['LNGX'], label='SENTIMIENTO: ETF Gas', color='#ff9f43', linewidth=1.5, alpha=0.6)
        plt.plot(relativa['JKM=F'], label='MOTOR: Gas JKM', color='#2ed573', linewidth=1.5, alpha=0.6)

        # Triángulos de Cruce
        for i in range(1, len(relativa)):
            if relativa['GLNG'].iloc[i-1] > sma_rel.iloc[i-1] and relativa['GLNG'].iloc[i] < sma_rel.iloc[i]:
                plt.scatter(relativa.index[i], relativa['GLNG'].iloc[i], color='red', marker='v', s=150, zorder=5)

        plt.title(f"MONITOR GOLAR: {estado}", fontsize=14, fontweight='bold', pad=20)
        plt.legend(loc='upper left', facecolor='#151515')
        plt.grid(alpha=0.1)
        plt.tight_layout()
        plt.savefig(ruta_grafico, dpi=130)
        plt.close()

        # --- 6. ENVÍO COMPLETO ---
        resumen = (
            f"📊 *MONITOR ESTRATÉGICO GOLAR*\n"
            f"------------------------------\n"
            f"💎 *PRECIO:* ${glng_act:.2f} ({pnl:+.2f}%)\n"
            f"🔥 *MOTOR (JKM):* ${jkm_act:.2f}\n"
            f"📈 *SENTIMIENTO:* ${lngx_act:.2f}\n"
            f"📊 *VOLUMEN:* {'✅ ALTO' if fuerza else '❌ BAJO'}\n"
            f"------------------------------\n"
            f"📢 *DIAGNÓSTICO:* {diagnostico}\n\n"
            f"✅ *ESTADO ACTUAL:* {estado}\n"
            f"------------------------------"
        )
        
        url = f"https://api.telegram.org/bot{TOKEN}/"
        requests.post(url + "sendMessage", data={"chat_id": CHAT_ID, "text": resumen, "parse_mode": "Markdown"})
        with open(ruta_grafico, 'rb') as f:
            requests.post(url + "sendPhoto", data={"chat_id": CHAT_ID}, files={"photo": f})

    except Exception as e:
        print(f"Error: {e}")

monitor_tesis_golar_pro()
