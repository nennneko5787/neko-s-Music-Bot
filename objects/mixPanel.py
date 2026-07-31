import discord

from .ad import Ad
from .player import MusicPlayer


def _progressBar(percentage: float, bar: str, circle: str, graybar: str, length: int = 14) -> str:
    # SPEC #28: percentage>=1.0 では graybar 数が負になり circle も付けると length+1 文字にはみ出す。
    if percentage >= 1.0:
        return bar * length
    if percentage <= 0.0:
        return circle + graybar * (length - 1)
    filled = int(length * percentage)
    return bar * filled + circle + graybar * (length - filled - 1)


def _buildAdItems(ad: Ad) -> list[discord.ui.Item]:
    """
    MusicPanel 末尾に埋め込む広告セクション。SPEC_FEATURE_ADS §4.1 のレイアウト。
    Separator + Section(短文 + Thumbnail accessory)。
    """
    titleLine = f"**[{ad.title}]({ad.linkUrl})**" if ad.linkUrl else f"**{ad.title}**"
    return [
        discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
        discord.ui.Section(
            discord.ui.TextDisplay("-# 広告 / Ad"),
            discord.ui.TextDisplay(titleLine),
            discord.ui.TextDisplay(f"-# {ad.description}"),
            accessory=discord.ui.Thumbnail(media=ad.imageUrl, description=ad.title),
        ),
    ]


class MixPanel(discord.ui.LayoutView):
    def __init__(
        self,
        player: MusicPlayer,
        bar: str,
        circle: str,
        graybar: str,
    ) -> None:
        super().__init__(timeout=None)

        volumeBar = _progressBar(player.volume / 100, bar, circle, graybar)
        self.volumeView = discord.ui.TextDisplay(f"-# ボリューム `{player.volume}%`\n{volumeBar}")

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
        self.speedView = discord.ui.TextDisplay(f"-# 速度 `{round(speed * 100)}%`\n{speedBar}")

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
        self.pitchView = discord.ui.TextDisplay(f"-# ピッチ `{round(pitch * 100)}%`\n{pitchBar}")

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

        containerItems: list[discord.ui.Item] = [
            self.volumeView,
            self.volumeActions,
            self.speedView,
            self.speedActions,
            self.pitchView,
            self.pitchActions,
        ]

        container = discord.ui.Container(
            *containerItems,
            accent_color=discord.Color.purple(),
        )
        self.add_item(container)
