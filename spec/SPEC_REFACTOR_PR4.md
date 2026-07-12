# SPEC_REFACTOR_PR4.md — onButtonClick の dispatch table 化

対象ブランチ: `lavalink` / 作成日: 2026-07-11 / 親仕様: `SPEC.md` / 前段: `SPEC_REFACTOR_PR3.md`

`cogs/music.py` 分割計画の**第 4 段階**(分割計画中で最大サイズの変更)。131 行の `onButtonClick` メソッド(pre-flight + 16 ケースの match 文 + 末尾パネル更新)を `objects/buttonHandler.py` に移設し、handler 関数の dispatch table 化する。**挙動不変**を厳格に維持する。

## 1. 背景

現行 `MusicCog.onButtonClick`(141-271 行、131 行)は以下の 4 領域を 1 メソッドに詰め込んでいる:

| 領域 | 行 | 内容 |
|---|---|---|
| **pre-flight** | 141-176 | interaction.guild / voice_client / player の 3 段 None 検証、VC 参加チェック、defer、track/mention 取得 |
| **dispatch** | 179-258 | 16 ケースの `match customField[0]` 分岐 |
| **tail: panel refresh** | 260-271 | 現在曲を再取得してパネル再構築+enqueue |
| **状態変数** | 179 | `finished = False`(PR2 で dead code 化しているが未削除) |

問題:
- 131 行の 1 関数として読解負荷が高い
- 16 case が同じインデントに並び、追加時にどこに入れるべきかが不明瞭
- 「新しいボタンを増やしたい」時、既存 case の末尾処理(panel refresh)がどう共通化されているかが読み取りづらい
- Cog 内メソッドなので `self` を持ち回るが、handler ごとの必要属性が識別できない
- テスト不能(Cog 全体を組む必要)

分割計画の目標:
- pre-flight と tail を `handleButtonClick(cog, interaction)` に集約
- 16 個の case を 16 個の**独立した handler 関数**に切り出す
- 各 handler は `ButtonContext` dataclass を受ける
- dispatch table `_HANDLERS: dict[str, Handler]` で custom_id → handler の対応を宣言的に

## 2. スコープ

### 2.1 新規ファイル: `objects/buttonHandler.py`

以下を定義:

#### 2.1.1 `ButtonContext` dataclass

handler に渡す実行時コンテキスト。frozen で immutable。

```python
@dataclasses.dataclass(frozen=True)
class ButtonContext:
    cog: "MusicCog"                       # queuePagenation の委譲用
    interaction: discord.Interaction      # 既に defer(ephemeral=True) 済み
    voiceClient: LavalinkVoiceClient      # stop の disconnect() 用
    player: MusicPlayer
    track: lavalink.AudioTrack            # ボタン押下時の current(handler 内で stale になりうる)
    requestAuthorMention: str             # 事前解決済み
    customField: list[str]                # split(",") 結果。customField[1] は queuePagenation で使用
```

#### 2.1.2 Handler 型と戻り値契約

```python
Handler = Callable[[ButtonContext], Awaitable[bool | None]]
```

**戻り値契約**:
- `True` を返す → 「handler 内で完結、末尾の panel refresh は不要」(prev/next/stop/queuePagenation)
- `None`(or `False`)を返す → 「末尾の panel refresh を実行」(resume/pause/reverse/forward/volume*/speed*/pitch*/loop/shuffle)

