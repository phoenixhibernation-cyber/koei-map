"""各運営元の読み取りで共通に使う部品：取得（間隔を空ける・保存済みは取り直さない）、住所→緯度経度（国土地理院）、数値や年の整形。"""
from __future__ import annotations
import json, re, time, pathlib, hashlib, unicodedata, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CACHE = ROOT / "data" / "geocode_cache.json"
UA = "koei-map/0.1 (public-housing map; contact via GitHub phoenixhibernation-cyber/koei-map)"
_last = {"t": 0.0}


def polite_sleep(sec: float = 2.0):
    wait = _last["t"] + sec - time.time()
    if wait > 0:
        time.sleep(wait)
    _last["t"] = time.time()


def fetch(url: str, name: str | None = None, subdir: str = "", delay: float = 2.0, binary: bool = True, encoding: str | None = None, refresh: bool = False) -> pathlib.Path:
    """URL を data/raw/<subdir>/<name> に保存して path を返す。保存済みなら取り直さない。"""
    d = RAW / subdir
    d.mkdir(parents=True, exist_ok=True)
    if not name:
        name = hashlib.md5(url.encode()).hexdigest()[:10] + "_" + pathlib.Path(urllib.parse.urlparse(url).path).name
    p = d / name
    if p.exists() and p.stat().st_size > 0 and not refresh:
        return p
    polite_sleep(delay)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if encoding:
        data = data.decode(encoding, errors="ignore").encode("utf-8")
    p.write_bytes(data)
    return p


def read_text(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


# ---------- 住所 → 緯度経度（国土地理院 住所検索API・無料・キー不要） ----------
_cache = None


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


def geocode(address: str, pref: str = "") -> dict | None:
    """住所を緯度経度に。見つからなければ表記を順に簡単にして再検索。結果はキャッシュ。"""
    c = _load_cache()
    addr = norm_addr(address)
    if not addr:
        return None
    key = (pref + addr) if pref and not addr.startswith(pref) else addr
    if key in c:
        return c[key]
    variants = [key]
    a = re.sub(r"(ほか|他|外|先|地内|番地|以下)$", "", key)
    variants.append(a)
    variants.append(re.sub(r"[-－‐−]\d+$", "", a))           # 枝番を落とす
    variants.append(re.sub(r"(\d+)[-－‐−]\d+[-－‐−]?\d*$", r"\1", a))  # 番地まで
    variants.append(re.sub(r"\d+[-－‐−]?\d*$", "", a))      # 丁目・大字まで
    seen, hit, level = set(), None, "exact"
    for i, v in enumerate(variants):
        v = v.strip()
        if not v or v in seen:
            continue
        seen.add(v)
        try:
            hit = _gsi(v)
        except Exception:
            hit = None
        if hit:
            level = "exact" if i == 0 else "approx"
            break
    c[key] = {**hit, "level": level, "query": v} if hit else None
    return c[key]


# ---------- 文字・数値の整形 ----------
def z2h(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").replace("〜", "～")


def norm_addr(s: str) -> str:
    s = z2h(s)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[（(].*?[)）]", "", s)   # （◯◯駅徒歩…）などを除く
    s = s.replace("大字", "").replace("字", "") if "大字" in s else s
    s = s.replace("丁目", "-").replace("番地", "-").replace("番", "-").replace("号", "")
    s = re.sub(r"-+$", "", s)
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
    nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", z2h(str(s or "")))]
    if not nums:
        return None, None
    return min(nums), max(nums)


_ERA = {"M": 1867, "T": 1911, "S": 1925, "H": 1988, "R": 2018, "明": 1867, "大": 1911, "昭": 1925, "平": 1988, "令": 2018}


def built_year(s) -> int | None:
    """'S58' 'H30' '昭56' '平11' '令3' '昭和46' '1998' → 西暦。複数あれば一番古い年。"""
    s = z2h(str(s or ""))
    years = []
    for m in re.finditer(r"(明治|大正|昭和|平成|令和|[MTSHR明大昭平令])\s*(元|\d{1,2})", s):
        era = m.group(1)[0]
        if era in ("明", "大", "昭", "平", "令") and len(m.group(1)) > 1:
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


def listing(**kw) -> dict:
    """共通の1件の形。足りない項目は既定値で埋める。"""
    base = {
        "id": "", "operator": "", "round_id": "", "category": "一般", "subtype": "", "name": "", "pref": "", "city": "",
        "address": "", "lat": None, "lon": None, "access": "", "stations": [], "walk_min": None, "bus": False,
        "persons": "", "single_ok": False, "units": None, "vacant_now": None, "layout": "", "layouts": [],
        "area_text": "", "area_min": None, "area_max": None, "rent_min": None, "rent_max": None,
        "built": "", "built_from": None, "elevator": False, "barrier_free": False, "spec": "", "floor": "",
        "accident": "", "ratio_prev": None, "priority_lottery": False, "official_url": "", "pdf_url": "", "pdf_page": "",
    }
    base.update(kw)
    if base["layout"] and not base["layouts"]:
        base["layouts"] = [x for x in re.split(r"[・/,、]", base["layout"]) if x]
    if base["access"] and not base["stations"]:
        base["stations"] = re.findall(r"「?([^「」\s（）()]+?)駅", z2h(base["access"]))
        base["stations"] = [s + "駅" for s in base["stations"]][:3]
    if base["access"] and base["walk_min"] is None:
        m = re.search(r"徒歩\s*(\d+)\s*分", z2h(base["access"]))
        base["walk_min"] = int(m.group(1)) if m else None
        base["bus"] = "バス" in z2h(base["access"]).replace("ﾊﾞｽ", "バス")
    if base["persons"] and not base["single_ok"]:
        base["single_ok"] = bool(re.search(r"単身|1人|１人|1～2人", z2h(base["persons"])))
    return base


def station_parts(s: str) -> str:
    """'(大宮駅ﾊﾞｽ11分徒歩4分)' のような括弧書きを '大宮駅バス11分徒歩4分' に。"""
    s = z2h(s or "").replace("ﾊﾞｽ", "バス")
    m = re.search(r"[（(]([^（）()]*駅[^（）()]*)[)）]", s)
    return m.group(1) if m else ""
