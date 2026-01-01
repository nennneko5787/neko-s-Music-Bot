import math

import discord
import lavalink as Lavalink

from objects.utils import formatTime

from .player import MusicPlayer


class MusicPanel(discord.ui.LayoutView):
    def __init__(
        self,
        player: MusicPlayer,
        track: Lavalink.AudioTrack,
        requestAuthor: discord.Member,
        bar: str,
        circle: str,
        graybar: str,
        *,
        finished: bool = False,
    ) -> None:
        super().__init__(timeout=None)

        if not finished:
            if player.is_playing:
                if player.paused:
                    self.title = discord.ui.TextDisplay(
                        f"⏸️一時停止中 - **[{track.title}]({track.uri})**\n-# {requestAuthor.mention} によるリクエスト"
                    )
                else:
                    self.title = discord.ui.TextDisplay(
                        f"🎶再生中 - **[{track.title}]({track.uri})**\n-# {requestAuthor.mention} によるリクエスト"
                    )
            else:
                self.title = discord.ui.TextDisplay(
                    f"再生準備中 - **[{track.title}]({track.uri})**\n-# {requestAuthor.mention} によるリクエスト"
                )
        else:
            self.trackInfoSection = discord.ui.TextDisplay(
                f"再生終了 - **[{track.title}]({track.uri})**\n-# {requestAuthor.mention} によるリクエスト"
            )
            container = discord.ui.Container(
                self.trackInfoSection,
                accent_color=discord.Color.red(),
            )
            self.add_item(container)
            return

        if track.artwork_url:
            self.thumbnail = discord.ui.Thumbnail(
                media=track.artwork_url, description=track.title
            )
            self.trackInfoSection = discord.ui.Section(
                self.title, accessory=self.thumbnail
            )
        else:
            self.trackInfoSection = discord.ui.TextDisplay(track.title)

        percentage = player.position / track.duration
        barLength = 14
        filledLength = int(barLength * percentage)
        progressBar = (
            bar * filledLength + circle + graybar * (barLength - filledLength - 1)
        )
        self.playProgress = discord.ui.TextDisplay(
            f"-# 再生時間 `{formatTime(player.position / 1000)} / {formatTime(track.duration / 1000)}`\n{progressBar}"
        )

        self.playActions = discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏪",
                custom_id="reverse",
                row=0,
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="▶" if player.paused else "⏸",
                custom_id="resume" if player.paused else "pause",
                row=0,
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏩",
                custom_id="forward",
                row=0,
            ),
            discord.ui.Button(
                style=(
                    discord.ButtonStyle.gray
                    if player.loop == player.LOOP_NONE
                    else discord.ButtonStyle.green
                    if player.loop == player.LOOP_SINGLE
                    else discord.ButtonStyle.blurple
                ),
                emoji="🔄",
                custom_id="loop",
                row=0,
            ),
        )

        self.playActions2 = discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏮",
                custom_id="prev",
                row=1,
                disabled=(player.prevQueue.qsize() <= 0),
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏹",
                custom_id="stop",
                row=1,
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏭",
                custom_id="next",
                row=1,
                disabled=(len(player.queue) <= 0),
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple
                if player.shuffle
                else discord.ButtonStyle.gray,
                emoji="🔀",
                custom_id="shuffle",
                row=1,
            ),
        )

        percentage = player.volume / 100
        barLength = 14
        filledLength = int(barLength * percentage)
        progressBar = (
            bar * filledLength + circle + graybar * (barLength - filledLength - 1)
        )
        self.volumeView = discord.ui.TextDisplay(
            f"-# ボリューム `{player.volume}%`\n{progressBar}"
        )

        self.volumeActions = discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="+",
                custom_id="volumeUp",
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="-",
                custom_id="volumeDown",
                row=1,
            ),
        )

        timescale = player.get_filter("timescale")
        if not timescale:
            speed = 1.0
            pitch = 1.0
        else:
            speed = timescale.values["speed"]
            pitch = timescale.values["pitch"]

        percentage = speed / 2.0
        barLength = 14
        filledLength = int(barLength * percentage)
        progressBar = (
            bar * filledLength + circle + graybar * (barLength - filledLength - 1)
        )
        self.speedView = discord.ui.TextDisplay(
            f"-# 速度 `{math.ceil(speed * 100)}%`\n{progressBar}"
        )

        self.speedActions = discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="+",
                custom_id="speedUp",
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="-",
                custom_id="speedDown",
                row=1,
            ),
        )

        percentage = pitch / 2.0
        barLength = 14
        filledLength = int(barLength * percentage)
        progressBar = (
            bar * filledLength + circle + graybar * (barLength - filledLength - 1)
        )
        self.pitchView = discord.ui.TextDisplay(
            f"-# ピッチ `{math.ceil(pitch * 100)}%`\n{progressBar}"
        )

        self.pitchActions = discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="+",
                custom_id="pitchUp",
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="-",
                custom_id="pitchDown",
                row=1,
            ),
        )

        container = discord.ui.Container(
            self.trackInfoSection,
            self.playProgress,
            self.playActions,
            self.playActions2,
            self.volumeView,
            self.volumeActions,
            self.speedView,
            self.speedActions,
            self.pitchView,
            self.pitchActions,
            accent_color=discord.Color.purple(),
        )
        self.add_item(container)
