from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _emptyToNone(v: object) -> object:
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


class Ad(BaseModel):
    """広告データ。SPEC_FEATURE_ADS.md §3.1。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    imageUrl: str = Field(min_length=1)
    linkUrl: Annotated[str | None, BeforeValidator(_emptyToNone)] = None
    weight: int = Field(default=1, ge=1)
    enabled: bool = True
