import contextlib
from typing import TYPE_CHECKING, cast

import discord
import lavalink
from lavalink.common import VoiceServerUpdatePayload, VoiceStateUpdatePayload
from lavalink.errors import ClientError

if TYPE_CHECKING:
    from objects.bot import MusicBot


class LavalinkVoiceClient(discord.VoiceProtocol):
    """lavalink へ音声送出を委譲する discord.VoiceProtocol 実装。"""

    __slots__ = (
        "_destroyed",
        "client",
        "guildId",
        "lavalink",
        "player",
        "track",
    )

    def __init__(
        self,
        client: discord.Client,
        channel: discord.abc.Connectable,
    ):
        # SPEC Phase 4 §2b: channel は基底の型に合わせて Connectable のまま持ち、利用点で cast する。
        self.client = client
        self.channel = channel
        self.guildId: int = cast(discord.VoiceChannel, channel).guild.id
        self._destroyed = False
        self.player: lavalink.DefaultPlayer | None = None
        self.track: lavalink.AudioTrack | None = None

        # SPEC D-5: music cog の on_ready より先に来た場合は AttributeError で落として良い。
        self.lavalink: lavalink.Client = cast("MusicBot", self.client).lavalink

    async def on_voice_server_update(self, data):
        payload: VoiceServerUpdatePayload = {"t": "VOICE_SERVER_UPDATE", "d": data}
        await self.lavalink.voice_update_handler(payload)

    async def on_voice_state_update(self, data):
        # data のキーは Discord ゲートウェイのペイロード形式(触らない)
        channelId = data["channel_id"]

        if not channelId:
            await self._destroy()
            return

        newChannel = self.client.get_channel(int(channelId))
        if newChannel is not None:
            self.channel = cast(discord.abc.Connectable, newChannel)

        payload: VoiceStateUpdatePayload = {"t": "VOICE_STATE_UPDATE", "d": data}

        await self.lavalink.voice_update_handler(payload)

    async def connect(
        self,
        *,
        timeout: float,  # noqa: ARG002 — VoiceProtocol 契約で必須
        reconnect: bool,  # noqa: ARG002 — 同上
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> None:
        channel = cast(discord.VoiceChannel, self.channel)
        self.player = self.lavalink.player_manager.create(guild_id=channel.guild.id)
        await channel.guild.change_voice_state(channel=channel, self_mute=self_mute, self_deaf=self_deaf)

    async def disconnect(self, *, force: bool = False) -> None:
        """VC から切断し、lavalink プレイヤーを破棄する。"""
        channel = cast(discord.VoiceChannel, self.channel)
        player = self.lavalink.player_manager.get(channel.guild.id)

        if player is None:
            # SPEC Phase 5 §2: 破棄済みの stale voice client からの呼び出しは no-op。
            await channel.guild.change_voice_state(channel=None)
            await self._destroy()
            return

        if not force and not player.is_connected:
            return

        await channel.guild.change_voice_state(channel=None)

        # 切断後は channelId を None にする on_voice_state_update が来ないため手動で消す
        player.channel_id = None
        await self._destroy()

    async def _destroy(self):
        self.cleanup()

        if self._destroyed:
            # disconnect() 経由の voice state 変化で二度呼ばれうる
            return

        self._destroyed = True

        with contextlib.suppress(ClientError):
            await self.lavalink.player_manager.destroy(self.guildId)
