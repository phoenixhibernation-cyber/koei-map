#!/usr/bin/env python3
"""全運営元のデータを集めて data/listings.json と data/rounds.json を作る。
使い方:
  python3 scripts/build_all.py                 # 全部
  python3 scripts/build_all.py --only saitama,kawasaki
  python3 scripts/build_all.py --no-geocode    # 住所→緯度経度をしない（読み取りの確認用）
手で管理する募集の予定は data/rounds_manual.json（自動で取れた運営元の分は自動が優先）。
結果の要約は data/build_report.md。読み取りが0件になった運営元があれば終了コード2（公開を止める）。
"""
from __future__ import annotations
import sys, json, argparse, datetime, importlib, pathlib, traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sources import common as C  # noqa: E402

SOURCES = ["toei", "saitama", "kawasaki", "sagamihara", "chibacity"]
OPS_PATH = ROOT / "data" / "operators.json"
MANUAL = ROOT / "data" / "rounds_manual.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--no-geocode", action="store_true")
    ap.add_argument("--today", default="")
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    names = [s for s in a.only.split(",") if s] or SOURCES
    operators = json.loads(OPS_PATH.read_text(encoding="utf-8"))
    manual = json.loads(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else []

    listings, rounds, report, failed = [], [], [], []
    for name in names:
        try:
            mod = importlib.import_module(f"sources.{name}")
            ls, rs = mod.run(today)
            listings += ls; rounds += rs
            report.append((name, len(ls), len(rs), ""))
            if not ls and not rs:
                failed.append(name)
        except Exception as e:
            traceback.print_exc()
            report.append((name, 0, 0, f"{type(e).__name__}: {e}"))
            failed.append(name)

    # 住所 → 緯度経度
    nogeo = []
    if not a.no_geocode:
        for r in listings:
            if r.get("lat") is None and r.get("address"):
                hit = C.geocode(r["address"], r.get("pref", ""))
                if hit:
                    r["lat"], r["lon"] = hit["lat"], hit["lon"]
                    r["geo_level"] = hit.get("level", "")
                else:
                    nogeo.append(f'{r["operator"]} {r["name"]}（{r["address"]}）')
        C.save_cache()

    # 募集の予定：自動で取れた運営元は自動を優先、それ以外は手入力
    auto_ops = {r["operator"] for r in rounds}
    auto_ids = {r["id"] for r in rounds}
    merged = rounds + [r for r in manual if r["id"] not in auto_ids and (r["operator"] not in auto_ops or r.get("expected"))]
    # 表示順：募集中 → いつでも → これから
    def status(r):
        if r.get("anytime"): return 1
        if r.get("apply_from") and r.get("apply_to"):
            if today.isoformat() < r["apply_from"]: return 2
            if today.isoformat() <= r["apply_to"]: return 0
            return 3
        return 2
    merged.sort(key=lambda r: (status(r), r.get("apply_from") or "9", r["label"]))

    # 既存の listings.json を読んで、今回失敗した運営元の分は前回の値を残す（空で上書きしない）
    out_path = ROOT / "data" / "listings.json"
    prev = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {"items": []}
    kept = [r for r in prev["items"] if r["operator"] in failed or r["operator"] not in names]
    all_items = listings + kept
    out_path.write_text(json.dumps({"generated_at": today.isoformat(), "items": all_items}, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data" / "rounds.json").write_text(json.dumps({"operators": operators, "rounds": merged}, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [f"# 作成レポート（{today.isoformat()}）", "", "| 運営元 | 件数 | 募集の予定 | エラー |", "|---|---|---|---|"]
    lines += [f"| {n} | {l} | {r} | {e} |" for n, l, r, e in report]
    lines += ["", f"合計 {len(all_items)} 件（前回の値を残した運営元: {', '.join(failed) or 'なし'}）", "", f"## 位置情報に変換できなかった住所（{len(nogeo)}件）", ""]
    lines += [f"- {x}" for x in nogeo] or ["- なし"]
    (ROOT / "data" / "build_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    sys.exit(2 if failed else 0)


if __name__ == "__main__":
    main()
