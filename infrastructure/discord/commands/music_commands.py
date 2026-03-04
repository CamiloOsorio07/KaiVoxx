from infrastructure.discord.bot_client import bot
from integration.queue_shim import ensure_queue_for_guild, music_queues
from infrastructure.discord.views.embeds import embed_info, embed_music, embed_success, embed_warning, embed_error
from infrastructure.discord.views.now_playing import send_now_playing_embed
from config.settings import BOT_PREFIX, MAX_QUEUE_LENGTH
from domain.entities.song import Song
import wavelink
from wavelink.ext import spotify
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
        
        # Check if already connected to this channel
        player = ctx.voice_client
        if player and player.channel.id == channel.id:
            await ctx.send(embed=embed_info("Ya estoy aquí", f"Ya estoy conectada en **{channel.name}** ✨"))
            return
        
        # Connect using Wavelink
        try:
            player = await channel.connect(cls=wavelink.Player)
            await ctx.send(embed=embed_success("Conectada al canal", f"Me uní a **{channel.name}** 🎧"))
        except Exception as e:
            await ctx.send(embed=embed_warning("Error de conexión", f"No pude unirme: {e}"))
    else:
        await ctx.send(embed=embed_warning("No estás en un canal", "Debes unirte primero a un canal de voz."))


@bot.command(name="leave", aliases=["l", "L", "Leave", "LEAVE"])
async def cmd_leave(ctx):
    player = ctx.voice_client
    if player:
        await player.disconnect()
        q = music_queues.get(ctx.guild.id)
        if q: q.clear()
        await ctx.send(embed=embed_success("Desconectada", "Me desconecté del canal y limpié la cola 🧹"))
    else:
        await ctx.send(embed=embed_warning("No estoy conectada", "No estoy en ningún canal de voz."))


async def play_music(ctx, search: str):
    """Play music using Wavelink."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(embed=embed_warning(
            "No estás en un canal de voz",
            "Debes unirte a un canal de voz antes de usar #play."
        ))
        return

    if not search:
        await ctx.send(embed=embed_warning("Falta el nombre", "Debes escribir el nombre de la canción o el link."))
        return

    # Get or create player
    player = ctx.voice_client
    if player is None:
        player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
    
    if player.channel.id != ctx.author.voice.channel.id:
        await ctx.send(embed=embed_warning(
            "Ya estoy en otro canal",
            "Estoy en otro canal de voz. Usa #join o muéveme."
        ))
        return

    queue = await ensure_queue_for_guild(ctx.guild.id)
    await ctx.send(embed=embed_info("Buscando en YouTube…", f"🔍 **{search}**"))

    # Search and add to queue
    try:
        # Determine if it's a Spotify URL
        if search.startswith('spotify:'):
            # Handle Spotify URLs
            decoded = spotify.decode_url(search)
            if decoded:
                if decoded.get('type') == spotify.SpotifyType.TRACK:
                    track = await spotify.SpotifyTrack.search(query=search, return_first=True)
                    if queue.enqueue(Song(track.uri, track.title, str(ctx.author), ctx.channel)):
                        await ctx.send(embed=embed_music(
                            "Canción añadida",
                            f"🎧 Ahora en cola: **{track.title}**\n📂 Posición: **{len(queue)}**"
                        ))
                elif decoded.get('type') == spotify.SpotifyType.PLAYLIST:
                    tracks = await spotify.SpotifyPlaylist.search(query=search)
                    songs_added = 0
                    for track in tracks:
                        if queue.enqueue(Song(track.uri, track.title, str(ctx.author), ctx.channel)):
                            songs_added += 1
                    await ctx.send(embed=embed_music(
                        "Playlist añadida",
                        f"🎶 Se añadieron **{songs_added} canciones**.\n📂 Cola actual: **{len(queue)}** / {queue.limit}"
                    ))
        else:
            # YouTube search
            if search.startswith('http://') or search.startswith('https://'):
                query = search
            else:
                query = f"ytsearch:{search}"
            
            tracks = await wavelink.Playable.search(query)
            
            if not tracks:
                await ctx.send(embed=embed_warning("Sin resultados", "No se encontraron resultados para la búsqueda."))
                return
            
            # Add first result
            track = tracks[0]
            if queue.enqueue(Song(track.uri, track.title, str(ctx.author), ctx.channel)):
                await ctx.send(embed=embed_music(
                    "Canción añadida",
                    f"🎧 Ahora en cola: **{track.title}**\n📂 Posición: **{len(queue)}**"
                ))

    except Exception as e:
        import logging
        logging.exception("Error buscando música")
        await ctx.send(embed=embed_warning("Error", f"Error buscando música: {e}"))
        return

    # Start playback
    await start_playback_if_needed(ctx.guild)


@bot.command(name="play", aliases=["p", "P", "Play", "PLAY"])
@requires_same_voice_channel_after_join()
async def cmd_play(ctx, *, search: str):
    await play_music(ctx, search)


async def start_playback_if_needed(guild: 'discord.Guild'):
    """Start playback using Wavelink."""
    player = guild.voice_client
    if not player or not player.is_connected():
        return
    
    queue = music_queues.get(guild.id)
    if not queue or len(queue) == 0:
        return
    
    # Check if already playing
    if player.is_playing():
        return
    
    # Get next song from queue
    song = queue.dequeue()
    if not song:
        return
    
    try:
        # Create track from URI
        track = await wavelink.Playable.from_uri(song.url)
        
        # Play the track
        await player.play(track)
        
        # Store current song
        bot._current_song = getattr(bot, '_current_song', {})
        bot._current_song[guild.id] = song
        
        # Send now playing
        asyncio.create_task(send_now_playing_embed(bot, song))
        
    except Exception as e:
        import logging
        logging.exception("Error iniciando reproducción")
        asyncio.create_task(song.channel.send(f"❌ Error al preparar el audio: {e}. Saltando..."))
        # Try next song
        await start_playback_if_needed(guild)


@bot.command(name="skip", aliases=["sk", "SK", "Skip", "next", "Next"])
@requires_same_voice_channel_after_join()
async def cmd_skip(ctx):
    player = ctx.voice_client
    if player and player.is_playing():
        await player.stop()
        await ctx.send(embed=embed_info("Saltado", "⏭ Se saltó la canción actual."))
    else:
        await ctx.send(embed=embed_warning("Nada reproduciéndose", "No hay ninguna canción sonando."))


@bot.command(name="stop", aliases=["s", "S", "Stop","STOP", "st", "ST"])
@requires_same_voice_channel_after_join()
async def cmd_stop(ctx):
    player = ctx.voice_client
    if player:
        await player.stop()
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


@bot.event
async def on_wavelink_track_end(player: wavelink.Player, track: wavelink.Track, reason):
    """Handle track end event."""
    guild = player.guild
    asyncio.create_task(start_playback_if_needed(guild))


@bot.event
async def on_wavelink_track_exception(player: wavelink.Player, track: wavelink.Track, error):
    """Handle track exception."""
    import logging
    logging.error(f"Track exception: {error}")
    guild = player.guild
    asyncio.create_task(start_playback_if_needed(guild))
