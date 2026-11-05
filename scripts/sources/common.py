"""各運営元の読み取りで共通に使う部品：取得（間隔を空ける・保存済みは取り直さない）、住所→緯度経度（国土地理院）、数値や年の整形。"""
from __future__ import annotations
import json, re, time, pathlib, hashlib, unicodedata, urllib.parse, urllib.request, datetime, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CACHE = ROOT / "data" / "geocode_cache.json"
UA = "koei-map/0.1 (public-housing map; contact via GitHub phoenixhibernation-cyber/koei-map)"
JST = ZoneInfo("Asia/Tokyo")
_last = {"t": 0.0}


class SourceError(Exception):
    """読み取りに失敗した（PDFを見つけたのに0件、必要な列が無い、など）。build_all が前回の値を残す。"""


def today_jst() -> datetime.date:
    return datetime.datetime.now(JST).date()


def log(*a):
    print(*a, file=sys.stderr)


def polite_sleep(sec: float = 2.0):
    wait = _last["t"] + sec - time.time()
    if wait > 0:
        time.sleep(wait)
    _last["t"] = time.time()


def fetch(url: str, name: str | None = None, subdir: str = "", delay: float = 2.0, encoding: str | None = None, refresh: bool = False, min_bytes: int = 200) -> pathlib.Path:
    """URL を data/raw/<subdir>/<name> に保存して path を返す。保存済みなら取り直さない（refresh=True で取り直す）。
    日本語を含むURLはそのまま送れないので %xx に直す。空の応答やエラーページは保存しない。"""
    d = RAW / subdir
    d.mkdir(parents=True, exist_ok=True)
    if not name:
        name = hashlib.md5(url.encode()).hexdigest()[:10] + "_" + re.sub(r"[^\w.]", "_", urllib.parse.unquote(pathlib.Path(urllib.parse.urlparse(url).path).name))
    p = d / name
    if p.exists() and p.stat().st_size > 0 and not refresh:
        return p
    polite_sleep(delay)
    safe_url = urllib.parse.quote(url, safe=":/?&=%#~+@,;")
    req = urllib.request.Request(safe_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "")
    if len(data) < min_bytes:
        raise SourceError(f"応答が小さすぎる（{len(data)}バイト）: {url}")
    if url.lower().endswith(".pdf") and not data.startswith(b"%PDF"):
        raise SourceError(f"PDFではない応答（{ctype}）: {url}")
    if encoding:
        data = data.decode(encoding, errors="ignore").encode("utf-8")
    p.write_bytes(data)
    return p


def read_text(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


# ---------- 住所 → 緯度経度（国土地理院 住所検索API・無料・キー不要） ----------
_cache = None
_errors = 0


def _load_cache():
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    return _cache


def save_cache():
    if _cache is not None:
        CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=0), encoding="utf-8")


def _gsi(q: str):
    polite_sleep(1.0)
    url = "https://msearch.gsi.go.jp/address-search/AddressSearch?q=" + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read().decode("utf-8"))
    if not res:
        return None
    f = res[0]
    lon, lat = f["geometry"]["coordinates"]
    return {"lat": lat, "lon": lon, "title": f["properties"].get("title", "")}


def _match_level(query: str, title: str) -> str:
    """返ってきた地名が、問い合わせた住所のどこまで合っているか：exact（番地まで）/ town（町名まで）/ city（市区町村だけ）。"""
    q, t = norm_addr(query), norm_addr(title)
    q_city = re.match(r"^(.*?(?:市.*?区|区|市|郡.*?[町村]|町|村))", q)
    q_town = re.sub(r"[-\d]+$", "", q)
    if t and q and (t.startswith(q) or q.startswith(t)) and re.search(r"\d", t):
        return "exact"
    if q_town and t.startswith(q_town) and len(t) > len(q_city.group(1) if q_city else ""):
        return "town"
    return "city"


def geocode(address: str, pref: str = "") -> dict | None:
    """住所を緯度経度に。見つからなければ表記を順に簡単にして再検索。
    結果はキャッシュ。通信エラーのときはキャッシュに書かない（翌日また調べる）。"""
    global _errors
    c = _load_cache()
    addr = norm_addr(address)
    if not addr:
        return None
    key = (pref + addr) if pref and not addr.startswith(pref) else addr
    if key in c and c[key] is not None:
        return c[key]
    if key in c and c[key] is None and (c.get("__missing__", {}).get(key, "0000-00-00") > (today_jst() - datetime.timedelta(days=30)).isoformat()):
        return None
    variants = [key]
    a = re.sub(r"(ほか|他|外|先|地内|以下)$", "", key)
    variants += [a, re.sub(r"-\d+$", "", a), re.sub(r"(\d+)-\d+-?\d*$", r"\1", a), re.sub(r"\d+-?\d*$", "", a)]
    seen, hit, v = set(), None, key
    for v in variants:
        v = v.strip()
        if not v or v in seen:
            continue
        seen.add(v)
        try:
            hit = _gsi(v)
        except Exception as e:
            _errors += 1
            log(f"geocode error ({v}): {type(e).__name__}: {e}")
            return None  # キャッシュしない
        if hit:
            break
    if hit:
        c[key] = {**hit, "level": _match_level(key, hit["title"]), "query": v}
    else:
        c[key] = None
        c.setdefault("__missing__", {})[key] = today_jst().isoformat()
    return c[key]


def geocode_errors() -> int:
    return _errors


