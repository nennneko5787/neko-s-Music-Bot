from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord
import lavalink

from objects.ad import Ad
from objects.panel import MusicPanel
from objects.player import MusicPlayer

if TYPE_CHECKING:
    from cogs.music import MusicCog


# SPEC §5.2: パネル更新の allowed_mentions は全 False。
ALLOWED_MENTIONS = discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False)


async def getPanelMessage(cog: MusicCog, player: MusicPlayer) -> discord.Message | None:
    """パネル Message を解決する。SPEC #22: プレイヤー寿命内でキャッシュする。"""
    cached = cast(discord.Message | None, player.fetch("_panelMessage"))
    if cached is not None:
        return cached
    channelId = player.fetch("channelId")
    messageId = player.fetch("messageId")
    if channelId is None or messageId is None:
        return None
    channel = cog.bot.get_channel(channelId)
    if not isinstance(channel, discord.abc.Messageable):
        return None
    try:
        message = await channel.fetch_message(messageId)
    except (discord.NotFound, discord.Forbidden):
        return None
    player.store("_panelMessage", message)
    return message


def buildPanel(
    player: MusicPlayer,
    track: lavalink.AudioTrack,
    mention: str,
    *,
    finished: bool = False,
) -> MusicPanel:
    """MusicPanel を生成する。SPEC_FEATURE_ADS §5.3: 現在の広告を player store から渡す。"""
    ad = cast(Ad | None, player.fetch("currentAd"))
    return MusicPanel(player, track, mention, finished=finished, ad=ad)


async def schedulePanelEdit(
    cog: MusicCog,
    target: discord.Interaction | discord.Message,
    panel: discord.ui.LayoutView,
) -> None:
    """editQueue に (target, kwargs) を put する。panel は MusicPanel / MixPanel の両方を受ける。"""
    await cog.editQueue.put(
        (
            target,
            {
                "view": panel,
                "allowed_mentions": ALLOWED_MENTIONS,
            },
        )
    )


async def refreshPanel(
    cog: MusicCog,
    player: MusicPlayer,
    track: lavalink.AudioTrack,
    mention: str,
    *,
    finished: bool = False,
) -> None:
    """パネル解決 → 構築 → enqueue。Message が解決できない場合はサイレント no-op。"""
    message = await getPanelMessage(cog, player)
    if message is None:
        return
    panel = buildPanel(player, track, mention, finished=finished)
    await schedulePanelEdit(cog, message, panel)


async def finalizePanel(
    cog: MusicCog,
    player: MusicPlayer,
    track: lavalink.AudioTrack,
    mention: str,
) -> None:
    """refreshPanel(..., finished=True) の別名。disconnect は呼び出し側の責務。"""
    await refreshPanel(cog, player, track, mention, finished=True)
