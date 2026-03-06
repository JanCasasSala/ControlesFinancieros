def enviar_telegram_robusto(texto, ruta_foto=None):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Error: Faltan Token o ID en el script.")
        return
    
    base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    
    # ENVÍO DE TEXTO
    try:
        res = requests.post(f"{base_url}/sendMessage", 
                             data={"chat_id": TELEGRAM_CHAT_ID, "text": texto, "parse_mode": "Markdown"}, 
                             timeout=15)
        # ESTA LÍNEA TE DIRÁ LA VERDAD:
        print(f"RESULTADO TELEGRAM: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ Error de red: {e}")

    # ENVÍO DE FOTO
    if ruta_foto and os.path.exists(ruta_foto):
        try:
            with open(ruta_foto, 'rb') as f:
                requests.post(f"{base_url}/sendPhoto", 
                              data={"chat_id": TELEGRAM_CHAT_ID}, 
                              files={"photo": f}, timeout=20)
        except:
            pass
