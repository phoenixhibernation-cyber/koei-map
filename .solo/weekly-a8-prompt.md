# 毎週月曜のA8確認（Claude Code に貼るプロンプト）

下の枠の中をそのまま Claude Code に貼ってください（作業フォルダはどこでもOK）。

```
A8の結果見て。
~/Projects/koei-map/.solo/weekly-a8-prompt.md の「手順」に沿って進めて。
```

## 手順（AIが読む）
1. Phoenix の Gmail（Chrome、phoenix.hibernation@gmail.com）で、前回から届いた A8.net の「プログラム参加承認」「参加お申し込み結果（不承認）」「掲載停止依頼」「プログラム終了」を拾う。接続済みの Gmail コネクタは仕事用なので使わない
2. A8.net（Chrome でログイン済み）の「申込中プログラム」「参加中プログラム」「終了プログラム」で状態を確かめる
3. カチトリ住まい：~/Projects/koei-map/data/partners.json の status を更新する
   - 承認 → 広告リンク作成ページ（/program/create-link?programId=ID、掲載サイト＝カチトリ住まい）から a8mat と計測ピクセルの wwwNN を取り、"active" にして a8mat・px を入れる
   - 不承認 → 候補から削除する。終了・掲載停止依頼 → 期日までに削除する
   - 各カードは active の中で score が一番高いものが自動で出る。新しく出るようになった提携先は、広告掲載URL管理（/ad-site-url-manager/detail?programId=ID）に https://sumai.kachitori.com/ を届け出る
   - テスト（tests/e2e.py）→ commit → push（Vercel が自動で公開）→ 公開サイトで版を確かめる
4. カチトリの履歴書（kachitori.com）：~/Desktop/Company/products/rakuraku-resume/site-clone/src/lib/affiliate.ts も同じ考えで更新する（承認→href・pixel を入れる／不承認・終了→定義ごと消す）。tsc → commit → vercel deploy --prod --yes → 公開サイト確認 → 掲載URLを届け出る
5. 結果を短く報告：承認・不承認・終了の件数と、各カード（引っ越し・ネット・電気ガス・賃貸）にいま出ている提携先

## 優先順位の決め方（data/partners.json の score）
点数＝利用者への合い方40＋サービスの質・信頼20＋確定率15＋報酬・EPC15＋わかりやすさ10。
新しい候補を足すときもこの配点で点を付ける。
