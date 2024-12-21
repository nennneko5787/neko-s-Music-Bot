import discord
from discord import app_commands
from discord.ext import commands


class HelpCog(commands.Cog):
    __slots__ = ("bot",)

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="help", description="neko's Music Botの使い方を確認します。"
    )
    async def pingCommand(self, interaction: discord.Interaction):
        embed = (
            discord.Embed(
                title="neko's Music Botの使い方",
                description="バグが発生した・使い方がわからない・再生できない動画がある場合は、[サポートサーバー](https://discord.gg/2TfFUuY3RG)へ報告をお願いします。",
                color=discord.Colour.purple(),
            )
            .add_field(
                name="/play",
                value="指定された動画・曲のURLをボイスチャンネルで再生します。\nボリュームを指定することもできます。\nボイスチャンネルに接続してから実行する必要があります。",
            )
            .add_field(
                name="/search youtube",
                value="Youtubeの動画・曲を指定されたキーワードで検索します。\nボリュームを指定することもできます。\nボイスチャンネルに接続してから実行する必要があります。",
            )
            .add_field(
                name="/alarm",
                value="指定された時間まで待ってから、動画・曲をボイスチャンネルで再生します。\nボリュームを指定することもできます。\nボイスチャンネルに接続してから実行する必要があります。",
            )
            .add_field(
                name="/ping",
                value="ボットのレイテンシー(Bot/Voice)やCPU・メモリ使用率を確認することができます。",
            )
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
