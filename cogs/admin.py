import discord
from discord.ext import commands

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    @commands.command(name="guild")
    async def guildCommand(self, ctx: commands.Context, guildId: int):
        guild = await self.bot.fetch_guild(guildId)
        await ctx.reply(guild.name)
        
async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))