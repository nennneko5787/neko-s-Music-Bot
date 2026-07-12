# SPEC_REFACTOR_PR1.md — 純関数の外出し(音声フィルタ + プレイヤーチェック)

対象ブランチ: `lavalink` / 作成日: 2026-07-11 / 親仕様: `SPEC.md`

`cogs/music.py`(1046 行)分割計画の**第 1 段階**。純関数化しやすい 6 関数を `objects/` 配下に切り出す、**挙動完全不変**の機械的リファクタ。

## 1. 背景

`cogs/music.py` は現状 1046 行で全ソースの 57% を占める。以下の 5 段階リファクタ計画のうち本 PR は最も安全な段階:

| PR | 内容 | リスク |
|---|---|---|
| **1(本仕様)** | 純関数の外出し(playerCheck, audioFilters) | 極小 |
| 2 | panelUpdater(fetch_message キャッシュ + 三重重複解消) | 小 |
| 3 | MessageEditQueue クラス化 | 小 |
| 4 | buttonHandler(dispatch table 化) | 中 |
| 5 | @requirePlaying/@requireSameVC + queuePagination | 中 |

## 2. スコープ

### 2.1 新規作成するファイル

#### `objects/audioFilters.py`

以下 4 関数を `MusicCog` のメソッドから**モジュール関数**へ移設する。第 1 引数を `self`(削除)から `player: MusicPlayer` に変える。

| 移設元 | 移設先 | シグネチャ変更 |
|---|---|---|
| `MusicCog.getTimescale(self, player)` | `audioFilters.getTimescale(player)` | self 削除のみ |
| `MusicCog.changeSpeed(self, player, up)` | `audioFilters.changeSpeed(player, up)` | self 削除のみ |
| `MusicCog.changePitch(self, player, up)` | `audioFilters.changePitch(player, up)` | self 削除のみ |
| `MusicCog.putPrevQueue(self, player, track)` | `audioFilters.putPrevQueue(player, track)` | self 削除のみ |

**根拠**: これらは `self` を一切参照していない純ラッパで、既に純関数として書かれている。self を落として module-level に移すのは形式的な変換。

#### `objects/playerCheck.py`

以下 2 関数を移設する。

| 移設元 | 移設先 | シグネチャ変更 |
|---|---|---|
| `cogs/music.py::isInBotVoiceChannel(interaction, voiceClient)` (モジュール関数) | `playerCheck.isInBotVoiceChannel(interaction, voiceClient)` | 変更なし |
| `MusicCog.createPlayer(interaction)` (`@staticmethod`) | `playerCheck.createPlayer(interaction)` | `@staticmethod` 削除、モジュール関数に |

**根拠**:
- `isInBotVoiceChannel` は既にモジュール関数なので単純移動。
- `createPlayer` は既に `@staticmethod` で `self` を使わない。`@app_commands.check(createPlayer)` に**関数参照**として渡されているだけなので、モジュール関数化しても `@app_commands.check(playerCheck.createPlayer)` に書き換えるだけで機能する(親 SPEC.md §5.4 の契約通り)。

### 2.2 削除するもの(`cogs/music.py`)

- クラスメソッド定義: `getTimescale`, `changeSpeed`, `changePitch`, `putPrevQueue`, `createPlayer`(staticmethod 版)
- モジュール関数: `isInBotVoiceChannel`

### 2.3 更新する呼び出しサイト(`cogs/music.py`)

| 呼び出し元 | 変更前 | 変更後 |
|---|---|---|
| onButtonClick "speedUp"/"speedDown" | `self.changeSpeed(player, ...)` | `audioFilters.changeSpeed(player, ...)` |
| onButtonClick "pitchUp"/"pitchDown" | `self.changePitch(player, ...)` | `audioFilters.changePitch(player, ...)` |
| onButtonClick "next" | `self.putPrevQueue(player, _track)` | `audioFilters.putPrevQueue(player, _track)` |
| onTrackEnd | `self.putPrevQueue(player, track)` | `audioFilters.putPrevQueue(player, track)` |
| onButtonClick, pitch/volume/queue/loop/toggle/stop 全コマンド | `isInBotVoiceChannel(...)` | `playerCheck.isInBotVoiceChannel(...)` |
| play コマンドのデコレータ | `@app_commands.check(createPlayer)` | `@app_commands.check(playerCheck.createPlayer)` |

`getTimescale` は `changeSpeed` と `changePitch` の内部からしか呼ばれない。これらが `audioFilters` に一緒に移るので同モジュール内呼び出しになる。

## 3. 不変条件(絶対に壊さない)

親仕様 `SPEC.md` §5 の契約に加えて、本 PR 固有の不変:

