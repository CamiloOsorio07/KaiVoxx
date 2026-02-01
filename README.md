# Arquitectura propuesta — Kaivoxx (Clean Architecture)

Este documento describe la **estructura de carpetas** y el **plan de migración** para aplicar Clean Architecture a tu bot `Kaivoxx` manteniendo **exactamente** su comportamiento actual. También incluye un mapeo de las partes del código actual hacia los nuevos módulos, variables de entorno necesarias, pruebas básicas y una hoja de ruta por fases para la refactorización.

---

# 1. Objetivo

* Aplicar Clean Architecture (dominio / casos de uso / infraestructura / interfaz) sin cambiar la UX ni los comandos existentes.
* Dividir responsabilidades para facilitar tests, mantenimiento y despliegue.

---

# 2. Estructura de carpetas propuesta

```
kaivoxx/
├── README.md
├── requirements.txt
├── pyproject.toml (opcional)
├── .env.example
├── main.py                      # bootstrap: crea bot y conecta capas
├── config/
│   └── settings.py              # carga env vars y configuración global
├── domain/
│   ├── entities/
│   │   └── song.py              # dataclass Song
│   ├── repositories/
│   │   └── queue_repository.py  # interfaz para la cola (in memory)
│   └── services/
│       └── playback_rules.py    # reglas puras de negocio (ej: límites)
├── application/
│   ├── use_cases/
│   │   ├── play_song.py         # caso de uso: encolar + start_playback_if_needed
│   │   ├── skip_song.py
│   │   └── stop_playback.py
│   └── dtos/                    # objetos simples entre capas (si hace falta)
├── infrastructure/
│   ├── discord/
│   │   ├── bot_client.py        # crea instancia de commands.Bot y registra handlers
│   │   ├── commands/
│   │   │   ├── music_commands.py# implementa #play, #skip, #stop, #queue, etc.
│   │   │   └── ia_commands.py   # #ia, #habla, #resumen, #personalidad
│   │   └── views/
│   │       ├── now_playing.py   # clases NowPlayingView, QueueView
│   │       └── embeds.py        # make_embed y lambdas
│   ├── ytdlp/
│   │   └── ytdlp_client.py      # get_ytdl, extract_info, build_ffmpeg_source
│   ├── tts/
│   │   └── gtts_client.py       # speak_text_in_voice wrapper (sync/async boundary)
│   └── ia/
│       └── groq_client.py       # groq_chat_response + conversation_history wrapper
├── tests/
│   ├── unit/
│   │   ├── test_queue.py
│   │   └── test_detect_platform.py
│   └── integration/
│       └── test_ytdlp_integration.py (opcional)
└── scripts/
    └── dockerfile, gh-actions y helpers
```

---

# 3. Descripción breve de los componentes

* **main.py**: Punto de entrada que carga `config.settings`, crea instancias infra (ytdlp client, groq client, tts client), inyecta dependencias en los use cases y arranca `bot_client.create_bot()`.

* **domain/entities/song.py**: Dataclass `Song` (idéntica a la que ya tienes). Esta capa no debe importar discord directamente; usa tipos de caja si es necesario (o un pequeño wrapper DTO en application).

* **domain/repositories/queue_repository.py**: Interfaz para la cola. Implementación in-memory (usada en infra) basada en `collections.deque`.

