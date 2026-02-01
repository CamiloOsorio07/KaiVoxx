"""
KaiVoxx - Refactor a single-file Clean Architecture version
- Mantiene compatibilidad con Railway/entorno original (env vars, yt-dlp, ffmpeg, gTTS)
- Organización: domain | application (use cases) | infrastructure (clients) | adapter (discord wiring)

Nota: revisa variables de entorno: DISCORD_TOKEN, GROQ_API_KEY, YTDLP_COOKIES_BASE64 / YTDLP_COOKIES
"""

import os
import base64
import tempfile
import atexit
import asyncio
import io
import logging
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, List

import discord
from discord.ext import commands
import requests
import yt_dlp
from gtts import gTTS

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kai_voxx")

# ----------------------------
# Config
# ----------------------------
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

BOT_PREFIX = "#"
MAX_QUEUE_LENGTH = 500
MAX_TTS_CHARS = 180
TTS_LANGUAGE = "es"
SYSTEM_PROMPT = (
    "Eres Kaivoxx, una asistente virtual estilo VTuber. "
    "Eres amigable, expresiva, un poco sarcástica pero respetuosa. "
    "Hablas en español latino, usas emojis con moderación 💜✨. "
    "Respondes de forma clara y no demasiado larga. "
    "Si te piden algo peligroso o ilegal, te niegas amablemente."
)

# ----------------------------
# Cookies helper (Infra)
# ----------------------------

def load_cookies_from_env() -> Optional[str]:
    cookies_b64 = os.getenv("YTDLP_COOKIES_BASE64")
    cookies_txt = os.getenv("YTDLP_COOKIES")

    if not cookies_b64 and not cookies_txt:
        log.info("No hay cookies configuradas.")
        return None

    try:
        if cookies_b64:
            cookies_data = base64.b64decode(cookies_b64).decode("utf-8")
        else:
            cookies_data = cookies_txt

        if "Netscape HTTP Cookie File" not in cookies_data and "# Netscape HTTP Cookie File" not in cookies_data:
            raise ValueError("Formato de cookies inválido: falta header 'Netscape HTTP Cookie File'")

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
        tmp.write(cookies_data)
        tmp.close()
        log.info(f"Cookies cargadas correctamente: {tmp.name}")
        return tmp.name
    except Exception as e:
        log.exception("Error cargando cookies")
        return None

COOKIE_FILE = load_cookies_from_env()
if COOKIE_FILE:
    def _cleanup_cookie_file():
        try:
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)
                log.info(f"Cookie file temporal eliminado: {COOKIE_FILE}")
        except Exception:
            log.warning("No pude borrar cookie file temporal")
    atexit.register(_cleanup_cookie_file)

# ----------------------------
# Domain
# ----------------------------
@dataclass
class Song:
    url: str
    title: str
    requester_name: str
    channel_id: int
    source: str = "YouTube"

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

# ----------------------------
# Infrastructure - yt-dlp client
# ----------------------------
YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'extract_flat': 'in_playlist',
    'ignoreerrors': True,
    'skip_download': True,
    'nocheckcertificate': True,
}
if COOKIE_FILE:
    YTDL_OPTS['cookiefile'] = COOKIE_FILE

class YTDLClient:
    def __init__(self, opts=None):
        self.opts = opts or YTDL_OPTS

    def get_ytdl(self):
        # instanciar por llamada evita corrupciones en entornos serverless
        return yt_dlp.YoutubeDL(self.opts)

    async def extract_info(self, query: str):
        ytdl = self.get_ytdl()
        return await asyncio.to_thread(lambda: ytdl.extract_info(query, download=False))

    async def build_ffmpeg_source(self, video_url: str):
        before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

        def _get_stream():
            ytdl = self.get_ytdl()
            info = ytdl.extract_info(video_url, download=False)
            if not info:
                raise RuntimeError("No se pudo extraer info con yt-dlp")

            stream_url = None
            if isinstance(info.get('url'), str):
                stream_url = info['url']
            else:
                formats = info.get('formats') or []
                for f in reversed(formats):
                    if f.get('acodec') != 'none' and f.get('url') and f.get('ext') in ('m4a','webm','opus','ogg','mp3'):
                        stream_url = f['url']
                        break

            if not stream_url:
                raise RuntimeError('No se obtuvo URL de stream válida')

            headers = info.get('http_headers', {})
            return stream_url, headers

        stream_url, headers = await asyncio.to_thread(_get_stream)
        headers_str = ''.join(f"{k}: {v}\r\n" for k,v in headers.items())
        return discord.FFmpegOpusAudio(stream_url, before_options=before_options, options=f'-headers "{headers_str}"')

