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
	myLoop.start()

@tree.command(name="join", description="neko's Music Botをボイスチャンネルに接続します")
async def join(interaction: discord.Interaction):
	if interaction.user.voice is None:
		await interaction.response.send_message("あなたはボイスチャンネルに接続していません。",ephemeral=True)
		return
	# ボイスチャンネルに接続する
	await interaction.user.voice.channel.connect()
	await interaction.response.send_message(f"ボイスチャンネル「{interaction.user.voice.channel.name}」に接続しました。")

@tree.command(name="leave", description="neko's Music Botをボイスチャンネルから切断します")
async def join(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	await voice_client.disconnect()
	await interaction.response.send_message(f"ボイスチャンネル「{voice_client.channel.name}」にから切断しました。")

	
@tasks.loop(seconds=20)  # repeat after every 10 seconds
async def myLoop():
	# work
	await client.change_presence(activity=discord.Game(
		name="☕猫の喫茶店でメイドとして勤務中 / https://discord.gg/aEEt8FgYBb"))
	await tree.sync()  #スラッシュコマンドを同期

TOKEN = os.getenv("DISCORD_TOKEN")
# Web サーバの立ち上げ
keep_alive()
client.run(TOKEN)
