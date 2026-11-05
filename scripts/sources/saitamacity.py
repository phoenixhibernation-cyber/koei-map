"""さいたま市営住宅（窓口は埼玉県住宅供給公社 saijk.or.jp）。
入口: https://www.saijk.or.jp/lookingfor/shiei/saitama/ （「募集状況」に応募期間。募集案内PDFは募集期間中だけ）
物件一覧: https://www.saijk.or.jp/lookingfor/shiei/saitama/list/ （HTML表：団地名・住所・棟数・管理戸数・竣工年度・間取り図PDF。常にある）
お知らせ一覧: https://www.saijk.or.jp/category/sityoson/ （市町村営住宅課。募集案内PDF・入居申込者数PDF・抽選結果PDFが残っている）
募集は年3回（原則4・8・12月の1日〜21日、公開抽選）。

読み方：
- 期間外 … HTML表の全団地を「団地情報」として物件にする（募集戸数なし。round_id は次の募集）。前回募集の申込み結果PDF（文字あり）が
  あれば、前回の倍率を添える。
- 期間中 … 募集案内PDF（「市営住宅募集一覧」: No./住宅名/間取り/募集戸数/家賃/竣工年度/建物階数/所在地/浴槽/EV/P/交通機関/前回倍率）を読む。
  ただし令和7年12月・令和8年4月・8月の案内PDFは画像だけ（DocuWorksのスキャン、文字なし）だったので、そのときは
  「入居申込者数」PDF（番号/住宅名/種別/間取り/募集戸数/申込者数/倍率。文字あり。期間の半ばに途中経過が出る）で代用し、
  それも無ければ団地情報に落とす。
"""
from __future__ import annotations
import re, datetime, hashlib
import pdfplumber
import pypdfium2 as pdfium
from . import common as C
from .saitama import is_stamp

OP = "saitamacity"
PREF = "埼玉県"
PAGE = "https://www.saijk.or.jp/lookingfor/shiei/saitama/"
LIST = "https://www.saijk.or.jp/lookingfor/shiei/saitama/list/"
NEWS = "https://www.saijk.or.jp/category/sityoson/"
MONTHS = (4, 8, 12)
NOTE = "年3回（原則4・8・12月の1日〜21日）。郵送またはWeb申込、公開抽選"
# 募集案内PDF「市営住宅募集一覧」の列（文字のあるPDFが出たときに使う）
GUIDE_KEYS = {"no": "No", "name": "住宅名", "layout": "間取り", "units": "募集", "rent": "家賃", "built": "竣工", "floors": "建物",
              "addr": "所在地", "bath": "浴槽", "ev": "EV", "park": "P", "access": "交通", "ratio": "前回"}
# 入居申込者数PDFの列
OUBO_KEYS = {"no": "番号", "name": "住宅名", "kind": "種別", "layout": "間取り", "units": "募集戸数", "applicants": "申込者数", "ratio": "倍率"}
PERIOD = re.compile(r"(?:令和(\d+)年)?(\d{1,2})月(\d{1,2})日\s*[（(]?[^0-9()（）～~-]{0,3}[)）]?\s*(?:午前|午後)?[\d:]*\s*[～~-]\s*(?:令和(\d+)年)?(\d{1,2})月(\d{1,2})日")


# ---------- 取得・文字 ----------
def strip_tags(html: str) -> str:
    html = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
    return C.z2h(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))).replace("　", " ")


def links(html: str) -> list[tuple[str, str]]:
    """(href, リンク文字) の一覧。"""
    out = []
    for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        out.append((m.group(1).replace("\n", ""), C.z2h(re.sub(r"<[^>]+>", "", m.group(2))).strip()))
    return out


def period_after(text: str, word: str, today: datetime.date) -> tuple[str | None, str | None]:
    """『【郵送申込み】令和8年8月1日(土)～令和8年8月21日(金)』のように、見出し語の直後の期間を読む。年が無ければ今日に近い年。"""
    for mm in re.finditer(re.escape(word), text):
        m = PERIOD.search(text[mm.end():mm.end() + 100])
        if m:
            r1, fm, fd, r2, tm, td = m.groups()
            fm, fd, tm, td = int(fm), int(fd), int(tm), int(td)
            fy = 2018 + int(r1) if r1 else C.pick_year(fm, fd, today)
            ty = 2018 + int(r2) if r2 else (fy if (tm, td) >= (fm, fd) else fy + 1)
            return f"{fy}-{fm:02d}-{fd:02d}", f"{ty}-{tm:02d}-{td:02d}"
    return None, None


