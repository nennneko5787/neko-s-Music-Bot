import discord
from discord.ext import tasks
import os
from keep_alive import keep_alive
import asyncio
import yt_dlp
from yt_dlp import YoutubeDL
from collections import defaultdict, deque
import logging
import traceback
import datetime
import aiohttp
from discord.app_commands import locale_str
from translate import MyTranslator
import copy
import psutil
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import re
import random

class DiscordClient(discord.Client):
	async def cleanup(self):
		for guild in client.guilds:
			if guild.voice_client != None:
				embed = discord.Embed(title="neko's Music Bot",description="ボットが再起動するため、ボイスチャンネルから切断します。 / The bot disconnects from the voice channel to restart.",color=discord.Colour.red())
				await guild.voice_client.channel.send(embed=embed)
				await guild.voice_client.disconnect()
			await asyncio.sleep(0.01)

	async def close(self):
		await self.cleanup()
		await super().close()

last_commit_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
last_commit_date = last_commit_dt.strftime('%Y/%m/%d %H:%M:%S')

queue_dict = defaultdict(deque)
isConnecting_dict = defaultdict(lambda: False)
isPlaying_dict = defaultdict(lambda: False)
nowPlaying_dict = defaultdict(lambda: {"title": None})

intents = discord.Intents.none()
intents.guilds = True
intents.voice_states = True
client = DiscordClient(intents=intents, member_cache_flags=discord.MemberCacheFlags.none(), max_message=None, chunk_guilds_at_startup=False)
tree = discord.app_commands.CommandTree(client) #←ココ

client_credentials_manager = SpotifyClientCredentials(os.getenv("spotify_clientid"), os.getenv("spotify_client_secret"))
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

languages = {
	discord.Locale.japanese: "ja-JP",
	discord.Locale.korean: "ko-KR",
	discord.Locale.chinese: "zh-CN",
	discord.Locale.taiwan_chinese: "zh-TW",
	discord.Locale.american_english: "en-US",
	discord.Locale.british_english: "en-GB",
	discord.Locale.ukrainian: "uk-UA",
	discord.Locale.russian: "ru-RU",
}

languages2 = {
	discord.Locale.japanese: "ja",
	discord.Locale.korean: "ko",
	discord.Locale.chinese: "zh-CN",
	discord.Locale.taiwan_chinese: "zh-TW",
	discord.Locale.american_english: "en-US",
	discord.Locale.british_english: "en-GB",
	discord.Locale.ukrainian: "uk",
	discord.Locale.russian: "ru",
}

YOUTUBE_DISABLED = False

@client.event
async def setup_hook():
	await tree.set_translator(MyTranslator())
	await tree.sync()  #スラッシュコマンドを同期
	
@client.event
async def on_ready():
	print(f'{client.user}にログインしました')
	myLoop.start()
	if "Develop" in client.user.name:
		global YOUTUBE_DISABLED
		YOUTUBE_DISABLED = False

@client.event
async def on_voice_state_update(member, before, after):
	if member.id == client.user.id:
		if after is None:
			flag = member.guild.id in queue_dict
			if flag:
				del queue_dict[member.guild.id]
				isPlaying_dict[member.guild.id] = False
				isConnecting_dict[member.guild.id] = False

async def videodownloader(url: str):
	ydl_opts = {
		"format": "bestaudio/best",
		"noplaylist": True,
	}
	ydl = YoutubeDL(ydl_opts)
	info_dict = await asyncio.to_thread(lambda: ydl.extract_info(url, download=False))
	return info_dict
	
async def nicodl(url: str, id: str):
	ydl_opts = {
		"outtmpl": "%(id)s",
		"format": "mp3/bestaudio/best",
		"noplaylist": True,
		"postprocessors": [
			{
				"key": "FFmpegExtractAudio",
				"preferredcodec": "mp3",
			}
		],
	}
	ydl = YoutubeDL(ydl_opts)
	if os.path.isfile(f"{id}.mp3") != True:
		await asyncio.to_thread(lambda: ydl.download([url]))
		print("download successful!")
	# 必要な情報を取り出す処理を追加
	return True

