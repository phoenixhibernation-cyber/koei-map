"""都営住宅 申込地区一覧PDFの読み取り（toei-housing-map/scripts/build.py から移植。読み取り部分だけ。取得・位置情報は common.py）"""
from __future__ import annotations
import re, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
import pdfplumber

CAT_GENERAL = "世帯向（一般募集住宅）"
CAT_YOUNG = "若年夫婦・子育て世帯向（定期使用住宅）"
CAT_DEATH = "居室内で病死等があった住宅"


def nfkc(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return s.replace("~", "〜").replace("～", "〜").replace("−", "-")


def to_int(s: str):
    s = nfkc(s).replace(",", "")
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


ERA = {"昭和": 1925, "平成": 1988, "令和": 2018}


def era_to_year(s: str):
    m = re.match(r"(昭和|平成|令和)(元|\d+)", s)
    if not m:
        return None
    n = 1 if m.group(2) == "元" else int(m.group(2))
    return ERA[m.group(1)] + n


HEADER_WORDS = {"入居", "申込", "人数", "地区番号", "住宅名（代表的な所在地）", "主な交通機関", "募集", "戸数",
                "間取り", "専用面積", "（㎡）", "建設年度", "エレベーター", "使用料", "（円）", "仕様等", "参考",
                "倍率", "住宅名", "（所在地）交通機関", "専用面積（㎡）", "事故内容", "対象階"}
LAYOUT = re.compile(r"^(\d?[SLDK]+|\d+[SLDK]+(・\d+[SLDK]+)*|\d[A-Z・\d]*K)$")


def page_category(words, text_top: str):
    if "病死" in text_top:
        return CAT_DEATH, ""
    if "若年夫婦" in text_top or "定期使用" in text_top:
        return CAT_YOUNG, ""
    sub = "改良住宅" if "改良住宅" in text_top else "再開発住宅" if "再開発住宅" in text_top else "一般"
    return CAT_GENERAL, sub


def parse_pdf(path: Path, source_url: str) -> list[dict]:
    recs = []
    ward = None
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages):
            raw_words = page.extract_words(extra_attrs=["size"], keep_blank_chars=False)
            # 同じ文字が重ねて埋め込まれている箇所があるので重複を除く
            words, by_text = [], defaultdict(list)
            for w in raw_words:
                if not any(abs(v["x0"] - w["x0"]) < 2.5 and abs(v["top"] - w["top"]) < 2.5 for v in by_text[w["text"]]):
                    by_text[w["text"]].append(w)
                    words.append(w)
            if not words:
                continue
            # 「申込地区一覧の見方」の記入例ページは除外
            if any("見方" in w["text"] or "【例】" in w["text"] for w in words):
                continue
            top_text = "".join(w["text"] for w in words if w["top"] < 80)
            # ページ番号（下端の数字）
            pno = next((w["text"] for w in words if w["top"] > 800 and re.fullmatch(r"\d+", w["text"])), None)
            # 表の見出し行（「地区番号」の位置）
            heads = [w for w in words if w["text"] == "地区番号"]
            anchors = [w for w in words if re.fullmatch(r"\d{5}", w["text"]) and w["size"] > 11.5]
            if not heads or not anchors:
                continue
            cat, sub = page_category(words, top_text)
            # 見出し語の位置から列の境界を求める（ページごとに左右のずれがあるため）
            hdr_tops = sorted({round(h["top"]) for h in heads})
            ref = [w for w in words if abs(w["top"] - heads[0]["top"]) < 16 and w["size"] < 9]
            def hx(name):
                c = [w for w in ref if w["text"] == name]
                return (c[0]["x0"] + c[0]["x1"]) / 2 if c else None
            cx = {k: hx(k) for k in ["入居", "地区番号", "募集", "間取り", "建設年度", "使用料", "仕様等", "参考", "事故内容"]}
            if cx["間取り"] is None:
                cx["間取り"] = hx("専用面積（㎡）")
            # 列境界
            b_name_l = cx["地区番号"] + 22
            b_cnt = cx["募集"] - 12
            b_lay = (cx["募集"] + cx["間取り"]) / 2
            b_year = (cx["間取り"] + cx["建設年度"]) / 2 + 2
            b_rent = (cx["建設年度"] + cx["使用料"]) / 2
            if cat == CAT_DEATH:
                b_acc = (cx["使用料"] + cx["事故内容"]) / 2
                b_spec = (cx["事故内容"] + cx["仕様等"]) / 2 - 4
                b_ratio = 9999
            else:
                b_acc = None
                b_spec = (cx["使用料"] + cx["仕様等"]) / 2
                b_ratio = (cx["仕様等"] + cx["参考"]) / 2 + 12 if cx["参考"] else 9999

            # 除外: 見出し行・上部注意書き・ページ番号・余白の縦書き
            def is_noise(w):
                if w["top"] < 75 or w["top"] > 800:
                    return True
                if w["x0"] < 25 or w["x0"] > 565:
                    return True
                for ht in hdr_tops:
                    if ht - 12 <= w["top"] <= ht + 9 and (w["text"] in HEADER_WORDS or w["size"] < 9):
                        return True
                return False

            # 区市町村見出し（大きめの文字、左側）
            ward_heads = [w for w in words if 11 <= w["size"] <= 11.6 and w["x0"] < 200
                          and re.search(r"(区|市|町|村)(（.+）)?$", w["text"])]
            body = [w for w in words if not is_noise(w) and w not in ward_heads]
            anchors.sort(key=lambda w: w["top"])
            # 区切り: 次の団地番号の16pt上 / 次の見出し
            def rec_start(a, prev):
                # 団地名（やや大きい文字）が番号の上にある。交通が3行あると20pt近く離れる
                nm = [w for w in body if 9.5 < w["size"] < 11 and b_name_l <= w["x0"] < b_cnt
                      and a["top"] - 26 <= w["top"] <= a["top"] + 1
                      and (prev is None or w["top"] > prev["top"] + 12)]
                t = min([a["top"] - 16] + [w["top"] for w in nm]) - 3
                return max(t, prev["top"] + 12) if prev else t
            starts = [rec_start(a, anchors[i - 1] if i else None) for i, a in enumerate(anchors)]
            cuts = sorted(starts + [t - 14 for t in hdr_tops] + [w["top"] - 2 for w in ward_heads] + [9999])
            cells, wards_of = [], []
            for a, start in zip(anchors, starts):
                end = min(c for c in cuts if c > start + 1)
                # 区市町村: 直前の見出し
                wh = [w for w in ward_heads if w["top"] < a["top"]]
                if wh:
                    ward = max(wh, key=lambda w: w["top"])["text"]
                cell = defaultdict(list)
                for w in body:
                    if w is a or not (start <= w["top"] < end):
                        continue
                    xc = (w["x0"] + w["x1"]) / 2
                    if w["x1"] <= b_name_l - 18 or (w["x0"] < b_name_l - 8 and w["size"] > 10):
                        col = "people"
                    elif w["x0"] < b_name_l and xc < b_name_l:
                        col = "people2"  # 優遇あり
                    elif xc < b_cnt:
                        col = "name"
                    elif xc < b_lay:
                        col = "count"
                    elif xc < b_year:
                        col = "layout"
                    elif xc < b_rent:
                        col = "year"
                    elif b_acc and xc < b_acc:
                        col = "rent"
                    elif b_acc and xc < b_spec:
                        col = "accident"
                    elif not b_acc and xc < b_spec:
                        col = "rent"
                    elif xc < b_ratio:
                        col = "spec"
                    else:
                        col = "ratio"
                    if col != "spec":
                        cell[col].append(w)
                cells.append(cell)
                wards_of.append(ward)
            # 仕様等: 行のかたまりごとに、縦方向の中心が一番近い団地へ割り当てる
            spec_ws = sorted([w for w in body if b_spec <= (w["x0"] + w["x1"]) / 2 < b_ratio
                              and w["top"] >= starts[0] - 20], key=lambda w: w["top"])
            blocks = []
            for w in spec_ws:
                if blocks and w["top"] - blocks[-1][-1]["top"] <= 12.5:
                    blocks[-1].append(w)
                else:
                    blocks.append([w])
            sect = lambda y: sum(1 for t in hdr_tops if t < y)
            for blk in blocks:
                cy = (blk[0]["top"] + blk[-1]["top"]) / 2
                cand = [i for i, a in enumerate(anchors) if sect(a["top"]) == sect(cy)]
                if not cand:
                    continue
                i = min(cand, key=lambda i: abs(anchors[i]["top"] + 4 - cy))
                cells[i]["spec"] += blk
            for a, cell, wd in zip(anchors, cells, wards_of):
                recs.append(build_record(a, cell, cat, sub, wd, pno, pi + 1, path.name, source_url))
    return recs


