# SPEC_REFACTOR_PR8.md — MixPanel 分離に伴う buttonHandler の再設計

対象ブランチ: `lavalink` / 作成日: 2026-08-08 / 親仕様: `SPEC.md` / 前段: `SPEC_REFACTOR_PR7.md`

音量 / 速度 / ピッチの操作を `MusicPanel` から `MixPanel`(ephemeral)へ分離した結果、
`services/buttonHandler.py` の dispatch 設計が破綻したため作り直す。

**挙動不変ではない**(§2.1 は明確なバグ修正)。

## 1. 背景

### 1.1 handler の戻り値契約が 3 値目を表現できない

PR4 で確立した契約は 2 値だった:

| 戻り値 | 意味 |
| --- | --- |
| `True` | handler 内で完結。末尾の panel refresh を実行しない |
| `None` | 末尾の panel refresh(= `MusicPanel` 再構築)を実行 |

MixPanel 分離により第 3 の状態「**押された Mix パネルを再構築する**」が必要になったが、
`bool | None` では表現できない。ここに `bool` をもう 1 個足すと、
「True/None/False/(True, True)…」の意味を読む側が覚える羽目になる。

### 1.2 dispatch table の二重管理

`_HANDLERS` と `_EXPECTED_CUSTOM_IDS` を手で同期させ、ずれを import 時 `assert` で検出していた。
ボタン 1 個の追加に 2 箇所の編集が必要で、パネルが 2 枚に増えた今もっとも壊れやすい。

### 1.3 描画コードの重複

`objects/mixPanel.py` は `objects/panel.py` から `_progressBar` を丸ごとコピーしていた。
加えて `_buildAdItems`(広告セクション)もコピーされているが、MixPanel は広告を表示しないため
**完全な未使用コード**だった。

## 2. スコープ

### 2.1 バグ: Mix パネルのボタンが Mix パネル自身を破壊する

component interaction に対する `InteractionResponse.defer()` は `DEFERRED_MESSAGE_UPDATE` になる。
つまり以降の `edit_original_response()` の対象は「**押されたボタンが載っていたメッセージ**」。

`handleButtonClick` の末尾は無条件に

```python
panel = panelUpdater.buildPanel(...)  # MusicPanel
await panelUpdater.schedulePanelEdit(cog, interaction, panel)
```

を実行していたため、`volumeUp` など MixPanel 上のボタンを押すと

- ephemeral な Mix パネルが `MusicPanel` の中身(⏮⏹⏭ 等)で上書きされる
- 音量 / 速度 / ピッチのバーは一度も更新されない

という二重の誤りになる。

### 2.2 潜在バグ: coalesce キーの不一致

`MessageEditQueue._targetKey` は `Interaction` を `("i", id)`、`Message` を `("m", id)` として区別する。
主パネルの更新経路は 2 つあり、キーが揃っていなかった:

| 経路 | 対象 | キー |
| --- | --- | --- |
| `onPlayerUpdate`(約 5 秒毎) | `discord.Message` | `("m", panelMessageId)` |
| ボタン押下の末尾処理 | `discord.Interaction` | `("i", interactionId)` |

