const { MusicQueue } = require('../queue/MusicQueue');
const { MAX_QUEUE_LENGTH } = require('../config');

const musicQueues = new Map();

async function ensureQueueForGuild(guildId) {
  if (!musicQueues.has(guildId)) {
    musicQueues.set(guildId, new MusicQueue(MAX_QUEUE_LENGTH));
  }
  return musicQueues.get(guildId);
}

module.exports = { musicQueues, ensureQueueForGuild };

