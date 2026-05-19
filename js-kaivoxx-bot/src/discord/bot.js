const { Client, GatewayIntentBits, ActivityType } = require('discord.js');
const { BOT_PREFIX } = require('../config');
const { handleMessage } = require('./message_handler');

function createBot() {
  const client = new Client({
    intents: [
      GatewayIntentBits.Guilds,
      GatewayIntentBits.GuildMessages,
      GatewayIntentBits.MessageContent,
      GatewayIntentBits.GuildVoiceStates
    ]
  });

  client.once('ready', async () => {
    console.log(`Bot conectado como ${client.user.tag}`);
    client.user.setPresence({
      status: 'online',
      activities: [{
        type: ActivityType.Listening,
        name: `${BOT_PREFIX}help 🎵 | 💜 Tu asistente musical y de IA favorita (IA en proceso)`
      }]
    });
  });

  client.on('messageCreate', async (message) => {
    if (!message || message.author?.bot) return;
    await handleMessage(client, message);
  });

  return client;
}

module.exports = { createBot };

