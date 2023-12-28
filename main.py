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
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
import datetime

last_commit_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
last_commit_date = last_commit_dt.strftime('%Y/%m/%d %H:%M:%S')

queue_dict = defaultdict(deque)
isPlaying_dict = defaultdict(lambda: False)

intents = discord.Intents.default()
intents.voice_states = True
client = discord.Client(intents=discord.Intents.default())
tree = discord.app_commands.CommandTree(client) #←ココ

@client.event
async def on_ready():
	print('ログインしました')
	await tree.sync()  #スラッシュコマンドを同期
	myLoop.start()

@client.event
async def on_voice_state_update(member, before, after):
	if member.id == client.user.id:
		if after == None:
			flag = member.guild.id in queue_dict
			if flag:
				del queue_dict[member.guild.id]
				isPlaying_dict[member.guild.id] = False

async def videodownloader(url: str, svid: int):
	ydl_opts = {
		"outtmpl": f"{svid}",
		"format": "bestaudio/best",
		"noplaylist": True,
	}
	loop = asyncio.get_event_loop()
	ydl = YoutubeDL(ydl_opts)
	info_dict = await loop.run_in_executor(ThreadPoolExecutor(), lambda: ydl.extract_info(url, download=False))
	return info_dict
	
async def nicodl(url: str, svid: int):
	ydl_opts = {
		"outtmpl": f"{svid}",
		"format": "mp3/bestaudio/best",
		"noplaylist": True,
		"postprocessors": [
			{
				"key": "FFmpegExtractAudio",
				"preferredcodec": "mp3",
			}
		],
	}
	loop = asyncio.get_event_loop()
	ydl = YoutubeDL(ydl_opts)
	await loop.run_in_executor(ThreadPoolExecutor(), lambda: ydl.download([url]))
	info_dict = await loop.run_in_executor(ThreadPoolExecutor(), lambda: ydl.extract_info(url, download=False))
	print("download successful!")
	# 必要な情報を取り出す処理を追加
	return {
		'title': info_dict.get('title', None),
		'url': info_dict.get('url', None),
		'webpage_url': info_dict.get('webpage_url', None)
	}

async def playbgm(voice_client,dqueue:deque=None):
	if dqueue == None:
		queue = queue_dict[voice_client.guild.id]
	else:
		queue = dqueue
	if len(queue) == 0 or not queue:
		await voice_client.channel.send(f"キューに入っている曲はありません")
		isPlaying_dict[voice_client.guild.id] = False
		await voice_client.disconnect()
		embed = discord.Embed(title="neko's Music Bot",description="ボイスチャンネルから切断しました。",color=discord.Colour.red())
		embed.add_field(name="切断先チャンネル",value=f"<#{voice_client.channel.id}>")
		await voice_client.channel.send("",embed=embed)
		return
	elif voice_client.is_connected() == False:
		embed = discord.Embed(title="neko's Music Bot",description="ボイスチャンネルからの接続が切れています",color=discord.Colour.red())
		await voice_client.channel.send("",embed=embed)
		isPlaying_dict[voice_client.guild.id] = False
		return
	if(os.path.isfile(f"{voice_client.guild.id}.mp3")):
		os.remove(f"{voice_client.guild.id}.mp3")
	url = queue.popleft()
	logging.info("ダウンロードを開始")
	embed = discord.Embed(title="neko's Music Bot",description="再生を待機中",color=0xda70d6)
	embed.add_field(name="url",value=url)
	await voice_client.channel.send("",embed=embed)
	loop = asyncio.get_event_loop()
	# 修正後の playbgm 関数の一部
	if url.find("ytsearch:") != -1:
		dic = await videodownloader(url, voice_client.guild.id)
		logging.info("再生")
		FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
		info_dict = dic['entries'][0]
		video_title = info_dict.get('title', None)
		videourl = info_dict.get('url', None)
		source = await discord.FFmpegOpusAudio.from_probe(videourl, **FFMPEG_OPTIONS)
		voice_client.play(source, after=lambda e: loop.create_task(playbgm(voice_client)))
		embed = discord.Embed(title="neko's Music Bot",description="再生中",color=0xda70d6)
		embed.add_field(name="url",value=video_title)
		await voice_client.channel.send("",embed=embed)
	elif url.find("nicovideo.jp") == -1:
		info_dict = await videodownloader(url, voice_client.guild.id)
		logging.info("再生")
		FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
		video_title = info_dict.get('title', None)
		videourl = info_dict.get('url', None)
		web = info_dict.get('webpage_url', None)
		source = await discord.FFmpegOpusAudio.from_probe(videourl, **FFMPEG_OPTIONS)
		voice_client.play(source, after=lambda e: loop.create_task(playbgm(voice_client)))
		embed = discord.Embed(title="neko's Music Bot",description="再生中",color=0xda70d6)
		embed.add_field(name="title",value=video_title)
		embed.add_field(name="url",value=web)
		await voice_client.channel.send("",embed=embed)
	else:
		embed = discord.Embed(title="neko's Music Bot",description="※ニコニコ動画の動画は再生に少し時間がかかります。ご了承ください。",color=0xda70d6)
		await voice_client.channel.send("",embed=embed)
		info_dict = await nicodl(url, voice_client.guild.id)
		# info_dict = await loop.run_in_executor(executor,nicodl,url, voice_client.guild.id)
		video_title = info_dict.get('title', None)
		web = info_dict.get('webpage_url', None)
		source = discord.FFmpegPCMAudio(f"{voice_client.guild.id}.mp3")
		voice_client.play(source, after=lambda e: loop.create_task(playbgm(voice_client)))
		voice_client.play(source, after=lambda e: loop.create_task(playbgm(voice_client)))
		embed = discord.Embed(title="neko's Music Bot",description="再生中",color=0xda70d6)
		embed.add_field(name="title",value=video_title)
		embed.add_field(name="url",value=web)
		await voice_client.channel.send("",embed=embed)