def next_round_month(after: tuple[int, int]) -> tuple[int, int]:
    """(年, 月) の次の募集月（4・8・12月）。"""
    y, m = after
    for mm in MONTHS:
        if mm > m:
            return y, mm
    return y + 1, MONTHS[0]


def stem(name: str) -> str:
    """住宅名を団地の表と突き合わせるための形：『馬宮住宅①』『峰岸住宅A棟』『浮谷住宅(中層)』『美幸町団地』→ 馬宮・峰岸・浮谷・美幸町。"""
    s = C.z2h(name).replace(" ", "")
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = re.sub(r"[①-⑳※].*$", "", s)
    s = re.sub(r"(住宅|団地)[A-Za-z0-9]*棟?$", "", s)
    s = re.sub(r"[A-Z]棟$", "", s)
    return s


def pdf_has_table_text(path) -> bool:
    """募集一覧の表が文字として入っているPDFか（スキャン画像だけのPDFは False。最後のチラシだけ文字がある版もあるので、
    「住宅名」と「所在地」の両方があるページを探す）。pdfplumber より速い pypdfium2 で見る。"""
    doc = pdfium.PdfDocument(str(path))
    try:
        for i in range(len(doc)):
            t = C.z2h(doc[i].get_textpage().get_text_range())
            if "住宅名" in t and "所在地" in t:
                return True
        return False
    finally:
        doc.close()


# ---------- 常にあるHTML表（全団地） ----------
def parse_list_html(html: str) -> list[dict]:
    """物件一覧の表 → [{name, address, bldgs, total, built, plan_pdf}]。"""
    m = re.search(r"<table.*?</table>", html, re.S)
    if not m:
        raise C.SourceError(f"物件一覧の表が無い: {LIST}")
    rows = re.findall(r"<tr.*?</tr>", m.group(0), re.S)
    idx, out = None, []
    for row in rows:
        raw = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
        cells = [C.z2h(re.sub(r"<[^>]+>", "", c)).replace(" ", "").strip() for c in raw]
        if idx is None:
            if any("団地名" in c for c in cells):
                idx = C.header_index(cells, {"name": "団地名", "addr": "住所", "bldgs": "棟数", "total": "管理戸数", "built": "竣工", "plan": "間取り図"})
                if not all(k in idx for k in ("name", "addr")):
                    raise C.SourceError(f"物件一覧の列が足りない: {cells}")
            continue
        g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
        if not g("name") or "さいたま市" not in g("addr"):
            continue
        pdf = re.search(r'href="([^"]+\.pdf)"', raw[idx["plan"]]) if "plan" in idx and idx["plan"] < len(raw) else None
        out.append({"name": g("name"), "address": g("addr"), "bldgs": C.to_int(g("bldgs")), "total": C.to_int(g("total")),
                    "built": g("built"), "plan_pdf": pdf.group(1) if pdf else ""})
    if len(out) < 10:
        raise C.SourceError(f"物件一覧の表を読んだが{len(out)}件: {LIST}")
    return out


def danchi_listings(danchi: list[dict], round_id: str, prev: dict | None) -> list[dict]:
    """団地情報（募集戸数なし）。prev は前回募集の申込み結果（stem → {label, ratio, units}）。"""
    out = []
    for d in danchi:
        ward = re.search(r"さいたま市(.*?区)", d["address"])
        p = (prev or {}).get(stem(d["name"]))
        spec = "・".join(x for x in [f"{d['bldgs']}棟" if d["bldgs"] else "", f"管理戸数{d['total']}戸" if d["total"] else ""] if x)
        if p:
            spec += f"　前回募集（{p['label']}）: {p['text']}"
        out.append(C.listing(
            id=f"{OP}-danchi-{hashlib.md5(d['name'].encode()).hexdigest()[:8]}", operator=OP, round_id=round_id,
            category="一般", subtype="団地情報（次回募集は公式で）", name=d["name"], pref=PREF,
            city="さいたま市" + (ward.group(1) if ward else ""), address=d["address"], units=None,
            built=d["built"], built_from=C.built_year(d["built"]), spec=spec, ratio_prev=p["ratio"] if p else None,
            official_url=PAGE, pdf_url=d["plan_pdf"],
        ))
    return out


