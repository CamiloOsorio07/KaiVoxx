# js-kaivoxx-bot

Bot Discord en JavaScript (réplica del bot Python) en carpeta separada.

## Requisitos
- Node.js 18+
- ffmpeg instalado (para música y TTS si aplica)
- `yt-dlp` instalado en el sistema (para música)

## Variables de entorno (.env)
- `DISCORD_TOKEN`
- `GROQ_API_KEY` (para IA)
- `BOT_PREFIX` (default `#`)
- `MAX_QUEUE_LENGTH` (default `500`)
- `MAX_TTS_CHARS` (default `180`)
- `TTS_LANGUAGE` (default `es`)

Cookies yt-dlp (opcional):
- `YTDLP_COOKIES_BASE64` o `YTDLP_COOKIES`

## Ejecutar
```bash
cd js-kaivoxx-bot
npm install
npm start
```

