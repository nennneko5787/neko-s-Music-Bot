import discord
import lavalink

from objects.progressBar import progressBar
from objects.utils import formatTime

from .ad import Ad
from .player import MusicPlayer


class WaitingView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

        self.trackInfoSection = discord.ui.TextDisplay("準備中")
        container = discord.ui.Container(
            self.trackInfoSection,
            accent_color=discord.Color.red(),
        )
        self.add_item(container)


def _buildAdItems(ad: Ad) -> list[discord.ui.Item]:
    """パネル末尾に埋め込む広告セクション。SPEC_FEATURE_ADS §4.1。"""
    titleLine = f"**[{ad.title}]({ad.linkUrl})**" if ad.linkUrl else f"**{ad.title}**"
    items: list[discord.ui.Item] = [
        discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
        discord.ui.Section(
            discord.ui.TextDisplay("-# 広告 / Ad"),
            discord.ui.TextDisplay(titleLine),
            discord.ui.TextDisplay(f"-# {ad.description}"),
            accessory=discord.ui.Thumbnail(media=ad.imageUrl, description=ad.title),
        ),
    ]
    # Section の子は TextDisplay 3 個までなので、ボタンは兄弟の ActionRow として置く。
    if ad.linkUrl:
        items.append(
            discord.ui.ActionRow(
                discord.ui.Button(style=discord.ButtonStyle.link, label="リンク先を開く", url=ad.linkUrl),
            )
        )
    return items


class MusicPanel(discord.ui.LayoutView):
    def __init__(
        self,
        player: MusicPlayer,
        track: lavalink.AudioTrack,
        requestAuthorMention: str,
        *,
        finished: bool = False,
        ad: Ad | None = None,
    ) -> None:
        super().__init__(timeout=None)

        if not finished:
            if player.is_playing:
                if player.paused:
                    titleText = (
                        f"⏸️一時停止中 - **[{track.title}]({track.uri})**\n-# {requestAuthorMention} によるリクエスト"
                    )
                else:
                    titleText = (
                        f"🎶再生中 - **[{track.title}]({track.uri})**\n-# {requestAuthorMention} によるリクエスト"
                    )
            else:
                titleText = f"再生準備中 - **[{track.title}]({track.uri})**\n-# {requestAuthorMention} によるリクエスト"
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

        # SPEC #7: ライブ配信は duration=0 を返しうるので ZeroDivision を回避する。
        if track.duration and track.duration > 0:
            playProgressPercentage = player.position / track.duration
            playDurationText = formatTime(track.duration / 1000)
        else:
            playProgressPercentage = 0
            playDurationText = "LIVE"
        playProgressBar = progressBar(playProgressPercentage, length=11, showCircle=True)
        self.playProgress = discord.ui.TextDisplay(
            f"{titleText}\n`{formatTime(player.position / 1000)} / {playDurationText}`\n{playProgressBar}"
        )

        if track.artwork_url:
            self.thumbnail = discord.ui.Thumbnail(media=track.artwork_url, description=track.title)
            self.trackInfoSection = discord.ui.Section(self.playProgress, accessory=self.thumbnail)
        else:
            # SPEC #4: アートワーク無しでも同じ情報行を出す。
            self.trackInfoSection = self.playProgress

        self.playActions = discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏮",
                custom_id="prev",
                row=1,
                disabled=(player.prevQueue.qsize() <= 0),
            ),
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
                style=discord.ButtonStyle.blurple,
                emoji="⏭",
                custom_id="next",
                row=1,
                disabled=(len(player.queue) <= 0),
            ),
        )

        self.playActions2 = discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.blurple if player.shuffle else discord.ButtonStyle.gray,
                emoji="🔀",
                custom_id="shuffle",
                row=1,
            ),
            discord.ui.Button(
                style=(
                    discord.ButtonStyle.gray
                    if player.loop == player.LOOP_NONE
                    else discord.ButtonStyle.green
                    if player.loop == player.LOOP_SINGLE
                    else discord.ButtonStyle.blurple
                ),
                emoji="🔄" if player.loop == player.LOOP_NONE else "🔂" if player.loop == player.LOOP_SINGLE else "🔄",
                custom_id="loop",
                row=0,
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="📶",
                custom_id="mix",
                row=0,
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji="⏹",
                custom_id="stop",
                row=1,
            ),
        )

        containerItems: list[discord.ui.Item] = [
            self.trackInfoSection,
            self.playActions,
            self.playActions2,
        ]
        # SPEC_FEATURE_ADS §4.1: ad があれば末尾に埋め込む。
        if ad is not None:
            containerItems.extend(_buildAdItems(ad))

        container = discord.ui.Container(
            *containerItems,
            accent_color=discord.Color.purple(),
        )
        self.add_item(container)
