from __future__ import annotations

import asyncio
import dataclasses
import enum
import random
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

import discord
import lavalink

from objects.client import LavalinkVoiceClient
from objects.mixPanel import MixPanel
from objects.player import MusicPlayer
from objects.utils import clamp, resolveMemberMention
from services import audioFilters, panelUpdater, playerCheck, queuePagination

if TYPE_CHECKING:
    from cogs.music import MusicCog


class Refresh(enum.Enum):
    """handler 実行後に再構築するパネルの種別。"""

    NONE = "none"
    MUSIC = "music"
    """主パネル(MusicPanel)。対象は player に紐づくパネル Message。"""
    MIX = "mix"
    """押された Mix パネル(ephemeral)。対象は interaction 自身。"""


@dataclasses.dataclass
class ButtonContext:
    """handler に渡す実行時コンテキスト。"""

    cog: MusicCog
    interaction: discord.Interaction
    guild: discord.Guild
    voiceClient: LavalinkVoiceClient
    player: MusicPlayer
    track: lavalink.AudioTrack
    customField: list[str]
    _mentions: dict[int, str] = dataclasses.field(default_factory=dict, repr=False)

    async def mentionFor(self, track: lavalink.AudioTrack) -> str:
        """requester の mention を解決する。SPEC #22: fetch_member を 1 interaction 1 回に抑える。"""
        userId: int = track.extra["requester"]
        cached = self._mentions.get(userId)
        if cached is None:
            cached = await resolveMemberMention(self.guild, userId)
            self._mentions[userId] = cached
        return cached


Handler = Callable[[ButtonContext], Awaitable[None]]


@dataclasses.dataclass(frozen=True)
class ButtonSpec:
    handler: Handler
    refresh: Refresh
    requiresVoice: bool


_HANDLERS: dict[str, ButtonSpec] = {}


def button(
    customId: str,
    *,
    refresh: Refresh,
    requiresVoice: bool = True,
) -> Callable[[Handler], Handler]:
    """handler を定義と同時に _HANDLERS へ登録するデコレータ。"""

    def decorator(handler: Handler) -> Handler:
        if customId in _HANDLERS:
            raise RuntimeError(f"custom_id が重複して登録されました: {customId}")
        _HANDLERS[customId] = ButtonSpec(handler=handler, refresh=refresh, requiresVoice=requiresVoice)
        return handler

    return decorator


# -------------------------- MusicPanel 上のボタン ----------------------------


@button("prev", refresh=Refresh.NONE)
async def handlePrev(ctx: ButtonContext) -> None:
    # SPEC #16: play() の loop/shuffle ロジックを回避するため track= を明示する。
    _track = ctx.player.current
    if _track is None:
        return
    try:
        _prev = ctx.player.prevQueue.get_nowait()
    except asyncio.QueueEmpty:
        # SPEC #5: 空 prevQueue での await hang 回避。
        await ctx.interaction.followup.send("前の曲がありません。", ephemeral=True)
        return
    _track.position = 0
    # 現在曲を queue 先頭に戻し、prev 再生後に元の曲が続くようにする。
    ctx.player.queue.insert(0, _track)
    await ctx.player.play(track=_prev)


@button("next", refresh=Refresh.NONE)
async def handleNext(ctx: ButtonContext) -> None:
    # SPEC #16: skip() は使わない。手動 next は loop をバイパスし shuffle は尊重する。
    _track = ctx.player.current
    if _track is None:
        return
    await ctx.player.putPrevQueue(_track)

    if len(ctx.player.queue) == 0:
        await ctx.interaction.followup.send("次の曲がありません。", ephemeral=True)
        return
    popAt = random.randrange(len(ctx.player.queue)) if ctx.player.shuffle else 0
    _next = ctx.player.queue.pop(popAt)
    await ctx.player.play(track=_next)


@button("stop", refresh=Refresh.NONE)
async def handleStop(ctx: ButtonContext) -> None:
    # SPEC §5.2: stopCommand の force=True と区別して force=False で切断する。
    await panelUpdater.finalizePanel(ctx.cog, ctx.player, ctx.track, await ctx.mentionFor(ctx.track))
    await ctx.voiceClient.disconnect()


@button("resume", refresh=Refresh.MUSIC)
async def handleResume(ctx: ButtonContext) -> None:
    await ctx.player.set_pause(False)


@button("pause", refresh=Refresh.MUSIC)
async def handlePause(ctx: ButtonContext) -> None:
    await ctx.player.set_pause(True)


@button("reverse", refresh=Refresh.MUSIC)
async def handleReverse(ctx: ButtonContext) -> None:
    await ctx.player.seek(int(clamp(ctx.player.position - 10_000, 0, ctx.track.duration)))


@button("forward", refresh=Refresh.MUSIC)
async def handleForward(ctx: ButtonContext) -> None:
    await ctx.player.seek(int(clamp(ctx.player.position + 10_000, 0, ctx.track.duration)))


