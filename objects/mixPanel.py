import discord

from objects.progressBar import progressBar

from .player import MusicPlayer


class MixPanel(discord.ui.LayoutView):
    """音量 / 速度 / ピッチ の調整パネル。🎶 ボタンから ephemeral で開かれる。"""

    def __init__(self, player: MusicPlayer) -> None:
        super().__init__(timeout=None)

        volumeBar = progressBar(player.volume / 100)
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

        speedBar = progressBar(speed / 2.0)
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

        pitchBar = progressBar(pitch / 2.0)
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
