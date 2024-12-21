import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor

import discord
from yt_dlp import YoutubeDL

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -bufsize 64k -analyzeduration 2147483647 -probesize 2147483647",
}

_log = logging.getLogger("music")


class FetchVideoInfoFailed(Exception):
    pass


def _isPlayList(url) -> list[str] | bool:
    try:
        ydlOpts = {
            "quiet": True,
            "extract_flat": True,
            "cookiefile": "./cookies.txt",
        }
        with YoutubeDL(ydlOpts) as ydl:
            info = ydl.sanitize_info(ydl.extract_info(url, download=False))
        if "entries" in info and len(info["entries"]) > 1:
            urls = [entry["url"] for entry in info["entries"]]
            return urls
        else:
            return False
    except Exception as e:
        raise FetchVideoInfoFailed(f"Failed to fetch video info: {url}, {str(e)}")


async def isPlayList(url: str) -> list[str] | bool:
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as executor:
        return await loop.run_in_executor(executor, _isPlayList, url)


class YTDLSource(discord.PCMVolumeTransformer):
    """yt-dlpとうまく連携できるAudioSourceを提供します。クラスを直接作るのではなく、from_url関数を使用してAudioSourceを作成してください。"""

    __slots__ = (
        "info",
        "__count",
        "user",
    )

    def __init__(
        self,
        source,
        *,
        info: dict,
        volume: float = 0.5,
        progress: float = 0,
        user: discord.Member = None,
    ):
        super().__init__(source, volume=volume)
        self.info: dict = info
        self.__count = progress
        self.user = user

    @property
    def progress(self) -> float:
        return self.__count * 0.02  # count * 20ms

    def read(self) -> bytes:
        data = super().read()
        if data:
            self.__count += 1
        return data

    @classmethod
    def _getVideoInfo(cls, url) -> dict:
        try:
            ydlOpts = {
                "quiet": True,
                "format": "bestaudio/best",
                "noplaylist": True,
                "cookiefile": "./cookies.txt",
            }
            ydl = YoutubeDL(ydlOpts)
            info = ydl.sanitize_info(ydl.extract_info(url, download=False))
            return info
        except Exception as e:
            raise FetchVideoInfoFailed(f"Failed to fetch video info: {url}, {str(e)}")

    @classmethod
    async def getVideoInfo(cls, url: str) -> dict:
        loop = asyncio.get_event_loop()
        with ProcessPoolExecutor() as executor:
            return await loop.run_in_executor(executor, cls._getVideoInfo, url)

    @classmethod
    async def from_url(cls, url, volume: float = 0.5, user: discord.Member = None):
        """urlからAudioSourceを作成します。

        Args:
            url (str): yt-dlpに対応しているURL。
            volume (float, optional): AudioSourceの音量。デフォルトは0.5です。

        Returns:
            YTDLSource: 完成したAudioSource。
        """
        _log.info(f"loading {url} with YTDLSource now")
        info = await cls.getVideoInfo(url)
        _log.info(f"success loading {url}")
        if "entries" in info:
            info = info.get("entries", [])[0]
        return cls(
            discord.FFmpegPCMAudio(info.get("url", ""), **FFMPEG_OPTIONS),
            info=info,
            volume=volume,
            user=user,
        )
