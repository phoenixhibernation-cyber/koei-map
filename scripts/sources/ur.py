"""UR賃貸住宅（UR都市機構）1都3県の「団地」一覧：団地名・住所・交通・家賃の幅・間取り・管理年数を、公式サイトの静的HTMLから読む。
入口: https://www.ur-net.go.jp/chintai/kanto/
- 都県ごとの「物件一覧から探す」 https://www.ur-net.go.jp/chintai/kanto/<都県>/list/ に、全団地（空き部屋が無い団地も）の詳細リンクが静的に入っている
- 団地の詳細 https://www.ur-net.go.jp/chintai/kanto/<都県>/<団地コード>.html の本文（表）に団地名・家賃の幅・間取り・戸数・交通・住所・構造・管理年数が書かれている
- 部屋ごとの空室・家賃はJSのAPIの裏にあるので取らない（units / vacant_now は None）。空室の確認は official_url へ
取り方の決まり:
- C.fetch だけで取る（見せかけのヘッダーやヘッドレスブラウザは使わない）。robots.txt で禁止された /chintai/*/result/?... は読まない
- 一覧ページ（4枚）は毎回取り直す。詳細ページは data/raw/ur/<団地コード>.html に保存し、普段は取り直さない（新しい団地だけ取りに行く）
- 詳細ページの家賃の幅は古くなるので、保存から REFRESH_DAYS 日を過ぎたものを古い順に 1回の実行で REFRESH_PER_RUN 枚ずつ取り直す（約700枚を3週間ほどで一巡）
転載上の注意: 団地名・住所・交通・家賃の幅など事実情報だけを載せる（写真・紹介文・団地のくらし等は取らない）。家賃は「管理物件全体」の幅で、割引制度適用後の家賃を含む場合がある。
"""
from __future__ import annotations
import re, html, time, datetime, urllib.error
from . import common as C

OP = "ur"
ROUND_ID = "ur-anytime"
BASE = "https://www.ur-net.go.jp"
ENTRY = f"{BASE}/chintai/kanto/"
PREFS = [("tokyo", "東京都"), ("kanagawa", "神奈川県"), ("saitama", "埼玉県"), ("chiba", "千葉県")]
DELAY = 1.5           # 取得の間隔（秒）
REFRESH_DAYS = 30     # 詳細ページをこの日数より古ければ取り直す
REFRESH_PER_RUN = 40  # 1回の実行で取り直す詳細ページの上限（古い順）
ROUND = {"id": ROUND_ID, "operator": OP, "label": "UR賃貸住宅 空き部屋（1都3県）", "kind": "先着順・いつでも", "anytime": True,
         "url": ENTRY, "note": "礼金・仲介手数料・更新料・保証人が不要"}


