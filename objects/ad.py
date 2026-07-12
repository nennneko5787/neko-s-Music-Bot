"""
広告データクラス。SPEC_FEATURE_ADS.md §3.1。

`extra="forbid"` により JSON 側のキーのタイポは import 時に検出される
(ValidationError → adService.loadAds が WARN + skip)。

必須文字列は `min_length=1` で空文字を弾く(Discord へ空 URL を送ると 400 に
なるが、その時点で発火分の広告カウンタが 1 回消費されるため、事前に落とす)。
linkUrl は Optional なので空文字 / 空白のみを None に正規化する。
"""
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _emptyToNone(v: object) -> object:
    """空文字 / 空白のみの文字列を None として扱う(linkUrl 用)。"""
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


class Ad(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    imageUrl: str = Field(min_length=1)
    linkUrl: Annotated[str | None, BeforeValidator(_emptyToNone)] = None
    weight: int = Field(default=1, ge=1)
    enabled: bool = True
