import discord
from discord import Interaction, Locale, Member
from discord.app_commands import TranslationContext, Translator, locale_str

TLANSLATION_DATA: dict[Locale, dict[str, str]]= {
	Locale.japanese: {
		'Plays the music specified by url. If music is already being played, it is inserted into the cue.': 'urlで指定された音楽を再生します。すでに音楽が再生されている場合はキューに挿入します。',
		'Searches Youtube for the specified words or phrases. If music is already playing, it will be inserted into the cue.': '指定された語句でYoutubeを検索します。すでに音楽が再生されている場合は、キューに挿入されます。',
		'Connected to voice channel.': 'ボイスチャンネルに接続しました。',
		'Destination Channel': '接続先チャンネル',
		'You are not currently connecting to any voice channel.': 'あなたはボイスチャンネルに接続していません。',
		'Error!': 'エラーが発生しました。',
		'Starts playing the song.': '曲の再生を開始します。',
		'Song inserted into the queue.': '曲をキューに挿入しました。',
		'Video title': 'タイトル',
		'Video URL': '動画URL',
		'Stops the music currently playing and discards the cue.': '今再生している音楽を停止して、キューを破棄します。',
		"neko's Music Bot is not connected to the voice channel.": "neko's Music Botはボイスチャンネルに接続していません。",
		"The song was stopped and the queue was discarded.": "曲を停止し、キューを破棄しました。",
		"The song does not seem to be playing.": "曲が再生されていないようです。",
		"Skips the currently playing music and plays the next music in the queue.": "今再生している音楽をスキップして、キューに入っている次の音楽を再生します。",
		"Skipped one song.": "曲を一曲スキップしました。",
		"Pause the song.": "曲を一時停止しました。",
		"Song paused.": "曲を一時停止しました。",
		"Resume paused song.": "一時停止した音楽を再開します。",
		"Resumed songs that had been paused.": "一時停止していた曲を再開しました。",
		"You can check the available commands.": "使用できるコマンドを確認することができます。",
		"Disconnected from voice channel.": "ボイスチャンネルから切断しました。",
		"Disconnected channel": "切断したチャンネル",
		"Disconnected from voice channel.": "ボイスチャンネルからの接続が切れています",
		"Waiting for song playback": "曲の再生を待機中",
		"*Nico Nico Douga videos take a little time to play. Please understand.": "※ニコニコ動画の動画は再生に少し時間がかかります。ご了承ください。",
		"Playing": "再生中",
		"No songs in queue": "キューに入っている曲はありません",
	},
}

FMT_TLANSLATION_DATA: dict[Locale, dict[str, str]] = {
	Locale.japanese: {
		'Rest assured, the error log has been sent automatically to the developer. The error log has been automatically sent to the developer. \nIf you need a support, please join the [support server](https://discord.gg/PN3KWEnYzX). \nThe following is a traceback of the ```python\n{traceback}\n```': '安心してください。エラーログは開発者に自動的に送信されました。\nサポートが必要な場合は、[サポートサーバー](https://discord.gg/PN3KWEnYzX) に参加してください。\n以下、トレースバックです。```python\n{traceback}\n```',
		'{entries_count} songs inserted into the queue.': '{entries_count}個の曲をキューに挿入しました。'
	},
}

class MyTranslator(Translator):
	async def translate(self, string: locale_str, locale: Locale, context: TranslationContext):
		if 'fmt_arg' in string.extras:
			fmt = FMT_TLANSLATION_DATA.get(locale, {}).get(string.message, string.message)
			return fmt.format(**(string.extras['fmt_arg']))
		if TLANSLATION_DATA.get(locale, {}).get(string.message) != None:
			return TLANSLATION_DATA.get(locale, {}).get(string.message)
		else:
			return string
