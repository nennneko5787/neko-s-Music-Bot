import time

import lavalink
from lavalink import DefaultPlayer

from .queue import MusicQueue


class MusicPlayer(DefaultPlayer):
    def __init__(self, guild_id, node):
        super().__init__(guild_id, node)

        self.ping = 0
        self.prevQueue = MusicQueue()
        self.lastUpdated = 0.0

    def update(self):
        self.lastUpdated = time.time()

    async def putPrevQueue(self, track: lavalink.AudioTrack) -> None:
        """⏮ 用の履歴キューに積む。position=0 へのリセットもこの API の一部。"""
        track.position = 0
        await self.prevQueue.put(track)
