import asyncio
import os
import time
import traceback
from datetime import timedelta

import discord
from discord import app_commands
import dotenv
from discord.ext import commands, tasks
from spotdl import Spotdl
from spotdl.types.song import Song
from spotdl.types.album import Album
from spotdl.types.playlist import Playlist

from .youtube import YoutubeAPI
from .source import YTDLSource, isPlayList
from .niconico import NicoNicoAPI, NicoNicoSource

dotenv.load_dotenv()


class MusicActionPanelIfPaused(discord.ui.View):
    @discord.ui.button(emoji="▶", style=discord.ButtonStyle.blurple, custom_id="resume")
    async def resume(
        self, interaction: discord.Interaction, button: discord.Button
    ) -> None:
        if not interaction.guild.voice_client:
            embed = discord.Embed(
                title="音楽を再生していません。", colour=discord.Colour.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        interaction.guild.voice_client.resume()
        embed = interaction.message.embeds[0]
        await interaction.edit_original_response(embed=embed, view=notPausedView)


class MusicActionPanelIfNotPause(discord.ui.View):
    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.blurple, custom_id="pause")
    async def pause(
        self, interaction: discord.Interaction, button: discord.Button
    ) -> None:
        if not interaction.guild.voice_client:
            embed = discord.Embed(
                title="音楽を再生していません。", colour=discord.Colour.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        interaction.guild.voice_client.pause()
        embed = interaction.message.embeds[0]
        await interaction.edit_original_response(embed=embed, view=pausedView)


pausedView = MusicActionPanelIfPaused(timeout=None)
notPausedView = MusicActionPanelIfNotPause(timeout=None)


def formatTime(seconds):
    if seconds < 3600:
        return time.strftime("%M:%S", time.gmtime(seconds))
    elif seconds < 86400:
        return time.strftime("%H:%M:%S", time.gmtime(seconds))
    else:
        return time.strftime("%d:%H:%M:%S", time.gmtime(seconds))


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.source: dict[YTDLSource] = {}
        self.queue: dict[asyncio.Queue] = {}
        self.playing: dict[bool] = {}
        self.alarm: dict[bool] = {}
        self.youtube = YoutubeAPI()
        self.niconico = NicoNicoAPI()
        self.spotify = Spotdl(
            client_id=os.getenv("spotify_clientid"),
            client_secret=os.getenv("spotify_clientsecret"),
        )

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
            activity=discord.Game(
                f"脆弱性対策済みver / {len(playing)} / {len(self.bot.guilds)} サーバー"
            )
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

        while True:
            if guild.voice_client:
                try:
                    if not guild.id in self.source:
                        await get()
                except:
                    traceback.print_exc()
                    continue

                if (queue.empty()) and (not guild.id in self.source):
                    break
                
                try:
                    source: YTDLSource | NicoNicoSource = self.source[guild.id]
                except:
                    traceback.print_exc()
                    continue

                embed = (
                    discord.Embed(
                        title=source.info["title"],
                        colour=discord.Colour.purple(),
                        url=source.info["webpage_url"],
                    )
                    .set_image(url=source.info["thumbnail"])
                    .set_author(name="再生準備中")
                    .add_field(
                        name="再生時間",
                        value=f'{formatTime(source.progress)} / {formatTime(source.info["duration"])}',
                    )
                )

                message = await channel.send(embed=embed, view=notPausedView)
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
                        discord.Embed(
                            title=source.info["title"],
                            colour=discord.Colour.purple(),
                            url=source.info["webpage_url"],
                        )
                        .set_image(url=source.info["thumbnail"])
                        .set_author(name="再生中")
                        .add_field(
                            name="再生時間",
                            value=f'{formatTime(source.progress)} / {formatTime(source.info["duration"])}',
                        )
                    )
                    await message.edit(
                        embed=embed,
                        view=(
                            notPausedView if not voiceClient.is_paused() else pausedView
                        ),
                    )
                    await asyncio.sleep(5)
                embed = (
                    discord.Embed(
                        title=source.info["title"], url=source.info["webpage_url"]
                    )
                    .set_image(url=source.info["thumbnail"])
                    .set_author(name="再生終了")
                    .add_field(
                        name="再生時間",
                        value=f'{formatTime(source.progress)} / {formatTime(source.info["duration"])}',
                    )
                )
                await message.edit(embed=embed, view=None)
                voiceClient.stop()
            else:
                break
        await channel.send("再生終了")
        self.playing[guild.id] = False
        if guild.id in self.source:
            del self.source[guild.id]
        if guild.voice_client:
            await guild.voice_client.disconnect()

    @app_commands.command(name="alarm", description="アラームをセットします。")
    async def alarmCommand(
        self,
        interaction: discord.Interaction,
        delay: app_commands.Range[int, 0],
        url: str,
        volume: float = 0.5,
    ):
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        if not user.voice:
            await interaction.response.send_message(
                "ボイスチャンネルに接続してください。", ephemeral=True
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
        if "spotify" in url:
            if "track" in url:
                song: Song = await asyncio.to_thread(Song.from_url, url)
                urls: list[str | None] = await asyncio.to_thread(
                    self.spotify.get_download_urls, [song]
                )
            elif "album" in url:
                album = await asyncio.to_thread(Album.from_url, url)
                urls: list[str | None] = await asyncio.to_thread(
                    self.spotify.get_download_urls, album.songs
                )
            elif "playlist" in url:
                playlist = await asyncio.to_thread(Playlist.from_url, url)
                urls: list[str | None] = await asyncio.to_thread(
                    self.spotify.get_download_urls, playlist.songs
                )
            else:
                await interaction.followup.send("無効なSpotify URL")
                return

            await asyncio.gather(
                *[
                    queue.put(
                        {
                            "url": music,
                            "volume": volume,
                        }
                    )
                    for music in urls
                ]
            )
            await interaction.followup.send(
                f"**{len(urls)}個の曲**をキューに追加しました。"
            )
        else:
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
        if (not self.playing[guild.id]) and (not self.alarm.get(guild.id, False)):
            await self.playNext(guild, channel)

        self.alarm[guild.id] = True

        embed = discord.Embed(
            title="アラームをセットしました！",
            description=f"{discord.utils.format_dt(discord.utils.utcnow()+timedelta(seconds=delay), 'R')} に音楽を再生します。\n-# VCに参加している端末の電池残量・電力消費に注意してください。\n-# また、アラームを設定している最中にボットが再起動されると、アラームはリセットされます。ご注意ください。",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed)

        await asyncio.sleep(delay)
        del self.alarm[guild.id]
        await self.playNext(guild, channel)

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
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect()
        if not guild.id in self.playing:
            self.playing[guild.id] = False
        if not guild.id in self.queue:
            self.queue[guild.id] = asyncio.Queue()
        queue: asyncio.Queue = self.queue[guild.id]
        if "spotify" in url:
            if "track" in url:
                song: Song = await asyncio.to_thread(Song.from_url, url)
                urls: list[str | None] = await asyncio.to_thread(
                    self.spotify.get_download_urls, [song]
                )
            elif "album" in url:
                album = await asyncio.to_thread(Album.from_url, url)
                urls: list[str | None] = await asyncio.to_thread(
                    self.spotify.get_download_urls, album.songs
                )
            elif "playlist" in url:
                playlist = await asyncio.to_thread(Playlist.from_url, url)
                urls: list[str | None] = await asyncio.to_thread(
                    self.spotify.get_download_urls, playlist.songs
                )
            else:
                await interaction.followup.send("無効なSpotify URL")
                return

            await asyncio.gather(
                *[
                    queue.put(
                        {
                            "url": music,
                            "volume": volume,
                        }
                    )
                    for music in urls
                ]
            )
            await interaction.followup.send(
                f"**{len(urls)}個の曲**をキューに追加しました。"
            )
        else:
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
        if (not self.playing[guild.id]) and (not self.alarm.get(guild.id, False)):
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
    bot.add_view(pausedView)
    bot.add_view(notPausedView)
    await bot.add_cog(MusicCog(bot))