同一バッチに両方が入ると **同じメッセージに 2 回 edit が飛び**、
古い内容を持つ方が後勝ちしうる(SPEC #12 の coalesce が効かない)。

### 2.3 requester mention の二重解決

`member_cache_flags=none()` かつ members intent 無しのため `guild.get_member` はほぼ常に `None` を返し、
`resolveMemberMention` は毎回 `fetch_member` を打つ。
pre-flight と末尾処理で 1 クリックあたり 2 回解決していた。

## 3. 変更内容

### 3.1 `Refresh` enum と宣言的レジストリ(`services/buttonHandler.py`)

handler の戻り値契約を廃止し、`-> None` に統一する。
再描画対象は `@button` デコレータの `refresh` 引数**だけ**が宣言する。

```python
class Refresh(enum.Enum):
    NONE = "none"  # handler 内で完結
    MUSIC = "music"  # 主パネル(MusicPanel)を再構築 — 対象は player の messageId
    MIX = "mix"  # 押された Mix パネルを再構築 — 対象は interaction 自身


@button("volumeUp", refresh=Refresh.MIX)
async def handleVolumeUp(ctx: ButtonContext) -> None:
    await ctx.player.set_volume(int(clamp(ctx.player.volume + 5, 0, 100)))
```

`@button` は定義と同時に `_HANDLERS` へ登録するため、`_EXPECTED_CUSTOM_IDS` と
import 時 assert は不要になり削除した(登録漏れが構造的に起こせない)。
`custom_id` の重複登録は `RuntimeError` で即死する。

登録内容(17 個):

| custom_id | refresh | requiresVoice | 所属パネル |
| --- | --- | --- | --- |
| `prev` / `next` / `stop` | NONE | ✓ | MusicPanel |
| `resume` / `pause` / `reverse` / `forward` / `loop` / `shuffle` | MUSIC | ✓ | MusicPanel |
| `mix` | NONE | ✓ | MusicPanel |
| `volumeUp` / `volumeDown` / `speedUp` / `speedDown` / `pitchUp` / `pitchDown` | MIX | ✓ | MixPanel |
| `queuePagenation` | NONE | — | /queue |

- `mix` は NONE。Mix パネルは別メッセージとして開くだけで主パネルは変化しないため、
  従来の「戻り値 None → 主パネルを再構築」は 1 クリックあたり無駄な edit を 1 回増やしていた。
- VC 参加チェック(SPEC #14)の免除は `customField[0] != "queuePagenation"` というマジック文字列比較を
  やめ、`requiresVoice=False` の宣言に移した。

### 3.2 Refresh.MUSIC の対象を Interaction → Message に統一

`_refresh()` の MUSIC 経路は `panelUpdater.refreshPanel()`(= `player` の `messageId` から Message を解決)を使う。

- §2.1 の「押されたボタンが載っていたメッセージ」依存が消える
- §2.2 の coalesce キーが `onPlayerUpdate` と一致する

Message は `player.store("_panelMessage")` にキャッシュ済み(SPEC #22)のため追加の API 呼び出しは発生しない。
`messageId` / `channelId` は再生開始前(`playCommand` のパネル投稿時)に必ず store されるので、
ボタンが存在する時点で解決できることが保証される。

### 3.3 `ButtonContext.mentionFor()` によるメモ化

`requestAuthorMention` フィールド(pre-flight で eager 解決)を廃止し、
requester id をキーにした `dict` でメモ化する `async` アクセサに置き換えた。

- MUSIC 経路: 1 クリックあたり `fetch_member` 2 回 → 1 回
- MIX / NONE 経路: 2 回 → **0 回**(mention を必要としないため)

### 3.4 バー絵文字(bar / circle / graybar)の保持場所を 1 箇所へ

3 個の絵文字はアプリケーション絵文字でログイン後にしか取得できないため、

```
MusicCog.bar/circle/graybar → panelUpdater.buildPanel/buildMixPanel
  → MusicPanel.__init__ / MixPanel.__init__ → _progressBar()
```

と 4 階層に渡って str 3 個を引き回していた。加えて `_progressBar` は `panel.py` と
`mixPanel.py` に同じ実装がコピーされていた。

実体はプロセス内で不変な 3 文字なので、新設した **`objects/progressBar.py`** を唯一の保持場所とする。

```python
# 取得(MusicCog.on_ready から 1 度だけ)
await progressBar.loadEmojis(self.bot)

# 描画(各 Panel)
playProgressBar = progressBar(playProgressPercentage, showCircle=True)  # 再生バー
volumeBar = progressBar(player.volume / 100)  # 音量 / 速度 / ピッチ
```

`showCircle` は現在位置に circle(つまみ)を置くかのフラグ。「今どこを再生しているか」が
意味を持つ再生バーだけ `True` にし、量を示すだけの 音量 / 速度 / ピッチ は既定の `False`。
どちらの分岐でも戻り値がちょうど `length` 文字になることが本関数の契約(SPEC #28)。

これに伴う削除:

| 削除したもの | 理由 |
| --- | --- |
| `MusicCog.bar` / `.circle` / `.graybar`(属性 + `__slots__` 3 件) | 保持場所が progressBar モジュールへ移動 |
| `MusicPanel.__init__` の `bar` / `circle` / `graybar` 引数 | 同上 |
| `MixPanel.__init__` の `bar` / `circle` / `graybar` 引数 | 同上 |
| `panelUpdater.buildMixPanel()` | 引数が消え `MixPanel(player)` の 1 行になったためラッパの存在意義が消滅。buttonHandler が直接構築する |
| `buildPanel()` の `cog` 引数 | 用途が `cog.bar/circle/graybar` だけだった |
| `objects/utils.py` の `progressBar()` | `objects/progressBar.py` へ移設 |
| `mixPanel.py` の未使用 `_buildAdItems` と `Ad` import | MixPanel は広告を表示しないため完全なデッドコード |

副次的な修正:

- **API 呼び出しが 3 回 → 1 回**。従来は絵文字 1 個ごとに `fetch_application_emojis()` を呼んでいた。
- **絵文字が見つからないときの `"None"` 表示を修正**。従来は `str(discord.utils.get(...))` が
  `None` を文字列化し、バーが `"NoneNoneNone..."` になっていた。
  現在は ASCII フォールバック(`━` / `●` / `─`)で描画し、`music` ロガーに warning を出す。

`panelUpdater.schedulePanelEdit` の `panel` 引数は `MusicPanel` → `discord.ui.LayoutView` に緩和し、
MusicPanel / MixPanel の両方を受けられるようにした。

## 4. 影響しない範囲

- `custom_id` 文字列は 1 つも変更していないため、既存メッセージ上のパネルは引き続き動作する
- `cogs/music.py` の `on_interaction` → `handleButtonClick` の 1 行委譲は変更なし
- `MessageEditQueue` / `lavalinkHooks` / `queuePagination` は無変更

## 5. 検証

- `ruff check .` — pass
- `pyright` — 0 errors
- `_HANDLERS` に 17 件が登録され、refresh / requiresVoice が §3.1 の表と一致することを import 時に確認
