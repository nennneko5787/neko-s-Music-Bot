import asyncio
import discord
import orjson

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class FetchVideoInfoFailed(Exception):
    pass


async def isPlayList(url) -> list[str] | bool:
    process = await asyncio.create_subprocess_shell(
        f'yt-dlp -j -f bestaudio/best --cookies ./cookies.txt --flat-playlist --no-playlist --no-download -i "{url}"',
        stderr=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        json = f"[{','.join(stdout.decode('utf-8').strip().splitlines())}]"
        videoInfo: list = orjson.loads(json)
        if len(videoInfo) > 1:
            urls = []
            for info in videoInfo:
                urls.append(info["url"])
            return urls
        else:
            return False
    else:
        raise FetchVideoInfoFailed(f"download failed: {url}")


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
    async def getVideoInfo(cls, url) -> dict:
        process = await asyncio.create_subprocess_shell(
            f'yt-dlp -j -f bestaudio/best --cookies ./cookies.txt --no-playlist "{url}"',
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            videoInfo = orjson.loads(stdout.decode("utf-8"))
            return videoInfo
        else:
            raise FetchVideoInfoFailed(f"download failed: {url}")

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
