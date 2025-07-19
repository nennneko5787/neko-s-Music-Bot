import asyncio
import concurrent.futures
import math
import os
import random
import traceback
from datetime import timedelta
import concurrent

import discord
import dotenv
from discord import app_commands
from discord.ext import commands, tasks
from spotdl import Spotdl
from spotdl.types.album import Album
from spotdl.types.playlist import Playlist
from spotdl.types.song import Song

from objects.item import Item
from objects.queue import Queue
from objects.state import GuildState
from source.filesource import DiscordFileSource
from source.niconico import NicoNicoSource
from source.source import YTDLSource, isPlayList
from utils.func import clamp, formatTime
from utils.search import searchNicoNico, searchYoutube

dotenv.load_dotenv()


def createView(isPaused: bool, isLooping: bool, isShuffle: bool):
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
            style=(
                discord.ButtonStyle.blurple
                if not isLooping
                else discord.ButtonStyle.danger
            ),
            emoji="🔄",
            custom_id="loop",
            row=0,
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
    view.add_item(
        discord.ui.Button(
            style=(
                discord.ButtonStyle.blurple
                if not isShuffle
                else discord.ButtonStyle.danger
            ),
            emoji="🔀",
            custom_id="shuffle",
            row=1,
        )
    )
    return view


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
        self.bar = ""
        self.circle = ""
        self.graybar = ""

    @commands.Cog.listener()
    async def on_ready(self):
        if self.isFirstReady:
            for guild in self.bot.guilds:
                self.guildStates[guild.id] = GuildState()
            self.presenceLoop.start()
            self.isFirstReady = False
        self.bar = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="bar")
        )
        self.circle = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="circle")
        )
        self.graybar = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="graybar")
        )

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

    def releaseSource(self, source: discord.AudioSource) -> bool:
        if source:
            source.cleanup()
            return True
        return False

    def seekMusic(
        self, source: YTDLSource | NicoNicoSource | DiscordFileSource, seconds: float
    ) -> YTDLSource | NicoNicoSource | DiscordFileSource:
        options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": f"-vn -ss {formatTime(clamp(seconds, 0, int(source.info.duration)))} -bufsize 64k -analyzeduration 2147483647 -probesize 2147483647 -ac 2",
        }

        if isinstance(source, NicoNicoSource):
            options["before_options"] = (
                f"-headers 'cookie: {'; '.join(f'{k}={v}' for k, v in source.client.cookies.items())}' {options['before_options']}"
            )
            return NicoNicoSource(
                discord.FFmpegPCMAudio(source.hslContentUrl, **options),
                info=source.info,
                hslContentUrl=source.hslContentUrl,
                watchid=source.watchid,
                trackid=source.trackid,
                outputs=source.outputs,
                nicosid=source.nicosid,
                niconico=source.niconico,
                volume=source.volume,
                progress=seconds / 0.02,
                user=source.user,
            )
        elif isinstance(source, DiscordFileSource):
            return DiscordFileSource(
                discord.FFmpegPCMAudio(source.info.url, **options),
                info=source.info,
                volume=source.volume,
                progress=seconds / 0.02,
                user=source.user,
            )
        else:
            return YTDLSource(
                discord.FFmpegPCMAudio(source.info.url, **options),
                info=source.info,
                volume=source.volume,
                progress=seconds / 0.02,
                user=source.user,
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
        songList: tuple[Item] = queue.pagenation(page, pageSize=pageSize)
        songs = ""
        startIndex = (page - 1) * pageSize

        for i, song in enumerate(songList):
            if startIndex + i == index - 1:
                songs += f"{song.name} by {song.user.mention} (現在再生中)\n"
            else:
                songs += f"{song.name} by {song.user.mention}\n"

        view = (
            discord.ui.View(timeout=None)
            .add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.blurple,
                    emoji="⏪",
                    custom_id=f"queuePagenation,{page-1}",
                    row=0,
                    disabled=(page <= 1),
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
                    disabled=((queue.asize() // pageSize) + 1 == page),
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
                    embed=embed,
                    view=createView(
                        isPaused=False,
                        isLooping=self.guildStates[interaction.guild.id].loop,
                        isShuffle=self.guildStates[interaction.guild.id].shuffle,
                    ),
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
                await interaction.edit_original_response(
                    embed=embed,
                    view=createView(
                        isPaused=True,
                        isLooping=self.guildStates[interaction.guild.id].loop,
                        isShuffle=self.guildStates[interaction.guild.id].shuffle,
                    ),
                )
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
                self.releaseSource(interaction.guild.voice_client.source)
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
                self.releaseSource(interaction.guild.voice_client.source)
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
                    embed = interaction.message.embeds[0]
                    await interaction.edit_original_response(
                        embed=embed,
                        view=createView(
                            isPaused=True,
                            isLooping=self.guildStates[interaction.guild.id].loop,
                            isShuffle=self.guildStates[interaction.guild.id].shuffle,
                        ),
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
                    embed = interaction.message.embeds[0]
                    await interaction.edit_original_response(
                        embed=embed,
                        view=createView(
                            isPaused=True,
                            isLooping=self.guildStates[interaction.guild.id].loop,
                            isShuffle=self.guildStates[interaction.guild.id].shuffle,
                        ),
                    )
            case "loop":
                await interaction.response.defer(ephemeral=True)
                self.guildStates[interaction.guild.id].loop = not self.guildStates[
                    interaction.guild.id
                ].loop
                embed = interaction.message.embeds[0]
                await interaction.edit_original_response(
                    embed=embed,
                    view=createView(
                        isPaused=False,
                        isLooping=self.guildStates[interaction.guild.id].loop,
                        isShuffle=self.guildStates[interaction.guild.id].shuffle,
                    ),
                )
            case "shuffle":
                await interaction.response.defer(ephemeral=True)
                self.guildStates[interaction.guild.id].shuffle = not self.guildStates[
                    interaction.guild.id
                ].shuffle
                embed = interaction.message.embeds[0]
                await interaction.edit_original_response(
                    embed=embed,
                    view=createView(
                        isPaused=False,
                        isLooping=self.guildStates[interaction.guild.id].loop,
                        isShuffle=self.guildStates[interaction.guild.id].shuffle,
                    ),
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
            title=source.info.title,
            url=source.info.webpage_url,
        ).set_image(url=source.info.thumbnail)

        if finished:
            embed.colour = discord.Colour.greyple()
            embed.set_author(name="再生終了")
        elif voiceClient.is_playing() or voiceClient.is_paused():
            # bar = "<:bar:1320712302475083816>"
            # circle = "<:circle:1320712333676515328>"
            # graybar = "<:graybar:1320712319512219648>"

            percentage = source.progress / source.info.duration
            barLength = 14
            filledLength = int(barLength * percentage)
            progressBar = (
                self.bar * filledLength
                + self.circle
                + self.graybar * (barLength - filledLength - 1)
            )

            percentage = source.volume / 2.0
            barLength = 14
            filledLength = int(barLength * percentage)
            volumeProgressBar = (
                self.bar * filledLength
                + self.circle
                + self.graybar * (barLength - filledLength - 1)
            )

            embed.colour = discord.Colour.purple()
            if voiceClient.is_paused():
                embed.set_author(name="一時停止中")
            else:
                embed.set_author(name="再生中")
            embed.add_field(
                name="再生時間",
                value=f"{progressBar}\n`{formatTime(source.progress)} / {formatTime(source.info.duration)}`",
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
        info: Item = queue.get()
        if info.attachment is not None:
            return await DiscordFileSource.from_attachment(
                info.attachment, info.volume, info.user
            )
        elif ("nicovideo.jp" in info.url) or ("nico.ms" in info.url):
            return await NicoNicoSource.from_url(info.url, info.volume, info.user)
        else:
            return await YTDLSource.from_url(
                info.url, info.locale, info.volume, info.user
            )

    async def newSource(self, source: YTDLSource) -> YTDLSource:
        options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": f"-vn -ss {formatTime(0)} -bufsize 64k -analyzeduration 2147483647 -probesize 2147483647 -ac 2",
        }

        if isinstance(source, DiscordFileSource):
            return DiscordFileSource(
                discord.FFmpegPCMAudio(source.info.url, **options),
                info=source.info,
                volume=source.volume,
                progress=0,
                user=source.user,
            )
        elif isinstance(source, NicoNicoSource):
            return await NicoNicoSource.from_url(
                source.info.webpage_url, source.volume, source.user
            )
        else:
            return await YTDLSource.from_url(
                source.info.webpage_url, source.locale, source.volume, source.user
            )

    async def playNext(self, guild: discord.Guild, channel: discord.abc.Messageable):
        queue: Queue = self.guildStates[guild.id].queue
        while True:
            if guild.voice_client:
                if queue.empty():
                    break

                if self.guildStates[guild.id].shuffle and not queue.shuffled:
                    queue.shuffle()
                elif queue.shuffled:
                    queue.unshuffle()

                try:
                    source: YTDLSource | NicoNicoSource | DiscordFileSource = (
                        await self.getSourceFromQueue(queue)
                    )
                except:
                    traceback.print_exc()
                    continue

                voiceClient: discord.VoiceClient = guild.voice_client

                if (voiceClient.channel.type == discord.ChannelType.voice) and (
                    voiceClient.channel.permissions_for(guild.me).value & (1 << 48) != 0
                ):
                    await voiceClient.channel.edit(status=source.info.title)

                message: discord.Message = await channel.send(
                    embed=self.embedPanel(voiceClient, source=source),
                    view=createView(
                        isPaused=False,
                        isLooping=self.guildStates[guild.id].loop,
                        isShuffle=self.guildStates[guild.id].shuffle,
                    ),
                )

                if isinstance(source, NicoNicoSource):
                    await source.sendHeartBeat()

                voiceClient.play(source, after=lambda _: self.setToNotPlaying(guild.id))
                self.guildStates[guild.id].playing = True

                _break = False
                while True:
                    while self.guildStates[guild.id].playing:
                        if isinstance(source, NicoNicoSource):
                            await source.sendHeartBeat()
                        if voiceClient.source is not None:
                            source = voiceClient.source
                        if not voiceClient.is_paused():
                            await message.edit(
                                embed=self.embedPanel(voiceClient, source=source),
                                view=createView(
                                    isPaused=voiceClient.is_paused(),
                                    isLooping=self.guildStates[guild.id].loop,
                                    isShuffle=self.guildStates[guild.id].shuffle,
                                ),
                            )
                        for _ in range(5):
                            if (not self.guildStates[guild.id].playing) or (
                                not voiceClient.is_connected()
                            ):
                                _break = True
                                break
                            await asyncio.sleep(1)
                        if _break:
                            break
                    self.releaseSource(source)
                    if not self.guildStates[guild.id].loop:
                        break
                    elif not voiceClient.is_connected():
                        break
                    else:
                        _break = False
                        voiceClient.play(
                            await self.newSource(source),
                            after=lambda _: self.setToNotPlaying(guild.id),
                        )
                        self.guildStates[guild.id].playing = True
                        continue
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

    def getDownloadUrls(self, songs: tuple[Song]) -> tuple[
        list[tuple[str, str]],
        list[str],
    ]:
        """
        Get the download urls for a list of songs.

        ### Arguments
        - songs: List of Song objects

        ### Returns
        - A list of urls if successful.

        ### Notes
        - This function is multi-threaded.
        """

        urls: list[tuple[str, str]] = []
        failedSongs: list[int] = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.spotify.downloader.settings["threads"]
        ) as executor:
            future_to_song = {
                executor.submit(self.spotify.downloader.search, song): song
                for song in songs
            }
            for i, future in enumerate(concurrent.futures.as_completed(future_to_song)):
                song = future_to_song[future]
                try:
                    data = future.result()
                    urls.append(
                        (
                            data,
                            song.song_id,
                        )
                    )
                except Exception as exc:
                    failedSongs.append(song.song_id)

        return urls, failedSongs

    async def putQueue(
        self,
        interaction: discord.Interaction,
        url: str,
        volume: float,
    ):
        queue: Queue = self.guildStates[interaction.guild.id].queue
        if "spotify" in url:
            titles: dict[str] = {}

            if "track" in url:
                song: Song = await asyncio.to_thread(Song.from_url, url)
                titles[song.song_id] = song.display_name
                songs = (song,)
            elif "album" in url:
                album = await asyncio.to_thread(Album.from_url, url)
                for song in album.songs:
                    titles[song.song_id] = song.display_name
                songs = tuple(song for song in album.songs)
            elif "playlist" in url:
                playlist = await asyncio.to_thread(Playlist.from_url, url)
                for song in playlist.songs:
                    titles[song.song_id] = song.display_name
                songs = tuple(song for song in playlist.songs)
            else:
                await interaction.followup.send("無効なSpotify URL")
                return

            urls, failedSongs = await asyncio.to_thread(self.getDownloadUrls, songs)

            for songId in failedSongs:
                del titles[songId]

            for url, songId in urls:
                queue.put(
                    Item(
                        url=url,
                        volume=volume,
                        user=interaction.user,
                        title=titles[songId],
                    )
                )
            await interaction.followup.send(
                f"**{len(urls)}個の曲**をキューに追加しました。"
            )
        else:
            results = await isPlayList(url, interaction.locale)
            if not isinstance(results, list):
                queue.put(
                    Item(
                        url=url,
                        volume=volume,
                        user=interaction.user,
                        title=results["title"],
                        locale=interaction.locale,
                    )
                )
                await interaction.followup.send(f"**{url}** をキューに追加しました。")
            else:
                for result in results:
                    queue.put(
                        Item(
                            url=result["url"],
                            volume=volume,
                            user=interaction.user,
                            title=result["title"],
                            locale=interaction.locale,
                        )
                    )
                await interaction.followup.send(
                    f"**{len(results)}個の動画**をキューに追加しました。"
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
    ):
        if not await self.checks(interaction, url=url):
            return
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect(self_deaf=True)
        await self.putQueue(interaction, url, volume)

        self.guildStates[guild.id].alarm = True

        embed = discord.Embed(
            title="アラームをセットしました！",
            description=f"{discord.utils.format_dt(discord.utils.utcnow()+timedelta(seconds=delay), 'R')} に音楽を再生します。\n-# VCに参加している端末の電池残量・電力消費に注意してください。\n-# また、アラームを設定している最中にボットが再起動されると、アラームはリセットされます。ご注意ください。",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed)

        for _ in range(delay):
            if self.guildStates[guild.id].alarm != True:
                return
            await asyncio.sleep(1)
        self.guildStates[guild.id].alarm = False
        await self.playNext(guild, channel)

    @app_commands.command(name="play", description="曲を再生します。")
    @app_commands.guild_only()
    async def playMusic(
        self,
        interaction: discord.Interaction,
        url: str,
        volume: app_commands.Range[float, 0.0, 2.0] = 0.5,
    ):
        if not await self.checks(interaction, url=url):
            return
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect(self_deaf=True)
        await self.putQueue(interaction, url, volume)
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
        queue.put(Item(attachment=attachment, volume=volume, user=interaction.user))
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
        queue.put(Item(attachment=attachment, volume=volume, user=interaction.user))

        self.guildStates[guild.id].alarm = True

        embed = discord.Embed(
            title="アラームをセットしました！",
            description=f"{discord.utils.format_dt(discord.utils.utcnow()+timedelta(seconds=delay), 'R')} に音楽を再生します。\n-# VCに参加している端末の電池残量・電力消費に注意してください。\n-# また、アラームを設定している最中にボットが再起動されると、アラームはリセットされます。ご注意ください。",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed)

        for _ in range(delay):
            if self.guildStates[guild.id].alarm != True:
                return
            await asyncio.sleep(1)
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
        videos = await searchYoutube(keyword, language=interaction.locale)
        for video in videos:
            select.add_option(
                label=video["title"],
                description=video["uploader"],
                value=f"{video['url']}|{volume}|{video['title']}",
            )

        async def selectCallBack(interaction: discord.Interaction):
            url, volume, title = interaction.data["values"][0].split("|")
            if not await self.checks(interaction):
                return
            user = interaction.user
            guild = interaction.guild
            channel = interaction.channel
            await interaction.response.defer()
            if not guild.voice_client:
                await user.voice.channel.connect(self_deaf=True)
            self.guildStates[guild.id].queue.put(
                Item(url=url, volume=float(volume), user=interaction.user, title=title)
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
                value=f"{video['url']}|{volume}|{video['title']}",
            )

        async def selectCallBack(interaction: discord.Interaction):
            url, volume, title = interaction.data["values"][0].split("|")
            if not await self.checks(interaction):
                return
            user = interaction.user
            guild = interaction.guild
            channel = interaction.channel
            await interaction.response.defer()
            if not guild.voice_client:
                await user.voice.channel.connect(self_deaf=True)
            self.guildStates[guild.id].queue.put(
                Item(url=url, volume=float(volume), user=interaction.user, title=title)
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
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        await self.queuePagenation(interaction, None, edit=True)

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
        self.guildStates[guild.id].alarm = False
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
