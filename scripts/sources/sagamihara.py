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
HOST = "https://www.city.sagamihara.kanagawa.jp"


def wareki(s: str) -> tuple[int, int, int] | None:
    m = re.search(r"令和(\d+)年(\d{1,2})月(\d{1,2})日", C.z2h(s))
    return (2018 + int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def run(today: datetime.date) -> tuple[list[dict], list[dict]]:
    listings, rounds = [], []
    html = C.read_text(C.fetch(PAGE, subdir=OP, binary=False, refresh=True))
    text = re.sub(r"<[^>]+>", " ", html)
    text = C.z2h(re.sub(r"\s+", " ", text))
    # 定期募集の期間（「令和8年11月2日（月曜日）から11月16日（月曜日）」）
    m = re.search(r"令和(\d+)年(\d{1,2})月(\d{1,2})日[^0-9]{0,8}から\s*(\d{1,2})月(\d{1,2})日", text)
    if m:
        y = 2018 + int(m.group(1)); fm, fd, tm, td = map(int, m.group(2, 3, 4, 5))
        rid = f"{OP}-{y}-{fm:02d}"
        rounds.append({"id": rid, "operator": OP, "label": f"相模原市営住宅 {fm}月定期募集", "kind": "公開抽選・郵送申込",
                       "apply_from": f"{y}-{fm:02d}-{fd:02d}", "apply_to": f"{y}-{tm:02d}-{td:02d}", "url": PAGE, "note": "年2回（5月・11月）"})
        shiori = [urllib.parse.urljoin(PAGE, u) for u in re.findall(r'href="([^"]*shiori[^"]*\.pdf)"', html)]
        if shiori and f"{y}-{tm:02d}-{td:02d}" >= today.isoformat():
            listings += parse_shiori(shiori[0], rid)
    # 随時募集（電話・先着順）
    m2 = re.search(r"令和(\d+)年(\d{1,2})月(\d{1,2})日[^0-9]{0,8}[～〜から]\s*令和(\d+)年(\d{1,2})月(\d{1,2})日", text)
    rid2 = f"{OP}-anytime"
    rd = {"id": rid2, "operator": OP, "label": "相模原市営住宅 随時募集（先着順）", "kind": "先着順・電話で申込", "anytime": True, "url": PAGE,
          "note": "住宅課 042-769-8256（平日8:30〜17:00）"}
    if m2:
        rd.update({"anytime": False, "apply_from": f"{2018 + int(m2.group(1))}-{int(m2.group(2)):02d}-{int(m2.group(3)):02d}",
                   "apply_to": f"{2018 + int(m2.group(4))}-{int(m2.group(5)):02d}-{int(m2.group(6)):02d}"})
    rounds.append(rd)
    ichiran = [urllib.parse.urljoin(PAGE, u) for u in re.findall(r'href="([^"]*ichiran[^"]*\.pdf)"', html)]
    if ichiran:
        url = ichiran[0]
        path = C.fetch(url, subdir=OP, name=url.rsplit("/", 1)[-1])
        listings += parse_simple_table(path, url, rid2)
    return listings, rounds


def parse_simple_table(path, url, rid) -> list[dict]:
    out = []
    with pdfplumber.open(path) as pdf:
        for pi, pg in enumerate(pdf.pages):
            cat = ""
            for tb in pg.extract_tables():
                head = None
                for row in tb:
                    cells = [(c or "").replace("\n", "").strip() for c in row]
                    if cells[0] and "向け" in cells[0] and not cells[1]:
                        cat = re.sub(r"[（(].*", "", cells[0]); continue
                    if "住宅名" in cells:
                        head = cells; continue
                    if head and cells[0]:
                        r = dict(zip(head, cells))
                        addr = C.z2h(r.get("所在地", ""))
                        out.append(C.listing(
                            id=f"{OP}-{rid}-{pi}-{len(out)}", operator=OP, round_id=rid, category=cat or "一般", subtype="随時募集",
                            name=r.get("住宅名", ""), pref=PREF, city="相模原市" + (re.match(r"^(.*?区)", addr).group(1) if re.match(r"^(.*?区)", addr) else ""),
                            address="相模原市" + addr, persons=r.get("入居人数", ""), units=C.to_int(r.get("募集戸数")) or 1,
                            layout=C.layout_norm(r.get("間取り", "")), elevator=(r.get("エレベーター", "") or "").startswith("有"),
                            floor=r.get("備考", ""), official_url=PAGE, pdf_url=f"{url}#page={pi + 1}", pdf_page=str(pi + 1),
                        ))
    return out


def parse_shiori(url, rid) -> list[dict]:
    """募集のしおりの「募集住宅」一覧。表の形は回ごとに確かめる（列が合わないときは空を返す）。"""
    path = C.fetch(url, subdir=OP, name=url.rsplit("/", 1)[-1])
    out = []
    KEYS = {"name": "住宅名", "memo": "特記", "layout": "間取り", "persons": "入居人数", "units": "募集戸数", "floor": "建物階", "addr": "所在地",
            "access": "交通", "built": "竣工年度", "ratio": "応募倍率"}
    with pdfplumber.open(path) as pdf:
        cat = "一般"
        for pi, pg in enumerate(pdf.pages):
            txt = C.z2h(pg.extract_text() or "")
            m = re.search(r"(一般世帯向け|多人数世帯向け|単身者向け|高齢者世帯向け|障害者世帯向け|子育て世帯向け|車いす[^\s]*向け)住宅", txt)
            if m:
                cat = m.group(1)
            for tb in pg.extract_tables():
                idx = None
                for row in tb:
                    cells = [C.z2h((c or "").replace("\n", "")).strip() for c in row]
                    if any("住宅名" in c for c in cells) and any("所在地" in c.replace(" ", "") for c in cells):
                        idx = {}
                        for k, word in KEYS.items():
                            for i, c in enumerate(cells):
                                if word in c.replace(" ", ""):
                                    idx[k] = i; break
                        # エレベーター列は2段目の見出しにある：設備の先頭列＋1
                        for i, c in enumerate(cells):
                            if "設備" in c.replace(" ", ""):
                                idx["ev"] = i + 1
                        continue
                    if not idx or "name" not in idx:
                        continue
                    name = cells[idx["name"]] if idx["name"] < len(cells) else ""
                    if not name or "○○" in name or "＊" in cells[0] or name.startswith("申込"):
                        continue
                    g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                    addr = re.sub(r"\s+", "", g("addr"))
                    ratio = C.to_float(g("ratio").split("(")[0]) if g("ratio") else None
                    out.append(C.listing(
                        id=f"{OP}-{rid}-{cells[0] or f'{pi}-{len(out)}'}", operator=OP, round_id=rid, category=cat, subtype="定期募集",
                        name=name, pref=PREF, city="相模原市" + (re.match(r"^(.*?区)", addr).group(1) if re.match(r"^(.*?区)", addr) else ""),
                        address="相模原市" + addr if addr else "", access=re.sub(r"\s+", "", g("access")), persons=g("persons"),
                        units=C.to_int(g("units")) or 1, layout=C.layout_norm(g("layout")), floor=g("floor"),
                        built=g("built"), built_from=C.built_year(g("built")), elevator=g("ev").startswith("有"),
                        priority_lottery=("〇" in g("memo") or "○" in g("memo")), ratio_prev=ratio,
                        spec="", official_url=PAGE, pdf_url=f"{url}#page={pi + 1}", pdf_page=str(pi + 1),
                    ))
    return out
