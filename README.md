# neko's Music Bot
これはDiscordボット「neko's Music Bot」のソースコードです。  
[ボットはここから導入できます。](https://discord.com/oauth2/authorize?client_id=1315990542366281728)  

> [!CAUTION]
> https://github.com/nennneko5787/neko-s-Music-Bot/commit/f15d3f372d42792c83d9632af73ff8b3b189ad62 以前のコミットには、任意コード実行の脆弱性が存在します。  
> できる限り最新のコミットを使用することをおすすめします。  
> なお、この脆弱性はold_developmentやold_mainブランチのソースコードには存在しません。

## ブランチの説明
- lavalink - 現在開発中のバージョン(2024.12.10以降)のソースコードが入っています。
- ffmpeg - 以前のコード(2024.12.10以降)のソースコードが入っています。
- old_development - 2024.12.10以前の開発版のソースコードが入っています。
- old_main - 2023.12.05 ~ 2024.04.08 までのソースコードが入っています。

## セットアップ(lavalink ブランチ)

### 前提
- Python 3.13
- [uv](https://docs.astral.sh/uv/) (パッケージ管理)
- 稼働中の [Lavalink](https://github.com/lavalink-devs/Lavalink) v4+ ノード

### 手順

1. リポジトリを clone し、依存を同期:

```powershell
uv sync
```

2. `.env.example` を `.env` にコピーし、値を埋める(**キーは小文字のまま**):

```env
discord=<Discord Bot Token>
lavalink_host=<Lavalink host, e.g. 127.0.0.1>
lavalink_port=<Lavalink port, e.g. 2333>
lavalink_password=<Lavalink server password>
# 起動時に application commands を Discord へ登録し直す場合のみ 1(通常は空欄)
SYNC_COMMANDS=
```

3. Bot を起動:

```powershell
uv run python main.py
```

### コマンド定義を変えたとき

`SYNC_COMMANDS=1` にして 1 回起動 → コマンドが Discord 側へ登録されたら `SYNC_COMMANDS=` に戻す。毎起動 sync するとレート制限(429)に接触します。

### アプリケーション絵文字

このボットはパネル表示に `bar` / `circle` / `graybar` の 3 種類の Application Emoji を要求します。Discord Developer Portal でボットの Application Emoji として登録しておいてください。

### 開発ツール

- lint: `uv run ruff check .`
- 型チェック: `uv run pyright`
