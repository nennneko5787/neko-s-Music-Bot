# SPEC_REFACTOR_PR3.md — MessageEditQueue クラス化

対象ブランチ: `lavalink` / 作成日: 2026-07-11 / 親仕様: `SPEC.md` / 前段: `SPEC_REFACTOR_PR2.md`

`cogs/music.py` 分割計画の**第 3 段階**。現在 MusicCog にへばりついている 4 メンバー(`editQueue` / `editQueueTask` / `_editTargetKey` / `messageEditQueue` pump)を独立クラス `MessageEditQueue` として `objects/messageEditQueue.py` に切り出す、**挙動不変**のリファクタ。

## 1. 背景

現行 `cogs/music.py` の以下 4 メンバーは **1 つの責務(edit のコアレス+逐次処理)** を実現するために結束している:

| メンバー | 行 | 役割 |
|---|---|---|
| `self.editQueue: asyncio.Queue` | 59 | 生の非同期キュー |
| `self.editQueueTask: asyncio.Task \| None` | 60 | pump タスク参照 |
| `self._editTargetKey(instance) -> tuple` | 136-142 | coalesce 用のキー生成 |
| `self.messageEditQueue()` async | 144-177 | pump ループ本体 |
| `cog_load` の `create_task(self.messageEditQueue())` | 116 | ライフサイクル開始 |
| `cog_unload` の `self.editQueueTask.cancel()` | 133-134 | ライフサイクル終了 |

これらは MusicCog の他の関心事(app_commands / listener / lavalink bootstrap)とは無関係なため、独立クラスに切り出せる。

外部からの利用点:
- `cog.editQueue.put((target, kwargs))` を **7 サイト**が使用(音楽 cog 内 + panelUpdater 内)

`asyncio.Queue.put` 互換の `.put(item)` メソッドを提供すれば、外部呼び出し側は無変更で動く。

## 2. スコープ

### 2.1 新規ファイル: `objects/messageEditQueue.py`

`MessageEditQueue` クラスを定義。API は 3 メソッド:

| メソッド | 内容 |
|---|---|
| `put(item: tuple)` | 現行 `asyncio.Queue.put` と互換。`(target, kwargs)` の tuple を受ける async メソッド |
| `start()` | pump タスクを起動。すでに走っていれば何もしない(idempotent)|
| `stop()` | pump タスクをキャンセル。走っていなければ何もしない(idempotent)|

内部は `asyncio.Queue`、target key 判定、pump ループ、を全て隠蔽。SPEC #12(coalesce)と SPEC #21(reload 二重稼働防止のための idempotency)のロジックはそのまま持ち込む。

### 2.2 `cogs/music.py` の変更

**属性**:
- `self.editQueue: asyncio.Queue = asyncio.Queue()` → `self.editQueue: MessageEditQueue = MessageEditQueue()`
- `self.editQueueTask: asyncio.Task | None = None` を**削除**

**メソッド削除**:
- `MusicCog._editTargetKey`(136-142)
- `MusicCog.messageEditQueue`(144-177)

**ライフサイクル書き換え**:
- `cog_load`: `self.editQueueTask = asyncio.create_task(self.messageEditQueue())` → `self.editQueue.start()`
- `cog_unload`: `if self.editQueueTask is not None: self.editQueueTask.cancel()` → `self.editQueue.stop()`

**呼び出し側**: `cog.editQueue.put(...)` はそのまま動く(MessageEditQueue.put が同じシグネチャを提供)。panelUpdater.py や queuePagenation / playCommand も無変更。

**import 整理**: 不要になった `asyncio.Queue` / `asyncio.QueueEmpty` / `asyncio.CancelledError` の一部は music.py から落ち、`traceback` も pump が消えるので使われなければ削除。ただし `asyncio.QueueEmpty` は onButtonClick の `prev` case(`queue.get_nowait()` を `except asyncio.QueueEmpty` する — prevQueue 由来なのでこちらは残す)で使われているので `asyncio` 自体は維持。

## 3. 不変条件

親 SPEC.md §5 の契約に加えて、本 PR 固有:

1. **挙動完全不変**: coalesce ロジック、1 秒スリープ、target key の型と値(`("i", id)` / `("m", id)` / `("x", id)`)、`asyncio.CancelledError` の 3 段捕捉、`Exception` の traceback 出力、edit_original_response/edit の分岐、全て 1 バイト変更しない。
2. **`put` の互換性**: `cog.editQueue.put((target, kwargs))` の呼び出し形式は不変。外部ファイル(panelUpdater.py)の変更を発生させない。
3. **`start`/`stop` の冪等性**: SPEC #21 の「reload 後の二重稼働防止」ロジック(現行は cog_unload の cancel で担保)を、`stop()` メソッド側でも同じ性質を保つ。二度呼んでも安全。
4. **CancelledError の伝搬**: pump 内部の `CancelledError` 捕捉方式は現行通り(get / edit / sleep の 3 箇所で捕捉して break/return する)。
5. **例外処理**: pump 中で発生する `Exception`(discord API エラー等)は `traceback.print_exc()` で出力してループ継続(SPEC #12 の設計意図)。
6. **タスク参照**: pump タスクの参照は MessageEditQueue インスタンスの内部属性として保持し、Python の GC で回収されないようにする(discord.py の [asyncio.create_task の落とし穴](https://docs.python.org/3/library/asyncio-task.html#creating-tasks) 対策)。

## 4. 受け入れ基準

すべて成立すること:

1. `uv run ruff check .` → **All checks passed!**
2. `uv run pyright` → **0 errors, 0 warnings**
3. `uv run python -c "import main, cogs.music, cogs.ping, cogs.help, objects.messageEditQueue; print('OK')"`
4. **契約 diff**:
   - `cogs/music.py` 内の `self.editQueue.put(` 呼び出しが以前と同じ回数(2 サイト: queuePagenation, playCommand の直呼び)
   - `objects/panelUpdater.py` 内の `cog.editQueue.put(` が 1 サイト(schedulePanelEdit)、書き換え不要
   - custom_id / player.store キー / コマンド名すべて不変
5. **行数変化**: `cogs/music.py` が約 -60 行(`editQueueTask` 属性 + `_editTargetKey` メソッド + `messageEditQueue` メソッド分)、`objects/messageEditQueue.py` に約 +80 行(クラスと docstring)。ネット 20 行増(クラス化コスト)。
6. **削除確認**: `grep -c "editQueueTask" cogs/music.py` → 0、`grep -c "_editTargetKey" cogs/music.py` → 0、`grep -c "async def messageEditQueue" cogs/music.py` → 0

## 5. 実施手順

### Phase 1: SPEC 執筆(本ファイル)→ 完了

### Phase 2: `objects/messageEditQueue.py` を新規作成

- `MessageEditQueue` クラス実装
- import: `asyncio`, `traceback`, `discord`
- start/stop の冪等性ガードを実装(既存 task の done() チェック)
- `.put()` は `asyncio.Queue.put` に委譲する await ラッパ

### Phase 3: `cogs/music.py` の書き換え

順序:
1. import 追加: `from objects.messageEditQueue import MessageEditQueue`
2. `__init__` で `self.editQueue: MessageEditQueue = MessageEditQueue()`、`self.editQueueTask` を削除
3. `_editTargetKey` メソッド削除
4. `messageEditQueue` メソッド削除
5. `cog_load`: `self.editQueue.start()`
6. `cog_unload`: `self.editQueue.stop()`
7. 不要な import 整理(`traceback` は onTreeError で使われるので残す、`asyncio` は onButtonClick.prev で使われるので残す)

### Phase 4: 検証

- ruff / pyright / import
- 契約 grep
- 行数変化

## 6. スコープ外

- `onButtonClick` の dispatch table 化は PR 4
- `@requirePlaying`/`@requireSameVC` デコレータは PR 5
- 親 SPEC.md §8/§8.1 のバックログ追加なし

## 7. ロールバック

```
git checkout HEAD cogs/music.py
rm objects/messageEditQueue.py SPEC_REFACTOR_PR3.md
```
