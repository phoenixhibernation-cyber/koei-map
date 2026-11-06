// 友だちごとの設定の置き場所（Vercel Blob・非公開）。1人1ファイル subs/<userId>.json なので同時書き込みでぶつからない
import { put, get, del, list } from "@vercel/blob";

export const PREFS = ["東京都", "神奈川県", "埼玉県", "千葉県"];
const OPT = { access: "private" };

async function readJson(pathname) {
  const r = await get(pathname, { ...OPT, useCache: false });
  if (!r || r.statusCode !== 200) return null;
  return JSON.parse(await new Response(r.stream).text());
}
async function writeJson(pathname, obj) {
  await put(pathname, JSON.stringify(obj), { ...OPT, addRandomSuffix: false, allowOverwrite: true, contentType: "application/json" });
}

export const getSub = (userId) => readJson(`subs/${userId}.json`);
export const putSub = (sub) => writeJson(`subs/${sub.userId}.json`, sub);
export const delSub = (userId) => del(`subs/${userId}.json`).catch(() => {});
export async function allSubs() {
  const out = [];
  let cursor;
  do {
    const page = await list({ prefix: "subs/", cursor, limit: 1000 });
    for (const b of page.blobs) { const s = await readJson(b.pathname); if (s) out.push(s); }
    cursor = page.hasMore ? page.cursor : undefined;
  } while (cursor);
  return out;
}
export const getState = async () => (await readJson("state/notified.json")) || {};
export const putState = (st) => writeJson("state/notified.json", st);
