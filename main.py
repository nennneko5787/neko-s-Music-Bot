import asyncio
import logging
import os
import sys

import discord
import dotenv
from discord.ext import commands

dotenv.load_dotenv()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

intents = discord.Intents.none()
intents.guilds = True
intents.voice_states = True


bot = commands.Bot(
    "music#",
    intents=intents,
    member_cache_flags=discord.MemberCacheFlags.none(),
    max_message=None,
)

level = logging.INFO
handler = logging.StreamHandler()
if isinstance(handler, logging.StreamHandler) and discord.utils.stream_supports_colour(
    handler.stream
):
    formatter = discord.utils._ColourFormatter()
else:
    dt_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(
        "[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{"
    )
_log = logging.getLogger("music")
handler.setFormatter(formatter)
_log.setLevel(level)
_log.addHandler(handler)


@bot.event
async def on_ready():
    _log.info(f"Logined as {bot.user.name}")


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.ping")
    await bot.load_extension("cogs.help")
    await bot.tree.sync()


if __name__ == "__main__":
    bot.run(os.getenv("discord"))
