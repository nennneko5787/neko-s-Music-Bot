"""
広告機能サービス。SPEC_FEATURE_ADS.md §4.2 実装。

config/ads/*.json から Ad を読み込み、TrackStart イベントごとにギルド別
8〜15 回間隔でランダム広告 LayoutView (Components V2) を音楽 channel に送信する。
ループ再生の同一トラック連続再生はカウント対象外(handleTrackStart 側で dedup)。

Public API:
- loadAds(directory) -> int: startup で 1 度呼ぶ。有効広告数を返す。
- buildAdView(ad) -> AdView: AdView を返す薄いファクトリ(テスト用)。
- maybeShowAd(channel, guildId) -> None: TrackStart hook から呼ぶ。
- clearGuildState(guildId) -> None: ギルド切断時に呼ぶ(カウンタ/閾値の GC)。
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path

import discord
from pydantic import ValidationError

from objects.ad import Ad
from objects.adPanel import AdView

_log = logging.getLogger("music")

# SPEC §4.2: ギルド別 8〜15 回に 1 回。定数はここに集約。
# 曲平均 3 分と仮定すると 24〜45 分に 1 回の露出。ループ dedup と合わせて非スパム化。
_MIN_INTERVAL = 8
_MAX_INTERVAL = 15

_ADS: list[Ad] = []
_GUILD_COUNTERS: dict[int, int] = {}
_GUILD_THRESHOLDS: dict[int, int] = {}
# 送信失敗を検出したギルド。同一ギルドで連続失敗しても WARN は最初の 1 回のみ出す。
# 成功したら pop してリセット。
_GUILD_FAILED: set[int] = set()

# 広告メッセージは対話性を持たないため、mention は全 False に固定。
# panelUpdater.ALLOWED_MENTIONS と同じ意図(通知汚染防止)。
_ALLOWED_MENTIONS = discord.AllowedMentions(
    everyone=False, users=False, roles=False, replied_user=False
)


def _rerollThreshold() -> int:
    return random.randint(_MIN_INTERVAL, _MAX_INTERVAL)


def loadAds(directory: str | Path = "config/ads") -> int:
    """
    directory 配下の *.json をすべて読み込んで _ADS を再構築する。
    有効な広告数(enabled=True かつ parse 成功)を返す。

    - ディレクトリ不在: 0 件でリターン(致命的にしない、SPEC §7)。
    - 個別 JSON parse 失敗 / ValidationError: WARN + skip、他は継続。
    """
    global _ADS
    _ADS = []

    dirPath = Path(directory)
    if not dirPath.exists():
        _log.info("Ad directory %s does not exist; no ads loaded.", dirPath)
        return 0

    # sorted で決定的順序。ログの読みやすさと再現性のため。
    for jsonFile in sorted(dirPath.glob("*.json")):
        try:
            with jsonFile.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            # UnicodeDecodeError は ValueError の派生。BOM や非 UTF-8 の混入ファイルで発生。
            # 該当 1 ファイルだけ skip し、他の広告読み込みと bot 起動は継続(SPEC §7)。
            _log.warning("Skipping unreadable ad file %s: %s", jsonFile, e)
            continue

        try:
            ad = Ad.model_validate(data)
        except ValidationError as e:
            _log.warning("Skipping malformed ad file %s: %s", jsonFile, e)
            continue

        if not ad.enabled:
            _log.debug("Skipping disabled ad %s (%s)", ad.id, jsonFile.name)
            continue

        _ADS.append(ad)

    _log.info("Loaded %d ad(s) from %s", len(_ADS), dirPath)
    return len(_ADS)


def _pickRandomAd() -> Ad | None:
    if not _ADS:
        return None
    weights = [ad.weight for ad in _ADS]
    return random.choices(_ADS, weights=weights, k=1)[0]


def buildAdView(ad: Ad) -> AdView:
    """AdView を構築する。単体テストや外部呼び出し用に公開している。"""
    return AdView(ad)


async def maybeShowAd(channel: discord.abc.Messageable, guildId: int) -> None:
    """
    ギルド別カウンタを進め、閾値到達なら重み付き抽選で 1 件を
    `channel.send(view=AdView)` する。TrackStart hook から呼ばれる想定。

    - _ADS が空: 何もしない(counter も進めない)。
    - 閾値未到達: counter を +1 して終了。
    - 閾値到達: 広告送信、counter=0、閾値を 8〜15 で再抽選。
    - Exception: WARN のみ、上位に伝播しない(音楽再生を止めない、SPEC §7)。
      discord.HTTPException だけでは aiohttp.ClientError / asyncio.TimeoutError
      などのトランスポート層例外を取り逃がすため広く捕える。
    """
    if not _ADS:
        return

    counter = _GUILD_COUNTERS.get(guildId, 0) + 1
    threshold = _GUILD_THRESHOLDS.get(guildId)
    if threshold is None:
        threshold = _rerollThreshold()
        _GUILD_THRESHOLDS[guildId] = threshold

    if counter < threshold:
        _GUILD_COUNTERS[guildId] = counter
        return

    ad = _pickRandomAd()
    _GUILD_COUNTERS[guildId] = 0
    _GUILD_THRESHOLDS[guildId] = _rerollThreshold()

    if ad is None:
        return

    view = buildAdView(ad)
    try:
        # Components V2 の LayoutView。embed 引数は使わない。
        await channel.send(view=view, allowed_mentions=_ALLOWED_MENTIONS)
    except Exception as e:
        # 権限不足等でこのチャンネルへの送信が慢性的に失敗する場合、
        # WARN が 3〜5 曲ごとに永久出続けるとログが埋まる。1 ギルド 1 回だけ WARN、
        # 以降は DEBUG に降格。次に送信成功したら失敗フラグを解除する。
        if guildId in _GUILD_FAILED:
            _log.debug("Ad send still failing for guild %s (%s): %s", guildId, ad.id, e)
        else:
            _log.warning(
                "Failed to send ad %s in guild %s (further failures logged at DEBUG): %s",
                ad.id, guildId, e,
            )
            _GUILD_FAILED.add(guildId)
    else:
        _GUILD_FAILED.discard(guildId)


def clearGuildState(guildId: int) -> None:
    """
    ギルドのカウンタ / 閾値 / 失敗フラグを削除する。
    lavalinkHooks.handleQueueEnd から disconnect 直前に呼ばれる想定。
    数千ギルドを長期間ホストしたときの dict 肥大化を抑える。
    """
    _GUILD_COUNTERS.pop(guildId, None)
    _GUILD_THRESHOLDS.pop(guildId, None)
    _GUILD_FAILED.discard(guildId)
