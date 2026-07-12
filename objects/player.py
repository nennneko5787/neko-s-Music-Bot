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
        """
        ⏮ ボタン用の履歴 LIFO キューにトラックを積む(SPEC_REFACTOR_PR7 で method 化)。
        再挿入時に position=0 に戻すのはこの API の一部(呼び出し側で二重設定不要)。
        """
        track.position = 0
        await self.prevQueue.put(track)
