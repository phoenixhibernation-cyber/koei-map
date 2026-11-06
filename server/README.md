# koei-map-line（LINE通知のサーバー）

住まいのSmiley の LINE 公式アカウント用。Vercel の無料枠で動く小さな仕組み。

- `api/webhook.js` … LINE からの通知を受ける。友だち追加で都県を選ぶボタンを出し、選択を覚える（Vercel Blob・非公開・1人1ファイル）
- `api/cron.js` … 毎朝 06:30（日本時間）に、公開データから「募集が始まった」「締切3日前」を作り、都県ごとに送る
- 環境変数（Vercel の Settings → Environment Variables。オーナーが入れる）：
  - `LINE_CHANNEL_ACCESS_TOKEN` … LINE Developers の Messaging API「チャネルアクセストークン（長期）」
  - `LINE_CHANNEL_SECRET` … 同じ画面の「チャネルシークレット」
  - `CRON_SECRET` … cron を外から勝手に呼ばれないための合言葉（AI が作って入れた）
- LINE Developers 側の設定：Webhook URL = `https://<このプロジェクト>.vercel.app/api/webhook`、Webhook 利用=ON、応答メッセージ=OFF、あいさつメッセージ=OFF（こちらから送るため）
- 手元で確かめる：`node --input-type=module -e "import('./lib/notify.js').then(async m=>{const {rd,ld}=await m.fetchData(); console.log(m.buildMessages(rd,ld))})"`
- 配信：`cd server && vercel deploy --prod`
