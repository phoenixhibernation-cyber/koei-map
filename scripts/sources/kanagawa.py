"""神奈川県営住宅（神奈川県 住宅営繕事務所。募集事務は一般社団法人かながわ土地建物保全協会）。
入口: https://www.pref.kanagawa.jp/docs/h5z/cnt/f6022/index.html （県営住宅について）
  定期募集: https://www.pref.kanagawa.jp/docs/h5z/cnt/f6022/p28450.html （年2回：5月・11月。抽選。郵送申込）
  常時募集: https://www.pref.kanagawa.jp/docs/h5z/cnt/f6022/p28456.html （10月から翌3月末。原則先着順）
どちらも「募集のしおり」が分割PDFで置かれ、その中の「募集住宅一覧」の表（募集地区番号・地区名・募集戸数・間取・建設年度・
概算の家賃額（原則/裁量）・所在地（次の行に最寄りの交通機関）・駐車場・エレベーター・フロ設備・ガス種類〔・前回募集時倍率〕）を読む。
しおりの表の上にある「一般世帯向住宅」「《特別あき家》」などの見出しで区分を決める（見出しが無いページは前の表の区分を引き継ぐ）。
かながわ土地建物保全協会（thk.or.jp）の /notice/ は robots.txt で禁止なので読まない。
"""
from __future__ import annotations
import re, datetime, urllib.parse
import pdfplumber
from . import common as C

OP = "kanagawa"
PREF = "神奈川県"
INDEX = "https://www.pref.kanagawa.jp/docs/h5z/cnt/f6022/index.html"
TEIKI = "https://www.pref.kanagawa.jp/docs/h5z/cnt/f6022/p28450.html"
JOJI = "https://www.pref.kanagawa.jp/docs/h5z/cnt/f6022/p28456.html"
KEYS = {"no": "募集地区", "name": "地区名", "units": "募集戸数", "layout": "間取", "built": "建設年度", "rent": "概算の家賃額", "addr": "所在地", "add": "追加住宅"}
KEYS2 = {"park": "駐車場", "ev": "エレベーター", "bath": "フロ設備", "gas": "ガス種類", "step": "室内段差"}
CATS = ("一般世帯向住宅", "子育て世帯向住宅", "身体障害者向住宅", "高齢単身者向住宅", "一般単身者向住宅", "若年夫婦世帯向住宅")
WAREKI = re.compile(r"令和(\d+)年(\d{1,2})月(\d{1,2})日")


def page_text(url: str) -> tuple[str, list[tuple[str, str]]]:
    """ページ本文の文字列（タグ除去・全角→半角）と、本文中のPDFリンク [(url, リンク文字)]。毎回取り直す。"""
    html = C.read_text(C.fetch(url, subdir=OP, refresh=True))
    m = re.search(r"ここから本文です(.*?)このページに関するお問い合わせ先", html, flags=re.S)
    body = m.group(1) if m else html
    pdfs = [(urllib.parse.urljoin(url, h), re.sub(r"<[^>]+>|\s+", "", lab))
            for h, lab in re.findall(r'href="([^"]+\.pdf)"[^>]*>(.*?)</a>', body, flags=re.S)]
    text = C.z2h(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))
    return text, pdfs


def wareki_period(text: str, word: str) -> tuple[str | None, str | None]:
    """『配布期間 令和8年5月13日（水曜日）から令和8年6月1日（月曜日）まで』のように、見出し語の直後の期間（年付き）を読む。"""
    for mm in re.finditer(re.escape(word), text):
        seg = text[mm.end():mm.end() + 120]
        ds = WAREKI.findall(seg)
        if len(ds) >= 2:
            (a, b, c), (d, e, f) = ds[0], ds[1]
            return f"{2018 + int(a)}-{int(b):02d}-{int(c):02d}", f"{2018 + int(d)}-{int(e):02d}-{int(f):02d}"
    return None, None


def md_period(text: str, word: str, year: int) -> tuple[str | None, str | None]:
    """『申込受付期間は5月15日～6月1日（消印有効）』のように年の無い期間。year は「令和N年M月定期募集」の年。"""
    for mm in re.finditer(re.escape(word), text):
        seg = text[mm.end():mm.end() + 60]
        m = re.search(r"(\d{1,2})月(\d{1,2})日\s*[（(]?[^0-9()（）]{0,4}[)）]?\s*[～~-]\s*(\d{1,2})月(\d{1,2})日", seg)
        if m:
            fm, fd, tm, td = map(int, m.groups())
            ty = year if (tm, td) >= (fm, fd) else year + 1
            return f"{year}-{fm:02d}-{fd:02d}", f"{ty}-{tm:02d}-{td:02d}"
    return None, None


