"""埼玉県営住宅（埼玉県住宅供給公社）：定期募集の一覧表PDFと、随時募集（先着順）の一覧表PDFを読む。
入口: https://www.saijk.or.jp/lookingfor/kenei/apply/ （定期）, https://www.saijk.or.jp/lookingfor/kenei/zuiji/ （随時）
"""
from __future__ import annotations
import re, datetime
import pdfplumber
from . import common as C

OP = "saitama"
PREF = "埼玉県"
APPLY = "https://www.saijk.or.jp/lookingfor/kenei/apply/"
ZUIJI = "https://www.saijk.or.jp/lookingfor/kenei/zuiji/"


def find_pdfs(page_url: str, pattern: str) -> list[str]:
    html = C.read_text(C.fetch(page_url, subdir=OP, binary=False))
    urls = re.findall(r'href="(https://www\.saijk\.or\.jp/wp/wp-content/uploads/[^"]+\.pdf)"', html)
    return [u for u in urls if re.search(pattern, u)]


def jp_date(s: str, base_year: int) -> str | None:
    s = C.z2h(s)
    m = re.search(r"(\d{1,2})月(\d{1,2})日", s)
    if not m:
        return None
    return f"{base_year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"


def parse_table_pdf(path, round_id: str, pdf_url: str, kind: str) -> list[dict]:
    """一覧表PDF（定期・随時とも同じ列構成）を1件ずつに。"""
    out = []
    with pdfplumber.open(path) as pdf:
        for pi, pg in enumerate(pdf.pages):
            for tb in pg.extract_tables():
                head = None
                for row in tb:
                    cells = [(c or "").replace("\n", " ").strip() for c in row]
                    if "住宅名" in cells and "所在地" in cells:
                        head = cells
                        continue
                    if not head or not cells[0] or not re.match(r"^\d+$", C.z2h(cells[0])):
                        continue
                    r = dict(zip(head, cells))
                    # 定期募集の表は家賃が 最低/～/最高 の3列に分かれる
                    rent_txt = r.get("家賃（円）") or r.get("家賃") or ""
                    if not rent_txt:
                        nums = [c for c in cells if re.match(r"^[\d,]+$", c)]
                        rent_txt = " ".join(nums[-2:]) if len(nums) >= 2 else ""
                    rent_min, rent_max = C.rent_range(rent_txt)
                    addr_cell = r.get("所在地", "")
                    taken = "申込済" in addr_cell or "募集戸数に達しました" in " ".join(cells)
                    addr = re.sub(r"※.*?※", "", addr_cell)
                    access = C.station_parts(addr)
                    addr = re.sub(r"[（(].*?[)）]", "", addr).strip()
                    kubun = (r.get("住宅種別") or r.get("入居期間") or "").replace("\n", " ")
                    persons = r.get("世帯 人数") or r.get("世帯人数") or ""
                    units = C.to_int(r.get("募集 戸数") or r.get("募集戸数"))
                    name = re.sub(r"\s*※\d*$", "", r.get("住宅名", ""))
                    city = re.match(r"^(.*?[市郡区町村])", C.z2h(addr))
                    out.append(C.listing(
                        id=f"{OP}-{round_id}-{cells[0]}", operator=OP, round_id=round_id,
                        category=("先着順" if kind == "anytime" else "一般") if not kubun else kubun.split()[0],
                        subtype=kind, name=name, pref=PREF, city=city.group(1) if city else "",
                        address=addr, access=access, persons=persons,
                        units=0 if taken else units, vacant_now=None,
                        layout=C.layout_norm(re.sub(r"募集戸数.*", "", r.get("間取り", ""))),
                        rent_min=rent_min, rent_max=rent_max, built=r.get("建設 年度") or r.get("建設年度", ""),
                        built_from=C.built_year(r.get("建設 年度") or r.get("建設年度", "")),
                        elevator=(r.get("ＥＶ", "") or "").startswith("有"), floor=r.get("募集予定階 数") or r.get("募集予定 階数") or "",
                        spec=("駐車場あり" if (r.get("Ｐ", "") or "").startswith("有") else ""),
                        official_url=ZUIJI if kind == "anytime" else APPLY, pdf_url=f"{pdf_url}#page={pi + 1}", pdf_page=str(pi + 1),
                    ))
    return out


def run(today: datetime.date) -> tuple[list[dict], list[dict]]:
    listings, rounds = [], []
    # 随時募集（先着順）
    zu = find_pdfs(ZUIJI, r"zuiji")
    if zu:
        url = zu[0]
        path = C.fetch(url, subdir=OP)
        with pdfplumber.open(path) as pdf:
            first = pdf.pages[0].extract_text() or ""
        m = re.search(r"受付期間\s*(\d{1,2})月(\d{1,2})日.*?～\s*(\d{1,2})月(\d{1,2})日", C.z2h(first))
        y = today.year
        rid = f"{OP}-anytime"
        apply_from = apply_to = None
        if m:
            fm, fd, tm, td = map(int, m.groups())
            fy = y if fm <= today.month + 1 else y - 1
            ty = fy if tm >= fm else fy + 1
            apply_from, apply_to = f"{fy}-{fm:02d}-{fd:02d}", f"{ty}-{tm:02d}-{td:02d}"
        upd = re.search(r"(\d{1,2})月(\d{1,2})日更新", C.z2h(first))
        rounds.append({"id": rid, "operator": OP, "label": "埼玉県営住宅 随時募集（先着順）", "kind": "先着順・支所窓口で申込",
                       "apply_from": apply_from, "apply_to": apply_to, "anytime": not apply_from, "url": ZUIJI,
                       "note": f"空き住戸を先着順で受付。一覧は{upd.group(1)}月{upd.group(2)}日更新" if upd else "空き住戸を先着順で受付"})
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
        m = re.search(r"WEB申込み\s*(\d{1,2})月(\d{1,2})日.*?～\s*(\d{1,2})月(\d{1,2})日", first.replace("　", " "))
        apply_from = f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else f"{year}-{month:02d}-01"
        apply_to = f"{year}-{int(m.group(3)):02d}-{int(m.group(4)):02d}" if m else f"{year}-{month:02d}-21"
        rounds.append({"id": rid, "operator": OP, "label": f"埼玉県営住宅 {month}月定期募集", "kind": "抽せん方式",
                       "apply_from": apply_from, "apply_to": apply_to, "url": APPLY, "note": "年4回（4・7・10・1月）"})
        if apply_to >= today.isoformat():
            listings += parse_table_pdf(path, rid, url, "regular")
        break
    return listings, rounds
