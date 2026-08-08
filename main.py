import logging
import os
import traceback

import discord
from discord import app_commands

from objects.bot import MusicBot
from objects.exceptions import MusicCommandError, NoGuildError
from services import adService
from services.env import getEnv

# SPEC #32: 購読しないイベントの intent は落とす。
intents = discord.Intents.none()
intents.guilds = True
intents.voice_states = True


bot = MusicBot(
    command_prefix="music!",  # 未使用。app_commands 中心。
    intents=intents,
    member_cache_flags=discord.MemberCacheFlags.none(),
    max_messages=None,
)

# SPEC #11: root=True で music / lavalink のログも同じハンドラに乗せる。
discord.utils.setup_logging(level=logging.INFO, root=True)
_log = logging.getLogger("music")


@bot.event
async def on_ready():
    if not bot.user:
        return

    _log.info(f"Logined as {bot.user.name}")


async def onTreeError(interaction: discord.Interaction, error: app_commands.AppCommandError):
    send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message

    if isinstance(error, app_commands.CommandOnCooldown):
        await send(
            f"コマンドはクールダウン中です。 **{error.retry_after:.2f}** 秒後にお試しください。",
            ephemeral=True,
        )
        return
    elif isinstance(error, app_commands.MissingPermissions):
        await send("あなたにはこのコマンドを実行する権限がありません。", ephemeral=True)
        return
    # SPEC #9: 独自例外と discord.py 標準例外を両方拾う。
    elif isinstance(error, (NoGuildError, app_commands.NoPrivateMessage)):
        await send("このコマンドはこのチャンネルでは実行できません。", ephemeral=True)
        return
    elif isinstance(error, MusicCommandError):
        # exc 文字列がそのままユーザー向けメッセージ。
        await send(str(error), ephemeral=True)
        return
    else:
        # SPEC #27: 詳細はログだけに残し、ユーザーには汎用メッセージを返す。
        traceback.print_exception(error)

        await send(
            embed=discord.Embed(
                title="エラーが発生しました！",
                description=(
                    "予期せぬエラーが発生しました。しばらくしてもう一度お試しください。\n"
                    "問題が続く場合は [サポートサーバー](https://discord.gg/PN3KWEnYzX) までご連絡ください。"
                ),
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )


bot.tree.on_error = onTreeError  # ty: ignore[invalid-assignment]


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.ping")
    await bot.load_extension("cogs.help")

    # SPEC_FEATURE_ADS §5.1: 起動時に 1 度だけ読み込む(ホットリロード非対応)。
    adService.loadAds()

    # SPEC #20: 毎起動 sync すると再起動ループで 429 になるため env で明示したときだけ。
    if os.getenv("SYNC_COMMANDS") == "1":
        _log.info("Syncing application commands (SYNC_COMMANDS=1)")
        await bot.tree.sync()


if __name__ == "__main__":
    # log_handler=None: 省略すると discord.py 側でもハンドラが付き discord.* のログが二重になる。
    bot.run(getEnv("discord"), log_handler=None)
