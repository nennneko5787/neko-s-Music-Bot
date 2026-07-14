# SPEC_FEATURE_ADS.md — 広告機能(パネル埋め込み方式)

## 1. 概要

`config/ads/*.json` から広告データを読み込み、**MusicPanel の末尾に
Separator + Section(Thumbnail + 短文) として常時埋め込む**。

MusicPanel は 5 秒ごとに edit-in-place で更新されるので、広告は「新しい
メッセージ」ではなく既存パネルの一部として表示される。通知は増えず、
チャンネル上のスクロール量も一切増えない。

- 新しいトラックに切り替わった瞬間にランダム広告を rotate
- 同一トラック連続(LOOP_SINGLE / 1 曲 LOOP_QUEUE)は現在の広告を維持
- 広告 0 件のときはパネルから広告セクション自体が消える(既存挙動と等価)

## 2. モチベーション

- 従来案(独立 LayoutView メッセージを 8〜15 曲ごとに新規送信)は、
  頻度を絞ってもチャンネルにメッセージ通知が増えてスパム感があった。
- パネル埋め込みならメッセージ数は増えず、視覚的にも UI の一部として自然。
- MusicPanel は既に LayoutView なので、Section を 1 個追加するだけで実現できる。

## 3. データモデル

### 3.1 `objects/ad.py::Ad`(既存)

pydantic BaseModel(変更なし)。

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|----------|------|
| `id` | `str` | ✓ | — | 広告 ID |
| `title` | `str` | ✓ | — | 見出し(hyperlink されるので短めに) |
| `description` | `str` | ✓ | — | 本文(1〜2 行を推奨、パネルに収まる長さ) |
| `imageUrl` | `str` | ✓ | — | Thumbnail の画像 URL |
| `linkUrl` | `str \| None` | ✗ | `None` | タイトルの hyperlink 先 |
| `weight` | `int` | ✗ | `1` | 重み付き抽選の重み(≥1) |
| `enabled` | `bool` | ✗ | `True` | false なら候補から除外 |

**description の長さガイド**: パネル UI に収まるよう 1〜2 行 (〜60〜80 文字) 推奨。
極端に長くても panel は縦に伸びるだけで壊れないが、UI 汚染になるため注意。

## 4. UI 層 (Components V2)

### 4.1 MusicPanel の末尾に埋め込み

`objects/panel.py::MusicPanel.__init__(..., ad: Ad | None = None)` を新設。
`ad is not None` かつ MusicPanel が `finished=False` の描画パスに入ったとき、
Container 末尾に次を追加する:

```
Separator(spacing=large)
Section(
  TextDisplay("-# 広告 / Ad"),
  TextDisplay("**[<title>](<linkUrl>)**" if linkUrl else "**<title>**"),
  TextDisplay("-# <description>"),
  accessory=Thumbnail(media=imageUrl, description=title),
)
```

**契約:**
- `finished=True` の "再生終了" パネルには広告を表示しない(セッション終わりに UI を汚さない)
- Thumbnail は Section の accessory として右側に小さく表示される(全面 MediaGallery 使わない)
- LinkButton は使わない(title の hyperlink で代替、パネルの button 群を汚染しない)
- `buttonHandler._EXPECTED_CUSTOM_IDS` 契約と一切干渉しない(custom_id なし)

### 4.2 `services/adService.py`(縮小)

**Public API:**

- `loadAds(directory: str | Path = "config/ads") -> int`
  ディレクトリ配下の `*.json` を全部読み、有効広告を内部リストに格納。
  ディレクトリ非存在時は 0 件でリターン(致命的にしない)。
- `pickRandomAd() -> Ad | None`
  内部リストから weight で重み付き抽選して 1 件返す。空なら None。
  純粋関数(state を触らない)。

**削除された API:**
- ~~`buildAdView`~~(AdView 自体を削除)
- ~~`maybeShowAd`~~(channel.send を廃止)
- ~~`clearGuildState`~~(per-guild state 撤廃)

**内部状態:**
- `_ADS: list[Ad]` — enabled=True のみ格納
- カウンタ / 閾値 / 失敗フラグは全廃止(パネル埋め込みは常時表示のため不要)

### 4.3 `objects/adPanel.py`(削除)

`AdView` は独立 LayoutView 送信用だったので削除。MusicPanel に統合された。

## 5. 呼び出しポイント

### 5.1 `main.py::setup_hook`

