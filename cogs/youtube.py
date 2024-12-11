import os
from urllib.parse import urlparse, parse_qs

import aiohttp
import dotenv

dotenv.load_dotenv()


class YoutubeAPI:
    def isYoutubePlayList(self, url: str) -> bool:
        try:
            parsedUrl = urlparse(url)
            if parsedUrl.netloc in [
                "www.youtube.com",
                "youtube.com",
            ]:
                if "playlist" in url:
                    queryParams = parse_qs(parsedUrl.query)
                    return "list" in queryParams
                else:
                    return False
            return False
        except Exception as e:
            print(f"Error: {e}")
            return False

    def extractPlaylistId(self, playlistUrl: str) -> str:
        """
        Extracts the playlist ID from a YouTube playlist URL.
        :param parsedUrl: The URL of the YouTube playlist.
        :return: The playlist ID if found, otherwise None.
        """
        try:
            parsedUrl = urlparse(playlistUrl)
            queryParams = parse_qs(parsedUrl.query)
            return queryParams.get("list", [None])[0]
        except Exception as e:
            print(f"Error: {e}")
            return None

    async def fetchPlaylistItems(self, playListId: str, maxResult: int = 50):
        """
        Fetches the contents of a YouTube playlist asynchronously.
        :param playListId: The ID of the YouTube playlist.
        :param maxResult: The maximum number of results to fetch per request (max 50).
        :return: A list of video details.
        """
        async with aiohttp.ClientSession() as session:
            videos = []
            nextPageToken = None

            while True:
                params = {
                    "part": "snippet",
                    "playlistId": playListId,
                    "maxResults": maxResult,
                    "key": os.getenv("youtube"),
                }
                if nextPageToken:
                    params["pageToken"] = nextPageToken

                async with session.get(
                    "https://www.googleapis.com/youtube/v3/playlistItems", params=params
                ) as response:
                    if response.status != 200:
                        raise Exception(
                            f"Failed to fetch playlist: {response.status}, {await response.text()}"
                        )

                    data: dict = await response.json()
                    items = data.get("items", [])
                    videos.extend(items)

                    next_page_token = data.get("nextPageToken")
                    if not next_page_token:
                        break

            return videos
