import os

import discord
import dotenv
from discord.ext import commands

dotenv.load_dotenv()

intents = discord.Intents.none()
intents.guilds = True
intents.voice_states = True


class MusicBot(commands.Bot):
    async def cleanup(self):
        for guild in self.guilds:
            if guild.voice_client != None:
                embed = discord.Embed(
                    title="neko's Music Bot",
                    description="ボットが再起動するため、ボイスチャンネルから切断します。 / The bot disconnects from the voice channel to restart.",
                    color=discord.Colour.red(),
                )
                await guild.voice_client.channel.send(embed=embed)
                await guild.voice_client.disconnect()


bot = commands.Bot(
    "music#",
    intents=intents,
    member_cache_flags=discord.MemberCacheFlags.none(),
    max_message=None,
    chunk_guilds_at_startup=False,
)


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.music")
    # await bot.tree.sync()


bot.run(os.getenv("discord"))
