#!/usr/bin/env python3
"""全運営元のデータを集めて data/listings.json と data/rounds.json を作る。
使い方:
  python3 scripts/build_all.py                 # 全部
  python3 scripts/build_all.py --only saitama,kawasaki
  python3 scripts/build_all.py --no-geocode    # 住所→緯度経度をしない（読み取りの確認用）
各運営元は run(today) -> (listings, rounds, {"expect_listings": bool, "notes": [...]}) を返す。
- 失敗（例外、または物件を読むはずだったのに0件）した運営元は、前回の物件と募集の予定をそのまま残す
- --only で動かさなかった運営元も前回の値を残す
手入力の募集の予定は data/rounds_manual.json（自動で取れた運営元の分は自動が優先。「expected」付きの手入力は残す）。
結果の要約は data/build_report.md。失敗した運営元があれば終了コード2（Issue を立てて知らせる）。
日付はすべて日本時間。
"""
from __future__ import annotations
import sys, json, argparse, datetime, importlib, pathlib, traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sources import common as C  # noqa: E402

SOURCES = ["toei", "saitama", "kawasaki", "sagamihara", "chibacity"]
OPS_PATH = ROOT / "data" / "operators.json"
MANUAL = ROOT / "data" / "rounds_manual.json"
LISTINGS = ROOT / "data" / "listings.json"
ROUNDS = ROOT / "data" / "rounds.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--no-geocode", action="store_true")
    ap.add_argument("--today", default="")
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.today) if a.today else C.today_jst()
    names = [s for s in a.only.split(",") if s] or SOURCES
    operators = json.loads(OPS_PATH.read_text(encoding="utf-8"))
    manual = json.loads(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else []
    prev_items = json.loads(LISTINGS.read_text(encoding="utf-8"))["items"] if LISTINGS.exists() else []
    prev_rounds = json.loads(ROUNDS.read_text(encoding="utf-8"))["rounds"] if ROUNDS.exists() else []
    prev_count = {}
    for r in prev_items:
        prev_count[r["operator"]] = prev_count.get(r["operator"], 0) + 1

    listings, rounds, report, failed, notes = [], [], [], [], []
    for name in names:
        try:
            mod = importlib.import_module(f"sources.{name}")
            ls, rs, meta = mod.run(today)
            notes += [f"{name}: {n}" for n in meta.get("notes", [])]
            if meta.get("expect_listings") and not ls:
                raise C.SourceError("物件を読むはずだったが0件")
            if prev_count.get(name, 0) >= 20 and ls and len(ls) < prev_count[name] * 0.5:
                notes.append(f"{name}: 件数が前回の半分未満（{prev_count[name]}→{len(ls)}）。念のため確認")
            listings += ls; rounds += rs
            report.append((name, len(ls), len(rs), ""))
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
                    r["lat"], r["lon"], r["geo_level"] = hit["lat"], hit["lon"], hit.get("level", "")
                else:
                    nogeo.append(f'{r["operator"]} {r["name"]}（{r["address"]}）')
        C.save_cache()

    # 前回の値を残す：失敗した運営元と、今回動かさなかった運営元
    keep_ops = set(failed) | (set(SOURCES) - set(names))
    kept_items = [r for r in prev_items if r["operator"] in keep_ops]
    kept_rounds = [r for r in prev_rounds if r["operator"] in keep_ops and not r.get("manual")]
    all_items = listings + kept_items
    auto_rounds = rounds + kept_rounds
    auto_ops = {r["operator"] for r in auto_rounds}
    auto_ids = {r["id"] for r in auto_rounds}
    merged = auto_rounds + [{**r, "manual": True} for r in manual if r["id"] not in auto_ids and (r["operator"] not in auto_ops or r.get("expected"))]

    # 同じ id が2つ以上ないか
    seen, dups = set(), []
    for r in all_items:
        if r["id"] in seen:
            dups.append(r["id"])
        seen.add(r["id"])
    if dups:
        failed.append("duplicate-id")
        notes.append(f"id の重複 {len(dups)} 件: {dups[:5]}")

    def status(r):
        if r.get("anytime"): return 1
        if r.get("apply_from") and r.get("apply_to"):
            if today.isoformat() < r["apply_from"]: return 2
            if today.isoformat() <= r["apply_to"]: return 0
            return 3
        return 2
    merged.sort(key=lambda r: (status(r), r.get("apply_from") or "9", r.get("label", "")))
    used = {x["round_id"] for x in all_items}
    merged = [r for r in merged if status(r) != 3 or r["id"] in used]  # 終わった募集は物件が無ければ外す

    LISTINGS.write_text(json.dumps({"generated_at": today.isoformat(), "items": all_items}, ensure_ascii=False), encoding="utf-8")
    ROUNDS.write_text(json.dumps({"operators": operators, "rounds": merged}, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [f"# 作成レポート（{today.isoformat()}）", "", "| 運営元 | 件数 | 募集の予定 | エラー |", "|---|---|---|---|"]
    lines += [f"| {n} | {l} | {r} | {e} |" for n, l, r, e in report]
    lines += ["", f"合計 {len(all_items)} 件（前回の値を残した運営元: {', '.join(sorted(keep_ops)) or 'なし'}）", ""]
    if notes:
        lines += ["## 注意", ""] + [f"- {x}" for x in notes] + [""]
    lines += [f"## 位置情報に変換できなかった住所（{len(nogeo)}件）" + (f"（通信エラー {C.geocode_errors()} 回）" if C.geocode_errors() else ""), ""]
    lines += [f"- {x}" for x in nogeo] or ["- なし"]
    (ROOT / "data" / "build_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    sys.exit(2 if failed else 0)


if __name__ == "__main__":
    main()
