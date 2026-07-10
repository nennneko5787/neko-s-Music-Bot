import asyncio
import logging
import random
import re
import time
import traceback
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
from objects.exceptions import MusicCommandError, NoGuildError
from objects.panel import MusicPanel, WaitingView
from objects.player import MusicPlayer
from objects.utils import clamp, resolveMemberMention
from services.env import getEnv

dotenv.load_dotenv()


def isInBotVoiceChannel(
    interaction: discord.Interaction,
    voiceClient: LavalinkVoiceClient,
) -> bool:
    """
    SPEC #14: 呼び出し者がボットと同じ VC にいる場合のみ True。
    パネルボタンと playback 変更コマンドで使う荒らし対策。
    """
    user = interaction.user
    if not isinstance(user, discord.Member):
        return False
    userVoice = user.voice
    if userVoice is None or userVoice.channel is None:
        return False
    botChannel = cast(discord.VoiceChannel | None, voiceClient.channel)
    if botChannel is None:
        return False
    return userVoice.channel.id == botChannel.id


class MusicCog(commands.Cog):
    # NOTE: commands.Cog は __slots__ を持たないため、下記 __slots__ は事実上無効。
    # 属性は __dict__ に載る(SPEC 分析で検証済み)。ここでは lint 対象を減らす目的で列挙のみ残す。
    __slots__ = (
        "bar",
        "bot",
        "circle",
        "editQueue",
        "editQueueTask",
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
        self.editQueue: asyncio.Queue = asyncio.Queue()
        self.editQueueTask: asyncio.Task | None = None

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
        # SPEC #13: 元コードは再接続のたびに emoji fetch が走った(initialized ガード外だった)。
        # 一度だけ実行するように initialized ガード内へ移動。lavalink Client の構築もここ。
        if self.initialized:
            return

        self.bar = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="bar")
        )
        self.circle = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="circle")
        )
        self.graybar = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="graybar")
        )

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
        self.editQueueTask = asyncio.create_task(self.messageEditQueue())

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

        # task cancel
        if self.editQueueTask is not None:
            self.editQueueTask.cancel()

    def _editTargetKey(self, instance) -> tuple:
        # 同一パネル(Message)や同一 Interaction の連続更新はまとめる。
        if isinstance(instance, discord.Interaction):
            return ("i", instance.id)
        if isinstance(instance, discord.Message):
            return ("m", instance.id)
        return ("x", id(instance))

    async def messageEditQueue(self):
        # SPEC #12: 元コードは 1秒/編集の逐次処理でキュー無制限、
        # PlayerUpdate 多発時にパネル更新が際限なく遅延した。
        # 同じ Message/Interaction 宛の連続更新を最後のものだけに coalesce する。
        while True:
            try:
                instance, kwargs = await self.editQueue.get()
            except asyncio.CancelledError:
                break

            pending: dict[tuple, tuple] = {self._editTargetKey(instance): (instance, kwargs)}
            # 追加分を drain して同じキーは上書き
            while True:
                try:
                    nextInstance, nextKwargs = self.editQueue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                pending[self._editTargetKey(nextInstance)] = (nextInstance, nextKwargs)

            for inst, kw in pending.values():
                try:
                    if isinstance(inst, discord.Interaction):
                        await inst.edit_original_response(**kw)
                    elif isinstance(inst, discord.Message):
                        await inst.edit(**kw)
                except asyncio.CancelledError:
                    return
                except Exception:
                    traceback.print_exc()

            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break

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

    async def putPrevQueue(self, player: MusicPlayer, track: lavalink.AudioTrack):
        track.position = 0
        await player.prevQueue.put(track)

    async def _getPanelMessage(self, player: MusicPlayer) -> discord.Message | None:
        """
        SPEC #22: 元コードは onPlayerUpdate(約5秒/ギルド)ごと・ボタン1クリックごとに
        fetch_message() を呼んでいた。Message は id/channel が固定なのでプレイヤー寿命内で
        キャッシュしても安全(edit は id 経由なので stale でも動く)。
        """
        cached = cast(discord.Message | None, player.fetch("_panelMessage"))
        if cached is not None:
            return cached
        channelId = player.fetch("channelId")
        messageId = player.fetch("messageId")
        if channelId is None or messageId is None:
            return None
        channel = self.bot.get_channel(channelId)
        if not isinstance(channel, discord.abc.Messageable):
            return None
        try:
            message = await channel.fetch_message(messageId)
        except (discord.NotFound, discord.Forbidden):
            return None
        player.store("_panelMessage", message)
        return message

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component:
            return
        data = cast(dict, interaction.data)
        if data.get("component_type") == 2:
            await self.onButtonClick(interaction)

    async def onButtonClick(self, interaction: discord.Interaction):
        data = cast(dict, interaction.data)
        customField: list[str] = data["custom_id"].split(",")

        if interaction.guild is None:
            return
        voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
        if not voiceClient:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        player = cast(MusicPlayer | None, voiceClient.player)
        if player is None:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        # SPEC #14: VC 参加チェック — /queue の pagination だけは view-only なので許可。
        if customField[0] != "queuePagenation" and not isInBotVoiceChannel(
            interaction, voiceClient
        ):
            await interaction.response.send_message(
                "ボットと同じボイスチャンネルに参加してください。", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)

        current = player.current
        if current is None:
            # 曲終了直後にボタンが押されるレース窓(SPEC Phase 5 §5)
            return
        track: lavalink.AudioTrack = current
        requestAuthorMention = await resolveMemberMention(
            interaction.guild, track.extra["requester"]
        )
        queue = player.prevQueue

        finished = False
        match customField[0]:
            case "prev":
                # SPEC #16: player.play() 引数無しは loop/shuffle 由来のバグ(1曲ループで戻れない・
                # shuffle でランダム曲になる・キュー内ループで重複)を引き起こす。track= 明示で回避。
                _track = player.current
                if _track is None:
                    return
                try:
                    _prev = queue.get_nowait()
                except asyncio.QueueEmpty:
                    # SPEC #5: stale パネル経由で空 prevQueue に到達したときの hang 回避。
                    await interaction.followup.send(
                        "前の曲がありません。", ephemeral=True
                    )
                    return
                _track.position = 0
                # 現在曲を queue 先頭に戻す(prev 再生後に自然に元の曲が続く)
                player.queue.insert(0, _track)
                await player.play(track=_prev)
                return
            case "next":
                # SPEC #16: 1曲ループ中は skip() が同じ曲を再生し、キュー内ループでは queue の末尾に
                # current が append されて無限成長する。手動 next は loop バイパス、shuffle は尊重。
                _track = player.current
                if _track is None:
                    return
                _track.position = 0
                await self.putPrevQueue(player, _track)

                if len(player.queue) == 0:
                    await interaction.followup.send(
                        "次の曲がありません。", ephemeral=True
                    )
                    return
                popAt = random.randrange(len(player.queue)) if player.shuffle else 0
                _next = player.queue.pop(popAt)
                await player.play(track=_next)
                return
            case "stop":
                channelId = player.fetch("channelId")
                messageId = player.fetch("messageId")
                if channelId is None or messageId is None:
                    await voiceClient.disconnect()
                    return

                channel = self.bot.get_channel(channelId)
                if not isinstance(channel, discord.abc.Messageable):
                    await voiceClient.disconnect()
                    return
                message = await channel.fetch_message(messageId)

                await self.editQueue.put(
                    (
                        message,
                        {
                            "view": MusicPanel(
                                player,
                                track,
                                requestAuthorMention,
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
                    int(clamp(player.position - 10_000, 0, track.duration))
                )
            case "forward":
                await player.seek(
                    int(clamp(player.position + 10_000, 0, track.duration))
                )
            case "volumeUp":
                await player.set_volume(int(clamp(player.volume + 5, 0, 100)))
            case "volumeDown":
                await player.set_volume(int(clamp(player.volume - 5, 0, 100)))
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
                # SPEC #3: return が無いと後段のパネル書き換えで queue 表示が上書きされる。
                await self.queuePagenation(interaction, int(customField[1]), edit=True)
                return

        if not finished:
            refreshed = player.current
            if refreshed is None:
                return
            track = refreshed
            requestAuthorMention = await resolveMemberMention(
                interaction.guild, track.extra["requester"]
            )
        await self.editQueue.put(
            (
                interaction,
                {
                    "view": MusicPanel(
                        player,
                        track,
                        requestAuthorMention,
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
        self, queue: list[lavalink.AudioTrack], page: int, *, pageSize: int = 10
    ):
        startIndex = (page - 1) * pageSize
        endIndex = startIndex + pageSize
        if startIndex >= len(queue) or page < 1:
            return ()
        return tuple(queue[startIndex:endIndex])

    async def queuePagenation(
        self, interaction: discord.Interaction, page: int = 1, *, edit: bool = False
    ):
        # queue コマンド経由の場合は既に defer 済み(SPEC バックログ #3 のダブル defer 回避)。
        if not interaction.response.is_done():
            await interaction.response.defer()
        if interaction.guild is None:
            return
        voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        player = cast(MusicPlayer | None, voiceClient.player)
        if player is None:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return

        queue = player.queue.copy()
        if player.current is not None:
            queue.insert(0, player.current)

        pageSize = 10
        songList: tuple[lavalink.AudioTrack, ...] = self.pagenation(
            queue, page, pageSize=pageSize
        )
        songs = ""

        for i, song in enumerate(songList):
            mention = await resolveMemberMention(interaction.guild, song.extra["requester"])
            songs += (
                f"[{song.title}]({song.uri}) "
                f"by {mention} "
                f"`{'(現在再生中)' if i == 0 else ''}`\n"
            )

        # SPEC #19: 元の (len // pageSize) + 1 は 10 の倍数で空ページを生む。
        # ceil(len / pageSize) を使い、少なくとも 1 ページは表示する。
        totalPages = max(1, (len(queue) + pageSize - 1) // pageSize)
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
                    label=f"ページ {page} / {totalPages}",
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
                    disabled=(page >= totalPages),
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

    @staticmethod
    async def createPlayer(interaction: discord.Interaction):
        # SPEC #25: 元コードは検証前に player_manager.create() を呼ぶため、失敗した /play でも
        # lavalink プレイヤーがプロセス寿命まで残る。検証を全部通してから create する。
        if interaction.guild is None:
            raise NoGuildError()

        shouldConnect = (
            interaction.command is not None and interaction.command.name in ("play",)
        )

        voiceClient = interaction.guild.voice_client

        # DM 系の User インスタンスには .voice が無い(SPEC §5.1)。Member に絞る。
        if not isinstance(interaction.user, discord.Member):
            raise MusicCommandError(
                "このコマンドを実行するには、ボイスチャンネルに接続する必要があります。"
            )
        if not interaction.user.voice or not isinstance(
            interaction.user.voice.channel, discord.VoiceChannel
        ):
            if voiceClient is not None:
                raise MusicCommandError(
                    "このコマンドを実行するには、ボットが接続しているチャンネルに接続する必要があります。"
                )

            raise MusicCommandError(
                "このコマンドを実行するには、ボイスチャンネルに接続する必要があります。"
            )

        voiceChannel = interaction.user.voice.channel

        if voiceClient is None:
            if not shouldConnect:
                raise MusicCommandError("現在音楽を再生していません。")

            permissions = voiceChannel.permissions_for(interaction.guild.me)

            if not permissions.connect or not permissions.speak:
                raise MusicCommandError(
                    "このボットに `接続` 及び `発言` の権限が必要です。"
                )

            if (
                voiceChannel.user_limit > 0
                and len(voiceChannel.members) >= voiceChannel.user_limit
                and not interaction.guild.me.guild_permissions.move_members
            ):
                raise MusicCommandError(
                    "ボイスチャンネルが満員のため、ボイスチャンネルに接続できません。"
                )

            # 全ての検証を通ったのでここで初めて player を作る
            client = cast(MusicBot, interaction.client)
            player: lavalink.DefaultPlayer = client.lavalink.player_manager.create(
                interaction.guild.id
            )
            assert interaction.channel is not None
            player.store("channel", interaction.channel.id)
            # SPEC #30: 受信音声データを消費しないので self_deaf=True で参加。
            await voiceChannel.connect(cls=LavalinkVoiceClient, self_deaf=True)
        else:
            existing = cast(LavalinkVoiceClient, voiceClient)
            existingChannel = cast(discord.VoiceChannel, existing.channel)
            if existingChannel.id != voiceChannel.id:
                raise MusicCommandError(
                    "このコマンドを実行するには、ボットが接続しているチャンネルに接続する必要があります。"
                )

        return True

    @lavalink.listener(TrackEndEvent)
    async def onTrackEnd(self, event: TrackEndEvent):
        # SPEC #17: 元コードは onTrackEnd 内で len(player.queue) <= 0 を見て「キュー空」
        # と判断していたが、lavalink は hook 呼び出し前に synchronously 次の曲を pop 済み
        # なため、最後から2曲目終了時にも常に空判定 → 誤って「再生終了」パネルに書き換わる。
        # 判定は onQueueEnd に移し、ここでは prev history 追加と last-track 保存だけを行う。
        player = cast(MusicPlayer, event.player)
        track = cast(lavalink.AudioTrack | None, event.track)

        if track is None:
            return

        # 表示用に最後に「触った」曲を保存(onQueueEnd で使う。SPEC #18)。
        player.store("lastFinishedTrack", track)

        if player.loop == player.LOOP_SINGLE:
            return
        if event.reason != lavalink.EndReason.FINISHED:
            return

        # SPEC #23: LOOP_QUEUE 中は lavalink が current を queue 末尾に再挿入するため、
        # putPrevQueue すると prev 履歴が毎ループ肥大化する。LOOP_QUEUE 時は履歴を積まない。
        if player.loop == player.LOOP_QUEUE:
            return

        track.position = 0
        await self.putPrevQueue(player, track)

    @lavalink.listener(QueueEndEvent)
    async def onQueueEnd(self, event: QueueEndEvent):
        # SPEC #18: QueueEndEvent 時点で event.player.current は必ず None(lavalink 実装検証済み)。
        # 元コードの `if track:` は dead code。onTrackEnd 側で保存した lastFinishedTrack を使う。
        # LOAD_FAILED 経由でキューが尽きたケースもここで拾える(reason 問わず保存しているため)。
        player = cast(MusicPlayer, event.player)
        lastTrack = cast(
            lavalink.AudioTrack | None, player.fetch("lastFinishedTrack")
        )

        if lastTrack is not None:
            channelId = player.fetch("channelId")
            messageId = player.fetch("messageId")
            if channelId is not None and messageId is not None:
                channel = self.bot.get_channel(channelId)
                if isinstance(channel, discord.abc.Messageable):
                    try:
                        message = await channel.fetch_message(messageId)
                    except (discord.NotFound, discord.Forbidden):
                        message = None
                    guild = getattr(channel, "guild", None)
                    if message is not None and guild is not None:
                        requestAuthorMention = await resolveMemberMention(
                            guild, lastTrack.extra["requester"]
                        )
                        await self.editQueue.put(
                            (
                                message,
                                {
                                    "view": MusicPanel(
                                        player,
                                        lastTrack,
                                        requestAuthorMention,
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

        guildId = player.guild_id
        guild = self.bot.get_guild(guildId)

        if guild is not None and guild.voice_client is not None:
            # SPEC Phase 5 §5 — キュー終了瞬間に管理者が bot を蹴ると None になる
            vc = cast(LavalinkVoiceClient, guild.voice_client)
            vc.track = None
            await vc.disconnect(force=True)

    @lavalink.listener(PlayerUpdateEvent)
    async def onPlayerUpdate(self, event: PlayerUpdateEvent):
        player = cast(MusicPlayer, event.player)
        track = player.current

        player.ping = event.ping

        if track and time.time() - player.lastUpdated >= 5.0:
            player.update()

            message = await self._getPanelMessage(player)
            if message is None:
                return

            guild = getattr(message.channel, "guild", None)
            if guild is None:
                return
            requestAuthorMention = await resolveMemberMention(guild, track.extra["requester"])

            await self.editQueue.put(
                (
                    message,
                    {
                        "view": MusicPanel(
                            player,
                            track,
                            requestAuthorMention,
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
            return await interaction.followup.send(
                "クエリに対応する検索結果が見つかりませんでした。"
            )
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

        # SPEC #24: is_playing は TrackStart 到着まで False のため、アイドルに2人が同時に /play すると
        # 二重パネルが投稿される。channelId store の有無でアトミックに判定する。
        if player.fetch("channelId") is None:
            channel = interaction.channel
            if not isinstance(channel, discord.abc.Messageable):
                return
            message = await channel.send(
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
        if interaction.guild is None:
            return
        voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        player = cast(MusicPlayer | None, voiceClient.player)
        if player is None:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        # SPEC #14: 同 VC 制限
        if not isInBotVoiceChannel(interaction, voiceClient):
            await interaction.followup.send(
                "ボットと同じボイスチャンネルに参加してください。", ephemeral=True
            )
            return

        tsFilter = Timescale(speed=speed, pitch=pitch, rate=1)
        await player.set_filter(tsFilter)

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
        if interaction.guild is None:
            return
        voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        player = cast(MusicPlayer | None, voiceClient.player)
        if player is None:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        # SPEC #14: 同 VC 制限
        if not isInBotVoiceChannel(interaction, voiceClient):
            await interaction.followup.send(
                "ボットと同じボイスチャンネルに参加してください。", ephemeral=True
            )
            return

        await player.set_volume(volume)
        await interaction.followup.send(f"曲の音量を **``{volume}``** に変更しました。")

    @app_commands.command(
        name="queue", description="キューに入っている曲の一覧を取得します。"
    )
    @app_commands.guild_install()
    async def queueCommand(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None or not guild.voice_client:
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
        if interaction.guild is None:
            return
        voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        player = cast(MusicPlayer | None, voiceClient.player)
        if player is None:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        # SPEC #14: 同 VC 制限
        if not isInBotVoiceChannel(interaction, voiceClient):
            await interaction.followup.send(
                "ボットと同じボイスチャンネルに参加してください。", ephemeral=True
            )
            return

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
        if interaction.guild is None:
            return
        voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        player = cast(MusicPlayer | None, voiceClient.player)
        if player is None:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        # SPEC #14: 同 VC 制限
        if not isInBotVoiceChannel(interaction, voiceClient):
            await interaction.followup.send(
                "ボットと同じボイスチャンネルに参加してください。", ephemeral=True
            )
            return

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
        if interaction.guild is None:
            return
        voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
        if not voiceClient:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return
        # SPEC #14: 同 VC 制限
        if not isInBotVoiceChannel(interaction, voiceClient):
            await interaction.followup.send(
                "ボットと同じボイスチャンネルに参加してください。", ephemeral=True
            )
            return

        player = cast(MusicPlayer | None, voiceClient.player)
        if player is None:
            await voiceClient.disconnect(force=True)
            await interaction.followup.send("切断しました。")
            return
        track = player.current

        channelId = player.fetch("channelId")
        messageId = player.fetch("messageId")
        if track is None or channelId is None or messageId is None:
            await voiceClient.disconnect(force=True)
            await interaction.followup.send("切断しました。")
            return

        channel = self.bot.get_channel(channelId)
        if not isinstance(channel, discord.abc.Messageable):
            await voiceClient.disconnect(force=True)
            await interaction.followup.send("切断しました。")
            return
        message = await channel.fetch_message(messageId)

        guild = getattr(channel, "guild", None)
        if guild is None:
            await voiceClient.disconnect(force=True)
            await interaction.followup.send("切断しました。")
            return
        requestAuthorMention = await resolveMemberMention(guild, track.extra["requester"])

        await self.editQueue.put(
            (
                message,
                {
                    "view": MusicPanel(
                        player,
                        track,
                        requestAuthorMention,
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


async def setup(bot: MusicBot):
    await bot.add_cog(MusicCog(bot))
