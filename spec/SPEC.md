# SPEC.md — Lint エラー修正仕様書(仕様駆動開発)

対象ブランチ: `lavalink` / 作成日: 2026-07-10 / 改訂1: D-2・D-3 決定済み(支援者コード機能と DB 層の廃止)、実装原則 §4.1 追加 / 改訂2: 追加調査で確認した実バグ・課題を §8.1 に追記

この文書は、本リポジトリの lint / 型チェックエラーをゼロにするための**実装仕様**である。
各フェーズは独立してコミットできる粒度で定義し、フェーズごとに受け入れ基準を持つ。
実装者(人間・AI 問わず)は **§5 の不変条件を最優先** で守ること。lint を通すために不変条件を壊すことは絶対に認めない。

---

## 1. 背景と現状

計測環境(2026-07-10 時点、`lavalink` ブランチ作業ツリー):

| ツール | 実行条件 | 件数 |
|---|---|---|
| ruff 0.15.21 | `--select F,E,W,I,N,UP,B,SIM,ARG,RUF`(line-length 88) | **131 件** |
| pyright 1.1.411 | standard モード、`.venv` 参照 | **156 件**(エラー155 + 警告1) |

`pyproject.toml` には `[tool.ruff]` / `[tool.pyright]` セクションが存在せず、lint 設定は未整備。

内訳(主要ルール):

- ruff: N806×61, N802×26, E501×12, SIM112×6, UP035/UP006×6, RUF001×3, N803×3, RUF023×2, N815×2, N812×2, ARG002×2, その他(UP045, UP015, SIM102/105/108, N805)
- pyright: reportAttributeAccessIssue×47, reportOptionalMemberAccess×44, reportArgumentType×26, reportAssignmentType×20, reportGeneralTypeIssues×12, reportOptionalSubscript×3, reportMissingImports×2, reportIncompatibleVariableOverride×1, reportSelfClsParameterName×1(警告)
- pyright 診断の 124/156 件(エラー123+警告1)は `cogs/music.py` に集中

**重大な発見**: pyright の `reportMissingImports` 2件は設定ミスではなく**起動不能バグ**である(§7 Phase 1 参照)。現在このブランチはボットが起動できない。

## 2. ゴールと受け入れ基準

全フェーズ完了時に以下がすべて成立すること:

1. `uv run ruff check .` → **エラー 0 件**(§7 Phase 0 の設定で)
2. `uv run pyright` → **エラー 0 件、警告 0 件**
3. `uv run python -c "import main, cogs.music, cogs.ping, cogs.help"` が成功する(現状は `cogs.music` で ModuleNotFoundError)
4. Discord 上での可視挙動(コマンド名、オプション名、ボタン、埋め込みテキスト)が**1文字も変わらない**。例外は2つだけ: §7 Phase 5 で明示した実バグ修正と、**D-2 で決定した /code・/ranking コマンドの削除**(削除後の `bot.tree.sync()` で Discord 側からも消える)
5. 既存の `.env` がそのまま使える(Postgres は D-2 により廃止のため対象外)

## 3. スコープ外(Non-goals)

- 機能追加・UI 文言の変更・リアーキテクチャ
- lint に flag されていない camelCase 属性の網羅的リネーム(例: `MusicPlayer.prevQueue` / `lastUpdated` は ruff に flag されていないため**触らない**。触る場合は cogs/music.py:182,207,216 / objects/panel.py:121 との協調変更になり、リスクに見合わない)
- §8 バックログの実バグ修正(lint 通過に必要なものだけ Phase 5 で扱う)

## 4. リスク分類

各修正項目は次の3分類のいずれかを持つ:

- **safe-auto**: ツールの自動修正をそのまま採用可
- **mechanical**: 手作業だが挙動不変(リネーム+参照更新、型注釈追加など)
- **behavioral**: 実行時挙動が変わる(クラッシュ→スキップ等)。個別に判断・記録すること

### 4.1 実装原則 — 「エラーを消すためのハック」の禁止

lint / 型エラーは**根本原因を直す**こと。チェッカーを黙らせるだけの小細工は、件数がゼロになっても本仕様の不合格とする。具体的に禁止するもの:

1. **無差別な抑制**: 素の `# noqa`(ルールコード無し)、`# type: ignore`(エラーコード無し)、ファイル先頭の `# ruff: noqa`、ファイル・ディレクトリ単位の pyright 除外による「解決」
2. **設定の弱体化**: `typeCheckingMode` の引き下げ、エラーを消す目的でのルールカテゴリ丸ごと ignore 追加(Phase 0 に明記したもの以外)。設定による抑制が許されるのは、この仕様が明示的に指定した箇所のみ(RUF001-003、D-1 の SIM112、ARG002 の2行)
3. **チェッカーへの嘘**: 実際に None が到達しうる箇所への `assert x is not None`(そこは Phase 5 の実ガード対象)/ 実行時型が保証されていない `cast()` / `Any` への逃がし / `getattr`・`setattr` による属性アクセスの間接化 / 例外の握りつぶし(`try/except: pass`)による型エラー回避
4. **仕様外のコード削除**: エラーを消す目的での機能・分岐の削除(削除してよいのは D-2 で決定した範囲のみ)
5. **契約の書き換え**: §5 の不変条件(文字列リテラル、公開名、シグネチャ)を変えて型を合わせること

