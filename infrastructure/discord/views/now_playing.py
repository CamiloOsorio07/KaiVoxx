import discord, logging
from datetime import datetime, timezone
from infrastructure.discord.views.embeds import embed_music
from integration.queue_shim import music_queues

log = logging.getLogger('kaivoxx.views')
now_playing_messages = {}

def build_queue_embed(queue, page: int = 0):
    """Build an embed showing the queue with pagination (50 songs per page)."""
    songs_per_page = 50
    total = len(queue)
    total_pages = max(1, (total + songs_per_page - 1) // songs_per_page)
    
    start_idx = page * songs_per_page
    end_idx = min(start_idx + songs_per_page, total)
    
    # Access the internal deque of the MusicQueue
    songs_list = list(queue._queue)
    song_lines = []
    for i in range(start_idx, end_idx):
        song = songs_list[i]
        song_lines.append(f"`{i+1}.` [{song.title}]({song.url}) - 👤 {song.requester_name}")
    
    description = "\n".join(song_lines) if song_lines else "No hay canciones en la cola 🎵"
    
    embed = discord.Embed(
        title=f"📋 Cola de música ({total} canciones)",
        description=description,
        color=0x9B59B6
    )
    embed.set_footer(text=f"Página {page + 1}/{total_pages}")
    return embed


class QueueView(discord.ui.View):
    def __init__(self, author_id: int, guild_id: int, initial_page: int = 0):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.guild_id = guild_id
        self.current_page = initial_page
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ No puedes interactuar con esta cola.", ephemeral=True)
            return False
        return True

    async def update_embed(self, interaction: discord.Interaction):
        queue = music_queues.get(self.guild_id)
        if not queue or len(queue) == 0:
            await interaction.response.send_message("La cola está vacía.", ephemeral=True)
            return
        embed = build_queue_embed(queue, self.current_page)
        await interaction.response.edit_message(embed=embed)

    @discord.ui.select()
    async def page_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.current_page = int(select.values[0])
        await self.update_embed(interaction)


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
            await interaction.response.send_message("⚠️ Debes estar en el mismo canal de voz que yo para usar este botón.", ephemeral=True)
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

async def send_now_playing_embed(bot, song):
    guild_id = song.channel.guild.id
    view = NowPlayingView(bot, guild_id)
    embed = embed_music("Now Playing ✨", f"**[{song.title}]({song.url})**")
    if "watch?v=" in song.url:
        embed.set_thumbnail(url=f"https://img.youtube.com/vi/{song.url.split('=')[1]}/hqdefault.jpg")
    embed.add_field(name="Requested by", value=f"💜 {song.requester_name}", inline=True)
    embed.add_field(name="Source", value="YouTube 🎵", inline=True)
    # Use Discord's built-in timestamp for real-time display without API calls
    # Discord automatically shows elapsed time based on start timestamp
    embed.add_field(name="Started at", value="▶️ Reproduciendo", inline=False)
    embed.timestamp = datetime.now(timezone.utc)
    msg = await song.channel.send(embed=embed, view=view)
    now_playing_messages[guild_id] = msg
