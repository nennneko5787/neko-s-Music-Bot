from __future__ import annotations

import time
from typing import TYPE_CHECKING, cast

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


async def handleTrackStart(
    cog: MusicCog,  # noqa: ARG001 — API 統一のため受ける
    event: TrackStartEvent,
) -> None:
    # SPEC_FEATURE_ADS §5.2: 別トラックに切り替わった瞬間だけ広告を rotate する。
    player = cast(MusicPlayer, event.player)
    currentId = event.track.identifier
    lastCountedId = cast(str | None, player.fetch("lastCountedAdTrackId"))
    if lastCountedId == currentId:
        return
    player.store("lastCountedAdTrackId", currentId)
    player.store("currentAd", adService.pickRandomAd())


async def handleTrackEnd(
    cog: MusicCog,  # noqa: ARG001 — API 統一のため受ける
    event: TrackEndEvent,
) -> None:
    # SPEC #17: キュー空の判定は onQueueEnd の責務。ここでは履歴と last-track だけ扱う。
    player = cast(MusicPlayer, event.player)
    track = event.track

    if track is None:
        return

    player.store("lastFinishedTrack", track)  # SPEC #18: onQueueEnd の表示に使う

    if player.loop == player.LOOP_SINGLE:
        return
    if event.reason != lavalink.EndReason.FINISHED:
        return

    # SPEC #23: LOOP_QUEUE は current が queue 末尾に戻るため履歴を積むと毎周肥大化する。
    if player.loop == player.LOOP_QUEUE:
        return

    await player.putPrevQueue(track)


async def handleQueueEnd(cog: MusicCog, event: QueueEndEvent) -> None:
    # SPEC #18: この時点で player.current は必ず None なので lastFinishedTrack を使う。
    player = cast(MusicPlayer, event.player)
    lastTrack = cast(lavalink.AudioTrack | None, player.fetch("lastFinishedTrack"))

    if lastTrack is not None:
        guildId = player.guild_id
        guildForMention = cog.bot.get_guild(guildId)
        if guildForMention is not None:
            requestAuthorMention = await resolveMemberMention(guildForMention, lastTrack.extra["requester"])
            await panelUpdater.finalizePanel(cog, player, lastTrack, requestAuthorMention)

    guildId = player.guild_id
    guild = cog.bot.get_guild(guildId)

    if guild is not None and guild.voice_client is not None:  # SPEC Phase 5 §5
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

        panel = panelUpdater.buildPanel(player, track, requestAuthorMention, finished=False)
        await panelUpdater.schedulePanelEdit(cog, message, panel)
