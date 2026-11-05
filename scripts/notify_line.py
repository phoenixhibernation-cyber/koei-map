#!/usr/bin/env python3
"""新しく「募集中」になった募集と、締切3日前の募集を LINE 公式アカウントから友だち全員に送る（broadcast）。
- 送った記録は data/notified.json に残し、同じ募集について同じ種類の通知は1回しか送らない
- LINE_CHANNEL_ACCESS_TOKEN が無ければ何もしない（手元での確認用に --dry-run あり）
"""
from __future__ import annotations
import os, sys, json, datetime, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = "https://phoenixhibernation-cyber.github.io/koei-map/"
TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
DRY = "--dry-run" in sys.argv
today = datetime.date.today()
rounds = json.loads((ROOT / "data" / "rounds.json").read_text(encoding="utf-8"))["rounds"]
ops = json.loads((ROOT / "data" / "operators.json").read_text(encoding="utf-8"))
npath = ROOT / "data" / "notified.json"
notified = json.loads(npath.read_text(encoding="utf-8")) if npath.exists() else {}
items = json.loads((ROOT / "data" / "listings.json").read_text(encoding="utf-8"))["items"]
count = {}
for r in items:
    count[r["round_id"]] = count.get(r["round_id"], 0) + 1


def fmt(s):
    d = datetime.date.fromisoformat(s)
    return f"{d.month}/{d.day}（{'月火水木金土日'[d.weekday()]}）"


msgs = []
for r in rounds:
    if r.get("anytime") or not (r.get("apply_from") and r.get("apply_to")):
        continue
    a, b = datetime.date.fromisoformat(r["apply_from"]), datetime.date.fromisoformat(r["apply_to"])
    key_open, key_dl = f"{r['id']}:open", f"{r['id']}:deadline"
    n = count.get(r["id"], 0)
    if a <= today <= b and key_open not in notified:
        msgs.append((key_open, f"【募集が始まりました】{r['label']}\n申込 {fmt(r['apply_from'])}〜{fmt(r['apply_to'])}"
                     + (f"\n{n:,}件を地図で見る → {SITE}?round={r['id']}" if n else f"\n詳しくは公式ページ → {r['url']}")))
    if (b - today).days == 3 and key_dl not in notified:
        msgs.append((key_dl, f"【締切まで3日】{r['label']}\n{fmt(r['apply_to'])}まで\n{SITE}?round={r['id']}"))

if not msgs:
    print("送るものはありません"); sys.exit(0)
text = "\n\n".join(m for _, m in msgs)
print(text)
if DRY or not TOKEN:
    print("（送信していません）"); sys.exit(0)
req = urllib.request.Request("https://api.line.me/v2/bot/message/broadcast", method="POST",
                             headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
                             data=json.dumps({"messages": [{"type": "text", "text": text[:4900]}]}).encode("utf-8"))
with urllib.request.urlopen(req, timeout=30) as res:
    print("LINE:", res.status)
for k, _ in msgs:
    notified[k] = today.isoformat()
npath.write_text(json.dumps(notified, ensure_ascii=False, indent=1), encoding="utf-8")
