"""
/queue コマンドと queuePagenation ボタンで使うキュー表示ロジック。

SPEC_REFACTOR_PR5.md 第 2 段階で cogs/music.py MusicCog.pagenation / queuePagenation を
切り出したもの。挙動不変(pure code motion)。

Public API:
- pagenation(queue, page, *, pageSize=10): 純関数のスライス
- queuePagenation(cog, interaction, page=1, *, edit=False): Embed+View 送信 or 編集

SPEC 契約:
- custom_id "queuePagenation,{page}" (SPEC.md §5.2、buttonHandler の dispatch キーと共有)
- pageSize = 10 固定
- ceil ページ計算 (SPEC #19)
- ALLOWED_MENTIONS は panelUpdater.ALLOWED_MENTIONS を参照
"""
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


def pagenation(
    queue: list[lavalink.AudioTrack], page: int, *, pageSize: int = 10
) -> tuple:
    """
    queue の page 番目(1-indexed)のスライスを tuple で返す純関数。
    範囲外の場合は空 tuple を返す。
    """
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
    """
    /queue と queuePagenation ボタンから呼ばれる本体。
    Embed(曲一覧)+ View(⏪/🔄/⏩ の 3 ボタン)を組み立て、
    edit=True: cog.editQueue 経由で書き換え
    edit=False: interaction.followup.send で新規送信
    """
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
    songList: tuple[lavalink.AudioTrack, ...] = pagenation(
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
