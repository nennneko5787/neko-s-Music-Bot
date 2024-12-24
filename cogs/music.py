import asyncio
import math
import os
import random
import traceback
from datetime import timedelta

import discord
import dotenv
from discord import app_commands
from discord.ext import commands, tasks
from spotdl import Spotdl
from spotdl.types.album import Album
from spotdl.types.playlist import Playlist
from spotdl.types.song import Song

from objects.queue import Queue
from objects.state import GuildState
from source.filesource import DiscordFileSource
from source.niconico import NicoNicoSource
from source.source import YTDLSource, isPlayList
from utils.func import clamp, formatTime
from utils.search import searchNicoNico, searchYoutube

dotenv.load_dotenv()


def createView(isPaused: bool):
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏪", custom_id="reverse", row=0
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple,
            emoji="▶" if isPaused else "⏸",
            custom_id="resume" if isPaused else "pause",
            row=0,
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏩", custom_id="forward", row=0
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, label="+", custom_id="volumeUp", row=0
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏮", custom_id="prev", row=1
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏹", custom_id="stop", row=1
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏭", custom_id="next", row=1
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, label="-", custom_id="volumeDown", row=1
        )
    )
    return view


pausedView = createView(isPaused=True)
notPausedView = createView(isPaused=False)


class MusicCog(commands.Cog):
    __slots__ = (
        "bot",
        "queue",
        "playing",
        "alarm",
        "presenceCount",
        "spotify",
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guildStates: dict[int, GuildState] = {}
        self.presenceCount = 0
        self.spotify = Spotdl(
            client_id=os.getenv("spotify_clientid"),
            client_secret=os.getenv("spotify_clientsecret"),
        )
        self.isFirstReady: bool = True

    @commands.Cog.listener()
    async def on_ready(self):
        if self.isFirstReady:
            for guild in self.bot.guilds:
                self.guildStates[guild.id] = GuildState()
            self.presenceLoop.start()
            self.isFirstReady = False

    @tasks.loop(seconds=20)
    async def presenceLoop(self):
        if self.presenceCount == 0:
            await self.bot.change_presence(
                activity=discord.Activity(
                    name=f"{len(self.bot.voice_clients)} / {len(self.bot.guilds)} サーバー",
                    type=discord.ActivityType.competing,
                )
            )
            self.presenceCount = 1
        elif self.presenceCount == 1:
            await self.bot.change_presence(activity=discord.Game("/help"))
            self.presenceCount = 2
        elif self.presenceCount == 2:
            await self.bot.change_presence(
                activity=discord.Game("Powered by nennneko5787")
            )
            self.presenceCount = 0

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self.guildStates[guild.id] = GuildState()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await asyncio.sleep(2)
        del self.guildStates[guild.id]

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            if interaction.data["component_type"] == 2:
                await self.onButtonClick(interaction)
            elif interaction.data["component_type"] == 3:
                pass
        except KeyError:
            pass

    def seekMusic(source, seconds: float):
        options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": f"-vn -ss {formatTime(clamp(seconds, 0, int(source.info['duration'])))} -bufsize 64k -analyzeduration 2147483647 -probesize 2147483647",
        }

        if isinstance(source, NicoNicoSource):
            options[
                "before_options"
            ] += f" -headers 'cookie: {'; '.join(f'{k}={v}' for k, v in source.client.cookies.items())}'"

        return type(source)(
            discord.FFmpegPCMAudio(
                source.info.get("url", source.hslContentUrl), **options
            ),
            **{k: v for k, v in vars(source).items() if k != "info"},
        )

    async def queuePagenation(
        self, interaction: discord.Interaction, page: int = None, *, edit: bool = False
    ):
        await interaction.response.defer()
        queue: Queue = self.guildStates[interaction.guild.id].queue
        pageSize = 10
        index = queue.index
        if page is None:
            page = (index // pageSize) + 1
        songList = queue.pagenation(page, pageSize=pageSize)
        songs = ""
        startIndex = (page - 1) * pageSize

        for i, song in enumerate(songList):
            if startIndex + i == index - 1:
                songs += f"{song['url']} by {song['user'].mention} (現在再生中)\n"
            else:
                songs += f"{song['url']} by {song['user'].mention}\n"

        view = (
            discord.ui.View(timeout=None)
            .add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.blurple,
                    emoji="⏪",
                    custom_id=f"queuePagenation,{page-1}",
                    row=0,
                )
            )
            .add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.gray,
                    emoji="🔄",
                    label=f"ページ {page} / {(queue.asize() // pageSize) + 1}",
                    custom_id=f"queuePagenation,{page}",
                    row=0,
                )
            )
            .add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.blurple,
                    emoji="⏩",
                    custom_id=f"queuePagenation,{page+1}",
                    row=0,
                )
            )
        )
        embed = discord.Embed(title=f"キュー", description=songs)
        if edit:
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view)

    async def onButtonClick(self, interaction: discord.Interaction):
        customField = interaction.data["custom_id"].split(",")
        match (customField[0]):
            case "prev":
                if not interaction.guild.voice_client:
                    await interaction.response.send_message(
                        "現在曲を再生していません。", ephemeral=True
                    )
                    return
                await interaction.response.defer(ephemeral=True)
                self.guildStates[interaction.guild.id].queue.prev()
                interaction.guild.voice_client.stop()
            case "next":
                if not interaction.guild.voice_client:
                    await interaction.response.send_message(
                        "現在曲を再生していません。", ephemeral=True
                    )
                    return
                await interaction.response.defer(ephemeral=True)
                self.guildStates[interaction.guild.id].playing = False
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
                self.guildStates[interaction.guild.id].playing = False
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
                source: YTDLSource | NicoNicoSource = (
                    interaction.guild.voice_client.source
                )
                interaction.guild.voice_client.source = self.seekMusic(
                    source, source.progress - 10
                )
            case "forward":
                if not interaction.guild.voice_client:
                    embed = discord.Embed(
                        title="音楽を再生していません。", colour=discord.Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                source: YTDLSource | NicoNicoSource = (
                    interaction.guild.voice_client.source
                )
                interaction.guild.voice_client.source = self.seekMusic(
                    source, source.progress + 10
                )
            case "volumeUp":
                if not interaction.guild.voice_client:
                    embed = discord.Embed(
                        title="音楽を再生していません。", colour=discord.Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                if interaction.guild.voice_client.source.volume < 2.0:
                    interaction.guild.voice_client.source.volume = (
                        math.floor(
                            (interaction.guild.voice_client.source.volume + 0.1) * 100
                        )
                        / 100
                    )
            case "volumeDown":
                if not interaction.guild.voice_client:
                    embed = discord.Embed(
                        title="音楽を再生していません。", colour=discord.Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                if interaction.guild.voice_client.source.volume > 0.0:
                    interaction.guild.voice_client.source.volume = (
                        math.floor(
                            (interaction.guild.voice_client.source.volume - 0.1) * 100
                        )
                        / 100
                    )
            case "queuePagenation":
                if not interaction.guild.voice_client or (
                    self.guildStates[interaction.guild.id].queue.qsize() <= 0
                ):
                    await interaction.response.send_message(
                        "現在曲を再生していません。", ephemeral=True
                    )
                    return
                await self.queuePagenation(interaction, int(customField[1]), edit=True)

    def setToNotPlaying(self, guildId: int):
        self.guildStates[guildId].playing = False

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
            bar = "<:bar:1320712302475083816>"
            circle = "<:circle:1320712333676515328>"
            graybar = "<:graybar:1320712319512219648>"

            percentage = source.progress / source.info["duration"]
            barLength = 14
            filledLength = int(barLength * percentage)
            progressBar = (
                bar * filledLength + circle + graybar * (barLength - filledLength - 1)
            )

            percentage = source.volume / 2.0
            barLength = 14
            filledLength = int(barLength * percentage)
            volumeProgressBar = (
                bar * filledLength + circle + graybar * (barLength - filledLength - 1)
            )

            embed.colour = discord.Colour.purple()
            if voiceClient.is_paused():
                embed.set_author(name="一時停止中")
            else:
                embed.set_author(name="再生中")
            embed.add_field(
                name="再生時間",
                value=f'{progressBar}\n`{formatTime(source.progress)} / {formatTime(source.info["duration"])}`',
                inline=False,
            ).add_field(
                name="リクエストしたユーザー",
                value=f"{source.user.mention}",
                inline=False,
            ).add_field(
                name="ボリューム",
                value=f"{volumeProgressBar}\n`{source.volume} / 2.0`",
                inline=False,
            )
        else:
            embed.colour = discord.Colour.greyple()
            embed.set_author(name="再生準備中")
        return embed

    async def getSourceFromQueue(self, queue: Queue):
        info: dict = queue.get()
        if (info["url"] is None) and (info.get("attachment")):
            return await DiscordFileSource.from_attachment(
                info["attachment"], info["volume"], info["user"]
            )
        elif ("nicovideo.jp" in info["url"]) or ("nico.ms" in info["url"]):
            return await NicoNicoSource.from_url(
                info["url"], info["volume"], info["user"]
            )
        else:
            return await YTDLSource.from_url(info["url"], info["volume"], info["user"])

    async def playNext(self, guild: discord.Guild, channel: discord.abc.Messageable):
        queue: Queue = self.guildStates[guild.id].queue
        while True:
            if guild.voice_client:
                if queue.empty():
                    break

                try:
                    source: YTDLSource | NicoNicoSource | DiscordFileSource = (
                        await self.getSourceFromQueue(queue)
                    )
                except:
                    traceback.print_exc()
                    continue

                voiceClient: discord.VoiceClient = guild.voice_client
                message: discord.Message = await channel.send(
                    embed=self.embedPanel(voiceClient, source=source),
                    view=notPausedView,
                )

                if isinstance(source, NicoNicoSource):
                    await source.sendHeartBeat()

                voiceClient.play(source, after=lambda _: self.setToNotPlaying(guild.id))
                self.guildStates[guild.id].playing = True

                _break = False
                while self.guildStates[guild.id].playing:
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
                        if not self.guildStates[guild.id].playing:
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
        self.guildStates[guild.id].queue.clear()
        self.guildStates[guild.id].playing = False
        if guild.voice_client:
            await guild.voice_client.disconnect()

    async def putQueue(
        self,
        interaction: discord.Interaction,
        url: str,
        volume: float,
        *,
        shuffle: bool = False,
    ):
        queue: Queue = self.guildStates[interaction.guild.id].queue
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

            if shuffle:
                random.shuffle(urls)

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
                if shuffle:
                    random.shuffle(result)

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

    async def checks(self, interaction: discord.Interaction, *, url: str = None):
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel

        if not user.voice:
            await interaction.response.send_message(
                "ボイスチャンネルに接続してください。", ephemeral=True
            )
            return False
        permission = channel.permissions_for(guild.me)
        if (not permission.send_messages) or (not permission.embed_links):
            embed = discord.Embed(
                title="権限が足りません！",
                description=f"このチャンネルの`メッセージを送信`権限と`埋め込みリンク`権限を {self.bot.user.mention} に与えてください。",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        permission = user.voice.channel.permissions_for(guild.me)
        if not permission.connect:
            embed = discord.Embed(
                title="権限が足りません！",
                description=f"ボイスチャンネルの`接続`権限を {self.bot.user.mention} に与えてください。",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        if url:
            if "music.apple.com" in url:
                await interaction.response.send_message(
                    "Apple Musicには対応していません。", ephemeral=True
                )
                return False
        return True

    @app_commands.command(name="alarm", description="アラームをセットします。")
    @app_commands.guild_only()
    async def alarmCommand(
        self,
        interaction: discord.Interaction,
        delay: app_commands.Range[int, 0],
        url: str,
        volume: app_commands.Range[float, 0.0, 2.0] = 0.5,
        shuffle: bool = False,
    ):
        if not await self.checks(interaction, url=url):
            return
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect(self_deaf=True)
        await self.putQueue(interaction, url, volume, shuffle=shuffle)

        self.guildStates[guild.id].alarm = True

        embed = discord.Embed(
            title="アラームをセットしました！",
            description=f"{discord.utils.format_dt(discord.utils.utcnow()+timedelta(seconds=delay), 'R')} に音楽を再生します。\n-# VCに参加している端末の電池残量・電力消費に注意してください。\n-# また、アラームを設定している最中にボットが再起動されると、アラームはリセットされます。ご注意ください。",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed)

        await asyncio.sleep(delay)
        self.guildStates[guild.id].alarm = False
        await self.playNext(guild, channel)

    @app_commands.command(name="play", description="曲を再生します。")
    @app_commands.guild_only()
    async def playMusic(
        self,
        interaction: discord.Interaction,
        url: str,
        volume: app_commands.Range[float, 0.0, 2.0] = 0.5,
        shuffle: bool = False,
    ):
        if not await self.checks(interaction, url=url):
            return
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect(self_deaf=True)
        await self.putQueue(interaction, url, volume, shuffle=shuffle)
        if (not self.guildStates[guild.id].playing) and (
            not self.guildStates[guild.id].alarm
        ):
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
        if not await self.checks(interaction):
            return
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect(self_deaf=True)
        queue: Queue = self.guildStates[guild.id].queue
        queue.put(
            {
                "url": None,
                "attachment": attachment,
                "volume": volume,
                "user": user,
            }
        )
        await interaction.followup.send(
            f"**{attachment.filename}**をキューに追加しました。"
        )
        if (not self.guildStates[guild.id].playing) and (
            not self.guildStates[guild.id].alarm
        ):
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
        if not await self.checks(interaction):
            return
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect(self_deaf=True)
        queue: Queue = self.guildStates[guild.id].queue
        queue.put(
            {
                "url": None,
                "attachment": attachment,
                "volume": volume,
                "user": user,
            }
        )

        self.guildStates[guild.id].alarm = True

        embed = discord.Embed(
            title="アラームをセットしました！",
            description=f"{discord.utils.format_dt(discord.utils.utcnow()+timedelta(seconds=delay), 'R')} に音楽を再生します。\n-# VCに参加している端末の電池残量・電力消費に注意してください。\n-# また、アラームを設定している最中にボットが再起動されると、アラームはリセットされます。ご注意ください。",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed)

        await asyncio.sleep(delay)
        self.guildStates[guild.id].alarm = False
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
            if not await self.checks(interaction):
                return
            user = interaction.user
            guild = interaction.guild
            channel = interaction.channel
            await interaction.response.defer()
            if not guild.voice_client:
                await user.voice.channel.connect(self_deaf=True)
            self.guildStates[guild.id].queue.put(
                {
                    "url": url,
                    "volume": float(volume),
                    "user": user,
                }
            )
            if (not self.guildStates[guild.id].playing) and (
                not self.guildStates[guild.id].alarm
            ):
                await self.playNext(guild, channel)

        select.callback = selectCallBack

        view.add_item(select)
        embed = discord.Embed(
            title=f"{len(videos)}本の動画がヒットしました。",
            description="動画を選択して、キューに追加します。",
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @searchCommandGroup.command(
        name="niconico", description="ニコニコ動画から動画を検索して再生します。"
    )
    async def searchNiconicoCommand(
        self,
        interaction: discord.Interaction,
        keyword: str,
        volume: app_commands.Range[float, 0.0, 2.0] = 0.5,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        view = discord.ui.View(timeout=None)
        select = discord.ui.Select(custom_id="nicosearch")
        videos = await searchNicoNico(keyword)
        for video in videos:
            select.add_option(
                label=video["title"],
                description=video["uploader"],
                value=f"{video['url']}|{volume}",
            )

        async def selectCallBack(interaction: discord.Interaction):
            url, volume = interaction.data["values"][0].split("|")
            if not await self.checks(interaction):
                return
            user = interaction.user
            guild = interaction.guild
            channel = interaction.channel
            await interaction.response.defer()
            if not guild.voice_client:
                await user.voice.channel.connect(self_deaf=True)
            self.guildStates[guild.id].queue.put(
                {
                    "url": url,
                    "volume": float(volume),
                    "user": user,
                }
            )
            if (not self.guildStates[guild.id].playing) and (
                not self.guildStates[guild.id].alarm
            ):
                await self.playNext(guild, channel)

        select.callback = selectCallBack

        view.add_item(select)
        embed = discord.Embed(
            title=f"{len(videos)}本の動画がヒットしました。",
            description="動画を選択して、キューに追加します。",
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="queue", description="キューに入っている曲の一覧を取得します。"
    )
    @app_commands.guild_only()
    async def queueCommand(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client or (
            not self.guildStates[guild.id].queue.qsize() <= 0
        ):
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        await self.queuePagenation(interaction, None, edit=True)

    # Non-support commands

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
        self.guildStates[guild.id].playing = False
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
        self.guildStates[guild.id].playing = False
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
        guild.voice_client.pause()
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
