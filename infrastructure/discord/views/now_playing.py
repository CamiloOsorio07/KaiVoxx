import discord, asyncio, time, logging
from infrastructure.discord.views.embeds import embed_music
from integration.queue_shim import music_queues

log = logging.getLogger('kaivoxx.views')
now_playing_messages = {}

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
    embed.add_field(name="Time Elapsed", value="0:00", inline=False)
    msg = await song.channel.send(embed=embed, view=view)
    now_playing_messages[guild_id] = msg
    asyncio.create_task(update_now_playing_bar(bot, guild_id, song))

async def update_now_playing_bar(bot, guild_id, song):
    start_time = time.time()
    msg = now_playing_messages.get(guild_id)
    if not msg: return
    while True:
        vc = msg.guild.voice_client
        if not vc or not vc.is_playing(): break
        elapsed = int(time.time() - start_time)
        embed = msg.embeds[0]
        embed.set_field_at(2, name="Time Elapsed", value=f"{elapsed//60:02}:{elapsed%60:02}", inline=False)
        try:
            await msg.edit(embed=embed)
        except Exception:
            break
        await asyncio.sleep(1)
