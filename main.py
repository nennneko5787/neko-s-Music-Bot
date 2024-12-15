import os

import discord
import dotenv
from discord.ext import commands

dotenv.load_dotenv()

intents = discord.Intents.default()


bot = commands.Bot(
    "music#",
    intents=intents,
    member_cache_flags=discord.MemberCacheFlags.none(),
    max_message=None,
)


@bot.event
async def on_ready():
    print("Logined as", bot.user.name)


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.admin")
    # await bot.tree.sync()


bot.run(os.getenv("discord"))
