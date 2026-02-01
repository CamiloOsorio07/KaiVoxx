from infrastructure.discord.bot_client import bot
from infrastructure.ia.groq_client import groq_chat_response
from integration.queue_shim import music_queues
from infrastructure.discord.views.embeds import embed_info
import asyncio

# Protección contra doble ejecución
_habla_processing = set()


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
    from infrastructure.tts.gtts_client import speak_text_in_voice
    from infrastructure.discord.views.embeds import embed_success, embed_warning

    # Evitar doble ejecución del mismo mensaje
    if ctx.message.id in _habla_processing:
        return
    _habla_processing.add(ctx.message.id)

    try:
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

        if len(response) > 180:
            await ctx.send(
                "⚠️ La respuesta es muy larga para leerla en voz. "
                "Acorta el mensaje o usa #ia para solo texto."
            )
            return

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(
                "💜 Para que hable necesito que estés en un canal de voz. "
                "Únete y usa `#habla` ahí."
            )
            return

        user_channel = ctx.author.voice.channel
        vc = ctx.voice_client

        if not vc:
            try:
                vc = await user_channel.connect()
                await ctx.send(
                    embed=embed_success(
                        "Conectada al canal",
                        f"Me uní a **{user_channel.name}** para hablar 🎤"
                    )
                )
            except Exception:
                import logging
                logging.exception("No pude unirme al canal desde cmd_habla")
                await ctx.send(
                    embed=embed_warning(
                        "No pude unirme",
                        "No tengo permisos para unirme al canal de voz."
                    )
                )
                return

        if vc.channel.id != user_channel.id:
            await ctx.send(
                embed=embed_warning(
                    "Ya estoy en otro canal",
                    "Estoy en otro canal de voz. Usa #join o muéveme."
                )
            )
            return

        ok = await speak_text_in_voice(vc, response)
        if not ok:
            await ctx.send(
                "⚠️ No pude reproducir la voz. "
                "Comprueba permisos y que ffmpeg esté disponible."
            )

    finally:
        # Liberar bloqueo
        _habla_processing.discard(ctx.message.id)


@bot.command(name="limpiar_ia")
async def cmd_limpiar_ia(ctx):
    key = f"chan_{ctx.channel.id}"
    from infrastructure.ia.groq_client import conversation_history

    if key in conversation_history:
        del conversation_history[key]
        await ctx.send("🧠 Memoria limpiada. Empezamos de cero 💜✨")
    else:
        await ctx.send("ℹ️ No había memoria previa en este canal.")


@bot.command(name="personalidad")
async def cmd_personalidad(ctx):
    from config.settings import SYSTEM_PROMPT
    await ctx.send(embed=embed_info("¿Quién es Kaivoxx?", SYSTEM_PROMPT))


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

    from infrastructure.ia.groq_client import conversation_history
    conversation_history.pop(f"temp_resumen_{ctx.message.id}", None)

    await ctx.send(f"📌 **Resumen:**\n{response}")
