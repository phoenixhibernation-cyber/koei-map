// 公開データ（rounds.json / listings.json）から「今日送るべきお知らせ」を作る。scripts/notify_line.py と同じ決まり
const SITE = "https://phoenixhibernation-cyber.github.io/koei-map/";

export function todayJST() { const d = new Date(Date.now() + 9 * 3600e3); return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())); }
const day = (s) => new Date(s + "T00:00:00Z");
const diff = (a, b) => Math.round((a - b) / 86400000);
const fmt = (s) => { const d = day(s); return `${d.getUTCMonth() + 1}/${d.getUTCDate()}（${"日月火水木金土"[d.getUTCDay()]}）`; };

export async function fetchData() {
  const q = "?t=" + Date.now();
  const [rd, ld] = await Promise.all([
    fetch(SITE + "data/rounds.json" + q, { cache: "no-store" }).then((r) => r.json()),
    fetch(SITE + "data/listings.json" + q, { cache: "no-store" }).then((r) => r.json()),
  ]);
  return { rd, ld };
}

// 戻り値：[{ key, pref, text }]  pref は都県名（運営元の pref）。UR など都県の無い運営元は全員向け（pref: null）
export function buildMessages(rd, ld, today = todayJST(), notified = {}) {
  const count = {};
  for (const it of ld.items) count[it.round_id] = (count[it.round_id] || 0) + 1;
  const out = [];
  for (const r of rd.rounds) {
    if (r.anytime || r.expected || !(r.apply_from && r.apply_to)) continue;
    const a = day(r.apply_from), b = day(r.apply_to);
    if (isNaN(a) || isNaN(b)) continue;
    const pref = rd.operators?.[r.operator]?.pref || null;
    const n = count[r.id] || 0;
    const kOpen = `${r.id}:${r.apply_from}:open`, kDl = `${r.id}:${r.apply_from}:deadline`;
    if (diff(today, a) >= 0 && diff(today, a) <= 2 && today <= b && !notified[kOpen])
      out.push({ key: kOpen, pref, text: `【募集が始まりました】${r.label}\n申込 ${fmt(r.apply_from)}〜${fmt(r.apply_to)}` + (n ? `\n${n.toLocaleString("ja-JP")}件を地図で見る → ${SITE}?round=${r.id}` : `\n詳しくは公式ページ → ${r.url}`) });
    const left = diff(b, today);
    if (left > 0 && left <= 3 && !notified[kDl])
      out.push({ key: kDl, pref, text: `【締切まであと${left}日】${r.label}\n${fmt(r.apply_to)}まで\n${SITE}?round=${r.id}` });
  }
  return out;
}
