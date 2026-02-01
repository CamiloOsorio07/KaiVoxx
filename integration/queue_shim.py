from domain.repositories.queue_repository import MusicQueue

music_queues = {}

async def ensure_queue_for_guild(guild_id: int) -> MusicQueue:
    if guild_id not in music_queues:
        music_queues[guild_id] = MusicQueue(limit=MusicQueue().limit)
    return music_queues[guild_id]
