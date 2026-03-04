"""Entrypoint: crea el bot y lo ejecuta"""
import logging
import threading
import os

from infrastructure.discord import bot_client
from config.settings import DISCORD_TOKEN

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kaivoxx")

bot = bot_client.create_bot()  # crea e inicializa comandos/events

if __name__ == "__main__":
    log.info("Iniciando Kaivoxx...")

    # arrancar servidor web en hilo (usa web.server.run_uvicorn)
    try:
        # importa localmente para evitar importaciones circulares si no existe web
        import web.server as webserver  # asegúrate de que la carpeta `web` exista y contenga server.py
        # inyecta la instancia del bot para que el endpoint /api/status la use
        webserver.bot = bot

        def start_web():
            host = "0.0.0.0"
            port = int(os.environ.get("PORT", 8000))
            # run_uvicorn bloquea, por eso lo ejecutamos en un hilo
            webserver.run_uvicorn(host=host, port=port)

        t = threading.Thread(target=start_web, daemon=True)
        t.start()
        log.info("Servidor web (UI) arrancado en hilo.")
    except Exception as e:
        log.warning("No se pudo iniciar el servidor web integrado. Asegúrate de tener web/server.py. Error: %s", e)

    bot.run(DISCORD_TOKEN)
