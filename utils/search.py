import asyncio
from concurrent.futures import ProcessPoolExecutor

import httpx
from yt_dlp import YoutubeDL

_client = httpx.AsyncClient()


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


async def getNicoNicoVideo(contentId: str):
    response = await _client.get(
        f"https://www.nicovideo.jp/watch/{contentId}?responseType=json"
    )
    jsonData = response.json()
    if jsonData["data"]["response"]["owner"] is None:
        nickname = "削除済みユーザー"
    else:
        nickname = jsonData["data"]["response"]["owner"]["nickname"]
    return {
        "uploader": nickname,
        "url": f"https://www.nicovideo.jp/watch/{contentId}",
        "title": jsonData["data"]["response"]["video"]["title"],
    }


async def searchNicoNico(keyword: str, *, n: int = 20) -> list[dict]:
    response = await _client.get(
        f"https://snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search?q={keyword}&targets=title,description,tags&fields=contentId&_sort=viewCounter&_offset=0&_limit={n}&_context=neko-s-Music-Bot"
    )
    responseData = response.json()
    tasks = [getNicoNicoVideo(item["contentId"]) for item in responseData["data"]]
    return await asyncio.gather(*tasks)
