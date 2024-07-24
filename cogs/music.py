import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import time

import discord
from discord.ext import commands
from yt_dlp import YoutubeDL

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -bufsize 64k -analyzeduration 2147483647 -probesize 2147483647",
}


ytdlOptions: dict = {
    "format": "bestaudio/best",
    "quiet": True,
}


class YTDLSource(discord.PCMVolumeTransformer):
    """yt-dlpとうまく連携できるAudioSourceを提供します。クラスを直接作るのではなく、from_url関数を使用してAudioSourceを作成してください。"""

    def __init__(self, source, *, info: dict, volume: float = 0.5):
        super().__init__(source, volume=volume)
        self.info: dict = info

    @classmethod
    def getVideoInfo(cls, url):
        ytdl = YoutubeDL(ytdlOptions)
        return ytdl.extract_info(url, download=False)

    @classmethod
    async def from_url(cls, url, volume: float = 0.5):
        """urlからAudioSourceを作成します。

        Args:
            url (str): yt-dlpに対応しているURL。
            volume (float, optional): AudioSourceの音量。デフォルトは0.5です。

        Returns:
            YTDLSource: 完成したAudioSource。
        """
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            info = await loop.run_in_executor(executor, cls.getVideoInfo, url)
        if "entries" in info:
            info = info.get("entries", [])[0]
        fileName = info.get("url", "")
        return cls(
            discord.FFmpegPCMAudio(fileName, **FFMPEG_OPTIONS), info=info, volume=volume
        )


class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue: dict[asyncio.Queue] = {}
        self.playing: dict[bool] = {}

    def setToNotPlaying(self, guild_id: int):
        self.playing[guild_id] = False

    async def playNext(self, guild: discord.Guild, channel: discord.abc.Messageable):
        queue: asyncio.Queue = self.queue[guild.id]
        count = 0
        maxCount = queue.qsize()
        while count <= maxCount:
            playingTime = datetime.now().timestamp()
            startTime = datetime.now().timestamp()
            source: YTDLSource = await queue.get()
            source.read()
            if guild.voice_client:
                embed = (
                    discord.Embed(title=source.info["title"])
                    .set_author(name="再生中")
                    .add_field(
                        name="再生時間",
                        value=f'0:00 / {source.info["duration_string"]}',
                    )
                )
                message = await channel.send(embed=embed)
                voiceClient: discord.VoiceClient = guild.voice_client
                voiceClient.play(
                    source, after=lambda error: self.setToNotPlaying(guild.id)
                )
                self.playing[guild.id] = True
                while self.playing[guild.id]:
                    playingTime += 1
                    embed = (
                        discord.Embed(title=source.info["title"])
                        .set_author(name="再生中")
                        .add_field(
                            name="再生時間",
                            value=f'{time.strftime("%H:%M:%S", time.gmtime(playingTime - startTime))} / {source.info["duration_string"]}',
                        )
                    )
                    await message.edit(embed=embed)
                    await asyncio.sleep(1)

    @commands.hybrid_command(name="play", description="曲を再生します。")
    async def playMusic(self, ctx: commands.Context, url: str, volume: float = 0.5):
        user = ctx.author
        guild = ctx.guild
        channel = ctx.channel
        if not user.voice:
            await ctx.reply("ボイスチャンネルに接続してください。", ephemeral=True)
            return
        await ctx.defer()
        if not self.queue.get(guild.id) or not guild.voice_client:
            if not guild.voice_client:
                await user.voice.channel.connect()
            self.queue[guild.id] = asyncio.Queue()
            self.playing[guild.id] = False
            queue: asyncio.Queue = self.queue[guild.id]
            source: YTDLSource = await YTDLSource.from_url(url, volume=volume)
            await queue.put(source)
            await ctx.reply(f'**{source.info.get("title")}** をキューに追加しました。')
            await ctx.reply("再生を開始します。")
            await self.playNext(guild, channel)
        else:
            queue: asyncio.Queue = self.queue[guild.id]
            source: YTDLSource = await YTDLSource.from_url(url, volume=volume)
            await queue.put(source)
            await ctx.reply(f'**{source.info.get("title")}** をキューに追加しました。')

    @commands.hybrid_command(name="skip", description="曲をスキップします。")
    async def skipMusic(self, ctx: commands.Context):
        guild = ctx.guild
        if not guild.voice_client:
            ctx.reply("現在曲を再生していません。", ephemeral=True)
        self.playing[guild.id] = False
        ctx.reply("スキップしました。")

    @commands.hybrid_command(name="stop", description="曲を停止します。")
    async def stopMusic(self, ctx: commands.Context):
        guild = ctx.guild
        queue: asyncio.Queue = self.queue[guild.id]
        if not guild.voice_client:
            ctx.reply("現在曲を再生していません。", ephemeral=True)
        await guild.voice_client.disconnect()
        await queue.join()
        self.playing[guild.id] = False
        ctx.reply("停止しました。")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
