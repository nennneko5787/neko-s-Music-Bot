import discord
from discord import app_commands
from discord.ext import tasks
import os
from keep_alive import keep_alive
import asyncio
from yt_dlp import YoutubeDL
import ffmpeg
from collections import defaultdict, deque
import logging

queue_dict = defaultdict(deque)
isPlaying_dict = defaultdict(bool)

intents = discord.Intents.default()
intents.voice_states = True
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
	del queue_dict[interaction.guild.id]
	isPlaying_dict[voice_client.guild.id] = False
	await voice_client.disconnect()
	await interaction.response.send_message(f"ボイスチャンネル「<#{voice_client.channel.id}>」にから切断しました。")

@client.event
async def on_voice_state_update(member, before, after):
	if member.id == client.user.id:
		if after == None:
			del queue_dict[interaction.guild.id]
			isPlaying_dict[voice_client.guild.id] = False

def videodownloader(url: str, svid: int):
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
		info_dict = ydl.extract_info(url, download=False)
		video_title = info_dict.get('title', None)
		return video_title


async def playbgm(voice_client,queue):
	if len(queue) == 0:
		await voice_client.channel.send(f"キューに入っている曲はありません")
		isPlaying_dict[voice_client.guild.id] = False
		return
	elif voice_client.is_connected() == False:
		await voice_client.channel.send(f"ボイスチャンネルからの接続が切れていることがわかりました")
		isPlaying_dict[voice_client.guild.id] = False
		return
	if(os.path.isfile(f"{voice_client.guild.id}.mp3")):
		os.remove(f"{voice_client.guild.id}.mp3")
	url = queue.popleft()
	loop = asyncio.get_event_loop()
	logging.info("ダウンロードを開始")
	await voice_client.channel.send(f"ダウンロード中: **{url}**")
	dlow = loop.run_in_executor(None, videodownloader, url,voice_client.guild.id)
	title = await dlow
	loop.close()
	logging.info("再生")
	voice_client.play(discord.FFmpegPCMAudio(f"{voice_client.guild.id}.mp3"), after=lambda e:playbgm(voice_client, queue))
	await voice_client.channel.send(f"再生: **{title}**")


@tree.command(name="play", description="音楽を再生します")
async def play(interaction: discord.Interaction, url:str):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		if interaction.user.voice is None:
			await interaction.user.voice.channel.connect()
			await interaction.channel.send(f"ボイスチャンネル「<#{interaction.user.voice.channel.id}>」に接続しました。")
	queue = queue_dict[interaction.guild.id]
	queue.append(url)
	await interaction.response.send_message("曲をキューに挿入しました。")
	if isPlaying_dict[voice_client.guild.id] != True:
		isPlaying_dict[voice_client.guild.id] = True
		await interaction.channel.send("曲の再生を開始します。")
		await playbgm(voice_client,queue)

@tree.command(name="stop", description="音楽を停止します")
async def stop(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	del queue_dict[interaction.guild.id]
	isPlaying_dict[voice_client.guild.id] = False
	voice_client.stop()
	await interaction.response.send_message("停止しました")


@tree.command(name="skip", description="曲を一曲スキップします")
async def skip(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	voice_client.stop()
	queue = queue_dict[interaction.guild.id]
	await playbgm(voice_client,queue)
	await interaction.response.send_message("一曲スキップしました")


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
		name=f"{len(client.guilds)}サーバーで稼働中"))

TOKEN = os.getenv("DISCORD_TOKEN")
# Web サーバの立ち上げ
keep_alive()
client.run(TOKEN)