async def playbgm(voice_client, channel, language, dqueue: asyncio.Queue = None):
	queue = dqueue if dqueue else queue_dict.get(voice_client.guild.id)
	if voice_client.guild.id in nowPlaying_dict:
		nowPlaying_dict[f"{voice_client.guild.id}"] = {"title": None}
	if not queue or len(queue) == 0:
		await handle_empty_queue(voice_client, channel, language)
		return
	elif not voice_client.is_connected():
		await handle_voice_disconnection(voice_client, channel, language)
		return

	item = queue.popleft()
	await handle_download_and_play(item, voice_client, channel, language)

async def handle_empty_queue(voice_client, channel, language):
	embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("No songs in queue"),language),color=discord.Colour.red())
	await channel.send(embed=embed)
	isPlaying_dict[voice_client.guild.id] = False
	await voice_client.disconnect()
	isConnecting_dict[voice_client.guild.id] = False
	embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("Disconnected from voice channel."),language),
						  color=discord.Colour.red())
	embed.add_field(name=await MyTranslator().translate(locale_str("Disconnected channel"),language), value=voice_client.channel.jump_url)
	await channel.send(embed=embed)
	return

async def handle_voice_disconnection(voice_client, channel, language):
	embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("Disconnected from voice channel."),language),
						  color=discord.Colour.red())
	await channel.send(embed=embed)
	isPlaying_dict[voice_client.guild.id] = False
	isConnecting_dict[voice_client.guild.id] = False
	return

async def handle_download_and_play(item, voice_client, channel, language):
	logging.info("ダウンロードを開始")
	url = item.get("url")
	weburl = item.get("webpage_url")
	title = item.get("title")
	thumbnail = item.get("thumbnail")
	embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("Waiting for song playback"),language), color=discord.Colour.purple())
	await channel.send(embed=embed)
	
	if url.find("nicovideo.jp") == -1:
		FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
		source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
	else:
		embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("*Nico Nico Douga videos take a little time to play. Please understand."),language),
							  color=discord.Colour.purple())
		await channel.send(embed=embed)
		id = item.get("id")
		await nicodl(weburl, id)
		source = discord.FFmpegPCMAudio(f"{id}.mp3")

	nowPlaying_dict[f"{voice_client.guild.id}"] = item
	loop = asyncio.get_event_loop()
	await asyncio.to_thread(voice_client.play, source, after=lambda e: loop.create_task(playbgm(voice_client, channel, language)))
	embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("Playing"),language), color=discord.Colour.purple())
	embed.add_field(name=await MyTranslator().translate(locale_str("title"),language), value=title)
	embed.add_field(name="URL", value=weburl)
	embed.set_image(url=thumbnail)
	await channel.send(embed=embed)

@tree.command(name="play", description=locale_str('Plays the music specified by url. If music is already being played, it is inserted into the cue.'))
@discord.app_commands.guild_only()
async def play(interaction: discord.Interaction, url:str, shuffle_the_queue_if_playlist: bool = False):
	global YOUTUBE_DISABLED
	if YOUTUBE_DISABLED:
		if "youtube.com" in url:
			embed=discord.Embed(
				title="neko's Music Bot",
				description=await MyTranslator().translate(locale_str('The feature to play Youtube songs has been disabled.'),interaction.locale),
				color=discord.Colour.from_rgb(255,0,0)
			),
			await interaction.response.send_message(embed=embed,ephemeral=True)
			return
	await asyncio.create_task(musicPlayFunction(interaction, url, shuffle_the_queue_if_playlist))

@tree.command(name="yplay", description=locale_str('It is the same as the play command, except that it searches Youtube for the specified words.'))
@discord.app_commands.guild_only()
async def yplay(interaction: discord.Interaction, search:str):
	global YOUTUBE_DISABLED
	if YOUTUBE_DISABLED:
		embed=discord.Embed(
			title="neko's Music Bot",
			description=await MyTranslator().translate(locale_str('The feature to play Youtube songs has been disabled.'),interaction.locale),
			color=discord.Colour.from_rgb(255,0,0)
		),
		await interaction.response.send_message(embed=embed,ephemeral=True)
		return
	await asyncio.create_task(musicPlayFunction(interaction, f"ytsearch:{search}", False))

