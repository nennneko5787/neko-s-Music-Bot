import os
import asyncio

import discord
from discord.ext import commands
from contextlib import asynccontextmanager
from fastapi import FastAPI

if os.path.isfile(".env"):
    from dotenv import load_dotenv

    load_dotenv()

discord.utils.setup_logging()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="uwu#", intents=intents)


@bot.command(name="reload")
async def reloadExtention(ctx: commands.Context, extension: str):
    if ctx.author.id != 1048448686914551879:
        await ctx.reply(
            "お前はnennneko5787ではない、では一体誰なのだろうか", delete_after=5
        )
        return
    await bot.reload_extension(extension)
    await ctx.reply(f"reloaded {extension}")


@bot.command(name="sync")
async def commandSync(ctx: commands.Context):
    if ctx.author.id != 1048448686914551879:
        await ctx.reply(
            "お前はnennneko5787ではない、では一体誰なのだろうか", delete_after=5
        )
        return
    await bot.tree.sync()
    await ctx.reply(f"synced commands")


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.music")


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game("Musics"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    token = os.getenv("discord")
    asyncio.create_task(bot.start(token))
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return {
        "detail": "ok",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=10000)