許可される抑制は**個別行への理由コメント付き・ルールコード指定**のみ(例: `# noqa: ARG002 — discord.py VoiceProtocol 契約で必須の引数`)。`cast()` はアーキテクチャ上ランタイム型が保証される場所(例: voice_client は常に LavalinkVoiceClient)に限り、可能なら `isinstance` narrowing を優先する。

## 5. 不変条件 — 絶対に壊してはならない契約

### 5.1 Discord に公開されている名前

- スラッシュコマンド名は全て明示的な `name=` kwarg で定義済み(全11コマンド検証済み: play/timescale/volume/queue/loop/toggle/stop/ping/help + D-2 で削除する code/ranking)。**コールバック関数のリネームは安全だが、`name=` kwarg を消してはならない。**
- **コマンドのパラメータ名はユーザーに見える公開 API。** `@app_commands.rename` が無いパラメータ — `speed`(cogs/music.py:652)、`loop`(cogs/music.py:714)、`code`(cogs/music.py:809)— は**リネーム禁止**(N806/N803 の一括修正から除外すること)。

### 5.2 文字列リテラルの契約

- **ボタンの `custom_id`**(`"volumeDown"`, `"speedUp"`, `"pitchDown"`, `"queuePagenation,{n}"` 等 / objects/panel.py:86-222, cogs/music.py:358,368,376)は、投稿済み Discord メッセージの中に永続化されており、cogs/music.py:195-292 の文字列マッチで dispatch される。**camelCase のままにする。1バイトも変更禁止。**
- **`player.store()/fetch()` のキー文字列** `"channelId"` / `"messageId"` / `"channel"`(cogs/music.py:228-229,442,638-639 ほか)は objects/bot.py:35-36 と共有するファイル間契約。変数はリネームしても**キー文字列は変更禁止**。
- **日本語 UI 文字列は表示結果を1文字も変えない。** 全角「!」(main.py:75, cogs/music.py:836)は正しい日本語表記であり、RUF001 の「修正」を適用してはならない(設定で抑制する)。E501 の折り返しも暗黙の隣接文字列連結で行い、描画結果をバイト単位で同一に保つこと。

### 5.3 環境変数キー(小文字が本番契約)

`discord`(main.py:95)、`lavalink_host` / `lavalink_port` / `lavalink_password`(objects/client.py:47-49, cogs/music.py:103-105)は、ユーザーの実 `.env` に小文字で存在する(`dsn` は D-2 の migrations/ 削除とともに消滅)。リポジトリに `.env.example` は無く、キー名の記録はコードだけである。Linux では `os.environ` は大文字小文字を区別するため、**コード側だけ大文字化すると本番起動が壊れる(Windows 開発機では気づけない)**。→ 方針は §6 D-1。

### 5.4 フレームワークが名前・シグネチャで解決するもの

- `@bot.event` は関数 `__name__` で登録する: `on_ready`(main.py:42)、`setup_hook`(main.py:87)は**リネーム禁止**。
- `@commands.Cog.listener()`(name= なし)も同様: `on_ready`(cogs/music.py:88)、`on_interaction`(cogs/music.py:185)は**リネーム禁止**。
- `LavalinkVoiceClient` のメソッド名は discord.py VoiceProtocol 契約: `connect` / `disconnect` / `on_voice_server_update` / `on_voice_state_update`(objects/client.py)は**リネーム禁止**。
- `connect(timeout=…, reconnect=…)` は discord.py がキーワード渡しで呼ぶ(discord/abc.py:2149)。ARG002(未使用引数)は**削除もアンダースコア化も禁止、抑制のみ**。
- `MusicQueue._get`(objects/queue.py:5)は asyncio.Queue のオーバーライド契約名。また `self._queue.pop()`(右端 pop = LIFO)は「前の曲」履歴スタックの**意図的な仕様**。`popleft()` に変えたら機能が壊れる。
- `MusicPlayer.__init__(self, guild_id, node)` は lavalink.py が**位置引数2つで**インスタンス化する(playermanager.py:253)。シグネチャ変更禁止。
- `createPlayer`(cogs/music.py:399)は `@app_commands.check(createPlayer)`(:587)に**素の関数として**渡され、discord.py が `(interaction)` の1引数で呼ぶ。**N805 の「第1引数を self にする」自動修正を適用したら /play の権限チェックが静かに壊れる。**絶対に適用しないこと(正しい修正は Phase 4-6)。
- `@Lavalink.listener(EventType)` のフック(onTrackEnd 等)は関数の属性 `_lavalink_events` で登録される(名前ではない)ため、リネーム**可**。

### 5.5 pydantic モデルと Postgres の契約 — **D-2 の決定により廃止**

