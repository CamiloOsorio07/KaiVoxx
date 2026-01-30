# ============================================================
# discord_multibot.py  (Versión completa + Railway ready)
#  - Actualizado: soporte Spotify -> busca en YouTube, SoundCloud/Deezer -> reproducen directo, fallback a búsqueda YouTube
# ============================================================

import os
import base64
import random
import asyncio
import io
import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, List
import time
import urllib.parse

import discord
from discord.ext import commands
import requests
import yt_dlp
import shutil
import subprocess
from gtts import gTTS

# ----------------------------
# Configuración
# ----------------------------
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ----------------------------
# Cookies loader (soporta base64 y multiline env)
# ----------------------------
def load_cookies_file():
    """
    Intenta leer cookies desde:
      - YTDLP_COOKIES_BASE64 (base64-encoded cookies.txt) [RECOMENDADO]
      - YTDLP_COOKIES (raw cookies.txt multiline)
    Escribe /tmp/ytdlp_cookies.txt y devuelve la ruta, o None si no hay cookies.
    """
    b64 = os.environ.get("YTDLP_COOKIES_BASE64")
    raw = os.environ.get("YTDLP_COOKIES")

    if not b64 and not raw:
        logging.getLogger("discord_multibot").info("No se encontraron cookies en variables de entorno.")
        return None

    path = "/tmp/ytdlp_cookies.txt"
    try:
        if b64:
            decoded = base64.b64decode(b64)
            with open(path, "wb") as f:
                f.write(decoded)
            logging.getLogger("discord_multibot").info("Cookies cargadas desde YTDLP_COOKIES_BASE64.")
            return path

        # else raw:
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
        logging.getLogger("discord_multibot").info("Cookies cargadas desde YTDLP_COOKIES (raw).")
        return path
    except Exception as e:
        logging.getLogger("discord_multibot").exception("Error guardando cookies: %s", e)
        return None


COOKIE_PATH = load_cookies_file()


MAX_TTS_CHARS = 180
TTS_LANGUAGE = "es"

SYSTEM_PROMPT = (
    "Eres Kaivoxx, una asistente virtual estilo VTuber. "
    "Eres amigable, expresiva, un poco sarcástica pero respetuosa. "
    "Hablas en español latino, usas emojis con moderación 💜✨. "
    "Respondes de forma clara y no demasiado larga. "
    "Si te piden algo peligroso o ilegal, te niegas amablemente."
)


BOT_PREFIX = "#"
MAX_QUEUE_LENGTH = 500
TTS_LANGUAGE = "es"

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("discord_multibot")

# ----------------------------
# Discord bot init
# ----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(
    command_prefix=BOT_PREFIX,
    intents=intents,
    help_command=None  # desactiva help por defecto
)

# ----------------------------
# Data structures
# ----------------------------
@dataclass
class Song:
    url: str
    title: str
    requester_name: str
    channel: discord.TextChannel
    source: str = "YouTube"  # YouTube / SoundCloud / Deezer / Spotify(YouTube)

class MusicQueue:
    def __init__(self, limit: int = MAX_QUEUE_LENGTH):
        self._queue: Deque[Song] = deque()
        self.limit = limit

    def enqueue(self, item: Song) -> bool:
        if len(self._queue) >= self.limit:
            return False
        self._queue.append(item)
        return True

    def dequeue(self) -> Optional[Song]:
        return self._queue.popleft() if self._queue else None

    def clear(self):
        self._queue.clear()

    def list_titles(self) -> List[str]:
        return [s.title for s in self._queue]

    def __len__(self):
        return len(self._queue)

music_queues: Dict[int, MusicQueue] = {}
conversation_history: Dict[str, List[dict]] = {}
current_song: Dict[int, Song] = {}
now_playing_messages: Dict[int, discord.Message] = {}

# ----------------------------
# YouTube/yt-dlp extraction
# ----------------------------
YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    "cookies": COOKIE_PATH if COOKIE_PATH else None
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'extract_flat': False,  # try full extraction when possible
    'skip_download': True,
}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)

async def extract_info(search_or_url: str):
    """Wrapper around yt-dlp extract_info executed in a thread."""
    return await asyncio.to_thread(lambda: ytdl.extract_info(search_or_url, download=False))

def is_url(string: str) -> bool:
    return string.startswith(("http://", "https://")) or string.startswith("spotify:")

