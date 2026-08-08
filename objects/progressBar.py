import logging

import discord

# 絵文字を取得できなかった場合のフォールバック(SPEC_REFACTOR_PR8.md §3.4)。
_FALLBACK: dict[str, str] = {
    "bar": "━",
    "circle": "●",
    "graybar": "─",
}

_emojis: dict[str, str] = dict(_FALLBACK)


async def loadEmojis(bot: discord.Client) -> None:
    """
    bar / circle / graybar を取得して保持する。SPEC #13: on_ready から 1 度だけ呼ぶ。
    取得できなかった名前は _FALLBACK のまま残し、警告を出す。
    """
    fetched = {emoji.name: str(emoji) for emoji in await bot.fetch_application_emojis()}

    missing = [name for name in _FALLBACK if name not in fetched]
    _emojis.update({name: fetched[name] for name in _FALLBACK if name in fetched})

    if missing:
        logging.getLogger("music").warning(
            "アプリケーション絵文字が見つかりません: %s (フォールバック文字で描画します)",
            ", ".join(missing),
        )


def progressBar(percentage: float, length: int = 14, *, showCircle: bool = False) -> str:
    """
    percentage(0.0〜1.0)を length 文字のバーに描画する。
    showCircle=True で現在位置に circle(つまみ)を置く(再生バー用)。
    SPEC #28: どの分岐でも戻り値はちょうど length 文字になる。
    """
    if percentage >= 1.0:
        return _emojis["bar"] * length

    if not showCircle:
        if percentage <= 0.0:
            return _emojis["graybar"] * length
        filled = int(length * percentage)
        return _emojis["bar"] * filled + _emojis["graybar"] * (length - filled)

    if percentage <= 0.0:
        return _emojis["circle"] + _emojis["graybar"] * (length - 1)
    # percentage < 1.0 なので filled <= length-1。circle の 1 文字分は必ず収まる。
    filled = int(length * percentage)
    return _emojis["bar"] * filled + _emojis["circle"] + _emojis["graybar"] * (length - filled - 1)
