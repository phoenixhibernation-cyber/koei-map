"""埼玉県営住宅（埼玉県住宅供給公社）：定期募集の一覧表PDFと、随時募集（先着順）の一覧表PDFを読む。
入口: https://www.saijk.or.jp/lookingfor/kenei/apply/ （定期）, https://www.saijk.or.jp/lookingfor/kenei/zuiji/ （随時）
PDF には「※申込済※」「募集戸数に達しました」のハンコ（黄色・大きい文字）が本文に重なっているので、色で除いてから表を読む。
"""
from __future__ import annotations
import re, datetime
import pdfplumber
from . import common as C

OP = "saitama"
PREF = "埼玉県"
APPLY = "https://www.saijk.or.jp/lookingfor/kenei/apply/"
ZUIJI = "https://www.saijk.or.jp/lookingfor/kenei/zuiji/"
KEYS = {"no": "NO", "name": "住宅名", "built": "建設", "floors": "建物", "addr": "所在地", "layout": "間取り", "units": "募集戸数",
        "floor": "募集予定", "kind": "住宅種別", "persons": "世帯", "term": "入居", "rent": "家賃", "ev": "ＥＶ", "gas": "ガス", "park": "Ｐ"}
STAMP_COLOR = (1.0, 1.0, 0.0)


def find_pdfs(page_url: str, pattern: str) -> list[str]:
    html = C.read_text(C.fetch(page_url, subdir=OP, refresh=True))
    urls = re.findall(r'href="(https://www\.saijk\.or\.jp/wp/wp-content/uploads/[^"]+\.pdf)"', html)
    return [u for u in urls if re.search(pattern, u)]


def is_stamp(obj) -> bool:
    return obj.get("object_type") == "char" and tuple(obj.get("non_stroking_color") or ()) == STAMP_COLOR


def parse_table_pdf(path, round_id: str, pdf_url: str, kind: str) -> list[dict]:
    """一覧表PDF（定期・随時とも同じ列構成）を1件ずつに。ハンコ文字は除き、ハンコが重なっていた行は「申込済」にする。"""
    out = []
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages):
            stamps = [c for c in page.chars if is_stamp(c)]
            pg = page.filter(lambda o: not is_stamp(o))
            tables = pg.find_tables()
            for table in tables:
                idx = None
                for row_i, row in enumerate(table.rows):
                    cells = [(c or "").replace("\n", " ").strip() for c in table.extract()[row_i]]
                    if any("住宅名" in c for c in cells) and any("所在地" in c for c in cells):
                        idx = C.header_index(cells, KEYS)
                        if not all(k in idx for k in ("name", "addr", "layout", "rent")):
                            raise C.SourceError(f"一覧表の列が足りない: {cells}")
                        continue
                    if not idx:
                        continue
                    g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                    if not re.match(r"^\d+$", C.z2h(g("no"))):
                        continue
                    top, bottom = row.bbox[1], row.bbox[3]
                    taken = any(top <= s["top"] <= bottom or top <= s["bottom"] <= bottom for s in stamps)
                    addr_cell = C.z2h(g("addr"))
                    access = C.station_parts(addr_cell)
                    addr = re.sub(r"[（(].*?[)）]", "", addr_cell).strip()
                    rent_cell = g("rent")
                    if kind == "regular" and "rent" in idx:  # 定期の表は 最低/～/最高 の3列
                        rent_cell = " ".join(cells[idx["rent"]:idx["rent"] + 3])
                    rent_min, rent_max = C.rent_range(rent_cell)
                    city = re.match(r"^(.*?[市郡区町村])", addr)
                    out.append(C.listing(
                        id=f"{round_id}-{g('no')}", operator=OP, round_id=round_id,
                        category=(g("kind").split()[0] if g("kind") else ("先着順" if kind == "anytime" else "一般")),
                        subtype="随時募集" if kind == "anytime" else "定期募集", name=re.sub(r"\s*※\d*$", "", g("name")), pref=PREF,
                        city=city.group(1) if city else "", address=addr, access=access, persons=g("persons"),
                        units=0 if taken else C.to_int(g("units")), layout=C.layout_norm(g("layout")),
                        rent_min=rent_min, rent_max=rent_max, built=g("built"), built_from=C.built_year(g("built")),
                        elevator=g("ev").startswith("有"), floor=g("floor"), spec=("駐車場あり" if g("park").startswith("有") else "") + ("　申込済" if taken else ""),
                        official_url=ZUIJI if kind == "anytime" else APPLY, pdf_url=f"{pdf_url}#page={pi + 1}", pdf_page=str(pi + 1),
                    ))
    if not out:
        raise C.SourceError(f"一覧表PDFを読んだが0件: {pdf_url}")
    return out