(改訂1)この節の契約は、支援者コード機能・DB 層の全面削除(D-2)により消滅した。`objects/guilds.py` / `objects/members.py` は既に作業ツリーから削除済みであり、復活させないこと。N815(mixedCase フィールド)2件も削除により解消する。

## 6. 要決定事項

実装前にオーナー(nennneko5787)が決めること。推奨(★)はデフォルトとして採用してよい。

### D-1: SIM112(環境変数キーの小文字)★ 現状維持+ルール抑制

- **★ 案a**: キーは小文字のまま、`SIM112` を設定で無効化(または該当行 `# noqa: SIM112`)。`.env.example` を新規追加してキー名を文書化する。
- 案b: `LAVALINK_HOST` 等へ大文字化。**条件**: 本番 `.env`・デプロイ先のシークレットを同時に更新し、読み取り箇所(objects/client.py:47-49, cogs/music.py:103-105)を一括変更すること。

### D-2: 削除済み DB 層(起動ブロッカー)— **決定済み: 支援者コード機能とその特典を廃止し、DB 関連を全面削除する**

(改訂1でオーナー決定)`/code`(支援者コード入力)とその特典を廃止する。コード上の依存関係(検証済み)は次のとおり: 特典の実体は **/ranking(サポーター限定のサーバー内再生ランキング)** であり(cogs/music.py:851 が `expiresAt` で入場ゲート)、/play 内の再生履歴記録(`playedMusics`)は /ranking のためだけに存在する。したがって削除範囲は以下で閉じる(実施手順は Phase 1):

- `/code` コマンド本体(cogs/music.py:806-840)と `key.txt` 読み込み(:814、aiofiles の唯一の利用箇所)
- `/ranking` コマンド本体(cogs/music.py:842-878)
- **/help 内の案内**: cogs/help.py の `/code` フィールド(:34-38)と `/ranking` フィールド(:39-43)。消し忘れると存在しないコマンドを案内する嘘ヘルプになる
- /play 内の履歴記録(cogs/music.py:596, 610-612, 623, 627)
- import 群: cogs/music.py:24-25(services.guilds / services.members)、:30(objects.guilds の MusicData)、:11(aiofiles)、および削除で未使用になるもの(`Counter` :7、`tokyo` :37、`Dict` など。ruff の F401/F811 検出に従い機械的に除去)
- モデル `objects/guilds.py` / `objects/members.py`(**削除済み・復活させない**)、`services/db.py` / `services/guilds.py` / `services/members.py`(削除済み)
- `alembic.ini` + `migrations/` ディレクトリ(D-3)
- 依存パッケージ: `pydantic`、`aiofiles` を pyproject.toml から除去(両方とも他に利用箇所が無いことを grep で検証済み)。`tzdata` も `tokyo` 削除後に他で不要なら除去してよい(要 grep 確認)。その後 `uv lock` / `uv sync`
- 運用側: デプロイ先の `key.txt`・Postgres(`dsn`)は不要になる

**注意**: 「import 行だけ消す」のは禁止 — 上記の呼び出し箇所全体をセットで削除すること。/code・/ranking の削除はユーザー可視のコマンド廃止であり、§2 受け入れ基準4 の明示的例外である。

### D-3: alembic 残骸 — **決定済み: 削除**

`alembic.ini` + `migrations/` は D-2 とともに削除する(現時点でも alembic/sqlalchemy が依存に無いデッドコード)。削除後は Phase 0 設定内の `migrations` 除外指定は無意味になるので、除外を書かずに済む(下記設定から除去済み)。

### D-4: E501(行長)★ line-length = 120

日本語 UI 文字列が原因の大半。`line-length = 120` にし、それでも超える行 — cogs/ping.py:39(161 桁)、cogs/music.py:350(166 桁、キュー一覧の f-string)、objects/bot.py:13(142 桁)— だけ隣接文字列連結で折る(描画結果バイト同一の原則は §5.2)。

### D-5: objects/client.py の重複 lavalink ブートストラップ ★ 削除

objects/client.py:41-52 に cogs/music.py:101-108 と重複するフォールバックがあるが、こちらは `player=MusicPlayer` **無し**で Client を作るため、先に実行されると `player.ping` / `prevQueue` 参照(cogs/ping.py:28 等)が全て AttributeError になる潜在爆弾。music cog が必ず先に初期化する前提なら**フォールバックごと削除**(★)。残すなら `player=MusicPlayer` を必ず付ける。

## 7. 実装フェーズ

### Phase 0: ツール設定(safe-auto)

1. dev 依存を追加: `uv add --dev ruff pyright`
2. `pyproject.toml` に追記:

```toml
[tool.ruff]
line-length = 120
target-version = "py313"

[tool.ruff.lint]
select = ["F", "E", "W", "I", "N", "UP", "B", "SIM", "ARG", "RUF"]
# RUF001-003: 日本語 UI の全角記号(！ など)は正しい表記。ASCII 化はユーザー可視の文言変更になるため抑制。
ignore = ["RUF001", "RUF002", "RUF003"]

[tool.pyright]
pythonVersion = "3.13"
venvPath = "."
venv = ".venv"
include = ["main.py", "cogs", "objects", "services"]
exclude = [".venv"]
typeCheckingMode = "standard"
```

