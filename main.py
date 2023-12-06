import discord
from discord import app_commands
from discord.ext import tasks
import os
from keep_alive import keep_alive
import asyncio

client = discord.Client(intents=discord.Intents.default())
tree = discord.app_commands.CommandTree(client) #←ココ

@client.event
async def on_ready():
    print('ログインしました')
    await tree.sync()  #スラッシュコマンドを同期
    myLoop.start()

@tree.command(name="join", description="ボイスチャンネルに参加します")
async def join(interaction: discord.Interaction, text: str):
    await interaction.response.send_message("?")
@tasks.loop(seconds=20)  # repeat after every 10 seconds
async def myLoop():
  # work
  await client.change_presence(activity=discord.Game(
    name="☕猫の喫茶店でメイドとして勤務中 / https://discord.gg/aEEt8FgYBb"))

TOKEN = os.getenv("DISCORD_TOKEN")
# Web サーバの立ち上げ
keep_alive()
client.run(TOKEN)