@tree.command(name="play", description="urlで指定された音楽を再生します。すでに音楽が再生されている場合はキューに挿入します。")
async def play(interaction: discord.Interaction, url:str):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		if interaction.user.voice != None:
			isPlaying_dict[interaction.guild.id] = False
			await interaction.user.voice.channel.connect()
			embed = discord.Embed(title="neko's Music Bot",description="ボイスチャンネルに接続しました。",color=0xda70d6)
			embed.add_field(name="接続先チャンネル",value=f"<#{interaction.user.voice.channel.id}>")
			await interaction.response.send_message("",embed=embed)
			voice_client = interaction.guild.voice_client
		else:
			embed = discord.Embed(title="neko's Music Bot",description="あなたはボイスチャンネルに接続していません。",color=discord.Colour.red())
			await interaction.response.send_message("",embed=embed,ephemeral=True)
			return
	elif isPlaying_dict[interaction.guild.id] == True:
		queue = queue_dict[interaction.guild.id]
		loop = asyncio.get_event_loop()
		ydl_opts = {
			"outtmpl": f"{interaction.guild.id}",
			"format": "bestaudio/best",
			"noplaylist": False,
		}
		ydl = YoutubeDL(ydl_opts)
		dic = await loop.run_in_executor(ThreadPoolExecutor(), lambda: ydl.extract_info(url, download=False))
		flag = "entries" in dic
		if flag == True:
			await interaction.response.defer()
			count = 0
			for info_dict in dic['entries']:
				url = info_dict.get('webpage_url', None)
				queue.append(url)
				embed = discord.Embed(title="neko's Music Bot",description="曲をキューに挿入しました。",color=0xda70d6)
				embed.add_field(name="動画URL",value=url)
				await interaction.channel.send("",embed=embed)
				count += 1
			embed = discord.Embed(title="neko's Music Bot",description=f"{count}個の音楽をキューに挿入しました。",color=0xda70d6)
			await interaction.followup.send("",embed=embed)
		else:
				url = dic.get('webpage_url', None)
				queue.append(url)
				embed = discord.Embed(title="neko's Music Bot",description="曲をキューに挿入しました。",color=0xda70d6)
				embed.add_field(name="動画URL",value=url)
				await interaction.response.send_message("",embed=embed)
		return
	
	queue = queue_dict[interaction.guild.id]
	loop = asyncio.get_event_loop()
	ydl_opts = {
		"outtmpl": f"{interaction.guild.id}",
		"format": "bestaudio/best",
		"noplaylist": False,
	}
	ydl = YoutubeDL(ydl_opts)
	dic = await loop.run_in_executor(ThreadPoolExecutor(), lambda: ydl.extract_info(url, download=False))
	flag = "entries" in dic
	if flag == True:
		await interaction.response.defer()
		for info_dict in dic['entries']:
			url = info_dict.get('webpage_url', None)
			queue.append(url)
			embed = discord.Embed(title="neko's Music Bot",description="曲をキューに挿入しました。",color=0xda70d6)
			embed.add_field(name="動画URL",value=url)
			await interaction.channel.send("",embed=embed)
			count += 1
		embed = discord.Embed(title="neko's Music Bot",description=f"{count}個の音楽をキューに挿入しました。",color=0xda70d6)
		await interaction.followup.send("",embed=embed)
	else:
			url = dic.get('webpage_url', None)
			queue.append(url)
			embed = discord.Embed(title="neko's Music Bot",description="曲をキューに挿入しました。",color=0xda70d6)
			embed.add_field(name="動画URL",value=url)
			await interaction.response.send_message("",embed=embed)
	if isPlaying_dict[interaction.guild.id] != True:
		isPlaying_dict[interaction.guild.id] = True
		embed = discord.Embed(title="neko's Music Bot",description="再生を開始します。",color=0xda70d6)
		await interaction.channel.send("",embed=embed)
		await playbgm(voice_client,queue)
		return

