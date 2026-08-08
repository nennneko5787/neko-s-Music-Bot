from lavalink.filters import Timescale

from objects.player import MusicPlayer
from objects.utils import clamp


def getTimescale(player: MusicPlayer):
    return player.get_filter(Timescale)


async def changeSpeed(player: MusicPlayer, up: bool):
    timescale = getTimescale(player)

    if not timescale:
        speed = 1.0
        pitch = 1.0
    else:
        speed = timescale.values["speed"]
        pitch = timescale.values["pitch"]

    speed += 0.1 if up else -0.1

    await player.set_filter(Timescale(clamp(speed, 0.1, 2.0), clamp(pitch, 0.1, 2.0), 1))


async def changePitch(player: MusicPlayer, up: bool):
    timescale = getTimescale(player)

    if not timescale:
        speed = 1.0
        pitch = 1.0
    else:
        speed = timescale.values["speed"]
        pitch = timescale.values["pitch"]

    pitch += 0.1 if up else -0.1

    await player.set_filter(Timescale(clamp(speed, 0.1, 2.0), clamp(pitch, 0.1, 2.0), 1))
