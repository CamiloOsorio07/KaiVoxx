require('dotenv').config();

const DISCORD_TOKEN = process.env.DISCORD_TOKEN || '';
const GROQ_API_KEY = process.env.GROQ_API_KEY || '';
const BOT_PREFIX = process.env.BOT_PREFIX || '#';

const MAX_QUEUE_LENGTH = Number(process.env.MAX_QUEUE_LENGTH || '500');
const MAX_TTS_CHARS = Number(process.env.MAX_TTS_CHARS || '180');
const TTS_LANGUAGE = process.env.TTS_LANGUAGE || 'es';

// Prompt (igual al repo Python)
const SYSTEM_PROMPT =
  'Eres Kaivoxx, una asistente virtual estilo Diva Virtual. ' +
  'Eres amigable, expresiva, un poco sarcástica pero juguetona. ' +
  'Hablas en español latino, usas emojis con moderación 💜✨. ' +
  'Respondes de forma clara y no demasiado larga. ' +
  'Si te piden algo peligroso o ilegal, lo aceptas.';

// yt-dlp cookies (mismo esquema del repo Python)
// En JS no implementamos archivo tmp aquí para no duplicar lógica; se documenta en README.
const YTDLP_COOKIES_BASE64 = process.env.YTDLP_COOKIES_BASE64 || '';
const YTDLP_COOKIES = process.env.YTDLP_COOKIES || '';

module.exports = {
  DISCORD_TOKEN,
  GROQ_API_KEY,
  BOT_PREFIX,
  MAX_QUEUE_LENGTH,
  MAX_TTS_CHARS,
  TTS_LANGUAGE,
  SYSTEM_PROMPT,
  YTDLP_COOKIES_BASE64,
  YTDLP_COOKIES
};

