"""千葉県営住宅（千葉県住宅供給公社）：空家募集（年4回・抽選）、常時募集（先着順）、全団地の一覧を読む。
入口（Shift_JIS・http）:
  空家募集 http://www.chiba-kousya.or.jp/jutak/akitop.html   … 年度の募集日程表（配布日・募集期間・抽選日）がHTML表で載っている
  団地一覧 http://www.chiba-kousya.or.jp/jutak/akidan.html   … 募集期間中だけ「空家募集団地一覧表」PDF（akidanRRMM.pdf。RR=令和の年, MM=月）へのリンクが出る。
                                                               期間外は「○月分空家住宅募集は、終了しました」だけ
  常時募集 http://www.chiba-kousya.or.jp/jutak/jojitop.html  … 団地ごとのページ（joji*.html）に「募集戸数」のHTML表。取り消し線（<s>）の行は申込済
  団地情報 http://www.chiba-kousya.or.jp/jutak/danmap.html   … 地域ごとのページ（01/〜04/）に市区町村別の全団地表（住宅名称・所在地・交通の便・建設年度・間取り）
空家募集PDFには所在地が無いので、団地情報の表から（市区町村＋住宅名）で住所・交通を補う。
"""
from __future__ import annotations
import re, datetime, urllib.parse
from html.parser import HTMLParser
import pdfplumber
from . import common as C

OP = "chiba"
PREF = "千葉県"
BASE = "http://www.chiba-kousya.or.jp/jutak/"
AKITOP = BASE + "akitop.html"
AKIDAN = BASE + "akidan.html"
JOJITOP = BASE + "jojitop.html"
DANMAP = BASE + "danmap.html"
ENC = "cp932"
MONTHS = (4, 7, 10, 1)  # 空家募集の月（各1〜15日）
DAN_KEYS = {"name": "住宅名称", "type": "タイプ", "single": "単身", "layout": "間取り", "units": "管理戸数", "rent": "家賃",
            "addr": "所在地", "access": "交通", "built": "建設", "bath": "浴槽", "memo": "備考"}
JOJI_KEYS = {"danchi": "団地名", "type": "タイプ", "units": "戸数", "single": "単身", "young": "若年", "floor": "階数",
             "layout": "間取り", "plan": "間取図", "rent": "家賃", "deposit": "敷金", "bath": "浴槽"}
PDF_KEYS = {"city": "市・町", "name": "住宅名", "single": "単身入居", "young": "若年", "bath": "浴槽", "units": "募集戸数",
            "rent": "原則階層", "layout": "間取り", "plan": "間取り図", "struct": "構造", "memo": "備考"}


