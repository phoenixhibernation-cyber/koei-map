"""千葉市営住宅（千葉市住宅供給公社）：「募集住宅と抽選結果」ページの最新の「募集団地一覧表」PDF を読む。
入口: https://www.cjkk.or.jp/shiei/shiei/result/
"""
from __future__ import annotations
import re, datetime, urllib.parse
import pdfplumber
from . import common as C

OP = "chibacity"
PREF = "千葉県"
PAGE = "https://www.cjkk.or.jp/shiei/shiei/result/"

SCHED = [  # 定期（申込 1〜10日）と再募集（15〜24日）。公式ページの予定表（2026年度）
    ("定期募集（第1期）", 4, 1, 10), ("再募集（第1期再）", 5, 15, 24), ("定期募集（第2期）", 7, 1, 10), ("再募集（第2期再）", 8, 15, 24),
    ("定期募集（第3期）", 10, 1, 10), ("再募集（第3期再）", 11, 15, 24), ("定期募集（第4期）", 1, 1, 10), ("再募集（第4期再）", 2, 15, 24),
]


def run(today: datetime.date) -> tuple[list[dict], list[dict]]:
    listings, rounds = [], []
    html = C.read_text(C.fetch(PAGE, subdir=OP, binary=False, refresh=True))
    # 予定表から、今日以降で一番近い募集を1つ「これから」として出す
    fy = today.year if today.month >= 4 else today.year - 1
    upcoming = []
    for label, mo, d1, d2 in SCHED:
        y = fy if mo >= 4 else fy + 1
        a, b = datetime.date(y, mo, d1), datetime.date(y, mo, d2)
        if b >= today:
            upcoming.append((a, b, label))
    upcoming.sort()
    for a, b, label in upcoming[:2]:
        rid = f"{OP}-{a.year}-{a.month:02d}{'r' if '再' in label else ''}"
        rounds.append({"id": rid, "operator": OP, "label": f"千葉市営住宅 {a.month}月{label}", "kind": "抽選", "apply_from": a.isoformat(),
                       "apply_to": b.isoformat(), "url": PAGE, "note": "年4回の定期（1〜10日）と再募集（15〜24日）。公式の予定表より"})
    rounds.append({"id": f"{OP}-anytime", "operator": OP, "label": "千葉市営住宅 常時募集（先着順）", "kind": "先着順・公社窓口", "anytime": True,
                   "url": PAGE, "note": "定期・再募集で申込がなかった住宅。一覧はPDF"})
    # 募集団地一覧表PDF（募集期間中に掲載）
    pdfs = re.findall(r'href="(https://www\.cjkk\.or\.jp/wp-content/uploads/[^"]+\.pdf)"', html)
    cand = [u for u in pdfs if "募集団地一覧" in urllib.parse.unquote(u) or "募集住宅一覧" in urllib.parse.unquote(u)]
    if cand and upcoming and upcoming[0][0] <= today:
        url = cand[0]
        rid = rounds[0]["id"]
        path = C.fetch(url, subdir=OP, name=re.sub(r"[^\w.]", "_", urllib.parse.unquote(url).rsplit("/", 1)[-1]))
        listings += parse_pdf(path, url, rid)
    return listings, rounds


def parse_pdf(path, url, rid) -> list[dict]:
    out = []
    with pdfplumber.open(path) as pdf:
        for pi, pg in enumerate(pdf.pages):
            for tb in pg.extract_tables():
                idx = None; cat = ""
                for row in tb:
                    cells = [C.z2h((c or "").replace("\n", "")).strip() for c in row]
                    if cells[0] and ("向け住宅" in cells[0]):
                        cat = re.sub(r"^[IVX]+\s*", "", cells[0].split("(")[0]).strip(); continue
                    if "団地名" in "".join(cells) and "室番号" in "".join(cells):
                        idx = {}
                        for i, c in enumerate(cells):
                            cc = c.replace(" ", "")
                            for k, w in [("use", "住宅用途"), ("ward", "区"), ("single", "単身"), ("name", "団地名"), ("bldg", "棟"), ("room", "室番号"),
                                         ("floor", "階"), ("built", "竣工"), ("layout", "間取り"), ("area", "専用面積"), ("rent", "一般階層家賃"),
                                         ("rent2", "裁量階層家賃"), ("ev", "エレ"), ("memo", "備考")]:
                                if k not in idx and (cc == w or cc.startswith(w)):
                                    idx[k] = i
                        continue
                    if not idx or "name" not in idx:
                        continue
                    name = cells[idx["name"]] if idx["name"] < len(cells) else ""
                    if not name or name == "計" or cells[0] == "計":
                        continue
                    g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                    rents = [C.to_int(c) for c in cells[idx.get("rent", 0):idx.get("ev", len(cells))] if C.to_int(c)]
                    out.append(C.listing(
                        id=f"{OP}-{rid}-{pi}-{len(out)}", operator=OP, round_id=rid, category=cat or g("use") or "一般", subtype="定期募集",
                        name=name, pref=PREF, city=f"千葉市{g('ward')}区" if g("ward") else "千葉市", address=f"千葉市{g('ward')}区 {name}" if g("ward") else f"千葉市 {name}",
                        persons="単身可" if "可" in g("single") else "", single_ok="可" in g("single"), units=1,
                        layout=C.layout_norm(g("layout")), area_text=g("area"), area_min=C.to_float(g("area")), area_max=C.to_float(g("area")),
                        rent_min=min(rents) if rents else None, rent_max=max(rents) if rents else None,
                        built=g("built"), built_from=C.built_year(g("built")), elevator=g("ev").startswith("有"),
                        floor=f"{g('bldg')} {g('room')} {g('floor')}".strip(), spec=g("memo"), official_url=PAGE,
                        pdf_url=f"{url}#page={pi + 1}", pdf_page=str(pi + 1),
                    ))
    return out
