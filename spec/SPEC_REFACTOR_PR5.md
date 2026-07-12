# SPEC_REFACTOR_PR5.md — queuePagination 分離 + check デコレータ化(分割計画最終段)

対象ブランチ: `lavalink` / 作成日: 2026-07-11 / 親仕様: `SPEC.md` / 前段: `SPEC_REFACTOR_PR4.md`

`cogs/music.py` 分割計画の**第 5 段階(最終)**。以下の 2 テーマを 1 PR にまとめる:

1. `pagenation` / `queuePagenation` の `objects/queuePagination.py` への切り出し
2. `@requirePlaying` / `@requireSameVC` を `@app_commands.check` として導入、5 段 pre-flight のコピペを 4 コマンドから排除

**挙動改善**を 2 点含む(ephemeral 統一。§3 参照)。

## 1. 背景

### 1.1 queuePagination

現行 `cogs/music.py` にある `pagenation`(9 行の純関数)と `queuePagenation`(88 行、Embed+View 構築 + editQueue 送信 or followup)は music cog 固有の処理ではない — pure ロジックとしてキュー Embed を組み立てているだけ。切り出しの恩恵:
- ceil ページ計算(SPEC #19)、`queuePagenation,{page}` custom_id 生成、`ALLOWED_MENTIONS` 使用など、契約集中箇所が 1 ファイルに凝集
- MusicCog から 100 行減
- buttonHandler.handleQueuePagenation の委譲先が `objects` 配下に統一

### 1.2 5 段 pre-flight のコピペ

以下 4 コマンド(pitch / volume / loop / toggle)は同一の 15 行 pre-flight を持つ:

```python
await interaction.response.defer()
if interaction.guild is None: return
voiceClient = cast(...)
if not voiceClient:
    await interaction.followup.send("コマンドを実行する前に、曲を再生してください。")
    return
player = cast(...)
if player is None:
    await interaction.followup.send("コマンドを実行する前に、曲を再生してください。")
    return
if not playerCheck.isInBotVoiceChannel(interaction, voiceClient):
    await interaction.followup.send(
        "ボットと同じボイスチャンネルに参加してください。", ephemeral=True
    )
    return
```

4 × 15 = **60 行の重複**。discord.py には `@app_commands.check` があり、これを 2 つ(`requirePlaying`, `requireSameVC`)積むだけで pre-flight を宣言的に表現できる。エラーメッセージは `MusicCommandError` を raise → `main.onTreeError` が拾って表示する既存フローに乗る(SPEC #9 で構築済み)。

### 1.3 対象外のコマンド

- `queueCommand`: view-only なので `@requireSameVC` は不要。かつ error 文言が「現在曲を再生していません。」で他と異なる。**inline check のまま**残す。
- `stopCommand`: player が None でも disconnect したい特殊仕様(voice client の掃除)。`@requirePlaying` を付けると player None で早期 raise してしまうので、**inline check のまま**残す。
- `playCommand`: 既に `@app_commands.check(playerCheck.createPlayer)` が付いている。無変更。

## 2. スコープ

### 2.1 新規ファイル: `objects/queuePagination.py`

```
pagenation(queue, page, *, pageSize=10) -> tuple
    純関数。startIndex/endIndex のスライスして tuple を返す。

async queuePagenation(cog, interaction, page=1, *, edit=False) -> None
    現行 MusicCog.queuePagenation の全ロジックを移設。
    - defer 冪等ガード(SPEC #3)
    - guild/voiceClient/player の 3 段 None 検証
    - queue.copy() + player.current insert
    - Embed 組み立て(resolveMemberMention)
    - 3 ボタン View(⏪ / 🔄 / ⏩)with `queuePagenation,{page}` custom_id
    - ceil ページ計算 max(1, (len + pageSize - 1) // pageSize)(SPEC #19)
    - edit=True: cog.editQueue.put((interaction, {embed,view,allowed_mentions}))
    - edit=False: interaction.followup.send(embed, view)
```

`cog` は MusicCog を想定(editQueue アクセスのため)。circular import 対策で `TYPE_CHECKING` + 文字列アノテーション。

### 2.2 `objects/playerCheck.py` の拡張

以下 3 要素を追加:

```
async def requirePlaying(interaction) -> bool
    @app_commands.check として使う。guild/voice_client/player の 3 段検証。
    失敗時は NoGuildError または MusicCommandError を raise。
    成功時は True を返す。

async def requireSameVC(interaction) -> bool
    @app_commands.check として使う。呼び出し者が bot と同じ VC にいることを検証。
    guild/voice_client の 2 段検証(player は required でない — requirePlaying が担当)。
    失敗時は NoGuildError または MusicCommandError を raise。
    成功時は True を返す。

def resolveActivePlayer(interaction) -> tuple[LavalinkVoiceClient, MusicPlayer]
    requirePlaying が通ったあと、コマンド本体で voiceClient/player を non-None として narrowing。
    pyright の narrowing が check 越しには効かないため、明示的な cast + assert で対応。
```

### 2.3 `cogs/music.py` の変更

**削除**:
- `MusicCog.pagenation`(9 行)
- `MusicCog.queuePagenation`(88 行)
- pitchCommand / volumeCommand / loopToggleCommand / toggleCommand の**各 15 行の pre-flight**(合計 60 行)
- 使わなくなった import: `cast`(削除可能なら)、buttonHandler や panelUpdater の import は残る

**追加**:
- import: `from objects import queuePagination`
- 4 コマンドに `@app_commands.check(playerCheck.requirePlaying)` + `@app_commands.check(playerCheck.requireSameVC)` を付与

**書き換え**:
- 4 コマンドの本体: `voiceClient, player = playerCheck.resolveActivePlayer(interaction)` に集約
- `queueCommand`: `await self.queuePagenation(...)` → `await queuePagination.queuePagenation(self, ...)`

### 2.4 `objects/buttonHandler.py` の変更

- import 追加: `from objects import queuePagination`(既存の `from objects import audioFilters, panelUpdater, playerCheck` の兄弟)
- `handleQueuePagenation`: `await ctx.cog.queuePagenation(...)` → `await queuePagination.queuePagenation(ctx.cog, ...)`

## 3. 意図的な挙動改善 2 点(SPEC の例外的許容)

親 SPEC.md §2 の受け入れ基準 4「Discord 上での可視挙動は 1 文字も変わらない」の**例外**として、以下 2 点を明示的に許容する:

### 3.1 「曲を再生していません」エラーの ephemeral 化

**変更前**: pitch/volume/loop/toggle で "コマンドを実行する前に、曲を再生してください。" を `followup.send(...)`(**非ephemeral**、チャンネル全員に見える)で送っていた。

**変更後**: check 失敗が `MusicCommandError` を raise → `main.onTreeError` で `send_message(..., ephemeral=True)`(**ephemeral、呼び出し者のみに見える**)。

**理由**:
- 同じコード内で "ボットと同じボイスチャンネルに参加してください。" は既に ephemeral だった(現行から一貫性欠如)
- `queueCommand` の "現在曲を再生していません。" も既に ephemeral
- onButtonClick の同種エラーも全て ephemeral
- ephemeral 化はチャンネルのノイズを減らす UX 改善
- **文言自体は不変**

### 3.2 defer の削除(check 失敗時)

**変更前**: 各コマンドは冒頭で `await interaction.response.defer()` を呼ぶ。check 失敗時も defer 済みの状態でエラーメッセージを followup で送る。

**変更後**: check は defer より前に走る。check 失敗時は defer されないため、`main.onTreeError` の `is_done()` チェックが False で `response.send_message` を使う。

**理由**:
- discord.py の `@app_commands.check` の仕様上の帰結(避けられない)
- ユーザー可視の挙動としては「エラー時に "Bot は考えています…" 表示が出ない」だけで、成功時の defer 挙動は不変

## 4. 不変条件

親 SPEC.md §5 の契約に加えて、本 PR 固有:

1. **queuePagination の logic 不変**: pagenation の startIndex/endIndex 計算、queue.copy() + insert の順序、Embed の f-string、View の 3 ボタン構成、custom_id `queuePagenation,{page}` の 3 つ、`ALLOWED_MENTIONS` の参照、`resolveMemberMention` の呼び出しはすべて 1 バイト変更しない。
2. **ceil ページ計算**: `max(1, (len(queue) + pageSize - 1) // pageSize)`(SPEC #19)を維持。
3. **pageSize = 10** を維持。
4. **エラー文言**: "コマンドを実行する前に、曲を再生してください。" と "ボットと同じボイスチャンネルに参加してください。" は 1 バイト変更しない(§3 で挙げた ephemeral 変更は許容するが**文言は不変**)。
5. **check の順序**: `@app_commands.check(requirePlaying)` を先に、`@app_commands.check(requireSameVC)` を後に付ける(requireSameVC は requirePlaying が済んでいることを前提にしない — 独立して voice_client を検証するが、requireSameVC 単独で失敗すると "曲を再生してください" になるので、順序で意図を表現する)。
6. **queueCommand の inline check**: そのまま維持("現在曲を再生していません。" 文言と ephemeral=True の呼び出しを 1 バイト変更しない)。
7. **stopCommand の inline check**: そのまま維持(player None でも disconnect する挙動の温存)。
8. **playCommand**: `@app_commands.check(playerCheck.createPlayer)` は無変更。

## 5. 受け入れ基準

1. `uv run ruff check .` → **All checks passed!**
2. `uv run pyright` → **0 errors, 0 warnings**
3. `uv run python -c "import main, cogs.music, cogs.ping, cogs.help, objects.queuePagination; print('OK')"`
4. **契約 diff**:
   - `custom_id` 生値 17(panel.py 14 + queuePagination.py の "queuePagenation,{page}" 3)不変
   - `player.store/fetch` キー 5 種不変
   - コマンド名 9 個不変
   - **エラー文言**: "コマンドを実行する前に、曲を再生してください。" が MusicCommandError の raise 引数として 1 箇所以上あり、"ボットと同じボイスチャンネルに参加してください。" も同様
5. **削除確認**:
   - `grep -c "def pagenation" cogs/music.py` → 0
   - `grep -c "async def queuePagenation" cogs/music.py` → 0
   - `grep -c "playerCheck.isInBotVoiceChannel" cogs/music.py` → 0(全て check 経由になる)
6. **行数変化**: `cogs/music.py` が約 -150 行、`objects/queuePagination.py` に +130 行、`objects/playerCheck.py` に +40 行。ネット +20 行(クラス・関数の docstring 分)。
7. **cogs/music.py の最終サイズ**: 目標 **250 行以下**(元 1046 → 現在 579 → 目標 ~430)。実際は 4 コマンドから 15 行×4 = 60 行、queuePagination 97 行を削除で ~420 行を目指す。

## 6. 実施手順

### Phase 1: SPEC 執筆(本ファイル)→ 完了

### Phase 2: `objects/queuePagination.py` を作成

- `from __future__ import annotations` を先頭に
- `pagenation` 純関数と `queuePagenation` async 関数を実装
- `cog: MusicCog` は文字列アノテーション
- `panelUpdater.ALLOWED_MENTIONS` 参照

### Phase 3: `objects/playerCheck.py` に 3 要素追加

- `requirePlaying`(raise NoGuildError / MusicCommandError)
- `requireSameVC`(同上)
- `resolveActivePlayer` narrowing helper

### Phase 4: `objects/buttonHandler.py` を更新

- import 追加: `from objects import queuePagination`(既存のグループに)
- `handleQueuePagenation`: `ctx.cog.queuePagenation` → `queuePagination.queuePagenation(ctx.cog, ...)`

### Phase 5: `cogs/music.py` の書き換え

順序:
1. import 追加: `from objects import queuePagination`
2. `MusicCog.pagenation` と `MusicCog.queuePagenation` を削除
3. pitchCommand / volumeCommand / loopToggleCommand / toggleCommand に check デコレータ 2 つ追加、pre-flight 削除、`resolveActivePlayer` で narrow
4. `queueCommand`: `self.queuePagenation` → `queuePagination.queuePagenation(self, ...)`
5. 未使用 import を整理

### Phase 6: 検証

- ruff / pyright / import
- 契約 grep
- 行数変化
- (可能なら)実機で pitch/volume/loop/toggle の正常系と VC 未参加時の ephemeral エラーを確認

## 7. スコープ外

- 分割計画は本 PR で完了。以降は個別機能追加 or SPEC.md §8/§8.1 のバックログに戻る
- 親 SPEC.md §8/§8.1 のバックログ追加なし

## 8. ロールバック

```
git checkout HEAD cogs/music.py objects/playerCheck.py objects/buttonHandler.py
rm objects/queuePagination.py SPEC_REFACTOR_PR5.md
```
