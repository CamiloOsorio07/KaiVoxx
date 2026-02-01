from infrastructure.discord.bot_client import bot
from infrastructure.discord.views.embeds import embed_info


@bot.command(
    name="help",
    aliases=["ayuda", "commands", "comandos"]
)
async def cmd_help(ctx):
    description = (
        "### 🎵 **Comandos de Música**\n"
        "**#play / #p** → Reproduce una canción o playlist\n"
        "**#join** → Me uno a tu canal de voz\n"
        "**#leave** → Salgo del canal y limpio la cola\n"
        "**#skip / #s** → Salta la canción actual\n"
        "**#stop** → Detiene la música y borra la cola\n"
        "**#queue / #q** → Muestra la cola de reproducción\n"
        "**#now** → Muestra la canción actual\n\n"
        "### 🤖 **Comandos de IA**\n"
        "**#ia / #i** → Habla con la IA (solo texto)\n"
        "**#habla / #voz / #tts** → IA que responde con voz\n"
        "**#limpiar_ia / #cia** → Limpia la memoria de la IA del canal\n"
        "**#resumen / #res / #tl** → Resume un texto\n"
        "**#personalidad / #perso** → Muestra la personalidad de Kaivoxx\n\n"
        "### ℹ️ **Notas**\n"
        "• Los comandos funcionan en **mayúsculas y minúsculas**\n"
        "• Puedes usar **abreviaciones** (`#p`, `#s`, `#h`)\n"
        "• Para usar voz debes estar en un canal de voz 🎧"
    )

    await ctx.send(
        embed=embed_info(
            "Ayuda — Kaivoxx 💜",
            description
        )
    )
