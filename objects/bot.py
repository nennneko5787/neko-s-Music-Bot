import discord
import lavalink
from discord.ext import commands

from services.db import DBService

from .player import MusicPlayer


class BotStopPanel(discord.ui.LayoutView):
    def __init__(self, *, track: lavalink.AudioTrack, requestAuthor: discord.Member):
        super().__init__()

        self.trackInfoSection = discord.ui.TextDisplay(
            f"再生終了 - **[{track.title}]({track.uri})**\n-# {requestAuthor.mention} によるリクエスト\n-# ボットの再起動により停止されました"
        )
        container = discord.ui.Container(
            self.trackInfoSection,
            accent_color=discord.Color.red(),
        )
        self.add_item(container)
        return


class MusicBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.lavalink: lavalink.Client = None

    async def close(self):
        for voiceClient in self.voice_clients:
            await voiceClient.disconnect(force=True)

            player: MusicPlayer = voiceClient.player
            track = player.current
            channelId = track.extra["channelId"]
            messageId = track.extra["messageId"]

            channel = self.get_channel(channelId)
            message = await channel.fetch_message(messageId)

            member = await channel.guild.fetch_member(track.extra["requester"])

            await message.edit(
                view=BotStopPanel(track=track, requestAuthor=member),
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, users=False, roles=False, replied_user=False
                ),
            )

        await DBService.shutdown()

        return await super().close()