# ---------- しおりの「募集住宅一覧」 ----------
def category_above(page, top: float, prev: dict) -> dict:
    """表の上にある見出しから区分を決める。無ければ前の表の区分を引き継ぐ。"""
    txt = C.z2h(page.crop((0, 0, page.width, max(top, 1))).extract_text() or "")
    cur = dict(prev)
    found = [(m.start(), m.group()) for m in re.finditer("|".join(CATS), txt)]
    if not found:  # 表がページの一番上から始まると上に文字が無い。そのときはページ全体の見出しで判断
        txt = C.z2h(page.extract_text() or "")
        found = [(m.start(), m.group()) for m in re.finditer("|".join(CATS), txt)]
    if found:
        cat = found[-1][1]
        pos = next(p for p, c in found if c == cat)  # 同じ語が注記にも出るので、補足は最初の見出しの後ろで探す
        after = txt[pos + len(cat):pos + len(cat) + 250]  # 補足（特定の資格なし／入居期限付き住宅）は2〜3行下にある。縦書き文字が混ざるので決まった語だけ拾う
        if cat == "身体障害者向住宅":
            wheel = re.findall(r"[（(](車いす[^（）()]{0,6})[)）]", txt)
            cat += f"（{wheel[-1]}）" if wheel else ""
        elif "特定の資格なし" in after:
            cat += "（特定の資格なし）"
        elif "入居期限付き" in after:
            cat += "（入居期限付き住宅）"
        cur["cat"] = cat
    kinds = re.findall(r"《(あき家住宅|特別あき家(?:住宅)?|新築住宅|新築)》", txt)
    if kinds:
        cur["kind"] = "特別あき家" if kinds[-1].startswith("特別") else kinds[-1]
    ku = re.findall(r"(公営住宅|改良住宅)\s*\d+戸", txt)
    if ku:
        cur["ku"] = ku[-1]
    return cur


def split_layout(cell: str) -> tuple[str, str]:
    """'A2・A4\n（3DK・3LK）' → ('3DK・3LK', 'A2・A4')。括弧が無ければ 3DK のような部分を間取りとする。"""
    s = C.z2h(cell).replace(" ", "")
    m = re.search(r"[（(]([^（）()]*)[)）]", s)
    if m:
        return C.layout_norm(m.group(1)), re.sub(r"[（(].*?[)）]|\n", "", s).strip("・･")
    parts = [p for p in s.split("\n") if p]
    lay = [p for p in parts if re.search(r"\d?[LDKSU]{1,4}", p) and not re.match(r"^[A-Z]{1,2}\d*[-－]?\d*$", p)]
    return C.layout_norm("・".join(lay) if lay else s), "・".join(p for p in parts if p not in lay)


