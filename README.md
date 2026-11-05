# 住まいのSmiley（仮名）試作版

安く住める家の募集（都営・県営・市営・公社・UR）を、地図とカレンダーでまとめて探せるWebアプリ。
設計の文書は `docs/`（Obsidian の `07_Projects/都営住宅マップ（サービス化）/`）。進み具合は `.solo/progress.md`。

## 手元で開く
```bash
cd ~/Projects/koei-map
python3 -m http.server 8777 --bind 127.0.0.1
# ブラウザで http://127.0.0.1:8777/
```

## データを作り直す
- 都営：`python3 scripts/import_toei.py`（`~/Projects/toei-housing-map/data/housing.json` を共通形式 `data/listings.json` に変換）
- 募集の予定：`data/rounds.json` を手で直す（工程06で自動取得にする）

## 確かめる
```bash
~/Projects/toei-housing-map/.venv/bin/python tests/e2e.py   # スマホ幅で主な流れを通す。tests/screenshots/ に画像
```
