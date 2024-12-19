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

from .source import YTDLSource, isPlayList
from .filesource import DiscordFileSource
from .niconico import NicoNicoSource
from .queue import Queue
from .search import searchYoutube

dotenv.load_dotenv()

pausedView = (
    discord.ui.View(timeout=None)
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏪", custom_id="reverse", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="▶", custom_id="resume", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏩", custom_id="forward", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏮", custom_id="prev", row=1
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏹", custom_id="stop", row=1
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏭", custom_id="next", row=1
        )
    )
)
notPausedView = (
    discord.ui.View(timeout=None)
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏪", custom_id="reverse", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏸", custom_id="pause", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏩", custom_id="forward", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏮", custom_id="prev", row=1
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏹", custom_id="stop", row=1
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏭", custom_id="next", row=1
        )
    )
)


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
        self.queue: dict[Queue] = {}
        self.playing: dict[bool] = {}
        self.alarm: dict[bool] = {}
        self.seeking: dict[bool] = {}
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
                f"{len(playing)} 再生中 / {len(self.alarm.keys())} アラーム / {len(self.bot.guilds)} サーバー"
            )
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            if interaction.data["component_type"] == 2:
                await self.onButtonClick(interaction)
            elif interaction.data["component_type"] == 3:
                pass
        except KeyError:
            pass

    async def onButtonClick(self, interaction: discord.Interaction):
        customId = interaction.data["custom_id"]
        match (customId):
            case "prev":
                if not interaction.guild.voice_client:
                    await interaction.response.send_message(
                        "現在曲を再生していません。", ephemeral=True
                    )
                    return
                await interaction.response.defer(ephemeral=True)
                self.queue[interaction.guild.id].prev()
                if self.source.get(interaction.guild.id):
                    del self.source[interaction.guild.id]
                interaction.guild.voice_client.stop()
            case "next":
                if not interaction.guild.voice_client:
                    await interaction.response.send_message(
                        "現在曲を再生していません。", ephemeral=True
                    )
                    return
                await interaction.response.defer(ephemeral=True)
                self.playing[interaction.guild.id] = False
                interaction.guild.voice_client.stop()
            case "stop":
                if not interaction.guild.voice_client:
                    await interaction.response.send_message(
                        "現在曲を再生していません。", ephemeral=True
                    )
                    return
                await interaction.response.defer()
                await interaction.guild.voice_client.disconnect()
                del self.queue[interaction.guild.id]
                self.playing[interaction.guild.id] = False
            case "resume":
                if not interaction.guild.voice_client:
                    embed = discord.Embed(
                        title="音楽を再生していません。", colour=discord.Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                interaction.guild.voice_client.resume()
                embed = interaction.message.embeds[0]
                await interaction.edit_original_response(
                    embed=embed, view=notPausedView
                )
            case "pause":
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
            case "reverse":
                if not interaction.guild.voice_client:
                    embed = discord.Embed(
                        title="音楽を再生していません。", colour=discord.Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                if self.seeking.get(interaction.guild.id, False) is True:
                    return
                self.seeking[interaction.guild.id] = True
                source: YTDLSource | NicoNicoSource = (
                    interaction.guild.voice_client.source
                )
                options = {
                    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                    "options": f"-vn -ss {formatTime(source.progress-10)}",
                }

                if isinstance(source, NicoNicoSource):
                    options["before_options"] = (
                        f"-headers 'cookie: {'; '.join(f'{k}={v}' for k, v in source.client.cookies.items())}' {options['before_options']}"
                    )
                    interaction.guild.voice_client.source = NicoNicoSource(
                        discord.FFmpegPCMAudio(source.hslContentUrl, **options),
                        info=source.info,
                        hslContentUrl=source.hslContentUrl,
                        watchid=source.watchid,
                        trackid=source.trackid,
                        outputs=source.outputs,
                        nicosid=source.nicosid,
                        niconico=source.niconico,
                        volume=source.volume,
                        progress=(source.progress - 10) / 0.02,
                        user=source.user,
                    )
                elif isinstance(source, DiscordFileSource):
                    interaction.guild.voice_client.source = DiscordFileSource(
                        discord.FFmpegPCMAudio(source.info["url"], **options),
                        info=source.info,
                        volume=source.volume,
                        progress=(source.progress - 10) / 0.02,
                        user=source.user,
                    )
                else:
                    interaction.guild.voice_client.source = YTDLSource(
                        discord.FFmpegPCMAudio(source.info["url"], **options),
                        info=source.info,
                        volume=source.volume,
                        progress=(source.progress - 10) / 0.02,
                        user=source.user,
                    )
                self.seeking[interaction.guild.id] = False
            case "forward":
                if not interaction.guild.voice_client:
                    embed = discord.Embed(
                        title="音楽を再生していません。", colour=discord.Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                if self.seeking.get(interaction.guild.id, False) is True:
                    return
                self.seeking[interaction.guild.id] = True
                source: YTDLSource | NicoNicoSource = (
                    interaction.guild.voice_client.source
                )
                options = {
                    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                    "options": f"-vn -ss {formatTime(source.progress+10)}",
                }

                if isinstance(source, NicoNicoSource):
                    options["before_options"] = (
                        f"-headers 'cookie: {'; '.join(f'{k}={v}' for k, v in source.client.cookies.items())}' {options['before_options']}"
                    )
                    interaction.guild.voice_client.source = NicoNicoSource(
                        discord.FFmpegPCMAudio(source.hslContentUrl, **options),
                        info=source.info,
                        hslContentUrl=source.hslContentUrl,
                        watchid=source.watchid,
                        trackid=source.trackid,
                        outputs=source.outputs,
                        nicosid=source.nicosid,
                        niconico=source.niconico,
                        volume=source.volume,
                        progress=(source.progress + 10) / 0.02,
                        user=source.user,
                    )
                elif isinstance(source, DiscordFileSource):
                    interaction.guild.voice_client.source = DiscordFileSource(
                        discord.FFmpegPCMAudio(source.info["url"], **options),
                        info=source.info,
                        volume=source.volume,
                        progress=(source.progress + 10) / 0.02,
                        user=source.user,
                    )
                else:
                    interaction.guild.voice_client.source = YTDLSource(
                        discord.FFmpegPCMAudio(source.info["url"], **options),
                        info=source.info,
                        volume=source.volume,
                        progress=(source.progress + 10) / 0.02,
                        user=source.user,
                    )
                self.seeking[interaction.guild.id] = False

    def setToNotPlaying(self, guildId: int):
        self.playing[guildId] = False

    def embedPanel(
        self,
        voiceClient: discord.VoiceClient,
        *,
        source: YTDLSource | NicoNicoSource = None,
        finished: bool = False,
    ):
        if source is None:
            if voiceClient.source is None:
                return None
            source: YTDLSource | NicoNicoSource | DiscordFileSource = voiceClient.source
        embed = discord.Embed(
            title=source.info["title"],
            url=source.info["webpage_url"],
        ).set_image(url=source.info["thumbnail"])

        if finished:
            embed.colour = discord.Colour.greyple()
            embed.set_author(name="再生終了")
        elif voiceClient.is_playing() or voiceClient.is_paused():
            percentage = source.progress / source.info["duration"]
            barLength = 30
            filledLength = int(barLength * percentage)
            progressBar = "･" * filledLength + "-" * (barLength - filledLength)

            embed.colour = discord.Colour.purple()
            if voiceClient.is_paused():
                embed.set_author(name="一時停止中")
            else:
                embed.set_author(name="再生中")
            embed.add_field(
                name="再生時間",
                value=f'\\|{progressBar}\\|\n`{formatTime(source.progress)} / {formatTime(source.info["duration"])}`',
                inline=False,
            ).add_field(
                name="リクエストしたユーザー",
                value=f"{source.user.mention}",
                inline=False,
            )
        else:
            embed.colour = discord.Colour.greyple()
            embed.set_author(name="再生準備中")
        return embed

    async def playNext(self, guild: discord.Guild, channel: discord.abc.Messageable):
        queue: Queue = self.queue[guild.id]

        async def get():
            if not queue.empty():
                info: dict = queue.get()
                if (info["url"] is None) and (info.get("attachment")):
                    self.source[guild.id] = await DiscordFileSource.from_attachment(
                        info["attachment"], info["volume"], info["user"]
                    )
                elif "nicovideo" in info["url"]:
                    self.source[guild.id] = await NicoNicoSource.from_url(
                        info["url"], info["volume"], info["user"]
                    )
                else:
                    self.source[guild.id] = await YTDLSource.from_url(
                        info["url"], info["volume"], info["user"]
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
                    source: YTDLSource | NicoNicoSource | DiscordFileSource = (
                        self.source[guild.id]
                    )
                except:
                    traceback.print_exc()
                    continue

                voiceClient: discord.VoiceClient = guild.voice_client
                message = await channel.send(
                    embed=self.embedPanel(voiceClient, source=source),
                    view=notPausedView,
                )

                if isinstance(source, NicoNicoSource):
                    await source.sendHeartBeat()

                voiceClient.play(source, after=lambda _: self.setToNotPlaying(guild.id))
                self.playing[guild.id] = True

                del self.source[guild.id]

                asyncio.create_task(get())

                _break = False
                while self.playing[guild.id]:
                    if isinstance(source, NicoNicoSource):
                        await source.sendHeartBeat()
                    if voiceClient.source is not None:
                        source = voiceClient.source
                    if not voiceClient.is_paused():
                        await message.edit(
                            embed=self.embedPanel(voiceClient, source=source),
                            view=(
                                notPausedView
                                if not voiceClient.is_paused()
                                else pausedView
                            ),
                        )
                    for _ in range(5):
                        if not self.playing[guild.id]:
                            _break = True
                            break
                        await asyncio.sleep(1)
                    if _break:
                        break
                await message.edit(
                    embed=self.embedPanel(voiceClient, source=source, finished=True),
                    view=None,
                )
                voiceClient.stop()
            else:
                break
        await channel.send("再生終了")
        self.playing[guild.id] = False
        if guild.id in self.source:
            del self.source[guild.id]
        if guild.id in self.seeking:
            del self.seeking[guild.id]
        if guild.voice_client:
            await guild.voice_client.disconnect()

    async def putQueue(self, interaction: discord.Interaction, url: str, volume: float):
        queue: Queue = self.queue[interaction.guild.id]
        if "music.apple.com" in url:
            await interaction.response.send_message("Apple Musicには対応していません。")
            return

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

            for music in urls:
                queue.put(
                    {
                        "url": music,
                        "volume": volume,
                        "user": interaction.user,
                    }
                )
            await interaction.followup.send(
                f"**{len(urls)}個の曲**をキューに追加しました。"
            )
        else:
            result = await isPlayList(url)
            if not result:
                queue.put({"url": url, "volume": volume, "user": interaction.user})
                await interaction.followup.send(f"**{url}** をキューに追加しました。")
            else:
                for video in result:
                    queue.put(
                        {
                            "url": video,
                            "volume": volume,
                            "user": interaction.user,
                        }
                    )
                await interaction.followup.send(
                    f"**{len(result)}個の動画**をキューに追加しました。"
                )

    @app_commands.command(name="alarm", description="アラームをセットします。")
    @app_commands.guild_only()
    async def alarmCommand(
        self,
        interaction: discord.Interaction,
        delay: app_commands.Range[int, 0],
        url: str,
        volume: app_commands.Range[float, 0.0, 2.0] = 0.5,
    ):
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        if not user.voice:
            await interaction.response.send_message(
                "ボイスチャンネルに接続してください。", ephemeral=True
            )
            return
        if self.playing.get(guild.id, False) is True:
            await interaction.response.send_message(
                "現在曲を再生中です。停止してからアラームをセットしてください。",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect(self_deaf=True)
        if not guild.id in self.playing:
            self.playing[guild.id] = False
        if not guild.id in self.queue:
            self.queue[guild.id] = Queue()
        await self.putQueue(interaction, url, volume)

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
    @app_commands.guild_only()
    async def playMusic(
        self,
        interaction: discord.Interaction,
        url: str,
        volume: app_commands.Range[float, 0.0, 2.0] = 0.5,
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
            await user.voice.channel.connect(self_deaf=True)
        if not guild.id in self.playing:
            self.playing[guild.id] = False
        if not guild.id in self.queue:
            self.queue[guild.id] = Queue()
        await self.putQueue(interaction, url, volume)
        if (not self.playing[guild.id]) and (not self.alarm.get(guild.id, False)):
            await self.playNext(guild, channel)

    @app_commands.command(
        name="playfile",
        description="Discordのファイルを再生します。動画ファイルか音声ファイルでなければなりません。",
    )
    @app_commands.guild_only()
    async def playFile(
        self,
        interaction: discord.Interaction,
        attachment: discord.Attachment,
        volume: app_commands.Range[float, 0.0, 2.0] = 2.0,
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
            await user.voice.channel.connect(self_deaf=True)
        if not guild.id in self.playing:
            self.playing[guild.id] = False
        if not guild.id in self.queue:
            self.queue[guild.id] = Queue()
        queue: Queue = self.queue[guild.id]
        queue.put(
            {
                "url": None,
                "attachment": attachment,
                "volume": volume,
                "user": interaction.user,
            }
        )
        await interaction.followup.send(
            f"**{attachment.filename}**をキューに追加しました。"
        )
        if (not self.playing[guild.id]) and (not self.alarm.get(guild.id, False)):
            await self.playNext(guild, channel)

    @app_commands.command(
        name="alarmfile", description="Discordのファイルのアラームをセットします。"
    )
    @app_commands.guild_only()
    async def alarmFileCommand(
        self,
        interaction: discord.Interaction,
        delay: app_commands.Range[int, 0],
        attachment: discord.Attachment,
        volume: app_commands.Range[float, 0.0, 2.0] = 2.0,
    ):
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        if not user.voice:
            await interaction.response.send_message(
                "ボイスチャンネルに接続してください。", ephemeral=True
            )
            return
        if self.playing.get(guild.id, False) is True:
            await interaction.response.send_message(
                "現在曲を再生中です。停止してからアラームをセットしてください。",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect(self_deaf=True)
        if not guild.id in self.playing:
            self.playing[guild.id] = False
        if not guild.id in self.queue:
            self.queue[guild.id] = Queue()
        queue: Queue = self.queue[guild.id]
        queue.put(
            {
                "url": None,
                "attachment": attachment,
                "volume": volume,
                "user": interaction.user,
            }
        )

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

    searchCommandGroup = app_commands.Group(
        name="search", description="曲を検索して再生します。", guild_only=True
    )

    @searchCommandGroup.command(
        name="youtube", description="Youtubeから動画を検索して再生します。"
    )
    async def searchYoutubeCommand(
        self,
        interaction: discord.Interaction,
        keyword: str,
        volume: app_commands.Range[float, 0.0, 2.0] = 0.5,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        view = discord.ui.View(timeout=None)
        select = discord.ui.Select(custom_id="ytsearch")
        videos = await searchYoutube(keyword)
        for video in videos:
            select.add_option(
                label=video["title"],
                description=video["uploader"],
                value=f"{video['url']}|{volume}",
            )

        async def selectCallBack(interaction: discord.Interaction):
            url, volume = interaction.data["values"][0].split("|")
            user = interaction.user
            if not user.voice:
                await interaction.response.send_message(
                    "ボイスチャンネルに接続してください。", ephemeral=True
                )
                return
            guild = interaction.guild
            channel = interaction.channel
            await interaction.response.defer()
            if not guild.voice_client:
                await user.voice.channel.connect(self_deaf=True)
            if not guild.id in self.playing:
                self.playing[guild.id] = False
            if not guild.id in self.queue:
                self.queue[guild.id] = Queue()
            await self.putQueue(interaction, url, float(volume))
            if (not self.playing[guild.id]) and (not self.alarm.get(guild.id, False)):
                await self.playNext(guild, channel)

        select.callback = selectCallBack

        view.add_item(select)
        embed = discord.Embed(
            title=f"{len(videos)}本の動画がヒットしました。",
            description="動画を選択して、キューに追加します。",
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="skip", description="曲をスキップします。")
    @app_commands.guild_only()
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
    @app_commands.guild_only()
    async def stopMusic(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        await interaction.response.defer()
        await guild.voice_client.disconnect()
        del self.queue[guild.id]
        self.playing[guild.id] = False
        await interaction.followup.send("停止しました。")

    @app_commands.command(name="pause", description="曲を一時停止します。")
    @app_commands.guild_only()
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
    @app_commands.guild_only()
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