@button("loop", refresh=Refresh.MUSIC)
async def handleLoop(ctx: ButtonContext) -> None:
    match ctx.player.loop:
        case ctx.player.LOOP_NONE:
            ctx.player.loop = ctx.player.LOOP_QUEUE
        case ctx.player.LOOP_QUEUE:
            ctx.player.loop = ctx.player.LOOP_SINGLE
        case ctx.player.LOOP_SINGLE | _:
            ctx.player.loop = ctx.player.LOOP_NONE


@button("shuffle", refresh=Refresh.MUSIC)
async def handleShuffle(ctx: ButtonContext) -> None:
    ctx.player.set_shuffle(not ctx.player.shuffle)


@button("mix", refresh=Refresh.NONE)
async def handleOpenMix(ctx: ButtonContext) -> None:
    # 別メッセージを開くだけで主パネルは変化しないため refresh=NONE。
    await ctx.interaction.followup.send(
        view=MixPanel(ctx.player),
        ephemeral=True,
    )


# --------------------------- MixPanel 上のボタン -----------------------------
# 音量・速度・ピッチは MusicPanel に表示されないため、押された Mix パネル自身を描き直す。


@button("volumeUp", refresh=Refresh.MIX)
async def handleVolumeUp(ctx: ButtonContext) -> None:
    await ctx.player.set_volume(int(clamp(ctx.player.volume + 5, 0, 100)))


@button("volumeDown", refresh=Refresh.MIX)
async def handleVolumeDown(ctx: ButtonContext) -> None:
    await ctx.player.set_volume(int(clamp(ctx.player.volume - 5, 0, 100)))


@button("speedUp", refresh=Refresh.MIX)
async def handleSpeedUp(ctx: ButtonContext) -> None:
    await audioFilters.changeSpeed(ctx.player, True)


@button("speedDown", refresh=Refresh.MIX)
async def handleSpeedDown(ctx: ButtonContext) -> None:
    await audioFilters.changeSpeed(ctx.player, False)


@button("pitchUp", refresh=Refresh.MIX)
async def handlePitchUp(ctx: ButtonContext) -> None:
    await audioFilters.changePitch(ctx.player, True)


@button("pitchDown", refresh=Refresh.MIX)
async def handlePitchDown(ctx: ButtonContext) -> None:
    await audioFilters.changePitch(ctx.player, False)


# ----------------------------- /queue のボタン -------------------------------


@button("queuePagenation", refresh=Refresh.NONE, requiresVoice=False)
async def handleQueuePagenation(ctx: ButtonContext) -> None:
    # SPEC #14: view-only なので VC 参加チェック免除。SPEC #3: refresh すると queue 表示が消える。
    await queuePagination.queuePagenation(ctx.cog, ctx.interaction, int(ctx.customField[1]), edit=True)


# ----------------------------- エントリ関数 ----------------------------------


async def handleButtonClick(cog: MusicCog, interaction: discord.Interaction) -> None:
    """onButtonClick のエントリ。pre-flight → dispatch → refresh の 3 段構成。"""
    data = cast(dict, interaction.data)
    customField: list[str] = data["custom_id"].split(",")

    # 未知の custom_id は自分の持ち物ではないため defer もせずに抜ける。
    spec = _HANDLERS.get(customField[0])
    if spec is None:
        return

    if interaction.guild is None:
        return
    voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
    if voiceClient is None:
        await interaction.response.send_message("現在曲を再生していません。", ephemeral=True)
        return
    player = cast(MusicPlayer | None, voiceClient.player)
    if player is None:
        await interaction.response.send_message("現在曲を再生していません。", ephemeral=True)
        return
    # SPEC #14: VC 参加チェック。
    if spec.requiresVoice and not playerCheck.isInBotVoiceChannel(interaction, voiceClient):
        await interaction.response.send_message("ボットと同じボイスチャンネルに参加してください。", ephemeral=True)
        return
    # component interaction の defer は deferred_message_update になるため、
    # 以降の edit_original_response の対象は「押されたボタンが載っていたメッセージ」。
    await interaction.response.defer(ephemeral=True)

    current = player.current
    if current is None:
        return  # 曲終了直後にボタンが押されるレース窓(SPEC Phase 5 §5)

    ctx = ButtonContext(
        cog=cog,
        interaction=interaction,
        guild=interaction.guild,
        voiceClient=voiceClient,
        player=player,
        track=current,
        customField=customField,
    )

    await spec.handler(ctx)
    await _refresh(ctx, spec.refresh)


async def _refresh(ctx: ButtonContext, refresh: Refresh) -> None:
    """handler 実行後のパネル再描画。宣言された Refresh に従って対象を選ぶ。"""
    if refresh is Refresh.NONE:
        return

    if refresh is Refresh.MIX:
        # ephemeral で Message オブジェクトを持てないため interaction 経由で編集する。
        await panelUpdater.schedulePanelEdit(ctx.cog, ctx.interaction, MixPanel(ctx.player))
        return

    # SPEC_REFACTOR_PR8.md §3.2: 主パネルは interaction ではなく messageId から解決する。
    # handler の await 中に曲が終わっている可能性があるので current を取り直す。
    track = ctx.player.current
    if track is None:
        return
    await panelUpdater.refreshPanel(ctx.cog, ctx.player, track, await ctx.mentionFor(track))
