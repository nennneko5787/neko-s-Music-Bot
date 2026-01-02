import time

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
