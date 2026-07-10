import discord

# SPEC #9: 元の名前(CommandInvokeError / NoPrivateMessage)は discord.py 標準の
# app_commands.CommandInvokeError / app_commands.NoPrivateMessage と衝突していた。
# 別名にリネームし、handler 側で両方を捕捉するようにする。


class MusicCommandError(discord.app_commands.AppCommandError):
    """ユーザーに直接メッセージとして返したい実行時エラー。"""


class NoGuildError(discord.app_commands.AppCommandError):
    """ギルド外(DM 等)から呼ばれたときに投げる独自の例外。"""
