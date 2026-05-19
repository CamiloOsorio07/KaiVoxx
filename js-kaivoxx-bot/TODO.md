# js-kaivoxx-bot — TODO

## Paso 1: Levantar dependencias JS y env
- [x] Crear `js-kaivoxx-bot/package.json` con `discord.js`, `@discordjs/voice`, `dotenv`
- [x] Documentar requerimientos externos en `README.md` (ffmpeg + yt-dlp)


## Paso 2: Implementar core
- `src/queue/MusicQueue.js`
- `src/discord/bot.js` (prefijo #, onMessage con menciones + comandos)

## Paso 3: Música
- `src/ytdlp/ytdlp_client.js`: wrapper que llama `yt-dlp` y extrae stream/audio
- `src/audio/playback.js`: reproduce/pausa/skip/stop y gestiona transición al siguiente

## Paso 4: IA y TTS
- `src/discord/commands/ai.js`: `#ia`, `#habla`
- `src/tts/gtts_client.js`: modo A (auxiliar local) para generar mp3 como en Python
  - (si aplica) script helper en JS/Python auxiliar y limpieza temporal

## Paso 5: UI Now Playing
- `src/discord/views/now_playing.js`: embed + botones + barra de tiempo por segundo

## Paso 6: Help
- `src/discord/commands/help.js`: embed con comandos como en Python

## Paso 7: Validación
- `npm start` y pruebas manuales de:
  - join/leave
  - play con link y con búsqueda
  - skip/stop/queue/now
  - #ia y #habla
  - menciones <@id> ia / <@id> habla