async def musicPlayFunction(interaction: discord.Interaction, url: str, shuffle_the_queue_if_playlist: bool):
	voice_client = interaction.guild.voice_client
	responsed = False

	await interaction.response.defer(ephemeral=True)

	if voice_client is None and isConnecting_dict[interaction.guild.id] == False:
		if interaction.user.voice is not None:
			isPlaying_dict[interaction.guild.id] = False
			await interaction.user.voice.channel.connect()
			isConnecting_dict[interaction.guild.id] = True
			await interaction.followup.send(
				embed=discord.Embed(
					title="neko's Music Bot",
					description=await MyTranslator().translate(locale_str('Connected to voice channel.'),interaction.locale),
					color=discord.Colour.purple()
				).add_field(
					name=await MyTranslator().translate(locale_str('Destination Channel'),interaction.locale),
					value=f"<#{interaction.user.voice.channel.id}>"
				),
				ephemeral=False
			)
			voice_client = interaction.guild.voice_client
		else:
			await interaction.followup.send(
				embed=discord.Embed(
					title="neko's Music Bot",
					description=await MyTranslator().translate(locale_str("You are not currently connecting to any voice channel."),interaction.locale),
					color=discord.Colour.red()
				),
				ephemeral=True
			)
			return
	else:
		await interaction.followup.send(
			embed=discord.Embed(
				title="neko's Music Bot",
				description=await MyTranslator().translate(locale_str('Operation accepted. Please wait a moment...'),interaction.locale),
				color=discord.Colour.purple()
			),
			ephemeral=False
		)

	if isPlaying_dict[interaction.guild.id]:
		await handle_queue_entry(url, interaction, shuffle_the_queue_if_playlist)
		return

	await interaction.channel.send("https://i.imgur.com/bnNP1Ih.png")

	try:
		await handle_music_entry(url, interaction, voice_client, shuffle_the_queue_if_playlist)
	except yt_dlp.utils.DownloadError:
		error = traceback.format_exc()
		if "ERROR: Unsupported URL: " in error:
			embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("That URL is not supported."),interaction.locale),color=discord.Colour.red())
			await interaction.channel.send(embed=embed)
		elif "This video is not available" in error:
			embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("That video is not available."),interaction.locale),color=discord.Colour.red())
			await interaction.channel.send(embed=embed)
		else:
			await handle_error(interaction, voice_client, error)
	except Exception:
		await handle_error(interaction, voice_client)

async def handle_error(interaction, voice_client, error = None):
	# エラーメッセージを表示する
	default_msg = "Rest assured, the error log has been sent automatically to the developer. The error log has been automatically sent to the developer. \nIf you need a support, please join the [support server](https://discord.gg/PN3KWEnYzX). \nThe following is a traceback of the ```python\n{traceback}\n```"
	msg = await interaction.translate(locale_str(
		default_msg,
		fmt_arg={
			'traceback' : traceback.format_exc() if error is None else error, 
		},
	))
	embed = discord.Embed(title=await MyTranslator().translate(locale_str("Error!"),interaction.locale), description=msg)
	await interaction.channel.send(embed=embed)

	# ボイスチャンネルから切断する
	if voice_client:
		await voice_client.disconnect()
		isConnecting_dict[interaction.guild.id] = False

	# エラーログをDiscordのWebhookに送信する
	async with aiohttp.ClientSession() as session:
		webhook = discord.Webhook.from_url(os.getenv("errorlog_webhook"), session=session)
		embed = discord.Embed(
			title="エラーログが届きました！",
			description=f"{interaction.guild.name}(ID: {interaction.guild.id})っていうサーバーでエラーが発生しました。\n以下、トレースバックです。```python\n{traceback.format_exc()}\n```"
		)
		await webhook.send(embed=embed)

