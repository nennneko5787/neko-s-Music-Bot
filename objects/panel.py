import discord
import lavalink

from objects.utils import formatTime

from .player import MusicPlayer


def _progressBar(percentage: float, bar: str, circle: str, graybar: str, length: int = 14) -> str:
    # SPEC #28: percentage>=1.0 では graybar 数が負になり circle も付けると length+1 文字にはみ出す。
    if percentage >= 1.0:
        return bar * length
    if percentage <= 0.0:
        return circle + graybar * (length - 1)
    filled = int(length * percentage)
    return bar * filled + circle + graybar * (length - filled - 1)


class WaitingView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

        self.trackInfoSection = discord.ui.TextDisplay("準備中")
        container = discord.ui.Container(
            self.trackInfoSection,
            accent_color=discord.Color.red(),
        )
        self.add_item(container)


class MusicPanel(discord.ui.LayoutView):
    def __init__(
        self,
        player: MusicPlayer,
        track: lavalink.AudioTrack,
        requestAuthorMention: str,
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
                        f"⏸️一時停止中 - **[{track.title}]({track.uri})**\n-# {requestAuthorMention} によるリクエスト"
                    )
                else:
                    self.title = discord.ui.TextDisplay(
                        f"🎶再生中 - **[{track.title}]({track.uri})**\n-# {requestAuthorMention} によるリクエスト"
                    )
            else:
                self.title = discord.ui.TextDisplay(
                    f"再生準備中 - **[{track.title}]({track.uri})**\n-# {requestAuthorMention} によるリクエスト"
                )
        else:
            self.trackInfoSection = discord.ui.TextDisplay(
                f"再生終了 - **[{track.title}]({track.uri})**\n-# {requestAuthorMention} によるリクエスト"
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
            # SPEC #4: 元の実装は self.title(状態+リクエスト者情報)を捨てて track.title のみ表示する
            # バグだった。アートワーク無しでも同じ情報行を出す。
            self.trackInfoSection = self.title

        # SPEC #7: ライブ配信は duration=0 (もしくは 2^63-1) を返しうる。ZeroDivision を回避。
        if track.duration and track.duration > 0:
            playProgressPercentage = player.position / track.duration
            playDurationText = formatTime(track.duration / 1000)
        else:
            playProgressPercentage = 0
            playDurationText = "LIVE"
        playProgressBar = _progressBar(
            playProgressPercentage, bar, circle, graybar
        )
        self.playProgress = discord.ui.TextDisplay(
            f"-# 再生時間 `{formatTime(player.position / 1000)}"
            f" / {playDurationText}`\n"
            f"{playProgressBar}"
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

        volumeBar = _progressBar(player.volume / 100, bar, circle, graybar)
        self.volumeView = discord.ui.TextDisplay(
            f"-# ボリューム `{player.volume}%`\n{volumeBar}"
        )

        self.volumeActions = discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="-",
                custom_id="volumeDown",
                row=1,
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="+",
                custom_id="volumeUp",
            ),
        )

        timescale = player.get_filter("timescale")
        if not timescale:
            speed = 1.0
            pitch = 1.0
        else:
            speed = timescale.values["speed"]
            pitch = timescale.values["pitch"]

        speedBar = _progressBar(speed / 2.0, bar, circle, graybar)
        self.speedView = discord.ui.TextDisplay(
            f"-# 速度 `{round(speed * 100)}%`\n{speedBar}"
        )

        self.speedActions = discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="-",
                custom_id="speedDown",
                row=1,
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="+",
                custom_id="speedUp",
            ),
        )

        pitchBar = _progressBar(pitch / 2.0, bar, circle, graybar)
        self.pitchView = discord.ui.TextDisplay(
            f"-# ピッチ `{round(pitch * 100)}%`\n{pitchBar}"
        )

        self.pitchActions = discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="-",
                custom_id="pitchDown",
                row=1,
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                label="+",
                custom_id="pitchUp",
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
