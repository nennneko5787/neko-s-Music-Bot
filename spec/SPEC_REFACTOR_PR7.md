# SPEC_REFACTOR_PR7.md — putPrevQueue 再配置 + lavalinkHooks 抽出

対象ブランチ: `lavalink` / 作成日: 2026-07-11 / 親仕様: `SPEC.md` / 前段: `SPEC_REFACTOR_PR6.md`

分割計画後の**分類整理**。2 テーマを 1 PR にまとめる:

1. `putPrevQueue` を `services/audioFilters.py`(音声フィルタと無関係)から `objects/player.py` の `MusicPlayer` メソッドへ移設
2. `cogs/music.py` に残っている lavalink event listener 3 個(onTrackEnd / onQueueEnd / onPlayerUpdate)の実装本体を `services/lavalinkHooks.py` に切り出し

**挙動不変**(pure code motion + method 化)。

## 1. 背景

### 1.1 audioFilters の分類ミス

`services/audioFilters.py` は本来「音声フィルタ関連の純関数群」を集めるモジュールとして PR1 で切り出したが、`putPrevQueue`(prev 履歴キューへの push)が同居している。理由は PR1 実施時に `MusicCog` のメソッドが物理的に連続していたため一括で移設したもので、**意味的な分類ではない**。

- `getTimescale / changeSpeed / changePitch`: Timescale フィルタ操作 ✓ 音声フィルタ
- `putPrevQueue`: `player.prevQueue.put()` の 2 行ラッパ ✗ **音声フィルタではない**

putPrevQueue の本来の持ち主は `MusicPlayer` 自身(`prevQueue` 属性の所有者)。

### 1.2 cogs/music.py に残る lavalink hook 3 個

PR4 で `on_interaction` → `buttonHandler.handleButtonClick` の 1 行委譲パターンを確立したが、lavalink event listener 3 個(onTrackEnd 27 行 / onQueueEnd 23 行 / onPlayerUpdate 21 行、計 71 行)は本体が `MusicCog` に残っている。パターンの一貫性が欠けており、Cog が「listener の登録レジストリ」ではなく「lavalink 由来のロジックの置き場」になっている。

## 2. スコープ

### 2.1 案 A: putPrevQueue を MusicPlayer メソッドへ

**`objects/player.py`** に以下を追加:

```python
class MusicPlayer(DefaultPlayer):
    ...
    async def putPrevQueue(self, track: lavalink.AudioTrack) -> None:
        """
        ⏮ ボタン用の履歴 LIFO キューにトラックを積む。
        再挿入時に position=0 に戻すのはこの API の一部(呼び出し側で二重設定不要)。
        """
        track.position = 0
        await self.prevQueue.put(track)
```

**`services/audioFilters.py`** から `putPrevQueue` を削除。`lavalink` の import は他の関数で使わなくなれば落とす(要確認)。

**呼び出しサイト 2 箇所を更新**:

| ファイル | 変更前 | 変更後 |
|---|---|---|
| `services/buttonHandler.py::handleNext` | `_track.position = 0; await audioFilters.putPrevQueue(ctx.player, _track)` | `await ctx.player.putPrevQueue(_track)`(外側の `position=0` は method 内に統合) |
| `cogs/music.py::onTrackEnd`(PR7 §2.2 で lavalinkHooks に移る) | `track.position = 0; await audioFilters.putPrevQueue(player, track)` | `await player.putPrevQueue(track)` |

外側の `track.position = 0` 削除は**挙動不変**(method 内で同じ代入をしているため)。

### 2.2 案 1: lavalinkHooks を新設

**新規ファイル: `services/lavalinkHooks.py`**

3 個の handler 関数を module 関数として定義:

```python
async def handleTrackEnd(cog: MusicCog, event: TrackEndEvent) -> None:
    """
    SPEC #17/#23: lastFinishedTrack 保存と prev history 追加のみ。
    キュー空判定は onQueueEnd に委譲。LOOP_QUEUE 時は履歴を積まない。
    """
    ...

async def handleQueueEnd(cog: MusicCog, event: QueueEndEvent) -> None:
    """
    SPEC #18: lastFinishedTrack を使って finished パネル化 + voice disconnect。
    """
    ...

async def handlePlayerUpdate(cog: MusicCog, event: PlayerUpdateEvent) -> None:
    """
    5 秒スロットルでパネル(シークバー / 音量バー / 速度・ピッチバー)を再構築。
    """
    ...
```

**`cogs/music.py`** の 3 listener は 1 行委譲へ:

```python
@lavalink.listener(TrackEndEvent)
async def onTrackEnd(self, event: TrackEndEvent):
    await lavalinkHooks.handleTrackEnd(self, event)

@lavalink.listener(QueueEndEvent)
async def onQueueEnd(self, event: QueueEndEvent):
    await lavalinkHooks.handleQueueEnd(self, event)

@lavalink.listener(PlayerUpdateEvent)
async def onPlayerUpdate(self, event: PlayerUpdateEvent):
    await lavalinkHooks.handlePlayerUpdate(self, event)
```

**契約維持**: `@lavalink.listener(EventType)` デコレータは Cog インスタンスのメソッドに付ける必要がある(lavalink.py の `add_event_hooks(self)` がインスタンスをスキャン)。中身の委譲だけ行う。