# ---------- 入居申込者数PDF（文字あり） ----------
def parse_oubo_pdf(path, pdf_url: str) -> tuple[list[dict], str]:
    """番号/住宅名/種別/間取り/募集戸数/申込者数/倍率 → 行の一覧と、集計日（『2026年8月31日』）。"""
    rows = []
    with pdfplumber.open(path) as pdf:
        first = C.z2h(pdf.pages[0].extract_text() or "")
        dm = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", first)
        asof = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}" if dm else ""
        for pi, page in enumerate(pdf.pages):
            for table in page.extract_tables():
                idx = None
                for row in table:
                    raw = [(c or "").replace("\n", "").strip() for c in row]
                    cells = [C.z2h(c) for c in raw]
                    if idx is None:
                        if any("住宅名" in c for c in cells) and any("申込者数" in c for c in cells):
                            idx = C.header_index(cells, OUBO_KEYS)
                            if not all(k in idx for k in ("no", "name", "units", "applicants")):
                                raise C.SourceError(f"入居申込者数PDFの列が足りない: {cells}")
                        continue
                    g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                    if not re.match(r"^\d+$", g("no")):
                        continue
                    # 住宅名は ①②やＡ棟をそのまま見せたいので z2h 前の文字
                    rows.append({"no": g("no"), "name": raw[idx["name"]], "kind": g("kind"), "layout": g("layout"), "units": C.to_int(g("units")),
                                 "applicants": C.to_int(g("applicants")), "ratio": C.to_float(g("ratio")), "page": pi + 1})
    if not rows:
        raise C.SourceError(f"入居申込者数PDFを読んだが0件: {pdf_url}")
    return rows, asof


def oubo_listings(rows: list[dict], asof: str, round_id: str, pdf_url: str, danchi: list[dict], subtype: str) -> list[dict]:
    by_stem = {stem(d["name"]): d for d in danchi}
    out = []
    for r in rows:
        d = by_stem.get(stem(r["name"]), {})
        ward = re.search(r"さいたま市(.*?区)", d.get("address", ""))
        kind = r["kind"]
        persons = {"単身": "単身", "一般(3人以上)": "3人以上の世帯", "若者夫婦・子育て": "若者夫婦・子育て世帯"}.get(kind, "")
        spec = f"申込者数{r['applicants']}人" + (f"（倍率{r['ratio']}倍）" if r["ratio"] is not None else "") + (f" {asof}時点" if asof else "")
        out.append(C.listing(
            id=f"{round_id}-{r['no']}", operator=OP, round_id=round_id, category=kind or "一般", subtype=subtype,
            name=r["name"], pref=PREF, city="さいたま市" + (ward.group(1) if ward else ""), address=d.get("address", ""),
            persons=persons, single_ok=kind == "単身", units=r["units"], layout=C.layout_norm(r["layout"]),
            built=d.get("built", ""), built_from=C.built_year(d.get("built", "")), spec=spec,
            official_url=PAGE, pdf_url=f"{pdf_url}#page={r['page']}", pdf_page=str(r["page"]),
        ))
    return out


