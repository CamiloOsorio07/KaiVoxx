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
GEMMA_API_KEY = os.environ.get("GEMMA_API_KEY")

GEMMA_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

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
    'cookiefile': 'cookies.txt',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'extract_flat': 'in_playlist',
    'skip_download': True,
}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)

async def extract_info(search_or_url: str):
    return await asyncio.to_thread(lambda: ytdl.extract_info(search_or_url, download=False))

def is_url(string: str) -> bool:
    return string.startswith(("http://", "https://"))

async def build_ffmpeg_source(video_url: str):
    before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

    def _get_url():
        info = ytdl.extract_info(video_url, download=False)
        if 'url' in info:
            return info['url']
        return info.get('formats', [])[-1].get('url')

    direct_url = await asyncio.to_thread(_get_url)
    return discord.FFmpegOpusAudio(direct_url, before_options=before_options)

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



def gemma_chat_response(context_key: str, user_prompt: str):
    add_to_history(context_key, "user", user_prompt)

    prompt_text = build_gemma_prompt(conversation_history[context_key])

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt_text}]
            }
        ],
        "generationConfig": {
            "temperature": 0.6,
            "maxOutputTokens": 300,
            "topP": 0.9,
            "topK": 40
        }
    }

    try:
        response = requests.post(
            f"{GEMMA_API_URL}?key={GEMMA_API_KEY}",
            json=payload,
            timeout=20
        )
        response.raise_for_status()

        data = response.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        add_to_history(context_key, "assistant", content)
        return content

    except Exception:
        log.exception("Error Gemma IA")
        return "❌ Tuve un problema pensando… inténtalo otra vez 💜"



# ----------------------------
# TTS (Google gTTS usando texto de Gemma)
# ----------------------------
async def speak_text_in_voice(vc: discord.VoiceClient, text: str):
    if not vc or not vc.is_connected():
        return

    if len(text) > MAX_TTS_CHARS:
        return  # no leer textos largos

    clean_text = text.replace("*", "").replace("_", "").replace("`", "")

    def _generate_audio():
        buf = io.BytesIO()
        gTTS(
            text=clean_text,
            lang=TTS_LANGUAGE,
            slow=False
        ).write_to_fp(buf)
        buf.seek(0)
        return buf

    audio_buf = await asyncio.to_thread(_generate_audio)

    temp_path = f"tts_{vc.guild.id}.mp3"
    with open(temp_path, "wb") as f:
        f.write(audio_buf.read())

    source = discord.FFmpegPCMAudio(temp_path)
    vc.play(
        source,
        after=lambda e: os.remove(temp_path) if os.path.exists(temp_path) else None
    )

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

    is_ia = message.content.startswith(f"{BOT_PREFIX}ia")
    is_habla = message.content.startswith(f"{BOT_PREFIX}habla")
    is_mention = bot.user.mentioned_in(message)

    if is_ia or is_habla or is_mention:
        prompt = (
            message.content
            .replace(f"{BOT_PREFIX}ia", "")
            .replace(f"{BOT_PREFIX}habla", "")
            .replace(f"<@{bot.user.id}>", "")
            .strip()
        )

        if not prompt:
            await message.channel.send("💜 Dime qué quieres que responda.")
            return

        # 👇 ESTA ES LA FORMA CORRECTA
        async with message.channel.typing():
            response = await asyncio.to_thread(
                gemma_chat_response,
                f"chan_{message.channel.id}",
                prompt
            )

        await message.channel.send(response)

        # 🔊 SOLO HABLA SI:
        # - Usaron #habla
        # - Está en un canal de voz
        # - El texto no es muy largo
        if (
            is_habla
            and message.guild
            and message.guild.voice_client
            and len(response) <= MAX_TTS_CHARS
        ):
            await speak_text_in_voice(
                message.guild.voice_client,
                response
            )

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

    # Conectar al canal si el bot aún no está
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    queue = await ensure_queue_for_guild(ctx.guild.id)
    await ctx.send(embed=embed_info("Buscando en YouTube…", f"🔍 **{search}**"))

    info = await extract_info(search if is_url(search) else f"ytsearch:{search}")
    songs_added = 0

    if isinstance(info, dict) and 'entries' in info and info['entries']:
        for count, entry in enumerate(info['entries']):
            if count >= 200: break
            url = entry.get('webpage_url') or entry.get('url')
            title = entry.get('title', 'Unknown title')
            if queue.enqueue(Song(url, title, str(ctx.author), ctx.channel)):
                songs_added += 1
        await ctx.send(embed=embed_music(
            "Playlist / Mix añadido",
            f"🎶 Se añadieron **{songs_added} canciones** (máximo 200).\n📂 Cola actual: **{len(queue)}** / {queue.limit}"
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
# Comandos Bot IA
# ----------------------------        

@bot.command(name="ia")
async def cmd_ia(ctx, *, prompt: str):
    async with ctx.typing():
        response = await asyncio.to_thread(
            gemma_chat_response,
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
            gemma_chat_response,
            f"chan_{ctx.channel.id}",
            prompt
        )

    await ctx.send(response)

    if ctx.voice_client and len(response) <= MAX_TTS_CHARS:
        await speak_text_in_voice(ctx.voice_client, response)


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
            gemma_chat_response,
            f"temp_resumen_{ctx.message.id}",
            prompt
        )

    conversation_history.pop(f"temp_resumen_{ctx.message.id}", None)

    await ctx.send(f"📌 **Resumen:**\n{response}")



# ----------------------------
# Run bot
# ----------------------------
bot.run(DISCORD_TOKEN)