def parse_shiori(url: str, rid: str, subtype: str, official_url: str, seen_ids: set) -> list[dict]:
    """しおりPDF1本の中の「募集住宅一覧」の表をすべて読む。一覧の無いPDF（記入例・間取り図など）は0件で返す。"""
    name = "_".join(url.rsplit("/", 2)[-2:])
    path = C.fetch(url, subdir=OP, name=name)
    out, cur = [], {"cat": "", "kind": "", "ku": ""}
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages):
            for table in page.find_tables():
                rows = table.extract()
                if not rows or len(rows[0]) < 10:
                    continue
                hdr = [(c or "").replace("\n", "").replace(" ", "") for c in rows[0]]
                idx = C.header_index(hdr, KEYS)
                if not all(k in idx for k in ("no", "name", "addr", "rent")):
                    continue
                for hrow in rows[1:4]:  # 設備の見出しは2〜3段目（車いす向の表は「車いす向住宅仕様」の列が割り込む）
                    hdr2 = [(c or "").replace("\n", "").replace(" ", "") for c in hrow]
                    found = C.header_index(hdr2, KEYS2)
                    if "park" in found:
                        idx.update(found)
                        break
                cur = category_above(page, table.bbox[1], cur)
                last = None
                for row in rows[1:]:
                    cells = [(c or "").strip() for c in row]
                    g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                    no = C.z2h(g("no")).strip()
                    name_raw = C.z2h(g("name"))
                    if re.match(r"^\d{5}$", no):  # 6桁目が地区名の列にこぼれていることがある（'32125' + '日 野 Z\n1\n〔…〕' / '1相 沢 原 Z'）
                        m6 = re.match(r"^(\d)(?=\D)", name_raw) or re.search(r"\n(\d)(?:\n|$)", name_raw)
                        if m6:
                            no += m6.group(1)
                            name_raw = name_raw[:m6.start(1)] + name_raw[m6.end(1):]
                    if not re.match(r"^\d{6}$", no):
                        if last is not None and g("addr").strip() and not g("name").strip():
                            last["access"] = C.z2h(re.sub(r"\s+", "", g("addr")))  # 所在地の下の行＝最寄りの交通機関
                            fill_access(last)
                        continue
                    memo = re.findall(r"[〔\[（(]([^〔〕\[\]（）()]+)[〕\]）)]", name_raw)
                    nm = re.sub(r"[〔\[（(].*?([〕\]）)]|$)|\s+", "", name_raw)
                    step = C.z2h(g("step")).replace("\n", "")
                    layout, ltype = split_layout(g("layout"))
                    addr = re.sub(r"\s+", "", C.z2h(g("addr")))
                    city = re.match(r"^(.+?市(?:.+?区)?|.+?郡.+?[町村]|.+?[町村])", addr)
                    rent_cells = " ".join(cells[idx["rent"]:idx["rent"] + 2])
                    rent_min, rent_max = C.rent_range(rent_cells)
                    ratio = None
                    if "gas" in idx and idx["gas"] + 1 < len(cells):
                        ratio = C.to_float(cells[idx["gas"] + 1]) if re.match(r"^\d+(\.\d+)?$", C.z2h(cells[idx["gas"] + 1]).strip()) else None
                    added = "追加" in C.z2h(g("add")).replace("\n", "")
                    cat = cur["cat"] or "一般"
                    special = cur["kind"] == "特別あき家"
                    spec = "・".join(x for x in [ltype and f"住戸型式{ltype}", cur["ku"] if cur["ku"] == "改良住宅" else "",
                                               "駐車場あり" if "○" in g("park") else "", _bath(g("bath")), "都市ガス" if g("gas").strip().upper() in ("G", "Ｇ") else ("プロパンガス" if g("gas").strip().upper() == "P" else ""),
                                               *memo, f"室内段差{step}" if step else "", "10月追加住宅（10/1〜10/15受付分は抽選）" if added else ""] if x)
                    pid = f"{rid}-{no}"
                    n = 2
                    while pid in seen_ids:
                        pid = f"{rid}-{no}-{n}"; n += 1
                    seen_ids.add(pid)
                    last = C.listing(
                        id=pid, operator=OP, round_id=rid, category=cat, subtype=subtype + ("・特別あき家" if special else ""),
                        name=nm, pref=PREF, city=city.group(1) if city else "", address=addr,
                        persons="単身" if "単身" in cat else ("2人以上" if "世帯" in cat else ""),
                        units=C.to_int(g("units")) or 1, layout=layout, rent_min=rent_min, rent_max=rent_max,
                        built=C.z2h(g("built")).replace("\n", "").strip(), built_from=C.built_year(g("built")),
                        elevator=("○" in g("ev")) or ("一部" in g("ev").replace("\n", "")), barrier_free=step.startswith("なし"), spec=spec,
                        accident="人身事故等があった住宅（特別あき家）" if special else "", ratio_prev=ratio,
                        official_url=official_url, pdf_url=f"{url}#page={pi + 1}", pdf_page=str(pi + 1),
                    )
                    out.append(last)
    return out


def _bath(cell: str) -> str:
    c = C.z2h(cell).replace("\n", "")
    if "バ" in c:
        return "風呂：バランス釜" + ("（一部）" if "一部" in c else "")
    return "風呂あり" if "○" in c else ""


def fill_access(r: dict):
    """交通機関の文から駅名・徒歩分・バスの有無を埋め直す（C.listing は作成時にしか埋めないため）。"""
    acc = r["access"]
    r["stations"] = C.station_names(acc)
    m = re.search(r"徒歩\s*(\d+)\s*分", acc)
    r["walk_min"] = int(m.group(1)) if m else None
    r["bus"] = "バス" in acc