Cog 読み込み後に 1 度だけ `adService.loadAds()` を呼ぶ(不変)。

### 5.2 `services/lavalinkHooks.py::handleTrackStart`

TrackStart hook で「別トラックに切り替わった」瞬間にランダム広告を選択し、
`player.store("currentAd", ad)` に保存する。同一トラック連続なら現在の広告を維持。

```python
async def handleTrackStart(cog, event):
    player = cast(MusicPlayer, event.player)
    currentId = event.track.identifier
    lastCountedId = player.fetch("lastCountedAdTrackId")
    if lastCountedId == currentId:
        return  # 同一トラック(ループ) → 現在の広告を維持
    player.store("lastCountedAdTrackId", currentId)
    newAd = adService.pickRandomAd()
    player.store("currentAd", newAd)  # None も store(消したいときのため)
```

チャンネル送信は行わない。パネル自体が edit-in-place で次の onPlayerUpdate 時に
反映される(最大 5 秒後)。

### 5.3 `services/panelUpdater.py::buildPanel`

`player.fetch("currentAd")` で現在の広告を取得し、MusicPanel コンストラクタに渡す。
無しなら `None` が渡り、MusicPanel は広告セクションをスキップする。

## 6. 依存関係

pydantic(既存)を利用。追加変更なし。

## 7. エラーハンドリング契約

- JSON parse エラー / pydantic ValidationError → WARN ログ + 該当ファイル skip
- ディレクトリ不在 → INFO ログ + 0 件でリターン
- `imageUrl` が壊れている場合 → Thumbnail が Discord 側でエラー画像になる可能性。
  panel 全体は動作する(fallback として画像なしで表示される)。
- `_ADS` が空 → `pickRandomAd()` が常に None を返す → 広告セクション消える

## 8. 非目標

- 広告クリック計測: 対応しない(必要なら linkUrl 側で query param)
- ホットリロード: 再起動が必要
- Guild ごとの ON/OFF: 全 guild 一律
- 曲パネル外への独立ポスト: **廃止**(スパム性が問題だった)
- LinkButton: 使わない(pane button 群と混ざるため)

## 9. 契約(既存挙動を壊さないこと)

- MusicPanel の既存 16 個の custom_id ボタン群は不変。
- `buttonHandler._EXPECTED_CUSTOM_IDS` の網羅性 assertion は不変。
- WaitingView は変更なし(広告表示前は準備中のまま)。
- finalizePanel(再生終了パネル) にも広告は入らない。
- 広告 0 件の場合、MusicPanel の見た目は従来と完全に一致する。
- `/play` の応答フロー(defer → followup → WaitingView post → player.play())も変更なし。

## 10. 受け入れ基準

- [x] `objects/ad.py::Ad` は変更なし。
- [ ] `objects/adPanel.py` は削除されている。
- [ ] `objects/panel.py::MusicPanel` が `ad: Ad | None = None` パラメータを受け、
      `ad is not None` かつ `finished=False` のとき広告 Section を追加する。
- [ ] `services/adService.py` は `loadAds` と `pickRandomAd` のみを公開する。
- [ ] `services/lavalinkHooks.py::handleTrackStart` が
      dedup + `pickRandomAd` + `player.store("currentAd", ...)` を行う。
- [ ] `services/panelUpdater.py::buildPanel` が `player.fetch("currentAd")` を
      MusicPanel コンストラクタに渡す。
- [ ] `ruff check` / `pyright` が 0 error / 0 warning。
- [ ] 手動: 空の config/ads/ で再生 → パネルに広告セクション出ない。
- [ ] 手動: enabled=true の広告 1 件で再生 → パネル末尾に Separator + Thumbnail + 短文表示。
- [ ] 手動: LOOP_SINGLE で同曲リピート → 広告は変わらず維持。
- [ ] 手動: 別トラックへの ⏭ / TrackEnd 経由の遷移 → 広告 rotate。

## 11. ファイル差分

新規: なし

編集:
- `services/adService.py` — 大幅縮小
- `services/lavalinkHooks.py::handleTrackStart` — 送信削除 → rotate に変更
- `services/lavalinkHooks.py::handleQueueEnd` — clearGuildState 呼び出し削除
- `services/panelUpdater.py::buildPanel` — MusicPanel に `ad=` 渡す
- `objects/panel.py::MusicPanel` — `ad` パラメータ + 末尾 Section

削除:
- `objects/adPanel.py`
