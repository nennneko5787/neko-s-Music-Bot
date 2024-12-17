import psutil
import discord
from discord.ext import commands
from discord import app_commands


class PingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="ping", description="ボットのレイテンシーやCPU・メモリ状況を確認します。"
    )
    async def pingCommand(self, interaction: discord.Interaction):
        ping = self.bot.latency
        cpu_percent = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        embed = discord.Embed(
            title="Ping",
            description=f"Ping : {ping*1000}ms\nCPU : {cpu_percent}%\nMemory : {mem.percent}%",
            color=discord.Colour.purple(),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(PingCog(bot))
