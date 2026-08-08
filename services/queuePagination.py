from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord
import lavalink

from objects.client import LavalinkVoiceClient
from objects.player import MusicPlayer
from objects.utils import resolveMemberMention
from services import panelUpdater

if TYPE_CHECKING:
    from cogs.music import MusicCog


def pagenation(queue: list[lavalink.AudioTrack], page: int, *, pageSize: int = 10) -> tuple:
    """queue の page 番目(1-indexed)のスライス。範囲外なら空 tuple。"""
    startIndex = (page - 1) * pageSize
    endIndex = startIndex + pageSize
    if startIndex >= len(queue) or page < 1:
        return ()
    return tuple(queue[startIndex:endIndex])


async def queuePagenation(
    cog: MusicCog,
    interaction: discord.Interaction,
    page: int = 1,
    *,
    edit: bool = False,
) -> None:
    """キュー一覧の Embed + ページ送り View を送信(edit=False)または書き換え(edit=True)する。"""
    # SPEC #3: /queue 経由では既に defer 済みなのでダブル defer を避ける。
    if not interaction.response.is_done():
        await interaction.response.defer()
    if interaction.guild is None:
        return
    voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
    if not voiceClient:
        await interaction.followup.send("コマンドを実行する前に、曲を再生してください。")
        return
    player = cast(MusicPlayer | None, voiceClient.player)
    if player is None:
        await interaction.followup.send("コマンドを実行する前に、曲を再生してください。")
        return

    queue = player.queue.copy()
    if player.current is not None:
        queue.insert(0, player.current)

    pageSize = 10
    songList: tuple[lavalink.AudioTrack, ...] = pagenation(queue, page, pageSize=pageSize)
    songs = ""

    for i, song in enumerate(songList):
        mention = await resolveMemberMention(interaction.guild, song.extra["requester"])
        songs += f"[{song.title}]({song.uri}) by {mention} `{'(現在再生中)' if i == 0 else ''}`\n"

    # SPEC #19: ceil で計算する(切り捨て + 1 は 10 の倍数で空ページを生む)。
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
        await cog.editQueue.put(
            (
                interaction,
                {
                    "embed": embed,
                    "view": view,
                    "allowed_mentions": panelUpdater.ALLOWED_MENTIONS,
                },
            )
        )
    else:
        await interaction.followup.send(embed=embed, view=view)
