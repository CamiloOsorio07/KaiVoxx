const { EmbedBuilder } = require('discord.js');

function makeEmbed(type, title, description) {
  const colors = {
    success: 0x2ECC71,
    info: 0x9B59B6,
    warning: 0xF1C40F,
    error: 0xE74C3C,
    music: 0x9B59B6
  };
  const icons = {
    success: '✅ ✨',
    info: 'ℹ️ 🎙️',
    warning: '⚠️ ✴️',
    error: '❌ ✖️',
    music: '🎵 🎵'
  };

  const embed = new EmbedBuilder()
    .setTitle(`${icons[type]} ${title}`)
    .setDescription(description)
    .setColor(colors[type]);

  if (type === 'music') embed.setFooter({ text: '💜 Disfruta tu música 💜' });
  return embed;
}

const embedSuccess = (t, d) => makeEmbed('success', t, d);
const embedInfo = (t, d) => makeEmbed('info', t, d);
const embedWarning = (t, d) => makeEmbed('warning', t, d);
const embedError = (t, d) => makeEmbed('error', t, d);
const embedMusic = (t, d) => makeEmbed('music', t, d);

module.exports = {
  embedSuccess,
  embedInfo,
  embedWarning,
  embedError,
  embedMusic
};

