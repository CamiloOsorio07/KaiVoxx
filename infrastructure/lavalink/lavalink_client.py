"""
Lavalink client for Kaivoxx bot.
Handles connection to external Lavalink server for audio playback.
"""
import logging
import wavelink
from config.settings import LAVALINK_HOST, LAVALINK_PORT, LAVALINK_PASSWORD, LAVALINK_USE_SSL

log = logging.getLogger('kaivoxx.lavalink')


class LavalinkClient:
    """Manages Lavalink node connections."""
    
    def __init__(self, bot):
        self.bot = bot
        self.nodes = []
    
    async def initialize(self):
        """Initialize Lavalink nodes."""
        try:
            # Create Lavalink node
            node = wavelink.Node(
                uri=f"{'https' if LAVALINK_USE_SSL else 'http'}://{LAVALINK_HOST}:{LAVALINK_PORT}",
                password=LAVALINK_PASSWORD,
                secure=LAVALINK_USE_SSL,
                name="kaivoxx-main"
            )
            
            # Connect the node
            await wavelink.Pool.connect(node=node, client=self.bot)
            self.nodes.append(node)
            log.info(f"Conectado a Lavalink: {LAVALINK_HOST}:{LAVALINK_PORT}")
            
        except Exception as e:
            log.error(f"Error conectando a Lavalink: {e}")
            raise
    
    async def close(self):
        """Close all Lavalink connections."""
        for node in self.nodes:
            await node.close()
        self.nodes.clear()
        log.info("Conexiones Lavalink cerradas")


# Global instance
lavalink_client: LavalinkClient = None


async def init_lavalink(bot):
    """Initialize Lavalink for the bot."""
    global lavalink_client
    
    # Add webhook for Wavelink events
    bot.wavelink = wavelink.Client(bot)
    
    lavalink_client = LavalinkClient(bot)
    await lavalink_client.initialize()
    
    return lavalink_client


async def close_lavalink():
    """Close Lavalink connections."""
    global lavalink_client
    if lavalink_client:
        await lavalink_client.close()
        lavalink_client = None
