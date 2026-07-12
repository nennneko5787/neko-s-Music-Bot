"""
パネルボタンの dispatch 層。

SPEC_REFACTOR_PR4.md 第 2 段階で cogs/music.py MusicCog.onButtonClick(131 行の match 文と
pre-flight + tail 処理)を切り出したもの。挙動不変(pure code motion + dispatch table 化)。

構造:
- ButtonContext: handler に渡す実行時コンテキスト(frozen dataclass)
- 16 個の handleXxx(ctx) 関数: 各 custom_id に対応する非同期 handler
- _HANDLERS: custom_id → handler の dispatch table
- _EXPECTED_CUSTOM_IDS: 網羅性を import 時に assert する期待キー集合
- handleButtonClick(cog, interaction): エントリ関数(pre-flight + dispatch + tail)

handler の戻り値契約:
- True   → handler 内で完結、末尾の panel refresh を実行しない
           (prev/next/stop/queuePagenation の 4 種)
- None   → 末尾の panel refresh を実行(残り 12 種)
"""
from __future__ import annotations

import asyncio
import dataclasses
import random
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

import discord
import lavalink

from objects.client import LavalinkVoiceClient
from objects.player import MusicPlayer
from objects.utils import clamp, resolveMemberMention
from services import audioFilters, panelUpdater, playerCheck, queuePagination

if TYPE_CHECKING:
    from cogs.music import MusicCog


@dataclasses.dataclass(frozen=True)
class ButtonContext:
    """
    handler に渡す実行時コンテキスト。
    handleButtonClick の pre-flight で全フィールドが確定してから作られる。
    """

    cog: MusicCog
    interaction: discord.Interaction
    voiceClient: LavalinkVoiceClient
    player: MusicPlayer
    track: lavalink.AudioTrack
    requestAuthorMention: str
    customField: list[str]


Handler = Callable[[ButtonContext], Awaitable[bool | None]]


# ------------------------------- 個別 handler ---------------------------------


async def handlePrev(ctx: ButtonContext) -> bool:
    # SPEC #16: player.play() 引数無しは loop/shuffle 由来のバグ(1曲ループで戻れない・
    # shuffle でランダム曲になる・キュー内ループで重複)を引き起こす。track= 明示で回避。
    _track = ctx.player.current
    if _track is None:
        return True
    try:
        _prev = ctx.player.prevQueue.get_nowait()
    except asyncio.QueueEmpty:
        # SPEC #5: stale パネル経由で空 prevQueue に到達したときの hang 回避。
        await ctx.interaction.followup.send(
            "前の曲がありません。", ephemeral=True
        )
        return True
    _track.position = 0
    # 現在曲を queue 先頭に戻す(prev 再生後に自然に元の曲が続く)
    ctx.player.queue.insert(0, _track)
    await ctx.player.play(track=_prev)
    return True


async def handleNext(ctx: ButtonContext) -> bool:
    # SPEC #16: 1曲ループ中は skip() が同じ曲を再生し、キュー内ループでは queue の末尾に
    # current が append されて無限成長する。手動 next は loop バイパス、shuffle は尊重。
    _track = ctx.player.current
    if _track is None:
        return True
    await ctx.player.putPrevQueue(_track)

    if len(ctx.player.queue) == 0:
        await ctx.interaction.followup.send(
            "次の曲がありません。", ephemeral=True
        )
        return True
    popAt = random.randrange(len(ctx.player.queue)) if ctx.player.shuffle else 0
    _next = ctx.player.queue.pop(popAt)
    await ctx.player.play(track=_next)
    return True


async def handleStop(ctx: ButtonContext) -> bool:
    # SPEC.md §5.2: onButtonClick.stop は disconnect(force=False)。
    # stopCommand の disconnect(force=True) とは意図的に区別されている。
    await panelUpdater.finalizePanel(
        ctx.cog, ctx.player, ctx.track, ctx.requestAuthorMention
    )
    await ctx.voiceClient.disconnect()
    return True


async def handleResume(ctx: ButtonContext) -> None:
    await ctx.player.set_pause(False)


async def handlePause(ctx: ButtonContext) -> None:
    await ctx.player.set_pause(True)


async def handleReverse(ctx: ButtonContext) -> None:
    await ctx.player.seek(
        int(clamp(ctx.player.position - 10_000, 0, ctx.track.duration))
    )


async def handleForward(ctx: ButtonContext) -> None:
    await ctx.player.seek(
        int(clamp(ctx.player.position + 10_000, 0, ctx.track.duration))
    )


