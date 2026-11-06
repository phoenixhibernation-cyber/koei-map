// LINE からの通知（友だち追加・ボタン・メッセージ）を受けて、その人の「知りたい都県」を覚える
import crypto from "node:crypto";
import { PREFS, getSub, putSub, delSub } from "../lib/store.js";
import { reply } from "../lib/line.js";

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
    return reply(ev.replyToken, [{ type: "text", text: `友だち追加ありがとうございます。住まいのSmiley（公営住宅・URの募集マップ）です。\n地図はこちら → ${SITE}` }, menu(sub)]);
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
    if (/停止|解除|やめ/.test(t)) { sub.prefs = []; await putSub(sub); return reply(ev.replyToken, [{ type: "text", text: "お知らせを止めました。また受け取りたいときは「設定」と送ってください。" }]); }
    return reply(ev.replyToken, [menu(sub)]);   // 「設定」「地域」など、何を送られても地域の選び直しを出す
  }
}

export async function POST(req) {
  const raw = await req.text();
  const secret = process.env.LINE_CHANNEL_SECRET || "";
  const sig = req.headers.get("x-line-signature") || "";
  const mac = crypto.createHmac("sha256", secret).update(raw).digest("base64");
  if (!secret || sig.length !== mac.length || !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(mac))) {
    console.warn("署名が合いません（LINE_CHANNEL_SECRET 未設定か、LINE 以外からの呼び出し）");
    return new Response("bad signature", { status: 401 });
  }
  const body = JSON.parse(raw || "{}");
  for (const ev of body.events || []) { try { await handle(ev); } catch (e) { console.error("event error", ev.type, e); } }
  return new Response("ok");
}
export const GET = () => new Response("koei-map-line webhook", { status: 200 });
