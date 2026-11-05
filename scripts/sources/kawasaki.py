"""川崎市営住宅：常時募集（申込順）の「募集住戸一覧」PDF を読む。
入口（公社サイトのメンテ中は川崎市サイトに臨時掲載）: https://www.city.kawasaki.jp/500/page/0000191069.html
"""
from __future__ import annotations
import re, datetime, urllib.parse
import pdfplumber
from . import common as C

OP = "kawasaki"
PREF = "神奈川県"
PAGE = "https://www.city.kawasaki.jp/500/page/0000191069.html"
TEIKI = "https://www.city.kawasaki.jp/500/page/0000191068.html"


def run(today: datetime.date) -> tuple[list[dict], list[dict]]:
    listings, rounds = [], []
    html = C.read_text(C.fetch(PAGE, subdir=OP, binary=False, refresh=True))
    pdfs = [urllib.parse.urljoin(PAGE, u) for u in re.findall(r'href="([^"]+\.pdf)"', html)]
    # 「募集住戸一覧」は日付入りファイル名（例 08_20261102.pdf）
    cand = [u for u in pdfs if re.search(r"/\d+_\d{8}\.pdf$", u)]
    rid = f"{OP}-anytime"
    rounds.append({"id": rid, "operator": OP, "label": "川崎市営住宅 常時募集（申込順）", "kind": "先着順・公社窓口で申込", "anytime": True,
                   "url": PAGE, "note": "定期募集で応募がなかった住戸。一覧は毎週火曜に更新"})
    if not cand:
        return listings, rounds
    url = cand[0]
    path = C.fetch(url, subdir=OP, name=url.rsplit("/", 1)[-1])
    with pdfplumber.open(path) as pdf:
        n = 0
        for pi, pg in enumerate(pdf.pages):
            for tb in pg.extract_tables():
                name = addr = access = ""
                head = None
                for row in tb:
                    cells = [(c or "").replace("\n", "").strip() for c in row]
                    joined = "".join(cells)
                    if "住宅の所在地" in joined.replace(" ", ""):
                        name = cells[0] or name
                        addr = next((c for c in cells[2:] if c and "所在地" not in c.replace(" ", "")), "")
                        continue
                    if "最寄りの交通機関" in joined.replace(" ", ""):
                        access = next((c for c in cells[2:] if c and "交通機関" not in c.replace(" ", "")), "")
                        continue
                    if "棟-部屋番号" in joined or "部屋番号" in joined:
                        head = cells
                        continue
                    if head and cells[0] and re.match(r"^[\dA-Za-z]+-\d+", C.z2h(cells[0])):
                        r = dict(zip(head, cells))
                        rent_min, rent_max = C.rent_range(r.get("予定使用料", ""))
                        n += 1
                        city = re.match(r"^(.*?区)", C.z2h(addr))
                        listings.append(C.listing(
                            id=f"{OP}-anytime-{n}", operator=OP, round_id=rid, category="先着順", subtype="常時募集",
                            name=name, pref=PREF, city=("川崎市" + city.group(1)) if city else "川崎市", address="川崎市" + addr,
                            access=access, units=1, floor=cells[0], area_text=str(C.to_float(r.get("住戸面積")) or ""),
                            area_min=C.to_float(r.get("住戸面積")), area_max=C.to_float(r.get("住戸面積")),
                            rent_min=rent_min, rent_max=rent_max, built=r.get("竣工年度", ""), built_from=C.built_year(r.get("竣工年度", "")),
                            elevator=(r.get("ｴﾚﾍﾞｰﾀｰ") or r.get("エレベーター") or "") in ("○", "〇", "有"),
                            spec=r.get("備考", ""), official_url=PAGE, pdf_url=f"{url}#page={pi + 1}", pdf_page=str(pi + 1),
                        ))
    return listings, rounds
