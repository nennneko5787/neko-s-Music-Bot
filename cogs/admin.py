import traceback

import discord
from discord.ext import commands


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="sync")
    async def syncCommand(self, ctx: commands.Context):
        if ctx.author.id != 1048448686914551879:
            return
        try:
            await self.bot.tree.sync()
            await ctx.reply("ok")
        except:
            traceback.print_exc()
            await ctx.reply("ng")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