3. SIM112 は D-1 の決定に従う(★案a なら `ignore` に `"SIM112"` を追加し、`.env.example` を作成)。

**受け入れ基準**: `uv run ruff check .` と `uv run pyright` が上記設定で動く(件数はまだ 0 でなくてよい)。

### Phase 1: 起動ブロッカーの解消 = 支援者コード機能・DB 層の全面削除(behavioral / D-2 決定済み)

D-2 に列挙した削除範囲を1コミットで実施する。手順:

1. cogs/music.py から `/code`(:806-840)・`/ranking`(:842-878)コマンドを削除
2. cogs/music.py の playCommand から履歴記録を削除(:596 の `getGuild`、:610-612 と :623 の `playedMusics.append`、:627 の `updateGuild`。**:638-639 の `player.store(...)` は消さないこと** — これは再生パネルの契約で無関係)
2b. cogs/help.py の /help embed から `/code`(:34-38)と `/ranking`(:39-43)のフィールドを削除
3. 不要になった import・モジュールレベル定数を削除(:11 aiofiles, :24-25 services.*, :30 MusicData, :7 Counter, :37 tokyo 等 — `uv run ruff check --select F401` の検出に従う)
4. `alembic.ini` と `migrations/` を削除
5. pyproject.toml から `pydantic`、`aiofiles` を除去(`tzdata` は grep で他に利用が無ければ除去可)→ `uv lock` → `uv sync`
6. pyright の reportMissingImports ×2 がこれで消える

**受け入れ基準**: `uv run python -c "import main, cogs.music"` が成功する / `grep -rn "getGuild\|getMember\|MusicData\|aiofiles\|key.txt" main.py cogs objects services` が 0 件 / 削除対象外のコマンド(play/timescale/volume/queue/loop/toggle/stop/ping/help)に変更が無い

### Phase 2: 単純な近代化修正(safe-auto + 小さな手修正)

2a. `uv run ruff check . --fix` を実行し、diff を目視確認してからコミット。自動修正対象(ruff ログの `[*]` 印のうち、Phase 1 の削除で消えていない残り):

- UP006: `typing.List/Dict` → `list/dict`(cogs/music.py:320。:860 と objects/guilds.py・members.py の分は Phase 1 の削除で消滅)。UP035(import 行 / cogs/music.py:9)は注釈の書き換えに伴う未使用 import 削除で解消
- RUF023: `__slots__` ソート(cogs/music.py:41, objects/client.py:19)
- (UP015 / cogs/music.py:814 と UP045 / objects/members.py:10 は Phase 1 の削除で消滅済みのはず — 残っていたら Phase 1 のやり残し)

2b. SIM 3件は unsafe-fix 扱いのため**手で**書き換える(いずれも挙動不変):

- SIM105: try/except-pass → `contextlib.suppress(ClientError)` + `import contextlib`(objects/client.py:130)
- SIM108: 三項演算子化(cogs/ping.py:30)
- SIM102: ネスト if を `and` で結合(cogs/music.py:433)

**注意**: `--unsafe-fixes` は使わない(N805 など §5.4 で禁止した自動修正が混ざるため)。**受け入れ基準**: UP*/RUF023/SIM102/105/108 が 0 件、`git diff` に文字列リテラルの変更が無い。

### Phase 3: リネーム(mechanical)

原則: **Python 識別子だけを変更し、文字列リテラルには一切触れない。** エディタの一括置換ではなく、以下の対応表に従い参照箇所を同時に更新する。

#### 3.1 関数・メソッド(N802)

| ファイル | 現在 | 変更後 | 同時更新する参照 |
|---|---|---|---|
| main.py:49 | `onTreeError` | `on_tree_error` | main.py:83 の代入 |
| services/env.py:8 | `getEnv` | `get_env` | main.py:9,95(全 import 元はこの2箇所のみ・検証済み) |
| objects/utils.py:1 | `formatTime` | `format_time` | objects/panel.py:6,79(全利用箇所) |
| cogs/ping.py:19 | `pingCommand` | `ping_command` | なし(name="ping" 維持) |
| cogs/help.py:17 | `pingCommand` | `help_command` | なし(コピペ由来の誤名。name="help" 維持) |
| cogs/music.py:69 | `presenceLoop` | `presence_loop` | music.py:99 `self.presenceLoop.start()` |
| cogs/music.py:130 | `messageEditQueue` | `message_edit_queue` | 呼び出し箇所 |
| cogs/music.py:145 | `getTimescale` | `get_timescale` | 呼び出し箇所 |
| cogs/music.py:148 | `changeSpeed` | `change_speed` | 呼び出し箇所 |
| cogs/music.py:164 | `changePitch` | `change_pitch` | 呼び出し箇所 |
| cogs/music.py:180 | `putPrevQueue` | `put_prev_queue` | music.py:224,463 |
| cogs/music.py:194 | `onButtonClick` | `on_button_click` | music.py:188 |
| cogs/music.py:328 | `queuePagenation` | `queue_pagenation` | music.py:292,704。**custom_id 文字列 `"queuePagenation,{n}"` は変更禁止** |
| cogs/music.py:452/498/542 | `onTrackEnd`/`onQueueEnd`/`onPlayerUpdate` | `on_track_end`/`on_queue_end`/`on_player_update` | なし(イベント型で登録・検証済み) |
| cogs/music.py:588 ほか | `playCommand` 等 7 コマンド(codeCommand / rankingCommand は Phase 1 で削除済み) | `play_command` / `pitch_command` / `volume_command` / `queue_command` / `loop_toggle_command` / `toggle_command` / `stop_command` | なし(全て name= 明示・検証済み) |

