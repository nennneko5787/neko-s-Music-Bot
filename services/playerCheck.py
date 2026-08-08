from typing import cast

import discord
import lavalink

from objects.bot import MusicBot
from objects.client import LavalinkVoiceClient
from objects.exceptions import MusicCommandError, NoGuildError
from objects.player import MusicPlayer


def isInBotVoiceChannel(
    interaction: discord.Interaction,
    voiceClient: LavalinkVoiceClient,
) -> bool:
    """SPEC #14: 呼び出し者がボットと同じ VC にいる場合のみ True。"""
    user = interaction.user
    if not isinstance(user, discord.Member):
        return False
    userVoice = user.voice
    if userVoice is None or userVoice.channel is None:
        return False
    botChannel = cast(discord.VoiceChannel | None, voiceClient.channel)
    if botChannel is None:
        return False
    return userVoice.channel.id == botChannel.id


async def requirePlaying(interaction: discord.Interaction) -> bool:
    """@app_commands.check。guild / voice_client / player の 3 段検証。"""
    if interaction.guild is None:
        raise NoGuildError()
    voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
    if not voiceClient:
        raise MusicCommandError("コマンドを実行する前に、曲を再生してください。")
    player = cast(MusicPlayer | None, voiceClient.player)
    if player is None:
        raise MusicCommandError("コマンドを実行する前に、曲を再生してください。")
    return True


async def requireSameVC(interaction: discord.Interaction) -> bool:
    """@app_commands.check。呼び出し者が bot と同じ VC にいることを検証する(SPEC #14)。"""
    if interaction.guild is None:
        raise NoGuildError()
    voiceClient = cast(LavalinkVoiceClient | None, interaction.guild.voice_client)
    if voiceClient is None:
        raise MusicCommandError("コマンドを実行する前に、曲を再生してください。")
    if not isInBotVoiceChannel(interaction, voiceClient):
        raise MusicCommandError("ボットと同じボイスチャンネルに参加してください。")
    return True


def resolveActivePlayer(
    interaction: discord.Interaction,
) -> tuple[LavalinkVoiceClient, MusicPlayer]:
    """requirePlaying 通過後に呼び、non-None な voiceClient と player を返す。"""
    assert interaction.guild is not None, "requirePlaying check must have passed"
    voiceClient = cast(LavalinkVoiceClient, interaction.guild.voice_client)
    player = cast(MusicPlayer, voiceClient.player)
    return voiceClient, player


async def createPlayer(interaction: discord.Interaction):
    """
    /play の @app_commands.check。事前検証 + VC 接続 + player 生成。
    SPEC §5.4: 関数参照として渡されるため self/cls を受け取ってはならない。
    SPEC #25: player の生成は全検証を通ったあとに行う。
    """
    if interaction.guild is None:
        raise NoGuildError()

    shouldConnect = interaction.command is not None and interaction.command.name in ("play",)

    voiceClient = interaction.guild.voice_client

    # SPEC §5.1: DM 系の User には .voice が無いため Member に絞る。
    if not isinstance(interaction.user, discord.Member):
        raise MusicCommandError("このコマンドを実行するには、ボイスチャンネルに接続する必要があります。")
    if not interaction.user.voice or not isinstance(interaction.user.voice.channel, discord.VoiceChannel):
        if voiceClient is not None:
            raise MusicCommandError(
                "このコマンドを実行するには、ボットが接続しているチャンネルに接続する必要があります。"
            )

        raise MusicCommandError("このコマンドを実行するには、ボイスチャンネルに接続する必要があります。")

    voiceChannel = interaction.user.voice.channel

    if voiceClient is None:
        if not shouldConnect:
            raise MusicCommandError("現在音楽を再生していません。")

        permissions = voiceChannel.permissions_for(interaction.guild.me)

        if not permissions.connect or not permissions.speak:
            raise MusicCommandError("このボットに `接続` 及び `発言` の権限が必要です。")

        if (
            voiceChannel.user_limit > 0
            and len(voiceChannel.members) >= voiceChannel.user_limit
            and not interaction.guild.me.guild_permissions.move_members
        ):
            raise MusicCommandError("ボイスチャンネルが満員のため、ボイスチャンネルに接続できません。")

        client = cast(MusicBot, interaction.client)
        player: lavalink.DefaultPlayer = client.lavalink.player_manager.create(interaction.guild.id)
        assert interaction.channel is not None
        player.store("channel", interaction.channel.id)
        # SPEC #30: 受信音声データを消費しないので self_deaf=True。
        await voiceChannel.connect(cls=LavalinkVoiceClient, self_deaf=True)
    else:
        existing = cast(LavalinkVoiceClient, voiceClient)
        existingChannel = cast(discord.VoiceChannel, existing.channel)
        if existingChannel.id != voiceChannel.id:
            raise MusicCommandError(
                "このコマンドを実行するには、ボットが接続しているチャンネルに接続する必要があります。"
            )

    return True