async def handle_music(url, interaction, voice_client=None, shuffle_the_queue_if_playlist=False):
	queue = queue_dict[interaction.guild.id]
	match = re.search(r'/track/([^/?]+)', url)

	isSpotify = False

	if match:
		track_id = match.group(1)
		result = await asyncio.to_thread(sp.track, f"spotify:track:{track_id}")
		url = f"ytsearch: {result['name']}"
		isSpotify = True

	lang = languages.get(interaction.locale,"en-US")
	langg = languages2.get(interaction.locale,"en-US")

	ydl_opts = {
		"outtmpl": "%(id)s",
		"format": "bestaudio/best",
		"noplaylist": False,
	}

	"""
	Can't work
	ydl_opts = {
		"outtmpl": "%(id)s",
		"format": "bestaudio/best",
		"noplaylist": False,
		'extractor_args': {
			'youtube': {
				'lang': langg
			}
		},
		'headers': {
			'Accept-Language': lang
		},
	}
	"""

	ydl = YoutubeDL(ydl_opts)
	
	dic = await asyncio.to_thread(lambda: ydl.extract_info(url, download=False))
	flag = "entries" in dic

	if flag:
		for info_dict in dic['entries']:
			queue.append({
				"webpage_url": info_dict.get('webpage_url') if not isSpotify else f"https://open.spotify.com/track/{result['id']}",
				"url": info_dict.get('url'),
				"title": info_dict.get('title') if not isSpotify else result['name'],
				"id": info_dict.get('id') if not isSpotify else result['id'],
				"thumbnail": info_dict.get('thumbnail') if not isSpotify else None,
			})
			await asyncio.sleep(0.01)
		if shuffle_the_queue_if_playlist is True:
			random.shuffle(queue)
	else:
		queue.append({
			"webpage_url": dic.get('webpage_url') if not isSpotify else f"https://open.spotify.com/track/{result['id']}",
			"url": dic.get('url'),
			"title": dic.get('title') if not isSpotify else result['name'],
			"id": dic.get('id') if not isSpotify else result['id'],
			"thumbnail": dic.get('thumbnail') if not isSpotify else None,
		})

	await send_music_inserted_message(dic, interaction)

	if voice_client and not isPlaying_dict[interaction.guild.id]:
		isPlaying_dict[interaction.guild.id] = True
		await interaction.channel.send(
			embed=discord.Embed(
				title="neko's Music Bot",
				description=await MyTranslator().translate(locale_str("Starts playing the song."),interaction.locale),
				color=discord.Colour.purple()
			)
		)
		await asyncio.create_task(playbgm(voice_client, interaction.channel, interaction.locale, queue))

async def handle_queue_entry(url, interaction, shuffle_the_queue_if_playlist):
	return await handle_music(url, interaction,shuffle_the_queue_if_playlist)

async def handle_music_entry(url, interaction, voice_client,shuffle_the_queue_if_playlist):
	return await handle_music(url, interaction, voice_client,shuffle_the_queue_if_playlist)

async def send_music_inserted_message(dic, interaction):
	if 'entries' in dic:
		entries_count = len(dic['entries'])
		if entries_count == 1:
			default_msg = '{entries_count} songs inserted into the '
			description = await interaction.translate(locale_str(
				default_msg,
				fmt_arg={
					'entries_count' : entries_count, 
				},
			))

			embed = discord.Embed(
				title="neko's Music Bot",
				description=description,
				color=discord.Colour.purple()
			).add_field(
				name=await MyTranslator().translate(locale_str("Title"),interaction.locale),
				value=dic["entries"][0].get('title')
			).add_field(
				name="URL",
				value=dic["entries"][0].get('webpage_url')
			)
		else:
			default_msg = '{entries_count} songs inserted into the '
			description = await interaction.translate(locale_str(
				default_msg,
				fmt_arg={
					'entries_count' : entries_count, 
				},
			))
	else:
		description = await MyTranslator().translate(locale_str("Song inserted into the ",),interaction.locale)

	embed = discord.Embed(
		title="neko's Music Bot",
		description=description,
		color=discord.Colour.purple()
	).add_field(
		name=await MyTranslator().translate(locale_str("Title"),interaction.locale),
		value=dic.get('title')
	).add_field(
		name="URL",
		value=dic.get('webpage_url')
	)

	await interaction.channel.send(embed=embed)


@tree.command(name="stop", description=locale_str("Stops the music currently playing and discards the cue."))
@discord.app_commands.guild_only()
async def stop(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("neko's Music Bot is not connected to the voice channel."),interaction.locale),color=discord.Colour.red())
		await interaction.response.send_message(embed=embed,ephemeral=True)
		return
	if isPlaying_dict[interaction.guild.id] == True:
		del queue_dict[interaction.guild.id]
		isPlaying_dict[interaction.guild.id] = False
		asyncio.to_thread(voice_client.stop)
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("The song was stopped and the queue was discarded."),interaction.locale),color=discord.Colour.purple())
		await interaction.response.send_message(embed=embed)
	else:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("The song does not seem to be playing."),interaction.locale),color=discord.Colour.purple())
		await interaction.response.send_message(embed=embed)