# ----------------------------
# Infrastructure - IA client (Groq)
# ----------------------------
class IAClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('GROQ_API_KEY')

    def add_to_history(self, history_dict: Dict[str, List[dict]], context_key: str, role: str, content: str, max_len: int = 10):
        history = history_dict.setdefault(context_key, [])
        if not history:
            history.append({'role':'system','content': SYSTEM_PROMPT})
        history.append({'role': role, 'content': content})
        history_dict[context_key] = history[-max_len:]

    def build_messages(self, history: List[dict]):
        messages = [{'role':'system','content':SYSTEM_PROMPT}]
        for msg in history:
            if msg['role'] in ('user','assistant'):
                messages.append(msg)
        return messages

    def chat_response(self, history_store: Dict[str, List[dict]], context_key: str, user_prompt: str) -> str:
        try:
            self.add_to_history(history_store, context_key, 'user', user_prompt)
            messages = self.build_messages(history_store.get(context_key, []))
            payload = {
                'model': 'llama-3.1-8b-instant',
                'messages': messages,
                'temperature': 0.6,
                'max_tokens': 300
            }
            headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
            r = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=20)
            r.raise_for_status()
            content = r.json()['choices'][0]['message']['content'].strip()
            self.add_to_history(history_store, context_key, 'assistant', content)
            return content
        except Exception:
            log.exception('Error Groq IA')
            return '❌ Tuve un problema pensando… inténtalo otra vez 💜'

# ----------------------------
# Infrastructure - TTS
# ----------------------------
class TTSService:
    def __init__(self, language: str = TTS_LANGUAGE, max_chars: int = MAX_TTS_CHARS):
        self.language = language
        self.max_chars = max_chars

    async def speak(self, vc: discord.VoiceClient, text: str) -> bool:
        if not vc or not vc.is_connected():
            log.warning('TTS: VoiceClient no conectado')
            return False
        if len(text) > self.max_chars:
            log.info('Texto demasiado largo para TTS')
            return False

        clean_text = text.replace('*','').replace('_','').replace('`','')

        def _gen():
            buf = io.BytesIO()
            gTTS(text=clean_text, lang=self.language, slow=False).write_to_fp(buf)
            buf.seek(0)
            return buf

        try:
            audio_buf = await asyncio.to_thread(_gen)
        except Exception:
            log.exception('Error generando TTS')
            return False

        temp_path = f"tts_{vc.guild.id}.mp3"
        try:
            with open(temp_path,'wb') as f:
                f.write(audio_buf.read())

            if vc.is_playing():
                try:
                    vc.stop()
                except Exception:
                    log.exception('No se pudo detener reproducción previa')

            source = discord.FFmpegOpusAudio(temp_path)
            played = asyncio.Event()

            def _after(err):
                if err:
                    log.exception(f'TTS playback error: {err}')
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass
                # signal completion
                try:
                    loop = asyncio.get_event_loop()
                    loop.call_soon_threadsafe(played.set)
                except Exception:
                    pass

            vc.play(source, after=_after)
            # wait until playback finished
            await played.wait()
            return True
        except Exception:
            log.exception('Error reproduciendo TTS')
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            return False

