Kaivoxx - Refactor (Clean Architecture scaffold)
===============================================

Este repo contiene una refactorización del bot original `discord_multibot.py`
organizada por capas (domain / application / infrastructure).

NOTA: El objetivo fue **preservar el comportamiento**. Para ejecutar, copia tus
variables de entorno (DISCORD_TOKEN, GROQ_API_KEY, YTDLP_COOKIES...)
y asegúrate que ffmpeg esté disponible.

Estructura principal:
- main.py
- config/
- domain/
- integration/
- infrastructure/

Ejecutar:
    python main.py
