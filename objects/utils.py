import discord


async def resolveMemberMention(guild: discord.Guild, userId: int) -> str:
    """SPEC #15: 要求者がギルドを抜けていても落ちない mention 解決。"""
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
    # SPEC #28: 日は数値だけだと読み取れないため "日" ラベルを付ける。
    if d > 0:
        return f"{d}日 {h:02}:{m:02}:{s:02}"
    elif h > 0:
        return f"{h:02}:{m:02}:{s:02}"
    else:
        return f"{m:02}:{s:02}"


def clamp(value: float | int, min_value: float | int, max_value: float | int):
    return max(min_value, min(value, max_value))