def lines_text(ws, sep=""):
    ws = sorted(ws, key=lambda w: (round(w["top"] / 4), w["x0"]))
    return sep.join(w["text"] for w in ws)


def build_record(a, cell, cat, sub, ward, pno, pidx, fname, url):
    wm0 = re.match(r"^(.+?)(?:（(.+)）)?$", ward or "")
    r = {"id": a["text"], "category": cat, "subtype": sub,
         "ward": wm0.group(1) if wm0 else ward, "ward_area": (wm0.group(2) or "") if wm0 else ""}
    # 入居人数・優遇
    ppl = [w for w in cell["people"] + cell["people2"]]
    yuu = any("優遇" in w["text"] for w in ppl)
    r["persons"] = nfkc("".join(w["text"] for w in sorted(ppl, key=lambda w: w["top"]) if "優遇" not in w["text"]))
    r["priority_lottery"] = yuu
    # 住宅名・所在地・交通
    nm = cell["name"]
    names = [w for w in nm if w["size"] > 9.5]
    others = [w for w in nm if w["size"] <= 9.5]
    r["name"] = nfkc("".join(w["text"] for w in sorted(names, key=lambda w: (w["top"], w["x0"]))))
    txt = lines_text(others)
    m = re.search(r"（([^）]+)）", txt)
    r["address"] = nfkc(m.group(1)) if m else ""
    traffic = (txt[:m.start()] + txt[m.end():]) if m else txt
    traffic = fix_traffic(traffic)
    r["access"] = traffic
    st = re.findall(r"「([^」]+?駅)」", traffic)
    r["stations"] = list(dict.fromkeys(st))
    r["station"] = st[0] if st else ""
    wm = re.search(r"徒歩\s*(\d+)\s*分", nfkc(traffic))
    r["walk_min"] = int(wm.group(1)) if wm else None
    r["bus"] = "バス" in traffic
    # 戸数
    cnt = [nfkc(w["text"]) for w in sorted(cell["count"], key=lambda w: w["top"])]
    total = [c for c in cnt if re.fullmatch(r"\d+", c)]
    vac = [c for c in cnt if re.fullmatch(r"\(\d+\)", c)]
    r["units"] = int(total[0]) if total else None
    r["vacant_now"] = int(vac[0].strip("()")) if vac else None
    # 間取り・面積
    lay = [nfkc(w["text"]) for w in sorted(cell["layout"], key=lambda w: w["top"])]
    r["layout"] = "".join(x for x in lay if re.search(r"[KDLS]", x)).replace(" ", "")
    r["layouts"] = [x for x in r["layout"].split("・") if x]
    areas = [x for x in lay if re.fullmatch(r"[\d.]+(〜[\d.]+)?", x)]
    r["area_text"] = areas[0] if areas else ""
    nums = [float(v) for v in re.findall(r"[\d.]+", r["area_text"])]
    r["area_min"], r["area_max"] = (min(nums), max(nums)) if nums else (None, None)
    # 建設年度・EV・対象階
    yr = [nfkc(w["text"]) for w in sorted(cell["year"], key=lambda w: (w["top"], w["x0"]))]
    r["elevator"] = "有" if "有" in yr else "無" if "無" in yr else ""
    fl = [x for x in yr if x.endswith("階")]
    r["floor"] = fl[0] if fl else ""
    ytxt = "".join(x for x in yr if x not in ("有", "無") and not x.endswith("階"))
    r["built"] = ytxt
    ys = [era_to_year(m.group()) for m in re.finditer(r"(昭和|平成|令和)(元|\d+)", ytxt)]
    r["built_from"] = min(ys) if ys else None
    r["built_to"] = max(ys) if ys else None
    # 使用料
    rent = "".join(nfkc(w["text"]) for w in sorted(cell["rent"], key=lambda w: (w["top"], w["x0"])))
    rv = [int(v.replace(",", "")) for v in re.findall(r"\d{1,3}(?:,\d{3})+", rent)]
    r["rent_min"] = min(rv) if rv else None
    r["rent_max"] = max(rv) if rv else None
    # 仕様等・倍率・事故内容
    sp = nfkc(lines_text(cell["spec"]))
    sp = re.sub(r"(バリアフリー仕様|スーパーリフォーム\([^)]*\))(?=\S)(?!です)", r"\1／", sp)
    r["spec"] = sp
    rt = nfkc(lines_text(cell["ratio"]))
    r["ratio_prev"] = rt if rt and rt not in ("-", "ー", "−") else ""
    if cat == CAT_DEATH:
        r["accident"] = nfkc(lines_text(cell["accident"], " "))
    r["page"] = pno
    r["pdf"] = fname
    r["pdf_page_index"] = pidx
    r["pdf_url"] = url
    return r


