"""
lavalink event handler の実装本体。

SPEC_REFACTOR_PR7.md 第 5 段階で cogs/music.py MusicCog.onTrackEnd/onQueueEnd/
onPlayerUpdate の 3 個の中身を切り出したもの。挙動不変(pure code motion)。

Cog 側では `@lavalink.listener(EventType)` デコレータを持つメソッドが 1 行委譲で
本モジュールの handleXxx を呼ぶ。デコレータの登録契約は lavalink.py の
add_event_hooks(self) が Cog インスタンスをスキャンする形なので、listener 本体は
Cog に残す必要がある。

Public API:
- handleTrackStart(cog, event): SPEC_FEATURE_ADS §5.2 — 広告カウンタ進行 + 送信
- handleTrackEnd(cog, event): SPEC #17/#23 — lastFinishedTrack 保存 + prev history 追加
- handleQueueEnd(cog, event): SPEC #18 — finished パネル化 + voice disconnect
- handlePlayerUpdate(cog, event): 5秒スロットルでパネル(シークバー等)再構築
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, cast

import discord
import lavalink
from lavalink.events import (
    PlayerUpdateEvent,
    QueueEndEvent,
    TrackEndEvent,
    TrackStartEvent,
)

from objects.client import LavalinkVoiceClient
from objects.player import MusicPlayer
from objects.utils import resolveMemberMention
from services import adService, panelUpdater

if TYPE_CHECKING:
    from cogs.music import MusicCog


async def handleTrackStart(cog: MusicCog, event: TrackStartEvent) -> None:
    # SPEC_FEATURE_ADS §5.2: 曲頭ごとに広告カウンタを進め、閾値到達で送信する。
    player = cast(MusicPlayer, event.player)

    # ループ再生の連続同一トラック TrackStart はカウント対象外。
    # LOOP_SINGLE では毎サイクル同じ track.identifier で TrackStart が来るのでスパム源になる。
    # LOOP_QUEUE でも 1 曲キューだと同じ挙動。直前 counted トラックと同一なら skip。
    currentId = event.track.identifier
    lastCountedId = cast(str | None, player.fetch("lastCountedAdTrackId"))
    if lastCountedId == currentId:
        return
    player.store("lastCountedAdTrackId", currentId)

    channelId = cast(int | None, player.fetch("channelId"))
    if channelId is None:
        # 通常フローでは playCommand が player.play() の前に channelId を store する。
        # このガードは念のため(TrackStart が想定外タイミングで到達した場合の防御)。
        return
    channel = cog.bot.get_channel(channelId)
    if not isinstance(channel, discord.abc.Messageable):
        # チャンネル削除、bot 蹴られ、DM ではない、等
        return
    await adService.maybeShowAd(channel, player.guild_id)


async def handleTrackEnd(
    cog: MusicCog,  # noqa: ARG001 — API 統一のため受ける(handleQueueEnd/handlePlayerUpdate と揃える)
    event: TrackEndEvent,
) -> None:
    # SPEC #17: 元コードは onTrackEnd 内で len(player.queue) <= 0 を見て「キュー空」
    # と判断していたが、lavalink は hook 呼び出し前に synchronously 次の曲を pop 済み
    # なため、最後から2曲目終了時にも常に空判定 → 誤って「再生終了」パネルに書き換わる。
    # 判定は onQueueEnd に移し、ここでは prev history 追加と last-track 保存だけを行う。
    player = cast(MusicPlayer, event.player)
    track = event.track

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

    await player.putPrevQueue(track)


async def handleQueueEnd(cog: MusicCog, event: QueueEndEvent) -> None:
    # SPEC #18: QueueEndEvent 時点で event.player.current は必ず None(lavalink 実装検証済み)。
    # 元コードの `if track:` は dead code。onTrackEnd 側で保存した lastFinishedTrack を使う。
    # LOAD_FAILED 経由でキューが尽きたケースもここで拾える(reason 問わず保存しているため)。
    player = cast(MusicPlayer, event.player)
    lastTrack = cast(lavalink.AudioTrack | None, player.fetch("lastFinishedTrack"))

    if lastTrack is not None:
        guildId = player.guild_id
        guildForMention = cog.bot.get_guild(guildId)
        if guildForMention is not None:
            requestAuthorMention = await resolveMemberMention(
                guildForMention, lastTrack.extra["requester"]
            )
            await panelUpdater.finalizePanel(cog, player, lastTrack, requestAuthorMention)

    guildId = player.guild_id
    guild = cog.bot.get_guild(guildId)

    # SPEC_FEATURE_ADS §7: セッション終了と同時にギルド別カウンタを解放(dict 肥大化防止)。
    # 次回 /play で 0 からの再カウントとなり、初回 3〜5 曲後に広告が出るのを保つ。
    adService.clearGuildState(guildId)

    if guild is not None and guild.voice_client is not None:
        # SPEC Phase 5 §5 — キュー終了瞬間に管理者が bot を蹴ると None になる
        vc = cast(LavalinkVoiceClient, guild.voice_client)
        vc.track = None
        await vc.disconnect(force=True)


async def handlePlayerUpdate(cog: MusicCog, event: PlayerUpdateEvent) -> None:
    player = cast(MusicPlayer, event.player)
    track = player.current

    player.ping = event.ping

    if track and time.time() - player.lastUpdated >= 5.0:
        player.update()

        message = await panelUpdater.getPanelMessage(cog, player)
        if message is None:
            return

        guild = getattr(message.channel, "guild", None)
        if guild is None:
            return
        requestAuthorMention = await resolveMemberMention(guild, track.extra["requester"])

        panel = panelUpdater.buildPanel(cog, player, track, requestAuthorMention, finished=False)
        await panelUpdater.schedulePanelEdit(cog, message, panel)