@tree.command(name="skip", description=locale_str("Skips the currently playing music and plays the next music in the "))
@discord.app_commands.guild_only()
async def skip(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("neko's Music Bot is not connected to the voice channel."),interaction.locale),color=discord.Colour.red())
		await interaction.response.send_message(embed=embed,ephemeral=True)
		return
	embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("Skipped one song."),interaction.locale),color=discord.Colour.purple())
	await interaction.response.send_message(embed=embed)
	asyncio.to_thread(voice_client.stop())

@tree.command(name="pause", description=locale_str("Pause the song."))
@discord.app_commands.guild_only()
async def pause(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("neko's Music Bot is not connected to the voice channel."),interaction.locale),color=discord.Colour.red())
		await interaction.response.send_message(embed=embed,ephemeral=True)
		return
	asyncio.to_thread(voice_client.pause())
	embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("Song paused."),interaction.locale),color=discord.Colour.purple())
	await interaction.response.send_message(embed=embed)

@tree.command(name="resume", description=locale_str("Resume paused song."))
@discord.app_commands.guild_only()
async def resume(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("neko's Music Bot is not connected to the voice channel."),interaction.locale),color=discord.Colour.red())
		await interaction.response.send_message(embed=embed,ephemeral=True)
		return
	asyncio.to_thread(voice_client.resume())
	embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("Resumed songs that had been paused."),interaction.locale),color=discord.Colour.purple())
	await interaction.response.send_message(embed=embed)

class QueueView(discord.ui.View):
	def __init__(self):
		super().__init__(timeout=None)
		self.page = 0
	
	@discord.ui.button(emoji="◀", style=discord.ButtonStyle.primary)
	async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.guild.id in queue_dict:
			await interaction.response.defer()
			self.page -= 1
			qlist = []
			c = 1
			if nowPlaying_dict[f"{interaction.guild.id}"].get("title",None) is not None:
				qlist.append(f"**{await MyTranslator().translate(locale_str('Playing'),interaction.locale)}: **[{nowPlaying_dict[f'{interaction.guild.id}'].get('title')}]({nowPlaying_dict[f'{interaction.guild.id}'].get('webpage_url')})")
			else:
				qlist.append(f"**{await MyTranslator().translate(locale_str('Playing'),interaction.locale)}: **None")
			# キューの中身を表示
			for _ in queue_dict[interaction.guild.id]:
				item = queue_dict[interaction.guild.id][_]
				if c >= 0 and c <= 9:
					qlist.append(f"#{c} [{item.get('title')}]({item.get('webpage_url')})")
				c = c + 1
				await asyncio.sleep(0.01)
			embed = discord.Embed(title="neko's Music Bot", description="\n".join(qlist), color=discord.Colour.purple())
			view = QueueView()
			if self.page == 1:
				view.prev.disabled = True
			else:
				view.prev.disabled = False
			if (self.page + 1)*10 > c:
				view.next.disabled = True
			else:
				view.next.disabled = False
			await interaction.message.edit(embed=embed, view=view)
		else:
			embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("No songs in queue"),interaction.locale),color=discord.Colour.red())
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

	@discord.ui.button(emoji="▶", style=discord.ButtonStyle.primary)
	async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.guild.id in queue_dict:
			await interaction.response.defer()
			self.page += 1
			qlist = []
			c = 1
			if nowPlaying_dict[f"{interaction.guild.id}"].get("title",None) is not None:
				qlist.append(f"**{await MyTranslator().translate(locale_str('Playing'),interaction.locale)}: **[{nowPlaying_dict[f'{interaction.guild.id}'].get('title')}]({nowPlaying_dict[f'{interaction.guild.id}'].get('webpage_url')})")
			else:
				qlist.append(f"**{await MyTranslator().translate(locale_str('Playing'),interaction.locale)}: **None")
			# キューの中身を表示
			for _ in queue_dict[interaction.guild.id]:
				item = queue_dict[interaction.guild.id][_]
				if c >= 0 and c <= 9:
					qlist.append(f"#{c} [{item.get('title')}]({item.get('webpage_url')})")
				c = c + 1
				await asyncio.sleep(0.01)
			embed = discord.Embed(title="neko's Music Bot", description="\n".join(qlist), color=discord.Colour.purple())
			view = QueueView()
			if self.page == 1:
				view.prev.disabled = True
			else:
				view.prev.disabled = False
			if (self.page + 1)*10 > c:
				view.next.disabled = True
			else:
				view.next.disabled = False
			await interaction.message.edit(embed=embed, view=view)
		else:
			embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("No songs in queue"),interaction.locale),color=discord.Colour.red())
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

	@discord.ui.button(emoji="🔄", style=discord.ButtonStyle.primary)
	async def reload(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.guild.id in queue_dict:
			await interaction.response.defer()
			qlist = []
			c = 1
			if nowPlaying_dict[f"{interaction.guild.id}"].get("title",None) is not None:
				qlist.append(f"**{await MyTranslator().translate(locale_str('Playing'),interaction.locale)}: **[{nowPlaying_dict[f'{interaction.guild.id}'].get('title')}]({nowPlaying_dict[f'{interaction.guild.id}'].get('webpage_url')})")
			else:
				qlist.append(f"**{await MyTranslator().translate(locale_str('Playing'),interaction.locale)}: **None")
			# キューの中身を表示
			for _ in queue_dict[interaction.guild.id]:
				item = queue_dict[interaction.guild.id][_]
				if c >= 0 and c <= 9:
					qlist.append(f"#{c} [{item.get('title')}]({item.get('webpage_url')})")
				c = c + 1
				await asyncio.sleep(0.01)
			embed = discord.Embed(title="neko's Music Bot", description="\n".join(qlist), color=discord.Colour.purple())
			view = QueueView()
			if self.page == 1:
				view.prev.disabled = True
			else:
				view.prev.disabled = False
			if (self.page + 1)*10 > c:
				view.next.disabled = True
			else:
				view.next.disabled = False
			await interaction.message.edit(embed=embed, view=view)
		else:
			embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("No songs in queue"),interaction.locale),color=discord.Colour.red())
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

	@discord.ui.button(emoji="❌", style=discord.ButtonStyle.secondary)
	async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
		await interaction.response.defer()
		await interaction.message.delete()