#### 3.2 pydantic フィールド(N815)— **廃止(改訂1)**

D-2 の決定により `objects/guilds.py` / `objects/members.py` は削除済み。N815 ×2 は Phase 1 で消滅するため、本項の作業は無い。

#### 3.3 引数・ローカル変数(N803/N806)

- objects/panel.py:28 `requestAuthor` → `request_author`(呼び出しは全6箇所とも位置渡し・検証済み。本体内 :41,45,49,53 を更新)
- objects/bot.py:9 `requestAuthor` → `request_author`(**こちらはキーワード専用引数**。呼び出し bot.py:44 の `requestAuthor=member` を同時に変更しないと実行時 TypeError)
- 各ファイルのローカル変数(voiceClient, channelId, guildData, barLength 等 61 件)を snake_case 化。**除外**: §5.1 のコマンドパラメータ(`speed`/`loop`/`code`)。**注意**: cogs/ping.py:26-27 は同名 `voiceClient` を2つの意味で使い回している。`for voice_client in self.bot.voice_clients:` + `player = cast(MusicPlayer, voice_client.player)` の2変数に分離する(pyright の ping.py:26-27 エラーもこれで解消。None ガードは Phase 5 の項4)
- cogs/music.py:320 の keyword 引数 `pageSize` → `page_size`(内部ヘルパー `pagenation` の引数でユーザー非公開・検証済み。**呼び出し側 music.py:345 の `pageSize=` も同時に更新**)
- objects/panel.py の進捗バー4連コピペ(73-75,147-149,179-181,203-205)は、ローカル変数リネームの代わりに `_progress_bar(percentage, bar, circle, graybar, length=14)` ヘルパー1つに抽出して4回呼ぶ(N806×12 が一括解消、出力は同一)

#### 3.4 import エイリアス(N812)

- cogs/music.py:14 / objects/panel.py:4 の `import lavalink as Lavalink` → `import lavalink` にし、ファイル内の `Lavalink.` を `lavalink.` へ置換(`self.lavalink` 属性とは衝突しない・検証済み)

#### 3.5 createPlayer(N805 + N802 + reportSelfClsParameterName)

- `createPlayer` → `create_player` にリネームし **`@staticmethod` を付ける**(Python 3.13 の staticmethod は素で呼べるため `@app_commands.check(create_player)` は class 本体内でそのまま動く)。music.py:587 の参照を更新。**self を追加する修正は禁止(§5.4)。**

#### 3.6 パッケージ構造

- `objects/__init__..py`(ドット2つ・空・未追跡)を `objects/__init__.py` にリネームし、`cogs/__init__.py` / `services/__init__.py` と一緒にコミット(現在 objects/ だけ暗黙の namespace package という不整合の解消)

**受け入れ基準**: N802/N803/N805/N806/N812/N815 が 0 件。`git diff` 内で変更された文字列リテラルが 0 個(`custom_id`・store キー・日本語文言・env キーすべて不変)。

### Phase 4: 型エラー修正(mechanical)

方針: **構造を変えず、注釈・narrowing・cast で pyright を納得させる。** 実行時挙動が変わる修正は Phase 5 へ。

