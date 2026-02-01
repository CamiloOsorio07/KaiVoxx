import logging
import discord
from discord.ext import commands
from config.settings import BOT_PREFIX

log = logging.getLogger('kaivoxx.bot')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)

@bot.event
async def on_ready():
    log.info(f"Bot conectado como {bot.user}")
    activity = discord.Activity(type=discord.ActivityType.listening, name="#help 🎵 | 💜 Tu asistente musical y de IA favorita (IA en proceso)")
    await bot.change_presence(status=discord.Status.online, activity=activity)

# on_message: handle mentions and IA
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    content = (message.content or "").strip()
    mention_prefixes = []
    if bot.user:
        mention_prefixes = [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]
    is_ia = content.startswith(f"{BOT_PREFIX}ia")
    is_habla = content.startswith(f"{BOT_PREFIX}habla")
    is_mention_direct = bot.user and bot.user.mentioned_in(message)
    for mp in mention_prefixes:
        if content.startswith(mp):
            after = content[len(mp):].strip()
            if after.lower().startswith("ia ") or after.lower() == "ia":
                is_ia = True
                content = after[len("ia"):].strip()
            elif after.lower().startswith("habla ") or after.lower() == "habla":
                is_habla = True
                content = after[len("habla"):].strip()
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
        await message.channel.send("💜 Dime qué quieres que responda.")
        await bot.process_commands(message)
        return
    async with message.channel.typing():
        from infrastructure.ia.groq_client import groq_chat_response
        response = await __import__('asyncio').to_thread(groq_chat_response, f"chan_{message.channel.id}", prompt)
    await message.channel.send(response)
    # habla por voz si corresponde
    if (is_habla or False) and message.guild and len(response) <= 180:
        author_voice = message.author.voice
        vc = message.guild.voice_client
        from infrastructure.tts.gtts_client import speak_text_in_voice
        from infrastructure.discord.views.embeds import embed_success, embed_warning
        if not author_voice or not author_voice.channel:
            await message.channel.send("💜 Para que hable, debes estar en un canal de voz y usar `#habla` o mencionar y decir 'habla'.")
        else:
            user_channel = author_voice.channel
            if not vc:
                try:
                    vc = await user_channel.connect()
                    await message.channel.send(embed=embed_success("Conectada al canal", f"Me uní a **{user_channel.name}** para hablar 🎤"))
                except Exception:
                    log.exception('No pude unirme al canal de voz')
                    await message.channel.send(embed=embed_warning("No pude unirme", "No tengo permisos para unirme al canal de voz o ocurrió un error."))
                    await bot.process_commands(message)
                    return
            if vc.channel.id != user_channel.id:
                await message.channel.send(embed=embed_warning("Ya estoy en otro canal", "Estoy en otro canal de voz. Pide que me unan al mismo canal o usa `#join`."))
            else:
                ok = await speak_text_in_voice(vc, response) if 'speak_text_in_voice' in globals() else await __import__('infrastructure.tts.gtts_client', fromlist=['speak_text_in_voice']).speak_text_in_voice(vc, response)
                if not ok:
                    await message.channel.send("⚠️ No pude reproducir la voz. Comprueba permisos y que ffmpeg esté disponible.")

def create_bot():
    # import commands to register them
    try:
        import infrastructure.discord.commands.music_commands as _mc
        import infrastructure.discord.commands.ia_commands as _ia
        # views are imported on demand
    except Exception as e:
        logging.exception('Error importing commands: %s', e)
    return bot
