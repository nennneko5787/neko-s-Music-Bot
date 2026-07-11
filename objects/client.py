import contextlib
from typing import TYPE_CHECKING, cast

import discord
import lavalink
from lavalink.common import VoiceServerUpdatePayload, VoiceStateUpdatePayload
from lavalink.errors import ClientError

if TYPE_CHECKING:
    from objects.bot import MusicBot


class LavalinkVoiceClient(discord.VoiceProtocol):
    """
    This is the preferred way to handle external voice sending
    This client will be created via a cls in the connect method of the channel
    see the following documentation:
    https://discordpy.readthedocs.io/en/latest/api.html#voiceprotocol
    """

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
        # base VoiceProtocol declares `self.channel: abc.Connectable` — 再宣言せず
        # runtime は必ず VoiceChannel だが型は基底に合わせて Connectable のまま持ち、
        # 実利用点で cast する(SPEC Phase 4 §2b)。
        self.client = client
        self.channel = channel
        # guildId は VoiceChannel 前提でしかここに来ない(discord.py の connect 経路)
        self.guildId: int = cast(discord.VoiceChannel, channel).guild.id
        self._destroyed = False
        self.player: lavalink.DefaultPlayer | None = None
        self.track: lavalink.AudioTrack | None = None

        # D-5: cogs/music.py 側の on_ready で必ず先に Lavalink.Client を構築するため
        # 旧フォールバック(hasattr で自前 client 生成)は削除。music cog より先にここが
        # 走ると self.client.lavalink は AttributeError で正しく落ちる(旧フォールバックは
        # player=MusicPlayer 無しで作られる潜在爆弾だった)。
        self.lavalink: lavalink.Client = cast("MusicBot", self.client).lavalink

    async def on_voice_server_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        payload: VoiceServerUpdatePayload = {"t": "VOICE_SERVER_UPDATE", "d": data}
        await self.lavalink.voice_update_handler(payload)

    async def on_voice_state_update(self, data):
        # 注: data["channel_id"] は Discord ゲートウェイのペイロード形式(触らない)
        channelId = data["channel_id"]

        if not channelId:
            await self._destroy()
            return

        newChannel = self.client.get_channel(int(channelId))
        if newChannel is not None:
            # 実行時は必ず VoiceChannel(voice state update 由来)。
            self.channel = cast(discord.abc.Connectable, newChannel)

        # the data needs to be transformed before being handed down to
        # voice_update_handler
        payload: VoiceStateUpdatePayload = {"t": "VOICE_STATE_UPDATE", "d": data}

        await self.lavalink.voice_update_handler(payload)

    async def connect(
        self,
        *,
        timeout: float,  # noqa: ARG002 — discord.py VoiceProtocol 契約で必須(keyword で呼ばれる)
        reconnect: bool,  # noqa: ARG002 — 同上
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> None:
        """
        Connect the bot to the voice channel and create a player_manager
        if it doesn't exist yet.
        """
        channel = cast(discord.VoiceChannel, self.channel)
        # ensure there is a player_manager when creating a new voice_client
        self.player = self.lavalink.player_manager.create(guild_id=channel.guild.id)
        await channel.guild.change_voice_state(
            channel=channel, self_mute=self_mute, self_deaf=self_deaf
        )

    async def disconnect(self, *, force: bool = False) -> None:
        """
        Handles the disconnect.
        Cleans up running player and leaves the voice client.
        """
        channel = cast(discord.VoiceChannel, self.channel)
        player = self.lavalink.player_manager.get(channel.guild.id)

        if player is None:
            # 破棄済み(kick + _destroy 済み)の stale voice client からの
            # disconnect(force=True) は静かに no-op で返す(SPEC Phase 5 §2)。
            await channel.guild.change_voice_state(channel=None)
            await self._destroy()
            return

        # no need to disconnect if we are not connected
        if not force and not player.is_connected:
            return

        # None means disconnect
        await channel.guild.change_voice_state(channel=None)

        # update the channelId of the player to None
        # this must be done because the on_voice_state_update that would set channelId
        # to None doesn't get dispatched after the disconnect
        player.channel_id = None
        await self._destroy()

    async def _destroy(self):
        self.cleanup()

        if self._destroyed:
            # Idempotency handling, if `disconnect()` is called, the changed voice state
            # could cause this to run a second time.
            return

        self._destroyed = True

        with contextlib.suppress(ClientError):
            await self.lavalink.player_manager.destroy(self.guildId)
