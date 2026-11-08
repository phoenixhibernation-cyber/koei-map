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

// 団地を見張る：キーは「都道府県/団地名」。地図の詳細の「この団地をLINEで見張る」から届く
export const watchKey = (pref, name) => `${pref || ""}/${String(name || "").trim()}`;
// 見張っている団地が、今日の募集（始まった・締切3日前）に入っていれば、その人あての文を作る
export function buildWatchMessages(msgs, ld, subs) {
  const inRound = new Map();
  for (const it of ld.items) { if (!inRound.has(it.round_id)) inRound.set(it.round_id, new Map()); inRound.get(it.round_id).set(watchKey(it.pref, it.name), it); }
  const out = [];
  for (const s of subs) {
    if (!s.watch?.length) continue;
    const lines = [];
    for (const m of msgs) {
      const hit = s.watch.filter((w) => inRound.get(m.round)?.has(w));
      if (!hit.length) continue;
      const names = hit.map((w) => w.split("/").slice(1).join("/")).join("・");
      const body = m.text.split("\n").slice(1).join("\n");   // 見出し行を除いた本文（運営元・期間・締切・地図）
      lines.push(m.type === "open" ? `【見張り中の団地が募集に入りました】\n${names}\n\n${body}` : `【見張り中の団地・締切まであと${m.left}日】\n${names}\n\n${body}`);
    }
    if (lines.length) out.push({ userId: s.userId, texts: lines.slice(0, 5) });
  }
  return out;
}

// 戻り値：[{ key, pref, round, type, label, text }]  pref は都県名（運営元の pref）。UR など都県の無い運営元は全員向け（pref: null）
// 文面：運営元・募集名・申込期間・締切・抽せん日・戸数・地図のリンク。読んだ人がそのまま動けるだけの中身を入れる
export function buildMessages(rd, ld, today = todayJST(), notified = {}) {
  const count = {};
  for (const it of ld.items) count[it.round_id] = (count[it.round_id] || 0) + 1;
  const out = [];
  for (const r of rd.rounds) {
    if (r.anytime || r.expected || !(r.apply_from && r.apply_to)) continue;
    const a = day(r.apply_from), b = day(r.apply_to);
    if (isNaN(a) || isNaN(b)) continue;
    const op = rd.operators?.[r.operator] || {};
    const pref = op.pref || null;
    const n = count[r.id] || 0;
    const kOpen = `${r.id}:${r.apply_from}:open`, kDl = `${r.id}:${r.apply_from}:deadline`;
    const left = diff(b, today);
    const body = roundLines(r, op, n, left);
    if (diff(today, a) >= 0 && diff(today, a) <= 2 && today <= b && !notified[kOpen])
      out.push({ key: kOpen, pref, round: r.id, type: "open", label: r.label, text: `【募集が始まりました】\n${body}` });
    if (left > 0 && left <= 3 && !notified[kDl])
      out.push({ key: kDl, pref, round: r.id, type: "deadline", label: r.label, left, text: `【締切まであと${left}日】\n${body}` });
  }
  return out;
}
// 1つの募集の説明（通知の本文）
export function roundLines(r, op, n, left) {
  const lines = [`■ ${r.label}`]; if (op.long) lines.push(`運営：${op.long}`);
  lines.push(`申込期間：${fmt(r.apply_from)}〜${fmt(r.apply_to)}${left > 0 ? `（締切まで${left}日）` : ""}`);
  if (r.lottery) lines.push(`抽せん日：${fmt(r.lottery)}`);
  if (r.units) lines.push(`募集戸数：${Number(r.units).toLocaleString("ja-JP")}戸`);
  if (r.kind) lines.push(`決め方：${r.kind}`);
  if (r.note) lines.push(`※ ${r.note}`);
  lines.push(n ? `対象の住まい ${n.toLocaleString("ja-JP")}件を地図で見る\n${SITE}?round=${r.id}` : `詳しくは公式ページ\n${r.url}`);
  return lines.join("\n");
}
