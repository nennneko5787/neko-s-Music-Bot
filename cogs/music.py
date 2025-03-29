import asyncio
import logging
import os
import time
from typing import List

import discord
import dotenv
import wavelink
from discord import app_commands
from discord.ext import commands, tasks

dotenv.load_dotenv()


class MusicCog(commands.Cog):
    __slots__ = ("bot",)

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger("music")
        self.bar = ""
        self.circle = ""
        self.graybar = ""
        self.presenceCount = 0
        self.presenceLoop.start()

    @tasks.loop(seconds=20)
    async def presenceLoop(self):
        if self.presenceCount == 0:
            await self.bot.change_presence(
                activity=discord.Activity(
                    name=f"{len(self.bot.voice_clients)} / {len(self.bot.guilds)} サーバー",
                    type=discord.ActivityType.competing,
                )
            )
            self.presenceCount = 1
        elif self.presenceCount == 1:
            await self.bot.change_presence(activity=discord.Game("/help"))
            self.presenceCount = 2
        elif self.presenceCount == 2:
            await self.bot.change_presence(
                activity=discord.Game("Powered by nennneko5787")
            )
            self.presenceCount = 0

    async def cog_load(self):
        nodes = [
            wavelink.Node(
                uri=os.getenv("lavalink_uri"), password=os.getenv("lavalink_password")
            )
        ]
        await wavelink.Pool.connect(nodes=nodes, client=self.bot, cache_capacity=100)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bar = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="bar")
        )
        self.circle = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="circle")
        )
        self.graybar = str(
            discord.utils.get(await self.bot.fetch_application_emojis(), name="graybar")
        )

    @commands.Cog.listener()
    async def on_wavelink_node_ready(
        self, payload: wavelink.NodeReadyEventPayload
    ) -> None:
        self.log.info(
            "Wavelink Node connected: %r | Resumed: %s", payload.node, payload.resumed
        )

    def formatTime(self, seconds: int):
        if seconds < 3600:
            return time.strftime("%M:%S", time.gmtime(seconds))
        elif seconds < 86400:
            return time.strftime("%H:%M:%S", time.gmtime(seconds))
        else:
            return time.strftime("%d:%H:%M:%S", time.gmtime(seconds))

    def createView(self, player: wavelink.Player):
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏪",
                custom_id="reverse",
                row=0,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="▶" if player.paused else "⏸",
                custom_id="resume" if player.paused else "pause",
                row=0,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏩",
                custom_id="forward",
                row=0,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="+",
                custom_id="volumeUp",
                row=0,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=(
                    discord.ButtonStyle.blurple
                    if not player.loop
                    else discord.ButtonStyle.danger
                ),
                emoji="🔄",
                custom_id="loop",
                row=0,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏮",
                custom_id="prev",
                row=1,
                disabled=True,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple, emoji="⏹", custom_id="stop", row=1
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏭",
                custom_id="next",
                row=1,
                disabled=(len(player.queue) <= 0),
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="-",
                custom_id="volumeDown",
                row=1,
            )
        )
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="🔀",
                custom_id="shuffle",
                row=1,
            )
        )
        return view

    def clamp(self, value: float | int, min_value: float | int, max_value: float | int):
        """
        指定した範囲内に数値を制限する関数。

        :param value: 制限したい数値
        :param min_value: 最小値
        :param max_value: 最大値
        :return: 制限された数値
        """
        return max(min_value, min(value, max_value))

    def embedPanel(
        self,
        player: wavelink.Player,
        *,
        finished: bool = False,
    ):
        embed = discord.Embed(
            title=player.track.title,
            url=player.track.uri,
        ).set_image(url=player.track.artwork)

        if finished:
            embed.colour = discord.Colour.greyple()
            embed.set_author(name="再生終了")
        elif player.playing or player.paused:
            percentage = player.position / player.track.length
            barLength = 14
            filledLength = int(barLength * percentage)
            progressBar = (
                self.bar * filledLength
                + self.circle
                + self.graybar * (barLength - filledLength - 1)
            )

            percentage = player.volume / 100
            barLength = 14
            filledLength = int(barLength * percentage)
            volumeProgressBar = (
                self.bar * filledLength
                + self.circle
                + self.graybar * (barLength - filledLength - 1)
            )

            embed.colour = discord.Colour.purple()
            if player.paused:
                embed.set_author(name="一時停止中")
            else:
                embed.set_author(name="再生中")
            embed.add_field(
                name="再生時間",
                value=f"{progressBar}\n`{self.formatTime(player.position / 1000)} / {self.formatTime(player.track.length / 1000)}`",
                inline=False,
            ).add_field(
                name="リクエストしたユーザー",
                value=player.track.user.mention,
                inline=False,
            ).add_field(
                name="ボリューム",
                value=f"{volumeProgressBar}\n`{player.volume} / 100`",
                inline=False,
            )
        else:
            embed.colour = discord.Colour.greyple()
            embed.set_author(name="再生準備中")

        if player.original and player.original.recommended:
            embed.set_footer(
                text=f"このトラックは {player.track.source} 経由でおすすめされました。"
            )

        if player.track.album.name:
            embed.add_field(name="アルバム", value=player.track.album.name)
        return embed

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
        customField = interaction.data["custom_id"].split(",")
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        match (customField[0]):
            case "prev":
                player.queue.put_at(0, player.track)
                await player.play(player._previous)
            case "next":
                player.skip()
            case "stop":
                await player.disconnect()
            case "resume":
                await player.pause(False)
            case "pause":
                await player.pause(True)
            case "reverse":
                await player.seek(
                    self.clamp(
                        player.position / 1000 - 10, 0, player.track.length / 1000
                    )
                )
            case "forward":
                await player.seek(
                    self.clamp(
                        player.position / 1000 + 10, 0, player.track.length / 1000
                    )
                )
            case "volumeUp":
                await player.set_volume(self.clamp(player.volume + 5, 0, 100))
            case "volumeDown":
                await player.set_volume(self.clamp(player.volume - 5, 0, 100))
            case "loop":
                player.loop = not player.loop
            case "shuffle":
                player.queue.shuffle()
            case "queuePagenation":
                await self.queuePagenation(interaction, int(customField[1]), edit=True)
        await interaction.edit_original_response(
            embed=self.embedPanel(player, finished=False),
            view=self.createView(player),
        )

    def pagenation(
        self, queue: List[wavelink.Playable], page: int, *, pageSize: int = 10
    ):
        startIndex = (page - 1) * pageSize
        endIndex = startIndex + pageSize
        if startIndex >= len(queue) or page < 1:
            return ()
        return tuple(queue[startIndex:endIndex])

    async def queuePagenation(
        self, interaction: discord.Interaction, page: int = 1, *, edit: bool = False
    ):
        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return

        queue = player.queue._items
        queue.insert(0, player.track)

        pageSize = 10
        songList: tuple[wavelink.Playable] = self.pagenation(
            queue, page, pageSize=pageSize
        )
        songs = ""

        for _, song in enumerate(songList):
            songs += f"[{song.title}]({song.uri}) by {(await interaction.guild.fetch_member(song.extras.userId)).mention} (現在再生中)\n"

        view = (
            discord.ui.View(timeout=None)
            .add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.blurple,
                    emoji="⏪",
                    custom_id=f"queuePagenation,{page-1}",
                    row=0,
                    disabled=(page <= 1),
                )
            )
            .add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.gray,
                    emoji="🔄",
                    label=f"ページ {page} / {(len(player.queue) // pageSize) + 1}",
                    custom_id=f"queuePagenation,{page}",
                    row=0,
                )
            )
            .add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.blurple,
                    emoji="⏩",
                    custom_id=f"queuePagenation,{page+1}",
                    row=0,
                    disabled=((len(player.queue) // pageSize) + 1 == page),
                )
            )
        )
        embed = discord.Embed(title=f"キュー", description=songs)
        if edit:
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player: wavelink.Player = payload.player
        if not player:
            # Handle edge cases...
            return

        original: wavelink.Playable | None = payload.original
        track: wavelink.Playable = payload.track

        track.user = await player.home.guild.fetch_member(track.extras.userId)

        player.original = original
        player.track = track

        message = await player.home.send(
            embed=self.embedPanel(player, finished=False),
            view=self.createView(player),
        )

        await asyncio.sleep(3)

        count = 0
        while True:
            if hasattr(player, "track"):
                if (
                    player.position / 1000 >= player.track.length / 1000
                    or not player.playing
                ):
                    if player.loop:
                        await player.seek(0)
                        await asyncio.sleep(3)
                    else:
                        await message.edit(
                            embed=self.embedPanel(player, finished=True),
                            view=None,
                        )
                        break
            if count >= 5:
                await message.edit(
                    embed=self.embedPanel(player, finished=False),
                    view=self.createView(player),
                )
                count = 0
            count += 0.01
            await asyncio.sleep(0.01)

        if len(player.queue) > 0:
            await player.play(player.queue.get(), volume=15)
        else:
            await player.home.send("再生終了")
            await player.disconnect()

    @app_commands.command(name="play", description="曲を再生します。")
    @app_commands.rename(query="クエリ")
    @app_commands.describe(query="URLまたは検索ワードを入力してください。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def playCommand(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        player: wavelink.Player = interaction.guild.voice_client

        if not player:
            try:
                player = await interaction.user.voice.channel.connect(cls=wavelink.Player)  # type: ignore
                player.loop = False
            except AttributeError:
                await interaction.followup.send(
                    "コマンドを実行する前に、ボイスチャンネルに接続してください。"
                )
                return
            except discord.ClientException:
                await interaction.followup.send(
                    "ボイスチャンネルに接続できませんでした。数秒待って、もう一度お試しください。"
                )
                return

        # Turn on AutoPlay to enabled mode.
        # enabled = AutoPlay will play songs for us and fetch recommendations...
        # partial = AutoPlay will play songs for us, but WILL NOT fetch recommendations...
        # disabled = AutoPlay will do nothing...
        player.autoplay = wavelink.AutoPlayMode.disabled

        # Lock the player to this channel...
        if not hasattr(player, "home"):
            player.home = interaction.channel
        elif player.home != interaction.channel:
            await interaction.send(
                f"現在 {player.home.mention} にてボットが曲を再生しているため、このチャンネルで曲を再生することはできません。"
            )
            return

        # This will handle fetching Tracks and Playlists...
        # Seed the doc strings for more information on this method...
        # If spotify is enabled via LavaSrc, this will automatically fetch Spotify tracks if you pass a URL...
        # Defaults to YouTube for non URL based queries...
        _tracks: wavelink.Search = await wavelink.Playable.search(query)
        if not _tracks:
            await interaction.followup.send(
                f"{interaction.user.mention} 曲がヒットしませんでした。もう一度お試しください。"
            )
            return
        tracks = []
        for track in _tracks:
            track.extras = {"userId": interaction.user.id}
            tracks.append(track)

        if isinstance(tracks, wavelink.Playlist):
            # tracks is a playlist...
            added: int = await player.queue.put_wait(tracks)
            await interaction.followup.send(
                f"**`{tracks.name}`** ({added}曲) をキューに追加しました。"
            )
        else:
            track: wavelink.Playable = tracks[0]
            await player.queue.put_wait(track)
            await interaction.followup.send(f"**`{track}`**をキューに追加しました。")

        if not player.playing:
            await player.play(player.queue.get(), volume=15)

    @app_commands.command(name="pitch", description="曲のピッチを変更します。")
    @app_commands.rename(pitch="ピッチ")
    @app_commands.describe(pitch="曲のピッチを指定してください。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def pitchCommand(
        self,
        interaction: discord.Interaction,
        pitch: app_commands.Range[float, 0.1, 2.0],
    ):
        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return

        filters: wavelink.Filters = player.filters
        filters.timescale.set(pitch=pitch, speed=pitch, rate=1)
        await player.set_filters(filters)

        await interaction.followup.send(
            f"曲のピッチを **``{pitch}``** に変更しました。"
        )

    @app_commands.command(name="volume", description="曲の音量を変更します。")
    @app_commands.rename(volume="音量")
    @app_commands.describe(volume="曲の音量を指定してください。")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def volumeCommand(
        self,
        interaction: discord.Interaction,
        volume: app_commands.Range[int, 0.0, 100.0],
    ):
        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return

        await player.set_volume(volume)
        await interaction.followup.send(f"曲の音量を **``{volume}``** に変更しました。")

    @app_commands.command(
        name="queue", description="キューに入っている曲の一覧を取得します。"
    )
    @app_commands.guild_only()
    async def queueCommand(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            await interaction.response.send_message(
                "現在曲を再生していません。", ephemeral=True
            )
            return
        await self.queuePagenation(interaction, 1, edit=True)

    @app_commands.command(
        name="loop", description="ループ・ループ解除状態を切り替えます。"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def loopToggleCommand(self, interaction: discord.Interaction):
        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return

        player.loop = not player.loop
        if player.loop:
            await interaction.followup.send("ループを開始します。")
        else:
            await interaction.followup.send("ループを終了します。")

    @app_commands.command(
        name="toggle", description="一時停止・再開状態を切り替えます。"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def toggleCommand(self, interaction: discord.Interaction):
        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return

        await player.pause(not player.paused)
        if player.paused:
            await interaction.followup.send("一時停止しました。")
        else:
            await interaction.followup.send("再生を再開しました。")

    @app_commands.command(
        name="stop", description="曲の再生を停止し、ボイスチャンネルから切断します。"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def stopCommand(self, interaction: discord.Interaction):
        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.followup.send(
                "コマンドを実行する前に、曲を再生してください。"
            )
            return

        await player.disconnect()
        await interaction.followup.send("切断しました。")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
