"""
KaiVoxx Web Server
Sirve la página web y expone endpoints públicos seguros.
"""

import os
from typing import Optional
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="KaiVoxx Web Interface")

# ==========================================
# VARIABLES GLOBALES
# ==========================================

# Aquí se inyectará la instancia real del bot
# desde tu entrypoint:
#
#   import web.server as webserver
#   webserver.bot = bot
#
bot = None


# ==========================================
# SERVIR ARCHIVOS ESTÁTICOS
# ==========================================

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    print("⚠️  Advertencia: No existe la carpeta web/static")


# ==========================================
# ENDPOINT: CONFIGURACIÓN PÚBLICA
# ==========================================

@app.get("/api/config")
def get_public_config():
    """
    Devuelve configuración NO sensible.
    Estas variables deben estar en Railway:
    - CLIENT_ID
    - BOT_ICON
    - SUPPORT_INVITE
    """

    return {
        "clientId": os.environ.get("CLIENT_ID"),
        "botIcon": os.environ.get("BOT_ICON"),
        "supportInvite": os.environ.get("SUPPORT_INVITE"),
        "repoUrl": "https://github.com/CamiloOsorio07/KaiVoxx"
    }


# ==========================================
# ENDPOINT: ESTADO DEL BOT
# ==========================================

@app.get("/api/status")
def get_bot_status():
    """
    Devuelve estado en tiempo real del bot.
    Usa la instancia inyectada desde tu entrypoint.
    """

    if bot is None:
        return JSONResponse({
            "online": False,
            "servers": 0,
            "users": 0
        })

    try:
        # discord.py
        guilds = getattr(bot, "guilds", [])
        servers = len(guilds)

        total_users = 0
        for g in guilds:
            if hasattr(g, "member_count") and g.member_count:
                total_users += g.member_count

        is_online = False
        if hasattr(bot, "is_ready"):
            is_online = bot.is_ready()

        return {
            "online": bool(is_online),
            "servers": servers,
            "users": total_users
        }

    except Exception as e:
        return JSONResponse({
            "online": False,
            "servers": 0,
            "users": 0,
            "error": str(e)
        })


# ==========================================
# FUNCIÓN PARA ARRANCAR UVICORN
# ==========================================

def run_uvicorn(host="0.0.0.0", port: Optional[int] = None):
    """
    Se usa desde el entrypoint del bot
    para levantar el servidor en un hilo.
    """
    port = port or int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "web.server:app",
        host=host,
        port=port,
        log_level="info"
    )


# ==========================================
# EJECUCIÓN DIRECTA (solo web, sin bot)
# ==========================================

if __name__ == "__main__":
    run_uvicorn()
