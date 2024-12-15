import asyncio
import discord
from concurrent.futures import ThreadPoolExecutor

from yt_dlp import YoutubeDL

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class FetchVideoInfoFailed(Exception):
    pass


def _isPlayList(url) -> list[str] | bool:
    try:
        ydlOpts = {
            "quiet": True,
            "extract_flat": True,
            "cookiefile": "./cookies.txt",
        }
        ydl = YoutubeDL(ydlOpts)
        info = ydl.extract_info(url, download=False)
        if "entries" in info and len(info["entries"]) > 1:
            urls = [entry["url"] for entry in info["entries"]]
            return urls
        else:
            return False
    except Exception as e:
        raise FetchVideoInfoFailed(f"Failed to fetch video info: {url}, {str(e)}")


async def isPlayList(url: str) -> list[str] | bool:
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        return await loop.run_in_executor(executor, _isPlayList, url)


class YTDLSource(discord.PCMVolumeTransformer):
    """yt-dlpとうまく連携できるAudioSourceを提供します。クラスを直接作るのではなく、from_url関数を使用してAudioSourceを作成してください。"""

    def __init__(self, source, *, info: dict, volume: float = 0.5):
        super().__init__(source, volume=volume)
        self.info: dict = info
        self._count = 0

    @property
    def progress(self) -> float:
        return self._count * 0.02  # count * 20ms

    def read(self) -> bytes:
        data = super().read()
        if data:
            self._count += 1
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
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            raise FetchVideoInfoFailed(f"Failed to fetch video info: {url}, {str(e)}")

    @classmethod
    async def getVideoInfo(self, url: str) -> dict:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self._getVideoInfo, url)

    @classmethod
    async def from_url(cls, url, volume: float = 0.5):
        """urlからAudioSourceを作成します。

        Args:
            url (str): yt-dlpに対応しているURL。
            volume (float, optional): AudioSourceの音量。デフォルトは0.5です。

        Returns:
            YTDLSource: 完成したAudioSource。
        """
        print(f"loading {url}")
        info = await cls.getVideoInfo(url)
        print("ok")
        if "entries" in info:
            info = info.get("entries", [])[0]
        fileName = info.get("url", "")
        return cls(
            discord.FFmpegPCMAudio(fileName, **FFMPEG_OPTIONS), info=info, volume=volume
        )