async def handleVolumeUp(ctx: ButtonContext) -> None:
    await ctx.player.set_volume(int(clamp(ctx.player.volume + 5, 0, 100)))


async def handleVolumeDown(ctx: ButtonContext) -> None:
    await ctx.player.set_volume(int(clamp(ctx.player.volume - 5, 0, 100)))


async def handleSpeedUp(ctx: ButtonContext) -> None:
    await audioFilters.changeSpeed(ctx.player, True)


async def handleSpeedDown(ctx: ButtonContext) -> None:
    await audioFilters.changeSpeed(ctx.player, False)


async def handlePitchUp(ctx: ButtonContext) -> None:
    await audioFilters.changePitch(ctx.player, True)


async def handlePitchDown(ctx: ButtonContext) -> None:
    await audioFilters.changePitch(ctx.player, False)


async def handleLoop(ctx: ButtonContext) -> None:
    loop = ctx.player.loop + 1
    if loop > 2:
        loop = 0
    ctx.player.loop = loop


async def handleShuffle(ctx: ButtonContext) -> None:
    ctx.player.set_shuffle(not ctx.player.shuffle)


async def handleQueuePagenation(ctx: ButtonContext) -> bool:
    # SPEC #3: return が無いと後段のパネル書き換えで queue 表示が上書きされる。
    await queuePagination.queuePagenation(
        ctx.cog, ctx.interaction, int(ctx.customField[1]), edit=True
    )
    return True


# ------------------------------ dispatch table -------------------------------


_HANDLERS: dict[str, Handler] = {
    "prev": handlePrev,
    "next": handleNext,
    "stop": handleStop,
    "resume": handleResume,
    "pause": handlePause,
    "reverse": handleReverse,
    "forward": handleForward,
    "volumeUp": handleVolumeUp,
    "volumeDown": handleVolumeDown,
    "speedUp": handleSpeedUp,
    "speedDown": handleSpeedDown,
    "pitchUp": handlePitchUp,
    "pitchDown": handlePitchDown,
    "loop": handleLoop,
    "shuffle": handleShuffle,
    "queuePagenation": handleQueuePagenation,
}

# 網羅性契約: この集合と _HANDLERS のキー集合は一致しなければならない。
# 追加 handler を書いたが _HANDLERS に登録し忘れた場合、import 時に AssertionError で落ちる。
_EXPECTED_CUSTOM_IDS: frozenset[str] = frozenset(
    {
        "prev",
        "next",
        "stop",
        "resume",
        "pause",
        "reverse",
        "forward",
        "volumeUp",
        "volumeDown",
        "speedUp",
        "speedDown",
        "pitchUp",
        "pitchDown",
        "loop",
        "shuffle",
        "queuePagenation",
    }
)

assert set(_HANDLERS.keys()) == _EXPECTED_CUSTOM_IDS, (
    "buttonHandler._HANDLERS のキー集合と _EXPECTED_CUSTOM_IDS が一致していません。"
    f" 差分: {set(_HANDLERS.keys()) ^ _EXPECTED_CUSTOM_IDS}"
)


# ----------------------------- エントリ関数 ----------------------------------


async def handleButtonClick(cog: MusicCog, interaction: discord.Interaction) -> None:
    """
    onButtonClick のエントリ。cogs/music.py MusicCog.onButtonClick から 1 行で委譲される。
    pre-flight → dispatch → tail (panel refresh) の 3 段構成。
    """
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
    if customField[0] != "queuePagenation" and not playerCheck.isInBotVoiceChannel(
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

    ctx = ButtonContext(
        cog=cog,
        interaction=interaction,
        voiceClient=voiceClient,
        player=player,
        track=track,
        requestAuthorMention=requestAuthorMention,
        customField=customField,
    )

    handler = _HANDLERS.get(customField[0])
    if handler is None:
        # 未知の custom_id は silent ignore(将来ボタン追加時の後方互換のため)
        return
    skipRefresh = await handler(ctx)
    if skipRefresh:
        return

    # tail: 現在曲を再取得してパネル再構築+enqueue。
    # handler の結果 player.current が変わっている可能性があるので再フェッチ。
    refreshed = player.current
    if refreshed is None:
        return
    track = refreshed
    requestAuthorMention = await resolveMemberMention(
        interaction.guild, track.extra["requester"]
    )
    panel = panelUpdater.buildPanel(
        cog, player, track, requestAuthorMention, finished=False
    )
    await panelUpdater.schedulePanelEdit(cog, interaction, panel)
