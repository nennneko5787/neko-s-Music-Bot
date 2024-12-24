import discord
import psutil
from discord import app_commands
from discord.ext import commands


class PingCog(commands.Cog):
    __slots__ = ("bot",)

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="ping", description="ボットのレイテンシーやCPU・メモリ状況を確認します。"
    )
    async def pingCommand(self, interaction: discord.Interaction):
        ping = self.bot.latency

        _count = 0
        _totalPing = 0
        voicePing = 0
        for voiceClient in self.bot.voice_clients:
            voiceClient: discord.VoiceClient = voiceClient
            _totalPing += voiceClient.average_latency
            _count += 1
        if _count != 0:
            voicePing = _totalPing / _count
        else:
            voicePing = 0

        cpu_percent = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        embed = discord.Embed(
            title="Ping",
            description=f"(Client)Ping : `{int(ping*1000)}ms`\n(VoiceClient, Average)Ping: `{int(voicePing*1000)}ms`\nCPU : `{cpu_percent}%`\nMemory : `{mem.percent}%`",
            color=discord.Colour.purple(),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(PingCog(bot))