# ---------- HTML の表を rowspan/colspan を広げて読む（標準ライブラリだけ） ----------
class _Tables(HTMLParser):
    """<table> を入れ子も含めて全部集める。各セルは {"text", "s"(取り消し線), "href"}。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack = [], []

    def _end_cell(self):
        t = self.stack[-1]
        if t["cell"] is not None:
            c = t["cell"]; c["text"] = "".join(c["text"]); t["row"].append(c); t["cell"] = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs); tag = tag.lower()
        if tag == "table":
            self.stack.append({"rows": [], "row": None, "cell": None})
            return
        if not self.stack:
            return
        t = self.stack[-1]
        if tag == "tr":
            self._end_cell()
            if t["row"] is not None:
                t["rows"].append(t["row"])
            t["row"] = []
        elif tag in ("td", "th"):
            self._end_cell()
            if t["row"] is None:
                t["row"] = []
            t["cell"] = {"text": [], "rs": int(a.get("rowspan") or 1), "cs": int(a.get("colspan") or 1), "s": False, "href": None}
        elif t["cell"] is not None:
            if tag in ("s", "strike", "del"):
                t["cell"]["s"] = True
            elif tag == "a" and a.get("href"):
                t["cell"]["href"] = a["href"]
            elif tag == "br":
                t["cell"]["text"].append(" ")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if not self.stack:
            return
        t = self.stack[-1]
        if tag in ("td", "th"):
            self._end_cell()
        elif tag == "tr":
            self._end_cell()
            if t["row"] is not None:
                t["rows"].append(t["row"]); t["row"] = None
        elif tag == "table":
            self._end_cell()
            if t["row"] is not None:
                t["rows"].append(t["row"])
            self.stack.pop()
            self.tables.append(_expand(t["rows"]))

    def handle_data(self, d):
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"]["text"].append(d)


def _expand(rows):
    """rowspan/colspan を広げて、どの行も同じ列数で引けるようにする。"""
    grid, pend = [], {}
    for r in rows:
        out, ci, it = [], 0, iter(r)
        while True:
            if ci in pend:
                c, n = pend[ci]; out.append(c)
                if n > 1: pend[ci] = (c, n - 1)
                else: del pend[ci]
                ci += 1; continue
            try:
                c = next(it)
            except StopIteration:
                break
            for _ in range(c["cs"]):
                out.append(c)
                if c["rs"] > 1:
                    pend[ci] = (c, c["rs"] - 1)
                ci += 1
        while ci in pend:
            c, n = pend[ci]; out.append(c)
            if n > 1: pend[ci] = (c, n - 1)
            else: del pend[ci]
            ci += 1
        grid.append(out)
    return grid


def html_tables(text: str):
    p = _Tables(); p.feed(text); return p.tables


def T(c) -> str:
    """セルの文字（全角→半角、空白をまとめる）。"""
    return re.sub(r"\s+", " ", C.z2h((c or {}).get("text", "") if isinstance(c, dict) else (c or "")).replace("\xa0", " ")).strip()


def page_text(html: str) -> str:
    return C.z2h(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I))))


# ---------- 文字の整形 ----------
_KANJI = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "七", "8": "八", "9": "九", "10": "十"}


def norm_name(s: str) -> str:
    """住宅名の表記ゆれを吸収：全角→半角、空白除去、括弧書き（地番・棟）除去、ヶ→ケ、第2→第二。"""
    s = C.z2h(s or "").replace(" ", "")
    s = re.sub(r"[（(][^（）()]*[)）]?", "", s)
    s = s.replace(")", "").replace("ヶ", "ケ").replace("ｹ", "ケ").replace("県営住宅", "")
    s = re.sub(r"第(\d{1,2})", lambda m: "第" + _KANJI.get(m.group(1), m.group(1)), s)
    return s


def norm_city(s: str) -> str:
    s = C.z2h(s or "").replace(" ", "").replace("ヶ", "ケ")
    return s


def built_year2(s: str) -> int | None:
    """団地情報の建設年度は '57 59' 'H14' '63 ～H2' のように元号抜きの2桁がある（昭和とみなす）。"""
    y = C.built_year(s)
    if y:
        return y
    nums = [int(x) for x in re.findall(r"(?<![\dH-])(\d{2})(?![\d.])", C.z2h(s or "")) if 20 <= int(x) <= 64]
    return 1925 + min(nums) if nums else None


_ERA_BASE = {"令和": 2018, "平成": 1988, "昭和": 1925}


def wareki_year(s: str) -> int | None:
    m = re.search(r"(令和|平成|昭和)\s*(元|\d{1,2})\s*年", C.z2h(s or ""))
    if not m:
        return None
    return _ERA_BASE[m.group(1)] + (1 if m.group(2) == "元" else int(m.group(2)))


def jp_date(s: str) -> datetime.date | None:
    """'令和７年１月３０日（木）' → date。"""
    m = re.search(r"(令和|平成)\s*(元|\d{1,2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", C.z2h(s or ""))
    if not m:
        return None
    y = _ERA_BASE[m.group(1)] + (1 if m.group(2) == "元" else int(m.group(2)))
    try:
        return datetime.date(y, int(m.group(3)), int(m.group(4)))
    except ValueError:
        return None


def fy_date(fy: int, month: int, day: int) -> datetime.date:
    return datetime.date(fy if month >= 4 else fy + 1, month, day)


def round_id(y: int, m: int) -> str:
    return f"{OP}-{y}-{m:02d}"


def rent_cells(cells, start, stop) -> tuple[int | None, int | None]:
    return C.rent_range(" ".join(cells[start:stop]))


# ---------- 募集の予定（akitop.html の日程表） ----------
def parse_schedule(html: str, today: datetime.date, notes: list) -> list[dict]:
    fy = None
    m = re.search(r"(令和\d{1,2}年度)\s*入居者募集日程表", page_text(html))
    if m:
        fy = wareki_year(m.group(1))
    rounds = []
    for tb in html_tables(html):
        hdr = [T(c).replace(" ", "") for c in tb[0]] if tb else []
        if not any("募集期間" in h for h in hdr) or not any("抽選日" in h for h in hdr):
            continue
        idx = C.header_index(hdr, {"dist": "配布", "period": "募集期間", "lottery": "抽選日", "movein": "入居時期"})
        for row in tb[1:]:
            cells = [T(c) for c in row]
            g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
            mm = next((m for m in (re.match(r"^(\d{1,2})月募集", c.replace(" ", "")) for c in cells) if m), None)  # 「4月募集」の行
            if not mm or not fy:
                continue
            month = int(mm.group(1))
            days = re.findall(r"(\d{1,2})月(\d{1,2})日", g("period"))
            lot = re.findall(r"(\d{1,2})月(\d{1,2})日", g("lottery"))
            dist = re.findall(r"(\d{1,2})月(\d{1,2})日", g("dist"))
            if len(days) < 2:
                continue
            a, b = fy_date(fy, int(days[0][0]), int(days[0][1])), fy_date(fy, int(days[-1][0]), int(days[-1][1]))
            rd = {"id": round_id(a.year, a.month), "operator": OP, "label": f"千葉県営住宅 {month}月期 空家募集", "kind": "抽選",
                  "apply_from": a.isoformat(), "apply_to": b.isoformat(), "url": AKITOP,
                  "note": f"令和{fy - 2018}年度の募集日程表より。申込は郵送（期間内の消印）。一覧表は募集期間中に団地一覧ページでPDF公開"}
            if lot:
                rd["lottery"] = fy_date(fy, int(lot[0][0]), int(lot[0][1])).isoformat()
            if dist:
                rd["note"] += f"。案内配布 {dist[0][0]}/{dist[0][1]}以降"
            if g("movein"):
                rd["note"] += f"。入居時期 {g('movein')}"
            rounds.append(rd)
        if rounds:
            break
    if not rounds:
        notes.append("千葉県営：空家募集の日程表が読めなかった（例年の月だけ出す）")
    return rounds


def next_expected(rounds: list[dict], today: datetime.date) -> dict | None:
    """日程表の募集が全部終わっていたら、次の月（日付なし）を1件。"""
    if any(r.get("apply_to", "") >= today.isoformat() for r in rounds):
        return None
    y, mth = today.year, today.month
    while not (mth in MONTHS and datetime.date(y, mth, 15) >= today):  # 今日以降で最初の 4・7・10・1月
        mth += 1
        if mth > 12:
            y, mth = y + 1, 1
    return {"id": round_id(y, mth), "operator": OP, "label": f"千葉県営住宅 {mth}月期 空家募集", "kind": "抽選",
            "expected": f"例年{mth}月1日〜15日（日程表は未発表）", "url": AKITOP, "note": "年4回（4・7・10・1月、各1〜15日）"}


# ---------- 団地情報（全団地の一覧） ----------
def parse_danchi(notes: list) -> dict:
    """danmap.html → 地域ページ → {(市区町村, 住宅名): {...}}。"""
    html = C.read_text(C.fetch(DANMAP, subdir=OP, encoding=ENC, refresh=True))
    pages = sorted({re.sub(r"#.*", "", u) for u in re.findall(r'href="([^"]+)"', html) if re.match(r"0\d/[\w.]+\.html", u)})
    if len(pages) < 5:
        raise C.SourceError(f"団地情報の地域ページのリンクが少なすぎる（{len(pages)}件）: {DANMAP}")
    out = {}
    for rel in pages:
        url = urllib.parse.urljoin(DANMAP, rel)
        text = C.read_text(C.fetch(url, subdir=OP, encoding=ENC, refresh=True))
        caps = [T({"text": re.sub(r"<[^>]+>", "", c)}) for c in re.findall(r"<caption[^>]*>(.*?)</caption>", text, flags=re.S | re.I)]
        tbs = [tb for tb in html_tables(text) if tb and any("住宅名称" in T(c) for c in tb[0])]
        if not tbs:
            raise C.SourceError(f"団地情報の表が見つからない: {url}")
        for i, tb in enumerate(tbs):
            cap = caps[i] if i < len(caps) else ""
            m = re.match(r"^[○\s]*(.+?)内県営住宅[（(](.+?)[）)]", cap)
            city, cat = (norm_city(m.group(1)), m.group(2)) if m else ("", "一般住宅")
            hdr = [T(c) for c in tb[0]]
            idx = C.header_index(hdr, DAN_KEYS)
            if not all(k in idx for k in ("name", "addr", "layout")):
                raise C.SourceError(f"団地情報の列が足りない: {hdr}")
            for row in tb[1:]:
                cells = [T(c) for c in row]
                g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                name = g("name")
                if not name:
                    continue
                key = (city, norm_name(name))
                d = out.setdefault(key, {"name": name, "city": city, "cat": cat, "addrs": [], "access": "", "layouts": [], "single": False,
                                         "units": None, "built": [], "memo": [], "rents": [], "href": row[idx["name"]].get("href"), "url": url})
                addr = re.sub(r"[（(][^（）()]*[)）]?", "", g("addr")).strip()
                if addr and addr not in d["addrs"]:
                    d["addrs"].append(addr)
                d["access"] = d["access"] or g("access")
                lay = C.layout_norm(g("layout"))
                if lay and lay not in d["layouts"]:
                    d["layouts"].append(lay)
                d["single"] = d["single"] or ("可" in g("single"))
                d["units"] = d["units"] or C.to_int(g("units"))
                if g("built") and g("built") not in d["built"]:
                    d["built"].append(g("built"))
                if g("memo") and g("memo") not in d["memo"]:
                    d["memo"].append(g("memo"))
                if "rent" in idx and C.to_int(g("rent")):
                    d["rents"].append(C.to_int(g("rent")))
    if len(out) < 50:
        raise C.SourceError(f"団地情報が少なすぎる（{len(out)}団地）")
    return out


def full_address(city: str, addr: str) -> str:
    """団地情報の所在地は千葉市内だと「中央区松波2-24-3」（市が無い）、他は「市川市国府台1-2」（市から）。"""
    if city.endswith("区"):
        if addr.startswith("千葉市"):
            return addr
        return "千葉市" + (addr if addr.startswith(city) or re.match(r"^.+?区", addr) else city + addr)
    if not addr:
        return city
    return addr if addr.startswith(city) else city + addr


def city_label(city: str) -> str:
    return "千葉市" + city if city.endswith("区") else city


def lookup(dan: dict, city: str, name: str) -> dict | None:
    """空家募集PDFの（市・町・名, 住宅名）から団地情報を引く。千葉市は区が分からないので名前だけで探す。"""
    city, nm = norm_city(city), norm_name(name)
    if (city, nm) in dan:
        return dan[(city, nm)]
    hits = [v for (c, n), v in dan.items() if n == nm and (c == city or (city == "千葉市" and c.endswith("区")))]
    if not hits:
        hits = [v for (c, n), v in dan.items() if (n.startswith(nm) or nm.startswith(n)) and (c == city or (city == "千葉市" and c.endswith("区")))]
    return hits[0] if len(hits) == 1 else None


def danchi_listings(dan: dict, rid: str) -> list[dict]:
    out = []
    for (city, key), d in dan.items():
        years = [built_year2(b) for b in d["built"]]
        years = [y for y in years if y]
        memo = " / ".join(d["memo"])
        rent_min, rent_max = (min(d["rents"]), max(d["rents"])) if d["rents"] else (None, None)
        out.append(C.listing(
            id=f"{OP}-danchi-{city}-{key}", operator=OP, round_id=rid, category=d["cat"], subtype="団地情報（次回募集は公式で）",
            name=d["name"] + "県営住宅", pref=PREF, city=city_label(city), address=full_address(city, d["addrs"][0] if d["addrs"] else ""),
            access=d["access"], persons="単身可（一部）" if d["single"] else "", single_ok=d["single"], units=None,
            layout="・".join(d["layouts"]), layouts=d["layouts"], rent_min=rent_min, rent_max=rent_max,
            built=" / ".join(d["built"]), built_from=min(years) if years else None, elevator="エレベータ" in memo and "無" not in memo,
            spec=(memo + (f"。所在地ほか: {'、'.join(d['addrs'][1:])}" if len(d["addrs"]) > 1 else "")).strip("。"),
            floor=f"管理戸数{d['units']}" if d["units"] else "", official_url=d["url"],
        ))
    return out


# ---------- 常時募集（先着順） ----------
def parse_joji(rid: str, notes: list) -> list[dict]:
    html = C.read_text(C.fetch(JOJITOP, subdir=OP, encoding=ENC, refresh=True))
    links = []
    for u in re.findall(r'href="([^"]+)"', html):
        u = urllib.parse.urljoin(JOJITOP, u)
        if re.search(r"/joji[\w]*\.html$", u) and u != JOJITOP and u not in links:
            links.append(u)
    if not links:
        raise C.SourceError(f"常時募集の団地ページへのリンクが無い: {JOJITOP}")
    out, skipped = [], 0
    for url in links:
        text = C.read_text(C.fetch(url, subdir=OP, encoding=ENC, refresh=True))
        stem = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1].replace(".html", "")
        ptxt = page_text(text)
        title = re.search(r"<title>(.*?)</title>", text, flags=re.S | re.I)
        title = T({"text": title.group(1)}) if title else ""
        cat = next((k for k in ("特定公共賃貸住宅", "地域特別賃貸住宅", "改良住宅", "一般県営住宅") if k in title), "一般県営住宅")
        asof = re.search(r"(令和\d{1,2}年\d{1,2}月\d{1,2}日)\s*現在", ptxt)
        info = {}
        tabs = html_tables(text)
        for tb in tabs:
            for row in tb:
                cells = [T(c) for c in row]
                if len(cells) >= 2 and cells[0] and cells[0] != cells[1]:
                    k = cells[0].replace(" ", "")
                    for key, word in (("name", "団地名"), ("addr", "所在地"), ("struct", "構"), ("built", "建設年度"), ("access", "交通"), ("access", "最寄駅")):
                        if k.startswith(word) and key not in info:
                            info[key] = cells[1]
        addr = re.sub(r"[（(][^（）()]*[)）]?", "", info.get("addr", "")).strip()
        addr = re.sub(r"\s*\d+棟.*$", "", addr).strip()
        m = re.match(r"^(.+?(?:市|郡.+?[町村]|町|村))", addr)
        city = m.group(1) if m else ""
        found = 0
        for tb in tabs:
            hdr = [T(c) for c in tb[0]] if tb else []
            if not any(h.startswith("タイプ") for h in hdr) or not any("家賃" in h for h in hdr):
                continue
            idx = C.header_index(hdr, JOJI_KEYS)
            if "type" not in idx or "rent" not in idx or "layout" not in idx:
                raise C.SourceError(f"常時募集の表の列が足りない: {hdr} {url}")
            rent_stop = min([i for i in (idx.get("deposit"), idx.get("bath"), len(hdr)) if i is not None and i > idx["rent"]])
            for row in tb[1:]:
                cells = [T(c) for c in row]
                g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                typ = g("type").replace(" ", "")
                if not re.match(r"^[A-Z0-9]{1,4}$", typ) or g("type") == hdr[idx["type"]]:
                    continue
                struck = any(c.get("s") for c in row)
                units = C.to_int(g("units"))
                if struck or not units:
                    skipped += 1
                    continue
                danchi = g("danchi").replace(" ", "") if "danchi" in idx else ""
                dname = (danchi + "県営住宅") if danchi else info.get("name", stem)
                rent_min, rent_max = rent_cells(cells, idx["rent"], rent_stop)
                found += 1
                out.append(C.listing(
                    id=f"{OP}-anytime-{stem}-{norm_name(danchi) or 'x'}-{typ}", operator=OP, round_id=rid, category="先着順",
                    subtype=f"常時募集（{cat}）", name=dname, pref=PREF, city=city, address=addr,
                    access=info.get("access", ""), persons=("単身可" if "可" in g("single") else "") + ("・若年単身可" if "可" in g("young") else ""),
                    single_ok="可" in g("single"), units=units, vacant_now=True, layout=C.layout_norm(g("layout")),
                    rent_min=rent_min, rent_max=rent_max, built=info.get("built", ""), built_from=C.built_year(info.get("built", "")),
                    elevator="エレベーター有" in info.get("struct", "") or "エレベータ有" in info.get("struct", ""),
                    floor=(f"{g('floor')}階" if g("floor") else "") , spec=(f"{info.get('struct', '')}" + (f"。{asof.group(1)}現在" if asof else "")).strip("。"),
                    official_url=url,
                ))
        if not found and not re.search(r"募集(戸数|住戸)", ptxt):
            notes.append(f"千葉県営：常時募集ページに募集表が無い {url}")
    if skipped:
        notes.append(f"千葉県営：常時募集で申込済（取り消し線）・戸数0の行を {skipped} 件除いた")
    return out


# ---------- 空家募集（募集期間中の PDF） ----------
def parse_akidan_pdf(url: str, dan: dict, rounds: list[dict], notes: list) -> list[dict]:
    path = C.fetch(url, subdir=OP)
    out = []
    with pdfplumber.open(path) as pdf:
        head = C.z2h(pdf.pages[0].extract_text() or "")
        ym = re.search(r"(令和\d{1,2}年)\s*(\d{1,2})月分", head)
        if not ym:
            raise C.SourceError(f"空家募集PDFの表紙に「○年○月分」が無い: {url}")
        y, mth = wareki_year(ym.group(1)), int(ym.group(2))
        rid = round_id(y, mth)
        rd = next((r for r in rounds if r["id"] == rid), None)
        # 「募 集 期 間 …令和７年１月１日（水）から１５日（水）まで」。z2h で「…」は「...」になるので記号は幅を持たせて読む
        a = re.search(r"募\s*集\s*期\s*間[^令]{0,8}(令和\d{1,2}年\d{1,2}月\d{1,2}日)[^\d]{0,6}から\s*(\d{1,2})日", head)
        lot = re.search(r"抽\s*選\s*日[^令]{0,8}(令和\d{1,2}年\d{1,2}月\d{1,2}日)", head)
        if rd is None:
            rd = {"id": rid, "operator": OP, "label": f"千葉県営住宅 {mth}月期 空家募集", "kind": "抽選", "url": AKIDAN, "note": "空家募集団地一覧表PDFより"}
            rounds.append(rd)
        if a:
            d1 = jp_date(a.group(1))
            if d1:
                rd["apply_from"], rd["apply_to"] = d1.isoformat(), datetime.date(d1.year, d1.month, int(a.group(2))).isoformat()
        if lot and jp_date(lot.group(1)):
            rd["lottery"] = jp_date(lot.group(1)).isoformat()
        rd["pdf_url"] = url
        section, seen = "一般住宅", {}
        for pi, pg in enumerate(pdf.pages):
            if pi == 0:
                continue
            first = C.z2h((pg.extract_text() or "").split("\n")[0]).split("*")[0].split("＊")[0].strip()
            if first and ("住宅" in first or "世帯" in first) and len(first) < 60 and "市" not in first[:1]:
                section = re.split(r"[(:：]", first)[0].strip()  # '18歳未満の子がいる世帯(申込対象者限定住宅):一般住宅' → '18歳未満の子がいる世帯'
            for tb in pg.extract_tables():
                idx, sub, city = None, {}, ""
                for row in tb:
                    cells = [T({"text": (c or "").replace("\n", " ")}) for c in row]
                    joined = "".join(cells).replace(" ", "")
                    if "住宅名" in joined and "市・町" in joined:
                        idx = C.header_index([c.replace(" ", "") for c in cells], PDF_KEYS)
                        if "name" in idx and "type" not in idx:
                            idx["type"] = idx["name"] + 1
                        continue
                    if idx and "戸数" in joined and "階数" in joined:
                        pos = [i for i, c in enumerate(cells) if c.replace(" ", "") == "戸数"]
                        fl = [i for i, c in enumerate(cells) if c.replace(" ", "") == "階数"]
                        rt = [i for i, c in enumerate(cells) if "倍率" in c]
                        sub = {"units": pos, "floor": fl, "ratio": rt}
                        continue
                    if not idx or not all(k in idx for k in ("name", "rent", "layout")):
                        continue
                    if cells[idx["city"]] if "city" in idx else cells[0]:
                        city = cells[idx.get("city", 0)]
                    raw = C.z2h(cells[idx["name"]] + " " + cells[idx["name"] + 1])
                    raw = re.sub(r"[（(][^（）()]*[)）]?", "", raw).replace(")", "")
                    parts = raw.split()
                    if not parts or not city:
                        continue
                    name = parts[0]
                    typ = parts[1] if len(parts) > 1 and re.match(r"^[A-Z0-9]{1,4}$", parts[1]) else ""
                    if not typ:
                        continue
                    g = lambda k: cells[idx[k]] if k in idx and idx[k] < len(cells) else ""
                    units_all = [C.to_int(cells[i]) for i in sub.get("units", []) if i < len(cells)]
                    units = sum(u for u in units_all if u) or None
                    floors = "・".join(cells[i] for i in sub.get("floor", []) if i < len(cells) and cells[i])
                    ratios = [cells[i] for i in sub.get("ratio", []) if i < len(cells) and cells[i]]
                    ratio = next((C.to_float(r) for r in ratios if C.to_float(r) is not None), None)
                    rent_min, rent_max = rent_cells(cells, idx["rent"], idx["layout"])
                    info = lookup(dan, city, name)
                    if not info:
                        notes.append(f"千葉県営：空家募集の「{city} {name}」が団地情報に見つからない（住所は市区町村まで）")
                    city_full = city_label(info["city"]) if info else norm_city(city)
                    addr = full_address(info["city"], info["addrs"][0]) if info and info["addrs"] else city_full + name
                    base_id = f"{rid}-{norm_city(city)}-{norm_name(name)}-{typ}"
                    seen[base_id] = seen.get(base_id, 0) + 1
                    out.append(C.listing(
                        id=base_id + (f"-{seen[base_id]}" if seen[base_id] > 1 else ""), operator=OP, round_id=rid,
                        category=section if "子" in section or "高齢" in section or "車椅子" in section else "一般",
                        subtype="空家募集", name=name + "県営住宅", pref=PREF, city=city_full, address=addr,
                        access=info["access"] if info else "", persons=("単身可" if "可" in g("single") else "") + ("・若年単身可" if "可" in g("young") else ""),
                        single_ok="可" in g("single"), units=units, layout=C.layout_norm(g("layout")),
                        rent_min=rent_min, rent_max=rent_max, built=" / ".join(info["built"]) if info else "",
                        built_from=min([y for y in (built_year2(b) for b in info["built"]) if y], default=None) if info else None,
                        elevator="エレベータ" in g("memo"), floor=(floors + "階") if floors else "", ratio_prev=ratio,
                        spec=(g("struct") + " " + g("memo") + (" 浴槽釜有" if "有" in g("bath") else "") + (" 前回無抽選" if "無抽選" in "".join(ratios) else "")).strip(),
                        official_url=AKIDAN, pdf_url=f"{url}#page={pi + 1}", pdf_page=str(pi + 1),
                    ))
    if not out:
        raise C.SourceError(f"空家募集団地一覧表PDFを読んだが0件: {url}")
    return out


# ---------- まとめ ----------
def run(today: datetime.date):
    notes = []
    sched_html = C.read_text(C.fetch(AKITOP, subdir=OP, encoding=ENC, refresh=True))
    rounds = parse_schedule(sched_html, today, notes)
    nx = next_expected(rounds, today)
    if nx:
        rounds.append(nx)
    upcoming = sorted([r for r in rounds if r.get("apply_to", "9") >= today.isoformat()], key=lambda r: r.get("apply_from", "9"))
    next_rid = upcoming[0]["id"] if upcoming else ""
    rounds.append({"id": f"{OP}-anytime", "operator": OP, "label": "千葉県営住宅 常時募集（先着順）", "kind": "先着順・郵送で申込", "anytime": True,
                   "url": JOJITOP, "note": "団地ごとのページで公開（一般：市原市菊間・袖ケ浦市蔵波、特定公共賃貸：市原市五所、地域特別賃貸：船橋市薬円台）。空家募集との重複申込は不可"})

    dan = parse_danchi(notes)
    listings = danchi_listings(dan, next_rid)
    listings += parse_joji(f"{OP}-anytime", notes)

    # 空家募集の一覧表（募集期間中だけPDFが出る）
    akidan_html = C.read_text(C.fetch(AKIDAN, subdir=OP, encoding=ENC, refresh=True))
    pdfs = [urllib.parse.urljoin(AKIDAN, u) for u in re.findall(r'href="([^"]+\.pdf)"', akidan_html, flags=re.I)]
    pdfs = [u for u in pdfs if re.search(r"akidan", u, re.I)] or pdfs
    in_period = [r for r in rounds if r.get("apply_from") and r["apply_from"] <= today.isoformat() <= r.get("apply_to", "")]
    ptxt = page_text(akidan_html)
    ended = re.search(r"(令和\d{1,2}年)\s*(\d{1,2})月分\s*空家住宅募集は、?\s*終了", ptxt)  # 「令和８年10月分空家住宅募集は、終了しました」
    ended_id = round_id(wareki_year(ended.group(1)), int(ended.group(2))) if ended else ""
    if pdfs:
        listings += parse_akidan_pdf(pdfs[0], dan, rounds, notes)
        if len(pdfs) > 1:
            notes.append(f"千葉県営：団地一覧ページにPDFが{len(pdfs)}件。先頭だけ読んだ: {pdfs}")
    elif in_period and ended_id != in_period[0]["id"]:
        raise C.SourceError(f"募集期間中（{in_period[0]['id']}）なのに空家募集団地一覧表PDFのリンクが無い: {AKIDAN}")
    else:
        nxt = re.search(r"次回、?(令和\d{1,2}年\d{1,2}月分)[^。]*?(令和\d{1,2}年\d{1,2}月\d{1,2}日)", ptxt)
        notes.append("千葉県営：空家募集は期間外（" + (f"{ended.group(1)}{ended.group(2)}月分は終了" if ended else "一覧表PDFなし")
                     + (f"、次回{nxt.group(1)}の一覧表は{nxt.group(2)}以降" if nxt else "") + "）。期間中のPDF読み取りは未検証")
    return listings, rounds, {"expect_listings": True, "notes": notes}
