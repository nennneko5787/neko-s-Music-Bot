import asyncio
import os
import time

import discord
from discord import app_commands
import dotenv
from discord.ext import commands, tasks

from .youtube import YoutubeAPI
from .source import YTDLSource, isPlayList
from .niconico import NicoNicoAPI, NicoNicoSource

dotenv.load_dotenv()


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.source: dict[YTDLSource] = {}
        self.queue: dict[asyncio.Queue] = {}
        self.playing: dict[bool] = {}
        self.youtube = YoutubeAPI()
        self.niconico = NicoNicoAPI()

    @commands.Cog.listener()
    async def on_ready(self):
        self.presenceLoop.start()

    @tasks.loop(seconds=20)
    async def presenceLoop(self):
        playing = []
        for p in self.playing.values():
            if p:
                playing.append(p)

        await self.bot.change_presence(
            activity=discord.Game(f"{len(playing)} / {len(self.bot.guilds)} サーバー")
        )

    def setToNotPlaying(self, guildId: int):
        self.playing[guildId] = False

    async def playNext(self, guild: discord.Guild, channel: discord.abc.Messageable):
        queue: asyncio.Queue = self.queue[guild.id]

        async def get():
            if not queue.empty():
                info: dict = await queue.get()
                if "nicovideo" in info["url"]:
                    self.source[guild.id] = await NicoNicoSource.from_url(
                        info["url"], self.niconico, info["volume"]
                    )
                else:
                    self.source[guild.id] = await YTDLSource.from_url(
                        info["url"], info["volume"]
                    )

        while not queue.empty():
            if guild.voice_client:
                if not guild.id in self.source:
                    await get()
                source: YTDLSource | NicoNicoSource = self.source[guild.id]

                embed = (
                    discord.Embed(title=source.info["title"])
                    .set_author(name="再生準備中")
                    .add_field(
                        name="再生時間",
                        value=f'0:00 / {source.info["duration_string"]}',
                    )
                )

                message = await channel.send(embed=embed)
                voiceClient: discord.VoiceClient = guild.voice_client

                if isinstance(source, NicoNicoSource):
                    await source.sendHeartBeat()

                voiceClient.play(source, after=lambda _: self.setToNotPlaying(guild.id))
                self.playing[guild.id] = True

                del self.source[guild.id]

                asyncio.create_task(get())

                while self.playing[guild.id]:
                    if isinstance(source, NicoNicoSource):
                        await source.sendHeartBeat()
                    embed = (
                        discord.Embed(title=source.info["title"])
                        .set_author(name="再生中")
                        .add_field(
                            name="再生時間",
                            value=f'{time.strftime("%H:%M:%S", time.gmtime(source.progress))} / {source.info["duration_string"]}',
                        )
                    )
                    await message.edit(embed=embed)
                    await asyncio.sleep(5)
                embed = (
                    discord.Embed(title=source.info["title"])
                    .set_author(name="再生終了")
                    .add_field(
                        name="再生時間",
                        value=f'{time.strftime("%H:%M:%S", time.gmtime(source.progress))} / {source.info["duration_string"]}',
                    )
                )
                await message.edit(embed=embed)
                voiceClient.stop()
            else:
                break
        self.playing[guild.id] = False
        del self.source[guild.id]
        await guild.voice_client.disconnect()

    @app_commands.command(name="play", description="曲を再生します。")
    async def playMusic(
        self, interaction: discord.Interaction, url: str, volume: float = 0.5
    ):
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        if not user.voice:
            await interaction.response.send_message(
                "ボイスチャンネルに接続してください。", ephemeral=True
            )
            return
        if "spotify" in url:
            await interaction.response.send_message(
                "まだSpotifyには対応していません。すみません。", ephemeral=True
            )
            return
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect()
        if not guild.id in self.playing:
            self.playing[guild.id] = False
        if not guild.id in self.queue:
            self.queue[guild.id] = asyncio.Queue()
        queue: asyncio.Queue = self.queue[guild.id]
        result = await isPlayList(url)
        if not result:
            await queue.put({"url": url, "volume": volume})
            await interaction.followup.send(f"**{url}** をキューに追加しました。")
        else:
            await asyncio.gather(
                *[
                    queue.put(
                        {
                            "url": video,
                            "volume": volume,
                        }
                    )
                    for video in result
                ]
            )
            await interaction.followup.send(
                f"**{len(result)}個の動画**をキューに追加しました。"
            )
        if not self.playing[guild.id]:
            await self.playNext(guild, channel)

    @app_commands.command(name="skip", description="曲をスキップします。")
    async def skipMusic(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        await interaction.response.defer()
        self.playing[guild.id] = False
        guild.voice_client.stop()
        await interaction.followup.send("スキップしました。")

    @app_commands.command(name="stop", description="曲を停止します。")
    async def stopMusic(self, interaction: discord.Interaction):
        guild = interaction.guild
        queue: asyncio.Queue = self.queue[guild.id]
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        await interaction.response.defer()
        await guild.voice_client.disconnect()
        while not queue.empty():
            await queue.get()
        self.playing[guild.id] = False
        await interaction.followup.send("停止しました。")

    @app_commands.command(name="pause", description="曲を一時停止します。")
    async def pauseMusic(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        if guild.voice_client.is_paused():
            await interaction.response.send_message(
                "すでに一時停止しています。", ephemeral=True
            )
            return
        await interaction.response.defer()
        await guild.voice_client.pause()
        await interaction.followup.send("一時停止しました。")

    @app_commands.command(name="resume", description="曲を一時停止します。")
    async def resumeMusic(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        if not guild.voice_client.is_paused():
            await interaction.response.send_message(
                "一時停止していません。", ephemeral=True
            )
            return
        await interaction.response.defer()
        await guild.voice_client.resume()
        await interaction.followup.send("一時停止しました。")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
