# ============================================================
# discord_multibot.py  (Versión completa + Railway ready)
# ============================================================

import os
import asyncio
import io
import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, List
import time

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
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Validación mínima
if not DISCORD_TOKEN:
    print("❌ ERROR: Falta DISCORD_TOKEN en variables de entorno")
    exit(1)

BOT_PREFIX = "#"
MAX_QUEUE_LENGTH = 200
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
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# ----------------------------
# Data structures
# ----------------------------
@dataclass
class Song:
    url: str
    title: str
    requester_name: str
    channel: discord.TextChannel

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
# YouTube extraction
# ----------------------------
YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'extract_flat': 'in_playlist',
    'skip_download': True,
}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)

async def extract_info(search_or_url: str):
    return await asyncio.to_thread(lambda: ytdl.extract_info(search_or_url, download=False))

def debug_ffmpeg_locations():
    print("=== DEBUG FFMPEG LOCATIONS ===")

    # Ver PATH
    print("PATH:", os.environ.get("PATH", ""))

    # Buscar ffmpeg con which
    ffm = subprocess.getoutput("which ffmpeg")
    print("which ffmpeg →", ffm)

    # Buscar todos los ffmpeg posibles
    possible_paths = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/bin/ffmpeg",
        "/nix/var/nix/profiles/default/bin/ffmpeg",
        "/nix/store",
    ]

    for path in possible_paths:
        print(f"exists({path}) =", os.path.exists(path))

debug_ffmpeg_locations()

def is_url(string: str) -> bool:
    return string.startswith(("http://", "https://"))

def find_ffmpeg():
    """
    Busca ffmpeg en rutas comunes de Railway/Nixpacks.
    """
    # 1. Si está en el PATH del contenedor
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    # 2. Rutas típicas de Nixpacks
    fallback_paths = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/nix/var/nix/profiles/default/bin/ffmpeg",
        "/bin/ffmpeg",
    ]

    for path in fallback_paths:
        if os.path.exists(path):
            return path

    # 3. Si no existe, avisamos
    raise FileNotFoundError("FFmpeg no encontrado en Railway.")

async def build_ffmpeg_source(url: str):
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "default_search": "auto",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            direct_url = info["url"]

        # Detectar FFmpeg automáticamente
        ffmpeg_exec = find_ffmpeg()
        print(f"[DEBUG] Usando FFmpeg en: {ffmpeg_exec}")

        return discord.FFmpegOpusAudio(
            direct_url,
            executable=ffmpeg_exec,
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        )

    except Exception as e:
        logging.error(f"Error construyendo FFmpeg source: {e}")
        return None



# ----------------------------
# DeepSeek IA
# ----------------------------
def add_to_history(context_key: str, role: str, content: str, max_len: int = 10):
    history = conversation_history.setdefault(context_key, [])
    history.append({'role': role, 'content': content})
    conversation_history[context_key] = history[-max_len:]

