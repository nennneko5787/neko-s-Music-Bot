import discord
from typing import Optional


class Item:
    __slots__ = (
        "url",
        "attachment",
        "volume",
        "user",
        "title",
    )

    def __init__(
        self,
        *,
        user: discord.Member,
        url: Optional[str] = None,
        title: Optional[str] = None,
        attachment: Optional[discord.Attachment] = None,
        volume: float = 0.5,
    ):
        self.url: Optional[str] = url
        self.title: Optional[str] = title
        self.attachment: Optional[discord.Attachment] = attachment
        self.volume: float = volume
        self.user: discord.Member = user

    @property
    def name(self):
        if self.attachment is not None:
            return self.attachment.filename
        elif self.title is not None:
            return f"[{self.title}]({self.url})"
        else:
            return self.url
