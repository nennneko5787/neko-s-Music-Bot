import discord
from discord import app_commands
from discord.ext import tasks
import os
from keep_alive import keep_alive
import asyncio
from yt_dlp import YoutubeDL
from niconico import NicoNico
import ffmpeg

nicoclient = NicoNico()
client = discord.Client(intents=discord.Intents.default())
tree = discord.app_commands.CommandTree(client) #←ココ

@client.event
async def on_ready():
	print('ログインしました')
	await tree.sync()  #スラッシュコマンドを同期
	myLoop.start()

@tree.command(name="join", description="neko's Music Botをボイスチャンネルに接続します")
async def join(interaction: discord.Interaction):
	if interaction.user.voice is None:
		await interaction.response.send_message("あなたはボイスチャンネルに接続していません。",ephemeral=True)
		return
	# ボイスチャンネルに接続する
	await interaction.user.voice.channel.connect()
	await interaction.response.send_message(f"ボイスチャンネル「<#{interaction.user.voice.channel.id}>」に接続しました。")

@tree.command(name="leave", description="neko's Music Botをボイスチャンネルから切断します")
async def leave(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	await voice_client.disconnect()
	await interaction.response.send_message(f"ボイスチャンネル「<#{voice_client.channel.id}>」にから切断しました。")

def ytdl(url: str, svid: int):
	ydl_opts = {
		"outtmpl": f"{svid}",
		"format": "mp3/bestaudio/best",
		"postprocessors": [
			{
				"key": "FFmpegExtractAudio",
				"preferredcodec": "mp3",
			}
		],
	}
	with YoutubeDL(ydl_opts) as ydl:
		ydl.download([url])


def ncdl(url: str, svid: int):
	with nicoclient.video.get_video(url) as video:
		video.download(f"{video.video.id}.mp4")
		print("dl com")
		# 入力 
		stream = ffmpeg.input(f"{video.video.id}.mp4") 
		# 出力 
		stream = ffmpeg.output(stream, f"{svid}.mp3") 
		# 実行
		ffmpeg.run(stream)
		print("ok")


@tree.command(name="play", description="音楽を再生します")
@discord.app_commands.choices(
    platform=[
        discord.app_commands.Choice(name="Youtube",value="Youtube"),
        discord.app_commands.Choice(name="Niconico",value="Niconico")
    ]
)
async def play(interaction: discord.Interaction, url:str, platform: str):
	await interaction.response.defer()
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	if(os.path.isfile(f"{interaction.guild.id}.mp3")):
		os.remove(f"{interaction.guild.id}.mp3")
	loop = asyncio.get_event_loop()
	if platform == "Youtube":
		await loop.run_in_executor(None, ytdl, url,interaction.guild.id)
	elif platform == "Niconico":
		await loop.run_in_executor(None, ncdl, url,interaction.guild.id)
	voice_client.play(discord.FFmpegPCMAudio(f"{interaction.guild.id}.mp3"))
	await interaction.followup.send("再生中")


@tree.command(name="stop", description="音楽を停止します")
async def stop(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	voice_client.stop()
	os.remove(f"{interaction.guild.id}.mp3")
	await interaction.response.send_message("停止しました")


@tree.command(name="pause", description="音楽を一時停止します")
async def pause(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	voice_client.pause()
	await interaction.response.send_message("停止しました")


@tree.command(name="resume", description="一時停止した音楽を再開します")
async def resume(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	voice_client.resume()
	await interaction.response.send_message("再開しました")


@tasks.loop(seconds=20)  # repeat after every 10 seconds
async def myLoop():
	# work
	await client.change_presence(activity=discord.Game(
		name="起動中."))

TOKEN = os.getenv("DISCORD_TOKEN")
# Web サーバの立ち上げ
keep_alive()
client.run(TOKEN)
