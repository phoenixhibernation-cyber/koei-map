#!/usr/bin/env python3
"""1都3県の市区町村・都県の境界を data/areas.json に作る（地名を選んだ・検索したときに太い線で囲むため）。
元データ：国土数値情報 行政区域（N03, 2021年）を簡略化した smartnews-smri/japan-topography（s0010）。
使い方：~/Projects/toei-housing-map/.venv/bin/python scripts/build_areas.py <N03_11.json> <N03_12.json> <N03_13.json> <N03_14.json>
"""
import json, sys
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
ISLANDS = {"大島町", "利島村", "新島村", "神津島村", "三宅村", "御蔵島村", "八丈町", "青ヶ島村", "小笠原村"}
TOL = 0.0004   # 約40m で線を間引く


def rnd(o):
    if isinstance(o, (list, tuple)):
        if o and isinstance(o[0], (int, float)):
            return [round(o[0], 4), round(o[1], 4)]
        return [rnd(x) for x in o]
    return o


def geo(g):
    g = g.simplify(TOL, preserve_topology=True)
    m = mapping(g)
    return {"type": m["type"], "coordinates": rnd(m["coordinates"])}


def main(paths):
    cities, prefs = {}, {}
    for p in paths:
        src = json.loads(Path(p).read_text(encoding="utf-8"))
        for f in src["features"]:
            pr = f["properties"]
            pref, gun, name = pr.get("N03_001"), pr.get("N03_003") or "", pr.get("N03_004") or ""
            if not name or name in ISLANDS or name == "所属未定地":
                continue
            full = (gun + name) if gun.endswith("市") else name           # 横浜市鶴見区（地図のデータと同じ書き方）
            alt = [gun + name] if gun.endswith("郡") else []              # 足柄上郡山北町 ↔ 山北町
            g = shape(f["geometry"]).buffer(0)
            key = (pref, full)
            if key in cities:
                cities[key]["g"] = cities[key]["g"].union(g)
            else:
                cities[key] = {"g": g, "alt": alt}
            prefs.setdefault(pref, []).append(g)
            if gun.endswith("市"):                                          # 政令市そのもの（横浜市・さいたま市など）
                k2 = (pref, gun)
                cities.setdefault(k2, {"g": None, "alt": [], "parts": []})
                cities[k2].setdefault("parts", []).append(g)
    feats = []
    for (pref, name), v in cities.items():
        g = v["g"] if v["g"] is not None else unary_union(v["parts"]).buffer(0)
        feats.append({"type": "Feature", "properties": {"pref": pref, "name": name, "alt": v["alt"], "kind": "city"}, "geometry": geo(g)})
    for pref, gs in prefs.items():
        feats.append({"type": "Feature", "properties": {"pref": pref, "name": pref, "alt": [pref.rstrip("都県")], "kind": "pref"}, "geometry": geo(unary_union(gs).buffer(0))})
    out = ROOT / "data" / "areas.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "source": "国土数値情報（行政区域）国土交通省 を加工", "features": feats}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(out, len(feats), "features", out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main(sys.argv[1:])
