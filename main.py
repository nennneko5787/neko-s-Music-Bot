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
import traceback

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
	flag = interaction.guild.id in queue_dict
	if flag:
		del queue_dict[interaction.guild.id]
		isPlaying_dict[voice_client.guild.id] = False
	await voice_client.disconnect()
	await interaction.response.send_message(f"ボイスチャンネル「<#{voice_client.channel.id}>」から切断しました。")

@client.event
async def on_voice_state_update(member, before, after):
	if member.id == client.user.id:
		if after == None:
			flag = member.guild.id in queue_dict
			if flag:
				del queue_dict[member.guild.id]
				isPlaying_dict[member.guild.id] = False

def videodownloader(url: str, svid: int):
	ydl_opts = {
		"outtmpl": f"{svid}",
		"format": "bestaudio/best",
		"noplaylist": True,
	}
	with YoutubeDL(ydl_opts) as ydl:
		#ydl.download([url])
		info_dict = ydl.extract_info(url, download=False)
		return info_dict


async def playbgm(voice_client,queue):
	try:
		if len(queue) == 0 or not queue:
			await voice_client.channel.send(f"キューに入っている曲はありません")
			isPlaying_dict[voice_client.guild.id] = False
			return
		elif voice_client.is_connected() == False:
			await voice_client.channel.send(f"ボイスチャンネルからの接続が切れています")
			isPlaying_dict[voice_client.guild.id] = False
			return
		if(os.path.isfile(f"{voice_client.guild.id}.mp3")):
			os.remove(f"{voice_client.guild.id}.mp3")
		url = queue.popleft()
		logging.info("ダウンロードを開始")
		await voice_client.channel.send(f"再生待機中: **{url}**")
		info_dict = videodownloader(url,voice_client.guild.id)
		logging.info("再生")
		#voice_client.play(discord.FFmpegPCMAudio(f"{voice_client.guild.id}.mp3"), after=lambda e:playbgm(voice_client, queue))
		FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
		video_title = info_dict.get('title', None)
		videourl = info_dict.get('url', None)
		source = await discord.FFmpegOpusAudio.from_probe(videourl, **FFMPEG_OPTIONS)
		voice_client.play(source, after=lambda e:skipsong(voice_client.guild.id, queue))
		await voice_client.channel.send(f"再生: **{video_title}**")
	except:
		await voice_client.channel.send(f"エラーが発生しました。以下のエラーを https://github.com/nennneko5787/neko-s-Music-Bot/issues/new にてお知らせください。\n```{}```")
		return
	

async def skipsong(svid,voice_client):
	if voice_client.is_playing == True:
		voice_client.stop()
	queue = queue_dict[svid]
	await playbgm(voice_client,queue)


@tree.command(name="play", description="音楽を再生します")
async def play(interaction: discord.Interaction, url:str):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		if interaction.user.voice != None:
			await interaction.user.voice.channel.connect()
			await interaction.channel.send(f"ボイスチャンネル「<#{interaction.user.voice.channel.id}>」に接続しました。")
		else:
			await interaction.response.send_message(f"あなたはボイスチャンネルに接続していません。",ephemeral=True)
			return
	queue = queue_dict[interaction.guild.id]
	queue.append(url)
	await interaction.response.send_message(f"曲( {url} )をキューに挿入しました。")
	if isPlaying_dict[voice_client.guild.id] != True:
		isPlaying_dict[voice_client.guild.id] = True
		await interaction.channel.send("再生を開始します。")
		await playbgm(voice_client,queue)

@tree.command(name="stop", description="音楽を停止します")
async def stop(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	flag = interaction.guild.id in queue_dict
	if flag:
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
	await interaction.response.send_message("一曲スキップしました")
	await skipsong(interaction.guild.id,voice_client)


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
