"""Entrypoint: crea el bot y lo ejecuta"""
import logging
from infrastructure.discord import bot_client
from config.settings import DISCORD_TOKEN
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kaivoxx")

bot = bot_client.create_bot()  # crea e inicializa comandos/events
if __name__ == "__main__":
    log.info("Iniciando Kaivoxx...")
    bot.run(DISCORD_TOKEN)
