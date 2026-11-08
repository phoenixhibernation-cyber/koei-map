// LINE からの通知（友だち追加・ボタン・メッセージ）を受けて、その人の「知りたい都県」を覚える
import crypto from "node:crypto";
import { PREFS, getSub, putSub, delSub } from "../lib/store.js";
import { reply } from "../lib/line.js";
import { watchKey } from "../lib/notify.js";

const short = (p) => p.replace(/[都県]$/, "");
const SITE = "https://phoenixhibernation-cyber.github.io/koei-map/";

function menu(sub) {
  const chosen = new Set(sub.prefs || []);
  const items = PREFS.map((p) => ({ type: "action", action: { type: "postback", label: `${chosen.has(p) ? "✓" : ""}${short(p)}`, data: `pref=${p}`, displayText: `${short(p)}${chosen.has(p) ? "をやめる" : "を追加"}` } }));
  items.push({ type: "action", action: { type: "postback", label: "すべて", data: "pref=all", displayText: "1都3県すべて" } });
  items.push({ type: "action", action: { type: "postback", label: "停止", data: "pref=none", displayText: "お知らせを止める" } });
  const now = chosen.size ? `いま選んでいる地域：${[...chosen].map(short).join("・")}` : "まだ地域を選んでいません（選ぶまでお知らせは届きません）";
  return { type: "text", text: `${now}\n\n知りたい都県を押してください（複数OK・押すと切り替わります）。届くのは「募集が始まった日」と「締切の3日前」だけです。`, quickReply: { items } };
}

async function handle(ev) {
  const userId = ev.source?.userId; if (!userId) return;
  if (ev.type === "unfollow") return delSub(userId);
  let sub = (await getSub(userId)) || { userId, prefs: [], since: new Date().toISOString() };
  if (ev.type === "follow") {
    await putSub(sub);
    return reply(ev.replyToken, [{ type: "text", text: `友だち追加ありがとうございます。住まいのSmiley（公営住宅・URの募集マップ）です。\n\n届くお知らせは2種類です。\n① 都県ごと：選んだ都県の「募集が始まった日」と「締切の3日前」\n② 団地ごと：地図で団地を開き「見張る」を押すと、その団地が募集に入った日と締切の3日前\n\nまず①の都県を、次のボタンで選んでください。\n地図 → ${SITE}` }, menu(sub)]);
  }
  if (ev.type === "postback") {
    const v = new URLSearchParams(ev.postback?.data || "").get("pref");
    const s = new Set(sub.prefs || []);
    if (v === "all") PREFS.forEach((p) => s.add(p));
    else if (v === "none") s.clear();
    else if (PREFS.includes(v)) s.has(v) ? s.delete(v) : s.add(v);
    sub.prefs = PREFS.filter((p) => s.has(p)); sub.updated = new Date().toISOString();
    await putSub(sub);
    return reply(ev.replyToken, [menu(sub)]);
  }
  if (ev.type === "message" && ev.message?.type === "text") {
    const t = ev.message.text.trim();
    // 地図の「この団地をLINEで見張る」から：「見張る 東京都 ○○団地」
    const mw = t.match(/^見張る\s+(\S+?[都道府県])\s+(.+)$/);
    if (mw) {
      const key = watchKey(mw[1], mw[2].slice(0, 60));
      const w = new Set(sub.watch || []); w.add(key);
      sub.watch = [...w].slice(-20); sub.updated = new Date().toISOString(); await putSub(sub);
      return reply(ev.replyToken, [{ type: "text", text: `「${mw[2]}」を見張ります。この団地が募集に入った日と、締切の3日前にお知らせします。\n\n見張り中：${sub.watch.length}件（最大20件）\n一覧は「見張り一覧」、やめるときは「見張りをやめる ${mw[2]}」と送ってください。` }]);
    }
    if (/^見張り一覧/.test(t)) {
      const names = (sub.watch || []).map((k) => "・" + k.split("/").slice(1).join("/"));
      return reply(ev.replyToken, [{ type: "text", text: names.length ? `見張り中の団地\n${names.join("\n")}` : "見張っている団地はありません。地図で団地を開き「この団地をLINEで見張る」を押すと追加できます。" }]);
    }
    const mu = t.match(/^見張りをやめる\s*(.*)$/);
    if (mu) {
      const name = mu[1].trim();
      sub.watch = name ? (sub.watch || []).filter((k) => k.split("/").slice(1).join("/") !== name) : [];
      await putSub(sub);
      return reply(ev.replyToken, [{ type: "text", text: name ? `「${name}」の見張りをやめました。` : "見張りを全部やめました。" }]);
    }
    if (/停止|解除|やめ/.test(t)) { sub.prefs = []; sub.watch = []; await putSub(sub); return reply(ev.replyToken, [{ type: "text", text: "お知らせを止めました。また受け取りたいときは「設定」と送ってください。" }]); }
    return reply(ev.replyToken, [menu(sub)]);   // 「設定」「地域」など、何を送られても地域の選び直しを出す
  }
}

export async function POST(req) {
  const raw = await req.text();
  const secret = (process.env.LINE_CHANNEL_SECRET || "").trim();
  const sig = req.headers.get("x-line-signature") || "";
  const mac = crypto.createHmac("sha256", secret).update(raw).digest("base64");
  if (!secret || sig.length !== mac.length || !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(mac))) {
    console.warn("署名が合いません（LINE_CHANNEL_SECRET 未設定か、LINE 以外からの呼び出し）", { secretLen: secret.length, secretLooksRight: /^[0-9a-f]{32}$/.test(secret), sigLen: sig.length });
    return new Response("bad signature", { status: 401 });
  }
  const body = JSON.parse(raw || "{}");
  for (const ev of body.events || []) { try { await handle(ev); } catch (e) { console.error("event error", ev.type, e); } }
  return new Response("ok");
}
export const GET = () => new Response("koei-map-line webhook", { status: 200 });
