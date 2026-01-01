import asyncio


class MusicQueue(asyncio.Queue):
    def _get(self):
        return self._queue.pop()
