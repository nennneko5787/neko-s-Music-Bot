# SPEC_REFACTOR_PR6.md — フォルダ再編(objects/ 分離 + spec/ 集約)

対象ブランチ: `lavalink` / 作成日: 2026-07-11 / 親仕様: `SPEC.md` / 前段: `SPEC_REFACTOR_PR5.md`

分割計画 PR1〜PR5 完了後の**構造整理**。挙動不変(pure code motion + import 書き換え)。

## 1. 背景

PR1〜PR5 の完了で `objects/` は 14 ファイルに膨らんだ(元 8 ファイル + 追加 6 モジュール)。内実を分類すると:

| 分類 | ファイル | 種別 |
|---|---|---|
| **data-class**(型定義) | bot.py, client.py, exceptions.py, panel.py, player.py, queue.py | framework サブクラス群 |
| **utility** | utils.py, __init__.py | 汎用ヘルパ |
| **behavioral**(振る舞い) | audioFilters.py, buttonHandler.py, messageEditQueue.py, panelUpdater.py, playerCheck.py, queuePagination.py | 関数群 + service クラス |

さらに repo ルートに SPEC ファイルが 6 個(SPEC.md + SPEC_REFACTOR_PR1〜PR5.md)。

**目的**: オーナー方針として「objects/ は型定義のみ」に絞り、振る舞いモジュールは既存の services/ に集約。SPEC ドキュメントは spec/ に集約してルートを整理。

## 2. スコープ

### 2.1 ファイル移設

**6 振る舞いモジュール** を `objects/` → `services/`:

- `objects/audioFilters.py` → `services/audioFilters.py`
- `objects/buttonHandler.py` → `services/buttonHandler.py`
- `objects/messageEditQueue.py` → `services/messageEditQueue.py`
- `objects/panelUpdater.py` → `services/panelUpdater.py`
- `objects/playerCheck.py` → `services/playerCheck.py`
- `objects/queuePagination.py` → `services/queuePagination.py`

**6 SPEC ドキュメント** を repo ルート → `spec/`:
- `SPEC.md` → `spec/SPEC.md`
- `SPEC_REFACTOR_PR1.md` → `spec/SPEC_REFACTOR_PR1.md`
- 同 PR2〜PR5、本 PR6 も。

### 2.2 据え置き(**変更禁止**)

- `objects/utils.py`(**移設しない** — objects/bot.py と objects/panel.py が依存しており、services/ に動かすと objects → services 逆流依存が生じる)
- `objects/{bot,client,exceptions,panel,player,queue}.py` の 6 ファイルは触らない
- `objects/__init__.py`(空 — 変更不要)
- `services/__init__.py`(空 — 変更不要、6 ファイル追加後もそのまま)
- `services/env.py`(既存)
- `main.py`, `cogs/ping.py`, `cogs/help.py`(いずれも `objects.bot / exceptions / client / player` のみを import しており、移設対象 6 モジュールに触っていない)

### 2.3 import 書き換え(全 4 サイト)

**cogs/music.py**(2 箇所): `from objects import ...` の集約 5 モジュールと `from objects.messageEditQueue import ...` を services 経由へ。

**services/buttonHandler.py**(移動後、1 箇所): `from objects import audioFilters, panelUpdater, playerCheck, queuePagination` → `from services import ...`

**services/queuePagination.py**(移動後、1 箇所): `from objects import panelUpdater` → `from services import panelUpdater`

その他の import(`objects.bot`, `objects.client`, `objects.exceptions`, `objects.panel`, `objects.player`, `objects.utils`)は据え置き — 全て objects/ にとどまるファイル群を指すため通る。

## 3. 不変条件

親 SPEC.md §5 の契約に加えて、本 PR 固有:

1. **挙動完全不変**: 移設対象 6 ファイルの中身は 1 バイト変更しない(intra-services import の書き換え 2 箇所を除く)
2. **契約文字列**: custom_id, player.store キー, コマンド名, 日本語 UI 文言 — すべて不変
3. **循環参照ゼロ**: 移設後の依存方向は常に `cogs → services → objects` の一方向(検証ワークフローで確認済み)
4. **buttonHandler の網羅性 assert**: `_HANDLERS.keys() == _EXPECTED_CUSTOM_IDS` が引き続き import 時に成立
5. **既存 PR1-5 SPEC の履歴**: SPEC_REFACTOR_PR1〜PR5.md 内の `objects/audioFilters.py` 等の記述は**歴史的アーティファクトとして原文維持**。書き換えると SPEC の意義(実施当時の状態を凍結する)が失われる。本 PR6 が「その後 services/ に移設した」旨を宣言する形で辻褄を合わせる

## 4. 受け入れ基準

1. `uv run ruff check .` → All checks passed!
2. `uv run pyright` → 0 errors, 0 warnings
3. **smoke test**: 全モジュールが services 側から import できる
4. **buttonHandler 網羅性**: `set(bh._HANDLERS.keys()) == bh._EXPECTED_CUSTOM_IDS`(16 個)
5. **契約 diff**: custom_id, player.store キー, コマンド名の grep 出現回数が変更前と一致
6. **フォルダ状態**:
   - `objects/` 内容: `__init__.py, bot.py, client.py, exceptions.py, panel.py, player.py, queue.py, utils.py` の 8 ファイルのみ
   - `services/` 内容: `__init__.py, env.py, audioFilters.py, buttonHandler.py, messageEditQueue.py, panelUpdater.py, playerCheck.py, queuePagination.py` の 8 ファイル
   - `spec/` 内容: `SPEC.md, SPEC_REFACTOR_PR1.md, ..., SPEC_REFACTOR_PR6.md` の 7 ファイル
   - repo ルートに `SPEC*.md` がゼロ

## 5. 実施手順

### Phase 1: SPEC 執筆(本ファイル)→ 完了

### Phase 2: 6 振る舞いモジュールを移動 → services/ 側の intra-services import を書き換え

### Phase 3: cogs/music.py の 2 箇所を書き換え

### Phase 4: spec/ ディレクトリ新規作成、SPEC 7 ファイルを spec/ に移動

### Phase 5: 検証(ruff, pyright, smoke test, 網羅性 assert, 契約 grep)

## 6. スコープ外

- 追加機能・バックログ対応なし
- utils.py の分割・移設なし
- SPEC 本文の書き換えなし

## 7. ロールバック

```
git checkout HEAD cogs/music.py services/ objects/ spec/
```
