"""都営住宅（JKK東京）：いまは toei-housing-map の build.py が作った housing.json（data/raw/toei/housing.json）を共通形式に変換する。
（募集ページの自動検知と PDF 読み取りの移植は、次の募集までに行う）
"""
from __future__ import annotations
import re, json, datetime
from . import common as C

OP = "toei"
SRC = C.RAW / "toei" / "housing.json"
INDEX = "https://www.to-kousya.or.jp/kouei/toeibosyu/index_teiki.html"
CAT = {"世帯向（一般募集住宅）": "世帯向", "若年夫婦・子育て世帯向（定期使用住宅）": "若年夫婦・子育て", "居室内で病死等があった住宅": "病死等があった住宅"}


def run(today: datetime.date) -> tuple[list[dict], list[dict]]:
    if not SRC.exists():
        return [], []
    d = json.loads(SRC.read_text(encoding="utf-8"))
    meta, items = d["meta"], d["items"]
    m = re.search(r"(\d{4})年(\d{1,2})月", meta.get("round", ""))
    year, month = (int(m.group(1)), int(m.group(2))) if m else (today.year, today.month)
    rid = f"{OP}-{year}-{month:02d}"
    per = meta.get("application_period") or {}
    total = sum((meta.get("official_totals") or {}).values()) or None
    rounds = [{"id": rid, "operator": OP, "label": f"都営住宅 {year}年{month}月 定期募集", "kind": "抽せん方式（家族向・単身者向等）",
               "apply_from": per.get("start"), "apply_to": per.get("end"), "lottery": meta.get("lottery_date"), "units": total,
               "url": meta.get("source_page"), "note": meta.get("period_note", "")}]
    out = []
    for r in items:
        out.append(C.listing(
            id=f"{OP}-{r['id']}", operator=OP, round_id=rid, category=CAT.get(r["category"], r["category"]), subtype=r.get("subtype") or "",
            name=r["name"], pref="東京都", city=r["ward"], address=r["address"], lat=r.get("lat"), lon=r.get("lon"),
            access=r.get("access", ""), stations=r.get("stations") or [], walk_min=r.get("walk_min"), bus=bool(r.get("bus")),
            persons=r.get("persons", ""), units=r.get("units"), vacant_now=r.get("vacant_now"), layout=r.get("layout", ""),
            layouts=r.get("layouts") or [], area_text=r.get("area_text", ""), area_min=r.get("area_min"), area_max=r.get("area_max"),
            rent_min=r.get("rent_min"), rent_max=r.get("rent_max"), built=r.get("built", ""), built_from=r.get("built_from"),
            elevator=(r.get("elevator") == "有"), barrier_free="バリアフリー" in (r.get("spec") or ""), spec=r.get("spec", ""),
            floor=r.get("floor", ""), accident=r.get("accident", ""), ratio_prev=C.to_float(r.get("ratio_prev")),
            priority_lottery=bool(r.get("priority_lottery")), official_url=meta.get("source_page"),
            pdf_url=f"{r['pdf_url']}#page={r['pdf_page_index']}" if r.get("pdf_url") else "", pdf_page=r.get("page", ""),
        ))
    return out, rounds
