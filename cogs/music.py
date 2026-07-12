import logging
import re
from typing import Literal, cast

import discord
import dotenv
import lavalink
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
from objects.panel import WaitingView
from objects.player import MusicPlayer
from objects.utils import resolveMemberMention
from services import (
    adService,
    buttonHandler,
    lavalinkHooks,
    panelUpdater,
    playerCheck,
    queuePagination,
)
from services.env import getEnv
from services.messageEditQueue import MessageEditQueue

dotenv.load_dotenv()


class MusicCog(commands.Cog):
    # NOTE: commands.Cog は __slots__ を持たないため、下記 __slots__ は事実上無効。
    # 属性は __dict__ に載る(SPEC 分析で検証済み)。ここでは lint 対象を減らす目的で列挙のみ残す。
    __slots__ = (
        "bar",
        "bot",
        "circle",
        "editQueue",
        "graybar",
        "initialized",
        "log",
        "presenceCount",
        "urlRegexp",
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
        self.lavalink: lavalink.Client | None = None
        self.editQueue: MessageEditQueue = MessageEditQueue()

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
            await self.bot.change_presence(activity=discord.Game("Powered by nennneko5787"))
            self.presenceCount = 0

    @commands.Cog.listener()
    async def on_ready(self):
        # SPEC #13: 元コードは再接続のたびに emoji fetch が走った(initialized ガード外だった)。
        # 一度だけ実行するように initialized ガード内へ移動。lavalink Client の構築もここ。
        if self.initialized:
            return

        self.bar = str(discord.utils.get(await self.bot.fetch_application_emojis(), name="bar"))
        self.circle = str(discord.utils.get(await self.bot.fetch_application_emojis(), name="circle"))
        self.graybar = str(discord.utils.get(await self.bot.fetch_application_emojis(), name="graybar"))

        self.presenceLoop.start()

        assert self.bot.user is not None  # on_ready 発火時点で保証される
        self.bot.lavalink = lavalink.Client(self.bot.user.id, player=MusicPlayer)
        self.bot.lavalink.add_node(
            host=getEnv("lavalink_host"),
            port=int(getEnv("lavalink_port")),
            password=getEnv("lavalink_password"),
            region="jp-1",
            name="jp-1",
        )

        self.lavalink = self.bot.lavalink
        self.lavalink.add_event_hooks(self)

        self.initialized = True

    async def cog_load(self):
        self.editQueue.start()

    async def cog_unload(self):
        """
        Cog reload 時のクリーンアップ。
        - SPEC #21: 元コードは presenceLoop.cancel() を忘れており、reload 後の再接続で二重稼働した。
        - 元コードは lavalink 未初期化のまま unload されると AttributeError を投げた
          (self.lavalink が None のときのガード欠如)。
        """
        # SPEC #21: presenceLoop を止めないと reload 後に二重ループになる。
        if self.presenceLoop.is_running():
            self.presenceLoop.cancel()

        if self.lavalink is not None:
            self.lavalink._event_hooks.clear()

        # SPEC #21: editQueue.stop() は冪等なので二度呼びも安全。
        self.editQueue.stop()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component:
            return
        data = cast(dict, interaction.data)
        if data.get("component_type") == 2:
            await self.onButtonClick(interaction)

    async def onButtonClick(self, interaction: discord.Interaction):
        await buttonHandler.handleButtonClick(self, interaction)

    @lavalink.listener(TrackEndEvent)
    async def onTrackEnd(self, event: TrackEndEvent):
        await lavalinkHooks.handleTrackEnd(self, event)

    @lavalink.listener(QueueEndEvent)
    async def onQueueEnd(self, event: QueueEndEvent):
        await lavalinkHooks.handleQueueEnd(self, event)

    @lavalink.listener(PlayerUpdateEvent)
    async def onPlayerUpdate(self, event: PlayerUpdateEvent):
        await lavalinkHooks.handlePlayerUpdate(self, event)

    @app_commands.command(name="play", description="曲を再生します。")
    @app_commands.rename(query="クエリ")
    @app_commands.describe(query="URLまたは検索ワード。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(playerCheck.createPlayer)
    async def playCommand(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        # create_player check により interaction.guild と self.lavalink は非 None が保証される
        assert interaction.guild is not None
        assert self.lavalink is not None
        player = cast(MusicPlayer, self.lavalink.player_manager.get(interaction.guild.id))
        query = query.strip("<>")
        if not self.urlRegexp.match(query):
            query = f"ytsearch:{query}"
        results = await player.node.get_tracks(query)

        embed = discord.Embed(color=discord.Color.blurple())

        if results.load_type == LoadType.EMPTY:
            return await interaction.followup.send("クエリに対応する検索結果が見つかりませんでした。")
        elif results.load_type == LoadType.PLAYLIST:
            tracks = results.tracks
            for track in tracks:
                track.extra["requester"] = interaction.user.id
                player.add(track=track)

            embed.title = "プレイリストがキューに挿入されました。"
            embed.description = f"{results.playlist_info.name} - {len(tracks)} トラック"
        else:
            track = results.tracks[0]
            embed.title = "トラックがキューに挿入されました。"
            embed.description = f"[{track.title}]({track.uri})"

            track.extra["requester"] = interaction.user.id

            player.add(track=track)

        await interaction.followup.send(embed=embed)

        # SPEC_FEATURE_ADS §5.2: キュー挿入 embed の直後、WaitingView 投稿より前に広告フックを呼ぶ。
        # 5〜10 回に 1 回だけ広告 embed が followup で追加送信される(閾値未到達時は no-op)。
        await adService.maybeShowAd(interaction, interaction.guild.id)

        # SPEC #24: is_playing は TrackStart 到着まで False のため、アイドルに2人が同時に /play すると
        # 二重パネルが投稿される。channelId store の有無でアトミックに判定する。
        if player.fetch("channelId") is None:
            channel = interaction.channel
            if not isinstance(channel, discord.abc.Messageable):
                return
            message = await channel.send(
                view=WaitingView(),
                allowed_mentions=panelUpdater.ALLOWED_MENTIONS,
            )
            player.store("channelId", message.channel.id)
            player.store("messageId", message.id)
            await player.play()

    @app_commands.command(name="timescale", description="曲の再生速度とピッチを変更します。")
    @app_commands.rename(pitch="ピッチ")
    @app_commands.describe(pitch="曲のピッチを指定してください。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(playerCheck.requirePlaying)
    @app_commands.check(playerCheck.requireSameVC)
    async def pitchCommand(
        self,
        interaction: discord.Interaction,
        speed: app_commands.Range[float, 0.1, 2.0],
        pitch: app_commands.Range[float, 0.1, 2.0],
    ):
        await interaction.response.defer()
        _voiceClient, player = playerCheck.resolveActivePlayer(interaction)

        tsFilter = Timescale(speed=speed, pitch=pitch, rate=1)
        await player.set_filter(tsFilter)

        await interaction.followup.send(f"曲の再生速度を **`{speed}`** に、ピッチを **``{pitch}``** に変更しました。")

    @app_commands.command(name="volume", description="曲の音量を変更します。")
    @app_commands.rename(volume="音量")
    @app_commands.describe(volume="曲の音量を指定してください。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(playerCheck.requirePlaying)
    @app_commands.check(playerCheck.requireSameVC)
    async def volumeCommand(
        self,
        interaction: discord.Interaction,
        volume: app_commands.Range[int, 0.0, 100.0],
    ):
        await interaction.response.defer()
        _voiceClient, player = playerCheck.resolveActivePlayer(interaction)

        await player.set_volume(volume)
        await interaction.followup.send(f"曲の音量を **``{volume}``** に変更しました。")

    @app_commands.command(name="queue", description="キューに入っている曲の一覧を取得します。")
    @app_commands.guild_install()
    async def queueCommand(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None or not guild.voice_client:
            await interaction.response.send_message("現在曲を再生していません。", ephemeral=True)
            return
        await queuePagination.queuePagenation(self, interaction, 1, edit=False)

    @app_commands.command(name="loop", description="ループ・ループ解除状態を切り替えます。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(playerCheck.requirePlaying)
    @app_commands.check(playerCheck.requireSameVC)
    async def loopToggleCommand(
        self,
        interaction: discord.Interaction,
        loop: Literal["ループしない", "1曲ループ", "キュー内ループ"],
    ):
        await interaction.response.defer()
        _voiceClient, player = playerCheck.resolveActivePlayer(interaction)

        loopTypes = {
            "ループしない": player.LOOP_NONE,
            "1曲ループ": player.LOOP_SINGLE,
            "キュー内ループ": player.LOOP_QUEUE,
        }

        player.set_loop(loopTypes[loop])
        await interaction.followup.send(f"ループを `{loop}` に設定しました。")

    @app_commands.command(name="toggle", description="一時停止・再開状態を切り替えます。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(playerCheck.requirePlaying)
    @app_commands.check(playerCheck.requireSameVC)
    async def toggleCommand(self, interaction: discord.Interaction):
        await interaction.response.defer()
        _voiceClient, player = playerCheck.resolveActivePlayer(interaction)

        await player.set_pause(not player.paused)
        if player.paused:
            await interaction.followup.send("一時停止しました。")
        else:
            await interaction.followup.send("再生を再開しました。")

    @app_commands.command(name="stop", description="曲の再生を停止し、ボイスチャンネルから切断します。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(playerCheck.requireSameVC)
    async def stopCommand(self, interaction: discord.Interaction):
        # SPEC_REFACTOR_PR5.md: requireSameVC で guild と voice_client の存在は保証される。
        # ただし player は None でも disconnect したい仕様(voice client の掃除)なので
        # requirePlaying は付けず、player の None チェックは inline に残す。
        await interaction.response.defer()
        assert interaction.guild is not None
        voiceClient = cast(LavalinkVoiceClient, interaction.guild.voice_client)

        player = cast(MusicPlayer | None, voiceClient.player)
        if player is not None:
            track = player.current
            if track is not None:
                requestAuthorMention = await resolveMemberMention(interaction.guild, track.extra["requester"])
                await panelUpdater.finalizePanel(self, player, track, requestAuthorMention)

        await voiceClient.disconnect(force=True)
        await interaction.followup.send("切断しました。")


async def setup(bot: MusicBot):
    await bot.add_cog(MusicCog(bot))
