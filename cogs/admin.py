import discord
from discord.ext import commands

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    @commands.command(name="guild")
    async def guildCommand(self, ctx: commands.Context, channelId: int):
        guild = self.bot.get_channel(channelId)
        await ctx.reply(channel.guild.name)
        
async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))