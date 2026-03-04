"""
Lavalink client for Kaivoxx bot.
Handles connection to external Lavalink server for audio playback.
"""
import logging
import wavelink
from config.settings import LAVALINK_HOST, LAVALINK_PORT, LAVALINK_PASSWORD, LAVALINK_USE_SSL

log = logging.getLogger('kaivoxx.lavalink')


# Global node reference
_node = None


async def init_lavalink(bot):
    """Initialize Lavalink for the bot."""
    global _node
    
    try:
        # Create node configuration
        node = wavelink.Node(
            uri=f"{'https' if LAVALINK_USE_SSL else 'http'}://{LAVALINK_HOST}:{LAVALINK_PORT}",
            password=LAVALINK_PASSWORD,
            secure=LAVALINK_USE_SSL,
            name="kaivoxx-main"
        )
        
        # Connect the node using Pool
        await wavelink.Pool.connect(node=node, client=bot)
        _node = node
        log.info(f"Conectado a Lavalink: {LAVALINK_HOST}:{LAVALINK_PORT}")
        
    except Exception as e:
        log.error(f"Error conectando a Lavalink: {e}")
        raise
    
    return _node


async def close_lavalink():
    """Close Lavalink connections."""
    global _node
    if _node:
        await _node.close()
        _node = None
        log.info("Conexión Lavalink cerrada")


def get_node():
    """Get the current node."""
    return _node
