const { embedWarning, embedInfo } = require('../views/embeds');

// IA + Groq + TTS: se implementan en el siguiente paso.

async function cmdIa(message, prompt) {
  if (!prompt) {
    await message.channel.send('💜 Dime qué quieres que responda.');
    return;
  }
  // placeholder
  await message.channel.send(`(IA) ${prompt}`);
}

async function cmdHabla(message, prompt) {
  if (!prompt) {
    await message.channel.send('💜 ¿Qué quieres que diga? 🎤');
    return;
  }
  if (!message.member?.voice?.channel) {
    await message.channel.send('💜 Para que hable necesito que estés en un canal de voz. Únete y usa #habla ahí.');
    return;
  }
  await message.channel.send(`(Habla) ${prompt} (pendiente TTS JS)`);
}

async function cmdLimpiarIa(message) {
  await message.channel.send('🧠 Memoria limpiada. (pendiente implementación)');
}

async function cmdPersonalidad(message) {
  await message.channel.send(embedInfo('¿Quién es Kaivoxx?', 'Pendiente: prompt completo.'));
}

async function cmdResumen(message, texto) {
  if (!texto) {
    await message.channel.send('✂️ Dame un texto para resumir.');
    return;
  }
  await message.channel.send(`📌 **Resumen:** ${texto}`);
}

const aiCommands = {
  ia: { execute: cmdIa },
  i: { execute: cmdIa },
  habla: { execute: cmdHabla },
  h: { execute: cmdHabla },
  voz: { execute: cmdHabla },
  tts: { execute: cmdHabla },
  limpiar_ia: { execute: cmdLimpiarIa },
  cia: { execute: cmdLimpiarIa },
  personalidad: { execute: cmdPersonalidad },
  perso: { execute: cmdPersonalidad },
  whoami: { execute: cmdPersonalidad },
  info: { execute: cmdPersonalidad },
  resumen: { execute: cmdResumen },
  res: { execute: cmdResumen },
  tl: { execute: cmdResumen },
  'tl;dr': { execute: cmdResumen }
};

module.exports = { aiCommands };

