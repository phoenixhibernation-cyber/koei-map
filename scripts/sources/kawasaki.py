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
KEYS = {"room": "部屋番号", "area": "住戸面積", "built": "竣工", "rent": "使用料", "ev": "ｴﾚﾍﾞｰﾀｰ", "gas": "ガス", "memo": "備考"}


def run(today: datetime.date):
    listings, rounds, notes = [], [], []
    html = C.read_text(C.fetch(PAGE, subdir=OP, refresh=True))
    pdfs = [urllib.parse.urljoin(PAGE, u) for u in re.findall(r'href="([^"]+\.pdf)"', html)]
    # 「募集住戸一覧」は日付入りファイル名（例 08_20261102.pdf）。複数あれば日付が新しいもの
    cand = sorted([u for u in pdfs if re.search(r"/\d+_\d{8}\.pdf$", u)], key=lambda u: re.search(r"_(\d{8})\.pdf$", u).group(1), reverse=True)
    rid = f"{OP}-anytime"
    rounds.append({"id": rid, "operator": OP, "label": "川崎市営住宅 常時募集（申込順）", "kind": "先着順・公社窓口で申込", "anytime": True,
                   "url": PAGE, "note": "定期募集で応募がなかった住戸。一覧は毎週火曜に更新"})
    if not cand:
        notes.append("川崎市営：募集住戸一覧PDFのリンクが見つからない")
        return listings, rounds, {"expect_listings": True, "notes": notes}
    url = cand[0]
    path = C.fetch(url, subdir=OP, name=url.rsplit("/", 1)[-1])
    with pdfplumber.open(path) as pdf:
        for pi, pg in enumerate(pdf.pages):
            for tb in pg.extract_tables():
                name = addr = access = ""
                idx = None
                for row in tb:
                    cells = [(c or "").replace("\n", "").strip() for c in row]
                    joined = "".join(cells).replace(" ", "")
                    if "住宅の所在地" in joined:
                        name = cells[0] or name
                        addr = next((c for c in cells[2:] if c and "所在地" not in c.replace(" ", "")), "")
                        continue
                    if "最寄りの交通機関" in joined:
                        access = next((c for c in cells[2:] if c and "交通機関" not in c.replace(" ", "")), "")
                        continue
                    if "部屋番号" in joined:
                        idx = C.header_index(cells, KEYS)
                        if not all(k in idx for k in ("room", "rent")):
                            raise C.SourceError(f"募集住戸一覧の列が足りない: {cells}")
                        continue
                    if idx and cells[idx["room"]] and re.match(r"^[\dA-Za-z]+-\d+", C.z2h(cells[idx["room"]])):
                        g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                        rent_min, rent_max = C.rent_range(g("rent"))
                        room = C.z2h(g("room"))
                        ward = re.match(r"^(.*?区)", C.z2h(addr))
                        area = C.to_float(g("area"))
                        listings.append(C.listing(
                            id=f"{rid}-{name}-{room}", operator=OP, round_id=rid, category="先着順", subtype="常時募集",
                            name=name, pref=PREF, city=("川崎市" + ward.group(1)) if ward else "川崎市", address="川崎市" + addr,
                            access=access, units=1, floor=room, area_text=str(area or ""), area_min=area, area_max=area,
                            rent_min=rent_min, rent_max=rent_max, built=g("built"), built_from=C.built_year(g("built")),
                            elevator=g("ev") in ("○", "〇", "有"), spec=g("memo"), official_url=PAGE,
                            pdf_url=f"{url}#page={pi + 1}", pdf_page=str(pi + 1),
                        ))
    if not listings:
        raise C.SourceError(f"募集住戸一覧PDFを読んだが0件: {url}")
    return listings, rounds, {"expect_listings": True, "notes": notes}
