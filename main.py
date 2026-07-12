import logging
import os
import traceback

import discord
from discord import app_commands

from objects.bot import MusicBot
from objects.exceptions import MusicCommandError, NoGuildError
from services import adService
from services.env import getEnv

# SPEC #32: emojis intent は使っていない(guild emoji イベント未購読)。prefix は
# app_commands 中心のため decorative。当たり障りの無い値だけ残しておく。
intents = discord.Intents.none()
intents.guilds = True
intents.voice_states = True


bot = MusicBot(
    command_prefix="music!",  # app_commands 中心。プレフィックス系コマンドは未使用。
    intents=intents,
    member_cache_flags=discord.MemberCacheFlags.none(),
    max_messages=None,
)

# SPEC #11: discord.utils.setup_logging は _ColourFormatter を内部で使うパブリック API。
# root=True で "music" ロガーにも色付きハンドラが伝播する。lavalink のログもここに乗る。
discord.utils.setup_logging(level=logging.INFO, root=True)
_log = logging.getLogger("music")


@bot.event
async def on_ready():
    if not bot.user:
        return

    _log.info(f"Logined as {bot.user.name}")


async def onTreeError(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    send = (
        interaction.followup.send
        if interaction.response.is_done()
        else interaction.response.send_message
    )

    if isinstance(error, app_commands.CommandOnCooldown):
        await send(
            f"コマンドはクールダウン中です。 **{error.retry_after:.2f}** 秒後にお試しください。",
            ephemeral=True,
        )
        return
    elif isinstance(error, app_commands.MissingPermissions):
        await send(
            "あなたにはこのコマンドを実行する権限がありません。", ephemeral=True
        )
        return
    # SPEC #9: 独自 NoGuildError と discord.py 標準 app_commands.NoPrivateMessage を両方拾う。
    elif isinstance(error, (NoGuildError, app_commands.NoPrivateMessage)):
        await send(
            "このコマンドはこのチャンネルでは実行できません。", ephemeral=True
        )
        return
    elif isinstance(error, MusicCommandError):
        # createPlayer から投げられるユーザー向けメッセージ。exc 文字列がそのままメッセージ。
        await send(str(error), ephemeral=True)
        return
    else:
        # SPEC #27: 例外の生テキストをユーザーへ返すと内部情報の漏えい面がある。
        # 詳細はログのみに残し、ユーザーには汎用メッセージを返す。
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


bot.tree.on_error = onTreeError


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.ping")
    await bot.load_extension("cogs.help")

    # SPEC_FEATURE_ADS §5.1: config/ads/*.json を 1 度読み込む。ホットリロード非対応。
    adService.loadAds()

    # SPEC #20: tree.sync を毎起動実行すると、クラッシュ再起動ループで global sync 連打 → 429。
    # コマンド定義変更時のみ手動で行うため、環境変数 SYNC_COMMANDS=1 のときだけ実行。
    if os.getenv("SYNC_COMMANDS") == "1":
        _log.info("Syncing application commands (SYNC_COMMANDS=1)")
        await bot.tree.sync()


if __name__ == "__main__":
    bot.run(getEnv("discord"))