@tree.command(name="stop", description="今再生している音楽を停止して、キューを破棄します。")
async def stop(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description="neko's Music Botはボイスチャンネルに接続していません。",color=discord.Colour.red())
		await interaction.response.send_message("",embed=embed,ephemeral=True)
		return
	if isPlaying_dict[interaction.guild.id] == True:
		del queue_dict[interaction.guild.id]
		isPlaying_dict[interaction.guild.id] = False
		voice_client.stop()
		embed = discord.Embed(title="neko's Music Bot",description="停止しました。",color=0xda70d6)
		await interaction.response.send_message("",embed=embed)
	else:
		embed = discord.Embed(title="neko's Music Bot",description="曲が再生されていないようです。",color=0xda70d6)
		await interaction.response.send_message("",embed=embed)

@tree.command(name="skip", description="今再生している音楽をスキップして、キューに入っている次の音楽を再生します。")
async def skip(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description="neko's Music Botはボイスチャンネルに接続していません。",color=discord.Colour.red())
		await interaction.response.send_message("",embed=embed,ephemeral=True)
		return
	embed = discord.Embed(title="neko's Music Bot",description="一曲スキップしました。",color=0xda70d6)
	await interaction.response.send_message("",embed=embed)
	voice_client.stop()
	await playbgm(voice_client)

@tree.command(name="pause", description="一時停止します。")
async def pause(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description="neko's Music Botはボイスチャンネルに接続していません。",color=discord.Colour.red())
		await interaction.response.send_message("",embed=embed,ephemeral=True)
		return
	voice_client.pause()
	embed = discord.Embed(title="neko's Music Bot",description="一時停止しました。",color=0xda70d6)
	await interaction.response.send_message("",embed=embed)

@tree.command(name="resume", description="一時停止した音楽を再開します。")
async def resume(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description="neko's Music Botはボイスチャンネルに接続していません。",color=discord.Colour.red())
		await interaction.response.send_message("",embed=embed,ephemeral=True)
		return
	voice_client.resume()
	embed = discord.Embed(title="neko's Music Bot",description="再開しました",color=0xda70d6)
	await interaction.response.send_message("",embed=embed)

@tree.command(name="help", description="使用できるコマンドを確認することができます。")
async def help(interaction: discord.Interaction):
	embed = discord.Embed(title="neko's Music Bot",description="",color=0xda70d6)
	embed.add_field(name="/play **url**:<video>",value="urlで指定された音楽を再生します。すでに音楽が再生されている場合はキューに挿入します。")
	embed.add_field(name="/pause",value="一時停止します。")
	embed.add_field(name="/resume",value="一時停止した音楽を再開します。")
	embed.add_field(name="/skip",value="今再生している音楽をスキップして、キューに入っている次の音楽を再生します。")
	embed.add_field(name="/stop",value="今再生している音楽を停止して、キューを破棄します。")
	embed.add_field(name="/help",value="使用できるコマンドを確認することができます。")
	await interaction.response.send_message("",embed=embed)

@tasks.loop(seconds=20)  # repeat after every 10 seconds
async def myLoop():
	# work
	await client.change_presence(activity=discord.Game(
		name=f"/help | deployed: {last_commit_date} | {len(client.guilds)}サーバーで稼働中"))

TOKEN = os.getenv("DISCORD_TOKEN")
# Web サーバの立ち上げ
keep_alive()
client.run(TOKEN)