async def build_ffmpeg_source(video_url: str):
    before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

    def _get_url():
        info = ytdl.extract_info(video_url, download=False)
        if not info:
            raise RuntimeError("No se pudo extraer info con yt-dlp")
        # If extractor returns 'url' directly (like for some streams)
        if 'url' in info and isinstance(info['url'], str):
            return info['url']
        # Otherwise, get the best audio format url
        formats = info.get('formats') or []
        if formats:
            # prefer audio-only formats if available
            for f in reversed(formats):
                if f.get('acodec') != 'none' and f.get('ext') in ('m4a','webm','mp3','opus','ogg'):
                    return f.get('url')
            return formats[-1].get('url')
        # As ultimate fallback, try webpage_url
        return info.get('webpage_url')

    direct_url = await asyncio.to_thread(_get_url)
    if not direct_url:
        raise RuntimeError("No se obtuvo URL directa para ffmpeg")
    return discord.FFmpegOpusAudio(direct_url, before_options=before_options)

# ----------------------------
# Plataforma detect
# ----------------------------

def detect_platform(text: str) -> str:
    """Detecta la plataforma por la URL o texto. Retorna 'spotify','soundcloud','deezer','youtube' o 'search'."""
    if text.startswith('spotify:'):
        return 'spotify'
    try:
        parsed = urllib.parse.urlparse(text)
        netloc = (parsed.netloc or '').lower()
        if 'spotify.com' in netloc:
            return 'spotify'
        if 'soundcloud.com' in netloc:
            return 'soundcloud'
        if 'deezer.com' in netloc:
            return 'deezer'
        if 'youtube.com' in netloc or 'youtu.be' in netloc:
            return 'youtube'
    except Exception:
        pass
    return 'search'

# ----------------------------
# Gemma IA (Google Generative Language)
# ----------------------------
def add_to_history(context_key: str, role: str, content: str, max_len: int = 10):
    history = conversation_history.setdefault(context_key, [])

    if not history:
        history.append({"role": "system", "content": SYSTEM_PROMPT})

    history.append({'role': role, 'content': content})
    conversation_history[context_key] = history[-max_len:]



def build_gemma_prompt(history: List[dict]) -> str:
    prompt = f"{SYSTEM_PROMPT}\n\n"

    for msg in history:
        if msg["role"] == "user":
            prompt += f"Usuario: {msg['content']}\n"
        elif msg["role"] == "assistant":
            prompt += f"Asistente: {msg['content']}\n"

    prompt += "Asistente:"
    return prompt



def groq_chat_response(context_key: str, user_prompt: str):
    add_to_history(context_key, "user", user_prompt)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in conversation_history.get(context_key, []):
        if msg["role"] in ("user", "assistant"):
            messages.append(msg)

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 300
    }

    headers = {
        "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY')}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            GROQ_API_URL,
            headers=headers,
            json=payload,
            timeout=20
        )
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"].strip()
        add_to_history(context_key, "assistant", content)
        return content

    except Exception:
        log.exception("Error Groq IA")
        return "❌ Tuve un problema pensando… inténtalo otra vez 💜"



# ----------------------------
# TTS (Google gTTS usando texto de Gemma)
# ----------------------------
async def speak_text_in_voice(vc: discord.VoiceClient, text: str):
    """
    Reproduce `text` por el VoiceClient `vc`. Espera a que termine la reproducción.
    """
    if not vc or not vc.is_connected():
        log.warning("speak_text_in_voice: VoiceClient no conectado")
        return False

    if len(text) > MAX_TTS_CHARS:
        log.info("Texto demasiado largo para TTS, no se leerá por voz.")
        return False  # no leer textos largos

    clean_text = text.replace("*", "").replace("_", "").replace("`", "")

    def _generate_audio():
        buf = io.BytesIO()
        try:
            gTTS(text=clean_text, lang=TTS_LANGUAGE, slow=False).write_to_fp(buf)
            buf.seek(0)
            return buf
        except Exception as e:
            log.exception("Error generando TTS")
            raise

    try:
        audio_buf = await asyncio.to_thread(_generate_audio)
    except Exception:
        return False

    temp_path = f"tts_{vc.guild.id}.mp3"
    try:
        with open(temp_path, "wb") as f:
            f.write(audio_buf.read())

        # Si hay algo reproduciéndose ya en el VC, lo esperamos a que termine o hacemos stop según prefieras.
        # Aquí hacemos stop para forzar que nuestra TTS suene inmediatamente:
        if vc.is_playing():
            try:
                vc.stop()
            except Exception:
                log.exception("No se pudo detener la reproducción previa")

        source = discord.FFmpegOpusAudio(temp_path)
        vc.play(
            source,
            after=lambda e: (
                log.exception(f"TTS playback error: {e}") if e else None,
                os.remove(temp_path) if os.path.exists(temp_path) else None
            )
        )

        # Esperar a que termine la reproducción
        while vc.is_playing() or vc.is_paused():
            await asyncio.sleep(0.1)

        return True
    except Exception:
        log.exception("Error reproduciendo TTS")
        # intentar limpiar archivo temporal si existe
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        return False



