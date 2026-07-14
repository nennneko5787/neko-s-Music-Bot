"""
パネル更新ヘルパ群。
SPEC_REFACTOR_PR2.md 第 2 段階で cogs/music.py の 5 サイトのパネル構築+editQueue.put と
3 サイトの fetch_message 直呼びをここに集約する。挙動不変(pure code motion + 統合)。

主なエントリ:
- getPanelMessage(cog, player): パネル Message をキャッシュ経由で解決(SPEC #22)
- buildPanel(cog, player, track, mention, finished=): MusicPanel を統一構築
- schedulePanelEdit(cog, target, panel): editQueue に共通の allowed_mentions で put
- refreshPanel(cog, player, track, mention, finished=False): パネル解決→構築→enqueue の合成
- finalizePanel(cog, player, track, mention): refreshPanel の finished=True 別名(呼び出し意図明示)

`cog` は MusicCog を想定。動的属性 cog.bot / cog.bar / cog.circle / cog.graybar / cog.editQueue に
アクセスする(TYPE_CHECKING の circular import 回避のため型注釈は "MusicCog" の文字列参照)。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord
import lavalink

from objects.ad import Ad
from objects.panel import MusicPanel
from objects.player import MusicPlayer

if TYPE_CHECKING:
    from cogs.music import MusicCog


# SPEC.md §5.2 の契約: パネル更新の allowed_mentions は everyone/users/roles/replied_user 全 False。
# ここに一本化して 5 サイトの重複を排除する。
ALLOWED_MENTIONS = discord.AllowedMentions(
    everyone=False, users=False, roles=False, replied_user=False
)


async def getPanelMessage(cog: MusicCog, player: MusicPlayer) -> discord.Message | None:
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
    cog: MusicCog,
    player: MusicPlayer,
    track: lavalink.AudioTrack,
    mention: str,
    *,
    finished: bool = False,
) -> MusicPanel:
    """
    MusicPanel を共通コンストラクタで生成。cog.bar/circle/graybar の emoji 注入を集約。
    SPEC_FEATURE_ADS §5.3: player.store("currentAd") から現在の広告を取り出して渡す。
    """
    ad = cast(Ad | None, player.fetch("currentAd"))
    return MusicPanel(
        player,
        track,
        mention,
        cog.bar,
        cog.circle,
        cog.graybar,
        finished=finished,
        ad=ad,
    )


async def schedulePanelEdit(
    cog: MusicCog,
    target: discord.Interaction | discord.Message,
    panel: MusicPanel,
) -> None:
    """
    editQueue に (target, {view, allowed_mentions}) の tuple を put。
    allowed_mentions は ALLOWED_MENTIONS に一本化(SPEC.md §5.2 の契約)。
    """
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
    """
    パネル Message を解決 → MusicPanel を組む → editQueue に enqueue する共通フロー。
    パネル Message が解決できない場合はサイレント no-op(SPEC #15 と同じ精神)。

    - onPlayerUpdate は finished=False で呼ぶ(5秒毎の定期更新)
    - onQueueEnd / stopCommand / onButtonClick.stop は finalizePanel 経由で finished=True
    """
    message = await getPanelMessage(cog, player)
    if message is None:
        return
    panel = buildPanel(cog, player, track, mention, finished=finished)
    await schedulePanelEdit(cog, message, panel)


async def finalizePanel(
    cog: MusicCog,
    player: MusicPlayer,
    track: lavalink.AudioTrack,
    mention: str,
) -> None:
    """
    refreshPanel(..., finished=True) の意図明示エイリアス。
    onQueueEnd / stopCommand / onButtonClick.stop の三重重複を集約する主役。
    disconnect は本関数の責務外(呼び出し側で行う — force=True/False の意図が場所ごとに違うため)。
    """
    await refreshPanel(cog, player, track, mention, finished=True)
