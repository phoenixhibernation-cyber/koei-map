// LINE Messaging API の薄い包み（返信・一斉送信）。トークンは環境変数 LINE_CHANNEL_ACCESS_TOKEN
const TOKEN = () => (process.env.LINE_CHANNEL_ACCESS_TOKEN || "").trim();

async function call(path, body) {
  const res = await fetch("https://api.line.me/v2/bot/message/" + path, {
    method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${TOKEN()}` }, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`LINE ${path} ${res.status} ${(await res.text()).slice(0, 300)}`);
  return res;
}
export const reply = (replyToken, messages) => call("reply", { replyToken, messages });
export const multicast = (to, messages) => call("multicast", { to, messages });
export const push = (to, messages) => call("push", { to, messages });
