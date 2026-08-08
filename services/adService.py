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
    directory 配下の *.json を読み込んで _ADS を再構築し、有効な広告数を返す。
    SPEC_FEATURE_ADS §7: ディレクトリ不在・個別ファイルの不正はいずれも致命的にしない。
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
    """重み付き抽選で広告を 1 件返す。広告が 0 件なら None。"""
    if not _ADS:
        return None
    weights = [ad.weight for ad in _ADS]
    return random.choices(_ADS, weights=weights, k=1)[0]
