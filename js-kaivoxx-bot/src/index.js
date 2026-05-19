const { DISCORD_TOKEN } = require('./config');
const { createBot } = require('./discord/bot');

if (!DISCORD_TOKEN) {
  console.error('Falta DISCORD_TOKEN en variables de entorno');
  console.error('Copia `js-kaivoxx-bot/.env.example` a `js-kaivoxx-bot/.env` y completa el token.');
  process.exit(1);
}

const bot = createBot();
bot.login(DISCORD_TOKEN).catch((e) => {
  console.error('Error iniciando bot. Revisa DISCORD_TOKEN.');
  console.error(e);
  process.exit(1);
});


