import discord
from discord import app_commands
from discord.ext import commands

from objects.bot import MusicBot


class HelpCog(commands.Cog):
    __slots__ = ("bot",)

    def __init__(self, bot: MusicBot):
        self.bot = bot

    @app_commands.command(
        name="help", description="neko's Music Botの使い方を確認します。"
    )
    async def pingCommand(self, interaction: discord.Interaction):
        embed = (
            discord.Embed(
                title="neko's Music Botの使い方",
                description="バグが発生した・使い方がわからない・再生できない動画がある場合は、[サポートサーバー](https://discord.gg/PN3KWEnYzX)へ報告をお願いします。",
                color=discord.Colour.purple(),
            )
            .add_field(
                name="/play",
                value="指定された動画・曲のURLをボイスチャンネルで再生します。ボイスチャンネルに接続してから実行する必要があります。",
                inline=False,
            )
            .add_field(
                name="/queue",
                value="キューに溜まっている動画・曲を確認します。",
                inline=False,
            )
            .add_field(
                name="/code",
                value="コードを入力し、サポーター限定特典を受け取ることができます。",
                inline=False,
            )
            .add_field(
                name="/ranking",
                value="サーバーで再生された動画・曲のランキングを確認します。(サポーター限定)",
                inline=False,
            )
            .add_field(
                name="/ping",
                value="ボットのレイテンシー(Bot/Voice)やCPU・メモリ使用率を確認することができます。",
                inline=False,
            )
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: MusicBot):
    await bot.add_cog(HelpCog(bot))
