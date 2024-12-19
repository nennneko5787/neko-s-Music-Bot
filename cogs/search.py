import asyncio
from concurrent.futures import ProcessPoolExecutor

from yt_dlp import YoutubeDL


class SearchFailed(Exception):
    pass


def _searchYoutube(keyword: str, n: int = 20) -> list[dict]:
    try:
        ydlOpts = {
            "quiet": True,
            "extract_flat": True,
            "cookiefile": "./cookies.txt",
        }
        with YoutubeDL(ydlOpts) as ydl:
            info = ydl.sanitize_info(
                ydl.extract_info(f"ytsearch{n}:{keyword}", download=False)
            )
        if "entries" in info and len(info["entries"]) > 1:
            infos = [entry for entry in info["entries"]]
            return infos
        else:
            return [info]
    except Exception as e:
        raise SearchFailed(f"Failed to search video: {keyword}, {str(e)}")


async def searchYoutube(keyword: str, *, n: int = 20) -> list[dict]:
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as executor:
        return await loop.run_in_executor(executor, _searchYoutube, keyword, n)