@tree.command(name="queue", description=locale_str("You can check the songs in the "))
@discord.app_commands.guild_only()
async def queue(interaction: discord.Interaction):
	if interaction.guild.id in queue_dict:
		await interaction.response.defer()
		qlist = []
		c = 1
		if nowPlaying_dict[f"{interaction.guild.id}"].get("title",None) is not None:
			qlist.append(f"**{await MyTranslator().translate(locale_str('Playing'),interaction.locale)}: **[{nowPlaying_dict[f'{interaction.guild.id}'].get('title')}]({nowPlaying_dict[f'{interaction.guild.id}'].get('webpage_url')})")
		else:
			qlist.append(f"**{await MyTranslator().translate(locale_str('Playing'),interaction.locale)}: **None")
		# キューの中身を表示
		for _ in queue_dict[interaction.guild.id]:
			item = queue_dict[interaction.guild.id][_]
			if c >= 0 and c <= 9:
				qlist.append(f"#{c} [{item.get('title')}]({item.get('webpage_url')})")
			c = c + 1
			await asyncio.sleep(0.01)
		embed = discord.Embed(title="neko's Music Bot", description="\n".join(qlist), color=discord.Colour.purple())
		view = QueueView()
		view.prev.disabled = True
		if (1 + 1)*10 > c:
			view.next.disabled = True
		else:
			view.next.disabled = False
		await interaction.followup.send(embed=embed, view=view)
	else:
		embed = discord.Embed(title="neko's Music Bot",description=await MyTranslator().translate(locale_str("No songs in queue"),interaction.locale),color=discord.Colour.red())
		await interaction.response.send_message(embed=embed, ephemeral=True)
		return

