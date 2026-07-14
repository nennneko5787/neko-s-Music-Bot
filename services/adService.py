"""
広告機能サービス。SPEC_FEATURE_ADS.md §4.2 実装(panel-embedded 方式)。

config/ads/*.json から Ad を読み込み、重み付き抽選で 1 件を返すだけの
純粋な public API に絞られている。表示は MusicPanel 側が担当する。

Public API:
- loadAds(directory) -> int: startup で 1 度呼ぶ。有効広告数を返す。
- pickRandomAd() -> Ad | None: 重み付き抽選。空なら None(state を触らない純粋関数)。
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from pydantic import ValidationError

from objects.ad import Ad

_log = logging.getLogger("music")

_ADS: list[Ad] = []


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

    for jsonFile in sorted(dirPath.glob("*.json")):
        try:
            with jsonFile.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
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


def pickRandomAd() -> Ad | None:
    """
    重み付き抽選で広告を 1 件返す。広告が 0 件なら None。
    純粋関数(モジュール state を書き換えない、副作用なし)。
    """
    if not _ADS:
        return None
    weights = [ad.weight for ad in _ADS]
    return random.choices(_ADS, weights=weights, k=1)[0]
