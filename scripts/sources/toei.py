"""都営住宅（JKK東京）定期募集：募集ページを自動で見つけ、「申込地区一覧」PDFを読む。
入口: https://www.to-kousya.or.jp/kouei/toeibosyu/index_teiki.html （年4回：2・5・8・11月）
- index から teiki_YYYY_M.html の一番新しいものを選ぶ
- 募集ページの「申込期間：令和8年11月2日から17日まで」と「募集戸数」表を読む
- *_dl.html → 「申込地区一覧」PDF を取り、toei_pdf.parse_pdf で読む（toei-housing-map から移植）
- 申込期間が終わっていれば物件は出さない（募集の予定だけ返す）
"""
from __future__ import annotations
import re, datetime, html as htmllib, urllib.parse
from . import common as C
from . import toei_pdf as T

OP = "toei"
INDEX = "https://www.to-kousya.or.jp/kouei/toeibosyu/index_teiki.html"
CAT = {T.CAT_GENERAL: "世帯向", T.CAT_YOUNG: "若年夫婦・子育て", T.CAT_DEATH: "病死等があった住宅"}


def links(html_text: str, base: str):
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.S):
        label = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        yield urllib.parse.urljoin(base, m.group(1)), label


def strip_comments(t: str) -> str:
    return re.sub(r"<!--.*?-->", "", t, flags=re.S)


def latest_round_url(index_html: str) -> tuple[str, int, int] | None:
    found = []
    for u, _ in links(strip_comments(index_html), INDEX):
        m = re.search(r"/teiki_(\d{4})_(\d{1,2})\.html$", u)
        if m:
            found.append(((int(m.group(1)), int(m.group(2))), u))
    if not found:
        return None
    (y, mo), u = max(found)
    return u, y, mo


def application_period(page_html: str) -> dict:
    t = T.nfkc(re.sub(r"<[^>]+>", " ", strip_comments(page_html)))
    m = re.search(r"申込期間\s*[:：]?\s*令和\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日\s*(?:\([^)]*\)\s*)?(?:から|〜)\s*(?:令和\s*\d+\s*年\s*)?(?:(\d+)\s*月\s*)?(\d+)\s*日", t)
    if not m:
        return {}
    y, mo = 2018 + int(m.group(1)), int(m.group(2))
    mo2 = int(m.group(4) or mo)
    y2 = y + (1 if mo2 < mo else 0)
    return {"start": f"{y}-{mo:02d}-{int(m.group(3)):02d}", "end": f"{y2}-{mo2:02d}-{int(m.group(5)):02d}"}


def official_totals(page_html: str) -> dict:
    d = {}
    for m in re.finditer(r"<td>([^<]+?)</td>\s*<td>([\d,]+)戸</td>", strip_comments(page_html)):
        d[T.canon(m.group(1).strip())] = int(m.group(2).replace(",", ""))
    return d


def run(today: datetime.date):
    notes = []
    index_html = C.read_text(C.fetch(INDEX, subdir=OP, refresh=True))
    hit = latest_round_url(index_html)
    if not hit:
        raise C.SourceError("定期募集の一覧ページに teiki_YYYY_M.html のリンクが無い")
    url, y, mo = hit
    rid = f"{OP}-{y}-{mo:02d}"
    page_html = C.read_text(C.fetch(url, subdir=OP, name=url.rsplit("/", 1)[-1], refresh=True))
    per = application_period(page_html)
    totals = official_totals(page_html)
    rd = {"id": rid, "operator": OP, "label": f"都営住宅 {y}年{mo}月 定期募集", "kind": "抽せん方式（家族向・単身者向等）" if mo != 2 else "家族向（ポイント方式）・単身者向（抽せん）",
          "apply_from": per.get("start"), "apply_to": per.get("end"), "units": sum(totals.values()) or None, "url": url, "note": ""}
    if not per:
        notes.append(f"都営: {url} に申込期間が見つからない（日付なしで出す）")
        rd["expected"] = f"{y}年{mo}月"
    if per and per["end"] < today.isoformat():
        notes.append(f"都営: {rd['label']} は {per['end']} に終了。次の募集ページが出るまで物件なし")
        return [], [rd], {"expect_listings": False, "notes": notes}

    # ダウンロードページ → 申込地区一覧PDF
    dl_pages = []
    for u, _ in links(strip_comments(page_html), url):
        if re.search(r"_dl\.html$", u) and u not in dl_pages:
            dl_pages.append(u)
    manifest = []
    for page in dl_pages:
        ph = C.read_text(C.fetch(page, subdir=OP, name=page.rsplit("/", 1)[-1], refresh=True))
        for u, label in links(strip_comments(ph), page):
            if u.lower().endswith(".pdf") and "申込地区一覧" in label:
                path = C.fetch(u, subdir=OP, name=u.rsplit("/", 1)[-1])
                manifest.append({"label": label, "url": u, "path": path})
    if not manifest:
        raise C.SourceError(f"申込地区一覧のPDFが見つからない: {url}（dl ページ {len(dl_pages)}）")

    recs = []
    for m in manifest:
        recs += T.parse_pdf(m["path"], m["url"])
    recs.sort(key=lambda r: r["id"])
    _, ok, probs = T.validate(recs, totals)
    if not ok:
        got = {CAT.get(k, k): sum(r["units"] or 0 for r in recs if r["category"] == k) for k in totals}
        notes.append(f"都営: 戸数が公式発表と不一致 公式={ {CAT.get(k, k): v for k, v in totals.items()} } 読み取り={got}")
    if probs:
        notes.append(f"都営: 項目の欠け・異常 {len(probs)} 件（例: {probs[0]}）")

    out = []
    for r in recs:
        out.append(C.listing(
            id=f"{OP}-{r['id']}", operator=OP, round_id=rid, category=CAT.get(r["category"], r["category"]), subtype=r.get("subtype") or "",
            name=r["name"], pref="東京都", city=r["ward"], address=r["address"],
            access=r.get("access", ""), stations=r.get("stations") or [], walk_min=r.get("walk_min"), bus=bool(r.get("bus")),
            persons=r.get("persons", ""), units=r.get("units"), vacant_now=r.get("vacant_now"), layout=r.get("layout", ""),
            layouts=r.get("layouts") or [], area_text=r.get("area_text", ""), area_min=r.get("area_min"), area_max=r.get("area_max"),
            rent_min=r.get("rent_min"), rent_max=r.get("rent_max"), built=r.get("built", ""), built_from=r.get("built_from"),
            elevator=(r.get("elevator") == "有"), barrier_free="バリアフリー" in (r.get("spec") or ""), spec=r.get("spec", ""),
            floor=r.get("floor", ""), accident=r.get("accident", ""), ratio_prev=C.to_float(r.get("ratio_prev")),
            priority_lottery=bool(r.get("priority_lottery")), official_url=url,
            pdf_url=f"{r['pdf_url']}#page={r['pdf_page_index']}" if r.get("pdf_url") else "", pdf_page=r.get("page", ""),
        ))
    return out, [rd], {"expect_listings": True, "notes": notes}
