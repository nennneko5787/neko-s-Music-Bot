# SPEC_FEATURE_ADS.md — 広告機能

## 1. 概要

`config/ads/*.json` から広告データを読み込み、`/play` 実行時に画像付き
**Discord Components V2 (LayoutView / Container)** メッセージとしてユーザーに
表示する機能を追加する。

トリガーはコマンド単位(1 曲/1 プレイリスト単位)。ギルドごとに 3〜5 回
のランダム間隔で表示され、確実にスポンサー露出を確保する。

Components V2 化の理由:
- MusicPanel / WaitingView が既に LayoutView 化されており、UI 体系が統一される。
- Container の accent_color でトーンを揃えられる(embed の色帯とほぼ同じ効果)。
- LinkButton を使えばクリック導線が明示的になり、モバイルでもタップしやすい。

## 2. モチベーション

- Bot 運営に伴うインフラコストの一部をスポンサー枠で回収したい。
- 既存の音楽体験(パネル・ボタン UI)を汚さず、独立したメッセージとして送る。
- 管理者が JSON ファイルを差し替えるだけで広告を差替え可能にする。

## 3. データモデル

### 3.1 `objects/ad.py::Ad`(新規)

pydantic BaseModel。

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|----------|------|
| `id` | `str` | ✓ | — | 広告 ID(重複可だがログ用に一意推奨) |
| `title` | `str` | ✓ | — | 見出し(H2 相当で表示) |
| `description` | `str` | ✓ | — | 本文(Markdown 可) |
| `imageUrl` | `str` | ✓ | — | 画像 URL(MediaGallery に貼る) |
| `linkUrl` | `str \| None` | ✗ | `None` | LinkButton の URL、タイトルのハイパーリンク先 |
| `weight` | `int` | ✗ | `1` | 重み付き抽選の重み(≥1) |
| `enabled` | `bool` | ✗ | `True` | false なら非表示 |

- `model_config = ConfigDict(extra="forbid")`:
  JSON のタイポを import 時に検出する。

### 3.2 JSON ファイル形式

`config/ads/<name>.json` に 1 ファイル 1 広告。ファイル名はソート順に
ロードされる(挙動決定要因ではないが、ログ順が安定する)。

```json
{
  "id": "example",
  "title": "サンプル広告",
  "description": "説明文",
  "imageUrl": "https://example.com/ad.png",
  "linkUrl": "https://example.com/",
  "weight": 1,
  "enabled": true
}
```

## 4. UI 層 (Components V2)

### 4.1 `objects/adPanel.py::AdView`(新規)

`discord.ui.LayoutView` サブクラス。`AdView(ad: Ad)` で 1 個の広告レイアウトを構築する。

**構造 (上→下):**

```
Container(accent_color=gold)
├─ TextDisplay: "## <title>" (linkUrl があれば [title](linkUrl) で hyperlink)
├─ TextDisplay: <description>
├─ MediaGallery(MediaGalleryItem(media=imageUrl, description=title))
├─ [linkUrl があれば] ActionRow(Button(style=link, url=linkUrl, label="詳しく見る"))
├─ Separator(spacing=small)
└─ TextDisplay: "-# 広告 / Ad"
```

**契約:**
- `timeout=None`(link button のみなので handler 不要)
- `custom_id` を持つ Button は含まない
  ⇒ `buttonHandler._EXPECTED_CUSTOM_IDS` 契約と一切干渉しない
- 送信時は `view=AdView(ad)` のみ、`embed=` は使わない
  (Components V2 と Embed の同時使用は Discord 側で拒否される)

### 4.2 `services/adService.py`(新規)

**Public API:**

- `loadAds(directory: str | Path = "config/ads") -> int`
  ディレクトリ配下の `*.json` を全部読み、有効広告を内部リストに格納。
  ディレクトリ非存在時は 0 件でリターン(致命的エラーにしない)。
  個別 JSON の parse 失敗は WARNING ログを出して skip(その 1 件だけ落ちる)。
- `buildAdView(ad: Ad) -> AdView`
  `AdView(ad)` を返す薄いファクトリ(単体テストからの呼び出し用)。
- `maybeShowAd(interaction, guildId) -> None`
  ギルド別カウンタを進め、閾値到達なら重み付き抽選で 1 件を LayoutView で送信。
  送信後はカウンタ 0、閾値を 3〜5 で再抽選。
  広告 0 件のときは何もしない。

**内部状態:**

- `_ADS: list[Ad]` — enabled=True のみ格納
- `_GUILD_COUNTERS: dict[int, int]` — 現在の /play 実行回数
- `_GUILD_THRESHOLDS: dict[int, int]` — 次に広告を出す閾値

**閾値: `random.randint(3, 5)`**
    初回はカウンタ 0/閾値 未設定 → 閾値をまず抽選し、以後 3〜5 回に 1 回。

