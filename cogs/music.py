import asyncio
import os
import time
import traceback
from datetime import timedelta

import discord
from discord import app_commands
import dotenv
from discord.ext import commands, tasks
from spotdl import Spotdl
from spotdl.types.song import Song
from spotdl.types.album import Album
from spotdl.types.playlist import Playlist

from .source import YTDLSource, isPlayList
from .niconico import NicoNicoSource
from .queue import Queue

dotenv.load_dotenv()

pausedView = (
    discord.ui.View(timeout=None)
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏪", custom_id="reverse", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="▶", custom_id="resume", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏩", custom_id="forward", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏮", custom_id="prev", row=1
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏹", custom_id="stop", row=1
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏭", custom_id="next", row=1
        )
    )
)
notPausedView = (
    discord.ui.View(timeout=None)
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏪", custom_id="reverse", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏸", custom_id="pause", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏩", custom_id="forward", row=0
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏮", custom_id="prev", row=1
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏹", custom_id="stop", row=1
        )
    )
    .add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.blurple, emoji="⏭", custom_id="next", row=1
        )
    )
)


def formatTime(seconds):
    if seconds < 3600:
        return time.strftime("%M:%S", time.gmtime(seconds))
    elif seconds < 86400:
        return time.strftime("%H:%M:%S", time.gmtime(seconds))
    else:
        return time.strftime("%d:%H:%M:%S", time.gmtime(seconds))


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.source: dict[YTDLSource] = {}
        self.queue: dict[Queue] = {}
        self.playing: dict[bool] = {}
        self.alarm: dict[bool] = {}
        self.spotify = Spotdl(
            client_id=os.getenv("spotify_clientid"),
            client_secret=os.getenv("spotify_clientsecret"),
        )

    @commands.Cog.listener()
    async def on_ready(self):
        self.presenceLoop.start()

    @tasks.loop(seconds=20)
    async def presenceLoop(self):
        playing = []
        for p in self.playing.values():
            if p:
                playing.append(p)

        await self.bot.change_presence(
            activity=discord.Game(
                f"{len(playing)} 再生中 / {len(self.alarm.keys())} アラーム / {len(self.bot.guilds)} サーバー"
            )
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            if interaction.data["component_type"] == 2:
                await self.onButtonClick(interaction)
            elif interaction.data["component_type"] == 3:
                pass
        except KeyError:
            pass

    async def onButtonClick(self, interaction: discord.Interaction):
        customId = interaction.data["custom_id"]
        match (customId):
            case "prev":
                if not interaction.guild.voice_client:
                    await interaction.response.send_message(
                        "現在曲を再生していません。", ephemeral=True
                    )
                    return
                await interaction.response.defer(ephemeral=True)
                self.queue[interaction.guild.id].prev()
                self.playing[interaction.guild.id] = False
                interaction.guild.voice_client.stop()
            case "next":
                if not interaction.guild.voice_client:
                    await interaction.response.send_message(
                        "現在曲を再生していません。", ephemeral=True
                    )
                    return
                await interaction.response.defer(ephemeral=True)
                self.playing[interaction.guild.id] = False
                interaction.guild.voice_client.stop()
            case "stop":
                if not interaction.guild.voice_client:
                    await interaction.response.send_message(
                        "現在曲を再生していません。", ephemeral=True
                    )
                    return
                await interaction.response.defer()
                await interaction.guild.voice_client.disconnect()
                del self.queue[interaction.guild.id]
                self.playing[interaction.guild.id] = False
                await interaction.followup.send("停止しました。")
            case "resume":
                if not interaction.guild.voice_client:
                    embed = discord.Embed(
                        title="音楽を再生していません。", colour=discord.Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                interaction.guild.voice_client.resume()
                embed = interaction.message.embeds[0]
                await interaction.edit_original_response(
                    embed=embed, view=notPausedView
                )
            case "pause":
                if not interaction.guild.voice_client:
                    embed = discord.Embed(
                        title="音楽を再生していません。", colour=discord.Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                interaction.guild.voice_client.pause()
                embed = interaction.message.embeds[0]
                await interaction.edit_original_response(embed=embed, view=pausedView)
            case "reverse":
                if not interaction.guild.voice_client:
                    embed = discord.Embed(
                        title="音楽を再生していません。", colour=discord.Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                source: YTDLSource | NicoNicoSource = (
                    interaction.guild.voice_client.source
                )
                options = {
                    "before_options": f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {source.progress-10}",
                    "options": "-vn -c copy",
                }

                if isinstance(source, NicoNicoSource):
                    options["before_options"] = (
                        f"-headers 'cookie: {'; '.join(f'{k}={v}' for k, v in source.client.cookies.items())}' {options['before_options']}"
                    )
                    interaction.guild.voice_client.source = NicoNicoSource(
                        discord.FFmpegPCMAudio(source.hslContentUrl, **options),
                        info=source.info,
                        hslContentUrl=source.hslContentUrl,
                        watchid=source.watchid,
                        trackid=source.trackid,
                        outputs=source.outputs,
                        nicosid=source.nicosid,
                        niconico=source.niconico,
                        volume=source.volume,
                    )
                else:
                    interaction.guild.voice_client.source = YTDLSource(
                        discord.FFmpegPCMAudio(source.info["url"], **options),
                        info=source.info,
                        volume=source.volume,
                    )
            case "forward":
                if not interaction.guild.voice_client:
                    embed = discord.Embed(
                        title="音楽を再生していません。", colour=discord.Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                source: YTDLSource | NicoNicoSource = (
                    interaction.guild.voice_client.source
                )
                options = {
                    "before_options": f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {source.progress+10}",
                    "options": "-vn -c copy",
                }

                if isinstance(source, NicoNicoSource):
                    options["before_options"] = (
                        f"-headers 'cookie: {'; '.join(f'{k}={v}' for k, v in source.client.cookies.items())}' {options['before_options']}"
                    )
                    interaction.guild.voice_client.source = NicoNicoSource(
                        discord.FFmpegPCMAudio(source.hslContentUrl, **options),
                        info=source.info,
                        hslContentUrl=source.hslContentUrl,
                        watchid=source.watchid,
                        trackid=source.trackid,
                        outputs=source.outputs,
                        nicosid=source.nicosid,
                        niconico=source.niconico,
                        volume=source.volume,
                    )
                else:
                    interaction.guild.voice_client.source = YTDLSource(
                        discord.FFmpegPCMAudio(source.info["url"], **options),
                        info=source.info,
                        volume=source.volume,
                    )

    def setToNotPlaying(self, guildId: int):
        self.playing[guildId] = False

    def embedPanel(
        self,
        voiceClient: discord.VoiceClient,
        *,
        source: YTDLSource | NicoNicoSource = None,
        finished: bool = False,
    ):
        if source is None:
            source: YTDLSource | NicoNicoSource = voiceClient.source
        embed = discord.Embed(
            title=source.info["title"],
            url=source.info["webpage_url"],
        ).set_image(url=source.info["thumbnail"])

        if finished:
            embed.colour = discord.Colour.greyple()
            embed.set_author(name="再生終了")
        elif voiceClient.is_playing():
            embed.colour = discord.Colour.purple()
            if voiceClient.is_paused():
                embed.set_author(name="一時停止中")
            else:
                embed.set_author(name="再生中")
            embed.add_field(
                name="再生時間",
                value=f'{formatTime(source.progress)} / {formatTime(source.info["duration"])}',
            )
        else:
            embed.colour = discord.Colour.greyple()
            embed.set_author(name="再生準備中")
        return embed

    async def playNext(self, guild: discord.Guild, channel: discord.abc.Messageable):
        queue: Queue = self.queue[guild.id]

        async def get():
            if not queue.empty():
                info: dict = queue.get()
                if "nicovideo" in info["url"]:
                    self.source[guild.id] = await NicoNicoSource.from_url(
                        info["url"], info["volume"]
                    )
                else:
                    self.source[guild.id] = await YTDLSource.from_url(
                        info["url"], info["volume"]
                    )

        while True:
            if guild.voice_client:
                try:
                    if not guild.id in self.source:
                        await get()
                except:
                    traceback.print_exc()
                    continue

                if (queue.empty()) and (not guild.id in self.source):
                    break

                try:
                    source: YTDLSource | NicoNicoSource = self.source[guild.id]
                except:
                    traceback.print_exc()
                    continue

                voiceClient: discord.VoiceClient = guild.voice_client
                message = await channel.send(
                    embed=self.embedPanel(voiceClient, source=source),
                    view=notPausedView,
                )

                if isinstance(source, NicoNicoSource):
                    await source.sendHeartBeat()

                voiceClient.play(source, after=lambda _: self.setToNotPlaying(guild.id))
                self.playing[guild.id] = True

                del self.source[guild.id]

                asyncio.create_task(get())

                while self.playing[guild.id]:
                    if isinstance(source, NicoNicoSource):
                        await source.sendHeartBeat()
                    await message.edit(
                        embed=self.embedPanel(voiceClient),
                        view=(
                            notPausedView if not voiceClient.is_paused() else pausedView
                        ),
                    )
                    await asyncio.sleep(5)
                await message.edit(
                    embed=self.embedPanel(voiceClient, finished=True), view=None
                )
                voiceClient.stop()
            else:
                break
        await channel.send("再生終了")
        self.playing[guild.id] = False
        if guild.id in self.source:
            del self.source[guild.id]
        if guild.voice_client:
            await guild.voice_client.disconnect()

    async def putQueue(self, interaction: discord.Interaction, url: str, volume: float):
        queue: Queue = self.queue[interaction.guild.id]
        if "spotify" in url:
            if "track" in url:
                song: Song = await asyncio.to_thread(Song.from_url, url)
                urls: list[str | None] = await asyncio.to_thread(
                    self.spotify.get_download_urls, [song]
                )
            elif "album" in url:
                album = await asyncio.to_thread(Album.from_url, url)
                urls: list[str | None] = await asyncio.to_thread(
                    self.spotify.get_download_urls, album.songs
                )
            elif "playlist" in url:
                playlist = await asyncio.to_thread(Playlist.from_url, url)
                urls: list[str | None] = await asyncio.to_thread(
                    self.spotify.get_download_urls, playlist.songs
                )
            else:
                await interaction.followup.send("無効なSpotify URL")
                return

            for music in urls:
                queue.put(
                    {
                        "url": music,
                        "volume": volume,
                    }
                )
            await interaction.followup.send(
                f"**{len(urls)}個の曲**をキューに追加しました。"
            )
        else:
            result = await isPlayList(url)
            if not result:
                queue.put({"url": url, "volume": volume})
                await interaction.followup.send(f"**{url}** をキューに追加しました。")
            else:
                for video in result:
                    queue.put(
                        {
                            "url": video,
                            "volume": volume,
                        }
                    )
                await interaction.followup.send(
                    f"**{len(result)}個の動画**をキューに追加しました。"
                )

    @app_commands.command(name="alarm", description="アラームをセットします。")
    async def alarmCommand(
        self,
        interaction: discord.Interaction,
        delay: app_commands.Range[int, 0],
        url: str,
        volume: float = 0.5,
    ):
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        if not user.voice:
            await interaction.response.send_message(
                "ボイスチャンネルに接続してください。", ephemeral=True
            )
            return
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect()
        if not guild.id in self.playing:
            self.playing[guild.id] = False
        if not guild.id in self.queue:
            self.queue[guild.id] = Queue()
        await self.putQueue(interaction, url, volume)

        self.alarm[guild.id] = True

        embed = discord.Embed(
            title="アラームをセットしました！",
            description=f"{discord.utils.format_dt(discord.utils.utcnow()+timedelta(seconds=delay), 'R')} に音楽を再生します。\n-# VCに参加している端末の電池残量・電力消費に注意してください。\n-# また、アラームを設定している最中にボットが再起動されると、アラームはリセットされます。ご注意ください。",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed)

        await asyncio.sleep(delay)
        del self.alarm[guild.id]
        await self.playNext(guild, channel)

    @app_commands.command(name="play", description="曲を再生します。")
    async def playMusic(
        self, interaction: discord.Interaction, url: str, volume: float = 0.5
    ):
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        if not user.voice:
            await interaction.response.send_message(
                "ボイスチャンネルに接続してください。", ephemeral=True
            )
            return
        await interaction.response.defer()
        if not guild.voice_client:
            await user.voice.channel.connect()
        if not guild.id in self.playing:
            self.playing[guild.id] = False
        if not guild.id in self.queue:
            self.queue[guild.id] = Queue()
        print("a")
        await self.putQueue(interaction, url, volume)
        print("a")
        if (not self.playing[guild.id]) and (not self.alarm.get(guild.id, False)):
            await self.playNext(guild, channel)

    @app_commands.command(name="skip", description="曲をスキップします。")
    async def skipMusic(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        await interaction.response.defer()
        self.playing[guild.id] = False
        guild.voice_client.stop()
        await interaction.followup.send("スキップしました。")

    @app_commands.command(name="stop", description="曲を停止します。")
    async def stopMusic(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        await interaction.response.defer()
        await guild.voice_client.disconnect()
        del self.queue[guild.id]
        self.playing[guild.id] = False
        await interaction.followup.send("停止しました。")

    @app_commands.command(name="pause", description="曲を一時停止します。")
    async def pauseMusic(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        if guild.voice_client.is_paused():
            await interaction.response.send_message(
                "すでに一時停止しています。", ephemeral=True
            )
            return
        await interaction.response.defer()
        await guild.voice_client.pause()
        await interaction.followup.send("一時停止しました。")

    @app_commands.command(name="resume", description="曲を一時停止します。")
    async def resumeMusic(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        if not guild.voice_client.is_paused():
            await interaction.response.send_message(
                "一時停止していません。", ephemeral=True
            )
            return
        await interaction.response.defer()
        await guild.voice_client.resume()
        await interaction.followup.send("一時停止しました。")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
