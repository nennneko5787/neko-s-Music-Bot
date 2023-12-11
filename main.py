import discord
from discord import app_commands
from discord.ext import tasks
import os
from keep_alive import keep_alive
import asyncio
from yt_dlp import YoutubeDL
from niconico import NicoNico
import ffmpeg
from collections import defaultdict, deque

queue_dict = defaultdict(deque)
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
		info_dict = ydl.extract_info(url, download=False)
		video_title = info_dict.get('title', None)
		return video_title


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
		return video.video.title


async def playbgm(voice_client,queue):
	if not queue or voice_client.is_playing():
		await voice_client.channel.send(f"キューに入っている曲はありません")
		return
	if(os.path.isfile(f"{voice_client.guild.id}.mp3")):
		os.remove(f"{voice_client.guild.id}.mp3")
	source = queue.popleft()
	uuaaru = source.split()
	url = uuaaru[0]
	platform = uuaaru[1]
	loop = asyncio.get_event_loop()
	title = ""
	await voice_client.channel.send(f"ダウンロード中: **{url}**")
	if platform == "Youtube":
		title = await loop.run_in_executor(None, ytdl, url,voice_client.guild.id)
	elif platform == "Niconico":
		title = await loop.run_in_executor(None, ncdl, url,voice_client.guild.id)
	voice_client.play(discord.FFmpegPCMAudio(f"{voice_client.guild.id}.mp3"), after=lambda e:play(voice_client, queue))
	await voice_client.channel.send(f"再生: **{title}**")


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
		await interaction.followup.send("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	queue = queue_dict[interaction.guild.id]
	queue.append(f"{url}\n{platform}")
	await interaction.followup.send("曲をキューに挿入しました。")
	if not voice_client.is_playing():
		await interaction.channel.send("曲の再生を開始します。")
		try:
			await playbgm(voice_client,queue)
		except:
			del queue_dict[interaction.guild.id]

@tree.command(name="stop", description="音楽を停止します")
async def stop(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	del queue_dict[interaction.guild.id]
	voice_client.stop()
	await interaction.response.send_message("一曲スキップしました")


@tree.command(name="skip", description="曲を一曲スキップします")
async def skip(interaction: discord.Interaction):
	voice_client = interaction.guild.voice_client
	if voice_client is None:
		await interaction.response.send_message("neko's Music Botはボイスチャンネルに接続していません。",ephemeral=True)
		return
	voice_client.stop()
	queue = queue_dict[interaction.guild.id]
	await playbgm(voice_client,queue)
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
		name=f"{len(client.guilds)}"))

TOKEN = os.getenv("DISCORD_TOKEN")
# Web サーバの立ち上げ
keep_alive()
client.run(TOKEN)
