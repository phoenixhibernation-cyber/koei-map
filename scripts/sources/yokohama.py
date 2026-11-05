"""横浜市営住宅（横浜市住宅供給公社）：定期募集（年2回、4月・10月、抽選）の「募集のしおり」PDF の住宅一覧表と、
常時募集（先着順、2〜6月・8〜12月）の受付期間を読む。
入口: https://www.yokohama-kousya.or.jp/municipal/regular.php （定期）, https://www.yokohama-kousya.or.jp/municipal/about.php （常時）

- 定期募集の申込期間・抽選日は regular.php の本文から。しおり（約19MB、/src/files/ 以下）は申込期間中だけ読む。
  しおりの一覧表は「データ行（地域コード・住宅名・戸数・所在地・EV・駐車場・2部屋/3部屋・使用料・直近の倍率・地図番号）」と
  その直下の「交通行（所在地の列に最寄りの交通機関だけ）」の2行で1件。借上型は「借上期間」列が、車いす用は EV と部屋数の列が無い。
  単身向の章（後半）は世帯向の章の「（単身者可）」の表をそのまま繰り返すので、地域コードで重複を除く。
- 「市営住宅位置図・一覧表」PDF（全市営住宅の 地図番号→建設年度・種類）を地図番号で結合して建設年度を付ける。
- 常時募集の「募集住戸一覧」PDF は robots.txt で禁止の /user_files/ 以下にあるので読まない（受付期間だけ about.php から読む）。
"""
from __future__ import annotations
import re, datetime, urllib.parse
import pdfplumber
from . import common as C

OP = "yokohama"
PREF = "神奈川県"
REGULAR = "https://www.yokohama-kousya.or.jp/municipal/regular.php"
ANYTIME = "https://www.yokohama-kousya.or.jp/municipal/about.php"
KEYS = {"code": "地域コード", "name": "地域名", "units": "募集戸数", "target": "対象住宅名称", "addr": "所在地", "lease": "借上期間",
        "ev": "エレベーター", "park": "駐車場", "r2": "2部屋", "r3": "3部屋", "rent": "使用料", "ratio": "直近の倍率", "mapno": "地図番号"}
PERIOD = re.compile(r"令和(\d+)年(\d{1,2})月(\d{1,2})日[^0-9]{0,10}(?:から|～|~)\s*(?:令和(\d+)年)?(\d{1,2})月(\d{1,2})日")
MARKS = {"※": "入居収入基準が低い住宅", "◎": "室内リフォーム済（ユニットバス・三点給湯）", "●": "1DKの住戸あり"}


def period_after(text: str, word: str) -> tuple[str | None, str | None]:
    """『受付期間 令和8年8月27日（木）から12月28日（月）まで』のように、見出し語の直後の期間を読む。"""
    for mm in re.finditer(re.escape(word), text):
        m = PERIOD.search(text[mm.end():mm.end() + 120])
        if m:
            fy, fm, fd = 2018 + int(m.group(1)), int(m.group(2)), int(m.group(3))
            tm, td = int(m.group(5)), int(m.group(6))
            ty = 2018 + int(m.group(4)) if m.group(4) else (fy if (tm, td) >= (fm, fd) else fy + 1)
            return f"{fy}-{fm:02d}-{fd:02d}", f"{ty}-{tm:02d}-{td:02d}"
    return None, None


def page_text(url: str, name: str) -> tuple[str, str]:
    html = C.read_text(C.fetch(url, subdir=OP, name=name, refresh=True))
    text = C.z2h(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))).replace("&nbsp;", " ")
    return html, text