def _text(s: str) -> str:
    """HTMLの断片 → 文字だけ（タグを外し、実体参照を戻し、空白をまとめる）。"""
    s = re.sub(r"<br\s*/?>", " ", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("　", " ")
    return re.sub(r"\s+", " ", s).strip()


def _h(s: str) -> str:
    """全角数字などを半角に（C.z2h）。範囲の「～」は既存データに合わせて「〜」に。"""
    return C.z2h(s).replace("~", "〜").replace("～", "〜")


def list_codes(pref_key: str) -> dict[str, str]:
    """都県の「物件一覧から探す」ページから {団地コード: 団地名}。読めなければ SourceError。"""
    url = f"{BASE}/chintai/kanto/{pref_key}/list/"
    h = C.read_text(C.fetch(url, name=f"list_{pref_key}.html", subdir=OP, delay=DELAY, refresh=True))
    codes = {}
    for m in re.finditer(r'href="\.\./(\d+_\d+)\.html"[^>]*>(.*?)</a>', h, re.S):
        name = re.search(r'class="item_name[^"]*"[^>]*>(.*?)</span>', m.group(2), re.S)
        codes[m.group(1)] = _text(name.group(1) if name else m.group(2))
    if not codes:
        raise C.SourceError(f"団地一覧に詳細リンクが無い: {url}")
    return codes


def rows(h: str) -> dict[str, str]:
    """詳細ページの表（<th scope="row">見出し</th><td>…</td>）を {見出し: tdの中身(HTML)} に。"""
    out = {}
    for m in re.finditer(r'<th[^>]*scope="row"[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>', h, re.S):
        k = _text(m.group(1))
        if k and k not in out:
            out[k] = m.group(2)
    return out


def parse_detail(h: str, code: str, pref_key: str, pref: str, list_name: str, today: datetime.date) -> dict:
    r = rows(h)
    m = re.search(r'<h1 class="article_headings">.*?<span>(.*?)</span>\s*(?:<rt>(.*?)</rt>)?', h, re.S)
    name = _text(m.group(1)) if m else list_name
    kana = _text(m.group(2)) if m and m.group(2) else ""
    m = re.search(rf'href="/chintai/kanto/{pref_key}/area/\d+\.html"[^>]*>(.*?)</a>', h, re.S)
    city = _text(m.group(1)) if m else ""
    address = _h(_text(re.sub(r'<p class="arrangement_link.*', "", r.get("住所", ""), flags=re.S))).replace(" ", "")
    if address.startswith(pref):
        address = address[len(pref):]
    if city and not address.startswith(city):
        address = city + address  # 「千葉市美浜区…」のように市区が住所に無い形に備える
    # 家賃（<strong>家賃の幅</strong><span class="item_commonfee">(共益費)</span>）。共益費は含めない
    rent_html = r.get("家賃(共益費)", "")
    strong = re.search(r"<strong>(.*?)</strong>", rent_html, re.S)
    rent_min, rent_max = C.rent_range(_text(strong.group(1) if strong else re.sub(r'<span class="item_commonfee">.*?</span>', "", rent_html, flags=re.S)))
    fee = re.search(r'class="item_commonfee"[^>]*>(.*?)</span>', rent_html, re.S)
    fee_text = _text(fee.group(1)).strip("()（）") if fee else ""
    # 間取り/床面積 「1DK～3DK/30㎡～56㎡」
    la = _text(r.get("間取り/床面積", ""))
    layout, area_text = (la.split("/", 1) + [""])[:2] if "/" in la else (la, "")
    layout = _h(C.layout_norm(layout))
    area_text = _h(area_text).replace("㎡", "").replace("m2", "").strip()
    areas = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", area_text)]
    # 交通 <ul class="danchiaccess"><li>路線「駅名」駅 徒歩2～11分</li>…
    acc_html = r.get("交通", "")
    lines = [_text(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", acc_html, re.S)] or [_text(re.sub(r'<div class="trafficpdf">.*', "", acc_html, flags=re.S))]
    lines = [_h(x) for x in lines if x]
    access = " ／ ".join(lines)
    stations = []
    for x in lines:
        for st in re.findall(r"「(.+?)」\s*駅", x):
            st = st + "駅"
            if st not in stations:
                stations.append(st)
    # 徒歩分：バスの後の徒歩（「バス15分徒歩1分」）は除き、駅から直接歩ける一番短い分数。全部バスならバスの後の徒歩
    legs = re.findall(r"(バス\s*\d+\s*分\s*)?徒歩\s*(\d+)", access)
    walks = [int(w) for bus_leg, w in legs if not bus_leg] or [int(w) for _, w in legs]
    # 管理年数 「53年～54年」→ 一番古い棟のおおよその竣工年
    kanri = _text(r.get("管理年数", ""))
    years = [int(y) for y in re.findall(r"\d+", C.z2h(kanri))]
    built_from = today.year - max(years) if years else None
    built = f"管理{_h(kanri)}" if kanri else ""
    units_total = C.to_int(_text(r.get("戸数", "")))
    spec = " ".join(x for x in [
        f"総戸数{units_total:,}戸" if units_total else "", _text(r.get("構造", "")), f"共益費{_h(fee_text)}" if fee_text else "",
        f"読み{kana}" if kana else ""] if x)
    remarks = _text(r.get("備考", ""))
    return C.listing(
        id=f"{OP}-{code}", operator=OP, round_id=ROUND_ID, category="UR", subtype="先着順", name=name, pref=pref, city=city,
        address=address, access=access, stations=stations[:3], walk_min=min(walks) if walks else None, bus="バス" in access,
        persons="", single_ok=True, units=None, vacant_now=None, layout=layout, layouts=[layout] if layout else [],
        area_text=area_text, area_min=min(areas) if areas else None, area_max=max(areas) if areas else None,
        rent_min=rent_min, rent_max=rent_max, built=built, built_from=built_from, spec=spec,
        accident=remarks[:80], official_url=f"{BASE}/chintai/kanto/{pref_key}/{code}.html",
    )


def run(today: datetime.date):
    listings, notes, counts, failed = [], [], {}, []
    refresh_budget = REFRESH_PER_RUN
    now = time.time()
    for pref_key, pref in PREFS:
        codes = list_codes(pref_key)
        # 古い順に取り直す候補
        stale = []
        for code in codes:
            p = C.RAW / OP / f"{code}.html"
            if p.exists() and now - p.stat().st_mtime > REFRESH_DAYS * 86400:
                stale.append((p.stat().st_mtime, code))
        stale.sort()
        to_refresh = {c for _, c in stale[:refresh_budget]}
        refresh_budget -= len(to_refresh)
        n = 0
        for code, list_name in codes.items():
            url = f"{BASE}/chintai/kanto/{pref_key}/{code}.html"
            try:
                h = C.read_text(C.fetch(url, name=f"{code}.html", subdir=OP, delay=DELAY, refresh=code in to_refresh))
            except (urllib.error.URLError, C.SourceError, OSError) as e:
                failed.append(f"{pref}:{code}")
                C.log(f"ur: 詳細が読めない {url}: {type(e).__name__}: {e}")
                continue
            row = parse_detail(h, code, pref_key, pref, list_name, today)
            if not row["name"] or not row["address"]:
                failed.append(f"{pref}:{code}")
                C.log(f"ur: 名前か住所が読めない {url}")
                continue
            listings.append(row)
            n += 1
        counts[pref] = n
        if n == 0:
            raise C.SourceError(f"{pref} の団地が1件も読めなかった（一覧は{len(codes)}件）")
    notes.append("UR: 団地ごとの家賃の幅（共益費別・管理物件全体）。部屋ごとの空室・家賃は取らない（official_url で確認）")
    notes.append("UR: 都県別 " + "、".join(f"{k}{v}" for k, v in counts.items()))
    if failed:
        notes.append(f"UR: 読めなかった団地 {len(failed)}件: " + " ".join(failed[:10]))
    norent = sum(1 for r in listings if r["rent_min"] is None)
    if norent:
        notes.append(f"UR: 家賃の幅が読めない団地 {norent}件")
    return listings, [ROUND], {"expect_listings": True, "notes": notes}
