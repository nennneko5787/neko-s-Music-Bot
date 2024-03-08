import discord
from discord.ext import tasks
import os
from keep_alive import keep_alive
import asyncio
from yt_dlp import YoutubeDL
from collections import defaultdict
import lmp3ing
import traceback
import datetime
import aiohttp
from discord.app_commands import locale_str
from translate import MyTranslator
import copy

last_commit_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
last_commit_date = last_commit_dt.strftime('%Y/%m/%d %H:%M:%S')

queue_dict = defaultdict(asyncio.Queue)
isPlaying_dict = defaultdict(lambda: False)
nowPlaying_dict = defaultdict(lambda: "None")

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
client = discord.Client(intents=discord.Intents.default())
tree = discord.app_commands.CommandTree(client) #←ココ

@client.event
async def setup_hook():
	print('ログインしました')
	await tree.set_translator(MyTranslator())
	await tree.sync()  #スラッシュコマンドを同期
	
@client.event
async def on_ready():
	myLoop.start()

@client.event
async def on_voice_state_update(member, before, after):
	if member.id == client.user.id:
		if after == None:
			flag = member.guild.id in queue_dict
			if flag:
				del queue_dict[member.guild.id]
				isPlaying_dict[member.guild.id] = False

async def videodownloader(url: str):
	ydl_opts = {
		"format": "bestaudio/best",
		"noplaylist": True,
	}
	loop = asyncio.get_event_loop()
	ydl = YoutubeDL(ydl_opts)
	info_dict = await asyncio.to_thread(lambda: ydl.extract_info(url, download=False))
	return info_dict
	
async def nicodl(url: str):
	ydl_opts = {
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
	info_dict = await asyncio.to_thread(lambda: ydl.extract_info(url, download=False))
	if os.path.isfile(f"{info_dict.get('id', None)}.mp3") != True:
		await asyncio.to_thread(lambda: ydl.download([url]))
		print("download successful!")
	# 必要な情報を取り出す処理を追加
	return {
		'title': info_dict.get('title', None),
		'url': info_dict.get('url', None),
		'webpage_url': info_dict.get('webpage_url', None),
		'id': info_dict.get('id', None)
	}

async def playbgm(voice_client, channel, language, dqueue: asyncio.Queue = None):
	queue = dqueue if dqueue else queue_dict.get(voice_client.guild.id)
	if voice_client.guild.id in nowPlaying_dict:
		del nowPlaying_dict[f"{voice_client.guild.id}"]
	if not queue or queue.qsize() == 0:
		await handle_empty_queue(voice_client, channel, language)
		return
	if not voice_client.is_connected():
		await handle_voice_disconnection(voice_client, channel, language)
		return

	url = await queue.get()
	await handle_download_and_play(url, voice_client, channel, language)

async def handle_empty_queue(voice_client, channel, language):
	embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("No songs in queue"),language),color=discord.Colour.red())
	await channel.send(embed=embed)
	isPlaying_dict[voice_client.guild.id] = False
	await voice_client.disconnect()
	embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("Disconnected from voice channel."),language),
						  color=discord.Colour.red())
	embed.add_field(name=await MyTranslator().translate(locale_str("Disconnected channel"),language), value=voice_client.channel.jump_url)
	await channel.send("", embed=embed)

async def handle_voice_disconnection(voice_client, channel, language):
	embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("Disconnected from voice channel."),language),
						  color=discord.Colour.red())
	await channel.send("", embed=embed)
	isPlaying_dict[voice_client.guild.id] = False

async def handle_download_and_play(url, voice_client, channel, language):
	lmp3ing.info("ダウンロードを開始")
	embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("Waiting for song playback"),language), color=0xda70d6)
	embed.add_field(name="url", value=url)
	await channel.send("", embed=embed)
	loop = asyncio.get_event_loop()

	if url.find("nicovideo.jp") == -1:
		info_dict = await videodownloader(url)
		lmp3ing.info("再生")
		FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
		video_title = info_dict.get('title', None)
		videourl = info_dict.get('url', None)
		web = info_dict.get('webpage_url', None)
		source = await discord.FFmpegOpusAudio.from_probe(videourl, **FFMPEG_OPTIONS)
	else:
		embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("*Nico Nico Douga videos take a little time to play. Please understand."),language),
							  color=0xda70d6)
		await channel.send("", embed=embed)
		info_dict = await nicodl(url)
		video_title = info_dict.get('title', None)
		web = info_dict.get('webpage_url', None)
		id = info_dict.get('id', None)
		source = discord.FFmpegPCMAudio(f"{id}.mp3")

	nowPlaying_dict[f"{voice_client.guild.id}"] = info_dict.get('webpage_url', None)
	await asyncio.to_thread(voice_client.play, source, after=lambda e: loop.create_task(playbgm(voice_client, channel, language)))
	embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("Playing"),language), color=0xda70d6)
	embed.add_field(name=await MyTranslator().translate(locale_str("Video title"),language), value=video_title)
	embed.add_field(name=await MyTranslator().translate(locale_str("Video URL"),language), value=web)
	await channel.send("", embed=embed)

