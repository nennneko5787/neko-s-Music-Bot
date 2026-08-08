import discord


class MusicCommandError(discord.app_commands.AppCommandError):
    """ユーザーに直接メッセージとして返したい実行時エラー。"""


class NoGuildError(discord.app_commands.AppCommandError):
    """ギルド外(DM 等)から呼ばれたときに投げる独自の例外。"""