1. **main.py:58-69**: `return await send(…)` → `await send(…)` + 素の `return`(CommandTree.on_error は `-> None` 契約。戻り値は discord.py が無視するため挙動不変)
2. **objects/client.py:38-39**: `self.player: lavalink.DefaultPlayer | None = None`、`self.track: lavalink.AudioTrack | None = None` と正直に注釈(下流の非 None 前提箇所には assert)
2b. **objects/client.py:35,36,70 の channel 型クラスタ**(reportIncompatibleVariableOverride ×1 を含む計4件): 基底 `VoiceProtocol` の `self.channel` は `abc.Connectable` 宣言なので、サブクラスで `discord.VoiceChannel` と再宣言すると override 不整合になる。**再宣言をやめ**、`__init__` では `self.channel = cast(discord.VoiceChannel, channel)`(:35)とし、:70 の再代入も cast で受ける(None ガードは Phase 5 の項3)。`.guild` アクセス(:36)は cast 後なら解決する
3. **objects/client.py:45,55 / `client.lavalink`**: `TYPE_CHECKING` 下で `MusicBot` を import し client 引数を型付けするか、`cast` を使う(objects/bot.py:27 に既に `self.lavalink: lavalink.Client` 注釈あり)。D-5 でフォールバック削除を選べばこの問題の大半が消える
4. **objects/client.py:47-49**: `os.getenv(…)` → `services.env.get_env(…)` に置換(キー名は小文字のまま)。`str | None` が消え、設定漏れ時に `int(None)` の TypeError ではなく明確な KeyError になる。cogs/music.py:103-105 も同様
5. **objects/queue.py**: `class MusicQueue(asyncio.Queue)` + `self._queue.pop()` → **`class MusicQueue(asyncio.LifoQueue): pass`** に置換(LifoQueue の `_get` は完全に同一実装。LIFO 仕様を維持しつつ私有属性アクセスが消える・検証済み)
6. **cogs/music.py**: `__init__` の `self.lavalink` / `self.editQueueTask` を `| None` で注釈(:64,66)/ ガード済み箇所に `assert interaction.guild is not None` / `interaction.user` は `isinstance(interaction.user, discord.Member)` で narrowing / on_interaction 冒頭に `if interaction.type is not discord.InteractionType.component: return` を置き `interaction.data` を cast(既存の try/except KeyError を置換)/ `voice_client` は `cast(LavalinkVoiceClient, …)` するヘルパー1つに集約 / `interaction.channel.send`(:632)は Messageable への narrowing / lavalink イベントハンドラ内の `event.player` 受け(:453-454, :499-500, :543-544)と `player_manager.get()` の戻り(:590)は `cast(MusicPlayer, …)` または None ガードで受ける
7. **cogs/music.py:273,275**: `set_volume(clamp(…))` → `set_volume(int(clamp(…)))`(seek の既存パターン :266,270 と同じ。値は常に整数なので無損失)
8. **cogs/music.py:344**: 注釈 `tuple[Lavalink.AudioTrack]`(1要素タプルの意味)→ `tuple[lavalink.AudioTrack, ...]`
9. **cogs/ping.py:42, cogs/help.py:50**: `bot.user.display_avatar` の前に `assert self.bot.user is not None`(ログイン後にしか実行されないため純粋な narrowing)。ping.py:26-27 の型エラーは Phase 3.3 の2変数分離+cast で解消する
10. **objects/client.py:81-82**: `timeout` / `reconnect` に `# noqa: ARG002`(§5.4 のとおり抑制のみ)

**受け入れ基準**: pyright エラーが Phase 5 対象(下記)のみになる。

### Phase 5: pyright が暴いた実バグの修正(behavioral — 挙動変更を明示)

これらは型エラーであると同時に**現実に到達可能なクラッシュ**。「クラッシュ → 安全にスキップ」への変更なので behavioral と明記してコミットを分ける。

1. **objects/bot.py:29-48 `MusicBot.close()`**(pyright エラー11件の塊):
   - `isinstance(voice_client, LavalinkVoiceClient)` で narrowing
   - **`disconnect(force=True)` を呼ぶ前に** player / track / channelId / messageId を取り出す(現状は破棄後のオブジェクトを読んでいる)
   - `if not (track and channel_id and message_id): continue`(再生していない・パネル未投稿の接続はスキップ。現状はシャットダウン時 AttributeError)
   - `get_channel` の戻りを `isinstance(channel, discord.abc.Messageable)` 系で narrowing し、None なら continue
2. **objects/client.py:103-117 `disconnect()`**: `player_manager.get()` が None のときのガードを追加(ボットが VC から蹴られて `_destroy()` 済みの後に stale な voice client から `disconnect(force=True)` が来ると None 参照。call site: cogs/music.py:539,803, objects/bot.py:31)。None なら `change_voice_state(channel=None)` だけして return(サイレント no-op)
3. **objects/client.py:70**: `get_channel` が None(キャッシュミス)のとき `self.channel` を上書きしないガード
4. **cogs/ping.py:26-28**: `player = voice_client.player` が None(接続処理中)なら `continue`(現状は /ping が AttributeError)
5. **cogs/music.py の到達可能な None**: on_button_click 冒頭の `player.current.extra`(:205-206)、stopCommand(:770-778)、queue_pagenation(:341)に `player.current` の None ガード / `self.bot.get_channel(…)`(:231,469,506,554,775)と `player.fetch("channelId")` の None ガード(ボット再起動後の stale データで到達可能)/ onQueueEnd の `guild.voice_client`(:538)にも None ガード(管理者がキュー終了の瞬間に切断ボタンで蹴ると AttributeError・検証済み)

**受け入れ基準**: `uv run pyright` エラー 0 件。各ガードの「スキップ時挙動」がコミットメッセージに記録されている。

### Phase 6: 検証