# ---------- 募集案内PDF（文字のあるものが出たとき） ----------
def parse_guide_pdf(path, round_id: str, pdf_url: str) -> list[dict]:
    """「市営住宅募集一覧」の表。種別は表の直前の見出し（一般住宅／一般住宅(3人以上世帯)／若者夫婦・子育て世帯向け住宅／単身住宅／車イス住宅）。
    埼玉県営と同じ公社なので、ハンコ文字（黄色）があれば除く。"""
    out = []
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages):
            pg = page.filter(lambda o: not is_stamp(o))
            text = C.z2h(pg.extract_text() or "")
            if "募集一覧" not in text and "住宅名" not in text:
                continue
            heads = [(m.start(), m.group(1)) for m in re.finditer(r"(一般住宅\s*\(3人以上世帯\)|一般住宅|若者夫婦・子育て世帯向け住宅|単身住宅|車イス住宅\s*\([^)]*\)|車イス住宅)", text)]
            for table in pg.find_tables():
                idx = None
                cat = "一般"
                top = table.bbox[1]
                # 表より上にある見出しのうち一番近いもの
                above = [w for w in pg.extract_words() if w["bottom"] <= top + 2 and re.search(r"住宅$", C.z2h(w["text"]))]
                if above:
                    cat = C.z2h(max(above, key=lambda w: w["bottom"])["text"])
                data = table.extract()
                for row_i, row in enumerate(table.rows):
                    cells = [C.z2h((c or "").replace("\n", " ")).strip() for c in data[row_i]]
                    if idx is None:
                        if any("住宅名" in c for c in cells) and any("所在地" in c for c in cells):
                            idx = C.header_index(cells, GUIDE_KEYS)
                            if not all(k in idx for k in ("no", "name", "layout", "units", "rent", "addr")):
                                raise C.SourceError(f"募集一覧の列が足りない: {cells}")
                        continue
                    g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                    if not re.match(r"^\d+$", g("no")):
                        continue
                    addr = re.sub(r"\s+", "", g("addr"))
                    ward = re.match(r"^(.*?区)", addr)
                    rent_min, rent_max = C.rent_range(g("rent"))
                    area = re.search(r"\((\d+(?:\.\d+)?)", g("layout"))
                    floor = re.search(r"\((.*?)\)", g("units"))
                    out.append(C.listing(
                        id=f"{round_id}-{g('no')}", operator=OP, round_id=round_id, category=cat, subtype="定期募集",
                        name=re.sub(r"【新築】|※注\d*", "", g("name")).strip(), pref=PREF, city="さいたま市" + (ward.group(1) if ward else ""),
                        address=("さいたま市" + addr) if addr and not addr.startswith("さいたま市") else addr, access=re.sub(r"\s+", "", g("access")),
                        persons="単身" if "単身" in cat else ("3人以上の世帯" if "3人以上" in cat else ""), single_ok="単身" in cat,
                        units=C.to_int(g("units")), layout=C.layout_norm(re.sub(r"\(.*", "", g("layout"))),
                        area_text=g("layout"), area_min=float(area.group(1)) if area else None, area_max=float(area.group(1)) if area else None,
                        rent_min=rent_min, rent_max=rent_max, built=g("built"), built_from=C.built_year(g("built")),
                        elevator=g("ev").startswith("有"), floor=(floor.group(1) if floor else "") + (f" {g('floors')}" if g("floors") else ""),
                        spec=("駐車場あり" if g("park").startswith("有") else "") + ("　新築" if "新築" in g("name") else ""),
                        ratio_prev=C.to_float(g("ratio")), official_url=PAGE, pdf_url=f"{pdf_url}#page={pi + 1}", pdf_page=str(pi + 1),
                    ))
    if not out:
        raise C.SourceError(f"募集案内PDF（文字あり）を読んだが0件: {pdf_url}")
    return out


# ---------- 本体 ----------
def find_news(news_links, reiwa: int, month: int, word: str, exclude=("訂正",)) -> str | None:
    for href, text in news_links:
        if "さいたま" in text and word in text and re.search(rf"令和{reiwa}年\s*{month}月", text) and not any(x in text for x in exclude) and href.lower().endswith(".pdf"):
            return href
    return None


