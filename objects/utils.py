import discord


async def resolveMemberMention(guild: discord.Guild, userId: int) -> str:
    """
    SPEC #15: 要求者が該当ギルドを抜けていても NotFound で落ちない mention 解決。
    1) キャッシュ 2) fetch_member 3) 失敗時は raw mention 文字列
       (Discord が表示側で "Unknown User" に変換する)。
    """
    member = guild.get_member(userId)
    if member is not None:
        return member.mention
    try:
        member = await guild.fetch_member(userId)
        return member.mention
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return f"<@{userId}>"


def formatTime(seconds):
    seconds = int(max(0, seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    # SPEC #28: 元の dd:hh:mm:ss は「日」の存在が字面から分かりづらいため "日" ラベルを付ける。
    if d > 0:
        return f"{d}日 {h:02}:{m:02}:{s:02}"
    elif h > 0:
        return f"{h:02}:{m:02}:{s:02}"
    else:
        return f"{m:02}:{s:02}"


def clamp(value: float | int, min_value: float | int, max_value: float | int):
    """
    指定した範囲内に数値を制限する関数。

    :param value: 制限したい数値
    :param min_value: 最小値
    :param max_value: 最大値
    :return: 制限された数値
    """
    return max(min_value, min(value, max_value))