@tree.command(name="play", description=locale_str('Plays the music specified by url. If music is already being played, it is inserted into the cue.'))
async def play(interaction: discord.Interaction, url:str):
	await musicPlayFunction(interaction, url)

@tree.command(name="yplay", description=locale_str('It is the same as the play command, except that it searches Youtube for the specified words.'))
async def yplay(interaction: discord.Interaction, search:str):
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
					description=await MyTranslator().translate(locale_str('Connected to voice channel.'),interaction.locale),
					color=0xda70d6
				).add_field(
					name=await MyTranslator().translate(locale_str('Destination Channel'),interaction.locale),
					value=f"<#{interaction.user.voice.channel.id}>"
				)
			)
			voice_client = interaction.guild.voice_client
		else:
			await interaction.response.send_message(
				embed=discord.Embed(
					title="neko's Music Bot",
					description=await MyTranslator().translate(locale_str("You are not currently connecting to any voice channel."),interaction.locale),
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
	default_msg = "Rest assured, the error log has been sent automatically to the developer. The error log has been automatically sent to the developer. \nIf you need a support, please join the [support server](https://discord.gg/PN3KWEnYzX). \nThe following is a traceback of the ```python\n{traceback}\n```"
	msg = await interaction.translate(locale_str(
		default_msg,
		fmt_arg={
			'traceback' : traceback.format_exc(), 
		},
	))
	embed = discord.Embed(title=await MyTranslator().translate(locale_str("Error!"),interaction.locale), description=msg)
	await interaction.channel.send(embed=embed)

	# ボイスチャンネルから切断する
	await voice_client.disconnect()

	# エラーログをDiscordのWebhookに送信する
	async with aiohttp.ClientSession() as session:
		webhook = discord.Webhook.from_url(os.getenv("errorlog_webhook"), session=session)
		embed = discord.Embed("<@&1130083364116897862>",title="エラーログが届きました！", description=f"{interaction.guild.name}(ID: {interaction.guild.id})っていうサーバーでエラーが発生しました。\n以下、トレースバックです。```python\n{traceback.format_exc()}\n```")
		await webhook.send(embed=embed)


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
	dic = await asyncio.to_thread(lambda: ydl.extract_info(url, download=False))
	flag = "entries" in dic

	if flag:
		entries_count = len(dic['entries'])
		if entries_count <= 1:
			responsed = True
		for info_dict in dic['entries']:
			await queue.put(info_dict.get('webpage_url'))
			await asyncio.sleep(0)
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
	dic = await asyncio.to_thread(lambda: ydl.extract_info(url, download=False))
	flag = "entries" in dic

	if flag:
		for info_dict in dic['entries']:
			await queue.put(info_dict.get('webpage_url'))
			await asyncio.sleep(0)
	else:
		await queue.put(dic.get('webpage_url'))

	responsed = await send_music_inserted_message(dic, interaction, responsed)

	if not isPlaying_dict[interaction.guild.id]:
		isPlaying_dict[interaction.guild.id] = True
		await interaction.channel.send(
			embed=discord.Embed(
				title="neko's Music Bot",
				description=await MyTranslator().translate(locale_str("Starts playing the song."),interaction.locale),
				color=0xda70d6
			)
		)
		await playbgm(voice_client, interaction.channel, interaction.locale, queue)


async def send_music_inserted_message(dic, interaction, responsed):
	if 'entries' in dic:
		entries_count = len(dic['entries'])
		default_msg = '{entries_count} songs inserted into the queue.'
		description = await interaction.translate(locale_str(
			default_msg,
			fmt_arg={
				'entries_count' : entries_count, 
			},
		))
	else:
		description = await MyTranslator().translate(locale_str("Song inserted into the queue.",),interaction.locale)

	embed = discord.Embed(
		title="neko's Music Bot",
		description=description,
		color=0xda70d6
	).add_field(
		name=await MyTranslator().translate(locale_str("Video title"),interaction.locale),
		value=dic.get('title')
	).add_field(
		name=await MyTranslator().translate(locale_str("Video URL"),interaction.locale),
		value=dic.get('webpage_url')
	)

	if responsed == False:
		await interaction.followup.send(embed=embed)  # ここでresponsedがTrueの場合はinteraction.followup.send()を呼び出す
		responsed = True
	else:
		await interaction.channel.send(embed=embed)
	return responsed


@tree.command(name="stop", description=locale_str("Stops the music currently playing and discards the cue."))
async def stop(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("neko's Music Bot is not connected to the voice channel."),interaction.locale),color=discord.Colour.red())
		await interaction.response.send_message("",embed=embed,ephemeral=True)
		return
	if isPlaying_dict[interaction.guild.id] == True:
		del queue_dict[interaction.guild.id]
		isPlaying_dict[interaction.guild.id] = False
		voice_client.stop()
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("The song was stopped and the queue was discarded."),interaction.locale),color=0xda70d6)
		await interaction.response.send_message("",embed=embed)
	else:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("The song does not seem to be playing."),interaction.locale),color=0xda70d6)
		await interaction.response.send_message("",embed=embed)

