# SPEC_REFACTOR_PR2.md — パネル更新層の集約(panelUpdater)

対象ブランチ: `lavalink` / 作成日: 2026-07-11 / 親仕様: `SPEC.md` / 前段: `SPEC_REFACTOR_PR1.md`

`cogs/music.py` 分割計画の**第 2 段階**。パネル更新に関わる**5 サイトの MusicPanel 構築 + editQueue.put 重複**と**3 サイトの `fetch_message` 直呼び**を `objects/panelUpdater.py` に集約する、**挙動不変**のリファクタ。

## 1. 背景 — 三重四重の重複

現行 `cogs/music.py` には MusicPanel を構築して editQueue に put する場所が **5 サイト**ある:

| # | サイト | 行 | finished | 用途 |
|---|---|---|---|---|
| 1 | onButtonClick "stop" case | 300-323 | `True` | ボタン→切断時のパネル終了化 |
| 2 | onButtonClick match tail | 370-388 | 変数(通常 False) | 各ボタン処理後の即時反映 |
| 3 | onQueueEnd | 541-565 | `True` | キュー終了時のパネル終了化 |
| 4 | onPlayerUpdate | 592-616 | `False` | 5 秒毎の定期更新 |
| 5 | stopCommand | 888-912 | `True` | /stop 時のパネル終了化 |

このうち **#1, #3, #5 の三重重複**が最大の問題(いずれも「finished=True の MusicPanel を組んで editQueue に put する」パターン)。片方だけ SPEC を反映して片方を忘れるバグを生む温床。

また `fetch_message` の直呼びも:

| # | サイト | 経路 |
|---|---|---|
| A | onPlayerUpdate | `_getPanelMessage(player)` 経由(キャッシュ効いてる) |
| B | onQueueEnd | `channel.fetch_message(messageId)` 直呼び(毎回 HTTP) |
| C | onButtonClick "stop" | `channel.fetch_message(messageId)` 直呼び(毎回 HTTP) |
| D | stopCommand | `channel.fetch_message(messageId)` 直呼び(毎回 HTTP) |

B/C/D も `_getPanelMessage` 経由に統一することで **SPEC #22 のキャッシュヒット率が改善**する(既に onPlayerUpdate で作られていたキャッシュを再利用できるようになる)。

## 2. スコープ

### 2.1 新規ファイル: `objects/panelUpdater.py`

以下の関数群を定義する。

| 関数 | 目的 |
|---|---|
| `getPanelMessage(cog, player)` | `_getPanelMessage` を移設。名前は `_` を落として module public に |
| `buildPanel(cog, player, track, mention, *, finished)` | MusicPanel の共通コンストラクタ。cog.bar/circle/graybar を暗黙注入 |
| `schedulePanelEdit(cog, target, panel)` | editQueue.put に `allowed_mentions` の共通 AllowedMentions を付けて enqueue |
| `refreshPanel(cog, player, track, mention, *, finished)` | getPanelMessage → buildPanel → schedulePanelEdit の共通フロー。message 解決失敗時はサイレント no-op |
| `finalizePanel(cog, player, track, mention)` | `refreshPanel(..., finished=True)` の名前付き別名(意図を明確化) |

モジュール定数として:
```python
_ALLOWED_MENTIONS = discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False)
```

### 2.2 `cogs/music.py` の変更

**削除**:
- `MusicCog._getPanelMessage`(179-201 行、`panelUpdater.getPanelMessage(self, ...)` に置き換え)

**書き換え**(5 サイトのパネル構築 + editQueue.put):

| サイト | 変更前(概要) | 変更後 |
|---|---|---|
| onButtonClick "stop" case | 手動 fetch_message + MusicPanel + editQueue.put | `await panelUpdater.finalizePanel(self, player, track, requestAuthorMention)` |
| onButtonClick match tail | MusicPanel(track, ..., finished=finished) + editQueue.put(interaction) | `panel = panelUpdater.buildPanel(self, player, track, requestAuthorMention, finished=finished); await panelUpdater.schedulePanelEdit(self, interaction, panel)` |
| onQueueEnd | 手動 fetch_message + MusicPanel + editQueue.put + disconnect | `await panelUpdater.finalizePanel(self, player, lastTrack, mention)` + 既存 disconnect |
| onPlayerUpdate | _getPanelMessage → MusicPanel + editQueue.put | `await panelUpdater.refreshPanel(self, player, track, mention, finished=False)` |
| stopCommand | 手動 fetch_message + MusicPanel + editQueue.put + disconnect + followup | `await panelUpdater.finalizePanel(self, player, track, mention)` + 既存 disconnect + followup |