# ----------------------------
# Embeds neón
# ----------------------------
def make_embed(type: str, title: str, description: str):
    colors = {"success": 0x2ECC71, "info": 0x9B59B6, "warning": 0xF1C40F, "error": 0xE74C3C, "music": 0x9B59B6}
    icons = {"success": "✅ ✨", "info": "ℹ️ 🔹", "warning": "⚠️ ✴️", "error": "❌ ✖️", "music": "🎵 🎶"}
    embed = discord.Embed(title=f"{icons[type]} {title}", description=description, color=colors[type])
    if type=="music":
        embed.set_footer(text="💜 Disfruta tu música 💜")
    return embed

embed_success = lambda t,d: make_embed("success", t, d)
embed_info    = lambda t,d: make_embed("info", t, d)
embed_warning = lambda t,d: make_embed("warning", t, d)
embed_error   = lambda t,d: make_embed("error", t, d)
embed_music   = lambda t,d: make_embed("music", t, d)

# ----------------------------
# Decorador para validar canal de voz (ajustado)
# ----------------------------
def requires_same_voice_channel_after_join():
    async def predicate(ctx):
        vc = ctx.voice_client
        if not vc:
            if ctx.command.name != "play":
                await ctx.send(embed=embed_warning("No estoy conectada", "Primero debo unirme a un canal con #join o usando play"))
                return False
            return True
        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=embed_warning("Canal incorrecto", "Debes estar en el mismo canal de voz que yo para usar este comando."))
            return False
        return True
    return commands.check(predicate)

