"""申し込みガイド（data/guide/*.json）のリンクが開くかを確かめる。切れていれば一覧を出して 1 で終わる（ワークフローが失敗＝メールが届く）。"""
import json, glob, sys, urllib.request
bad = []
for p in sorted(glob.glob("data/guide/*.json")):
    g = json.load(open(p, encoding="utf-8"))
    for k in ("docs_url", "guide_url", "apply_url"):
        u = g.get(k)
        if not u: continue
        try:
            req = urllib.request.Request(u.split("#")[0], headers={"User-Agent": "Mozilla/5.0 (koei-map link check)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status >= 400: bad.append((g["op"], k, u, r.status))
        except Exception as e:
            bad.append((g["op"], k, u, str(e)[:80]))
for b in bad: print("切れている:", *b)
print(f"確認 {len(glob.glob('data/guide/*.json'))} 件／切れ {len(bad)} 本")
sys.exit(1 if bad else 0)
