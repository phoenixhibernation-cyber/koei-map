"""千葉市営住宅（千葉市住宅供給公社）：「募集住宅と抽選結果」ページの、今の回に対応する「募集団地一覧表」PDF を読む。
入口: https://www.cjkk.or.jp/shiei/shiei/result/
募集の予定は公式の予定表（2026年度）を写したもの。2026年度以外は「目安」として出し、通知の対象にしない。
"""
from __future__ import annotations
import re, datetime, urllib.parse
import pdfplumber
from . import common as C

OP = "chibacity"
PREF = "千葉県"
PAGE = "https://www.cjkk.or.jp/shiei/shiei/result/"
SCHED_FY = 2026
SCHED = [  # (名前, 期, 再募集か, 月, 日から, 日まで)
    ("定期募集（第1期）", 1, False, 4, 1, 10), ("再募集（第1期再）", 1, True, 5, 15, 24), ("定期募集（第2期）", 2, False, 7, 1, 10), ("再募集（第2期再）", 2, True, 8, 15, 24),
    ("定期募集（第3期）", 3, False, 10, 1, 10), ("再募集（第3期再）", 3, True, 11, 15, 24), ("定期募集（第4期）", 4, False, 1, 1, 10), ("再募集（第4期再）", 4, True, 2, 15, 24),
]
KEYS = {"use": "住宅用途", "ward": "区", "single": "単身", "name": "団地名", "bldg": "棟", "room": "室番号", "floor": "階", "built": "竣工",
        "layout": "間取り", "area": "専用面積", "rent": "一般階層家賃", "rent2": "裁量階層家賃", "ev": "エレ", "memo": "備考"}


def schedule(today: datetime.date):
    """今日以降の募集を日付順に（今年度と翌年度）。"""
    fy = today.year if today.month >= 4 else today.year - 1
    items = []
    for base in (fy, fy + 1):
        for label, ki, re_, mo, d1, d2 in SCHED:
            y = base if mo >= 4 else base + 1
            a, b = datetime.date(y, mo, d1), datetime.date(y, mo, d2)
            if b >= today:
                items.append((a, b, label, ki, re_, base == SCHED_FY))
    items.sort()
    return items


def pdf_matches(url: str, ki: int, re_: bool, a: datetime.date) -> bool:
    """PDFのファイル名が、その回（第N期・再募集・年度）のものか。"""
    n = C.z2h(urllib.parse.unquote(url))
    fy = a.year if a.month >= 4 else a.year - 1
    if not re.search(rf"第{ki}期|{fy}年度.*{ki}期|R{fy - 2018}-{ki}", n):
        return False
    return ("再" in n) == re_


def run(today: datetime.date):
    listings, rounds, notes = [], [], []
    expect = False
    html = C.read_text(C.fetch(PAGE, subdir=OP, refresh=True))
    pdfs = re.findall(r'href="(https://www\.cjkk\.or\.jp/wp-content/uploads/[^"]+\.pdf)"', html)
    cand = [u for u in pdfs if re.search(r"募集(団地|住宅)一覧", urllib.parse.unquote(u))]
    sched = schedule(today)
    for a, b, label, ki, re_, confirmed in sched[:2]:
        rid = f"{OP}-{a.year}-{a.month:02d}{'r' if re_ else ''}"
        rd = {"id": rid, "operator": OP, "label": f"千葉市営住宅 {a.month}月{label}", "kind": "抽選", "url": PAGE,
              "note": "年4回の定期（1〜10日）と再募集（15〜24日）。公式の予定表より"}
        if confirmed:
            rd.update({"apply_from": a.isoformat(), "apply_to": b.isoformat()})
        else:
            rd["expected"] = f"例年{a.month}月{a.day}日〜{b.day}日（予定表は未発表）"
        rounds.append(rd)
        if confirmed and a <= today <= b:
            match = [u for u in cand if pdf_matches(u, ki, re_, a)]
            if match:
                expect = True
                listings += parse_pdf(match[0], rid)
            else:
                notes.append(f"千葉市営：{label} の一覧表PDFがまだ出ていない（{len(cand)}件のPDFは別の回）")
    rounds.append({"id": f"{OP}-anytime", "operator": OP, "label": "千葉市営住宅 常時募集（先着順）", "kind": "先着順・公社窓口", "anytime": True,
                   "url": PAGE, "note": "定期・再募集で申込がなかった住宅。一覧はPDF"})
    return listings, rounds, {"expect_listings": expect, "notes": notes}


def parse_pdf(url, rid) -> list[dict]:
    path = C.fetch(url, subdir=OP)
    out = []
    with pdfplumber.open(path) as pdf:
        for pi, pg in enumerate(pdf.pages):
            for tb in pg.extract_tables():
                idx = None; cat = ""
                for row in tb:
                    cells = [C.z2h((c or "").replace("\n", "")).strip() for c in row]
                    if cells[0] and "向け住宅" in cells[0]:
                        cat = re.sub(r"^[IVX]+\s*", "", cells[0].split("(")[0]).strip(); continue
                    if "団地名" in "".join(cells) and "室番号" in "".join(cells):
                        idx = C.header_index(cells, KEYS)
                        if not all(k in idx for k in ("name", "room", "layout", "rent")):
                            raise C.SourceError(f"募集団地一覧表の列が足りない: {cells}")
                        continue
                    if not idx:
                        continue
                    g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                    name = g("name")
                    if not name or name == "計" or cells[0] == "計":
                        continue
                    rents = [C.to_int(c) for c in cells[idx["rent"]:idx.get("ev", len(cells))] if C.to_int(c) and C.to_int(c) >= 5000]
                    out.append(C.listing(
                        id=f"{rid}-{pi}-{len(out)}", operator=OP, round_id=rid, category=cat or g("use") or "一般", subtype="定期募集",
                        name=name, pref=PREF, city=f"千葉市{g('ward')}区" if g("ward") else "千葉市", address=f"千葉市{g('ward')}区{name}" if g("ward") else f"千葉市{name}",
                        persons="単身可" if "可" in g("single") else "", single_ok="可" in g("single"), units=1,
                        layout=C.layout_norm(g("layout")), area_text=g("area"), area_min=C.to_float(g("area")), area_max=C.to_float(g("area")),
                        rent_min=min(rents) if rents else None, rent_max=max(rents) if rents else None,
                        built=g("built"), built_from=C.built_year(g("built")), elevator=g("ev").startswith("有"),
                        floor=f"{g('bldg')} {g('room')} {g('floor')}".strip(), spec=g("memo"), official_url=PAGE,
                        pdf_url=f"{url}#page={pi + 1}", pdf_page=str(pi + 1),
                    ))
    if not out:
        raise C.SourceError(f"募集団地一覧表PDFを読んだが0件: {url}")
    return out