@tree.command(name="skip", description=locale_str("Skips the currently playing music and plays the next music in the queue."))
async def skip(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("neko's Music Bot is not connected to the voice channel."),interaction.locale),color=discord.Colour.red())
		await interaction.response.send_message("",embed=embed,ephemeral=True)
		return
	embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("Skipped one song."),interaction.locale),color=0xda70d6)
	await interaction.response.send_message("",embed=embed)
	voice_client.stop()
	await playbgm(voice_client)

@tree.command(name="pause", description=locale_str("Pause the song."))
async def pause(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("neko's Music Bot is not connected to the voice channel."),interaction.locale),color=discord.Colour.red())
		await interaction.response.send_message("",embed=embed,ephemeral=True)
		return
	voice_client.pause()
	embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("Song paused."),interaction.locale),color=0xda70d6)
	await interaction.response.send_message("",embed=embed)

@tree.command(name="resume", description=locale_str("Resume paused song."))
async def resume(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("neko's Music Bot is not connected to the voice channel."),interaction.locale),color=discord.Colour.red())
		await interaction.response.send_message("",embed=embed,ephemeral=True)
		return
	voice_client.resume()
	embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("Resumed songs that had been paused."),interaction.locale),color=0xda70d6)
	await interaction.response.send_message("",embed=embed)

@tree.command(name="queue", description=locale_str("You can check the songs in the queue."))
async def queue(interaction: discord.Interaction):
	if interaction.guild.id in queue_dict:
		await interaction.response.defer()
		q = copy.deepcopy(queue_dict[interaction.guild.id])
		length = q.qsize()
		if length == 0:
			embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("No songs in queue"),interaction.locale),color=discord.Colour.red())
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return
		qlist = []
		ydl_opts = {
			"outtmpl": f"{interaction.guild.id}",
			"format": "bestaudio/best",
			"noplaylist": False,
		}
		c = 1
		ydl = YoutubeDL(ydl_opts)
		if nowPlaying_dict[f"{interaction.guild.id}"] != "None":
			dic = await asyncio.to_thread(lambda: ydl.extract_info(nowPlaying_dict[f"{interaction.guild.id}"], download=False))
			qlist.append(f"**{await MyTranslator().translate(locale_str('Playing'),interaction.locale)}: **[{dic.get('title')}]({dic.get('webpage_url')})\n")
		# キューの中身を表示
		while not q.empty():
			item = await q.get()
			dic = await asyncio.to_thread(lambda: ydl.extract_info(item, download=False))
			qlist.append(f"#{c} [{dic.get('title')}]({dic.get('webpage_url')})")
			c = c + 1
			await asyncio.sleep(0)
		embed = discord.Embed(title="neko's Music Bot", description="\n".join(qlist), color=discord.Colour.purple())
		await interaction.followup.send(embed=embed)
	else:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("No songs in queue"),interaction.locale),color=discord.Colour.red())
		await interaction.response.send_message(embed=embed, ephemeral=True)
		return

@tree.command(name="help", description=locale_str("You can check the available commands."))
async def help(interaction: discord.Interaction):
	await interaction.response.defer()
	embed = discord.Embed(title="neko's Music Bot",description="",color=0xda70d6)
	for command in tree.get_commands(type=discord.AppCommandType.chat_input):
		params = []
		for parameter in command.parameters:
			params.append(f"**{parameter.locale_name}**: <{parameter.type}>")
			await asyncio.sleep(0)
		p = ', '.join(params)
		embed.add_field(name=f"/{command.name} {p}",value=await MyTranslator().translate(locale_str(command.description),interaction.locale))
		await asyncio.sleep(0)
	# embed.add_field(name="/play **url**:<video>",value="urlで指定された音楽を再生します。すでに音楽が再生されている場合はキューに挿入します。")
	await interaction.followup.send("",embed=embed)

@tasks.loop(seconds=20)  # repeat after every 20 seconds
async def myLoop():
	# work
	vccount = 0
	for guild in client.guilds:
		if guild.voice_client != None:
			vccount += 1
		await asyncio.sleep(0)
	await client.change_presence(activity=discord.Game(
		name=f"/help | {len(client.guilds)} SERVERS | {vccount} VOICE CHANNELS | deployed: {last_commit_date}"))

TOKEN = os.getenv("DISCORD_TOKEN")
# Web サーバの立ち上げ(シン・クラウド for FreeのCronを噛ませる)
keep_alive()
client.run(TOKEN)
