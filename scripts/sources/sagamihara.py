"""相模原市営住宅：市のページから「随時募集」一覧PDFと定期募集の「募集のしおり」PDFを読む。
入口: https://www.city.sagamihara.kanagawa.jp/kurashi/1026489/sumai/1026509/1007952.html
"""
from __future__ import annotations
import re, datetime, urllib.parse
import pdfplumber
from . import common as C

OP = "sagamihara"
PREF = "神奈川県"
PAGE = "https://www.city.sagamihara.kanagawa.jp/kurashi/1026489/sumai/1026509/1007952.html"
KEYS = {"no": "申込住宅番号", "name": "住宅名", "memo": "特記", "layout": "間取り", "persons": "入居人数", "units": "募集戸数", "floor": "建物階",
        "addr": "所在地", "access": "交通", "built": "竣工年度", "equip": "設備", "rent": "家賃額", "ratio": "応募倍率"}


PERIOD = re.compile(r"令和(\d+)年(\d{1,2})月(\d{1,2})日[^0-9]{0,10}(?:から|～|~)\s*(?:令和(\d+)年)?(\d{1,2})月(\d{1,2})日")


def period_after(text: str, word: str, today: datetime.date) -> tuple[str | None, str | None]:
    """『申込期間 令和8年11月2日(月曜日)から11月16日(月曜日)まで』のように、見出し語の直後の期間を読む。
    見出し語が何度も出るときは、直後120字に期間があるものを順に見て、最初に見つかったものを使う。"""
    m = None
    for mm in re.finditer(re.escape(word), text):
        m = PERIOD.search(text[mm.end():mm.end() + 120])
        if m:
            break
    if not m:
        return None, None
    fy = 2018 + int(m.group(1)); fm, fd = int(m.group(2)), int(m.group(3))
    ty = 2018 + int(m.group(4)) if m.group(4) else (fy if (int(m.group(5)), int(m.group(6))) >= (fm, fd) else fy + 1)
    return f"{fy}-{fm:02d}-{fd:02d}", f"{ty}-{int(m.group(5)):02d}-{int(m.group(6)):02d}"


def run(today: datetime.date):
    listings, rounds, notes = [], [], []
    expect = False
    html = C.read_text(C.fetch(PAGE, subdir=OP, refresh=True))
    text = C.z2h(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))
    pdfs = [urllib.parse.urljoin(PAGE, u) for u in re.findall(r'href="([^"]+\.pdf)"', html)]
    # 定期募集：「申込期間」の直後（無ければ「配布期間」）
    a, b = period_after(text, "申込期間", today)
    if not a:
        a, b = period_after(text, "配布期間", today)
        if a:
            notes.append("相模原市営：申込期間が見つからず配布期間で代用")
    if a:
        y, m = int(a[:4]), int(a[5:7])
        rid = f"{OP}-{y}-{m:02d}"
        rounds.append({"id": rid, "operator": OP, "label": f"相模原市営住宅 {m}月定期募集", "kind": "公開抽選・郵送申込",
                       "apply_from": a, "apply_to": b, "url": PAGE, "note": "年2回（5月・11月）"})
        shiori = [u for u in pdfs if "shiori" in u]
        if shiori and b >= today.isoformat():
            expect = True
            listings += parse_shiori(shiori[0], rid)
    # 随時募集（電話・先着順）
    rid2 = f"{OP}-anytime"
    a2, b2 = period_after(text, "電話受付", today)
    if not a2:
        a2, b2 = period_after(text, "随時募集", today)
    rd = {"id": rid2, "operator": OP, "label": "相模原市営住宅 随時募集（先着順）", "kind": "先着順・電話で申込", "anytime": not a2, "url": PAGE,
          "note": "住宅課 042-769-8256（平日8:30〜17:00）"}
    if a2:
        rd.update({"apply_from": a2, "apply_to": b2})
    rounds.append(rd)
    ichiran = [u for u in pdfs if "ichiran" in u]
    if ichiran:
        expect = True
        listings += parse_simple_table(ichiran[0], rid2)
    return listings, rounds, {"expect_listings": expect, "notes": notes}