### 2.3 音楽 cog の import 整理

`onTrackEnd/onQueueEnd/onPlayerUpdate` の移設で music.py から使われなくなる可能性がある import:

- `time`(onPlayerUpdate の 5 秒スロットル判定でのみ使用)
- `services.audioFilters`(onTrackEnd の putPrevQueue 呼び出しでのみ使用)
- `LavalinkVoiceClient`(onQueueEnd の cast で使用、stopCommand も使うので残る)
- `resolveMemberMention`(onQueueEnd/onPlayerUpdate で使用、stopCommand も使うので残る)
- `services.panelUpdater`(onQueueEnd/onPlayerUpdate で使用、playCommand の ALLOWED_MENTIONS / stopCommand の finalizePanel でも使うので残る)
- `PlayerUpdateEvent / QueueEndEvent / TrackEndEvent`(listener デコレータで残す)

ruff の unused-import 検出に任せて機械的に整理する。

### 2.4 スコープ外

- 現行 SPEC 契約(custom_id 17, player.store キー 5, コマンド名 9)は不変
- 日本語 UI 文言・エラーメッセージ・disconnect の force フラグは 1 バイト不変
- `services/audioFilters.py` の 3 個の音声フィルタ関数(getTimescale/changeSpeed/changePitch)は 1 バイト変更しない
- 親 SPEC.md §8/§8.1 のバックログ追加なし

## 3. 不変条件

親 SPEC.md §5 に加えて本 PR 固有:

1. **挙動完全不変**: 3 個の lavalink hook の中身は 1 バイト変更しない(移設のみ)。putPrevQueue の method 化に伴う `track.position = 0` の二重代入解消は**同一代入の統合**であり挙動不変
2. **listener デコレータの契約**: `@lavalink.listener(EventType)` は Cog インスタンスメソッドに付ける必須。委譲経由でも登録は cog の method 名として行う
3. **method 名 `putPrevQueue`**: 既存関数名と揃えて呼び出し側の混乱を避ける(`putPrev` などへの改名はしない)
4. **循環依存ゼロ**: `services/lavalinkHooks.py` は `services/panelUpdater.py` を import する。両方 `services/` 内で意味的に自然
5. **audioFilters の絞り込み**: putPrevQueue 削除後、`services/audioFilters.py` は「Timescale フィルタ操作の 3 関数のみ」に絞られ、名前と実態が一致する

## 4. 受け入れ基準

1. `uv run ruff check .` → All checks passed!
2. `uv run pyright` → 0 errors, 0 warnings
3. **smoke test**:
   ```
   uv run python -c "import main, cogs.music, cogs.ping, cogs.help, services.lavalinkHooks; print('OK')"
   ```
4. **契約 diff**: custom_id 17 / player.store キー 5 / コマンド名 9 / 日本語文言 いずれも不変
5. **buttonHandler 網羅性**: `set(bh._HANDLERS.keys()) == bh._EXPECTED_CUSTOM_IDS`(16)引き続き成立
6. **削除確認**:
   - `grep -c "audioFilters.putPrevQueue" .` → 0(全て `player.putPrevQueue` へ)
   - `grep -c "putPrevQueue" services/audioFilters.py` → 0
   - `grep -c "handleTrackEnd\|handleQueueEnd\|handlePlayerUpdate" services/lavalinkHooks.py` → 各 1 以上
   - `cogs/music.py` の onTrackEnd/onQueueEnd/onPlayerUpdate はそれぞれ 3 行以下(デコレータ + async def + 委譲 1 行)
7. **`services/audioFilters.py` の関数数**: 3 個のみ(getTimescale, changeSpeed, changePitch)

## 5. 実施手順

### Phase 1: SPEC 執筆(本ファイル)→ 完了

### Phase 2: `objects/player.py` に `putPrevQueue` メソッド追加

- lavalink import が必要なら追加
- docstring で「track.position=0 を method 内で行う」ことを明記

### Phase 3: `services/audioFilters.py` から `putPrevQueue` を削除

- 呼び出しがなくなった `import lavalink` などを整理

### Phase 4: 呼び出しサイト 2 箇所を更新

- `services/buttonHandler.py::handleNext`: `player.putPrevQueue(_track)` に、外側 `_track.position = 0` を削除
- `cogs/music.py::onTrackEnd` はどうせ次 Phase で移設するので後回し

### Phase 5: `services/lavalinkHooks.py` 新設

- 3 個の handler 関数を実装
- import: discord, lavalink, time, typing, objects.client (LavalinkVoiceClient), objects.player (MusicPlayer), objects.utils (resolveMemberMention), services.panelUpdater, TYPE_CHECKING で cogs.music.MusicCog

### Phase 6: `cogs/music.py` の 3 listener を委譲化

- import 追加: `from services import lavalinkHooks`
- 3 メソッドの中身を 1 行委譲に置換
- 使われなくなった import(`time`, `audioFilters`)を整理

### Phase 7: 検証

- ruff / pyright / import
- 契約 grep + 網羅性 assert
- 行数変化

## 6. ロールバック

```
git checkout HEAD cogs/music.py objects/player.py services/audioFilters.py services/buttonHandler.py
rm services/lavalinkHooks.py spec/SPEC_REFACTOR_PR7.md
```
