from typing import cast

import discord
import psutil
from discord import app_commands
from discord.ext import commands

from objects.bot import MusicBot
from objects.client import LavalinkVoiceClient
from objects.player import MusicPlayer


class PingCog(commands.Cog):
    __slots__ = ("bot",)

    def __init__(self, bot: MusicBot):
        self.bot = bot

    @app_commands.command(name="ping", description="ボットのレイテンシーやCPU・メモリ状況を確認します。")
    async def pingCommand(self, interaction: discord.Interaction):
        ping = self.bot.latency

        _count = 0
        _totalPing = 0

        for voiceClient in self.bot.voice_clients:
            player = cast(MusicPlayer | None, cast(LavalinkVoiceClient, voiceClient).player)
            if player is None:
                continue  # connect() 完了前(SPEC Phase 5 §4)
            # SPEC #31: 未接続時の ping = -1 センチネルを除外する。
            if player.ping < 0:
                continue
            _totalPing += player.ping
            _count += 1
        voicePing = int(_totalPing / _count) if _count != 0 else 0

        cpuPercent = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        embed = discord.Embed(
            title="Ping",
            description=(
                f"(Client)Ping : `{int(ping * 1000)}ms`\n"
                f"(VoiceClient, Average)Ping: `{voicePing}ms`\n"
                f"CPU : `{cpuPercent}%`\n"
                f"Memory : `{mem.percent}%`"
            ),
            color=discord.Colour.purple(),
        )
        assert self.bot.user is not None
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)


async def setup(bot: MusicBot):
    await bot.add_cog(PingCog(bot))
