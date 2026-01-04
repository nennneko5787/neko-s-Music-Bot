import asyncio
import logging
import os
import re
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal

import aiofiles
import discord
import dotenv
import lavalink as Lavalink
from discord import app_commands
from discord.ext import commands, tasks
from lavalink.events import (
    PlayerUpdateEvent,
    QueueEndEvent,
    TrackEndEvent,
)
from lavalink.filters import Timescale
from lavalink.server import LoadType

from objects.bot import MusicBot
from objects.client import LavalinkVoiceClient
from objects.exceptions import CommandInvokeError, NoPrivateMessage
from objects.guilds import MusicData
from objects.panel import MusicPanel, WaitingView
from objects.player import MusicPlayer
from objects.utils import clamp
from services.guilds import getGuild, updateGuild
from services.members import getMember, updateMember

dotenv.load_dotenv()

tokyo = timezone(timedelta(hours=9), "Asia/Tokyo")


class MusicCog(commands.Cog):
    __slots__ = (
        "bot",
        "log",
        "bar",
        "circle",
        "graybar",
        "presenceCount",
        "initialized",
        "urlRegexp",
        "lavalink",
        "editQueue",
        "editQueueTask",
    )

    def __init__(self, bot: MusicBot):
        self.bot = bot
        self.log = logging.getLogger("music")
        self.bar = ""
        self.circle = ""
        self.graybar = ""
        self.presenceCount = 0
        self.initialized = False
        self.urlRegexp: re.Pattern = re.compile(r"https?://(?:www\.)?.+")
        self.lavalink = None
        self.editQueue = asyncio.Queue()
        self.editQueueTask = None

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
    async def on_ready(self):
        self.bar = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="bar")
        )
        self.circle = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="circle")
        )
        self.graybar = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="graybar")
        )
        if not self.initialized:
            self.presenceLoop.start()

            self.bot.lavalink = Lavalink.Client(self.bot.user.id, player=MusicPlayer)
            self.bot.lavalink.add_node(
                host=os.getenv("lavalink_host"),
                port=int(os.getenv("lavalink_port")),
                password=os.getenv("lavalink_password"),
                region="jp-1",
                name="jp-1",
            )

            self.lavalink: Lavalink.Client = self.bot.lavalink
            self.lavalink.add_event_hooks(self)

            self.initialized = True

    async def cog_load(self):
        self.editQueueTask = asyncio.create_task(self.messageEditQueue())

    async def cog_unload(self):
        """
        This will remove any registered event hooks when the cog is unloaded.
        They will subsequently be registered again once the cog is loaded.

        This effectively allows for event handlers to be updated when the cog is reloaded.
        """
        self.lavalink._event_hooks.clear()

        # task cancel
        self.editQueueTask.cancel()

    async def messageEditQueue(self):
        while True:
            try:
                instance, kwargs = await self.editQueue.get()

                if isinstance(instance, discord.Interaction):
                    await instance.edit_original_response(**kwargs)
                elif isinstance(instance, discord.Message):
                    await instance.edit(**kwargs)
            except asyncio.CancelledError:
                break
            except Exception:
                traceback.print_exc()
            await asyncio.sleep(1)

    def getTimescale(self, player: MusicPlayer):
        return player.get_filter(Timescale)

    async def changeSpeed(self, player: MusicPlayer, up: bool):
        timescale = self.getTimescale(player)

        if not timescale:
            speed = 1.0
            pitch = 1.0
        else:
            speed = timescale.values["speed"]
            pitch = timescale.values["pitch"]

        speed += 0.1 if up else -0.1

        await player.set_filter(
            Timescale(clamp(speed, 0.1, 2.0), clamp(pitch, 0.1, 2.0), 1)
        )

    async def changePitch(self, player: MusicPlayer, up: bool):
        timescale = self.getTimescale(player)

        if not timescale:
            speed = 1.0
            pitch = 1.0
        else:
            speed = timescale.values["speed"]
            pitch = timescale.values["pitch"]

        pitch += 0.1 if up else -0.1

        await player.set_filter(
            Timescale(clamp(speed, 0.1, 2.0), clamp(pitch, 0.1, 2.0), 1)
        )

    async def putPrevQueue(self, player: MusicPlayer, track: Lavalink.AudioTrack):
        track.position = 0
        await player.prevQueue.put(track)

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
        customField = interaction.data["custom_id"].split(",")
        voiceClient: LavalinkVoiceClient = interaction.guild.voice_client
        if not voiceClient:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        player: MusicPlayer = voiceClient.player
        await interaction.response.defer(ephemeral=True)

        track: Lavalink.AudioTrack = interaction.guild.voice_client.player.current
        requestAuthor = await interaction.guild.fetch_member(track.extra["requester"])
        queue = player.prevQueue

        finished = False
        match customField[0]:
            case "prev":
                _track = player.current
                _track.position = 0
                player.queue.insert(0, _track)

                _track = await queue.get()
                player.queue.insert(0, _track)
                await player.play()
                return
            case "next":
                _track = player.current
                _track.position = 0

                await self.putPrevQueue(player, _track)
                await player.skip()
                return
            case "stop":
                channelId = player.fetch("channelId")
                messageId = player.fetch("messageId")

                channel = self.bot.get_channel(channelId)
                message = await channel.fetch_message(messageId)

                await self.editQueue.put(
                    (
                        message,
                        {
                            "view": MusicPanel(
                                player,
                                track,
                                requestAuthor,
                                self.bar,
                                self.circle,
                                self.graybar,
                                finished=True,
                            ),
                            "allowed_mentions": discord.AllowedMentions(
                                everyone=False,
                                users=False,
                                roles=False,
                                replied_user=False,
                            ),
                        },
                    )
                )

                await voiceClient.disconnect()
                finished = True
                return
            case "resume":
                await player.set_pause(False)
            case "pause":
                await player.set_pause(True)
            case "reverse":
                await player.seek(
                    int(clamp(player.position - 10_000, 0, player.current.duration))
                )
            case "forward":
                await player.seek(
                    int(clamp(player.position + 10_000, 0, player.current.duration))
                )
            case "volumeUp":
                await player.set_volume(clamp(player.volume + 5, 0, 100))
            case "volumeDown":
                await player.set_volume(clamp(player.volume - 5, 0, 100))
            case "speedUp":
                await self.changeSpeed(player, True)
            case "speedDown":
                await self.changeSpeed(player, False)
            case "pitchUp":
                await self.changePitch(player, True)
            case "pitchDown":
                await self.changePitch(player, False)
            case "loop":
                loop = player.loop + 1
                if loop > 2:
                    loop = 0
                player.loop = loop
            case "shuffle":
                player.set_shuffle(not player.shuffle)
            case "queuePagenation":
                await self.queuePagenation(interaction, int(customField[1]), edit=True)

        if not finished:
            track: Lavalink.AudioTrack = interaction.guild.voice_client.player.current
            requestAuthor = await interaction.guild.fetch_member(
                track.extra["requester"]
            )
        await self.editQueue.put(
            (
                interaction,
                {
                    "view": MusicPanel(
                        player,
                        track,
                        requestAuthor,
                        self.bar,
                        self.circle,
                        self.graybar,
                        finished=finished,
                    ),
                    "allowed_mentions": discord.AllowedMentions(
                        everyone=False, users=False, roles=False, replied_user=False
                    ),
                },
            )
        )

    def pagenation(
        self, queue: List[Lavalink.AudioTrack], page: int, *, pageSize: int = 10
    ):
        startIndex = (page - 1) * pageSize
        endIndex = startIndex + pageSize
        if startIndex >= len(queue) or page < 1:
            return ()
        return tuple(queue[startIndex:endIndex])

    async def queuePagenation(
        self, interaction: discord.Interaction, page: int = 1, *, edit: bool = False
    ):
        await interaction.response.defer()
        voiceClient: LavalinkVoiceClient = interaction.guild.voice_client
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        player = voiceClient.player

        queue = player.queue.copy()
        queue.insert(0, player.current)

        pageSize = 10
        songList: tuple[Lavalink.AudioTrack] = self.pagenation(
            queue, page, pageSize=pageSize
        )
        songs = ""

        for i, song in enumerate(songList):
            songs += f"[{song.title}]({song.uri}) by {(await interaction.guild.fetch_member(song.extra['requester'])).mention} `{'(現在再生中)' if i == 0 else ''}`\n"

        view = (
            discord.ui.View(timeout=None)
            .add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.blurple,
                    emoji="⏪",
                    custom_id=f"queuePagenation,{page - 1}",
                    row=0,
                    disabled=(page <= 1),
                )
            )
            .add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.gray,
                    emoji="🔄",
                    label=f"ページ {page} / {(len(queue) // pageSize) + 1}",
                    custom_id=f"queuePagenation,{page}",
                    row=0,
                )
            )
            .add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.blurple,
                    emoji="⏩",
                    custom_id=f"queuePagenation,{page + 1}",
                    row=0,
                    disabled=((len(queue) // pageSize) + 1 == page),
                )
            )
        )
        embed = discord.Embed(title="キュー", description=songs)
        if edit:
            await self.editQueue.put(
                (
                    interaction,
                    {
                        "embed": embed,
                        "view": view,
                        "allowed_mentions": discord.AllowedMentions(
                            everyone=False, users=False, roles=False, replied_user=False
                        ),
                    },
                )
            )
        else:
            await interaction.followup.send(embed=embed, view=view)

    async def createPlayer(interaction: discord.Interaction):
        if interaction.guild is None:
            raise NoPrivateMessage()

        player: Lavalink.DefaultPlayer = (
            interaction.client.lavalink.player_manager.create(interaction.guild.id)
        )
        shouldConnect = interaction.command.name in ("play",)

        voiceClient = interaction.guild.voice_client

        if not interaction.user.voice or not interaction.user.voice.channel:
            if voiceClient is not None:
                raise CommandInvokeError(
                    "このコマンドを実行するには、ボットが接続しているチャンネルに接続する必要があります。"
                )

            raise CommandInvokeError(
                "このコマンドを実行するには、ボイスチャンネルに接続する必要があります。"
            )

        voiceChannel = interaction.user.voice.channel

        if voiceClient is None:
            if not shouldConnect:
                raise CommandInvokeError("現在音楽を再生していません。")

            permissions = voiceChannel.permissions_for(interaction.guild.me)

            if not permissions.connect or not permissions.speak:
                raise CommandInvokeError(
                    "このボットに `接続` 及び `発言` の権限が必要です。"
                )

            if voiceChannel.user_limit > 0:
                if (
                    len(voiceChannel.members) >= voiceChannel.user_limit
                    and not interaction.guild.me.guild_permissions.move_members
                ):
                    raise CommandInvokeError(
                        "ボイスチャンネルが満員のため、ボイスチャンネルに接続できません。"
                    )

            player.store("channel", interaction.channel.id)
            await interaction.user.voice.channel.connect(cls=LavalinkVoiceClient)
        elif voiceClient.channel.id != voiceChannel.id:
            raise CommandInvokeError(
                "このコマンドを実行するには、ボットが接続しているチャンネルに接続する必要があります。"
            )

        return True

    @Lavalink.listener(TrackEndEvent)
    async def onTrackEnd(self, event: TrackEndEvent):
        player: MusicPlayer = event.player
        track: Lavalink.AudioTrack = event.track

        if player.loop == player.LOOP_SINGLE:
            return

        if event.reason != Lavalink.EndReason.FINISHED:
            return

        track.position = 0
        await self.putPrevQueue(player, track)

        if len(player.queue) <= 0:
            channelId = player.fetch("channelId")
            messageId = player.fetch("messageId")

            channel = self.bot.get_channel(channelId)
            message = await channel.fetch_message(messageId)

            requestAuthor = await channel.guild.fetch_member(track.extra["requester"])

            await self.editQueue.put(
                (
                    message,
                    {
                        "view": MusicPanel(
                            player,
                            track,
                            requestAuthor,
                            self.bar,
                            self.circle,
                            self.graybar,
                            finished=True,
                        ),
                        "allowed_mentions": discord.AllowedMentions(
                            everyone=False,
                            users=False,
                            roles=False,
                            replied_user=False,
                        ),
                    },
                )
            )

    @Lavalink.listener(QueueEndEvent)
    async def onQueueEnd(self, event: QueueEndEvent):
        player: MusicPlayer = event.player
        track: Lavalink.AudioTrack = event.player.current

        if track:
            channelId = player.fetch("channelId")
            messageId = player.fetch("messageId")

            channel = self.bot.get_channel(channelId)
            message = await channel.fetch_message(messageId)

            requestAuthor = await channel.guild.fetch_member(track.extra["requester"])

            await self.editQueue.put(
                (
                    message,
                    {
                        "view": MusicPanel(
                            player,
                            track,
                            requestAuthor,
                            self.bar,
                            self.circle,
                            self.graybar,
                            finished=True,
                        ),
                        "allowed_mentions": discord.AllowedMentions(
                            everyone=False,
                            users=False,
                            roles=False,
                            replied_user=False,
                        ),
                    },
                )
            )

        guildId = event.player.guild_id
        guild = self.bot.get_guild(guildId)

        if guild is not None:
            guild.voice_client.track = None
            await guild.voice_client.disconnect(force=True)

    @Lavalink.listener(PlayerUpdateEvent)
    async def onPlayerUpdate(self, event: PlayerUpdateEvent):
        player: MusicPlayer = event.player
        track: Lavalink.AudioTrack = event.player.current

        player.ping = event.ping

        if track and time.time() - player.lastUpdated >= 5.0:
            player.update()

            channelId = player.fetch("channelId")
            messageId = player.fetch("messageId")

            channel = self.bot.get_channel(channelId)
            message = await channel.fetch_message(messageId)

            requestAuthor = await channel.guild.fetch_member(track.extra["requester"])

            await self.editQueue.put(
                (
                    message,
                    {
                        "view": MusicPanel(
                            player,
                            track,
                            requestAuthor,
                            self.bar,
                            self.circle,
                            self.graybar,
                            finished=False,
                        ),
                        "allowed_mentions": discord.AllowedMentions(
                            everyone=False,
                            users=False,
                            roles=False,
                            replied_user=False,
                        ),
                    },
                )
            )

    @app_commands.command(name="play", description="曲を再生します。")
    @app_commands.rename(query="クエリ")
    @app_commands.describe(query="URLまたは検索ワード。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(createPlayer)
    async def playCommand(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        player: MusicPlayer = self.lavalink.player_manager.get(interaction.guild.id)
        query = query.strip("<>")
        if not self.urlRegexp.match(query):
            query = f"ytsearch:{query}"
        results = await player.node.get_tracks(query)

        guildData = await getGuild(interaction.guild.id)

        embed = discord.Embed(color=discord.Color.blurple())

        if results.load_type == LoadType.EMPTY:
            return await interaction.followup.send(
                "クエリに対応する検索結果が見つかりませんでした。"
            )
        elif results.load_type == LoadType.PLAYLIST:
            tracks = results.tracks
            for track in tracks:
                track.extra["requester"] = interaction.user.id
                player.add(track=track)

                guildData.playedMusics.append(
                    MusicData(url=track.uri, title=track.title)
                )

            embed.title = "プレイリストがキューに挿入されました。"
            embed.description = f"{results.playlist_info.name} - {len(tracks)} トラック"
        else:
            track = results.tracks[0]
            embed.title = "トラックがキューに挿入されました。"
            embed.description = f"[{track.title}]({track.uri})"

            track.extra["requester"] = interaction.user.id

            guildData.playedMusics.append(MusicData(url=track.uri, title=track.title))

            player.add(track=track)

        await updateGuild(guildData)

        await interaction.followup.send(embed=embed)

        if not player.is_playing:
            message = await interaction.channel.send(
                view=WaitingView(),
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, users=False, roles=False, replied_user=False
                ),
            )
            player.store("channelId", message.channel.id)
            player.store("messageId", message.id)
            await player.play()

    @app_commands.command(
        name="timescale", description="曲の再生速度とピッチを変更します。"
    )
    @app_commands.rename(pitch="ピッチ")
    @app_commands.describe(pitch="曲のピッチを指定してください。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def pitchCommand(
        self,
        interaction: discord.Interaction,
        speed: app_commands.Range[float, 0.1, 2.0],
        pitch: app_commands.Range[float, 0.1, 2.0],
    ):
        await interaction.response.defer()
        voiceClient: LavalinkVoiceClient = interaction.guild.voice_client
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        player = voiceClient.player

        filter = Timescale(speed=speed, pitch=pitch, rate=1)
        await player.set_filter(filter)

        await interaction.followup.send(
            f"曲の再生速度を **`{speed}`** に、ピッチを **``{pitch}``** に変更しました。"
        )

    @app_commands.command(name="volume", description="曲の音量を変更します。")
    @app_commands.rename(volume="音量")
    @app_commands.describe(volume="曲の音量を指定してください。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def volumeCommand(
        self,
        interaction: discord.Interaction,
        volume: app_commands.Range[int, 0.0, 100.0],
    ):
        await interaction.response.defer()
        voiceClient: LavalinkVoiceClient = interaction.guild.voice_client
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        player = voiceClient.player

        await player.set_volume(volume)
        await interaction.followup.send(f"曲の音量を **``{volume}``** に変更しました。")

    @app_commands.command(
        name="queue", description="キューに入っている曲の一覧を取得します。"
    )
    @app_commands.guild_install()
    async def queueCommand(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        await self.queuePagenation(interaction, 1, edit=False)

    @app_commands.command(
        name="loop", description="ループ・ループ解除状態を切り替えます。"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def loopToggleCommand(
        self,
        interaction: discord.Interaction,
        loop: Literal["ループしない", "1曲ループ", "キュー内ループ"],
    ):
        await interaction.response.defer()
        voiceClient: LavalinkVoiceClient = interaction.guild.voice_client
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        player = voiceClient.player

        loopTypes = {
            "ループしない": player.LOOP_NONE,
            "1曲ループ": player.LOOP_SINGLE,
            "キュー内ループ": player.LOOP_QUEUE,
        }

        player.set_loop(loopTypes[loop])
        await interaction.followup.send(f"ループを `{loop}` に設定しました。")

    @app_commands.command(
        name="toggle", description="一時停止・再開状態を切り替えます。"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def toggleCommand(self, interaction: discord.Interaction):
        await interaction.response.defer()
        voiceClient: LavalinkVoiceClient = interaction.guild.voice_client
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        player = voiceClient.player

        await player.set_pause(not player.paused)
        if player.paused:
            await interaction.followup.send("一時停止しました。")
        else:
            await interaction.followup.send("再生を再開しました。")

    @app_commands.command(
        name="stop", description="曲の再生を停止し、ボイスチャンネルから切断します。"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def stopCommand(self, interaction: discord.Interaction):
        await interaction.response.defer()
        voiceClient: LavalinkVoiceClient = interaction.guild.voice_client
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return

        player: MusicPlayer = voiceClient.player
        track: Lavalink.AudioTrack = player.current

        channelId = player.fetch("channelId")
        messageId = player.fetch("messageId")

        channel = self.bot.get_channel(channelId)
        message = await channel.fetch_message(messageId)

        requestAuthor = await channel.guild.fetch_member(track.extra["requester"])

        await self.editQueue.put(
            (
                message,
                {
                    "view": MusicPanel(
                        player,
                        track,
                        requestAuthor,
                        self.bar,
                        self.circle,
                        self.graybar,
                        finished=True,
                    ),
                    "allowed_mentions": discord.AllowedMentions(
                        everyone=False,
                        users=False,
                        roles=False,
                        replied_user=False,
                    ),
                },
            )
        )

        await voiceClient.disconnect(force=True)
        await interaction.followup.send("切断しました。")

    @app_commands.command(name="code", description="支援者コードを使用します。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def codeCommand(self, interaction: discord.Interaction, code: str):
        await interaction.response.defer(ephemeral=True)

        member = await getMember(interaction.user.id)

        async with aiofiles.open("key.txt", "r", encoding="utf-8") as f:
            key = (await f.read()).strip()

        if key.strip() != code:
            return await interaction.followup.send(
                embed=discord.Embed(
                    title="コードが違います",
                    description="支援はここから行えます\nhttps://nennneko5787.fanbox.cc/",
                    color=discord.Color.red(),
                ),
                ephemeral=True,
            )

        now = datetime.now(tokyo)
        member.expiresAt = now.replace(
            month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        await updateMember(member)

        await interaction.followup.send(
            embed=discord.Embed(
                title="サーバー内再生ランキング",
                description="ご支援ありがとうございます！来月までのサポーター限定機能の開放を行います！",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="ranking", description="サーバー内再生ランキングを取得します。"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def rankingCommand(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        member = await getMember(interaction.user.id)
        if not member.expiresAt or member.expiresAt < datetime.now(tokyo):
            return await interaction.followup.send(
                "サーバー内再生ランキングはサポーター限定機能です。\nfanboxでサポーターになりましょう。\nhttps://nennneko5787.fanbox.cc/",
                ephemeral=True,
            )

        guildData = await getGuild(interaction.guild.id)

        counter = Counter(m.url for m in guildData.playedMusics)
        musicMap: Dict[str, MusicData] = {}
        for m in guildData.playedMusics:
            musicMap.setdefault(m.url, m)

        result = [(musicMap[url], count) for url, count in counter.most_common()][0:5]

        await interaction.followup.send(
            embed=discord.Embed(
                title="サーバー内再生ランキング",
                description="\n".join(
                    [
                        f"{i}. {m.title} ({v}回)\n{m.url}"
                        for i, (m, v) in enumerate(result, 1)
                    ]
                ),
                color=discord.Color.purple(),
            ),
            ephemeral=True,
        )


async def setup(bot: MusicBot):
    await bot.add_cog(MusicCog(bot))