def deepseek_chat_response(context_key: str, user_prompt: str, model: str = "gpt-4o"):
    add_to_history(context_key, 'user', user_prompt)
    payload = {
        "model": model,
        "messages": conversation_history[context_key],
        "max_tokens": 300,
        "temperature": 0.6,
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    try:
        resp = requests.post(DEEPSEEK_API_URL, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']
        add_to_history(context_key, 'assistant', content)
        return content
    except Exception as e:
        log.exception("Error DeepSeek")
        return "❌ Error al solicitar la IA."

# ----------------------------
# TTS
# ----------------------------
async def speak_text_in_voice(vc: discord.VoiceClient, text: str):
    if not vc or not vc.is_connected():
        return

    def _generate_audio():
        try:
            voice_id = "pNInz6obpgDQGcFmaJgB"
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {"xi-api-key": ELEVENLABS_API_KEY,"Content-Type": "application/json"}
            payload = {"text": text,"model_id": "eleven_multilingual_v2","voice_settings": {"stability":0.4,"similarity_boost":0.7}}
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return io.BytesIO(response.content)
        except Exception as e:
            log.warning(f"Fallo ElevenLabs: {e}, usando gTTS")
            buf = io.BytesIO()
            gTTS(text, lang=TTS_LANGUAGE).write_to_fp(buf)
            buf.seek(0)
            return buf

    audio_buf = await asyncio.to_thread(_generate_audio)
    temp_path = f"tts_{vc.guild.id}.mp3"
    with open(temp_path, "wb") as f: f.write(audio_buf.read())
    source = discord.FFmpegPCMAudio(temp_path)
    vc.play(source, after=lambda e: (os.remove(temp_path) if os.path.exists(temp_path) else None) or (log.error(f"TTS error: {e}" if e else "")))
    while vc.is_playing():
        await asyncio.sleep(0.1)

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
# Decorador
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
# Now Playing View
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
# Now Playing
# ----------------------------
async def send_now_playing_embed(song: Song):
    guild_id = song.channel.guild.id
    view = NowPlayingView(bot, guild_id)
    embed = embed_music("Now Playing ✨", f"**[{song.title}]({song.url})**")
    if "watch?v=" in song.url:
        embed.set_thumbnail(url=f"https://img.youtube.com/vi/{song.url.split('=')[1]}/hqdefault.jpg")
    embed.add_field(name="Requested by", value=f"💜 {song.requester_name}", inline=True)
    embed.add_field(name="Source", value="YouTube 🎵", inline=True)
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
# Queue utils
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

    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name="#help 🎵 | 💜 Tu asistente musical y de IA favorita (IA en proceso)"
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    if message.content.startswith(f"{BOT_PREFIX}ia") or bot.user.mentioned_in(message):
        prompt = message.content.replace(f"{BOT_PREFIX}ia", "").replace(f"<@{bot.user.id}>", "").strip()
        if not prompt:
            await message.channel.send("Dime qué quieres que responda.")
        else:
            await message.channel.trigger_typing()
            response = await asyncio.to_thread(deepseek_chat_response, f"chan_{message.channel.id}", prompt)
            await message.channel.send(response)
            if message.guild.voice_client:
                await speak_text_in_voice(message.guild.voice_client, response)
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
        await channel.connect()
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

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    queue = await ensure_queue_for_guild(ctx.guild.id)
    await ctx.send(embed=embed_info("Buscando en YouTube…", f"🔍 **{search}**"))

    info = await extract_info(search if is_url(search) else f"ytsearch:{search}")
    songs_added = 0

    # ================================
    # ✔ FIX: evitar crash en playlists
    # ================================
    if isinstance(info, dict) and 'entries' in info and info['entries']:
        for count, entry in enumerate(info['entries']):
            if count >= 50:
                break

            if entry is None:
                continue

            url = entry.get("webpage_url") or entry.get("url")
            if not url:
                continue  # evita crashear con elementos vacíos

            title = entry.get('title', 'Unknown title')

            if queue.enqueue(Song(url, title, str(ctx.author), ctx.channel)):
                songs_added += 1

        await ctx.send(embed=embed_music(
            "Playlist / Mix añadido",
            f"🎶 Se añadieron **{songs_added} canciones** (máximo 50).\n📂 Cola actual: **{len(queue)}** / {queue.limit}"
        ))

    else:
        url = info.get('webpage_url') or info.get('url')
        title = info.get('title', 'Unknown title')
        if queue.enqueue(Song(url, title, str(ctx.author), ctx.channel)):
            songs_added = 1
        await ctx.send(embed=embed_music(
            "Canción añadida",
            f"🎧 Ahora en cola: **{title}**\n📂 Posición: **{len(queue)}**"
        ))

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

@bot.command(name="queue")
@requires_same_voice_channel_after_join()
async def cmd_queue(ctx):
    queue = music_queues.get(ctx.guild.id)
    if not queue or len(queue) == 0:
        await ctx.send(embed=embed_info("Cola vacía", "No hay canciones en la cola 🎵"))
        return
    desc = "\n".join([f"{i+1}. {s.title}" for i, s in enumerate(queue._queue)])
    await ctx.send(embed=embed_music("Cola actual", desc))

@bot.command(name="now")
@requires_same_voice_channel_after_join()
async def cmd_now(ctx):
    song = current_song.get(ctx.guild.id)
    if song:
        await ctx.send(embed=embed_music("Ahora reproduciendo", f"🎧 **[{song.title}]({song.url})**\n💜 Pedido por {song.requester_name}"))
    else:
        await ctx.send(embed=embed_info("Nada reproduciéndose", "No hay música sonando actualmente."))

# ----------------------------
# Run bot
# ----------------------------
bot.run(DISCORD_TOKEN)
