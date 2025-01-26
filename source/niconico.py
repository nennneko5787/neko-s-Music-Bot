import logging
import time
from datetime import datetime
from urllib.parse import ParseResult, urlparse
from zoneinfo import ZoneInfo

import discord
import httpx

from objects.videoInfo import VideoInfo

_log = logging.getLogger("music")


class DownloadFailed(Exception):
    pass


class NicoNicoAPI:
    def __init__(self):
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "neko-s-music-bot",
                "X-Frontend-Id": "6",
                "X-Frontend-Version": "0",
                "X-Niconico-Language": "ja-jp",
                "X-Client-Os-Type": "others",
                "X-Request-With": "https://www.nicovideo.jp",
                "Referer": "https://www.nicovideo.jp/",
            }
        )

    async def getWatchData(self, videoId: str) -> dict:
        response = await self.client.get(
            f"https://www.nicovideo.jp/watch/{videoId}?responseType=json"
        )
        response.raise_for_status()
        self.domandBid = response.cookies.get("domand_bid", None)
        return response.json()

    def getOutputs(
        self, videoInfo: dict, *, audioOnly: bool = True
    ) -> dict[str, list[str]]:
        outputs: dict[str, list[str]] = {}
        topAudioId = None
        topAudioQuality = -1

        for audio in videoInfo["data"]["response"]["media"]["domand"]["audios"]:
            if audio["isAvailable"] and audio["qualityLevel"] > topAudioQuality:
                topAudioId = audio["id"]
                topAudioQuality = audio["qualityLevel"]

        if topAudioId is None:
            return outputs

        for video in videoInfo["data"]["response"]["media"]["domand"]["videos"]:
            if video["isAvailable"]:
                outputs[video["label"]] = (
                    [topAudioId] if audioOnly else [video["id"], topAudioId]
                )

        return outputs

    async def getHlsContentUrl(
        self, videoInfo: dict, outputs: dict[str, list[str]]
    ) -> str | None:
        videoId = videoInfo["data"]["response"]["client"]["watchId"]
        actionTrackId = videoInfo["data"]["response"]["client"]["watchTrackId"]
        accessRightKey = videoInfo["data"]["response"]["media"]["domand"][
            "accessRightKey"
        ]

        headers = self.client.headers
        headers["X-Access-Right-Key"] = accessRightKey

        response = await self.client.post(
            f"https://nvapi.nicovideo.jp/v1/watch/{videoId}/access-rights/hls?actionTrackId={actionTrackId}",
            json={"outputs": outputs},
            headers=headers,
        )

        if response.status_code == 201:
            self.domandBid = response.cookies.get("domand_bid", None)
            jsonData = response.json()
            if jsonData["data"] is not None:
                return jsonData["data"]["contentUrl"]

        return None


