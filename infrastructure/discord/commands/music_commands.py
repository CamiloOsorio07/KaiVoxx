from infrastructure.discord.bot_client import bot
from integration.queue_shim import ensure_queue_for_guild, music_queues
from infrastructure.ytdlp.ytdlp_client import extract_info, build_ffmpeg_source
from infrastructure.discord.views.embeds import embed_info, embed_music, embed_success, embed_warning, embed_error
from infrastructure.discord.views.now_playing import send_now_playing_embed
from config.settings import BOT_PREFIX, MAX_QUEUE_LENGTH
from domain.entities.song import Song
import asyncio
import discord

# Decorator (copiado)
from discord.ext import commands
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

@bot.command(name="join", aliases=["j", "J", "JOIN", "Join"])
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

@bot.command(name="leave", aliases=["l", "L", "Leave", "LEAVE"])
async def cmd_leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        q = music_queues.get(ctx.guild.id)
        if q: q.clear()
        await ctx.send(embed=embed_success("Desconectada", "Me desconecté del canal y limpié la cola 🧹"))
    else:
        await ctx.send(embed=embed_warning("No estoy conectada", "No estoy en ningún canal de voz."))

async def play_music(ctx, search: str):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(embed=embed_warning(
            "No estás en un canal de voz",
            "Debes unirte a un canal de voz antes de usar #play."
        ))
        return

    if not search:
        await ctx.send(embed=embed_warning("Falta el nombre", "Debes escribir el nombre de la canción o el link."))
        return

    vc = ctx.voice_client
    if vc and vc.channel.id != ctx.author.voice.channel.id:
        await ctx.send(embed=embed_warning(
            "Ya estoy en otro canal",
            "Estoy en otro canal de voz. Usa #join o muéveme."
        ))
        return

    if not vc:
        vc = await ctx.author.voice.channel.connect()

    queue = await ensure_queue_for_guild(ctx.guild.id)
    await ctx.send(embed=embed_info("Buscando en YouTube…", f"🔍 **{search}**"))

    info = await extract_info(search if (search.startswith('http://') or search.startswith('https://') or search.startswith('spotify:')) else f"ytsearch:{search}")
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

    # start playback
    await start_playback_if_needed(ctx.guild)

@bot.command(name="play", aliases=["p", "P", "Play", "PLAY"])
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
        vc = await ctx.author.voice.channel.connect()

    queue = await ensure_queue_for_guild(ctx.guild.id)
    await ctx.send(embed=embed_info("Buscando en YouTube…", f"🔍 **{search}**"))

    info = await extract_info(search if (search.startswith('http://') or search.startswith('https://') or search.startswith('spotify:')) else f"ytsearch:{search}")
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

    # start playback
    await start_playback_if_needed(ctx.guild)

async def start_playback_if_needed(guild: 'discord.Guild'):
    vc = guild.voice_client
    if not vc or not vc.is_connected(): return
    queue = music_queues.get(guild.id)
    if not queue or len(queue) == 0: return
    if not vc.is_playing():
        song = queue.dequeue()
        if not song: return
        try:
            source = await build_ffmpeg_source(song.url)
            vc.play(source, after=lambda err: asyncio.run_coroutine_threadsafe(start_playback_if_needed(guild), bot.loop) or (print(f"Playback error: {err}" if err else "")))
            # store current song in a simple dict on the bot
            bot._current_song = getattr(bot, '_current_song', {})
            bot._current_song[guild.id] = song
            asyncio.create_task(send_now_playing_embed(bot, song))
        except Exception:
            import logging; logging.exception("Error iniciando reproducción")
            asyncio.create_task(song.channel.send("❌ Error al preparar el audio. Saltando..."))

@bot.command(name="skip", aliases=["sk", "SK", "Skip", "next", "Next"])
@requires_same_voice_channel_after_join()
async def cmd_skip(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send(embed=embed_info("Saltado", "⏭ Se saltó la canción actual."))
    else:
        await ctx.send(embed=embed_warning("Nada reproduciéndose", "No hay ninguna canción sonando."))

@bot.command(name="stop", aliases=["s", "S", "Stop","STOP", "st", "ST"])
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

@bot.command(name="queue", aliases=["q", "Q", "Queue", "QUEUE"])
@requires_same_voice_channel_after_join()
async def cmd_queue(ctx):
    queue = music_queues.get(ctx.guild.id)
    if not queue or len(queue) == 0:
        await ctx.send(embed=embed_info("Cola vacía", "No hay canciones en la cola 🎵"))
        return
    from infrastructure.discord.views.now_playing import QueueView, build_queue_embed
    total = len(queue)
    total_pages = max(1, (total + 50 - 1) // 50)
    view = QueueView(author_id=ctx.author.id, guild_id=ctx.guild.id, initial_page=0)
    options = [discord.SelectOption(label=f"Página {i+1}", description=f"{i*50+1}-{min((i+1)*50, total)} canciones", value=str(i)) for i in range(total_pages)]
    for child in view.children:
        if isinstance(child, discord.ui.Select):
            child.options = options
            child.placeholder = f"Ir a página (1/{total_pages})"
    embed = build_queue_embed(queue, 0)
    await ctx.send(embed=embed, view=view)

@bot.command(name="now", aliases=["np", "NP", "Now", "NOW"])
@requires_same_voice_channel_after_join()
async def cmd_now(ctx):
    song = getattr(bot, '_current_song', {}).get(ctx.guild.id)
    if song:
        await ctx.send(embed=embed_music("Ahora reproduciendo", f"🎧 **[{song.title}]({song.url})**\n💜 Pedido por {song.requester_name}"))
    else:
        await ctx.send(embed=embed_info("Nada reproduciéndose", "No hay música sonando actualmente."))
