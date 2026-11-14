#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「前回の倍率」の静的ページを data/listings.json から作る（手書きの数字は入れない）。

使い方: python3 scripts/build_bairitsu.py
出るもの:
  bairitsu/index.html            都営・区市ごとの倍率一覧（当たりやすい順・高い順）と倍率の読み方
  bairitsu/<区市のローマ字>.html  区市ごとのページ（倍率のある団地が MIN_ROWS 件以上の区市だけ）
  sitemap.xml                    / と guide/*.html と bairitsu/*.html を載せ直す
数字の出どころは data/listings.json の ratio_prev（都営の募集案内に載っている「前回募集倍率」）。
データが更新されたら（月・木の自動更新のあと）このスクリプトを再実行する。
"""
from __future__ import annotations
import json, html, pathlib, statistics, datetime, re, glob

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "bairitsu"
SITE = "https://sumai.kachitori.com"
MIN_ROWS = 5          # 区市ページを作る最少件数（少なすぎる区市は一覧の表にだけ出す）
TOP_N = 20            # 都内全体の「低い団地」「高い団地」の件数
GA_ID = "G-RQX3SMF3CR"

# 東京都の区市町村 → URL に使うローマ字
ROMAJI = {
    "千代田区": "chiyoda", "中央区": "chuo", "港区": "minato", "新宿区": "shinjuku", "文京区": "bunkyo", "台東区": "taito",
    "墨田区": "sumida", "江東区": "koto", "品川区": "shinagawa", "目黒区": "meguro", "大田区": "ota", "世田谷区": "setagaya",
    "渋谷区": "shibuya", "中野区": "nakano", "杉並区": "suginami", "豊島区": "toshima", "北区": "kita", "荒川区": "arakawa",
    "板橋区": "itabashi", "練馬区": "nerima", "足立区": "adachi", "葛飾区": "katsushika", "江戸川区": "edogawa",
    "八王子市": "hachioji", "立川市": "tachikawa", "武蔵野市": "musashino", "三鷹市": "mitaka", "青梅市": "ome", "府中市": "fuchu",
    "昭島市": "akishima", "調布市": "chofu", "町田市": "machida", "小金井市": "koganei", "小平市": "kodaira", "日野市": "hino",
    "東村山市": "higashimurayama", "国分寺市": "kokubunji", "国立市": "kunitachi", "福生市": "fussa", "狛江市": "komae",
    "東大和市": "higashiyamato", "清瀬市": "kiyose", "東久留米市": "higashikurume", "武蔵村山市": "musashimurayama",
    "多摩市": "tama", "稲城市": "inagi", "羽村市": "hamura", "あきる野市": "akiruno", "西東京市": "nishitokyo",
    "瑞穂町": "mizuho", "日の出町": "hinode", "檜原村": "hinohara", "奥多摩町": "okutama",
}

esc = html.escape


def fmt_ratio(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v)}"


def pill(v: float) -> str:
    cls = "r1" if v <= 3 else "r2" if v <= 10 else "r3"
    return f'<span class="ratio-pill {cls}">{fmt_ratio(v)}倍</span>'


def yen(n) -> str:
    return "—" if n is None else f"{n:,}"


def head(title: str, desc: str, path: str, extra_ld: str = "") -> str:
    url = SITE + path
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:site_name" content="カチトリ住まい">
<meta property="og:locale" content="ja_JP">
<meta name="theme-color" content="#ffffff">
<!-- Google アナリティクス（カチトリ住まい {GA_ID}）。window.gtag は画面のスクリプトより先に作る -->
<script>window.dataLayer=window.dataLayer||[];window.gtag=function(){{dataLayer.push(arguments);}};gtag('js',new Date());gtag('config','{GA_ID}');</script>
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%23234e8c'/%3E%3Cpath d='M16 7l-9 7.5V25h6.5v-6h5v6H25V14.5z' fill='white'/%3E%3C/svg%3E">
<link rel="stylesheet" href="/css/app.css?v={VER}">
<link rel="stylesheet" href="/css/article.css?v={VER}">
{extra_ld}</head>
<body class="article">
<div class="wrap">
  <header class="site-head">
    <a class="brand" href="/"><i aria-hidden="true"></i>カチトリ住まい</a>
    <a class="to-map" href="/">地図で募集を見る ›</a>
  </header>
"""


FOOT = """
  <footer class="site-foot">
    <p>カチトリ住まいは、都営・県営・市営・公社・UR の募集を地図とカレンダーでまとめて探せる非公式のサービスです。運営：カチトリ（<a href="https://kachitori.com/" target="_blank" rel="noopener">カチトリの履歴書</a>と同じ運営）<br>
    <a href="https://kachitori.com/company" target="_blank" rel="noopener">運営者情報</a>　<a href="https://kachitori.com/privacypolicy" target="_blank" rel="noopener">プライバシーポリシー</a>　<a href="https://kachitori.com/contact" target="_blank" rel="noopener">お問い合わせ</a></p>
  </footer>
</div>
<script src="/js/cards.js?v={VER}"></script>
</body>
</html>
"""


def cards_block(city: str) -> str:
    return f"""
    <section class="pick-sec">
      <p class="cards-h">落選したら、今すぐ入れる家<span class="pr">PR</span></p>
      <div class="cards pick-cards" data-kinds="ur,rent" data-pref="東京都" data-city="{esc(city)}"></div>
      <p class="hint">この枠には広告（PR）を含みます。リンク先で申し込みがあると、このサービスに紹介料が入ることがあります。UR のカードは UR都市機構の公式サイトへのリンクで、広告ではありません。</p>
    </section>"""


def line_block() -> str:
    return '<div class="line-cta article"><span><b>LINE</b>で「募集が始まった」「締切3日前」を受け取る</span><a class="line-btn" data-line href="#">友だち追加</a></div>'


def sources_block(official_urls: list[str], data_date: str, round_label: str) -> str:
    lis = "".join(f'<li>東京都住宅供給公社「{esc(round_label)}」 <a href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a></li>' for u in official_urls)
    return f"""
    <section class="sources">
      <h2>出どころ</h2>
      <ul>{lis}
        <li>倍率の数字は、上の募集の募集案内に載っている各住宅の「前回募集倍率」を、カチトリ住まいが読み取ったものです（データ {esc(data_date)} 時点）。読み取りの誤りがあるかもしれません。申し込む前に募集案内の原本で確かめてください。</li>
      </ul>
    </section>"""


def reading_block() -> str:
    return """
    <h2>倍率の読み方（3つだけ）</h2>
    <ol>
      <li><b>倍率＝申し込んだ人の数÷募集した戸数</b>。10倍なら、1戸に10人が申し込んだということです。1倍以下なら、申し込んだ人がほぼ全員当たった回です。</li>
      <li><b>「前回」の数字です</b>。同じ団地でも、募集のたびに倍率は変わります。次の募集で同じになるとは限りません。予想ではなく、過去の事実として見てください。</li>
      <li><b>同じ区でも団地で差が大きい</b>。区の中央値だけで決めず、団地ごとの表を見てください。</li>
    </ol>"""


def build():
    data = json.loads((ROOT / "data" / "listings.json").read_text(encoding="utf-8"))
    rounds = json.loads((ROOT / "data" / "rounds.json").read_text(encoding="utf-8"))
    site = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))
    global VER
    VER = re.sub(r"[^0-9a-z]", "", site.get("version", ""))   # 2026-11-14b → 20261114b（index.html の ?v= と同じ）
    data_date = data.get("generated_at") or datetime.date.today().isoformat()
    toei_all = [r for r in data["items"] if r.get("operator") == "toei"]
    rows = [r for r in toei_all if isinstance(r.get("ratio_prev"), (int, float)) and r["ratio_prev"] > 0]
    round_ids = sorted({r["round_id"] for r in toei_all})
    round_label = "・".join(rd["label"] for rd in rounds["rounds"] if rd["id"] in round_ids) or "都営住宅 定期募集"
    official_urls = sorted({r["official_url"] for r in rows if r.get("official_url")})
    today = datetime.date.today().isoformat()

    by_city: dict[str, list] = {}
    for r in rows:
        by_city.setdefault(r["city"], []).append(r)
    stats = []
    for city, rs in by_city.items():
        vals = [r["ratio_prev"] for r in rs]
        stats.append(dict(city=city, n=len(rs), med=statistics.median(vals), lo=min(vals), hi=max(vals),
                          slug=ROMAJI.get(city), page=(len(rs) >= MIN_ROWS and city in ROMAJI)))
    missing = [s["city"] for s in stats if s["slug"] is None]
    if missing:
        print("ローマ字が未登録（ページを作らず一覧だけ）:", missing)
    asc = sorted(stats, key=lambda s: (s["med"], s["lo"]))
    desc = sorted(stats, key=lambda s: (-s["med"], -s["hi"]))
    all_vals = [r["ratio_prev"] for r in rows]
    overall_med = statistics.median(all_vals)

    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.html"):
        old.unlink()

    def city_link(s):
        return f'<a href="/bairitsu/{s["slug"]}.html">{esc(s["city"])}</a>' if s["page"] else esc(s["city"])

    def city_table(order, me=None):
        trs = []
        for s in order:
            trs.append(f'<tr{" class=me" if s["city"] == me else ""}><td class="wrap">{city_link(s)}</td><td class="num">{s["n"]}</td><td class="num">{pill(s["med"])}</td><td class="num">{fmt_ratio(s["lo"])}倍</td><td class="num">{fmt_ratio(s["hi"])}倍</td></tr>')
        return f"""<div class="tbl-wrap"><table class="tbl">
      <thead><tr><th>区・市</th><th class="num">件数</th><th class="num">倍率の中央値</th><th class="num">最低</th><th class="num">最高</th></tr></thead>
      <tbody>{"".join(trs)}</tbody></table></div>"""

    def listing_table(rs, with_city=False):
        trs = []
        for r in rs:
            name = esc(r["name"]) + (f'<br><small style="color:var(--ink-3)">{esc(r["city"])}</small>' if with_city else "")
            cat = esc((r.get("category") or "").replace("住宅", ""))
            trs.append(f'<tr><td class="wrap">{name}</td><td class="wrap"><small>{cat}</small></td><td class="wrap">{esc(r.get("layout") or "—")}{(" " + esc(r["area_text"]) + "㎡") if r.get("area_text") else ""}</td><td class="num">¥{yen(r.get("rent_min"))}〜</td><td class="num">{r["units"] if r.get("units") is not None else "—"}</td><td class="num">{pill(r["ratio_prev"])}</td></tr>')
        return f"""<div class="tbl-wrap"><table class="tbl">
      <thead><tr><th>団地</th><th>区分</th><th>間取り・広さ</th><th class="num">家賃（月）</th><th class="num">戸数</th><th class="num">前回の倍率</th></tr></thead>
      <tbody>{"".join(trs)}</tbody></table></div>"""

    chip_row = '<div class="chip-row">' + "".join(f'<a href="/bairitsu/{s["slug"]}.html">{esc(s["city"])}</a>' for s in sorted(stats, key=lambda s: -s["n"]) if s["page"]) + "</div>"

    # ---- 一覧ページ ----
    title = "都営住宅の倍率｜区・市ごとの「前回の倍率」一覧と、当たりやすい団地の見つけ方"
    desc_txt = f"都営住宅の「前回の倍率」を区・市ごとにまとめました（{round_label}の募集案内より、{len(rows)}件）。倍率の低い順・高い順、団地ごとの一覧、倍率の読み方。地図から今の募集にそのまま進めます。"
    low = sorted(rows, key=lambda r: (r["ratio_prev"], -(r.get("units") or 0)))[:TOP_N]
    high = sorted(rows, key=lambda r: (-r["ratio_prev"], -(r.get("units") or 0)))[:TOP_N]
    ld = json.dumps({"@context": "https://schema.org", "@type": "Dataset", "name": title, "description": desc_txt, "url": SITE + "/bairitsu/",
                     "dateModified": data_date, "creator": {"@type": "Organization", "name": "カチトリ住まい"},
                     "isBasedOn": official_urls}, ensure_ascii=False)
    h = head(title, desc_txt, "/bairitsu/", f'<script type="application/ld+json">{ld}</script>\n')
    h += f"""  <p class="crumb"><a href="/">カチトリ住まい</a> › 前回の倍率</p>
  <p class="pr-note">※このページにはプロモーション（広告）が含まれます</p>
  <div class="sheet">
    <h1>都営住宅の倍率｜区・市ごとの「前回の倍率」一覧</h1>
    <p class="meta">データ {esc(data_date)} 時点 ／ 出どころ：{esc(round_label)}の募集案内（ページ末尾）</p>
    <div class="lead">
      <p>「どこなら当たりやすいの？」。都営住宅の申し込みで、いちばん多い迷いです。</p>
      <p>答えは「団地ごとに大きく違う」です。このページでは、{esc(round_label)}の募集案内に載っている<b>各団地の「前回の倍率」{len(rows)}件</b>を、区・市ごとにまとめました。都内全体の中央値は <b>{fmt_ratio(overall_med)}倍</b>です。</p>
    </div>
    <ul class="summary">
      <li>倍率が低い区・市から順に並べた表（中央値）。区・市の名前を押すと、団地ごとの表に進めます</li>
      <li>都内全体で倍率が低かった団地・高かった団地、それぞれ{TOP_N}件</li>
      <li>数字は「前回」の結果。次の募集で同じになるとは限りません</li>
    </ul>
    <div class="map-cta">
      <a class="btn" href="/">地図で今の募集を見る</a>
      <a class="btn ghost" href="/guide/toei-moushikomi.html">申し込み方（はじめての人向け）</a>
    </div>

    <h2>区・市ごとの倍率（低い順）</h2>
    <p>中央値は「真ん中の団地の倍率」です。極端に高い団地が1つあっても引っ張られません。</p>
    {city_table(asc)}
    <p class="hint">件数は、倍率の数字がある団地（住戸区分）の数です。倍率の無い団地（前回募集が無かったなど）は数えていません。</p>

    <h2>倍率が高い区・市（上位10）</h2>
    {city_table(desc[:10])}

    <h2>都内で倍率が低かった団地（{TOP_N}件）</h2>
    <p>当たりやすかった団地です。駅からの距離や築年と合わせて見てください。</p>
    {listing_table(low, with_city=True)}

    <h2>都内で倍率が高かった団地（{TOP_N}件）</h2>
    {listing_table(high, with_city=True)}
    {reading_block()}
    {cards_block("")}
    {line_block()}

    <h2>区・市ごとのページ</h2>
    {chip_row}
    <p class="hint">倍率のある団地が{MIN_ROWS}件以上の区・市だけページがあります。ほかの区・市は上の表で見てください。</p>
    <div class="map-cta">
      <a class="btn" href="/">地図で今の募集を見る</a>
      <a class="btn ghost" href="/guide/toei-moushikomi.html">申し込み方（はじめての人向け）</a>
    </div>
    {sources_block(official_urls, data_date, round_label)}
  </div>
"""
    h += FOOT.replace("{VER}", VER)
    (OUT / "index.html").write_text(h, encoding="utf-8")

    # ---- 区・市ごとのページ ----
    made = []
    for s in asc:
        if not s["page"]:
            continue
        city = s["city"]
        rs = sorted(by_city[city], key=lambda r: (r["ratio_prev"], -(r.get("units") or 0)))
        rank = asc.index(s) + 1
        title = f"{city}の都営住宅 前回の倍率｜団地ごとの一覧（低い順）と当たりやすさ"
        desc_txt = f"{city}の都営住宅の「前回の倍率」を団地ごとに一覧にしました（{round_label}の募集案内より、{s['n']}件）。中央値{fmt_ratio(s['med'])}倍、最低{fmt_ratio(s['lo'])}倍〜最高{fmt_ratio(s['hi'])}倍。地図で{city}の今の募集にそのまま進めます。"
        path = f"/bairitsu/{s['slug']}.html"
        ld = json.dumps({"@context": "https://schema.org", "@type": "Dataset", "name": title, "description": desc_txt, "url": SITE + path,
                         "dateModified": data_date, "creator": {"@type": "Organization", "name": "カチトリ住まい"}, "isBasedOn": official_urls}, ensure_ascii=False)
        ones = sum(1 for r in rs if r["ratio_prev"] <= 1)
        under3 = sum(1 for r in rs if r["ratio_prev"] <= 3)
        h = head(title, desc_txt, path, f'<script type="application/ld+json">{ld}</script>\n')
        h += f"""  <p class="crumb"><a href="/">カチトリ住まい</a> › <a href="/bairitsu/">前回の倍率</a> › {esc(city)}</p>
  <p class="pr-note">※このページにはプロモーション（広告）が含まれます</p>
  <div class="sheet">
    <h1>{esc(city)}の都営住宅 前回の倍率｜団地ごとの一覧</h1>
    <p class="meta">データ {esc(data_date)} 時点 ／ 出どころ：{esc(round_label)}の募集案内（ページ末尾）</p>
    <div class="lead">
      <p>{esc(city)}の都営住宅で、倍率の数字がある団地（住戸区分）は <b>{s['n']}件</b>。倍率の中央値は <b>{fmt_ratio(s['med'])}倍</b>（最低 {fmt_ratio(s['lo'])}倍 〜 最高 {fmt_ratio(s['hi'])}倍）。倍率の数字がある{len(stats)}の区・市の中で、中央値が低い方から <b>{rank}番目</b>です。</p>
      <p>{s['n']}件のうち、1倍以下（申し込んだ人がほぼ当たった）は {ones}件、3倍以下は {under3}件でした。</p>
    </div>
    <div class="map-cta">
      <a class="btn" href="/?city={esc(city)}">地図で{esc(city)}の今の募集を見る</a>
      <a class="btn ghost" href="/guide/toei-moushikomi.html">申し込み方（はじめての人向け）</a>
    </div>

    <h2>{esc(city)}の団地ごとの前回の倍率（低い順）</h2>
    {listing_table(rs)}
    <p class="hint">家賃は一番安い額です（世帯の収入で変わります）。戸数は今回の募集戸数、倍率は前回の募集のものです。</p>
    {reading_block()}
    {cards_block(city)}
    {line_block()}

    <h2>ほかの区・市と比べる</h2>
    {city_table(asc, me=city)}
    <div class="map-cta">
      <a class="btn" href="/?city={esc(city)}">地図で{esc(city)}の今の募集を見る</a>
      <a class="btn ghost" href="/bairitsu/">区・市ごとの一覧に戻る</a>
    </div>
    {sources_block(official_urls, data_date, round_label)}
  </div>
"""
        h += FOOT.replace("{VER}", VER)
        (OUT / f"{s['slug']}.html").write_text(h, encoding="utf-8")
        made.append(path)

    # ---- sitemap.xml ----
    urls = [("/", today, "daily")]
    for p in sorted(glob.glob(str(ROOT / "guide" / "*.html"))):
        urls.append(("/guide/" + pathlib.Path(p).name, today, "monthly"))
    urls.append(("/bairitsu/", today, "weekly"))
    urls += [(p, today, "weekly") for p in made]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, freq in urls:
        sm.append(f"  <url>\n    <loc>{SITE}{esc(loc)}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>{freq}</changefreq>\n  </url>")
    sm.append("</urlset>\n")
    (ROOT / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")

    print(f"都営 {len(toei_all)}件のうち倍率あり {len(rows)}件／区・市 {len(stats)}（ページを作った {len(made)}）／全体の中央値 {fmt_ratio(overall_med)}倍")
    print("sitemap.xml:", len(urls), "URL")


if __name__ == "__main__":
    build()