戻り値 True の内訳:
- prev/next: `player.play(track=X)` → TrackStart イベント → onPlayerUpdate が自動でパネル更新するため tail 不要
- stop: `finalizePanel + disconnect` を handler 内で完結
- queuePagenation: interaction の response をキュー表示に上書きするため、パネル再構築するとキュー表示が消える(SPEC #3)

#### 2.1.3 16 個の handler 関数

すべて `async def handleXxx(ctx: ButtonContext) -> bool | None`。ロジックは現行と 1 バイト変えない。

| custom_id | handler | 戻り値 | 参考 SPEC |
|---|---|---|---|
| `prev` | `handlePrev` | True | SPEC #5, #16 |
| `next` | `handleNext` | True | SPEC #16 |
| `stop` | `handleStop` | True | (PR2 で finalize 統合) |
| `resume` | `handleResume` | None | — |
| `pause` | `handlePause` | None | — |
| `reverse` | `handleReverse` | None | — |
| `forward` | `handleForward` | None | — |
| `volumeUp` | `handleVolumeUp` | None | — |
| `volumeDown` | `handleVolumeDown` | None | — |
| `speedUp` | `handleSpeedUp` | None | — |
| `speedDown` | `handleSpeedDown` | None | — |
| `pitchUp` | `handlePitchUp` | None | — |
| `pitchDown` | `handlePitchDown` | None | — |
| `loop` | `handleLoop` | None | — |
| `shuffle` | `handleShuffle` | None | — |
| `queuePagenation` | `handleQueuePagenation` | True | SPEC #3 |

#### 2.1.4 dispatch table `_HANDLERS`

```python
_HANDLERS: dict[str, Handler] = {
    "prev": handlePrev,
    "next": handleNext,
    ...
    "queuePagenation": handleQueuePagenation,
}
```

**網羅性チェック**: モジュール定数として期待キー集合 `_EXPECTED_CUSTOM_IDS`(17 個)を保持し、モジュールロード時に `assert set(_HANDLERS.keys()) == _EXPECTED_CUSTOM_IDS` で検証する。追加ハンドラを書いたが登録し忘れた場合、import 時点で失敗する。

#### 2.1.5 エントリ関数 `handleButtonClick(cog, interaction)`

- pre-flight: interaction.guild / voice_client / player の 3 段 None 検証、VC 参加チェック、defer、track/mention 取得
- dispatch: `_HANDLERS.get(customField[0])` で handler 取得、無ければ silent ignore、あれば await
- tail: 戻り値が truthy でなければ現在曲を再取得してパネル再構築+enqueue

### 2.2 `cogs/music.py` の変更

**onButtonClick の書き換え**:
```python
async def onButtonClick(self, interaction: discord.Interaction):
    await buttonHandler.handleButtonClick(self, interaction)
```

**削除される内部要素**:
- 131 行の match 文と pre-flight/tail 処理(全て buttonHandler へ)
- `finished` 変数(PR2 以降 dead code だったもの)
- 使われなくなった import(`random`, `asyncio.QueueEmpty` — buttonHandler 側で使う)

**残す**:
- `queuePagenation` メソッド(handleQueuePagenation から `ctx.cog.queuePagenation(...)` で呼ばれる — PR5 で移設予定)
- 他の listener と slash command はすべて無変更

### 2.3 循環 import の回避

`objects/buttonHandler.py` が `MusicCog` 型を参照する必要があるが、`cogs/music.py` は `buttonHandler` を import する。循環 import を避けるため:
- `from __future__ import annotations` で全アノテーションを文字列化
- `TYPE_CHECKING` ガード下で `from cogs.music import MusicCog` を条件付き import

## 3. 不変条件

親 SPEC.md §5 の契約に加えて、本 PR 固有:

1. **挙動完全不変**: 各 handler の内部ロジック、順序、エラーメッセージ、`player.play(track=X)` の呼び出し、`player.queue.pop(popAt)` の `popAt` 計算(random.randrange)、seek/set_volume の clamp 引数、すべて 1 バイト変更禁止。
2. **custom_id 文字列**: 16 個の case 文字列は既存の buttonHandler の dispatch table キーとしてそのまま使う。panel.py の button ラベルと byte-for-byte 一致。
3. **VC 参加チェックの例外**: `customField[0] != "queuePagenation"` のとき VC チェックを実施(SPEC #14)。この条件は buttonHandler.handleButtonClick 側にそのまま持ち込む。
4. **defer の位置**: VC チェック**後**の `interaction.response.defer(ephemeral=True)` を維持(先に defer するとエラー時に ephemeral response が送れなくなる)。
5. **prev の空 queue 処理**: `asyncio.QueueEmpty` 例外を捕捉して "前の曲がありません。" ephemeral、SPEC #5。
6. **next の空 queue 処理**: `len(player.queue) == 0` で "次の曲がありません。" ephemeral、SPEC #16。
7. **stop の disconnect**: `voiceClient.disconnect()`(force=False)を維持。stopCommand の `disconnect(force=True)` とは意図的に区別。
8. **queuePagenation の委譲**: `ctx.cog.queuePagenation(ctx.interaction, int(ctx.customField[1]), edit=True)` の呼び出しを維持。
9. **pop 順序**: next の `popAt = random.randrange(len(player.queue)) if player.shuffle else 0` の**判定と pop を分離しない**(handler 内でこの 2 行を並べる)。
10. **tail の narrowing**: refresh 前の `player.current` 再取得と None チェック、resolveMemberMention の呼び出しを handleButtonClick の tail に持ち込む。
11. **finalizePanel の呼び出し順**: `handleStop` は `finalizePanel → disconnect` の順序を維持(逆にするとパネル書き換えが失敗しうる)。

## 4. 受け入れ基準

1. `uv run ruff check .` → **All checks passed!**
2. `uv run pyright` → **0 errors, 0 warnings**
3. `uv run python -c "import main, cogs.music, cogs.ping, cogs.help, objects.buttonHandler; print('OK')"`
4. **網羅性 assert**: `objects/buttonHandler.py` の import 時に `set(_HANDLERS.keys()) == _EXPECTED_CUSTOM_IDS` が真になる。テスト:
   ```
   uv run python -c "from objects.buttonHandler import _HANDLERS, _EXPECTED_CUSTOM_IDS; assert set(_HANDLERS.keys()) == _EXPECTED_CUSTOM_IDS; print(len(_HANDLERS), 'handlers OK')"
   ```
   → `16 handlers OK`
5. **契約 diff**:
   - custom_id 生値(panel.py 内で 14、buttonHandler.py 内の dispatch キー 16、queuePagenation の f-string 3)は全て変更なし
   - コマンド名 `name=` kwarg 9 個変更なし
   - player.store/fetch キー 5 種類変更なし
6. **削除確認**:
   - `grep -c "match customField" cogs/music.py` → 0
   - `grep -c "case \"prev\"" cogs/music.py` → 0
   - `grep -c "finished = False" cogs/music.py` → 0
7. **onButtonClick のサイズ**: `MusicCog.onButtonClick` メソッドが 3 行以下(async def + 委譲 1 行 + 空白)
8. **行数変化**: `cogs/music.py` が約 -130 行、`objects/buttonHandler.py` に約 +200 行(handler 群+dispatch+docstring)。ネット +70 行。

## 5. 実施手順

### Phase 1: SPEC 執筆(本ファイル)→ 完了

### Phase 2: `objects/buttonHandler.py` を新規作成

- `from __future__ import annotations` を先頭に
- 16 handler + ButtonContext + _HANDLERS + handleButtonClick を定義
- モジュール末尾で `assert set(_HANDLERS.keys()) == _EXPECTED_CUSTOM_IDS`

### Phase 3: `cogs/music.py` の書き換え

順序:
1. import 追加: `from objects import buttonHandler`
2. `onButtonClick` メソッド本体を委譲 1 行に置換
3. 使われなくなった import 整理(`asyncio`, `random`, `clamp`, `resolveMemberMention` — 他の場所での使用有無を確認してから削除)
4. `queuePagenation` メソッド(PR5 対象)はそのまま残す

### Phase 4: 検証

- ruff / pyright / import
- 網羅性 assert 実行
- 契約 grep
- 行数変化

## 6. スコープ外

- `queuePagenation` の外出しは PR 5
- `@requirePlaying`/`@requireSameVC` デコレータは PR 5
- 親 SPEC.md §8/§8.1 のバックログ追加なし

## 7. ロールバック

```
git checkout HEAD cogs/music.py
rm objects/buttonHandler.py SPEC_REFACTOR_PR4.md
```
