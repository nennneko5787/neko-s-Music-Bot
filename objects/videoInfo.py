from typing import Optional


class VideoInfo:
    __slots__ = (
        "title",
        "duration",
        "webpage_url",
        "thumbnail",
        "url",
    )

    def __init__(
        self,
        *,
        title: str,
        duration: int,
        webpage_url: str,
        thumbnail: str,
        url: Optional[str] = None
    ):
        self.title = title
        self.duration = duration
        self.url = url
        self.webpage_url = webpage_url
        self.thumbnail = thumbnail
