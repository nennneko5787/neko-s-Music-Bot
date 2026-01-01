from typing import List

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_snake


class MusicData(BaseModel):
    url: str
    title: str


class GuildData(BaseModel):
    id: int
    playedMusics: List[MusicData] = []

    model_config = ConfigDict(alias_generator=to_snake)
