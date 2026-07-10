from typing import cast

import discord
import lavalink
from discord.ext import commands

from .client import LavalinkVoiceClient
from .player import MusicPlayer
from .utils import resolveMemberMention


class BotStopPanel(discord.ui.LayoutView):
    def __init__(self, *, track: lavalink.AudioTrack, requestAuthorMention: str):
        super().__init__()

        self.trackInfoSection = discord.ui.TextDisplay(
            f"再生終了 - **[{track.title}]({track.uri})**\n"
            f"-# {requestAuthorMention} によるリクエスト\n"
            f"-# ボットの再起動により停止されました"
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

        self.lavalink: lavalink.Client

    async def close(self):
        # SPEC Phase 5 §1 — 破棄前に state を吸い上げてから disconnect する。
        # 途中で None やチャンネル種別ミスマッチに当たったら黙ってスキップ
        # (再生中でない・パネル未投稿・チャンネル削除済みなど)。
        for voiceClient in self.voice_clients:
            if not isinstance(voiceClient, LavalinkVoiceClient):
                await voiceClient.disconnect(force=True)
                continue

            player = cast(MusicPlayer | None, voiceClient.player)
            if player is None:
                await voiceClient.disconnect(force=True)
                continue

            track = player.current
            channelId = player.fetch("channelId")
            messageId = player.fetch("messageId")

            if track is None or channelId is None or messageId is None:
                await voiceClient.disconnect(force=True)
                continue

            channel = self.get_channel(channelId)
            if not isinstance(channel, discord.abc.Messageable):
                await voiceClient.disconnect(force=True)
                continue

            guild = getattr(channel, "guild", None)
            if guild is None:
                await voiceClient.disconnect(force=True)
                continue

            try:
                message = await channel.fetch_message(messageId)
            except (discord.NotFound, discord.Forbidden):
                await voiceClient.disconnect(force=True)
                continue

            # SPEC #15: fetch_member は NotFound で落ちうる — resolveMemberMention でフォールバック。
            requestAuthorMention = await resolveMemberMention(
                guild, track.extra["requester"]
            )

            await message.edit(
                view=BotStopPanel(track=track, requestAuthorMention=requestAuthorMention),
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, users=False, roles=False, replied_user=False
                ),
            )
            await voiceClient.disconnect(force=True)

        return await super().close()