def read_listings(pdfs: list[tuple[str, str]], rid: str, subtype: str, official_url: str) -> list[dict]:
    """しおりの分割PDFのうち、募集住宅一覧が載っているものを読む。リンク名に「向け」があるものを優先し、無ければ siori を含む全部。"""
    urls = []
    for u, lab in pdfs:
        if "向け" in lab and u not in urls:
            urls.append(u)
    if not urls:
        urls = [u for u, _ in pdfs if "siori" in u.lower() or "shiori" in u.lower()]
        urls = list(dict.fromkeys(urls))
    if not urls:
        raise C.SourceError(f"しおりPDFのリンクが見つからない: {official_url}")
    out, seen = [], set()
    for u in urls:
        out += parse_shiori(u, rid, subtype, official_url, seen)
    if not out:
        raise C.SourceError(f"しおりPDFを読んだが0件: {urls}")
    return out


def run(today: datetime.date):
    listings, rounds, notes = [], [], []
    expect = False
    t = today.isoformat()

    # ---- 定期募集（年2回：5月・11月。抽選）----
    idx_text, _ = page_text(INDEX)
    teiki_text, teiki_pdfs = page_text(TEIKI)
    m = re.search(r"令和(\d+)年(\d{1,2})月定期募集", teiki_text) or re.search(r"令和(\d+)年(\d{1,2})月定期募集", idx_text)
    last_round = None
    if m:
        year, month = 2018 + int(m.group(1)), int(m.group(2))
        a, b = md_period(idx_text, "申込受付期間", year)
        src = "申込受付期間"
        if not a:
            a, b = wareki_period(teiki_text, "配布期間")
            src = "配布期間"
            if a:
                notes.append("神奈川県営 定期募集：申込受付期間が見つからず配布期間で代用")
        rid = f"{OP}-{year}-{month:02d}"
        rd = {"id": rid, "operator": OP, "label": f"神奈川県営住宅 {year}年{month}月定期募集", "kind": "抽選・郵送申込", "url": TEIKI,
              "note": "年2回（5月・11月）。募集のしおりは配布期間中に県政情報センター・市区町役場等で配布"}
        if a:
            rd.update({"apply_from": a, "apply_to": b})
        else:
            rd["expected"] = f"{year}年{month}月（申込期間はページから読めなかった）"
            notes.append("神奈川県営 定期募集：申込期間が読めなかった")
        ended = "募集は終了" in idx_text or "募集は終了" in teiki_text
        rounds.append(rd)
        last_round = (year, month, ended or (b is not None and b < t))
        if a and b >= t and not ended:
            expect = True
            listings += read_listings(teiki_pdfs, rid, "定期募集", TEIKI)
    else:
        notes.append("神奈川県営 定期募集：『令和N年M月定期募集』の見出しが見つからない")
    # 次回の定期募集：公式に「年2回（5月・11月）」とだけある。日付は作らず月だけ示す
    if last_round and last_round[2]:
        y, mo, _ = last_round
        ny, nm = (y, 11) if mo < 11 else (y + 1, 5)
        rounds.append({"id": f"{OP}-{ny}-{nm:02d}", "operator": OP, "label": f"神奈川県営住宅 {ny}年{nm}月定期募集", "kind": "抽選・郵送申込",
                       "expected": f"{ny}年{nm}月（公式：年2回 5月・11月。配布期間等は県のたより{nm}月号で発表）", "url": TEIKI, "note": "公式発表待ち"})

    # ---- 常時募集（10月〜翌3月末。原則先着順）----
    joji_text, joji_pdfs = page_text(JOJI)
    a2, b2 = wareki_period(joji_text, "申込受付期間")
    if not a2:
        a2, b2 = wareki_period(joji_text, "配布期間")
    ym = re.search(r"令和(\d+)年度(\d{1,2})月常時募集", joji_text)
    rid2 = f"{OP}-anytime-{2018 + int(ym.group(1))}-{int(ym.group(2)):02d}" if ym else f"{OP}-anytime"
    rd2 = {"id": rid2, "operator": OP, "label": "神奈川県営住宅 常時募集（先着順）", "kind": "原則先着順・郵送申込（同日消印が募集戸数を超えると抽選）",
           "url": JOJI, "anytime": not a2, "note": "募集戸数は9月1日現在のあき家状況。受付終了の住宅もあるので協会（045-201-3673）で確認"}
    if a2:
        rd2.update({"apply_from": a2, "apply_to": b2})
    else:
        notes.append("神奈川県営 常時募集：申込受付期間が読めなかった")
    rounds.append(rd2)
    if (not a2 or b2 >= t) and joji_pdfs:
        expect = True
        listings += read_listings(joji_pdfs, rid2, "常時募集", JOJI)
    elif not joji_pdfs:
        notes.append("神奈川県営 常時募集：しおりPDFが無い（募集期間外？）")
    return listings, rounds, {"expect_listings": expect, "notes": notes}
