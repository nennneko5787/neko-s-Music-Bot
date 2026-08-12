import discord
from discord import app_commands
from discord.ext import commands

from objects.bot import MusicBot


class HelpCog(commands.Cog):
    __slots__ = ("bot",)

    def __init__(self, bot: MusicBot):
        self.bot = bot

    @app_commands.command(name="support", description="サポートサーバーへのリンクを表示します。")
    async def supportCommand(self, interaction: discord.Interaction):
        await interaction.response.send_message("https://discord.gg/PN3KWEnYzX", ephemeral=True)

    @app_commands.command(name="help", description="neko's Music Botの使い方を確認します。")
    async def helpCommand(self, interaction: discord.Interaction):
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
                name="/toggle",
                value="曲の一時停止・再開を切り替えます。",
                inline=False,
            )
            .add_field(
                name="/stop",
                value="曲の再生を停止し、ボイスチャンネルから切断します。",
                inline=False,
            )
            .add_field(
                name="/loop",
                value="ループしない・1曲ループ・キュー内ループを切り替えます。",
                inline=False,
            )
            .add_field(
                name="/volume",
                value="曲の音量を 0〜100 の範囲で変更します。",
                inline=False,
            )
            .add_field(
                name="/timescale",
                value="曲の再生速度とピッチを 0.1〜2.0 の範囲で変更します。",
                inline=False,
            )
            .add_field(
                name="/ping",
                value="ボットのレイテンシー(Bot/Voice)やCPU・メモリ使用率を確認することができます。",
                inline=False,
            )
        )
        assert self.bot.user is not None  # ログイン完了後にしか到達しない
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: MusicBot):
    await bot.add_cog(HelpCog(bot))