# ----------------------------
# Application / Use cases
# ----------------------------
class MusicService:
    def __init__(self, ytdl_client: YTDLClient):
        self.ytdl = ytdl_client
        self.queues: Dict[int, MusicQueue] = {}
        self.current_song: Dict[int, Song] = {}
        self.now_playing_messages: Dict[int, discord.Message] = {}

    def ensure_queue(self, guild_id: int) -> MusicQueue:
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue(limit=MAX_QUEUE_LENGTH)
        return self.queues[guild_id]

    async def enqueue_search(self, guild_id: int, requester_name: str, channel_id: int, search: str) -> int:
        queue = self.ensure_queue(guild_id)
        info = await self.ytdl.extract_info(search if is_url(search) else f"ytsearch:{search}")
        songs_added = 0
        if isinstance(info, dict) and 'entries' in info and info['entries']:
            for count, entry in enumerate(info['entries']):
                if count >= 200: break
                url = entry.get('webpage_url') or entry.get('url')
                title = entry.get('title','Unknown title')
                if queue.enqueue(Song(url, title, requester_name, channel_id)):
                    songs_added += 1
        else:
            url = info.get('webpage_url') or info.get('url')
            title = info.get('title','Unknown title')
            if queue.enqueue(Song(url, title, requester_name, channel_id)):
                songs_added = 1
        return songs_added

    async def start_playback_if_needed(self, guild: discord.Guild, bot: commands.Bot):
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return
        queue = self.queues.get(guild.id)
        if not queue or len(queue) == 0:
            return
        if not vc.is_playing():
            song = queue.dequeue()
            if not song:
                return
            try:
                source = await self.ytdl.build_ffmpeg_source(song.url)
                # play and schedule next
                def _after(err):
                    if err:
                        log.error(f"Playback error: {err}")
                    # schedule next on bot loop
                    try:
                        asyncio.run_coroutine_threadsafe(self.start_playback_if_needed(guild, bot), bot.loop)
                    except Exception:
                        pass

                vc.play(source, after=_after)
                self.current_song[guild.id] = song
                # send now playing embed async
                asyncio.create_task(self.send_now_playing_embed(song, bot))
            except Exception:
                log.exception('Error iniciando reproducción')
                try:
                    ch = bot.get_channel(song.channel_id)
                    if ch:
                        asyncio.create_task(ch.send('❌ Error al preparar el audio. Saltando...'))
                except Exception:
                    pass

    async def send_now_playing_embed(self, song: Song, bot: commands.Bot):
        ch = bot.get_channel(song.channel_id)
        if not ch:
            return
        embed = make_embed('music', 'Now Playing ✨', f"**[{song.title}]({song.url})**")
        if 'watch?v=' in song.url:
            try:
                vid = song.url.split('=')[1]
                embed.set_thumbnail(url=f'https://img.youtube.com/vi/{vid}/hqdefault.jpg')
            except Exception:
                pass
        embed.add_field(name='Requested by', value=f'💜 {song.requester_name}', inline=True)
        embed.add_field(name='Source', value=song.source + ' 🎵', inline=True)
        embed.add_field(name='Time Elapsed', value='0:00', inline=False)
        msg = await ch.send(embed=embed, view=NowPlayingView(bot, song.channel_id))
        self.now_playing_messages[song.channel_id] = msg
        asyncio.create_task(self._update_now_playing_bar(song.channel_id))

    async def _update_now_playing_bar(self, channel_id: int):
        start_time = time.time()
        msg = self.now_playing_messages.get(channel_id)
        if not msg: return
        while True:
            vc = msg.guild.voice_client
            if not vc or not vc.is_playing(): break
            elapsed = int(time.time() - start_time)
            embed = msg.embeds[0]
            try:
                embed.set_field_at(2, name='Time Elapsed', value=f"{elapsed//60:02}:{elapsed%60:02}", inline=False)
                await msg.edit(embed=embed)
            except Exception:
                break
            await asyncio.sleep(1)

# ----------------------------
# Utilities
# ----------------------------

def is_url(string: str) -> bool:
    return string.startswith(("http://","https://")) or string.startswith('spotify:')