## 5. 呼び出しポイント

### 5.1 `main.py::setup_hook`

Cog 読み込み後に 1 度だけ `adService.loadAds()` を呼ぶ。ホットリロードは
対応しない(必要になったら別途)。

### 5.2 `cogs/music.py::playCommand`

キュー挿入 embed(followup.send)送信の**直後**に
`await adService.maybeShowAd(interaction, interaction.guild.id)` を呼ぶ。

配置理由:
- 既に defer + followup 済みなので channel context が確定している
- WaitingView の投稿(別 channel メッセージ)より前に置くことで、
  ユーザーの視線がまだ /play の結果に向いている間に露出できる
- `if player.fetch("channelId") is None:` ブロックの前(常に通る位置)

## 6. 依存関係

**pydantic を再追加する。**

Phase 1(SPEC.md §D-2)で pydantic は `/code`, `/ranking`, DB 層と共に
削除されたが、本 SPEC の目的(JSON バリデーション)は DB 復活とは無関係。
新しい正当なユースケースとして再導入する。

```toml
dependencies = [
    ...,
    "pydantic>=2.12.5",
]
```

## 7. エラーハンドリング契約

- JSON parse エラー / pydantic ValidationError → WARN ログ + 該当ファイル skip
- ディレクトリ不在 → INFO ログ + 0 件でリターン
- `followup.send` の HTTPException → WARN ログのみ、`/play` の成功は保つ
  (広告送信失敗が音楽再生を止めてはならない)
- `_ADS` が空でも `maybeShowAd` は無害(早期リターン)

## 8. 非目標

- 広告クリック計測(URL に query param 付与など): 本 SPEC では対応しない
- ホットリロード: 再起動が必要
- Guild ごとの ON/OFF 設定: 全 guild 一律
- ephemeral 表示: パブリック LayoutView 固定
- 曲パネル(MusicPanel) 内への埋め込み: MusicPanel 側は変更しない
- 広告表示の DB 保存 / 履歴: 状態はプロセス内メモリのみ

## 9. 契約(既存挙動を壊さないこと)

- `/play` の応答フロー: defer → followup(insertion embed) → WaitingView post
  → player.play() を**維持する**。広告 LayoutView は insertion embed の直後に
  追加送信される(順序: insertion embed → ad view → WaitingView)。
- 広告 0 件 / 閾値未到達時は「新しいメッセージが 1 通も増えない」ことを保つ。
- MusicPanel(WaitingView / 再生パネル)は一切変更しない。
- AdView は `custom_id` を持たない ⇒ `buttonHandler` の網羅性 assertion は不変。
- `_GUILD_COUNTERS` / `_GUILD_THRESHOLDS` のキーは guild_id のみで、
  再起動でリセットされる想定。

## 10. 受け入れ基準

- [ ] `objects/ad.py::Ad` が pydantic BaseModel として定義され、
      `extra="forbid"` が有効。
- [ ] `objects/adPanel.py::AdView` が `discord.ui.LayoutView` のサブクラスで、
      Container / TextDisplay / MediaGallery / (optional) ActionRow / Separator
      を含む。
- [ ] `services/adService.py` の 3 個の Public API が実装済み。
- [ ] `main.py::setup_hook` で `loadAds()` が呼ばれる。
- [ ] `cogs/music.py::playCommand` で `maybeShowAd()` が呼ばれる。
- [ ] `config/ads/example.json` にサンプル広告(enabled=false)がある。
- [ ] `pyproject.toml` に pydantic が追加され、`uv sync` が通る。
- [ ] `ruff check` / `pyright` が 0 error / 0 warning。
- [ ] `buttonHandler._EXPECTED_CUSTOM_IDS` の assertion が生きたまま。
- [ ] 手動: 空の config/ads/ で /play → 広告が送られない。
- [ ] 手動: enabled=true のサンプルを置いて 5 回 /play → 少なくとも 1 回は
      広告 LayoutView が送信される。
- [ ] 手動: linkUrl 有り → LinkButton が表示され、リンクは正しい URL。
- [ ] 手動: linkUrl 無し → LinkButton も title のハイパーリンクも出ない。
- [ ] 手動: malformed JSON を 1 件置いて起動 → WARN ログ + 起動継続。

## 11. ファイル差分(予想)

新規:
- `objects/ad.py`
- `objects/adPanel.py` — AdView(LayoutView)
- `services/adService.py`
- `spec/SPEC_FEATURE_ADS.md`(このファイル)
- `config/ads/example.json`(サンプル)

編集:
- `pyproject.toml`(pydantic 追加)
- `main.py`(setup_hook で `loadAds()` を追加)
- `cogs/music.py`(playCommand の末尾に `maybeShowAd()` 追加、import 追加)

削除: なし
