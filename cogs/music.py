import asyncio
import logging
import os
import random
import re
import time
from typing import List, Literal

import discord
import dotenv
import lavalink as Lavalink
from discord import app_commands
from discord.ext import commands, tasks
from lavalink.events import QueueEndEvent, TrackStartEvent
from lavalink.filters import Timescale
from lavalink.server import LoadType

from objects.client import LavalinkVoiceClient
from objects.exceptions import CommandInvokeError, NoPrivateMessage

dotenv.load_dotenv()


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
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger("music")
        self.bar = ""
        self.circle = ""
        self.graybar = ""
        self.presenceCount = 0
        self.initialized = False
        self.urlRegexp: re.Pattern = re.compile(r"https?://(?:www\.)?.+")
        self.lavalink = None

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

            if not hasattr(self.bot, "lavalink"):
                self.bot.lavalink = Lavalink.Client(self.bot.user.id)
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

    async def cog_unload(self):
        """
        This will remove any registered event hooks when the cog is unloaded.
        They will subsequently be registered again once the cog is loaded.

        This effectively allows for event handlers to be updated when the cog is reloaded.
        """
        self.lavalink._event_hooks.clear()

    def formatTime(self, seconds: int):
        if seconds < 3600:
            return time.strftime("%M:%S", time.gmtime(seconds))
        elif seconds < 86400:
            return time.strftime("%H:%M:%S", time.gmtime(seconds))
        else:
            return time.strftime("%d:%H:%M:%S", time.gmtime(seconds))

    def createView(self, player: Lavalink.DefaultPlayer):
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏪",
                custom_id="reverse",
                row=0,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="▶" if player.paused else "⏸",
                custom_id="resume" if player.paused else "pause",
                row=0,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏩",
                custom_id="forward",
                row=0,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="+",
                custom_id="volumeUp",
                row=0,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=(
                    discord.ButtonStyle.gray
                    if player.loop == player.LOOP_NONE
                    else discord.ButtonStyle.green
                    if player.loop == player.LOOP_SINGLE
                    else discord.ButtonStyle.blurple
                ),
                emoji="🔄",
                custom_id="loop",
                row=0,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏮",
                custom_id="prev",
                row=1,
                disabled=True,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple, emoji="⏹", custom_id="stop", row=1
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏭",
                custom_id="next",
                row=1,
                disabled=(len(player.queue) <= 0),
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="-",
                custom_id="volumeDown",
                row=1,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="🔀",
                custom_id="shuffle",
                row=1,
            )
        )
        return view

    def clamp(self, value: float | int, min_value: float | int, max_value: float | int):
        """
        指定した範囲内に数値を制限する関数。

        :param value: 制限したい数値
        :param min_value: 最小値
        :param max_value: 最大値
        :return: 制限された数値
        """
        return max(min_value, min(value, max_value))

    def embedPanel(
        self,
        player: Lavalink.DefaultPlayer,
        track: Lavalink.AudioTrack,
        requestAuthor: discord.Member,
        *,
        finished: bool = False,
    ):
        embed = discord.Embed(
            title=track.title,
            url=track.uri,
        ).set_image(url=track.artwork_url)

        if finished:
            embed.colour = discord.Colour.greyple()
            embed.set_author(name="再生終了")
        elif player.is_playing or player.paused:
            percentage = player.position / track.duration
            barLength = 14
            filledLength = int(barLength * percentage)
            progressBar = (
                self.bar * filledLength
                + self.circle
                + self.graybar * (barLength - filledLength - 1)
            )

            percentage = player.volume / 100
            barLength = 14
            filledLength = int(barLength * percentage)
            volumeProgressBar = (
                self.bar * filledLength
                + self.circle
                + self.graybar * (barLength - filledLength - 1)
            )

            embed.colour = discord.Colour.purple()
            if player.paused:
                embed.set_author(name="一時停止中")
            else:
                embed.set_author(name="再生中")
            embed.add_field(
                name="再生時間",
                value=f"{progressBar}\n`{self.formatTime(player.position / 1000)} / {self.formatTime(track.duration / 1000)}`",
                inline=False,
            ).add_field(
                name="リクエストしたユーザー",
                value=requestAuthor,
                inline=False,
            ).add_field(
                name="ボリューム",
                value=f"{volumeProgressBar}\n`{player.volume} / 100`",
                inline=False,
            )
        else:
            embed.colour = discord.Colour.greyple()
            embed.set_author(name="再生準備中")

        # if track.album.name:
        #    embed.add_field(name="アルバム", value=track.album.name)
        return embed

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
        player = voiceClient.player
        await interaction.response.defer(ephemeral=True)
        match customField[0]:
            case "prev":
                player.queue.insert(0, player.current)
                await player.play(player.current)
            case "next":
                await player.skip()
            case "stop":
                await voiceClient.disconnect()
            case "resume":
                await player.set_pause(False)
            case "pause":
                await player.set_pause(True)
            case "reverse":
                await player.seek(
                    self.clamp(
                        player.position / 1000 - 10, 0, player.track.length / 1000
                    )
                )
            case "forward":
                await player.seek(
                    self.clamp(
                        player.position / 1000 + 10, 0, player.track.length / 1000
                    )
                )
            case "volumeUp":
                await player.set_volume(self.clamp(player.volume + 5, 0, 100))
            case "volumeDown":
                await player.set_volume(self.clamp(player.volume - 5, 0, 100))
            case "loop":
                loop = player.loop + 1
                if loop > 2:
                    loop = 0
                player.loop = loop
            case "shuffle":
                random.shuffle(player.queue)
            case "queuePagenation":
                await self.queuePagenation(interaction, int(customField[1]), edit=True)

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

        for _, song in enumerate(songList):
            songs += f"[{song.title}]({song.uri}) by {(await interaction.guild.fetch_member(song.extra['requester'])).mention} (現在再生中)\n"

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
            await interaction.edit_original_response(embed=embed, view=view)
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

    @Lavalink.listener(TrackStartEvent)
    async def onTrackStart(self, event: TrackStartEvent):
        player: Lavalink.DefaultPlayer = event.player
        if not player:
            return

        guild = self.bot.get_guild(player.guild_id)
        # voiceChannel = self.bot.get_channel(player.fetch("channel"))
        track: Lavalink.AudioTrack = event.track
        channel = self.bot.get_channel(track.extra["channelId"])

        if not guild:
            return await self.lavalink.player_manager.destroy(player.guild_id)

        requestAuthor = await guild.fetch_member(track.extra["requester"])

        message = await channel.send(
            embed=self.embedPanel(player, track, requestAuthor, finished=False),
            view=self.createView(player),
        )

        await asyncio.sleep(3)

        count = 0
        while True:
            if player.position / 1000 >= track.duration / 1000 or not player.is_playing:
                if player.loop:
                    await player.queue.insert(0, track)
                    await player.seek(0)
                    await asyncio.sleep(3)
                else:
                    await message.edit(
                        embed=self.embedPanel(
                            player, track, requestAuthor, finished=True
                        ),
                        view=None,
                    )
                    break
            if count >= 5:
                await message.edit(
                    embed=self.embedPanel(player, track, requestAuthor, finished=False),
                    view=self.createView(player),
                )
                count = 0
            count += 0.01
            await asyncio.sleep(0.01)

    @Lavalink.listener(QueueEndEvent)
    async def onQueueEnd(self, event: QueueEndEvent):
        guildId = event.player.guild_id
        guild = self.bot.get_guild(guildId)

        if guild is not None:
            await guild.voice_client.disconnect(force=True)

    @app_commands.command(name="play", description="曲を再生します。")
    @app_commands.rename(query="クエリ")
    @app_commands.describe(query="URLまたは検索ワード。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(createPlayer)
    async def playCommand(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        player: Lavalink.DefaultPlayer = self.lavalink.player_manager.get(
            interaction.guild.id
        )
        query = query.strip("<>")
        if not self.urlRegexp.match(query):
            query = f"ytsearch:{query}"
        results = await player.node.get_tracks(query)

        embed = discord.Embed(color=discord.Color.blurple())

        if results.load_type == LoadType.EMPTY:
            return await interaction.followup.send(
                "クエリに対応する検索結果が見つかりませんでした。"
            )
        elif results.load_type == LoadType.PLAYLIST:
            tracks = results.tracks
            for track in tracks:
                track.extra["requester"] = interaction.user.id
                track.extra["channelId"] = interaction.channel.id
                player.add(track=track)

            embed.title = "プレイリストがキューに挿入されました。"
            embed.description = f"{results.playlist_info.name} - {len(tracks)} トラック"
        else:
            track = results.tracks[0]
            embed.title = "トラックがキューに挿入されました。"
            embed.description = f"[{track.title}]({track.uri})"

            track.extra["requester"] = interaction.user.id
            track.extra["channelId"] = interaction.channel.id

            player.add(track=track)

        await interaction.followup.send(embed=embed)

        if not player.is_playing:
            await player.play()

    @app_commands.command(name="pitch", description="曲のピッチを変更します。")
    @app_commands.rename(pitch="ピッチ")
    @app_commands.describe(pitch="曲のピッチを指定してください。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def pitchCommand(
        self,
        interaction: discord.Interaction,
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

        filter = Timescale(speed=pitch, pitch=pitch, rate=1)
        await player.set_filter(filter)

        await interaction.followup.send(
            f"曲のピッチを **``{pitch}``** に変更しました。"
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
        await self.queuePagenation(interaction, 1, edit=True)

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

        await voiceClient.disconnect(force=True)
        await interaction.followup.send("切断しました。")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
