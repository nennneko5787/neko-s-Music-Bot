"""
広告機能サービス。SPEC_FEATURE_ADS.md §4.2 実装。

config/ads/*.json から Ad を読み込み、/play 実行時にギルド別 3〜5 回間隔で
ランダム広告 LayoutView (Components V2) を送信する。

Public API:
- loadAds(directory) -> int: startup で 1 度呼ぶ。有効広告数を返す。
- buildAdView(ad) -> AdView: AdView を返す薄いファクトリ(テスト用)。
- maybeShowAd(interaction, guildId) -> None: /play 末尾で呼ぶ。
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

# SPEC §4.2: ギルド別 3〜5 回に 1 回。定数はここに集約。
_MIN_INTERVAL = 3
_MAX_INTERVAL = 5

_ADS: list[Ad] = []
_GUILD_COUNTERS: dict[int, int] = {}
_GUILD_THRESHOLDS: dict[int, int] = {}


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


async def maybeShowAd(interaction: discord.Interaction, guildId: int) -> None:
    """
    ギルド別カウンタを進め、閾値到達なら重み付き抽選で 1 件を followup 送信する。

    - _ADS が空: 何もしない(counter も進めない → 空 → 追加後にリセット挙動が乱れないよう温存)。
    - 閾値未到達: counter を +1 して終了。
    - 閾値到達: 広告送信、counter=0、閾値を 3〜5 で再抽選。
    - HTTPException: WARN のみ、上位に伝播しない(音楽再生を止めない、SPEC §7)。
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
        await interaction.followup.send(view=view)
    except Exception as e:
        # 広告送信失敗は絶対に /play を止めない(SPEC §7)。
        # discord.HTTPException だけでは aiohttp.ClientError / asyncio.TimeoutError /
        # ConnectionError などのトランスポート層例外を取り逃がし、上位の playCommand が
        # 続きの WaitingView 投稿・player.play() に到達できず SPEC #24 の
        # channelId ガードも張られないまま「無音」で停止する。広く捕える。
        _log.warning("Failed to send ad %s: %s", ad.id, e)