def detect_platform(text: str) -> str:
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
# Embeds helper
# ----------------------------

def make_embed(type: str, title: str, description: str):
    colors = {"success": 0x2ECC71, "info": 0x9B59B6, "warning": 0xF1C40F, "error": 0xE74C3C, "music": 0x9B59B6}
    icons = {"success": "✅ ✨", "info": "ℹ️ 🔹", "warning": "⚠️ ✴️", "error": "❌ ✖️", "music": "🎵 🎶"}
    embed = discord.Embed(title=f"{icons.get(type,'')} {title}", description=description, color=colors.get(type, 0x9B59B6))
    if type == 'music':
        embed.set_footer(text='💜 Disfruta tu música 💜')
    return embed

embed_success = lambda t,d: make_embed('success', t, d)
embed_info    = lambda t,d: make_embed('info', t, d)
embed_warning = lambda t,d: make_embed('warning', t, d)
embed_error   = lambda t,d: make_embed('error', t, d)
embed_music   = lambda t,d: make_embed('music', t, d)

# ----------------------------
# Discord Views (Infra-specific UI)
# ----------------------------
class NowPlayingView(discord.ui.View):
    def __init__(self, bot: commands.Bot, channel_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.channel_id = channel_id

    async def _validate_user_voice(self, interaction: discord.Interaction) -> bool:
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.response.send_message('❌ No estoy en un canal de voz.', ephemeral=True)
            return False
        if not interaction.user.voice or interaction.user.voice.channel.id != vc.channel.id:
            await interaction.response.send_message('⚠️ Debes estar en el mismo canal de voz que yo para usar este botón.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='⏯ Pausa/Resume', style=discord.ButtonStyle.primary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user_voice(interaction):
            return
        vc = interaction.guild.voice_client
        if vc.is_paused():
            vc.resume()
            await interaction.response.send_message('▶️ Reanudado', ephemeral=True)
        else:
            vc.pause()
            await interaction.response.send_message('⏸️ Pausado', ephemeral=True)

    @discord.ui.button(label='⏭ Skip', style=discord.ButtonStyle.green)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user_voice(interaction):
            return
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message('⏭ Canción saltada', ephemeral=True)
        else:
            await interaction.response.send_message('❌ No hay música sonando.', ephemeral=True)

    @discord.ui.button(label='🛑 Stop', style=discord.ButtonStyle.red)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user_voice(interaction):
            return
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            svc = bot_app.music_service
            q = svc.queues.get(interaction.guild.id)
            if q:
                q.clear()
            await interaction.response.send_message('🛑 Música detenida y cola vaciada', ephemeral=True)
        else:
            await interaction.response.send_message('❌ No hay música sonando.', ephemeral=True)

# QueueView
PER_PAGE = 50
class QueueView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author_id: int, channel_id: int, initial_page: int = 0):
        super().__init__(timeout=None)
        self.bot = bot
        self.author_id = author_id
        self.channel_id = channel_id
        self.page = initial_page
        # select placeholder
        self.add_item(discord.ui.Select(placeholder='Ir a página...', min_values=1, max_values=1, options=[]))

    async def _validate_user_voice(self, interaction: discord.Interaction) -> bool:
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.response.send_message('❌ No estoy en un canal de voz.', ephemeral=True)
            return False
        if not interaction.user.voice or interaction.user.voice.channel.id != vc.channel.id:
            await interaction.response.send_message('⚠️ Debes estar en el mismo canal de voz que yo para usar estos controles.', ephemeral=True)
            return False
        return True

    async def update_message(self, interaction: discord.Interaction):
        svc = bot_app.music_service
        queue = svc.queues.get(self.bot.get_channel(self.channel_id).guild.id)
        if not queue or len(queue) == 0:
            await interaction.response.edit_message(embed=embed_info('Cola vacía','No hay canciones en la cola 🎵'), view=None)
            return
        embed = build_queue_embed(queue, self.page)
        total = len(queue)
        total_pages = max(1,(total+PER_PAGE-1)//PER_PAGE)
        options = [discord.SelectOption(label=f'Página {i+1}', description=f'{i*PER_PAGE+1}-{min((i+1)*PER_PAGE,total)} canciones', value=str(i)) for i in range(total_pages)]
        select = None
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                select = child
                break
        if select:
            select.options = options
            select.placeholder = f'Ir a página (actual {self.page+1}/{total_pages})'
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label='⬅️ Anterior', style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user_voice(interaction):
            return
        svc = bot_app.music_service
        queue = svc.queues.get(interaction.guild.id)
        if not queue:
            await interaction.response.send_message('La cola fue eliminada o no existe.', ephemeral=True)
            return
        total = len(queue)
        total_pages = max(1,(total+PER_PAGE-1)//PER_PAGE)
        self.page = (self.page-1) % total_pages
        await self.update_message(interaction)

    @discord.ui.button(label='Siguiente ➡️', style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user_voice(interaction):
            return
        svc = bot_app.music_service
        queue = svc.queues.get(interaction.guild.id)
        if not queue:
            await interaction.response.send_message('La cola fue eliminada o no existe.', ephemeral=True)
            return
        total = len(queue)
        total_pages = max(1,(total+PER_PAGE-1)//PER_PAGE)
        self.page = (self.page+1) % total_pages
        await self.update_message(interaction)

    @discord.ui.select(placeholder='Ir a página...', min_values=1, max_values=1, options=[])
    async def page_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not await self._validate_user_voice(interaction):
            return
        try:
            chosen = int(select.values[0])
        except Exception:
            await interaction.response.send_message('Valor de página inválido.', ephemeral=True)
            return
        self.page = chosen
        await self.update_message(interaction)

# ----------------------------
# Application container (simple)
# ----------------------------
class AppContainer:
    def __init__(self):
        self.ytdl = YTDLClient()
        self.ia = IAClient()
        self.tts = TTSService()
        self.music_service = MusicService(self.ytdl)

bot_app = AppContainer()

# ----------------------------
# Discord Adapter (wiring)
# ----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)

# Helper decorator
def requires_same_voice_channel_after_join():
    async def predicate(ctx):
        vc = ctx.voice_client
        if not vc:
            if ctx.command.name != 'play':
                await ctx.send(embed=embed_warning('No estoy conectada','Primero debo unirme a un canal con #join o usando play'))
                return False
            return True
        if not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            await ctx.send(embed=embed_warning('Canal incorrecto','Debes estar en el mismo canal de voz que yo para usar este comando.'))
            return False
        return True
    return commands.check(predicate)

# Events
@bot.event
async def on_ready():
    log.info(f"Bot conectado como {bot.user}")
    activity = discord.Activity(type=discord.ActivityType.listening, name="#help 🎵 | 💜 Tu asistente musical y de IA favorita (IA en proceso)")
    await bot.change_presence(status=discord.Status.online, activity=activity)

# on_message - routes IA mentions and habla
conversation_history: Dict[str, List[dict]] = {}

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    content = (message.content or '').strip()
    mention_prefixes = []
    if bot.user:
        mention_prefixes = [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]

    is_ia = content.startswith(f"{BOT_PREFIX}ia")
    is_habla = content.startswith(f"{BOT_PREFIX}habla")
    is_mention_direct = bot.user and bot.user.mentioned_in(message)

    for mp in mention_prefixes:
        if content.startswith(mp):
            after = content[len(mp):].strip()
            if after.lower().startswith('ia ') or after.lower() == 'ia':
                is_ia = True
                content = after[len('ia'):].strip()
            elif after.lower().startswith('habla ') or after.lower() == 'habla':
                is_habla = True
                content = after[len('habla'):].strip()
            else:
                is_mention_direct = True
                content = after
            break

    if is_ia and content.startswith(f"{BOT_PREFIX}ia"):
        content = content[len(f"{BOT_PREFIX}ia"):].strip()
    if is_habla and content.startswith(f"{BOT_PREFIX}habla"):
        content = content[len(f"{BOT_PREFIX}habla"):].strip()

    if not (is_ia or is_habla or is_mention_direct):
        await bot.process_commands(message)
        return

    prompt = content.strip()
    if not prompt:
        await message.channel.send('💜 Dime qué quieres que responda.')
        await bot.process_commands(message)
        return

    async with message.channel.typing():
        response = await asyncio.to_thread(bot_app.ia.chat_response, conversation_history, f"chan_{message.channel.id}", prompt)

    await message.channel.send(response)

    # habla
    if (is_habla or False) and message.guild and len(response) <= MAX_TTS_CHARS:
        author_voice = message.author.voice
        vc = message.guild.voice_client
        if not author_voice or not author_voice.channel:
            await message.channel.send('💜 Para que hable, debes estar en un canal de voz y usar `#habla` o mencionar y decir \"habla\".')
        else:
            user_channel = author_voice.channel
            if not vc:
                try:
                    vc = await user_channel.connect()
                    await message.channel.send(embed=embed_success('Conectada al canal', f"Me uní a **{user_channel.name}** para hablar 🎤"))
                except Exception:
                    log.exception('No pude unirme al canal de voz')
                    await message.channel.send(embed=embed_warning('No pude unirme','No tengo permisos para unirme al canal de voz o ocurrió un error.'))
                    await bot.process_commands(message)
                    return

            if vc.channel.id != user_channel.id:
                await message.channel.send(embed=embed_warning('Ya estoy en otro canal','Estoy en otro canal de voz. Pide que me unan al mismo canal o usa `#join`.'))
            else:
                ok = await bot_app.tts.speak(vc, response)
                if not ok:
                    await message.channel.send('⚠️ No pude reproducir la voz. Comprueba permisos y que ffmpeg esté disponible.')

    await bot.process_commands(message)

# Commands (usecases delegados)
@bot.command(name='join')
async def cmd_join(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        channel = ctx.author.voice.channel
        if ctx.voice_client and ctx.voice_client.channel.id == channel.id:
            await ctx.send(embed=embed_info('Ya estoy aquí', f"Ya estoy conectada en **{channel.name}** ✨"))
            return
        vc = await channel.connect()
        await ctx.send(embed=embed_success('Conectada al canal', f"Me uní a **{channel.name}** 🎧"))
    else:
        await ctx.send(embed=embed_warning('No estás en un canal', 'Debes unirte primero a un canal de voz.'))

@bot.command(name='leave')
async def cmd_leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        svc = bot_app.music_service
        q = svc.queues.get(ctx.guild.id)
        if q: q.clear()
        await ctx.send(embed=embed_success('Desconectada', 'Me desconecté del canal y limpié la cola 🧹'))
    else:
        await ctx.send(embed=embed_warning('No estoy conectada', 'No estoy en ningún canal de voz.'))

@bot.command(name='play')
@requires_same_voice_channel_after_join()
async def cmd_play(ctx, *, search: str):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(embed=embed_warning('No estás en un canal de voz','Debes unirte a un canal de voz antes de usar #play.'))
        return
    if not search:
        await ctx.send(embed=embed_warning('Falta el nombre','Debes escribir el nombre de la canción o el link.'))
        return

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    await ctx.send(embed=embed_info('Buscando en YouTube…', f"🔍 **{search}**"))
    svc = bot_app.music_service
    songs_added = await svc.enqueue_search(ctx.guild.id, str(ctx.author), ctx.channel.id, search)

    if songs_added == 0:
        await ctx.send(embed=embed_warning('No se añadieron canciones', 'No pude encontrar resultados.'))
    elif songs_added == 1:
        await ctx.send(embed=embed_music('Canción añadida', f"🎧 Ahora en cola: **{search}**\n📂 Posición: **{len(svc.queues.get(ctx.guild.id))}**"))
    else:
        await ctx.send(embed=embed_music('Playlist / Mix añadido', f"🎶 Se añadieron **{songs_added} canciones** (máximo 200).\n📂 Cola actual: **{len(svc.queues.get(ctx.guild.id))}** / {svc.queues.get(ctx.guild.id).limit}"))

    await svc.start_playback_if_needed(ctx.guild, bot)

@bot.command(name='skip')
@requires_same_voice_channel_after_join()
async def cmd_skip(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send(embed=embed_info('Saltado', '⏭ Se saltó la canción actual.'))
    else:
        await ctx.send(embed=embed_warning('Nada reproduciéndose','No hay ninguna canción sonando.'))

@bot.command(name='stop')
@requires_same_voice_channel_after_join()
async def cmd_stop(ctx):
    vc = ctx.voice_client
    if vc:
        vc.stop()
        svc = bot_app.music_service
        q = svc.queues.get(ctx.guild.id)
        if q: q.clear()
        await ctx.send(embed=embed_error('Reproducción detenida','🛑 Cola eliminada y música detenida.'))
    else:
        await ctx.send(embed=embed_warning('Nada reproduciéndose','No hay música sonando.'))

@bot.command(name='queue')
@requires_same_voice_channel_after_join()
async def cmd_queue(ctx):
    svc = bot_app.music_service
    queue = svc.queues.get(ctx.guild.id)
    if not queue or len(queue) == 0:
        await ctx.send(embed=embed_info('Cola vacía','No hay canciones en la cola 🎵'))
        return
    total = len(queue)
    total_pages = max(1,(total+PER_PAGE-1)//PER_PAGE)
    view = QueueView(bot, ctx.author.id, ctx.channel.id, initial_page=0)
    options = [discord.SelectOption(label=f'Página {i+1}', description=f'{i*PER_PAGE+1}-{min((i+1)*PER_PAGE,total)} canciones', value=str(i)) for i in range(total_pages)]
    for child in view.children:
        if isinstance(child, discord.ui.Select):
            child.options = options
            child.placeholder = f'Ir a página (1/{total_pages})'
    embed = build_queue_embed(queue, 0)
    await ctx.send(embed=embed, view=view)

@bot.command(name='now')
@requires_same_voice_channel_after_join()
async def cmd_now(ctx):
    svc = bot_app.music_service
    song = svc.current_song.get(ctx.guild.id)
    if song:
        await ctx.send(embed=embed_music('Ahora reproduciendo', f"🎧 **[{song.title}]({song.url})**\n💜 Pedido por {song.requester_name}"))
    else:
        await ctx.send(embed=embed_info('Nada reproduciéndose','No hay música sonando actualmente.'))

@bot.command(name='help')
async def cmd_help(ctx):
    embed = discord.Embed(title='💜 Ayuda — Comandos de Kaivoxx', description='Soy tu asistente musical 🎵 y de IA 🤖\nUsa los comandos con el prefijo `#`', color=0x9B59B6)
    embed.add_field(name='🎵 Música', value=('`#join` → Me uno a tu canal de voz\n' '`#leave` → Salgo del canal de voz\n' '`#play <nombre o link>` → Reproduce música o playlists de YouTube\n' '`#skip` → Salta la canción actual\n' '`#stop` → Detiene la música y limpia la cola\n' '`#queue` → Muestra la cola de canciones (paginada)\n' '`#now` → Muestra la canción que está sonando'), inline=False)
    embed.add_field(name='🤖 IA', value=('`#ia <mensaje>` → Hablo contigo por texto usando IA\n' '`#habla <mensaje>` → Respondo con IA **y hablo por voz** 🎤\n' '`#limpiar_ia` → Borra la memoria de la conversación\n' '`#resumen <texto>` → Resume un texto largo\n' '`#personalidad` → Muestra mi personalidad'), inline=False)
    embed.add_field(name='ℹ️ Información', value=('También puedes **mencionarme** para hablar conmigo 💬\n' 'Ejemplo: `@Kaivoxx hola`'), inline=False)
    embed.set_footer(text='💜 Kaivoxx | Asistente musical y de IA')
    await ctx.send(embed=embed)

# IA Commands
@bot.command(name='ia')
async def cmd_ia(ctx, *, prompt: str):
    async with ctx.typing():
        response = await asyncio.to_thread(bot_app.ia.chat_response, conversation_history, f'chan_{ctx.channel.id}', prompt)
    await ctx.send(response)

@bot.command(name='habla')
async def cmd_habla(ctx, *, prompt: str = None):
    if not prompt:
        await ctx.send('💜 ¿Qué quieres que diga? 🎤')
        return
    async with ctx.typing():
        response = await asyncio.to_thread(bot_app.ia.chat_response, conversation_history, f'chan_{ctx.channel.id}', prompt)
    await ctx.send(response)
    if len(response) > MAX_TTS_CHARS:
        await ctx.send('⚠️ La respuesta es muy larga para leerla en voz. Acorta el mensaje o usa #ia para solo texto.')
        return
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send('💜 Para que hable necesito que estés en un canal de voz. Únete y usa `#habla` ahí.')
        return
    user_channel = ctx.author.voice.channel
    vc = ctx.voice_client
    if not vc:
        try:
            vc = await user_channel.connect()
            await ctx.send(embed=embed_success('Conectada al canal', f"Me uní a **{user_channel.name}** para hablar 🎤"))
        except Exception:
            log.exception('No pude unirme al canal desde cmd_habla')
            await ctx.send(embed=embed_warning('No pude unirme','No tengo permisos para unirme al canal de voz o ocurrió un error.'))
            return
    if vc and vc.channel.id != user_channel.id:
        await ctx.send(embed=embed_warning('Ya estoy en otro canal','Estoy en otro canal de voz. Pide que me unan al mismo canal o usa #join.'))
        return
    ok = await bot_app.tts.speak(vc, response)
    if not ok:
        await ctx.send('⚠️ No pude reproducir la voz. Comprueba permisos y que ffmpeg esté disponible.')

@bot.command(name='limpiar_ia')
async def cmd_limpiar_ia(ctx):
    key = f'chan_{ctx.channel.id}'
    if key in conversation_history:
        del conversation_history[key]
        await ctx.send('🧠 Memoria limpiada. Empezamos de cero 💜✨')
    else:
        await ctx.send('ℹ️ No había memoria previa en este canal.')

@bot.command(name='personalidad')
async def cmd_personalidad(ctx):
    await ctx.send(embed=embed_info('¿Quién es Kaivoxx?', SYSTEM_PROMPT))

@bot.command(name='resumen')
async def cmd_resumen(ctx, *, texto: str = None):
    if not texto:
        await ctx.send('✂️ Dame un texto para resumir.')
        return
    prompt = f"Resume el siguiente texto de forma clara y corta:\n\n{texto}"
    async with ctx.typing():
        response = await asyncio.to_thread(bot_app.ia.chat_response, conversation_history, f'temp_resumen_{ctx.message.id}', prompt)
    conversation_history.pop(f'temp_resumen_{ctx.message.id}', None)
    await ctx.send(f"📌 **Resumen:**\n{response}")

# ----------------------------
# Queue embed builder used by QueueView
# ----------------------------

def build_queue_embed(queue: MusicQueue, page: int = 0) -> discord.Embed:
    titles = list(queue._queue)
    total = len(titles)
    if total == 0:
        return embed_info('Cola vacía','No hay canciones en la cola 🎵')
    total_pages = max(1,(total+PER_PAGE-1)//PER_PAGE)
    page = max(0,min(page,total_pages-1))
    start = page * PER_PAGE
    end = min(start + PER_PAGE, total)
    lines = [f"{i+1}. {titles[i].title}" for i in range(start,end)]
    desc = "\n".join(lines) if lines else '(sin resultados)'
    embed = embed_music('Cola actual', desc)
    embed.set_footer(text=f'Página {page+1}/{total_pages} — {total} canciones en cola')
    return embed

# ----------------------------
# Run
# ----------------------------
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        log.error('No DISCORD_TOKEN provided in environment')
    else:
        bot.run(DISCORD_TOKEN)
