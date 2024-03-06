import discord
from discord import app_commands
from discord.ext import tasks
import os
from keep_alive import keep_alive
import asyncio
from yt_dlp import YoutubeDL
import ffmpeg
from collections import defaultdict
import logging
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
import datetime

last_commit_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
last_commit_date = last_commit_dt.strftime('%Y/%m/%d %H:%M:%S')

queue_dict = defaultdict(asyncio.Queue)
isPlaying_dict = defaultdict(lambda: False)

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
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
		"format": "ogg/bestaudio/best",
		"noplaylist": True,
		"postprocessors": [
			{
				"key": "FFmpegExtractAudio",
				"preferredcodec": "ogg",
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

async def playbgm(voice_client, channel, dqueue: asyncio.Queue = None):
	queue = dqueue if dqueue else queue_dict.get(voice_client.guild.id)
	if not queue or queue.qsize() == 0:
		await handle_empty_queue(voice_client, channel)
		return
	if not voice_client.is_connected():
		await handle_voice_disconnection(voice_client, channel)
		return

	url = await queue.get()
	await handle_download_and_play(url, voice_client, channel)

async def handle_empty_queue(voice_client, channel):
	await channel.send("キューに入っている曲はありません")
	isPlaying_dict[voice_client.guild.id] = False
	await voice_client.disconnect()
	embed = discord.Embed(title="neko's Music Bot", description="ボイスチャンネルから切断しました。",
						  color=discord.Colour.red())
	embed.add_field(name="切断先チャンネル", value=voice_client.channel.jump_url)
	await channel.send("", embed=embed)

async def handle_voice_disconnection(voice_client, channel):
	embed = discord.Embed(title="neko's Music Bot", description="ボイスチャンネルからの接続が切れています",
						  color=discord.Colour.red())
	await channel.send("", embed=embed)
	isPlaying_dict[voice_client.guild.id] = False

async def handle_download_and_play(url, voice_client, channel):
	logging.info("ダウンロードを開始")
	embed = discord.Embed(title="neko's Music Bot", description="再生を待機中", color=0xda70d6)
	embed.add_field(name="url", value=url)
	await channel.send("", embed=embed)
	loop = asyncio.get_event_loop()

	if url.find("nicovideo.jp") == -1:
		info_dict = await videodownloader(url, voice_client.guild.id)
		logging.info("再生")
		FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
		video_title = info_dict.get('title', None)
		videourl = info_dict.get('url', None)
		web = info_dict.get('webpage_url', None)
		source = await discord.FFmpegOpusAudio.from_probe(videourl, **FFMPEG_OPTIONS)
	else:
		embed = discord.Embed(title="neko's Music Bot", description="※ニコニコ動画の動画は再生に少し時間がかかります。ご了承ください。",
							  color=0xda70d6)
		await channel.send("", embed=embed)
		info_dict = await nicodl(url, voice_client.guild.id)
		video_title = info_dict.get('title', None)
		web = info_dict.get('webpage_url', None)
		source = discord.FFmpegPCMAudio(f"{voice_client.guild.id}.ogg")

	voice_client.play(source, after=lambda e: loop.create_task(playbgm(voice_client, channel)))
	embed = discord.Embed(title="neko's Music Bot", description="再生中", color=0xda70d6)
	embed.add_field(name="title", value=video_title)
	embed.add_field(name="url", value=web)
	await channel.send("", embed=embed)

@tree.command(name="play", description="urlで指定された音楽を再生します。すでに音楽が再生されている場合はキューに挿入します。")
async def play(interaction: discord.Interaction, url:str):
	await musicPlayFunction(interaction, url)

@tree.command(name="yplay", description="searchで指定されたワードを検索し、ヒットした音楽を再生します。すでに音楽が再生されている場合はキューに挿入します。")
async def play(interaction: discord.Interaction, search:str):
	await musicPlayFunction(interaction, f"ytsearch:{search}")

async def musicPlayFunction(interaction: discord.Interaction, url: str):
	voice_client = interaction.guild.voice_client
	responsed = False

	if voice_client is None:
		if interaction.user.voice is not None:
			isPlaying_dict[interaction.guild.id] = False
			await interaction.user.voice.channel.connect()
			responsed = True
			await interaction.response.send_message(
				embed=discord.Embed(
					title="neko's Music Bot",
					description="ボイスチャンネルに接続しました。",
					color=0xda70d6
				).add_field(
					name="接続先チャンネル",
					value=f"<#{interaction.user.voice.channel.id}>"
				)
			)
			voice_client = interaction.guild.voice_client
		else:
			await interaction.response.send_message(
				embed=discord.Embed(
					title="neko's Music Bot",
					description="あなたはボイスチャンネルに接続していません。",
					color=discord.Colour.red()
				),
				ephemeral=True
			)
			return

	if isPlaying_dict[interaction.guild.id]:
		await handle_queue_entry(url, interaction, responsed)
		return

	try:
		await handle_music_entry(url, interaction, responsed, voice_client)
	except Exception as e:
		await handle_error(e, interaction, voice_client)

async def handle_error(error, interaction, voice_client):
	# エラーメッセージを表示する
	embed = discord.Embed(title="エラーが発生しました。", description=f"安心してください。エラーログは開発者に自動的に送信されました。\nサポートが必要な場合は、[サポートサーバー](https://discord.gg/PN3KWEnYzX) に参加してください。\n以下、トレースバックです。```python\n{traceback.format_exc()}\n```")
	await interaction.channel.send(embed=embed)

	# エラーログをDiscordのWebhookに送信する
	async with aiohttp.ClientSession() as session:
		webhook = discord.Webhook.from_url(os.getenv("errorlog_webhook"), session=session)
	embed = discord.Embed("<@&1130083364116897862>",title="エラーログが届きました！", description=f"{interaction.guild.name}(ID: {interaction.guild.id})っていうサーバーでエラーが発生しました。\n以下、トレースバックです。```python\n{traceback.format_exc()}\n```")
	await webhook.send(embed=embed)

	# ボイスチャンネルから切断する
	await voice_client.disconnect()


async def handle_queue_entry(url, interaction, responsed):
	queue = queue_dict[interaction.guild.id]
	loop = asyncio.get_event_loop()
	ydl_opts = {
		"outtmpl": f"{interaction.guild.id}",
		"format": "bestaudio/best",
		"noplaylist": False,
	}
	await interaction.response.defer()
	ydl = YoutubeDL(ydl_opts)
	dic = await loop.run_in_executor(ThreadPoolExecutor(), lambda: ydl.extract_info(url, download=False))
	flag = "entries" in dic

	if flag:
		entries_count = len(dic['entries'])
		if entries_count <= 1
			responsed = True
		for info_dict in dic['entries']:
			await queue.put(info_dict.get('webpage_url'))
	else:
		await queue.put(dic.get('webpage_url'))

	responsed = await send_music_inserted_message(dic, interaction, responsed)


async def handle_music_entry(url, interaction, responsed, voice_client):
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

	if flag:
		for info_dict in dic['entries']:
			await queue.put(info_dict.get('webpage_url'))
	else:
		await queue.put(dic.get('webpage_url'))

	responsed = await send_music_inserted_message(dic, interaction, responsed)

	if not isPlaying_dict[interaction.guild.id]:
		isPlaying_dict[interaction.guild.id] = True
		await interaction.channel.send(
			embed=discord.Embed(
				title="neko's Music Bot",
				description="再生を開始します。",
				color=0xda70d6
			)
		)
		await playbgm(voice_client, interaction.channel, queue)


async def send_music_inserted_message(dic, interaction, responsed):
	if 'entries' in dic:
		entries_count = len(dic['entries'])
		description = f"{entries_count}個の音楽をキューに挿入しました。"
	else:
		description = "曲をキューに挿入しました。"

	embed = discord.Embed(
		title="neko's Music Bot",
		description=description,
		color=0xda70d6
	).add_field(
		name="タイトル",
		value=dic.get('title')
	).add_field(
		name="動画URL",
		value=dic.get('webpage_url')
	)

	if responsed == False:
		await interaction.followup.send(embed=embed)  # ここでresponsedがTrueの場合はinteraction.followup.send()を呼び出す
		responsed = True
	else:
		await interaction.channel.send(embed=embed)
	return responsed


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
	embed.add_field(name="/yplay **search**:<text>",value="searchで指定されたワードを検索し、ヒットした音楽を再生します。すでに音楽が再生されている場合はキューに挿入します。")
	embed.add_field(name="/pause",value="一時停止します。")
	embed.add_field(name="/resume",value="一時停止した音楽を再開します。")
	embed.add_field(name="/skip",value="今再生している音楽をスキップして、キューに入っている次の音楽を再生します。")
	embed.add_field(name="/stop",value="今再生している音楽を停止して、キューを破棄します。")
	embed.add_field(name="/help",value="使用できるコマンドを確認することができます。")
	await interaction.response.send_message("",embed=embed)

@tasks.loop(seconds=20)  # repeat after every 20 seconds
async def myLoop():
	# work
	vccount = 0
	for guild in client.guilds:
		if guild.voice_client != None:
			vccount += 1
	await client.change_presence(activity=discord.Game(
		name=f"/help | {len(client.guilds)}サーバーで稼働中 | {vccount}個のボイスチャンネルに接続中 | deployed: {last_commit_date}"))

TOKEN = os.getenv("DISCORD_TOKEN")
# Web サーバの立ち上げ(uptimerobotを噛ませる)
keep_alive()
client.run(TOKEN)