1. **挙動完全不変**: エラーメッセージ文字列、raise される例外の型、関数のロジック分岐は 1 バイトも変更しない。純粋な code motion。
2. **`@app_commands.check(createPlayer)`**: 参照される関数オブジェクトは `playerCheck.createPlayer` に変わるが、`interaction: discord.Interaction` を受けて `bool` を返す(または例外を raise する)契約は同じ。
3. **エラー例外**: `NoGuildError`, `MusicCommandError` の raise 箇所と文言は不変。
4. **SPEC #14 `isInBotVoiceChannel`**: `discord.Member` narrowing と `voiceClient.channel` の cast を含む 3 段判定ロジックは 1 バイト変更禁止。
5. **SPEC #25 `createPlayer` の順序契約**: `player_manager.create()` を検証**後**にのみ呼ぶ順序(親 SPEC.md §8.1 #25)を維持。docstring に SPEC 番号を複写する。
6. **`custom_id` 文字列**: SPEC.md §5.2 に記載の 17 個の custom_id は不変。
7. **`player.store/fetch` キー**: SPEC.md §5.2 に記載の 5 種のキー(`channelId`/`messageId`/`channel`/`lastFinishedTrack`/`_panelMessage`)は不変。

## 4. 受け入れ基準

すべて成立すること:

1. `uv run ruff check .` → **All checks passed!**
2. `uv run pyright` → **0 errors, 0 warnings**
3. `uv run python -c "import main, cogs.music, cogs.ping, cogs.help, objects.audioFilters, objects.playerCheck; print('OK')"` → 成功
4. **契約 diff 検証**:
   - `grep -rE '"(prev|next|stop|resume|pause|reverse|forward|volumeUp|volumeDown|speedUp|speedDown|pitchUp|pitchDown|loop|shuffle)"' cogs/ objects/` の結果件数が変更前後で一致
   - `grep -rE '\.(store|fetch)\("(channelId|messageId|channel|lastFinishedTrack|_panelMessage)"' cogs/ objects/` の結果件数が変更前後で一致
   - `grep -rE 'name="(play|timescale|volume|queue|loop|toggle|stop|ping|help)"' cogs/ main.py` の結果件数が変更前後で一致
5. **行数変化**: `cogs/music.py` が減り、`objects/` に 2 新規ファイル。総計はほぼ同じ。

## 5. 実施手順

### Phase 1: SPEC 執筆(本ファイル)
→ 完了。

### Phase 2: `objects/audioFilters.py` を作成

- 4 関数の**中身は現行から 1 バイト変更しない**。self を落として player を第 1 引数に。
- import は `lavalink`(型注釈)、`from lavalink.filters import Timescale`、`from objects.player import MusicPlayer`、`from objects.utils import clamp`。

### Phase 3: `objects/playerCheck.py` を作成

- 2 関数の**中身は現行から 1 バイト変更しない**。
- `isInBotVoiceChannel` はそのまま移動。
- `createPlayer` は `@staticmethod` を落として `async def createPlayer(interaction)` に。docstring で親 SPEC.md §5.4 の関数参照契約と §8.1 #25 の順序契約に触れる。
- import: discord, cast, lavalink, `MusicBot`, `MusicCommandError`, `NoGuildError`, `LavalinkVoiceClient`。

### Phase 4: `cogs/music.py` を更新

順序:
1. import を追加(`from objects import audioFilters, playerCheck`)。
2. `MusicCog.getTimescale`, `MusicCog.changeSpeed`, `MusicCog.changePitch`, `MusicCog.putPrevQueue` の定義を**削除**。
3. `MusicCog.createPlayer`(staticmethod)の定義を**削除**。
4. モジュール関数 `isInBotVoiceChannel` の定義を**削除**。
5. 呼び出しサイトを更新(§2.3 の表通り)。
6. 移設後に未使用になる import を整理(`Timescale` の直接 import は onButtonClick 側で使っていなければ削除)。

### Phase 5: 検証

- ruff / pyright / import 実行
- `git diff --stat` で行数変化確認
- 契約 grep 検証(§4)

## 6. スコープ外

- パネル関連(`_getPanelMessage`, `buildFinishedPanel`)の移設は PR 2 の対象
- `MessageEditQueue` のクラス化は PR 3 の対象
- `onButtonClick` の dispatch table 化は PR 4 の対象
- `@requirePlaying`/`@requireSameVC` デコレータの新設は PR 5 の対象
- 親 SPEC.md §8/§8.1 の新たなバックログ追加なし(本 PR は純粋なコード整理)

## 7. ロールバック

問題が出た場合:
```
git checkout HEAD cogs/music.py
rm objects/audioFilters.py objects/playerCheck.py
```