# ---------- 文字・数値の整形 ----------
def z2h(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").replace("〜", "～")
    return s.replace("−", "-").replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-").replace("ー", "ー")


def norm_addr(s: str) -> str:
    """住所の表記を国土地理院APIが解きやすい形に。地名の中の「番」「号」は壊さない（数字の直後だけ置き換える）。"""
    s = z2h(s)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = re.sub(r"(\d+)丁目", r"\1-", s)
    s = re.sub(r"(\d+)番地?", r"\1-", s)
    s = re.sub(r"(\d+)号", r"\1", s)
    s = s.replace("大字", "")
    s = re.sub(r"(?<![\d-])字(?=[^\d-])", "", s)
    s = s.replace("～", "-")
    s = re.sub(r"-+", "-", s)
    s = re.sub(r"-$", "", s)
    return s


def to_int(s) -> int | None:
    if s is None:
        return None
    m = re.search(r"-?\d[\d,]*", z2h(str(s)))
    return int(m.group().replace(",", "")) if m else None


def to_float(s) -> float | None:
    if s is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", z2h(str(s)))
    return float(m.group()) if m else None


def rent_range(s) -> tuple[int | None, int | None]:
    """'27,700 ～ 54,400' → (27700, 54400)。家賃らしくない数（5,000円未満・300,000円超）は捨てる。"""
    nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", z2h(str(s or "")))]
    nums = [n for n in nums if 5000 <= n <= 300000]
    if not nums:
        return None, None
    return min(nums), max(nums)


_ERA = {"M": 1867, "T": 1911, "S": 1925, "H": 1988, "R": 2018, "明": 1867, "大": 1911, "昭": 1925, "平": 1988, "令": 2018}


def built_year(s) -> int | None:
    """'S58' 'H30' '昭56' '平11' '令3' '昭和46' 'H13・15' 'S.58' '1998' → 西暦。複数あれば一番古い年。"""
    s = z2h(str(s or ""))
    years = []
    for m in re.finditer(r"(明治|大正|昭和|平成|令和|[MTSHR明大昭平令])[\s.]*(元|\d{1,2})", s):
        era = m.group(1)[0]
        n = 1 if m.group(2) == "元" else int(m.group(2))
        years.append(_ERA[era] + n)
    for m in re.finditer(r"(19|20)\d{2}", s):
        years.append(int(m.group()))
    return min(years) if years else None


def layout_norm(s) -> str:
    s = z2h(str(s or "")).upper().replace(" ", "")
    s = re.sub(r"[（(].*?[)）]", "", s)
    return s


def pick_year(month: int, day: int, today: datetime.date, prefer: str = "near") -> int:
    """月日だけ分かっている日付に年を付ける。今日から前後6か月に収まる年を選ぶ。"""
    best = None
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            d = datetime.date(y, month, day)
        except ValueError:
            continue
        diff = abs((d - today).days)
        if best is None or diff < best[0]:
            best = (diff, y)
    return best[1] if best else today.year


def listing(**kw) -> dict:
    """共通の1件の形。足りない項目は既定値で埋める。"""
    base = {
        "id": "", "operator": "", "round_id": "", "category": "一般", "subtype": "", "name": "", "pref": "", "city": "",
        "address": "", "lat": None, "lon": None, "geo_level": "", "access": "", "stations": [], "walk_min": None, "bus": False,
        "persons": "", "single_ok": False, "units": None, "vacant_now": None, "layout": "", "layouts": [],
        "area_text": "", "area_min": None, "area_max": None, "rent_min": None, "rent_max": None,
        "built": "", "built_from": None, "elevator": False, "barrier_free": False, "spec": "", "floor": "",
        "accident": "", "ratio_prev": None, "priority_lottery": False, "official_url": "", "pdf_url": "", "pdf_page": "",
    }
    base.update(kw)
    if base["layout"] and not base["layouts"]:
        base["layouts"] = [x for x in re.split(r"[・/,、]", base["layout"]) if x]
    acc = z2h(base["access"]).replace("ﾊﾞｽ", "バス")
    if acc and not base["stations"]:
        base["stations"] = [s + "駅" for s in re.findall(r"「?([^「」\s（）()『』｢｣、/]+?)駅", acc)][:3]
    if acc and base["walk_min"] is None:
        m = re.search(r"徒歩\s*(\d+)\s*分", acc)
        base["walk_min"] = int(m.group(1)) if m else None
        base["bus"] = "バス" in acc
    if base["persons"] and not base["single_ok"]:
        base["single_ok"] = bool(re.search(r"単身|1人|１人|1～2人", z2h(base["persons"])))
    return base


def station_parts(s: str) -> str:
    """'(大宮駅ﾊﾞｽ11分徒歩4分)' のような括弧書きを '大宮駅バス11分徒歩4分' に。"""
    s = z2h(s or "").replace("ﾊﾞｽ", "バス")
    m = re.search(r"[（(]([^（）()]*駅[^（）()]*)[)）]", s)
    return m.group(1) if m else ""


def header_index(cells: list[str], keys: dict[str, str]) -> dict[str, int]:
    """見出し行から、欲しい列（キー→見出しの一部の文字）の位置を引く。空白を除いて部分一致。"""
    idx = {}
    for k, word in keys.items():
        for i, c in enumerate(cells):
            if word in (c or "").replace(" ", "").replace("\n", ""):
                idx[k] = i
                break
    return idx
