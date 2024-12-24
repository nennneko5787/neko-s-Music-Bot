from .queue import Queue


class GuildState:
    __slots__ = (
        "playing",
        "queue",
        "alarm",
    )

    def __init__(self):
        self.playing: bool = False
        self.queue: Queue = Queue()
        self.alarm: bool = False