1. `uv run ruff check .` → 0 件
2. `uv run pyright` → 0 件
3. `uv run python -c "import main, cogs.music, cogs.ping, cogs.help, objects.client, objects.panel"` → 成功
4. 文字列契約の不変確認: `git diff <開始コミット> -- '*.py' | grep '^[-+].*custom_id'` などで custom_id / store キー / 日本語文言の変更が無いことを確認
5. 実機スモークテスト(可能なら): 起動 → /play → パネルの各ボタン → /queue のページ送り → /stop → プロセス終了(close() のパネル書き換え)

## 8. 付録A: lint 対象外だが今回発見された実バグ・課題(バックログ)

lint ゼロ化とは独立して直す価値があるもの。**本仕様のフェーズには含めない**(挙動変更の混入を避けるため)。

| # | 内容 | 場所 |
|---|---|---|
| 1 | `max_message=None` は `max_messages` のタイポ。unknown kwarg として**黙って捨てられており**、メッセージキャッシュ無効化が効いていない | main.py:21 |
| 2 | ~~/code の12月バグ: `now.replace(month=now.month + 1)` は12月に ValueError~~ → **D-2 の /code 削除で解消** | cogs/music.py:828-830 |
| 3 | キューのページ送りボタンが二重 defer(on_button_click :203 と queuePagenation :331)で InteractionResponded 例外。さらに match 節に return が無く成功時はパネルで上書きされる | cogs/music.py:292,331 |
| 4 | アートワーク無しトラックでステータス行(再生中/リクエスト者)が丸ごと消える(no-artwork 分岐が `self.title` を捨てて `track.title` を使っている) | objects/panel.py:69-70 |
| 5 | 「prev」ボタン: 空の prevQueue で `await queue.get()` が永久に待つ(stale パネル経由で到達可能)。`get_nowait()` + QueueEmpty 処理へ | cogs/music.py:216 |
| 6 | ~~/code 成功時の embed タイトルがランキングからのコピペ~~ → **D-2 の /code 削除で解消** | cogs/music.py:834-836 |
| 7 | `track.duration == 0`(ライブ配信等)で進捗バーが ZeroDivisionError | objects/panel.py:72 |
| 8 | `.gitignore` の変更で `/key.txt`・`/cookies.txt` の ignore が消えている。key.txt 自体は D-2 で不要になる(デプロイ先からの削除を推奨)が、**手元やデプロイ先に残っている間の誤コミットリスク**は残るため ignore 復活推奨 | .gitignore |
| 9 | `objects.exceptions` の `CommandInvokeError` / `NoPrivateMessage` が discord.py 標準例外と同名で、フレームワーク発の `app_commands.NoPrivateMessage` はハンドラ(main.py:66)を素通りする | objects/exceptions.py |
| 10 | ~~alembic downgrade バグ(`op.drop_column("members")` の引数不足)~~ → **D-3 の migrations/ 削除で解消** | migrations/versions/265ebbd65cab |
| 11 | `discord.utils._ColourFormatter` は private API(discord.py 更新で壊れうる)。`discord.utils.setup_logging()` へ | main.py:29 |
| 12 | editQueue ポンプは1秒/編集の逐次処理でキュー無制限 → PlayerUpdateEvent 多発時にパネル更新が際限なく遅延 | cogs/music.py:130-143 |
| 13 | presence 更新等を on_ready で初期化している(再接続ごとに再実行される)。`cog_load` へ移すのが筋 | cogs/music.py:88-113 |

### 8.1 追加調査(改訂2)で確認された問題

改訂2 の一斉捜索(3レンズ×検証エージェントで全件裏取り済み、誤検出は棄却)で確認。lint とは独立の実行時バグ・運用課題。**優先度 高 の3件はユーザー影響が大きく、lint 修正とは別に早期対応を推奨。**

