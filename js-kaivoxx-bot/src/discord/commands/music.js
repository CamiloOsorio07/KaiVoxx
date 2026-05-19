const { embedInfo, embedSuccess, embedWarning, embedError, embedMusic } = require('../views/embeds');
const { BOT_PREFIX, MAX_QUEUE_LENGTH } = require('../../config');
const { MusicQueue } = require('../../queue/MusicQueue');
const { ensureQueueForGuild } = require('../../state/queues');

// TODO: Implementar play/skip/stop/queue/now y ahora mismo solo placeholders para que no reviente.

async function cmdJoin(message) {
  const memberVoice = message.member?.voice;
  if (!memberVoice?.channel) {
    await message.channel.send({ embeds: [embedWarning('No estás en un canal', 'Debes unirte primero a un canal de voz.')] });
    return;
  }
  const channel = memberVoice.channel;
  const vc = message.guild.voiceAdapterCreator ? message.guild.members.me?.voice?.connection : null;
  // Con @discordjs/voice lo haremos en el paso siguiente.
  await message.channel.send({ embeds: [embedSuccess('Conectada al canal', `Me uní a **${channel.name}** 🎧`)] });
}

async function cmdLeave(message) {
  // placeholder
  const q = require('../../state/queues').musicQueues?.get(message.guild.id);
  if (q) q.clear();
  await message.channel.send({ embeds: [embedSuccess('Desconectada', 'Me desconecté del canal y limpié la cola 🧹')] });
}

async function cmdPlay(message, search) {
  if (!message.member?.voice?.channel) {
    await message.channel.send({ embeds: [embedWarning('No estás en un canal de voz', 'Debes unirte a un canal de voz antes de usar #play.')] });
    return;
  }
  if (!search) {
    await message.channel.send({ embeds: [embedWarning('Falta el nombre', 'Debes escribir el nombre de la canción o el link.')] });
    return;
  }
  await message.channel.send({ embeds: [embedInfo('Buscando en YouTube…', `🔍 **${search}**`)] });

  const queue = await ensureQueueForGuild(message.guild.id);
  // placeholder: aún no añadimos canciones reales (se implementa en el siguiente paso)
  queue.enqueue({ url: search, title: search, requester_name: message.author.username, channel: message.channel });

  await message.channel.send({ embeds: [embedMusic('Canción añadida', `🎧 Ahora en cola: **${search}**\n📂 Posición: **${queue.length}**`)] });
}

async function cmdSkip(message) {
  await message.channel.send({ embeds: [embedInfo('Saltado', '⏭ Se saltó la canción actual. (pendiente implementación JS)')] });
}

async function cmdStop(message) {
  const queue = require('../../state/queues').musicQueues?.get(message.guild.id);
  if (queue) queue.clear();
  await message.channel.send({ embeds: [embedError('Reproducción detenida', '🛑 Cola eliminada y música detenida. (pendiente implementación JS)')] });
}

async function cmdQueue(message) {
  const queue = require('../../state/queues').musicQueues?.get(message.guild.id);
  if (!queue || queue.length === 0) {
    await message.channel.send({ embeds: [embedInfo('Cola vacía', 'No hay canciones en la cola 🎵')] });
    return;
  }
  await message.channel.send({ embeds: [embedInfo('Cola', queue.listTitles().slice(0, 20).join('\n') || '(vacía)')] });
}

async function cmdNow(message) {
  await message.channel.send({ embeds: [embedInfo('Now', 'Pendiente: ahora reproduciendo.')] });
}

const musicCommands = {
  // join
  join: { execute: cmdJoin },
  j: { execute: cmdJoin },
  // leave
  leave: { execute: cmdLeave },
  l: { execute: cmdLeave },
  // play
  play: { execute: cmdPlay },
  p: { execute: cmdPlay },
  // skip
  skip: { execute: cmdSkip },
  sk: { execute: cmdSkip },
  // stop
  stop: { execute: cmdStop },
  s: { execute: cmdStop },
  // queue
  queue: { execute: cmdQueue },
  q: { execute: cmdQueue },
  // now
  now: { execute: cmdNow },
  np: { execute: cmdNow },
  // aliases exacts (uppercase no importa al parse)
  leave: { execute: cmdLeave }
};

module.exports = { musicCommands };