@tree.command(name="help", description=locale_str("You can check the available commands."))
@discord.app_commands.guild_only()
async def help(interaction: discord.Interaction):
	await interaction.response.defer()
	embed = discord.Embed(title="neko's Music Bot",description="",color=discord.Colour.purple())
	for command in tree.get_commands(type=discord.AppCommandType.chat_input):
		params = []
		for parameter in command.parameters:
			params.append(f"**{parameter.locale_name}**: <{parameter.type.name}>")
			await asyncio.sleep(0.01)
		p = ', '.join(params)
		embed.add_field(name=f"/{command.name} {p}",value=await MyTranslator().translate(locale_str(command.description),interaction.locale), inline=False)
		await asyncio.sleep(0.01)
	# embed.add_field(name="/play **url**:<video>",value="urlで指定された音楽を再生します。すでに音楽が再生されている場合はキューに挿入します。")
	await interaction.followup.send(embed=embed)

@tree.command(name="forceplay", description=locale_str("If a song is in the queue, it is forced to play the song."))
@discord.app_commands.guild_only()
async def forceplay(interaction: discord.Interaction):
	await interaction.response.defer()
	if voice_client is None and isConnecting_dict[interaction.guild.id] == False:
		if interaction.user.voice is not None:
			isPlaying_dict[interaction.guild.id] = False
			await interaction.user.voice.channel.connect()
			isConnecting_dict[interaction.guild.id] = True
			await interaction.followup.send(
				embed=discord.Embed(
					title="neko's Music Bot",
					description=await MyTranslator().translate(locale_str('Connected to voice channel.'),interaction.locale),
					color=discord.Colour.purple()
				).add_field(
					name=await MyTranslator().translate(locale_str('Destination Channel'),interaction.locale),
					value=f"<#{interaction.user.voice.channel.id}>"
				),
				ephemeral=False
			)
			voice_client = interaction.guild.voice_client
		else:
			await interaction.followup.send(
				embed=discord.Embed(
					title="neko's Music Bot",
					description=await MyTranslator().translate(locale_str("You are not currently connecting to any voice channel."),interaction.locale),
					color=discord.Colour.red()
				),
				ephemeral=True
			)
			return
	else:
		await interaction.followup.send(
			embed=discord.Embed(
				title="neko's Music Bot",
				description=await MyTranslator().translate(locale_str('Operation accepted. Please wait a moment...'),interaction.locale),
				color=discord.Colour.purple()
			),
			ephemeral=False
		)
	queue = queue_dict[interaction.guild.id]
	if len(queue) != 0:
		embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str('Starts playing the song.'),interaction.locale), color=discord.Colour.purple())
		await interaction.channel.send(embed=embed, ephemeral=True)
		isPlaying_dict[interaction.guild.id] = True
		await playbgm(voice_client, interaction.channel, interaction.locale, queue)
	else:
		embed = discord.Embed(title="neko's Music Bot", description=await MyTranslator().translate(locale_str("No songs in queue"),interaction.locale), color=discord.Colour.red())
		await interaction.channel.send(embed=embed, ephemeral=True)

@tree.command(name="ping", description=locale_str("View gateway Ping, CPU utilization, and memory utilization."))
async def ping(interaction: discord.Interaction):
	ping = client.latency
	cpu_percent = psutil.cpu_percent()
	mem = psutil.virtual_memory() 
	embed = discord.Embed(title="Ping", description=f"Ping : {ping*1000}ms\nCPU : {cpu_percent}%\nMemory : {mem.percent}%", color=discord.Colour.purple())
	embed.set_thumbnail(url=client.user.display_avatar.url)
	await interaction.response.send_message(embed=embed)

@tree.command(name="support", description=locale_str("Displays an invitation link to the support server."))
async def ping(interaction: discord.Interaction):
	embed = discord.Embed(title="neko's Music Bot", description="https://discord.gg/PN3KWEnYzX", color=discord.Colour.purple())
	embed.set_thumbnail(url=client.user.display_avatar.url)
	await interaction.response.send_message(embed=embed)

@tasks.loop(seconds=20)  # repeat after every 20 seconds
async def myLoop():
	# work
	vccount = 0
	for guild in client.guilds:
		if guild.voice_client != None:
			vccount += 1
		await asyncio.sleep(0.01)
	await client.change_presence(activity=discord.Game(
		name=f"/help | {len(client.guilds)} SERVERS | {vccount} VOICE CHANNELS | deployed: {last_commit_date}"))

TOKEN = os.getenv("DISCORD_TOKEN")
# Web サーバの立ち上げ(シン・クラウド for FreeのCronを噛ませる)
keep_alive()
client.run(TOKEN)
