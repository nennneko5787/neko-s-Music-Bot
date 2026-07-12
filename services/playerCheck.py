"""
プレイヤー接続前提の検証関数群。
SPEC_REFACTOR_PR1.md 第 3 段階で cogs/music.py から機械的に移設 +
SPEC_REFACTOR_PR5.md 第 3 段階で check デコレータと narrowing helper を追加。

- isInBotVoiceChannel: 呼び出し者と bot が同一 VC にいるかの判定(SPEC #14 荒らし対策)
- createPlayer: /play の @app_commands.check として使う事前検証+VC接続+player 生成
- requirePlaying: guild/voice_client/player の 3 段検証を行う @app_commands.check
- requireSameVC: 呼び出し者が bot と同じ VC にいることを検証する @app_commands.check
- resolveActivePlayer: requirePlaying 通過後のコマンド本体で voiceClient/player を narrow
"""
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
    """
    SPEC #14: 呼び出し者がボットと同じ VC にいる場合のみ True。
    パネルボタンと playback 変更コマンドで使う荒らし対策。
    """
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
    """
    @app_commands.check として使う。guild / voice_client / player の 3 段検証。
    失敗時は NoGuildError または MusicCommandError を raise し、
    main.onTreeError が ephemeral メッセージで返す(SPEC_REFACTOR_PR5.md §3.1)。
    """
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
    """
    @app_commands.check として使う。呼び出し者が bot と同じ VC にいることを検証(SPEC #14)。
    requirePlaying とは独立して voice_client の存在を検証するため、単独でも成立する。
    """
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
    """
    requirePlaying が通ったあとに呼び、確実に non-None な voiceClient と player を返す。
    pyright の narrowing は check 越しに保持されないため、明示的な cast + assert で対応。
    check を通っていない場合は AssertionError で早期発見する(実行時 assertion)。
    """
    assert interaction.guild is not None, "requirePlaying check must have passed"
    voiceClient = cast(LavalinkVoiceClient, interaction.guild.voice_client)
    player = cast(MusicPlayer, voiceClient.player)
    return voiceClient, player


async def createPlayer(interaction: discord.Interaction):
    """
    /play の @app_commands.check として関数参照で登録される事前検証。
    親 SPEC.md §5.4 の契約: `@app_commands.check(createPlayer)` に**関数参照**として渡され、
    discord.py が `(interaction)` の 1 引数で呼ぶ。self/cls を受け取ってはならない。
    """
    # SPEC #25: 元コードは検証前に player_manager.create() を呼ぶため、失敗した /play でも
    # lavalink プレイヤーがプロセス寿命まで残る。検証を全部通してから create する。
    if interaction.guild is None:
        raise NoGuildError()

    shouldConnect = (
        interaction.command is not None and interaction.command.name in ("play",)
    )

    voiceClient = interaction.guild.voice_client

    # DM 系の User インスタンスには .voice が無い(SPEC §5.1)。Member に絞る。
    if not isinstance(interaction.user, discord.Member):
        raise MusicCommandError(
            "このコマンドを実行するには、ボイスチャンネルに接続する必要があります。"
        )
    if not interaction.user.voice or not isinstance(
        interaction.user.voice.channel, discord.VoiceChannel
    ):
        if voiceClient is not None:
            raise MusicCommandError(
                "このコマンドを実行するには、ボットが接続しているチャンネルに接続する必要があります。"
            )

        raise MusicCommandError(
            "このコマンドを実行するには、ボイスチャンネルに接続する必要があります。"
        )

    voiceChannel = interaction.user.voice.channel

    if voiceClient is None:
        if not shouldConnect:
            raise MusicCommandError("現在音楽を再生していません。")

        permissions = voiceChannel.permissions_for(interaction.guild.me)

        if not permissions.connect or not permissions.speak:
            raise MusicCommandError(
                "このボットに `接続` 及び `発言` の権限が必要です。"
            )

        if (
            voiceChannel.user_limit > 0
            and len(voiceChannel.members) >= voiceChannel.user_limit
            and not interaction.guild.me.guild_permissions.move_members
        ):
            raise MusicCommandError(
                "ボイスチャンネルが満員のため、ボイスチャンネルに接続できません。"
            )

        # 全ての検証を通ったのでここで初めて player を作る
        client = cast(MusicBot, interaction.client)
        player: lavalink.DefaultPlayer = client.lavalink.player_manager.create(
            interaction.guild.id
        )
        assert interaction.channel is not None
        player.store("channel", interaction.channel.id)
        # SPEC #30: 受信音声データを消費しないので self_deaf=True で参加。
        await voiceChannel.connect(cls=LavalinkVoiceClient, self_deaf=True)
    else:
        existing = cast(LavalinkVoiceClient, voiceClient)
        existingChannel = cast(discord.VoiceChannel, existing.channel)
        if existingChannel.id != voiceChannel.id:
            raise MusicCommandError(
                "このコマンドを実行するには、ボットが接続しているチャンネルに接続する必要があります。"
            )

    return True
