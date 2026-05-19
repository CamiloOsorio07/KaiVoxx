const { BOT_PREFIX } = require('../../config');
const { embedInfo } = require('../views/embeds');

const helpCommand = {
  execute: async (message) => {
    const description =
      `### 🎵 **Comandos de Música**\n` +
      `**${BOT_PREFIX}play / ${BOT_PREFIX}p** → Reproduce una canción o playlist\n` +
      `**${BOT_PREFIX}join** → Me uno a tu canal de voz\n` +
      `**${BOT_PREFIX}leave** → Salgo del canal y limpio la cola\n` +
      `**${BOT_PREFIX}skip / ${BOT_PREFIX}s** → Salta la canción actual\n` +
      `**${BOT_PREFIX}stop** → Detiene la música y borra la cola\n` +
      `**${BOT_PREFIX}queue / ${BOT_PREFIX}q** → Muestra la cola de reproducción\n` +
      `**${BOT_PREFIX}now** → Muestra la canción actual\n\n` +
      `### 🤖 **Comandos de IA**\n` +
      `**${BOT_PREFIX}ia / ${BOT_PREFIX}i** → Habla con la IA (solo texto)\n` +
      `**${BOT_PREFIX}habla / ${BOT_PREFIX}h / ${BOT_PREFIX}voz / ${BOT_PREFIX}tts** → IA que responde con voz\n` +
      `**${BOT_PREFIX}limpiar_ia / ${BOT_PREFIX}cia** → Limpia la memoria de la IA del canal\n` +
      `**${BOT_PREFIX}resumen / ${BOT_PREFIX}res / ${BOT_PREFIX}tl** → Resume un texto\n` +
      `**${BOT_PREFIX}personalidad / ${BOT_PREFIX}perso** → Muestra la personalidad de Kaivoxx\n\n` +
      `### ℹ️ **Notas**\n` +
      `• Los comandos funcionan en **mayúsculas y minúsculas**\n` +
      `• Puedes usar **abreviaciones**\n` +
      `• Para usar voz debes estar en un canal de voz 🎧`;

    await message.channel.send({ embeds: [embedInfo('Ayuda — Kaivoxx 💜', description)] });
  }
};

module.exports = { helpCommand };