| # | 優先度 | 内容 | 場所 |
|---|---|---|---|
| 14 | **高** | **VC 参加チェックが /play にしか無い。** createPlayer による「ボットと同じ VC にいること」の検証は playCommand だけに付いており、パネルの全ボタン(stop/next/prev/pause/音量/速度/ピッチ/loop/shuffle)と /timescale /volume /queue /loop /toggle /stop は voice client の存在しか見ない。**VC にいない任意のメンバーが再生を止めたりボットを切断できる** | cogs/music.py:194,649,676,697,711,739,760 |
| 15 | **高** | **リクエスト者がサーバーを抜けると全ボタン・パネル更新が壊れる。** `fetch_member(track.extra["requester"])` が discord.NotFound を投げるが try/except が無い(:206, 296-298, 350, 472, 509, 557, 778)。ボタンは永久 defer、パネル更新は約5秒ごとに例外、/stop は切断まで到達しない。get_member フォールバック+例外処理が必要 | cogs/music.py:206 ほか |
| 16 | **高** | **loop / shuffle と prev・next ボタンの相互作用が壊れている。** DefaultPlayer.play() 自身の loop/shuffle ロジックが先に効くため: 1曲ループ中は next で同じ曲が永久リスタート・prev も同曲再生+キュー先頭に残骸、キュー内ループ中は prev のたびに現在曲が重複、shuffle 中は prev がランダムな曲を再生(ライブラリ実装 player.py:277-299 で裏取り済み) | cogs/music.py:211-226 |
| 17 | 中 | onTrackEnd の「キュー空」判定がライブラリの自動進行とレースする: 次の曲は hook 実行前に pop 済みのため、最後から2曲目が終わるたびにパネルが約5秒「再生終了」に化け、キュー内ループでは毎周フリッカーする | cogs/music.py:465 |
| 18 | 中 | onQueueEnd の finished パネル分岐はデッドコード(QueueEndEvent 時点で `event.player.current` は常に None・ライブラリ実装で裏取り済み)。最終曲が LOAD_FAILED で終わるとパネルが「再生中」のまま永久放置 | cogs/music.py:500 |
| 19 | 中 | /queue のページ数計算 `(len // 10) + 1` は10の倍数ちょうどで空ページを生む(現在曲が index 0 に挿入されるため計10曲で発生) | cogs/music.py:367,378 |
| 20 | 中 | `tree.sync()` を毎起動無条件実行 — クラッシュ再起動ループに入ると global sync 連打で 429(コマンド定義変更時のみ実行する仕組みか手動トリガーへ) | main.py:91 |
| 21 | 中 | cog のライフサイクル: presenceLoop が cog_unload でキャンセルされない(reload+再接続で二重稼働)/ lavalink 未初期化のまま unload すると AttributeError / reload 後は lavalink フックが死んだままになる | cogs/music.py:118-128 |
| 22 | 中 | REST 過剰呼び出し: PlayerUpdate ごと(約5秒毎/ギルド)に fetch_message+fetch_member、ボタン1クリックで requester を2回 fetch、/queue は行ごとに fetch_member(重複キャッシュ無し)。同時再生ギルドが増えるとレート制限に接触 | cogs/music.py:548-557,206,296,350 |
| 23 | 中 | prevQueue がキュー内ループで1周ごとに重複を積み無限成長(数日連続再生でメモリ線形増加+prev の意味が壊れる) | cogs/music.py:459-463 |
| 24 | 低 | 同時 /play レース: `player.is_playing` は TrackStart 到着まで False のため、アイドル時に2人が同時 /play すると二重パネル+孤児「準備中」メッセージ | cogs/music.py:631 |
| 25 | 低 | createPlayer が検証**前**に `player_manager.create()` するため、VC 不参加ユーザーの /play 失敗でも lavalink プレイヤーがプロセス寿命まで残る | cogs/music.py:403-405 |
| 26 | 低 | logging が "music" ロガーしか設定しておらず lavalink ライブラリのログ(ノード切断・再接続)がどこにも出ない | main.py:24-38 |
| 27 | 低 | フォールバックのエラー embed が例外の生テキストをユーザーへそのまま表示(内部情報の漏えい面) | main.py:70-80 |
| 28 | 低 | パネル表示の細部: 速度/ピッチが float 誤差+`math.ceil` で 71% 等にズレる(panel.py:185,209)/ 音量バーはデフォルト100で毎回15文字にはみ出す(:146-151、既知の off-by-one はデフォルト値でも発生)/ ライブ配信は duration=2^63-1 のため「106751991167:07:12:55」のような合計時間表示(:79、is_stream 分岐が無い)/ formatTime の日付き表示 dd:hh:mm:ss が紛らわしい(utils.py:7) | objects/panel.py, objects/utils.py |
| 29 | 低 | /help が実在コマンド8個中5個(/timescale /volume /loop /toggle /stop)を案内していない(D-2 の /code・/ranking 削除後は特に) | cogs/help.py:24-48 |
| 30 | 低 | ボットが VC にスピーカーミュート(self_deaf)無しで参加し、消費しない受信音声データを受け取り続ける — `channel.connect(cls=…, self_deaf=True)` 推奨 | objects/client.py:83, cogs/music.py:443 |
| 31 | 低 | /ping の VoiceClient Ping: lavalink の -1 センチネル(未接続)を除外せず平均に混入、また小数15桁の生 float を表示 | cogs/ping.py:28-39 |
| 32 | 低 | intents.emojis は不要(絵文字は application emoji を fetch しており guild emoji イベント未使用)、prefix "music#" はデッドウェイト / README にこのブランチのセットアップ手順(lavalink ノード、.env)が無い | main.py:11-18, README.md |

## 9. 付録B: 検証済み事実の出典

- コマンド名の name= kwarg 全11件、custom_id 一覧、`_lavalink_events` による登録方式、`to_snake` の恒等性、HEAD の DB 層(`git show HEAD:services/…`)、alembic スキーマ(snake_case カラム)は、2026-07-10 に本リポジトリ+ `.venv` 内の discord.py / lavalink.py / pydantic 実装を直接読んで検証した。
- lint 生ログ: ruff 131 件 / pyright 156 件(§1 の条件)。