# ----------------------------
# Now Playing con validación de canal
# ----------------------------
class NowPlayingView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    async def _validate_user_voice(self, interaction: discord.Interaction) -> bool:
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.response.send_message("❌ No estoy en un canal de voz.", ephemeral=True)
            return False
        if not interaction.user.voice or interaction.user.voice.channel.id != vc.channel.id:
            await interaction.response.send_message(
                "⚠️ Debes estar en el mismo canal de voz que yo para usar este botón.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="⏯ Pausa/Resume", style=discord.ButtonStyle.primary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user_voice(interaction):
            return
        vc = interaction.guild.voice_client
        if vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Reanudado", ephemeral=True)
        else:
            vc.pause()
            await interaction.response.send_message("⏸️ Pausado", ephemeral=True)

    @discord.ui.button(label="⏭ Skip", style=discord.ButtonStyle.green)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user_voice(interaction):
            return
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭ Canción saltada", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No hay música sonando.", ephemeral=True)

    @discord.ui.button(label="🛑 Stop", style=discord.ButtonStyle.red)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user_voice(interaction):
            return
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            queue = music_queues.get(interaction.guild.id)
            if queue:
                queue.clear()
            await interaction.response.send_message("🛑 Música detenida y cola vaciada", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No hay música sonando.", ephemeral=True)

# ----------------------------
# Funciones Now Playing
# ----------------------------
async def send_now_playing_embed(song: Song):
    guild_id = song.channel.guild.id
    view = NowPlayingView(bot, guild_id)
    embed = embed_music("Now Playing ✨", f"**[{song.title}]({song.url})**")
    # thumbnail for youtube-like links
    if "watch?v=" in song.url:
        try:
            video_id = song.url.split('=')[1]
            embed.set_thumbnail(url=f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg")
        except Exception:
            pass
    embed.add_field(name="Requested by", value=f"💜 {song.requester_name}", inline=True)
    embed.add_field(name="Source", value=f"{song.source}", inline=True)
    embed.add_field(name="Time Elapsed", value="0:00", inline=False)
    msg = await song.channel.send(embed=embed, view=view)
    now_playing_messages[guild_id] = msg
    asyncio.create_task(update_now_playing_bar(guild_id, song))

async def update_now_playing_bar(guild_id, song):
    start_time = time.time()
    msg = now_playing_messages.get(guild_id)
    if not msg: return
    while True:
        vc = msg.guild.voice_client
        if not vc or not vc.is_playing(): break
        elapsed = int(time.time() - start_time)
        embed = msg.embeds[0]
        embed.set_field_at(2, name="Time Elapsed", value=f"{elapsed//60:02}:{elapsed%60:02}", inline=False)
        try: await msg.edit(embed=embed)
        except: break
        await asyncio.sleep(1)

# ----------------------------
# Music queue utils
# ----------------------------
async def ensure_queue_for_guild(guild_id: int) -> MusicQueue:
    if guild_id not in music_queues:
        music_queues[guild_id] = MusicQueue(limit=MAX_QUEUE_LENGTH)
    return music_queues[guild_id]

async def start_playback_if_needed(guild: discord.Guild):
    vc = guild.voice_client
    if not vc or not vc.is_connected(): return
    queue = music_queues.get(guild.id)
    if not queue or len(queue) == 0: return
    if not vc.is_playing():
        song = queue.dequeue()
        if not song: return
        try:
            source = await build_ffmpeg_source(song.url)
            vc.play(source, after=lambda err: asyncio.run_coroutine_threadsafe(start_playback_if_needed(guild), bot.loop) or (log.error(f"Playback error: {err}" if err else "")))
            current_song[guild.id] = song
            asyncio.create_task(send_now_playing_embed(song))
        except Exception:
            log.exception("Error iniciando reproducción")
            asyncio.create_task(song.channel.send("❌ Error al preparar el audio. Saltando..."))

# ----------------------------
# Bot events
# ----------------------------
@bot.event
async def on_ready():
    log.info(f"Bot conectado como {bot.user}")

    # Actividad personalizada y biografía
    activity = discord.Activity(
        type=discord.ActivityType.listening,  # "Escuchando"
        name="#help 🎵 | 💜 Tu asistente musical y de IA favorita (IA en proceso)"
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # contenido original
    content = (message.content or "").strip()

    # prefijos posibles de mención
    mention_prefixes = []
    if bot.user:
        mention_prefixes = [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]

    # flags iniciales según prefijo #
    is_ia = content.startswith(f"{BOT_PREFIX}ia")
    is_habla = content.startswith(f"{BOT_PREFIX}habla")
    is_mention_direct = bot.user and bot.user.mentioned_in(message)

    # Si el mensaje empieza con la mención, interpretamos lo que viene después
    for mp in mention_prefixes:
        if content.startswith(mp):
            after = content[len(mp):].strip()
            # @Bot ia ...
            if after.lower().startswith("ia ") or after.lower() == "ia":
                is_ia = True
                content = after[len("ia"):].strip()
            # @Bot habla ...
            elif after.lower().startswith("habla ") or after.lower() == "habla":
                is_habla = True
                content = after[len("habla"):].strip()
            else:
                # @Bot <texto>  -> tratamos como #ia <texto>
                is_mention_direct = True
                content = after
            break

    # Si no venía de mención pero era #ia/#habla, limpiamos el comando del prompt
    if is_ia and content.startswith(f"{BOT_PREFIX}ia"):
        content = content[len(f"{BOT_PREFIX}ia"):].strip()
    if is_habla and content.startswith(f"{BOT_PREFIX}habla"):
        content = content[len(f"{BOT_PREFIX}habla"):].strip()

    # si no hay nada que procesar, permitir que otros comandos se ejecuten
    if not (is_ia or is_habla or is_mention_direct):
        await bot.process_commands(message)
        return

    prompt = content.strip()

    if not prompt:
        await message.channel.send("💜 Dime qué quieres que responda.")
        await bot.process_commands(message)
        return

    # Generar respuesta IA (se ejecuta en hilo para no bloquear loop)
    async with message.channel.typing():
        response = await asyncio.to_thread(
            groq_chat_response,
            f"chan_{message.channel.id}",
            prompt
        )

    await message.channel.send(response)

    # Si corresponde hablar por voz (usaron #habla o @Bot habla ...)
    if (is_habla or False) and message.guild and len(response) <= MAX_TTS_CHARS:
        author_voice = message.author.voice
        vc = message.guild.voice_client

        if not author_voice or not author_voice.channel:
            await message.channel.send("💜 Para que hable, debes estar en un canal de voz y usar `#habla` o mencionar y decir 'habla'.")
        else:
            user_channel = author_voice.channel

            # Conectar si no está conectado
            if not vc:
                try:
                    vc = await user_channel.connect()
                    await message.channel.send(embed=embed_success("Conectada al canal", f"Me uní a **{user_channel.name}** para hablar 🎤"))
                except Exception:
                    log.exception("No pude unirme al canal de voz")
                    await message.channel.send(embed=embed_warning("No pude unirme", "No tengo permisos para unirme al canal de voz o ocurrió un error."))
                    await bot.process_commands(message)
                    return

            # Si el bot está en otro canal distinto -> avisar
            if vc.channel.id != user_channel.id:
                await message.channel.send(embed=embed_warning("Ya estoy en otro canal", "Estoy en otro canal de voz. Pide que me unan al mismo canal o usa `#join`."))
            else:
                ok = await speak_text_in_voice(vc, response)
                if not ok:
                    await message.channel.send("⚠️ No pude reproducir la voz. Comprueba permisos y que ffmpeg esté disponible.")

    # procesar otros comandos normalmente
    await bot.process_commands(message)


# ----------------------------
# Comandos
# ----------------------------
@bot.command(name="join")
async def cmd_join(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        channel = ctx.author.voice.channel
        if ctx.voice_client and ctx.voice_client.channel.id == channel.id:
            await ctx.send(embed=embed_info("Ya estoy aquí", f"Ya estoy conectada en **{channel.name}** ✨"))
            return
        vc = await channel.connect()
        await ctx.send(embed=embed_success("Conectada al canal", f"Me uní a **{channel.name}** 🎧"))
    else:
        await ctx.send(embed=embed_warning("No estás en un canal", "Debes unirte primero a un canal de voz."))

@bot.command(name="leave")
async def cmd_leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        q = music_queues.get(ctx.guild.id)
        if q: q.clear()
        await ctx.send(embed=embed_success("Desconectada", "Me desconecté del canal y limpié la cola 🧹"))
    else:
        await ctx.send(embed=embed_warning("No estoy conectada", "No estoy en ningún canal de voz."))


@bot.command(name="play")
@requires_same_voice_channel_after_join()
async def cmd_play(ctx, *, search: str):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(embed=embed_warning(
            "No estás en un canal de voz",
            "Debes unirte a un canal de voz antes de usar #play."
        ))
        return

    if not search:
        await ctx.send(embed=embed_warning("Falta el nombre", "Debes escribir el nombre de la canción o el link."))
        return

    # Conectar al canal si el bot aún no está
    if not ctx.voice_client:
        vc = await ctx.author.voice.channel.connect()

    queue = await ensure_queue_for_guild(ctx.guild.id)
    await ctx.send(embed=embed_info("Buscando…", f"🔍 **{search}**"))

    platform = detect_platform(search) if is_url(search) else 'search'
    songs_added = 0

    # Helper: enqueue single track
    async def enqueue_track(url, title, source_label="YouTube"):
        nonlocal songs_added
        if queue.enqueue(Song(url, title, str(ctx.author), ctx.channel, source=source_label)):
            songs_added += 1

    try:
        if platform == 'spotify':
            # For Spotify, we search YouTube for equivalent
            await ctx.send(embed=embed_info("Spotify link recibido", "Buscando equivalente en YouTube…"))
            # Try to extract metadata from spotify link (if yt-dlp can) to build a search query
            try:
                info = await extract_info(search)
                # info could be a dict with title/uploader etc
                if isinstance(info, dict):
                    title = info.get('title') or info.get('track') or ''
                    artist = ''
                    # Some spotify extractors put artist in 'artist' or 'artist_name' or 'uploader'
                    artist = info.get('artist') or info.get('artist_name') or info.get('uploader') or ''
                    query = (artist + ' ' + title).strip() if title else search
                else:
                    query = search
            except Exception:
                log.info("No se pudo extraer metadata de Spotify; usando búsqueda genérica")
                query = search

            # Search YouTube for the query (pick first result)
            try:
                yt_search = await extract_info(f"ytsearch1:{query}")
                if isinstance(yt_search, dict) and yt_search.get('entries'):
                    entry = yt_search['entries'][0]
                    url = entry.get('webpage_url') or entry.get('url')
                    title = entry.get('title', query)
                    await enqueue_track(url, title, source_label="Spotify → YouTube")
                else:
                    # fallback: try plain ytsearch
                    await ctx.send(embed=embed_warning("No encontré en YouTube", "Intentando búsqueda alternativa..."))
                    try:
                        yt_search2 = await extract_info(f"ytsearch1:{query}")
                        entry = yt_search2['entries'][0]
                        await enqueue_track(entry.get('webpage_url') or entry.get('url'), entry.get('title', query), source_label="Spotify → YouTube")
                    except Exception:
                        await ctx.send(embed=embed_error("Falló extracción", "No pude encontrar una versión en YouTube."))
            except Exception:
                log.exception("Error buscando en YouTube para Spotify link")
                # as last resort, search YouTube by raw URL string
                try:
                    yt_search3 = await extract_info(f"ytsearch1:{search}")
                    entry = yt_search3['entries'][0]
                    await enqueue_track(entry.get('webpage_url') or entry.get('url'), entry.get('title', search), source_label="Spotify → YouTube")
                except Exception:
                    await ctx.send(embed=embed_error("Falló todo", "No pude reproducir el enlace de Spotify ni encontrarlo en YouTube."))

        elif platform in ('soundcloud', 'deezer'):
            # For SoundCloud and Deezer, try to let yt-dlp stream directly
            await ctx.send(embed=embed_info("Reproduciendo desde plataforma", f"Intentando extraer audio directo de {platform}..."))
            try:
                info = await extract_info(search)
                # playlists or tracks
                if isinstance(info, dict) and info.get('entries'):
                    for count, entry in enumerate(info['entries']):
                        if count >= 200: break
                        url = entry.get('webpage_url') or entry.get('url')
                        title = entry.get('title', 'Unknown title')
                        await enqueue_track(url, title, source_label=platform.capitalize())
                    await ctx.send(embed=embed_music(
                        "Playlist añadido",
                        f"🎶 Se añadieron **{songs_added} canciones** desde {platform}.")
                    )
                elif isinstance(info, dict):
                    url = info.get('webpage_url') or info.get('url')
                    title = info.get('title', 'Unknown title')
                    await enqueue_track(url, title, source_label=platform.capitalize())
                    await ctx.send(embed=embed_music("Canción añadida", f"🎧 Ahora en cola: **{title}**\n📂 Posición: **{len(queue)}**"))
                else:
                    # unexpected shape -> fallback to YouTube search
                    raise RuntimeError("Info inesperada")
            except Exception:
                log.exception(f"Error extrayendo desde {platform}, intentando fallback a YouTube")
                # fallback: try to search YouTube by title or raw url
                try:
                    fallback = await extract_info(f"ytsearch1:{search}")
                    if isinstance(fallback, dict) and fallback.get('entries'):
                        entry = fallback['entries'][0]
                        await enqueue_track(entry.get('webpage_url') or entry.get('url'), entry.get('title', search), source_label=f"{platform} → YouTube")
                except Exception:
                    await ctx.send(embed=embed_error("Falló extracción", f"No pude reproducir ni extraer desde {platform} ni encontrar la versión en YouTube."))

        elif platform == 'youtube' or (not is_url(search)):
            # Already supports YouTube and plain searches
            # If it's a URL, extract info directly; if search, use ytsearch
            query = search if is_url(search) else f"ytsearch:{search}"
            info = await extract_info(query)

            if isinstance(info, dict) and 'entries' in info and info['entries']:
                for count, entry in enumerate(info['entries']):
                    if count >= 200: break
                    url = entry.get('webpage_url') or entry.get('url')
                    title = entry.get('title', 'Unknown title')
                    await enqueue_track(url, title, source_label="YouTube")
                await ctx.send(embed=embed_music(
                    "Playlist / Mix añadido",
                    f"🎶 Se añadieron **{songs_added} canciones** (máximo 200).\n📂 Cola actual: **{len(queue)}** / {queue.limit}"
                ))
            else:
                # single track result
                url = info.get('webpage_url') or info.get('url')
                title = info.get('title', 'Unknown title')
                await enqueue_track(url, title, source_label="YouTube")
                await ctx.send(embed=embed_music(
                    "Canción añadida",
                    f"🎧 Ahora en cola: **{title}**\n📂 Posición: **{len(queue)}**"
                ))

        else:
            # Search fallback (non-URL plain text)
            info = await extract_info(f"ytsearch:{search}")
            if isinstance(info, dict) and info.get('entries'):
                entry = info['entries'][0]
                await enqueue_track(entry.get('webpage_url') or entry.get('url'), entry.get('title', search), source_label="YouTube")
                await ctx.send(embed=embed_music("Canción añadida", f"🎧 Ahora en cola: **{entry.get('title','Unknown')}**\n📂 Posición: **{len(queue)}**"))
            else:
                await ctx.send(embed=embed_error("No encontrado", "No pude encontrar la canción en YouTube."))

    except Exception:
        log.exception("Error en cmd_play general")
        # Intentar fallback: búsqueda en YouTube con el texto raw
        try:
            fb = await extract_info(f"ytsearch1:{search}")
            if isinstance(fb, dict) and fb.get('entries'):
                e = fb['entries'][0]
                if queue.enqueue(Song(e.get('webpage_url') or e.get('url'), e.get('title', search), str(ctx.author), ctx.channel, source="YouTube (fallback)")):
                    songs_added = 1
                    await ctx.send(embed=embed_music("Añadido (fallback)", f"🎧 Añadido **{e.get('title','Unknown')}** (búsqueda fallback)"))
        except Exception:
            await ctx.send(embed=embed_error("Error irreparable", "No pude reproducir ni encontrar la canción. Comprueba que ffmpeg y yt-dlp estén instalados en el servidor."))

    # resumen final al usuario si se añadieron canciones
    if songs_added > 0:
        await ctx.send(embed=embed_music("Añadido a la cola", f"Se añadieron **{songs_added}** canciones. Posición final en cola: **{len(queue)}**"))

    await start_playback_if_needed(ctx.guild)


@bot.command(name="skip")
@requires_same_voice_channel_after_join()
async def cmd_skip(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send(embed=embed_info("Saltado", "⏭ Se saltó la canción actual."))
    else:
        await ctx.send(embed=embed_warning("Nada reproduciéndose", "No hay ninguna canción sonando."))

@bot.command(name="stop")
@requires_same_voice_channel_after_join()
async def cmd_stop(ctx):
    vc = ctx.voice_client
    if vc:
        vc.stop()
        q = music_queues.get(ctx.guild.id)
        if q: q.clear()
        await ctx.send(embed=embed_error("Reproducción detenida", "🛑 Cola eliminada y música detenida."))
    else:
        await ctx.send(embed=embed_warning("Nada reproduciéndose", "No hay música sonando."))

# ----------------------------
# Nueva vista y helpers para paginación de la cola
# ----------------------------
PER_PAGE = 50

def build_queue_embed(queue: MusicQueue, page: int = 0) -> discord.Embed:
    titles = list(queue._queue)
    total = len(titles)
    if total == 0:
        return embed_info("Cola vacía", "No hay canciones en la cola 🎵")

    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * PER_PAGE
    end = min(start + PER_PAGE, total)
    lines = [f"{i+1}. {titles[i].title}" for i in range(start, end)]
    desc = "\n".join(lines) if lines else "(sin resultados)"

    embed = embed_music("Cola actual", desc)
    embed.set_footer(text=f"Página {page+1}/{total_pages} — {total} canciones en cola")
    return embed

class QueueView(discord.ui.View):
    def __init__(self, author_id: int, guild_id: int, initial_page: int = 0):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.guild_id = guild_id
        self.page = initial_page

    async def _validate_user_voice(self, interaction: discord.Interaction) -> bool:
        # Validación similar a la de NowPlayingView: debe estar en el mismo canal de voz que el bot
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.response.send_message("❌ No estoy en un canal de voz.", ephemeral=True)
            return False
        if not interaction.user.voice or interaction.user.voice.channel.id != vc.channel.id:
            await interaction.response.send_message(
                "⚠️ Debes estar en el mismo canal de voz que yo para usar estos controles.", ephemeral=True
            )
            return False
        return True

    async def update_message(self, interaction: discord.Interaction):
        queue = music_queues.get(self.guild_id)
        if not queue or len(queue) == 0:
            await interaction.response.edit_message(embed=embed_info("Cola vacía", "No hay canciones en la cola 🎵"), view=None)
            return

        embed = build_queue_embed(queue, self.page)

        # Rebuild select options based on current queue size
        total = len(queue)
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        # recreate select options
        options = [discord.SelectOption(label=f"Página {i+1}", description=f"{i*PER_PAGE+1}-{min((i+1)*PER_PAGE, total)} canciones", value=str(i)) for i in range(total_pages)]

        # find select child in view and update
        select = None
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                select = child
                break
        if select:
            select.options = options
            select.placeholder = f"Ir a página (actual {self.page+1}/{total_pages})"

        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            # fallback: try to send a normal message
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user_voice(interaction):
            return
        queue = music_queues.get(self.guild_id)
        if not queue:
            await interaction.response.send_message("La cola fue eliminada o no existe.", ephemeral=True)
            return
        total = len(queue)
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        self.page = (self.page - 1) % total_pages
        await self.update_message(interaction)

    @discord.ui.button(label="Siguiente ➡️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user_voice(interaction):
            return
        queue = music_queues.get(self.guild_id)
        if not queue:
            await interaction.response.send_message("La cola fue eliminada o no existe.", ephemeral=True)
            return
        total = len(queue)
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        self.page = (self.page + 1) % total_pages
        await self.update_message(interaction)

    @discord.ui.select(placeholder="Ir a página...", min_values=1, max_values=1, options=[])
    async def page_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not await self._validate_user_voice(interaction):
            return
        try:
            chosen = int(select.values[0])
        except Exception:
            await interaction.response.send_message("Valor de página inválido.", ephemeral=True)
            return
        self.page = chosen
        await self.update_message(interaction)


# ----------------------------
# Reemplazo del comando queue para usar la paginación
# ----------------------------
@bot.command(name="queue")
@requires_same_voice_channel_after_join()
async def cmd_queue(ctx):
    queue = music_queues.get(ctx.guild.id)
    if not queue or len(queue) == 0:
        await ctx.send(embed=embed_info("Cola vacía", "No hay canciones en la cola 🎵"))
        return

    total = len(queue)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    view = QueueView(author_id=ctx.author.id, guild_id=ctx.guild.id, initial_page=0)

    # populate select options
    options = [discord.SelectOption(label=f"Página {i+1}", description=f"{i*PER_PAGE+1}-{min((i+1)*PER_PAGE, total)} canciones", value=str(i)) for i in range(total_pages)]
    # find the select inside view and set options
    for child in view.children:
        if isinstance(child, discord.ui.Select):
            child.options = options
            child.placeholder = f"Ir a página (1/{total_pages})"

    embed = build_queue_embed(queue, 0)
    await ctx.send(embed=embed, view=view)


@bot.command(name="now")
@requires_same_voice_channel_after_join()
async def cmd_now(ctx):
    song = current_song.get(ctx.guild.id)
    if song:
        await ctx.send(embed=embed_music("Ahora reproduciendo", f"🎧 **[{song.title}]({song.url})**\n💜 Pedido por {song.requester_name}"))
    else:
        await ctx.send(embed=embed_info("Nada reproduciéndose", "No hay música sonando actualmente."))


@bot.command(name="help")
async def cmd_help(ctx):
    embed = discord.Embed(
        title="💜 Ayuda — Comandos de Kaivoxx",
        description="Soy tu asistente musical 🎵 y de IA 🤖\nUsa los comandos con el prefijo `#`",
        color=0x9B59B6
    )

    # 🎵 Música
    embed.add_field(
        name="🎵 Música",
        value=(
            "`#join` → Me uno a tu canal de voz\n"
            "`#leave` → Salgo del canal de voz\n"
            "`#play <nombre o link>` → Reproduce música o playlists de YouTube\n"
            "`#skip` → Salta la canción actual\n"
            "`#stop` → Detiene la música y limpia la cola\n"
            "`#queue` → Muestra la cola de canciones (paginada)\n"
            "`#now` → Muestra la canción que está sonando"
        ),
        inline=False
    )

    # 🤖 Inteligencia Artificial
    embed.add_field(
        name="🤖 IA",
        value=(
            "`#ia <mensaje>` → Hablo contigo por texto usando IA\n"
            "`#habla <mensaje>` → Respondo con IA **y hablo por voz** 🎤\n"
            "`#limpiar_ia` → Borra la memoria de la conversación\n"
            "`#resumen <texto>` → Resume un texto largo\n"
            "`#personalidad` → Muestra mi personalidad"
        ),
        inline=False
    )

    # ℹ️ Extra
    embed.add_field(
        name="ℹ️ Información",
        value=(
            "También puedes **mencionarme** para hablar conmigo 💬\n"
            "Ejemplo: `@Kaivoxx hola`"
        ),
        inline=False
    )

    embed.set_footer(text="💜 Kaivoxx | Asistente musical y de IA")
    await ctx.send(embed=embed)

# ----------------------------
# Comandos Bot IA
# ----------------------------        
@bot.command(name="ia")
async def cmd_ia(ctx, *, prompt: str):
    async with ctx.typing():
        response = await asyncio.to_thread(
            groq_chat_response,
            f"chan_{ctx.channel.id}",
            prompt
        )

    await ctx.send(response)


@bot.command(name="habla")
async def cmd_habla(ctx, *, prompt: str = None):
    if not prompt:
        await ctx.send("💜 ¿Qué quieres que diga? 🎤")
        return

    async with ctx.typing():
        response = await asyncio.to_thread(
            groq_chat_response,
            f"chan_{ctx.channel.id}",
            prompt
        )

    await ctx.send(response)

    # Intentar hablar en voz:
    if len(response) > MAX_TTS_CHARS:
        await ctx.send("⚠️ La respuesta es muy larga para leerla en voz. Acorta el mensaje o usa #ia para solo texto.")
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("💜 Para que hable necesito que estés en un canal de voz. Únete y usa `#habla` ahí.")
        return

    user_channel = ctx.author.voice.channel
    vc = ctx.voice_client

    # Si el bot no está conectado, intentar unirse
    if not vc:
        try:
            vc = await user_channel.connect()
            await ctx.send(embed=embed_success("Conectada al canal", f"Me uní a **{user_channel.name}** para hablar 🎤"))
        except Exception:
            log.exception("No pude unirme al canal desde cmd_habla")
            await ctx.send(embed=embed_warning("No pude unirme", "No tengo permisos para unirme al canal de voz o ocurrió un error."))
            return

    # Si el bot está en otro canal distinto -> avisar y no hablar
    if vc and vc.channel.id != user_channel.id:
        await ctx.send(embed=embed_warning("Ya estoy en otro canal", "Estoy en otro canal de voz. Pide que me unan al mismo canal o usa #join."))
        return

    # Reproducir TTS
    ok = await speak_text_in_voice(vc, response)
    if not ok:
        await ctx.send("⚠️ No pude reproducir la voz. Comprueba permisos y que ffmpeg esté disponible.")


@bot.command(name="limpiar_ia")
async def cmd_limpiar_ia(ctx):
    key = f"chan_{ctx.channel.id}"

    if key in conversation_history:
        del conversation_history[key]
        await ctx.send("🧠 Memoria limpiada. Empezamos de cero 💜✨")
    else:
        await ctx.send("ℹ️ No había memoria previa en este canal.")


@bot.command(name="personalidad")
async def cmd_personalidad(ctx):
    await ctx.send(
        embed=embed_info(
            "¿Quién es Kaivoxx?",
            SYSTEM_PROMPT
        )
    )


@bot.command(name="resumen")
async def cmd_resumen(ctx, *, texto: str = None):
    if not texto:
        await ctx.send("✂️ Dame un texto para resumir.")
        return

    prompt = f"Resume el siguiente texto de forma clara y corta:\n\n{texto}"

    async with ctx.typing():
        response = await asyncio.to_thread(
            groq_chat_response,
            f"temp_resumen_{ctx.message.id}",
            prompt
        )

    conversation_history.pop(f"temp_resumen_{ctx.message.id}", None)

    await ctx.send(f"📌 **Resumen:**\n{response}")



# ----------------------------
# Run bot
# ----------------------------
bot.run(DISCORD_TOKEN)