class NicoNicoSource(discord.PCMVolumeTransformer):
    """ニコニコ動画とうまく連携するAudioSourceを提供します。クラスを直接作るのではなく、from_url関数を使用してAudioSourceを作成してください。"""

    __slots__ = (
        "info",
        "hslContentUrl",
        "watchid",
        "trackid",
        "outputs",
        "nicosid",
        "niconico",
        "__count",
        "user",
        "original",
        "_volume",
    )

    def __init__(
        self,
        source,
        *,
        info: VideoInfo,
        hslContentUrl: str,
        watchid: str,
        trackid: str,
        outputs: str,
        nicosid: str,
        niconico: NicoNicoAPI,
        volume: float = 0.5,
        progress: float = 0,
        user: discord.Member = None,
    ):
        super().__init__(source, volume=volume)
        self.info = info
        self.hslContentUrl = hslContentUrl
        self.watchid = watchid
        self.trackid = trackid
        self.outputs = outputs
        self.nicosid = nicosid
        self.niconico = niconico
        self.user = user
        self.__count = progress
        self.client = niconico.client

    @property
    def progress(self) -> float:
        return self.__count * 0.02  # count * 20ms

    def read(self) -> bytes:
        data = super().read()
        if data:
            self.__count += 1
        return data

    async def sendHeartBeat(self) -> bool:
        response = await self.client.post(
            f"https://nvapi.nicovideo.jp/v1/watch/{self.watchid}/access-rights/hls?actionTrackId={self.trackid}&__retry=0",
            json={
                "outputs": self.outputs,
                "heartbeat": {
                    "method": "regular",
                    "params": {
                        "eventType": "start",
                        "eventOccurredAt": datetime.now(
                            ZoneInfo("Asia/Tokyo")
                        ).isoformat(),
                        "watchMilliseconds": 0,
                        "endCount": 0,
                        "additionalParameters": {
                            "___pc_v": 1,
                            "os": "Windows",
                            "os_version": "15.0.0",
                            "nicosid": self.nicosid,
                            "referer": "",
                            "query_parameters": {},
                            "is_ad_block": False,
                            "has_playlist": False,
                            "___abw": None,
                            "abw_show": False,
                            "abw_closed": False,
                            "abw_seen_at": None,
                            "viewing_source": "",
                            "viewing_source_detail": {},
                            "playback_rate": "",
                            "use_flip": False,
                            "quality": [],
                            "auto_quality": [],
                            "loop_count": 0,
                            "suspend_count": 0,
                            "load_failed": False,
                            "error_description": [],
                            "end_position_milliseconds": None,
                            "performance": {
                                "watch_access_start": datetime.now(
                                    ZoneInfo("Asia/Tokyo")
                                ).timestamp()
                                * 1000,
                                "watch_access_finish": None,
                                "video_loading_start": (
                                    datetime.now(ZoneInfo("Asia/Tokyo")).timestamp()
                                    + 10
                                )
                                * 1000,
                                "video_loading_finish": None,
                                "video_play_start": None,
                                "end_context": {
                                    "ad_playing": False,
                                    "video_playing": False,
                                    "is_suspending": False,
                                },
                            },
                        },
                    },
                },
            },
        )
        if response.status_code == 200:
            return True
        else:
            return False

    @classmethod
    async def from_url(cls, url, volume: float = 0.5, user: discord.Member = None):
        """urlからAudioSourceを作成します。

        Args:
            url (str): ニコニコの動画URL。
            volume (float, optional): AudioSourceの音量。デフォルトは0.5です。

        Returns:
            NicoNicoSource: 完成したAudioSource。
        """
        _log.info(f"loading {url} with NicoNicoSource now")

        niconico = NicoNicoAPI()

        parsed_url: ParseResult = urlparse(url)
        path_parts = parsed_url.path.split("/")
        videoId = path_parts[-1]

        data = await niconico.getWatchData(videoId)
        outputs = niconico.getOutputs(data, audioOnly=False)
        outputLabel = next(iter(outputs))

        hslContentUrl = await niconico.getHlsContentUrl(data, [outputs[outputLabel]])
        if hslContentUrl is None:
            raise DownloadFailed("Failed to get the HLS content URL.")

        watchid = data["data"]["response"]["client"]["watchId"]
        trackid = data["data"]["response"]["client"]["watchTrackId"]
        _outputs = [outputs[outputLabel]]
        nicosid = niconico.client.cookies["nicosid"]

        cookies = niconico.client.cookies

        FFMPEG_OPTIONS = {
            "before_options": f"-headers 'cookie: {'; '.join(f'{k}={v}' for k, v in cookies.items())}' -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -bufsize 64k -analyzeduration 2147483647 -probesize 2147483647",
        }

        info = VideoInfo(
            title=data["data"]["response"]["video"]["title"],
            duration=int(data["data"]["response"]["video"]["duration"]),
            webpage_url=f'https://www.nicovideo.jp/watch/{data["data"]["response"]["video"]["id"]}',
            thumbnail=data["data"]["response"]["video"]["thumbnail"]["ogp"],
        )

        _log.info(f"success loading {url}")

        return cls(
            discord.FFmpegPCMAudio(hslContentUrl, **FFMPEG_OPTIONS),
            info=info,
            hslContentUrl=hslContentUrl,
            watchid=watchid,
            trackid=trackid,
            outputs=_outputs,
            nicosid=nicosid,
            niconico=niconico,
            volume=volume,
            user=user,
        )
