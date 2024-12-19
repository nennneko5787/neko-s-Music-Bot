import asyncio
import discord
import time

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class MimeTypeNotMatch(Exception):
    pass


class DiscordFileSource(discord.PCMVolumeTransformer):
    """Discordの添付ファイルとうまく連携できるAudioSourceを提供します。クラスを直接作るのではなく、from_url関数を使用してAudioSourceを作成してください。"""

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
        self._count = progress
        self.user = user

    @property
    def progress(self) -> float:
        return self._count * 0.02  # count * 20ms

    def read(self) -> bytes:
        data = super().read()
        if data:
            self._count += 1
        return data

    @classmethod
    async def from_attachment(
        cls,
        attachment: discord.Attachment,
        volume: float = 0.5,
        user: discord.Member = None,
    ):
        """attachmentからAudioSourceを作成します。

        Args:
            attachment (discord.Attachment): Discordの添付ファイル。
            volume (float, optional): AudioSourceの音量。デフォルトは0.5です。

        Returns:
            DiscordFileSource: 完成したAudioSource。
        """
        print(f"loading {attachment.url}")
        if attachment.duration is None:
            raise MimeTypeNotMatch()

        info = {
            "title": attachment.filename,
            "duration_string": time.strftime(
                "%H:%M:%S",
                time.gmtime(attachment.duration),
            ),
            "duration": int(attachment.duration),
            "url": attachment.url,
            "webpage_url": attachment.url,
            "thumbnail": user.display_avatar,
        }
        fileName = attachment.url
        print("ok")
        return cls(
            discord.FFmpegPCMAudio(fileName, **FFMPEG_OPTIONS),
            info=info,
            volume=volume,
            user=user,
        )
