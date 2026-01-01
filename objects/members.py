from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_snake


class MemberData(BaseModel):
    id: int
    expiresAt: Optional[datetime] = None

    model_config = ConfigDict(alias_generator=to_snake)
