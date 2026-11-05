#!/usr/bin/env python3
"""新しく「募集中」になった募集（始まって2日以内）と、締切3日前〜前日の募集を LINE 公式アカウントから友だち全員に送る（broadcast）。
- 送った記録は data/notified.json。キーは「募集id:申込開始日:種類」なので、同じ随時募集の次の受付期間にはまた送る
- 1回の送信は5吹き出し・各5,000字まで。入りきらなかった分は記録せず翌日に回す
- LINE_CHANNEL_ACCESS_TOKEN が無ければ送らない。--dry-run は本文を出すだけ。--seed は今の状態を「送った」ことにして記録だけする（初回用）
日付は日本時間。
"""
from __future__ import annotations
import os, sys, json, datetime, pathlib, urllib.request, urllib.error
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = "https://phoenixhibernation-cyber.github.io/koei-map/"
TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
DRY, SEED = "--dry-run" in sys.argv, "--seed" in sys.argv
today = datetime.datetime.now(ZoneInfo("Asia/Tokyo")).date()
rounds = json.loads((ROOT / "data" / "rounds.json").read_text(encoding="utf-8"))["rounds"]
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
    if r.get("anytime") or r.get("expected") or not (r.get("apply_from") and r.get("apply_to")):
        continue
    try:
        a, b = datetime.date.fromisoformat(r["apply_from"]), datetime.date.fromisoformat(r["apply_to"])
    except ValueError:
        print(f"日付が読めない: {r['id']} {r.get('apply_from')} {r.get('apply_to')}", file=sys.stderr)
        continue
    key_open, key_dl = f"{r['id']}:{r['apply_from']}:open", f"{r['id']}:{r['apply_from']}:deadline"
    n = count.get(r["id"], 0)
    if 0 <= (today - a).days <= 2 and today <= b and key_open not in notified:
        msgs.append((key_open, f"【募集が始まりました】{r['label']}\n申込 {fmt(r['apply_from'])}〜{fmt(r['apply_to'])}"
                     + (f"\n{n:,}件を地図で見る → {SITE}?round={r['id']}" if n else f"\n詳しくは公式ページ → {r['url']}")))
    if 0 < (b - today).days <= 3 and key_dl not in notified:
        msgs.append((key_dl, f"【締切まであと{(b - today).days}日】{r['label']}\n{fmt(r['apply_to'])}まで\n{SITE}?round={r['id']}"))

if SEED:
    for k, _ in msgs:
        notified[k] = today.isoformat()
    npath.write_text(json.dumps(notified, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(msgs)} 件を送ったことにして記録しました（送信なし）"); sys.exit(0)
if not msgs:
    print("送るものはありません"); sys.exit(0)

# 5吹き出し・各5,000字に収まる分だけ送る
batch, size = [], 0
for k, m in msgs:
    if len(batch) >= 5 or len(m) > 4900:
        break
    batch.append((k, m))
print("\n\n".join(m for _, m in batch))
if DRY or not TOKEN:
    print(f"（送信していません。{len(msgs)}件中{len(batch)}件）"); sys.exit(0)
req = urllib.request.Request("https://api.line.me/v2/bot/message/broadcast", method="POST",
                             headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
                             data=json.dumps({"messages": [{"type": "text", "text": m} for _, m in batch]}).encode("utf-8"))
try:
    with urllib.request.urlopen(req, timeout=30) as res:
        print("LINE:", res.status)
except urllib.error.HTTPError as e:
    print("LINE error:", e.code, e.read().decode("utf-8", "ignore")[:500], file=sys.stderr)
    sys.exit(1)
for k, _ in batch:
    notified[k] = today.isoformat()
npath.write_text(json.dumps(notified, ensure_ascii=False, indent=1), encoding="utf-8")
