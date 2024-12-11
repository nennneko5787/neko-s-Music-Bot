import asyncio
import discord
import orjson

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -bufsize 64k -analyzeduration 2147483647 -probesize 2147483647",
}


class FetchVideoInfoFailed(Exception):
    pass


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
            video_info = orjson.loads(stdout.decode("utf-8"))
            return video_info
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