def run(today: datetime.date):
    listings, rounds, notes = [], [], []
    expect = False
    html = C.read_text(C.fetch(PAGE, subdir=OP, refresh=True))
    text = strip_tags(html)
    a, b = period_after(text, "郵送申込み", today)
    if not a:
        a, b = period_after(text, "応募期間", today)
    if not a:
        a, b = period_after(text, "Web申込み", today)

    danchi = parse_list_html(C.read_text(C.fetch(LIST, subdir=OP, name="list.html", refresh=True)))
    news_links = links(C.read_text(C.fetch(NEWS, subdir=OP, name="news.html", refresh=True)))
    page_links = links(html)

    # 公式ページに書かれている募集（過ぎていれば次の募集月の「例年」だけ）
    cur = None
    if a:
        y, m = int(a[:4]), int(a[5:7])
        cur = {"id": f"{OP}-{y}-{m:02d}", "operator": OP, "label": f"さいたま市営住宅 {m}月定期募集", "kind": "公開抽選・郵送またはWeb申込",
               "apply_from": a, "apply_to": b, "url": PAGE, "note": NOTE}
        if b < today.isoformat():
            ny, nm = next_round_month((y, m))
            cur = None
        else:
            rounds.append(cur)
    else:
        notes.append("さいたま市営：公式ページから応募期間が読めなかった")
        ny, nm = next_round_month((today.year, today.month - (1 if today.month in MONTHS and today.day <= 21 else 0)))
    if cur is None:
        rounds.append({"id": f"{OP}-{ny}-{nm:02d}", "operator": OP, "label": f"さいたま市営住宅 {nm}月定期募集", "kind": "公開抽選・郵送またはWeb申込",
                       "expected": f"例年4・8・12月の1日〜21日（次は{ny}年{nm}月の見込み。日付は募集月の1日ごろ公式で）", "url": PAGE, "note": NOTE})
    round_id = rounds[-1]["id"] if cur is None else cur["id"]

    # 前回募集の申込み結果（最終）：団地情報に前回の倍率を添える
    prev = {}
    for href, t in news_links:
        if "さいたま" in t and "入居申込者数" in t and "最終" in t and href.lower().endswith(".pdf"):
            try:
                rows, asof = parse_oubo_pdf(C.fetch(href, subdir=OP), href)
                lm = re.search(r"令和(\d+)年\s*(\d{1,2})月", t)
                label = f"{2018 + int(lm.group(1))}年{lm.group(2)}月" if lm else asof
                for r in rows:
                    s = stem(r["name"])
                    if s not in prev:
                        prev[s] = {"label": label, "ratio": r["ratio"], "text": ""}
                    prev[s]["text"] += (" / " if prev[s]["text"] else "") + f"{r['kind']} {r['layout']} {r['units']}戸" + (f" 倍率{r['ratio']}" if r["ratio"] is not None else "")
            except Exception as e:  # 添え物なので失敗しても止めない
                notes.append(f"さいたま市営：前回募集の申込み結果PDFが読めなかった（{type(e).__name__}: {e}）")
            break

    if cur and cur["apply_from"] <= today.isoformat() <= cur["apply_to"]:
        expect = True
        reiwa, month = int(cur["id"].split("-")[1]) - 2018, int(cur["id"].split("-")[2])
        # 1) 募集案内PDF（入口ページ → お知らせ一覧）
        guide = find_news(page_links, reiwa, month, "募集の案内") or find_news(news_links, reiwa, month, "募集の案内")
        if not guide:
            guide = next((h for h, t in page_links if "募集案内" in t and h.lower().endswith(".pdf") and "FAQ" not in h.upper()), None)
        if guide:
            path = C.fetch(guide, subdir=OP, name=f"annai_{cur['id']}.pdf")
            if pdf_has_table_text(path):
                listings += parse_guide_pdf(path, round_id, guide)
            else:
                notes.append("さいたま市営：募集案内PDFは画像だけ（文字なし）で読めない")
        else:
            notes.append("さいたま市営：募集期間中だが募集案内PDFのリンクが見つからない")
        # 2) 代わりに「入居申込者数」PDF（途中経過／最終）
        if not listings:
            oubo = find_news(news_links, reiwa, month, "入居申込者数")
            if oubo:
                rows, asof = parse_oubo_pdf(C.fetch(oubo, subdir=OP), oubo)
                listings += oubo_listings(rows, asof, round_id, oubo, danchi, "定期募集（募集住宅は申込み状況表から。家賃等は募集案内PDFで）")
                notes.append(f"さいたま市営：募集住宅は入居申込者数PDF（{asof}時点）から読んだ")
        # 3) それも無ければ団地情報
        if not listings:
            listings += danchi_listings(danchi, round_id, prev)
            notes.append("さいたま市営：募集期間中だが募集住宅の一覧が読めず、全団地を団地情報として出した")
    else:
        listings += danchi_listings(danchi, round_id, prev)
    return listings, rounds, {"expect_listings": expect, "notes": notes}
