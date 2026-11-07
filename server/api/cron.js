// 毎朝（06:30 JST）：今日送るべきお知らせを作り、都県ごとに、その都県を選んだ友だちへ送る
import { fetchData, buildMessages, buildWatchMessages, todayJST } from "../lib/notify.js";
import { allSubs, getState, putState } from "../lib/store.js";
import { multicast, push } from "../lib/line.js";

export async function GET(req) {
  const url = new URL(req.url);
  const auth = req.headers.get("authorization") || "";
  if (process.env.CRON_SECRET && auth !== `Bearer ${process.env.CRON_SECRET}` && url.searchParams.get("key") !== process.env.CRON_SECRET)
    return new Response("unauthorized", { status: 401 });
  const dry = url.searchParams.get("dry") === "1";
  const { rd, ld } = await fetchData();
  const state = await getState();
  const today = todayJST();
  const msgs = buildMessages(rd, ld, today, state);
  const everyone = await allSubs();
  const subs = everyone.filter((s) => s.prefs?.length);
  // 見張っている団地のお知らせ（都県を選んでいない人にも届く）
  const watch = buildWatchMessages(msgs, ld, everyone);
  const report = { date: today.toISOString().slice(0, 10), subscribers: subs.length, messages: msgs.length, sent: [] };
  // 都県ごとにまとめて、1人に最大5吹き出し
  const byPref = new Map();
  for (const m of msgs) { const k = m.pref || "*"; if (!byPref.has(k)) byPref.set(k, []); byPref.get(k).push(m); }
  for (const [pref, list] of byPref) {
    const to = subs.filter((s) => pref === "*" || s.prefs.includes(pref)).map((s) => s.userId);
    const batch = list.slice(0, 5);
    report.sent.push({ pref, to: to.length, texts: batch.map((m) => m.text) });
    if (dry) continue;
    if (to.length && process.env.LINE_CHANNEL_ACCESS_TOKEN) {
      for (let i = 0; i < to.length; i += 500) await multicast(to.slice(i, i + 500), batch.map((m) => ({ type: "text", text: m.text })));
    }
    for (const m of batch) state[m.key] = report.date;   // 送る相手がいなくても「今日分は済み」にする（後から登録した人に古い通知を送らない）
  }
  report.watch = watch.map((w) => ({ texts: w.texts }));
  if (!dry && process.env.LINE_CHANNEL_ACCESS_TOKEN) for (const w of watch) await push(w.userId, w.texts.map((t) => ({ type: "text", text: t })));
  if (!dry && msgs.length) await putState(state);
  return Response.json(report);
}