def fix_traffic(t: str) -> str:
    t = nfkc(t).replace(" ", "")
    # 「◯◯駅」がレイアウトの都合で「下車徒歩」の後ろに回る場合を直す
    m = re.match(r"^(.*?)(下車徒歩\d+分(?:ほか)?)(「[^」]+」)(.*)$", t)
    if m and "「" not in m.group(1)[-12:]:
        t = m.group(1) + m.group(3) + m.group(2) + m.group(4)
    m = re.match(r"^(.*?)(下車徒歩)(「[^」]+」)(\d+分.*)$", t)
    if m:
        t = m.group(1) + m.group(3) + m.group(2) + m.group(4)
    return t


# ---------------------------------------------------------------- 3. 検証
def validate(recs, expected: dict) -> list[str]:
    out = []
    tot = Counter()
    for r in recs:
        tot[r["category"]] += r["units"] or 0
    out.append("## 戸数の照合\n")
    out.append("| 募集区分 | 読み取り地区数 | 読み取り戸数 | 公式発表 | 判定 |\n|---|---|---|---|---|")
    ok_all = True
    for cat in [CAT_GENERAL, CAT_YOUNG, CAT_DEATH]:
        n = sum(1 for r in recs if r["category"] == cat)
        exp = expected.get(cat)
        ok = exp is None or exp == tot[cat]
        ok_all &= ok
        out.append(f"| {cat} | {n} | {tot[cat]:,} | {f"{exp:,}" if exp is not None else "-"} | {'一致' if ok else '不一致'} |")
    out.append("")
    # 項目の欠け
    probs = []
    ids = Counter(r["id"] for r in recs)
    for k, v in ids.items():
        if v > 1:
            probs.append(f"地区番号の重複: {k} ×{v}")
    for r in recs:
        miss = [k for k in ["name", "address", "layout", "rent_min", "units", "persons", "elevator", "built"]
                if not r.get(k)]
        if r["category"] != CAT_DEATH and r.get("vacant_now") is None:
            miss.append("vacant_now")
        if not r["station"] and not r["bus"]:
            miss.append("station")
        if miss:
            probs.append(f"{r['id']} {r['name']}（p.{r['page']}）: 空欄 {', '.join(miss)}")
        bad = re.search(r"[�□]|[A-Za-z]{6,}", r["name"] + r["address"] + r["access"])
        if bad:
            probs.append(f"{r['id']}: 文字化けの疑い {bad.group()}")
    out.append("## 項目の欠け・異常\n")
    out += [f"- {p}" for p in probs] or ["- なし"]
    out.append("")
    return out, ok_all, probs


# ---------------------------------------------------------------- 4. 位置情報
def canon(k: str) -> str:
    if "病死" in k:
        return CAT_DEATH
    if "若年" in k or "定期使用" in k:
        return CAT_YOUNG
    return CAT_GENERAL