def pdf_links(html: str, base: str) -> list[tuple[str, str]]:
    """(URL, リンク文字) の一覧。/user_files/ 以下は robots.txt で禁止なので除く。"""
    out = []
    for m in re.finditer(r'href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, flags=re.S | re.I):
        u = urllib.parse.urljoin(base, m.group(1))
        if "/user_files/" in u:
            continue
        out.append((u, C.z2h(re.sub(r"<[^>]+>|\s+|&nbsp;", "", m.group(2)))))
    return out


def load_map_table(url: str) -> dict[str, tuple[str, str]]:
    """位置図PDFの「横浜市営住宅一覧表」：地図番号 → (建設年度, 種類)。横に3組並んだ表。"""
    path = C.fetch(url, subdir=OP, name=url.rsplit("/", 1)[-1])
    out = {}
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            for tb in pg.extract_tables():
                for row in tb:
                    cells = [C.z2h((c or "").replace("\n", "")).strip() for c in row]
                    for i in range(0, len(cells) - 4, 5):
                        no, built, kind = cells[i + 1], cells[i + 3], cells[i + 4]
                        if re.match(r"^\d+$", no) and built:
                            out[no] = (built, kind)
    return out


def parse_shiori(url: str, rid: str, map_table: dict) -> list[dict]:
    path = C.fetch(url, subdir=OP, name=url.rsplit("/", 1)[-1])
    out, seen = [], set()
    with pdfplumber.open(path) as pdf:
        for pi, pg in enumerate(pdf.pages):
            for tb in pg.extract_tables():
                if len(tb) < 3 or len(tb[0]) < 8:
                    continue
                title = C.z2h(tb[0][0] or "")
                hdr = [C.z2h((c or "").replace("\n", "")).strip() for c in tb[1]]
                if "●" in title or "●" in "".join(hdr):   # 「一覧表の見方」の見本の表（●①〜⑧の印つき）
                    continue
                idx = C.header_index(hdr, KEYS)
                if not all(k in idx for k in ("code", "name", "addr", "rent", "mapno")):
                    continue
                cat, area_text, single, persons = classify(title)
                cur, code = None, ""
                for row in tb[2:]:
                    cells = [C.z2h((c or "")).replace("\x07", "").strip() for c in row]
                    g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                    if re.match(r"^\d{4}$", g("code")):
                        code = g("code")
                    is_data = bool(re.match(r"^\d{4}$", g("code"))) or (bool(g("target")) and not g("code"))
                    if is_data:
                        name = (g("target") or g("name")).replace("\n", " ")
                        if g("target"):   # 市内全域（住宅指定なし）：1つの地域コードに住宅が複数ぶら下がる
                            name = f"{g('target')}（市内全域・住宅指定なし）"
                        key = f"{code}-{g('mapno')}" if g("target") else code
                        if key in seen:   # 単身向の章の繰り返し
                            cur = None
                            continue
                        seen.add(key)
                        cur = {"key": key, "name": name, "units": g("units"), "addr": re.sub(r"\s+", "", g("addr")), "access": "",
                               "ev": g("ev"), "park": g("park"), "r2": g("r2"), "r3": g("r3"), "rent": g("rent"), "ratio": g("ratio"),
                               "mapno": g("mapno"), "lease": g("lease"), "page": pi + 1}
                        out.append(build(cur, rid, url, cat, area_text, single, persons, map_table))
                        continue
                    if cur and not g("name") and not g("target") and g("addr"):   # 交通行（使用料・倍率が2行に割れることもある）
                        cur["access"] += re.sub(r"\s+", "", g("addr"))
                        extra = " ".join(x for x in (g("rent"), g("ratio")) if x)
                        if extra:
                            cur["rent"] += " " + g("rent"); cur["ratio"] += " " + g("ratio")
                        out[-1] = build(cur, rid, url, cat, area_text, single, persons, map_table)
    if not out:
        raise C.SourceError(f"しおりPDFを読んだが0件: {url}")
    return out


def classify(title: str) -> tuple[str, str, bool, str]:
    """表の見出し『住宅単位募集（一般世帯向）／原則60㎡以上の2・3部屋の住戸』→ (種別, 広さの文, 単身可, 入居人数)。"""
    lines = [l.strip() for l in title.split("\n") if l.strip()]
    cat = re.sub(r"^住宅単位募集\s*", "", lines[0] if lines else "").replace("【", "・").replace("】", " ").strip("・ ")
    cat = re.sub(r"^[（(](.*)[)）]$", r"\1", cat).replace("(", "（").replace(")", "）")
    cat = re.sub(r"\s+(?=（)", "", cat) or "一般"
    area = next((l for l in lines[1:] if re.search(r"㎡|m2|部屋", l)), "").replace("m2", "㎡")
    single = bool(re.search(r"単身者可|単身者用", title))
    if "高齢二人" in title:
        persons = "高齢二人世帯"
    elif "高齢単身" in title:
        persons = "高齢単身"
    elif "単身者用" in title:
        persons = "単身"
    elif "子育て世帯専用" in title:
        persons = "子育て世帯"
    else:
        persons = "世帯（単身者可）" if single else "世帯"
    return cat, area, single, persons


def build(r: dict, rid: str, url: str, cat: str, area_text: str, single: bool, persons: str, map_table: dict) -> dict:
    name = r["name"]
    marks = [MARKS[k] for k in MARKS if k in name]
    name = re.sub(r"[※◎●]+", "", name).strip()
    spec = list(marks)
    ev = r["ev"]
    if ev in ("△", "□"):
        spec.append("EVは踊り場に停止" if ev == "△" else "EVは一部の階に停止")
    if r["park"] in ("○", "〇"):
        spec.append("駐車場あり")
    if r["lease"]:
        spec.append(f"借上型（借上期間 {r['lease']}まで）")
    elif "借上" in cat:
        spec.append("借上型")
    rooms = [x for x, c in (("2部屋", r["r2"]), ("3部屋", r["r3"])) if c in ("○", "〇")]
    if not rooms:   # 2部屋/3部屋の列が無い表（借上型・4部屋以上・高齢者向など）は見出しの『原則○部屋の住戸』から
        m = re.search(r"(\d)部屋", area_text)
        rooms = [f"{m.group(1)}部屋"] if m else (["4部屋以上"] if "4部屋" in cat else [])
    area_min = C.to_float(m.group(1)) if (m := re.search(r"(\d+)㎡以上", area_text)) else None
    area_max = C.to_float(m.group(1)) if (m := re.search(r"(\d+)㎡未満", area_text)) else None
    rent_min, rent_max = C.rent_range(r["rent"])
    ratio = C.to_float(r["ratio"].split("倍")[0]) if "倍" in r["ratio"] else None
    built, kind = map_table.get(r["mapno"], ("", ""))
    if kind == "改良":
        spec.append("改良住宅")   # 住宅地区改良法に基づく住宅（借上は上で書いている）
    ward = re.match(r"^(.*?区)", r["addr"])
    return C.listing(
        id=f"{rid}-{r['key']}", operator=OP, round_id=rid, category=cat, subtype="定期募集", name=name, pref=PREF,
        city="横浜市" + (ward.group(1) if ward else ""), address=("横浜市" + r["addr"]) if r["addr"] else "", access=r["access"],
        persons=persons, single_ok=single, units=C.to_int(r["units"]), layout="・".join(rooms), area_text=area_text,
        area_min=area_min, area_max=area_max, rent_min=rent_min, rent_max=rent_max, built=built, built_from=C.built_year(built),
        elevator=ev in ("○", "〇"), spec="、".join(spec), ratio_prev=ratio,
        accident="特別空家（住宅内で亡くなり発見が遅れた住宅など）" if "特別空家" in cat else "",
        official_url=REGULAR, pdf_url=f"{url}#page={r['page']}", pdf_page=str(r["page"]),
    )


def run(today: datetime.date):
    listings, rounds, notes = [], [], []
    expect = False
    # ---- 定期募集（抽選）：regular.php の本文から 募集の年月・申込期間・抽選日 ----
    html, text = page_text(REGULAR, "regular.php.html")
    ym = re.search(r"令和(\d+)年(\d{1,2})月(?:の)?(?:市営住宅)?(?:入居者)?募集", text)
    a, b = period_after(text, "受付期間")
    lot = re.search(r"抽選会\s*令和(\d+)年(\d{1,2})月(\d{1,2})日", text)
    lottery = f"{2018 + int(lot.group(1))}-{int(lot.group(2)):02d}-{int(lot.group(3)):02d}" if lot else None
    year, month = (2018 + int(ym.group(1)), int(ym.group(2))) if ym else (None, None)
    if a and not ym:
        year, month = int(a[:4]), int(a[5:7])
    if year:
        rid = f"{OP}-{year}-{month:02d}"
        rd = {"id": rid, "operator": OP, "label": f"横浜市営住宅 {month}月定期募集", "kind": "抽選・郵送またはインターネット申込",
              "url": REGULAR, "note": "年2回（4月・10月）。入居は抽選の約3〜9か月後に順次あっせん"}
        if a:
            rd.update({"apply_from": a, "apply_to": b})
        else:
            rd["expected"] = f"{year}年{month}月（申込期間はページから読めなかった）"
            notes.append("横浜市営 定期募集：申込期間が読めなかった")
        if lottery:
            rd["lottery"] = lottery
        rounds.append(rd)
        if a and b >= today.isoformat():
            links = pdf_links(html, REGULAR)
            shiori = [u for u, t in links if "しおり" in t and "正誤" not in t]
            if not shiori:
                raise C.SourceError("申込期間中なのに『募集のしおり』PDFのリンクが見つからない")
            maps = [u for u, t in links if "一覧表" in t or "位置図" in t]
            map_table = load_map_table(maps[0]) if maps else {}
            if not map_table:
                notes.append("横浜市営：位置図・一覧表PDFが読めず建設年度なし")
            expect = True
            listings += parse_shiori(shiori[0], rid, map_table)
            if any("正誤" in t for _, t in links):
                notes.append("横浜市営 定期募集：しおりに正誤表あり（反映していない）")
        elif a and b < today.isoformat():
            ny, nm = (year + 1, 4) if month >= 10 else (year, 10)
            rounds.append({"id": f"{OP}-{ny}-{nm:02d}", "operator": OP, "label": f"横浜市営住宅 {nm}月定期募集", "kind": "抽選",
                           "expected": f"例年{nm}月（前回の{month}月募集は{int(a[5:7])}/{int(a[8:10])}〜{int(b[5:7])}/{int(b[8:10])}）",
                           "url": REGULAR, "note": "年2回（4月・10月）。公式発表待ち"})
    else:
        notes.append("横浜市営 定期募集：募集の年月がページから読めなかった")
    # ---- 常時募集（先着順）：about.php の受付期間。住戸一覧PDFは /user_files/（robots.txt 禁止）なので読まない ----
    html2, text2 = page_text(ANYTIME, "about.php.html")
    a2, b2 = period_after(text2, "受付期間")
    upd = re.search(r"募集住戸一覧[^【]{0,20}【([^】]+)】", text2)
    note = "定期募集で応募がなかった住宅を先着順で受付（公社窓口のみ）。住戸一覧は公式ページのPDF（毎週水曜更新）で確認"
    if upd:
        note += f"。{upd.group(1)}"
    if "単身向住戸はありません" in text2.replace(" ", ""):
        note += "。現在、単身向住戸なし"
    rd2 = {"id": f"{OP}-anytime", "operator": OP, "label": "横浜市営住宅 常時募集（先着順）", "kind": "先着順・公社窓口で申込",
           "anytime": not a2, "url": ANYTIME, "note": note}
    if a2:
        rd2.update({"apply_from": a2, "apply_to": b2})
    else:
        notes.append("横浜市営 常時募集：受付期間が読めなかった（期間なしで表示）")
    rounds.append(rd2)
    notes.append("横浜市営 常時募集：住戸一覧PDFは robots.txt で禁止の /user_files/ 以下にあるため読んでいない")
    return listings, rounds, {"expect_listings": expect, "notes": notes}
