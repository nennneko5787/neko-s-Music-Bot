import discord


class CommandInvokeError(discord.app_commands.AppCommandError):
    pass


class NoPrivateMessage(discord.app_commands.AppCommandError):
    pass
