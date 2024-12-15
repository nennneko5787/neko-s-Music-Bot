import discord
from discord.ext import commands

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))