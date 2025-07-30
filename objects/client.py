import os

import discord
import dotenv
import lavalink
from lavalink.errors import ClientError

dotenv.load_dotenv()


class LavalinkVoiceClient(discord.VoiceProtocol):
    """
    This is the preferred way to handle external voice sending
    This client will be created via a cls in the connect method of the channel
    see the following documentation:
    https://discordpy.readthedocs.io/en/latest/api.html#voiceprotocol
    """

    __slots__ = (
        "client",
        "channel",
        "guildId",
        "_destroyed",
        "player",
        "lavalink",
        "track",
    )

    def __init__(
        self,
        client: discord.Client,
        channel: discord.abc.Connectable,
    ):
        self.client = client
        self.channel: discord.VoiceChannel = channel
        self.guildId = channel.guild.id
        self._destroyed = False
        self.player: lavalink.DefaultPlayer = None
        self.track: lavalink.AudioTrack = None

        if not hasattr(self.client, "lavalink"):
            # Instantiate a client if one doesn't exist.
            # We store it in `self.client` so that it may persist across cog reloads,
            # however this is not mandatory.
            self.client.lavalink = lavalink.Client(client.user.id)
            self.client.lavalink.add_node(
                host=os.getenv("lavalink_host"),
                port=int(os.getenv("lavalink_port")),
                password=os.getenv("lavalink_password"),
                region="jp-1",
                name="jp-1",
            )

        # Create a shortcut to the Lavalink client here.
        self.lavalink: lavalink.Client = self.client.lavalink

    async def on_voice_server_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalinkData = {"t": "VOICE_SERVER_UPDATE", "d": data}
        await self.lavalink.voice_update_handler(lavalinkData)

    async def on_voice_state_update(self, data):
        channelId = data["channel_id"]

        if not channelId:
            await self._destroy()
            return

        self.channel = self.client.get_channel(int(channelId))

        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalinkData = {"t": "VOICE_STATE_UPDATE", "d": data}

        await self.lavalink.voice_update_handler(lavalinkData)

    async def connect(
        self,
        *,
        timeout: float,
        reconnect: bool,
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> None:
        """
        Connect the bot to the voice channel and create a player_manager
        if it doesn't exist yet.
        """
        # ensure there is a player_manager when creating a new voice_client
        self.player = self.lavalink.player_manager.create(
            guild_id=self.channel.guild.id
        )
        await self.channel.guild.change_voice_state(
            channel=self.channel, self_mute=self_mute, self_deaf=self_deaf
        )

    async def disconnect(self, *, force: bool = False) -> None:
        """
        Handles the disconnect.
        Cleans up running player and leaves the voice client.
        """
        player: lavalink.DefaultPlayer = self.lavalink.player_manager.get(
            self.channel.guild.id
        )

        # no need to disconnect if we are not connected
        if not force and not player.is_connected:
            return

        # None means disconnect
        await self.channel.guild.change_voice_state(channel=None)

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

        try:
            await self.lavalink.player_manager.destroy(self.guildId)
        except ClientError:
            pass
