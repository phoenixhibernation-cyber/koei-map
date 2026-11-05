#!/usr/bin/env python3
"""都営住宅マップ（toei-housing-map）の data/housing.json を、共通形式 data/listings.json に変換する。
使い方: python3 scripts/import_toei.py [path/to/housing.json]
"""
import json, re, sys, pathlib

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path.home() / "Projects/toei-housing-map/data/housing.json")
OUT = pathlib.Path(__file__).resolve().parent.parent / "data/listings.json"

CAT = {
    "世帯向（一般募集住宅）": "世帯向",
    "若年夫婦・子育て世帯向（定期使用住宅）": "若年夫婦・子育て",
    "居室内で病死等があった住宅": "病死等があった住宅",
}

def num(s):
    try:
        return float(str(s).replace("倍", ""))
    except Exception:
        return None

d = json.loads(SRC.read_text(encoding="utf-8"))
meta, items = d["meta"], d["items"]
m = re.search(r"(\d{4})年(\d{1,2})月", meta.get("round", ""))
round_id = f"toei-{m.group(1)}-{int(m.group(2)):02d}" if m else "toei"
out = []
for r in items:
    out.append({
        "id": f"toei-{r['id']}",
        "operator": "toei",
        "round_id": round_id,
        "category": CAT.get(r["category"], r["category"]),
        "subtype": r.get("subtype") or "",
        "name": r["name"],
        "pref": "東京都",
        "city": r["ward"],
        "address": r["address"],
        "lat": r.get("lat"), "lon": r.get("lon"),
        "access": r.get("access", ""),
        "stations": r.get("stations") or [],
        "walk_min": r.get("walk_min"),
        "bus": bool(r.get("bus")),
        "persons": r.get("persons", ""),
        "single_ok": bool(re.search(r"単身|1〜2人|1人以上", r.get("persons") or "")),
        "units": r.get("units"),
        "vacant_now": r.get("vacant_now"),
        "layout": r.get("layout", ""),
        "layouts": r.get("layouts") or [],
        "area_text": r.get("area_text", ""),
        "area_min": r.get("area_min"), "area_max": r.get("area_max"),
        "rent_min": r.get("rent_min"), "rent_max": r.get("rent_max"),
        "built": r.get("built", ""), "built_from": r.get("built_from"),
        "elevator": (r.get("elevator") == "有"),
        "barrier_free": "バリアフリー" in (r.get("spec") or ""),
        "spec": r.get("spec", ""),
        "floor": r.get("floor", ""),
        "accident": r.get("accident", ""),
        "ratio_prev": num(r.get("ratio_prev")),
        "priority_lottery": bool(r.get("priority_lottery")),
        "official_url": meta.get("source_page"),
        "pdf_url": f"{r['pdf_url']}#page={r['pdf_page_index']}" if r.get("pdf_url") else "",
        "pdf_page": r.get("page", ""),
    })
OUT.write_text(json.dumps({"generated_at": meta.get("generated_at"), "items": out}, ensure_ascii=False), encoding="utf-8")
print(f"{len(out)} 件 → {OUT}")