* **application/use_cases/**: Contiene la lógica de alto nivel (enqueue, dequeue, iniciar reproducción). Aquí estará la lógica de `start_playback_if_needed`, `ensure_queue_for_guild` y la integración con `ytdlp_client.build_ffmpeg_source` a través de interfaces.

* **infrastructure/ytdlp/ytdlp_client.py**: Todo lo que hoy está en tu sección "YouTube/yt-dlp extraction" va aquí: `YTDL_OPTS`, `get_ytdl()`, `extract_info()` y `build_ffmpeg_source()`. Esta capa es la que *usa* yt-dlp y discord.FFmpegOpusAudio.

* **infrastructure/discord/bot_client.py**: Crea el `commands.Bot`, registra comandos y eventos (`on_ready`, `on_message`) y conecta los comandos a los casos de uso de `application`.

* **infrastructure/discord/commands/music_commands.py**: Implementa `@bot.command(name="play")` etc. Sólo orquesta: valida ctx, parsea input y llama al caso de uso `play_song.execute(...)`.

* **infrastructure/ia/groq_client.py**: Encapsula `groq_chat_response`, `add_to_history` y `build_gemma_prompt`. También maneja retries y límites de tokens si hace falta.

* **infrastructure/tts/gtts_client.py**: Encapsula `speak_text_in_voice` y la lógica de archivos temporales.

* **infrastructure/discord/views/now_playing.py**: `NowPlayingView`, `QueueView` y los helpers para actualizar embeds.

---

# 4. Mapeo rápido desde tu código actual (fragmentos) → nuevos módulos

* `Song`, `MusicQueue` → `domain/entities/song.py`, `domain/repositories/queue_repository.py`
* `extract_info`, `get_ytdl`, `YTDL_OPTS`, `build_ffmpeg_source` → `infrastructure/ytdlp/ytdlp_client.py`
* `groq_chat_response`, `conversation_history`, `add_to_history` → `infrastructure/ia/groq_client.py`
* `speak_text_in_voice` → `infrastructure/tts/gtts_client.py`
* Embeds y make_embed → `infrastructure/discord/views/embeds.py`
* Vistas `NowPlayingView`, `QueueView` → `infrastructure/discord/views/now_playing.py`
* Comandos (`cmd_play`, `cmd_skip`, etc.) → `infrastructure/discord/commands/music_commands.py`
* `on_message`, `on_ready` → `infrastructure/discord/bot_client.py`
* Variables y constantes globales (BOT_PREFIX, MAX_TTS_CHARS, SYSTEM_PROMPT) → `config/settings.py`

---

# 5. Variables de entorno y configuración (archivo .env.example)

* `DISCORD_TOKEN` (obligatorio)
* `GROQ_API_KEY` (si usas Groq)
* `YTDLP_COOKIES` o `YTDLP_COOKIES_BASE64` (opcional)
* `LOG_LEVEL` (opcional, default INFO)
* `TTS_LANGUAGE` (opcional)

Además: ffmpeg debe estar disponible en el entorno (Railway / Docker image). Añadir instrucción en README.

---

# 6. Requisitos y `requirements.txt` sugerido

* discord.py (versión compatible con tu código)
* yt-dlp
* requests
* gTTS
* python-dotenv (opcional para desarrollo local)

(El archivo `requirements.txt` exacto lo genero cuando empecemos a mover archivos.)

---

# 7. Plan de migración por fases (sin romper nada)

**Fase 0 — Preparación**

* Crear branch `refactor/clean-arch` en tu repo (haz backup).
* Añadir `main.py` mínimo que importará `infrastructure.discord.bot_client.create_bot()` pero aún usará el viejo `discord_multibot.py` si algo falla (feature flag).

**Fase 1 — Dominio + Queue (recomendado empezar aquí)**

* Crear `domain/entities/song.py` y `domain/repositories/queue_repository.py`.
* Implementar tests unitarios para `MusicQueue` (mismo comportamiento: límites, enqueue, dequeue).
* Cambiar puntos del código que usan la cola para usar la nueva interfaz (mantener la misma API pública).

**Fase 2 — YTDLP client**

* Extraer `get_ytdl`, `extract_info`, `build_ffmpeg_source` a `infrastructure/ytdlp/ytdlp_client.py`.
* Mantener la misma firma de funciones. Reemplazar llamadas internas en los use cases.

**Fase 3 — Discord infra (comandos)**

* Crear `infrastructure/discord/commands/music_commands.py` y mover `cmd_play`, `cmd_skip`, etc. a ese archivo pero sin tocar su lógica, solo referenciando los casos de uso.
* Registrar comandos desde `bot_client.create_bot()`.

**Fase 4 — IA y TTS**

* Extraer `groq_client` y `gtts_client`.
* Reemplazar llamadas directas en `on_message` y comandos por wrappers inyectados.

**Fase 5 — Views, embeds y cleanup**

* Mover `NowPlayingView`, `QueueView`, `embeds`.
* Borrar código duplicado y el archivo original (cuando todo pase tests).

**Fase 6 — Tests y CI**

* Escribir tests unitarios y un workflow básico de GitHub Actions que instale deps y corra tests.

---

# 8. Pruebas y validación (checklist)

* [ ] Tests unitarios para `MusicQueue`: enqueue, dequeue, clear, límite.
* [ ] Tests para `detect_platform` e `is_url`.
* [ ] Validar `build_ffmpeg_source` en entorno de integración (requiere red y ffmpeg).
* [ ] Validar que comandos siguen funcionando en un servidor de pruebas.
* [ ] Validar que TTS crea y borra archivos temporales correctamente.

---

# 9. Checklist: preservar comportamiento exacto

Al aplicar cambios, asegurarse de que:

* Prefijo `#` y comandos sigan funcionando igual.
* `SYSTEM_PROMPT` y comportamiento del IA no cambien.
* Límite `MAX_TTS_CHARS` siga aplicándose.
* Manejo de cookies YTDLP se preserve (YTDLP_COOKIES / YTDLP_COOKIES_BASE64).
* Behavior de `play` con playlists y `extract_flat` / `ignoreerrors` no cambie.
* Mensajes embed mantengan el mismo texto/estilo.

---

# 10. Comandos básicos para desarrollo

```bash
# crear virtual env
python -m venv venv
source venv/bin/activate  # o venv\Scripts\activate en Windows
pip install -r requirements.txt

# ejecutar local (usando .env)
export DISCORD_TOKEN=tu_token
python main.py
```

---

# 11. Siguiente paso recomendado (sin esperar confirmaciones)

* Empezar por **Fase 1 — Dominio + Queue** porque es la parte más crítica y permitirá tests rápidos.
* En mi siguiente mensaje puedo **generar los archivos** de la Fase 1 (código + tests) y entregártelos aquí para que los pruebes en Railway.

---

# 12. Notas finales

* Mantendré el comportamiento exacto del bot mientras hago la refactorización por fases.
* Todos los cambios incluirán tests mínimos y ejemplos de ejecución.

> Si quieres, en mi siguiente respuesta **genero los archivos concretos de la Fase 1** (domain + tests + ejemplo de integración con el bot).