`allowed_mentions=discord.AllowedMentions(everyone=False,...)` の指定は `panelUpdater._ALLOWED_MENTIONS` に一本化される。

## 3. 不変条件

親 SPEC.md §5 の契約に加えて、本 PR 固有:

1. **挙動完全不変**: 最終的な HTTP 呼び出しの回数・順序、投稿される Embed/View 内容、`disconnect(force=True/False)` の指定は変更しない。
2. **AllowedMentions**: `discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False)` の 4 パラメータは 1 文字も変えない(SPEC.md §5.2 の日本語 UI 文字列同様、ユーザー可視挙動)。
3. **`player.store/fetch` キー**: `channelId` / `messageId` / `_panelMessage` / `lastFinishedTrack` は不変。
4. **fetch_message のフォールバック**: 既存の `try: message = await channel.fetch_message; except (NotFound, Forbidden): message = None` パターンは、`getPanelMessage` 内の catch 節に統合される(SPEC #15 と同じ精神)。
5. **onQueueEnd の disconnect 順序**: panelUpdater.finalizePanel は disconnect を行わない(pure な panel 更新のみ)。disconnect(force=True) は onQueueEnd 側に残す。stopCommand も同様。
6. **onButtonClick.stop の disconnect(force=False)**: 現行 `await voiceClient.disconnect()`(force なし)は不変。stopCommand の `disconnect(force=True)` とは意図的に区別されている。
7. **キャッシュキー `_panelMessage`**: `getPanelMessage` の実装は前段 `_getPanelMessage` と同じキャッシュを共有する(key 文字列 `_panelMessage` を維持)。
8. **followup.send("切断しました。")**: stopCommand が返す文言は変更禁止。

## 4. 受け入れ基準

すべて成立すること:

1. `uv run ruff check .` → **All checks passed!**
2. `uv run pyright` → **0 errors, 0 warnings**
3. `uv run python -c "import main, cogs.music, cogs.ping, cogs.help, objects.panelUpdater; print('OK')"`
4. **契約 diff**:
   - custom_id 文字列 17 個(panel.py 内 14 + music.py 内 3)不変
   - `player.store/fetch` キー 5 種類が対称的に使われている
   - コマンド名 `name=` kwarg が 9 個(play/timescale/volume/queue/loop/toggle/stop/ping/help)
   - `allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False)` が **panelUpdater.py 内に 1 箇所**に集約されている(`_ALLOWED_MENTIONS` 定数)
5. **行数変化**: `cogs/music.py` が約 -90〜120 行、`objects/panelUpdater.py` に約 +80〜100 行。ネット減少。
6. **MusicPanel 構築サイト**: `cogs/music.py` 内の `MusicPanel(` 出現回数が **5 → 0**(全部 panelUpdater.buildPanel 経由になる)

## 5. 実施手順

### Phase 1: SPEC 執筆(本ファイル)→ 完了

### Phase 2: `objects/panelUpdater.py` を新規作成

- 5 関数と 1 モジュール定数を実装
- import: `from typing import cast`, `discord`, `lavalink`, `MusicPlayer`, `MusicPanel`
- circular import 対策: `cog` は動的型(TYPE_CHECKING でも回避可能だが、シンプルに `object` or forward ref)

### Phase 3: `cogs/music.py` の書き換え

順序:
1. import 追加: `from objects import panelUpdater`
2. `MusicCog._getPanelMessage` を削除
3. onPlayerUpdate(サイト A)を `panelUpdater.refreshPanel` に置換
4. onQueueEnd(サイト B+#3)を `panelUpdater.finalizePanel` に置換(disconnect は残す)
5. stopCommand(サイト D+#5)を `panelUpdater.finalizePanel` に置換(disconnect + followup は残す)
6. onButtonClick "stop" case(サイト C+#1)を `panelUpdater.finalizePanel` に置換
7. onButtonClick match tail(#2)を `panelUpdater.buildPanel + schedulePanelEdit` に置換
8. 使用しなくなった import を整理

### Phase 4: 検証

- ruff / pyright / import
- 契約 grep(§4)
- 行数変化(§4-5)

## 6. スコープ外

- `MessageEditQueue` のクラス化は PR 3
- `onButtonClick` の dispatch table 化は PR 4
- `@requirePlaying`/`@requireSameVC` デコレータは PR 5
- 親 SPEC.md §8/§8.1 のバックログ追加なし

## 7. ロールバック

```
git checkout HEAD cogs/music.py
rm objects/panelUpdater.py SPEC_REFACTOR_PR2.md
```