def parse_simple_table(url, rid) -> list[dict]:
    path = C.fetch(url, subdir=OP, name=url.rsplit("/", 1)[-1])
    out = []
    with pdfplumber.open(path) as pdf:
        for pi, pg in enumerate(pdf.pages):
            cat = ""
            for tb in pg.extract_tables():
                idx = None
                for row in tb:
                    cells = [(c or "").replace("\n", "").strip() for c in row]
                    if cells[0] and "向け" in cells[0] and not cells[1]:
                        cat = re.sub(r"[（(].*", "", cells[0]); continue
                    if "住宅名" in cells:
                        idx = C.header_index(cells, {"name": "住宅名", "layout": "間取り", "units": "募集戸数", "persons": "入居人数", "addr": "所在地", "ev": "エレベーター", "memo": "備考"})
                        continue
                    if idx and cells[idx["name"]]:
                        g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                        addr = C.z2h(g("addr"))
                        ward = re.match(r"^(.*?区)", addr)
                        out.append(C.listing(
                            id=f"{rid}-{pi}-{len(out)}", operator=OP, round_id=rid, category=cat or "一般", subtype="随時募集",
                            name=g("name"), pref=PREF, city="相模原市" + (ward.group(1) if ward else ""), address="相模原市" + addr,
                            persons=g("persons"), units=C.to_int(g("units")) or 1, layout=C.layout_norm(g("layout")),
                            elevator=g("ev").startswith("有"), floor=g("memo"), official_url=PAGE, pdf_url=f"{url}#page={pi + 1}", pdf_page=str(pi + 1),
                        ))
    if not out:
        raise C.SourceError(f"随時募集一覧PDFを読んだが0件: {url}")
    return out


def parse_shiori(url, rid) -> list[dict]:
    """募集のしおりの「募集する住宅一覧」。同じ団地の2行目以降は住宅名・所在地・交通が空欄なので直前の行から引き継ぐ。"""
    path = C.fetch(url, subdir=OP, name=url.rsplit("/", 1)[-1])
    out = []
    with pdfplumber.open(path) as pdf:
        cat = "一般"
        prev = {}
        for pi, pg in enumerate(pdf.pages):
            txt = C.z2h(pg.extract_text() or "")
            m = re.search(r"(一般世帯向け|多人数世帯向け|一般単身者向け|単身者向け|高齢者世帯向け|障害者世帯向け|子育て世帯向け|車いす[^\s]*向け)住宅", txt)
            if m:
                cat = m.group(1)
            for tb in pg.extract_tables():
                idx = None
                for row in tb:
                    cells = [C.z2h((c or "").replace("\n", "")).strip() for c in row]
                    if any("住宅名" in c for c in cells) and any("所在地" in c.replace(" ", "") for c in cells):
                        idx = C.header_index(cells, KEYS)
                        if "equip" in idx:
                            idx["ev"] = idx["equip"] + 1   # 設備の2段目：駐車場・エレベーター・ガス・コンロ・給湯
                        if not all(k in idx for k in ("no", "name", "layout", "addr")):
                            raise C.SourceError(f"しおりの一覧の列が足りない: {cells}")
                        continue
                    if not idx:
                        continue
                    g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                    no = g("no")
                    if not re.match(r"^\d{3,}$", no):
                        continue
                    name = g("name") or prev.get("name", "")
                    addr = re.sub(r"\s+", "", g("addr")) or prev.get("addr", "")
                    access = re.sub(r"\s+", "", g("access")) or prev.get("access", "")
                    prev = {"name": name, "addr": addr, "access": access}
                    if "○○" in name:
                        continue
                    rent_cells = " ".join(cells[idx["rent"]:idx["rent"] + 2]) if "rent" in idx else ""
                    rent_min, rent_max = C.rent_range(rent_cells)
                    ratio = C.to_float(g("ratio").split("(")[0]) if g("ratio") else None
                    ward = re.match(r"^(.*?区)", addr)
                    out.append(C.listing(
                        id=f"{rid}-{no}", operator=OP, round_id=rid, category=cat, subtype="定期募集",
                        name=name, pref=PREF, city="相模原市" + (ward.group(1) if ward else ""), address="相模原市" + addr if addr else "",
                        access=access, persons=g("persons"), units=C.to_int(g("units")) or 1, layout=C.layout_norm(g("layout")),
                        floor=g("floor"), built=g("built"), built_from=C.built_year(g("built")), elevator=g("ev").startswith("有"),
                        rent_min=rent_min, rent_max=rent_max, priority_lottery=("〇" in g("memo") or "○" in g("memo")), ratio_prev=ratio,
                        official_url=PAGE, pdf_url=f"{url}#page={pi + 1}", pdf_page=str(pi + 1),
                    ))
    if not out:
        raise C.SourceError(f"しおりPDFを読んだが0件: {url}")
    return out
