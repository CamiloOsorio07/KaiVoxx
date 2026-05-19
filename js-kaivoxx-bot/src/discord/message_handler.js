const { BOT_PREFIX } = require('../config');
const { registerCommands } = require('./commands/registry');

const cmds = registerCommands();

function normalizeContent(content) {
  return (content || '').trim();
}

async function handleMessage(client, message) {
  const content = normalizeContent(message.content);
  if (!content) return;

  // Menciones: replicamos la lógica de bot_client.py
  // Si empieza con <@id> o <@!id> procesamos como si fuera un comando directo.
  const mentionIds = [];
  if (client.user) {
    mentionIds.push(`<@${client.user.id}>`);
    mentionIds.push(`<@!${client.user.id}>`);
  }

  let isMentionDirect = false;
  let isIa = content.startsWith(`${BOT_PREFIX}ia`);
  let isHabla = content.startsWith(`${BOT_PREFIX}habla`);

  for (const mp of mentionIds) {
    if (content.startsWith(mp)) {
      const after = content.slice(mp.length).trim();
      if (after.toLowerCase().startsWith('ia ') || after.toLowerCase() === 'ia') {
        isIa = true;
        // convertimos a formato prefijo
        message.content = `${BOT_PREFIX}ia${after.toLowerCase() === 'ia' ? '' : after.slice(2).trim()}`;
      } else if (after.toLowerCase().startsWith('habla ') || after.toLowerCase() === 'habla') {
        isHabla = true;
        message.content = `${BOT_PREFIX}habla${after.toLowerCase() === 'habla' ? '' : after.slice(5).trim()}`;
      } else {
        isMentionDirect = true;
        message.content = after;
      }
      break;
    }
  }

  if (isIa) {
    // aseguramos que el mensaje comienza con prefijo #ia
    if (!message.content.startsWith(`${BOT_PREFIX}ia`)) {
      message.content = `${BOT_PREFIX}ia ${message.content}`.trim();
    }
  }

  if (isHabla) {
    if (!message.content.startsWith(`${BOT_PREFIX}habla`)) {
      message.content = `${BOT_PREFIX}habla ${message.content}`.trim();
    }
  }

  const handled = await maybeRunCommand(message);
  if (handled) return;

  // Caso menciones genéricas: no implementamos IA “default” porque en Python solo responde si es ia/habla o mention_direct.
  // Aquí, si es mention_direct, podemos mapear a IA texto (mejor opción: simular lo mismo que Python).
  if (isMentionDirect || isIa || isHabla) {
    // No hacemos nada si no es ia/habla: ya que comandos específicos manejan.
    // IA genérica (mención sin palabras clave) se podría extender luego.
  }
}

async function maybeRunCommand(message) {
  const content = normalizeContent(message.content);
  if (!content.startsWith(BOT_PREFIX)) return false;

  const parts = content.slice(BOT_PREFIX.length).trim().split(/\s+/);
  const cmdName = (parts.shift() || '').toLowerCase();
  const args = parts.join(' ');

  const cmd = cmds.get(cmdName);
  if (!cmd) return false;

  await cmd.execute(message, args);
  return true;
}

module.exports = { handleMessage };