def period_from_text(text: str, today: datetime.date) -> tuple[str | None, str | None]:
    """『受付期間 10月1日（木）～12月28日（月）』のような文から期間を。年は今日に近い年を選ぶ。"""
    t = C.z2h(text).replace("　", " ")
    m = re.search(r"(\d{1,2})月(\d{1,2})日\s*[（(]?[^0-9()（）]{0,3}[)）]?\s*(?:午前|午後)?[\d:：]*\s*[～~-]\s*(\d{1,2})月(\d{1,2})日", t)
    if not m:
        return None, None
    fm, fd, tm, td = map(int, m.groups())
    fy = C.pick_year(fm, fd, today)
    ty = fy if (tm, td) >= (fm, fd) else fy + 1
    return f"{fy}-{fm:02d}-{fd:02d}", f"{ty}-{tm:02d}-{td:02d}"


def run(today: datetime.date):
    listings, rounds, notes = [], [], []
    expect = False
    # 随時募集（先着順）
    zu = find_pdfs(ZUIJI, r"zuiji")
    if zu:
        url = zu[0]
        path = C.fetch(url, subdir=OP)
        with pdfplumber.open(path) as pdf:
            first = pdf.pages[0].extract_text() or ""
        seg = re.search(r"受付期間(.{0,60})", C.z2h(first).replace("\n", " "))
        apply_from, apply_to = period_from_text(seg.group(1), today) if seg else (None, None)
        if not apply_from:
            notes.append("埼玉県営 随時募集：受付期間が読めなかった（期間なしで表示）")
        upd = re.search(r"(\d{1,2})月(\d{1,2})日更新", C.z2h(first))
        rid = f"{OP}-anytime"
        rounds.append({"id": rid, "operator": OP, "label": "埼玉県営住宅 随時募集（先着順）", "kind": "先着順・支所窓口で申込",
                       "apply_from": apply_from, "apply_to": apply_to, "anytime": not apply_from, "url": ZUIJI,
                       "note": f"空き住戸を先着順で受付。一覧は{upd.group(1)}月{upd.group(2)}日更新" if upd else "空き住戸を先着順で受付"})
        expect = True
        listings += parse_table_pdf(path, rid, url, "anytime")
    # 定期募集（抽せん）：一覧表PDFが出ているときだけ
    for url in find_pdfs(APPLY, r"ichiranhyou"):
        path = C.fetch(url, subdir=OP)
        with pdfplumber.open(path) as pdf:
            first = C.z2h(pdf.pages[0].extract_text() or "")
        ym = re.search(r"令和(\d+)年(\d{1,2})月版", first)
        if not ym:
            continue
        year, month = 2018 + int(ym.group(1)), int(ym.group(2))
        rid = f"{OP}-{year}-{month:02d}"
        seg = re.search(r"WEB申込み(.{0,80})", first.replace("\n", " "))
        apply_from, apply_to = period_from_text(seg.group(1), today) if seg else (None, None)
        rd = {"id": rid, "operator": OP, "label": f"埼玉県営住宅 {month}月定期募集", "kind": "抽せん方式", "url": APPLY, "note": "年4回（4・7・10・1月）"}
        if apply_from:
            rd.update({"apply_from": apply_from, "apply_to": apply_to})
        else:
            rd["expected"] = f"{year}年{month}月（申込期間はPDFから読めなかった）"
            notes.append("埼玉県営 定期募集：申込期間が読めなかった")
        rounds.append(rd)
        if apply_from and apply_to >= today.isoformat():
            expect = True
            listings += parse_table_pdf(path, rid, url, "regular")
        break
    return listings, rounds, {"expect_listings": expect, "notes": notes}
