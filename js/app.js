/* カチトリ住まい 試作版（静的サイト・ビルドなし） */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const yen = (n) => (n == null ? "—" : n.toLocaleString("ja-JP"));
  const norm = (s) => String(s || "").normalize("NFKC").toLowerCase().replace(/\s+/g, "");
  const VERSION = "2026-11-14a";   // 画面の「このサービスについて」に出す版。index.html の ?v= も同じにする
  console.log("カチトリ住まい", VERSION);
  const PAGE = 50;
  const DESKTOP = window.matchMedia("(min-width: 900px)");
  const TODAY = new Date(); TODAY.setHours(0, 0, 0, 0);
  const dayOf = (s) => { const d = new Date(s + "T00:00:00"); return d; };
  const daysLeft = (s) => Math.round((dayOf(s) - TODAY) / 86400000);
  const fmtMD = (s) => { const d = dayOf(s); return `${d.getMonth() + 1}/${d.getDate()}（${"日月火水木金土"[d.getDay()]}）`; };
  const store = { get: (k) => { try { return JSON.parse(localStorage.getItem("smiley:" + k)); } catch (e) { console.warn("保存した設定を読めません:", k, e); return null; } },
    set: (k, v) => { try { localStorage.setItem("smiley:" + k, JSON.stringify(v)); } catch (e) { console.warn("設定を保存できません（プライベートモードなど）:", k, e); } } };
  const colorOf = (op) => /^#[0-9a-f]{3,8}$/i.test(op?.color || "") ? op.color : "#888";            // データ由来の色は形式を確かめてから属性に入れる
  const safeUrl = (u) => /^https?:\/\//i.test(u || "") ? u : "#";                                  // href は http(s) だけ

  let OPS = {}, ROUNDS = [], ITEMS = [], byId = new Map(), markers = new Map();
  const CITY_PREF = new Map();   // 市区町村名 → 都県
  const PREFS = ["東京都", "神奈川県", "埼玉県", "千葉県"];   // いま物件が載っている都県
  // 全国の枠組み（地方 → 都道府県 → 市区町村）。PREFS 以外は「準備中」で見せる
  const REGIONS = [
    ["北海道・東北", ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"]],
    ["関東", ["東京都", "神奈川県", "埼玉県", "千葉県", "茨城県", "栃木県", "群馬県"]],
    ["中部", ["新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県"]],
    ["関西（近畿）", ["大阪府", "京都府", "兵庫県", "奈良県", "滋賀県", "和歌山県", "三重県"]],
    ["中国・四国", ["鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県"]],
    ["九州・沖縄", ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]],
  ];
  let areaRegion = null;
  let filtered = [], shown = 0, activeId = null;
  const F = { now: true, prefs: new Set(), cities: new Set(), rentMax: null, layouts: new Set(), ops: new Set(), single: false, ev: false, q: "", round: null,
    builtFrom: null, areaMin: null, ratioMax: null, walkMax: null, noBus: false, bf: false, priority: false, unitsMin: null, vacant: false, cats: new Set() };
  const RESET = () => Object.assign(F, { prefs: new Set(), cities: new Set(), rentMax: null, layouts: new Set(), ops: new Set(), single: false, ev: false, q: "", round: null, now: true, builtFrom: null, areaMin: null, ratioMax: null, walkMax: null, noBus: false, bf: false, priority: false, unitsMin: null, vacant: false, cats: new Set() });
  const LAYOUTS = ["1DK", "1LDK", "2K", "2DK", "2LDK", "3DK", "3LDK", "4DK"];
  const isInfo = (r) => r.units == null && /団地情報/.test(r.subtype || "");
  const KINDS = ["都営", "県営", "市営", "UR"];                                   // 運営元の種別（operators.json の label）
  const shortOp = (op) => op.long.replace(/住宅.*$/, "").replace("UR賃貸", "UR");  // 都営／神奈川県営／横浜市営／UR   // 募集期間外に出す「団地の情報だけ」の項目

  /* ---------------- 地図 ---------------- */
  const map = L.map("map", { zoomControl: false, zoomSnap: 0.5, maxZoom: 17, tap: true, attributionControl: true });
  map.fitBounds([[35.45, 139.1], [35.92, 139.95]]);
  L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
    maxZoom: 18, updateWhenZooming: false, attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">国土地理院</a>',
  }).addTo(map);
  L.control.zoom({ position: "topright", zoomInTitle: "拡大", zoomOutTitle: "縮小" }).addTo(map);
  // ＋−ボタン・キーボードのズームは、パネルやシートに隠れていない「見えている範囲」の中心を基準にする
  function visibleCenter() {
    const W = map.getSize().x, H = map.getSize().y;
    let l = 0, r = W, t = 0, b = H;
    if (DESKTOP.matches) { l = 400; if (!$("detail").hidden) l = 416 + 420; }
    else {
      t = $("topbar").getBoundingClientRect().bottom;
      const det = $("detail"), dr = $("drawer");
      b = !det.hidden ? det.getBoundingClientRect().top : (dr ? dr.getBoundingClientRect().top : H);
      if (b - t < 80) { t = 0; b = H; }
    }
    return L.point((l + r) / 2, (t + b) / 2);
  }
  if (new URLSearchParams(location.search).has("e2e")) window.__map = map;   // 自動テスト用
  map.zoomIn = (delta, opt) => map.setZoomAround(visibleCenter(), map.getZoom() + (delta || map.options.zoomDelta || 1), opt);
  map.zoomOut = (delta, opt) => map.setZoomAround(visibleCenter(), map.getZoom() - (delta || map.options.zoomDelta || 1), opt);

  // 境界：1都3県の市区町村（細い線）と都県（太めの線）。地域を選んだ・地名で検索したときは、その範囲を青い太線で囲む
  ["bline", "bhi"].forEach((n, i) => { const p = map.createPane(n); p.style.zIndex = [380, 395][i]; p.style.pointerEvents = "none"; });
  let AREAS = null, hiLayer = null, hiKey = "";
  let DATA_DATE = "";   // 公開データを最後に作った日（表示用）
  const fmtDate = (d) => { const x = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || ""); return x ? `${x[1]}/${+x[2]}/${+x[3]}` : ""; };
  const areaNorm = (t) => norm(t).replace(/[ヶケ]/g, "け");
  fetch("data/areas.json").then((r) => r.json()).then((A) => {
    AREAS = A.features;
    const cityNames = AREAS.filter((f) => f.properties.kind === "city").map((f) => f.properties.name);
    const wholes = new Set(cityNames.filter((n) => cityNames.some((m) => m !== n && m.startsWith(n))));   // 横浜市など政令市そのもの（区の線で描けるので省く）
    const cityL = L.geoJSON({ type: "FeatureCollection", features: AREAS.filter((f) => f.properties.kind === "city" && !wholes.has(f.properties.name)) },
      { pane: "bline", interactive: false, fill: false, style: { color: "#5f6b7a", weight: 1, opacity: 0.55 } });
    const prefL = L.geoJSON({ type: "FeatureCollection", features: AREAS.filter((f) => f.properties.kind === "pref") },
      { pane: "bline", interactive: false, fill: false, style: { color: "#3c4757", weight: 2.2, opacity: 0.75 } }).addTo(map);
    const onZoom = () => { map.getZoom() >= 9.5 ? cityL.addTo(map) : cityL.remove(); };
    map.on("zoomend", onZoom); onZoom();
    highlightAreas(false);
  }).catch((e) => console.warn("境界を読めません", e));
  // 今の条件（地域チップ・検索の文字）から囲む範囲を決める
  function areaTargets() {
    if (!AREAS) return [];
    const byName = (n) => AREAS.filter((f) => f.properties.name === n || f.properties.alt.includes(n));
    if (F.cities.size) return [...F.cities].flatMap(byName);
    if (F.prefs.size) return [...F.prefs].flatMap((p) => AREAS.filter((f) => f.properties.kind === "pref" && f.properties.name === p));
    const q = areaNorm($("q").value || ""); if (q.length < 2) return [];
    const names = (f) => [f.properties.name, ...f.properties.alt].map(areaNorm);
    let hit = AREAS.filter((f) => names(f).some((n) => n === q || n.replace(/[都県市区町村]$/, "") === q));
    if (!hit.length) hit = AREAS.filter((f) => f.properties.kind === "city" && names(f).some((n) => n.endsWith(q) || n.replace(/[市区町村]$/, "").endsWith(q)));
    return hit.slice(0, 6);
  }
  function highlightAreas(fit) {
    const t = areaTargets(), key = t.map((f) => f.properties.name).join("|");
    if (key === hiKey) return; hiKey = key;
    if (hiLayer) { hiLayer.remove(); hiLayer = null; }
    if (!t.length) return;
    const fc = { type: "FeatureCollection", features: t };
    hiLayer = L.layerGroup([
      L.geoJSON(fc, { pane: "bhi", interactive: false, style: { color: "#fff", weight: 7, opacity: 0.9, fill: false } }),
      L.geoJSON(fc, { pane: "bhi", interactive: false, style: { color: "#1a73e8", weight: 3.5, opacity: 1, fillColor: "#1a73e8", fillOpacity: 0.07 } }),
    ]).addTo(map);
    if (fit) fitVisible(L.geoJSON(fc).getBounds());
  }
  // パネルやシートに隠れない範囲に収める
  function fitVisible(b) {
    if (!b.isValid()) return;
    const W = map.getSize().x, H = map.getSize().y, c = visibleCenter();
    const padL = DESKTOP.matches ? (c.x * 2 - W) + 24 : 16, padT = DESKTOP.matches ? 24 : $("topbar").getBoundingClientRect().bottom + 8;
    const padB = DESKTOP.matches ? 24 : H - (c.y * 2 - padT) + 8;
    map.fitBounds(b, { paddingTopLeft: [Math.max(16, padL), padT], paddingBottomRight: [16, Math.max(16, padB)], maxZoom: 14 });
  }

  const cluster = L.markerClusterGroup({
    showCoverageOnHover: false, spiderfyOnMaxZoom: true, chunkedLoading: true,
    maxClusterRadius: (z) => (z >= 15 ? 36 : 56),
    iconCreateFunction(c) {
      const n = c.getChildCount(); const size = n < 10 ? 36 : n < 100 ? 44 : 52; const cls = n < 10 ? "s" : n < 100 ? "m" : "l";
      return L.divIcon({ html: `<div class="cluster ${cls}" style="width:${size}px;height:${size}px">${n}</div>`, className: "", iconSize: [size, size] });
    },
  });
  map.addLayer(cluster);
  const pinIcon = (r, active) => L.divIcon({ className: "pin-icon", html: `<div class="pin${active ? " active" : ""}${isInfo(r) ? " info" : ""}" style="--op:${colorOf(OPS[r.operator])}"></div>`, iconSize: [24, 24], iconAnchor: [12, 30] });
  // 選んだ物件の赤いピン（クラスタに飲まれないよう、地図に直接置く）
  const activeIcon = L.divIcon({ className: "pin-icon", html: '<div class="pin-red"><svg viewBox="0 0 24 36" width="36" height="54"><path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 24 12 24s12-15 12-24C24 5.4 18.6 0 12 0z" fill="#ea4335"/><circle cx="12" cy="12" r="5" fill="#fff"/></svg></div>', iconSize: [36, 54], iconAnchor: [18, 54] });
  let activeMarker = null;
  function showActivePin(r) { if (activeMarker) activeMarker.remove(); activeMarker = null; if (r && r.lat != null) activeMarker = L.marker([r.lat, r.lon], { icon: activeIcon, zIndexOffset: 5000, keyboard: false, interactive: false }).addTo(map); }
  // 詳細パネル・シートに隠れない位置へ地図をずらす（パソコン：左のパネル2枚の右側の中央／スマホ：上の見えている帯の中央）
  function focusOn(r, zoomIn) {
    if (r.lat == null) return;
    const z = zoomIn ? Math.max(map.getZoom(), DESKTOP.matches ? 17 : 16) : map.getZoom();   // 建物の形が分かるところまで寄せる
    const W = map.getSize().x, H = map.getSize().y, c = visibleCenter();
    // ピンが「パネルやシートに隠れていない範囲」の中心に来るよう、地図の中心をずらす
    const target = map.project([r.lat, r.lon], z).add([W / 2 - c.x, H / 2 - c.y]);
    map.setView(map.unproject(target, z), z, { animate: true });
  }

  // 現在地
  let meMarker = null;
  let locTry = 0;
  function locate() {
    locTry++;
    // 1回目は高精度・10秒。だめなら通常精度・20秒・5分以内の位置も可（パソコンやWi-Fi測位向け）
    map.locate({ setView: true, maxZoom: 14, enableHighAccuracy: locTry === 1, timeout: locTry === 1 ? 10000 : 20000, maximumAge: locTry === 1 ? 0 : 300000 });
  }
  $("btnLocate").addEventListener("click", async () => {
    if (!navigator.geolocation) return toast("この端末では現在地を取得できません");
    try { const st = await navigator.permissions?.query({ name: "geolocation" }); if (st && st.state === "denied") return showLocHelp(); } catch {}
    if (!window.isSecureContext) return toast("現在地は https のページでだけ使えます");
    $("btnLocate").classList.add("busy");
    locTry = 0; locate();
  });
  map.on("locationfound", (e) => {
    $("btnLocate").classList.remove("busy");
    const icon = L.divIcon({ className: "", html: '<div class="me-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });
    if (meMarker) meMarker.setLatLng(e.latlng); else meMarker = L.marker(e.latlng, { icon, keyboard: false, interactive: false, zIndexOffset: 1000 }).addTo(map);
  });
  map.on("locationerror", (e) => {
    if (e.code !== 1 && locTry < 2) return locate();   // 許可されていない以外は、通常精度でもう一度
    $("btnLocate").classList.remove("busy");
    console.warn("現在地エラー", e.code, e.message);
    if (e.code === 1) return showLocHelp();
    toast(e.code === 3 ? "現在地の取得に時間がかかっています。少し待ってもう一度押してください"
      : "現在地を特定できませんでした。パソコンでは位置情報サービスがオフだと取れないことがあります");
  });

  // 現在地が使えないときの手順（端末・ブラウザで違うので、使っているものに合わせて出す）
  function showLocHelp() {
    const ua = navigator.userAgent, ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    let steps;
    if (ios && /CriOS/.test(ua)) steps = ["iPhoneの「設定」アプリを開く", "下へスクロールして「Chrome」を押す", "「位置情報」→「このAppの使用中」を選ぶ（「正確な位置情報」もオン）", "Chromeに戻ってページを再読み込みし、もう一度 ◎ を押す →「許可」"];
    else if (ios && /FxiOS|EdgiOS/.test(ua)) steps = ["iPhoneの「設定」アプリ → 使っているブラウザ（Firefox・Edge）を押す", "「位置情報」→「このAppの使用中」", "ブラウザに戻って再読み込みし、もう一度 ◎ を押す →「許可」"];
    else if (ios) steps = ["iPhoneの「設定」→「プライバシーとセキュリティ」→「位置情報サービス」をオン", "同じ画面の下の方の「Safari Webサイト」→「このAppの使用中」（「正確な位置情報」もオン）", "Safariのアドレスバー左の「ぁあ」→「Webサイトの設定」→「位置情報」→「許可」", "再読み込みして、もう一度 ◎ を押す"];
    else if (/Android/.test(ua)) steps = ["端末の上から下へスワイプし「位置情報」をオン", "Chromeのアドレスバー左のアイコン →「権限」→「位置情報」→「許可」", "再読み込みして、もう一度 ◎ を押す"];
    else if (/Mac/.test(ua)) steps = ["アドレスバー左のアイコン（鍵や調整のマーク）→「位置情報」→「許可」", "Macの「システム設定」→「プライバシーとセキュリティ」→「位置情報サービス」→ 使っているブラウザをオン", "ブラウザを再起動して、もう一度 ◎ を押す"];
    else steps = ["アドレスバー左のアイコン（鍵や調整のマーク）→「位置情報」→「許可」", "Windowsの「設定」→「プライバシーとセキュリティ」→「位置情報」→「位置情報サービス」とブラウザをオン", "再読み込みして、もう一度 ◎ を押す"];
    $("locSteps").innerHTML = steps.map((t) => `<li>${esc(t)}</li>`).join("");
    openPage("pageLoc");
  }

  /* ---------------- データ ---------------- */
  let SITE = { line_url: "" };
  let AFF = null;   // 提携先の候補と優先順位（data/partners.json。「aff」の名前は広告ブロッカーに消されるので使わない）。読めなくても画面は出す
  fetch("data/partners.json", { cache: "no-cache" }).then((r) => r.ok ? r.json() : null).then((j) => { AFF = j; }).catch(() => {});
  // その種類のカードに出す提携先：提携中（active）で広告リンクがあるもののうち、点数が一番高いもの
  const affPick = (kind) => {
    const list = (AFF && AFF.cards && AFF.cards[kind]) || [];
    return list.filter((c) => c.status === "active" && /^[A-Z0-9+]+$/.test(c.a8mat || "") && /^www\d+$/.test(c.px || "")).sort((a, z) => z.score - a.score)[0] || null;
  };
  Promise.all([fetch("data/rounds.json", { cache: "no-cache" }).then((r) => r.json()), fetch("data/listings.json", { cache: "no-cache" }).then((r) => r.json()),
    fetch("data/site.json", { cache: "no-cache" }).then((r) => r.json()).catch(() => ({}))])
    .then(([rd, ld, st]) => {
      SITE = Object.assign(SITE, st || {});
      // 端末が古い index.html を使い続けているとき（GitHub Pages のキャッシュ）、版の違いを見て自分で取り直す（1回だけ）
      if (SITE.version && SITE.version !== VERSION && !new URLSearchParams(location.search).has("e2e")) {
        let tried = null; try { tried = sessionStorage.getItem("smiley:reloaded"); } catch {}
        if (tried !== SITE.version) { try { sessionStorage.setItem("smiley:reloaded", SITE.version); } catch {} const u = new URLSearchParams(location.search); u.set("v", SITE.version); location.replace(location.pathname + "?" + u.toString() + location.hash); return; }
        console.warn("版が合いません（画面", VERSION, "／データ", SITE.version, "）");
      }
      init(rd, ld);
    })
    .catch((e) => { console.error(e); $("count").textContent = "データを読み込めませんでした"; });

  function roundStatus(r) {
    if (r.anytime) return "anytime";
    if (r.apply_from && r.apply_to) {
      if (TODAY < dayOf(r.apply_from)) return "upcoming";
      if (TODAY <= dayOf(r.apply_to)) return "open";
      return "closed";
    }
    return "upcoming";
  }

  // 選んだ条件はこの端末に残す（次に開いたとき、同じ条件で始まる）
  const SAVE_KEYS = ["now", "prefs", "cities", "rentMax", "layouts", "ops", "single", "ev", "builtFrom", "areaMin", "ratioMax", "walkMax", "noBus", "bf", "priority", "unitsMin", "vacant", "cats"];
  const COND_V = 1;                 // 保存する形の版。変えたら古い保存は無視する
  let NOSAVE = false;               // ?e2e（テスト）のときは保存しない
  function saveCond() {
    if (NOSAVE || F.round) return;  // 通知のリンク（?round=）から開いたときは、その人の条件を上書きしない
    const o = { v: COND_V }; for (const k of SAVE_KEYS) o[k] = F[k] instanceof Set ? [...F[k]] : F[k]; o.sort = $("sort").value; store.set("cond", o);
  }
  function restoreCond() {
    const o = store.get("cond"); if (!o || typeof o !== "object" || o.v !== COND_V) return false;
    // 今のデータに無い値（消えた運営元・地域など）は捨てる。型が違う値も捨てる
    const domain = { prefs: new Set(PREFS), cities: new Set(CITY_PREF.keys()), layouts: new Set(LAYOUTS), ops: new Set(Object.keys(OPS)), cats: new Set(ITEMS.map((r) => r.cat_group || r.category)) };
    const num = (v) => (typeof v === "number" && Number.isFinite(v)) ? v : null;
    for (const k of SAVE_KEYS) {
      if (!(k in o)) continue;
      if (F[k] instanceof Set) F[k] = new Set((Array.isArray(o[k]) ? o[k] : []).filter((v) => domain[k].has(v)));
      else if (typeof F[k] === "boolean") { if (typeof o[k] === "boolean") F[k] = o[k]; }   // 型が違えば今の値（初期値）のまま
      else F[k] = num(o[k]);
    }
    F.now = true;   // 「募集中」スイッチは廃止（2026-11-07）。常に今申し込めるものだけ
    const sortOk = o.sort && [...$("sort").options].some((x) => x.value === o.sort);
    if (sortOk) $("sort").value = o.sort;
    return SAVE_KEYS.some((k) => k !== "now" && (F[k] instanceof Set ? F[k].size : F[k])) || !F.now || (sortOk && o.sort !== "rent");
  }
  function init(rd, ld) {
    OPS = rd.operators; ROUNDS = rd.rounds; ITEMS = ld.items; DATA_DATE = fmtDate(ld.generated_at || rd.generated_at);
    const roundById = new Map(ROUNDS.map((r) => [r.id, r]));
    ITEMS.forEach((r) => {
      byId.set(r.id, r);
      r._round = roundById.get(r.round_id) || null;
      r._status = r._round ? roundStatus(r._round) : "open";
      r._search = norm([r.name, r.address, r.access, r.city, r.stations.join(" ")].join(" "));
      r._opLabel = OPS[r.operator]?.label || r.operator;
      if (r.city) CITY_PREF.set(r.city, r.pref);
    });
    buildAbout(); setupLine();
    const params = new URLSearchParams(location.search);
    NOSAVE = params.has("e2e");
    if (params.get("round") && roundById.has(params.get("round"))) { F.round = params.get("round"); F.now = false; }
    else if (!NOSAVE && restoreCond()) setTimeout(() => toast("前回の条件で表示しています（「条件を外す」で戻せます）"), 600);
    bindUI();
    apply();
  }

  /* ---------------- 絞り込み ---------------- */
  function matches(r) {
    if (F.round) { if (r.round_id !== F.round) return false; }
    else if (F.now && !(r._status === "open" || r._status === "anytime")) return false;
    if (F.prefs.size) {
      if (!F.prefs.has(r.pref)) return false;
      if (F.cities.size && !F.cities.has(r.city) && [...F.cities].some((c) => CITY_PREF.get(c) === r.pref)) return false;
    }
    if (F.rentMax != null && (r.rent_min == null || r.rent_min > F.rentMax)) return false;
    if (F.layouts.size && !r.layouts.some((l) => F.layouts.has(l))) return false;
    if (F.ops.size && !F.ops.has(r.operator)) return false;
    if (F.single && !r.single_ok) return false;
    if (F.ev && !r.elevator) return false;
    if (F.q && !r._search.includes(F.q)) return false;
    if (F.builtFrom != null && (r.built_from == null || r.built_from < F.builtFrom)) return false;
    if (F.areaMin != null && (r.area_max == null || r.area_max < F.areaMin)) return false;
    if (F.ratioMax != null && (r.ratio_prev == null || r.ratio_prev > F.ratioMax)) return false;
    if (F.walkMax != null && (r.walk_min == null || r.walk_min > F.walkMax)) return false;
    if (F.noBus && r.bus) return false;
    if (F.bf && !r.barrier_free) return false;
    if (F.priority && !r.priority_lottery) return false;
    if (F.unitsMin != null && (r.units == null || r.units < F.unitsMin)) return false;
    if (F.vacant && !(r.vacant_now > 0)) return false;
    if (F.cats.size && !F.cats.has(r.cat_group || r.category)) return false;
    return true;
  }
  const nz = (v, big) => (v == null || Number.isNaN(v) ? (big ? 1e12 : -1) : v);
  const SORTS = {
    rent: (a, b) => nz(a.rent_min, 1) - nz(b.rent_min, 1),
    ratio: (a, b) => nz(a.ratio_prev, 1) - nz(b.ratio_prev, 1),
    units: (a, b) => nz(b.units) - nz(a.units),
    walk: (a, b) => (a.bus - b.bus) || nz(a.walk_min, 1) - nz(b.walk_min, 1),
    new: (a, b) => nz(b.built_from) - nz(a.built_from),
    old: (a, b) => nz(a.built_from, 1) - nz(b.built_from, 1),
    area: (a, b) => nz(b.area_max) - nz(a.area_max),
  };

  function apply() {
    filtered = ITEMS.filter(matches).sort(SORTS[$("sort").value] || SORTS.rent);
    renderMarkers(); shown = 0; $("list").innerHTML = ""; renderMore(); renderCount(); renderChips(); saveCond();
    if (typeof highlightAreas === "function") highlightAreas(true);
  }
  function renderCount() {
    const n = filtered.length;
    const roundLabel = F.round ? (ROUNDS.find((r) => r.id === F.round)?.label || "") : "";
    $("count").innerHTML = `${n.toLocaleString("ja-JP")}件${roundLabel ? `<small>${esc(roundLabel)}</small>` : "<small>今申し込める</small>"}`;
    $("empty").hidden = n > 0;
  }
  function renderMore() {
    const frag = document.createDocumentFragment();
    filtered.slice(shown, shown + PAGE).forEach((r) => frag.appendChild(itemEl(r)));
    $("list").appendChild(frag); shown = Math.min(filtered.length, shown + PAGE);
    $("more").hidden = shown >= filtered.length;
  }
  $("more").addEventListener("click", renderMore);
  function itemEl(r) {
    const li = document.createElement("li"); li.className = "item" + (r.id === activeId ? " active" : ""); li.dataset.id = r.id; li.tabIndex = 0;
    const walk = r.walk_min != null ? `${r.bus ? "バス" : ""}${r.stations[0] || ""}${r.walk_min}分` : (r.stations[0] || "");
    const ratio = r.ratio_prev != null ? `・前回${r.ratio_prev}倍` : "";
    const cat = isInfo(r) || /^(一般|世帯向|先着順|UR|一般世帯向け?住宅?)$/.test(r.category || "") ? "" : `・${r.category.replace(/住宅$/, "")}`;
    li.innerHTML = `<b>${esc(r.name)}</b><span class="rent">${isInfo(r) ? '<small class="info">団地情報</small>' : r.rent_min != null ? `¥${yen(r.rent_min)}〜` : "家賃は募集時に"}</span>
      <span class="sub"><span class="tag" style="--op:${colorOf(OPS[r.operator])}">${esc(r._opLabel)}</span>${esc([r.layout, r.area_text ? r.area_text + "㎡" : ""].filter(Boolean).join(" "))}${r.layout || r.area_text ? "・" : ""}${esc(walk)}${ratio}${r.single_ok ? "・単身可" : ""}${esc(cat)}</span>`;
    li.addEventListener("click", () => openDetail(r.id, true));
    li.addEventListener("keydown", (e) => { if (e.key === "Enter") openDetail(r.id, true); });
    return li;
  }
  function renderMarkers() {
    cluster.clearLayers(); markers.clear();
    const ms = [];
    for (const r of filtered) {
      if (r.lat == null) continue;
      const m = L.marker([r.lat, r.lon], { icon: pinIcon(r, r.id === activeId), keyboard: false });
      m.on("click", () => openDetail(r.id, false));
      markers.set(r.id, m); ms.push(m);
    }
    cluster.addLayers(ms);
  }

  /* ---------------- 絞り込み（下のバーから開く・項目ごとに折りたたみ） ---------------- */
  const SECTIONS = [["area", "地域"], ["op", "運営元"], ["rent", "家賃"], ["layout", "間取り"], ["built", "築年"], ["more", "こだわり"]];
  const MORE_KEYS = () => [F.single, F.ev, F.areaMin != null, F.ratioMax != null, F.walkMax != null, F.noBus, F.bf, F.priority, F.unitsMin != null, F.vacant, F.cats.size > 0];
  function summaryOf(k) {
    if (k === "area") {
      const parts = [];
      for (const p of PREFS) { if (!F.prefs.has(p)) continue; const cs = [...F.cities].filter((c) => CITY_PREF.get(c) === p); parts.push(cs.length ? (cs.length <= 2 ? cs.join("・") : `${p.replace(/[都県]$/, "")}${cs.length}か所`) : p); }
      return parts.join("・");
    }
    if (k === "op") { const ops = [...F.ops]; return ops.length ? (ops.length <= 2 ? ops.map((o) => OPS[o] ? shortOp(OPS[o]) : o).join("・") : `${ops.length}つ`) : ""; }
    if (k === "rent") return F.rentMax != null ? `〜${F.rentMax / 10000}万円` : "";
    if (k === "layout") return F.layouts.size ? [...F.layouts].join("・") : "";
    if (k === "built") return F.builtFrom != null ? `${F.builtFrom}年〜` : "";
    if (k === "more") { const w = [F.single && "単身可", F.ev && "EVあり"].filter(Boolean); const n = MORE_KEYS().filter(Boolean).length - w.length; return [...w, n ? `ほか${n}` : ""].filter(Boolean).join("・"); }
    return "";
  }
  // いま効いている条件の数・文（下のバーのバッジと、一覧の上の1行）
  function renderChips() {
    const parts = SECTIONS.map(([k]) => summaryOf(k)).filter(Boolean);
    const n = parts.length;
    $("filterN").hidden = !n; $("filterN").textContent = n;
    const roundOn = !!F.round;
    $("cond").hidden = !(n || roundOn || F.q);
    $("condText").textContent = [roundOn ? "この募集だけ" : "", F.q ? `「${$("q").value}」` : "", ...parts].filter(Boolean).join("・");
  }
  $("condClear").addEventListener("click", () => { RESET(); $("q").value = ""; $("qClear").hidden = true; $("sort").value = "rent"; apply(); });

  let openSec = null;
  const TITLES = Object.fromEntries(SECTIONS);
  const selectRow = (label, options, cur, onChange) => {
    const g = document.createElement("div"); g.className = "opt-group"; g.innerHTML = `<h4>${esc(label)}</h4>`;
    const row = document.createElement("div"); row.className = "rent-row"; const sel = document.createElement("select");
    sel.innerHTML = options.map(([v, l]) => `<option value="${v}"${String(cur ?? "") === String(v) ? " selected" : ""}>${esc(l)}</option>`).join("");
    sel.addEventListener("change", () => onChange(sel.value === "" ? null : Number(sel.value)));
    row.appendChild(sel); g.appendChild(row); return g;
  };
  const toggleRow = (label, opts) => group(label, opts.map(([k, l]) => opt(l, F[k], () => { F[k] = !F[k]; })));
  function buildBody(k, b) {
    if (k === "area") {
      renderAreaBody(b);
    } else if (k === "rent") {
      const row = document.createElement("div"); row.className = "rent-row";
      const sel = document.createElement("select");
      sel.innerHTML = `<option value="">上限なし</option>` + [20000, 25000, 30000, 35000, 40000, 50000, 60000, 80000, 100000].map((v) => `<option value="${v}"${F.rentMax === v ? " selected" : ""}>${(v / 10000)}万円まで</option>`).join("");
      sel.addEventListener("change", () => { F.rentMax = sel.value ? Number(sel.value) : null; });
      row.appendChild(sel); b.appendChild(row);
      const h = document.createElement("p"); h.className = "hint"; h.textContent = "公営住宅の家賃は世帯の収入で変わります。ここでは一番安い額で絞り込みます。"; b.appendChild(h);
    } else if (k === "layout") {
      b.appendChild(group("いくつでも", LAYOUTS.map((l) => opt(l, F.layouts.has(l), () => { F.layouts.has(l) ? F.layouts.delete(l) : F.layouts.add(l); }))));
    } else if (k === "op") {
      for (const kind of KINDS) {
        const ops = Object.keys(OPS).filter((o) => OPS[o].label === kind); if (!ops.length) continue;
        b.appendChild(group(kind === "UR" ? "UR（いつでも・先着順）" : kind, ops.map((o) => { const el = opt(OPS[o].long, F.ops.has(o), () => { F.ops.has(o) ? F.ops.delete(o) : F.ops.add(o); }); el.insertAdjacentHTML("afterbegin", `<i class="dot" style="--op:${OPS[o].color}"></i>`); return el; })));
      }
      const h = document.createElement("p"); h.className = "hint"; h.textContent = "いくつでも。何も選ばなければ全部です。"; b.appendChild(h);
    } else if (k === "built") {
      const y = new Date().getFullYear();
      b.appendChild(selectRow("この年より新しい建物", [["", "指定なし"], ...[2015, 2010, 2005, 2000, 1995, 1990, 1985, 1980, 1975, 1970].map((v) => [v, `${v}年以降（築${y - v}年以内）`])], F.builtFrom, (v) => { F.builtFrom = v; }));
    } else if (k === "more") {
      b.appendChild(toggleRow("暮らし方", [["single", "単身可"], ["ev", "エレベーターあり"], ["bf", "バリアフリー"], ["vacant", "いま空きあり"]]));
      const cats = [...new Set(ITEMS.map((r) => r.cat_group || r.category))];
      b.appendChild(group("募集の種類", cats.map((c) => opt(c, F.cats.has(c), () => { F.cats.has(c) ? F.cats.delete(c) : F.cats.add(c); }))));
      b.appendChild(selectRow("広さ", [["", "指定なし"], [30, "30㎡以上"], [35, "35㎡以上"], [40, "40㎡以上"], [50, "50㎡以上"], [60, "60㎡以上"]], F.areaMin, (v) => { F.areaMin = v; }));
      b.appendChild(selectRow("前回の倍率", [["", "指定なし"], [1, "1倍以下（ほぼ当たる）"], [3, "3倍以下"], [5, "5倍以下"], [10, "10倍以下"]], F.ratioMax, (v) => { F.ratioMax = v; }));
      b.appendChild(selectRow("駅から", [["", "指定なし"], [5, "徒歩5分以内"], [10, "徒歩10分以内"], [15, "徒歩15分以内"]], F.walkMax, (v) => { F.walkMax = v; }));
      b.appendChild(selectRow("募集戸数", [["", "指定なし"], [2, "2戸以上"], [5, "5戸以上"], [10, "10戸以上"]], F.unitsMin, (v) => { F.unitsMin = v; }));
      b.appendChild(toggleRow("そのほか", [["noBus", "バス便は除く"], ["priority", "優遇抽せんあり"]]));
    }
  }
  function renderFilter() {
    const b = $("popBody"); b.innerHTML = "";
    for (const [k, title] of SECTIONS) {
      const sec = document.createElement("div"); sec.className = "acc" + (openSec === k ? " open" : ""); sec.dataset.sec = k;
      const v = summaryOf(k);
      sec.innerHTML = `<button type="button" class="acc-head" aria-expanded="${openSec === k}"><span class="acc-t">${esc(title)}</span><span class="acc-v${v ? " set" : ""}">${esc(v || "指定なし")}</span><span class="acc-c">›</span></button><div class="acc-body"></div>`;
      if (openSec === k) buildBody(k, sec.querySelector(".acc-body"));
      sec.querySelector(".acc-head").addEventListener("click", () => { openSec = openSec === k ? null : k; renderFilter(); const el = b.querySelector(`[data-sec="${k}"]`); if (openSec) b.scrollTop = Math.max(0, el.offsetTop - 8); });   // scrollIntoView は画面全体まで動かすので使わない
      b.appendChild(sec);
    }
    refreshFilterHead();
  }
  // 選ぶたびに：各項目の右の文字と「この条件で見る（N件）」を更新
  function refreshFilterHead() {
    $("popBody").querySelectorAll(".acc").forEach((sec) => { const v = summaryOf(sec.dataset.sec), el = sec.querySelector(".acc-v"); el.textContent = v || "指定なし"; el.classList.toggle("set", !!v); });
    const n = ITEMS.filter(matches).length;
    $("popDone").textContent = `${n.toLocaleString("ja-JP")}件を見る`;
    $("popN").textContent = "";
  }
  $("popBody").addEventListener("click", (e) => { if (!e.target.closest(".acc-head")) setTimeout(refreshFilterHead, 0); });
  $("popBody").addEventListener("change", () => setTimeout(refreshFilterHead, 0));
  function openFilter(k) {
    closePages(); openSec = k ?? null;
    renderFilter(); $("popover").hidden = false; $("scrim").hidden = false; setTab("filter");
  }
  const openPopover = openFilter;

  // 下のバー
  function setTab(t) { document.querySelectorAll("#bbar [data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === t)); }
  $("bbar").addEventListener("click", (e) => {
    const b = e.target.closest("[data-tab]"); if (!b) return;
    const t = b.dataset.tab;
    if (t === "filter") { if (!$("popover").hidden) { closePopover(); apply(); } else openFilter(); return; }
    if (!$("popover").hidden) { closePopover(); apply(); }
    if (t === "map") { closePages(); setTab("map"); return; }
    openPage(t === "cal" ? "pageCal" : "pageNotify");
  });

  function renderAreaBody(b) {
    b.innerHTML = "";
    const counts = new Map(), pc = new Map();
    ITEMS.forEach((r) => { if (!F.now || r._status === "open" || r._status === "anytime") { counts.set(r.city, (counts.get(r.city) || 0) + 1); pc.set(r.pref, (pc.get(r.pref) || 0) + 1); } });
    if (!areaRegion) areaRegion = (REGIONS.find(([, ps]) => ps.some((p) => F.prefs.has(p))) || REGIONS[1])[0];
    const sel = document.createElement("label"); sel.className = "region-sel";
    sel.innerHTML = `<span>地方</span><select>${REGIONS.map(([n, ps]) => `<option${n === areaRegion ? " selected" : ""}>${esc(n)}${ps.some((p) => PREFS.includes(p)) ? "" : "（準備中）"}</option>`).join("")}</select>`;
    sel.querySelector("select").addEventListener("change", (e) => { areaRegion = REGIONS[e.target.selectedIndex][0]; renderAreaBody(b); });
    b.appendChild(sel);
    const wrap = document.createElement("div"); wrap.className = "area-tree";
    const soon = [];
    for (const p of REGIONS.find(([n]) => n === areaRegion)[1]) {
      if (!PREFS.includes(p)) { soon.push(p); continue; }
      const on = F.prefs.has(p);
      const row = document.createElement("div"); row.className = "pref-row" + (on ? " open" : "");
      const head = document.createElement("label"); head.className = "ck pref";
      head.innerHTML = `<input type="checkbox"${on ? " checked" : ""}><span>${esc(p)}</span><small>${(pc.get(p) || 0).toLocaleString("ja-JP")}件</small>`;
      head.querySelector("input").addEventListener("change", (e) => {
        if (e.target.checked) F.prefs.add(p); else { F.prefs.delete(p); [...F.cities].forEach((c) => { if (CITY_PREF.get(c) === p) F.cities.delete(c); }); }
        renderAreaBody(b);
      });
      row.appendChild(head);
      if (on) {
        const cities = [...counts.keys()].filter((c) => CITY_PREF.get(c) === p).sort((a, z) => (z.endsWith("区") - a.endsWith("区")) || counts.get(z) - counts.get(a));
        const grid = document.createElement("div"); grid.className = "city-grid";
        if (!cities.length) grid.innerHTML = `<p class="hint">いま出せる市区町村がありません</p>`;
        for (const c of cities) {
          const l = document.createElement("label"); l.className = "ck";
          l.innerHTML = `<input type="checkbox"${F.cities.has(c) ? " checked" : ""}><span>${esc(c)}</span><small>${counts.get(c)}</small>`;
          l.querySelector("input").addEventListener("change", (e) => { if (e.target.checked) F.cities.add(c); else F.cities.delete(c); });
          grid.appendChild(l);
        }
        row.appendChild(grid);
      }
      wrap.appendChild(row);
    }
    if (soon.length) { const d = document.createElement("div"); d.className = "pref-soon"; d.innerHTML = `<b>準備中</b>${soon.map((p) => `<span>${esc(p)}</span>`).join("")}`; wrap.appendChild(d); }
    const h = document.createElement("p"); h.className = "hint"; h.textContent = "地方を選び、都道府県にチェックを入れると、その中の市区町村を選べます。何も選ばなければ全部です。いま載っているのは1都3県で、ほかの地域は順に増やします。";
    b.appendChild(wrap); b.appendChild(h);
  }
  function group(title, opts) { const g = document.createElement("div"); g.className = "opt-group"; g.innerHTML = `<h4>${esc(title)}</h4>`; const grid = document.createElement("div"); grid.className = "opt-grid"; opts.forEach((o) => grid.appendChild(o)); g.appendChild(grid); return g; }
  function opt(label, on, toggle) { const btn = document.createElement("button"); btn.type = "button"; btn.className = "opt"; btn.textContent = label; btn.setAttribute("aria-pressed", on); btn.addEventListener("click", () => { toggle(); btn.setAttribute("aria-pressed", btn.getAttribute("aria-pressed") !== "true"); }); return btn; }
  function closePopover() { $("popover").hidden = true; $("scrim").hidden = true; if (document.querySelectorAll(".page:not([hidden])").length === 0) setTab("map"); }
  $("popDone").addEventListener("click", () => { closePopover(); apply(); });
  $("popClose").addEventListener("click", () => { closePopover(); apply(); });
  $("scrim").addEventListener("click", () => { closePopover(); apply(); });
  $("popClear").addEventListener("click", () => {
    const q = F.q, round = F.round; RESET(); F.q = q; F.round = round; if (round) F.now = false;
    renderFilter();
  });

  /* ---------------- 検索 ---------------- */
  let qt = null;
  $("q").addEventListener("input", () => { clearTimeout(qt); $("qClear").hidden = !$("q").value; qt = setTimeout(() => { F.q = norm($("q").value); apply(); if (!DESKTOP.matches && F.q && !hiKey) $("drawer").classList.add("open"); }, 200); });
  $("qClear").addEventListener("click", () => { $("q").value = ""; $("qClear").hidden = true; F.q = ""; apply(); });

  /* ---------------- 引き出し ---------------- */
  const drawer = $("drawer");
  $("handle").addEventListener("click", () => drawer.classList.toggle("open"));
  $("handle").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); drawer.classList.toggle("open"); } });
  let y0 = null;
  $("handle").addEventListener("pointerdown", (e) => { y0 = e.clientY; });
  $("handle").addEventListener("pointerup", (e) => { if (y0 == null) return; const dy = e.clientY - y0; if (dy < -30) drawer.classList.add("open"); else if (dy > 30) drawer.classList.remove("open"); y0 = null; });
  $("sort").addEventListener("change", apply);

  /* ---------------- 物件の詳細（S4） ---------------- */
  function openDetail(id, fromList) {
    const r = byId.get(id); if (!r) return;
    if (activeId && markers.get(activeId)) markers.get(activeId).setIcon(pinIcon(byId.get(activeId), false));
    activeId = id;
    if (markers.get(id)) markers.get(id).setIcon(pinIcon(r, true));
    document.querySelectorAll(".item.active").forEach((el) => el.classList.remove("active"));
    document.querySelector(`.item[data-id="${CSS.escape(id)}"]`)?.classList.add("active");
    showActivePin(r);
    const rd = r._round;
    const gq = encodeURIComponent(`${r.pref}${r.address}`);
    const b = buildingInfo(r);
    const rows = [
      ...(r.geo_level === "city" ? [["地図の位置", "おおよそ（市区町村の中心）。正確な場所は公式ページで"]] : []),
      ["最寄駅", esc(r.access || "—")],
      ["入居できる人", esc(r.persons || "—")],
      ["建てた年", b.year],
      ["エレベーター", r.elevator ? "あり" : "なし"],
      ...(b.floors ? [["建物", esc(b.floors)]] : []),
      ...(b.floor ? [["募集する階", esc(b.floor)]] : []),
      ...(b.extra.length ? [["その他", b.extra.map(esc).join("<br>")]] : []),
    ];
    if (r.accident) rows.push(["事故内容", esc(r.accident)]);
    $("detailBody").innerHTML = `
      <h2>${esc(r.name)}</h2>
      <p class="addr"><span class="tag" style="--op:${colorOf(OPS[r.operator])}">${esc(r._opLabel)}</span><span class="tag cat">${esc(isInfo(r) ? "いまは募集期間外" : r.category)}</span>${esc(r.pref)}${esc(r.address)}</p>
      ${roundBox(r, rd)}
      <div class="kv-grid">
        <div class="kv"><div class="k">家賃（月）</div><div class="v">${r.rent_min != null ? `¥${yen(r.rent_min)}〜${yen(r.rent_max)}` : '<small>募集時に発表</small>'}</div></div>
        <div class="kv"><div class="k">間取り・広さ</div><div class="v wrap">${esc(r.layout.length > 22 ? r.layout.slice(0, 22) + "…" : r.layout) || "—"} ${r.area_text ? `<small>${esc(r.area_text)}㎡</small>` : ""}</div></div>
        <div class="kv"><div class="k">募集戸数</div><div class="v">${r.units != null ? `${r.units}戸` : '<small>募集時に発表</small>'}${typeof r.vacant_now === "number" ? `<small> いま空き${r.vacant_now}</small>` : ""}</div></div>
        <div class="kv"><div class="k">前回の倍率</div><div class="v">${r.ratio_prev != null ? `${r.ratio_prev}倍` : "—"}</div></div>
      </div>
      ${b.feats.length ? `<div class="feats">${b.feats.map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : ""}
      <h3 class="sec">建物と場所</h3>
      <table>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</table>
      <p class="cards-h">当選したら<span class="pr">PR</span></p>
      <div class="cards">
        ${affCard("move", "#", "引っ越し見積もり", "複数社を一括で比べる")}
        ${affCard("net", "#", "ネット回線", "入居日に合わせて開通")}
        ${affCard("power", "#", "電気・ガス", "まとめて申し込み")}
      </div>
      <p class="cards-h">落選したら、今すぐ入れる家<span class="pr">PR</span></p>
      <div class="cards">
        ${affCard("ur", safeUrl(urUrl(r)), `UR賃貸（${r.pref.replace(/[都県]$/, "")}）`, "礼金・仲介手数料なし。空き部屋を探す", true)}
        ${affCard("rent", "#", "家賃の安い賃貸", `${r.city}の近くで探す`)}
      </div>
      <p class="hint">「PR」の枠は広告です。リンク先で申し込みがあると、このサービスに紹介料が入ることがあります。</p>`;
    // この団地だけを見張る（LINEに「見張る 都道府県 団地名」を送る画面が開く。送ると、この団地が募集に入った日と締切3日前に届く）
    $("detailBody").querySelector(".round-box")?.insertAdjacentHTML("afterend", `<div class="line-cta slim watch"><span><b>LINE</b>でこの団地だけを見張る<small>募集に入った日と締切3日前に届きます</small></span><a class="line-btn" data-watch href="#">見張る</a></div>`);
    $("detailBody").querySelector(".watch")?.insertAdjacentHTML("afterend", `<button type="button" class="guide-cta" data-guide="${esc(r.operator)}"><span><b>申し込みの準備ガイド</b><small>必要なものと申し込み先（公式ページ）を案内します</small></span><i>›</i></button>`);
    setupLine();
    const wb = $("detailBody").querySelector("[data-watch]");
    if (wb) {
      if (SITE.line_id) { wb.href = `https://line.me/R/oaMessage/${encodeURIComponent(SITE.line_id)}/?${encodeURIComponent(`見張る ${r.pref} ${r.name}`)}`; wb.target = "_blank"; wb.rel = "noopener"; }
      else wb.addEventListener("click", (e) => { e.preventDefault(); toast(SITE.line_note || "LINE公式アカウントは準備中です"); });
    }
    $("detailFoot").innerHTML = `
      <div class="btn-row">
        <a class="btn ghost gmap" href="https://www.google.com/maps/search/?api=1&query=${gq}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true" width="18" height="18"><path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6a2.5 2.5 0 0 1 0 5.5z" fill="currentColor"/></svg>Googleマップ</a>
        <a class="btn official" href="${esc(safeUrl(r.official_url))}" target="_blank" rel="noopener">公式ページで申し込む ↗</a>
      </div>
      ${r.pdf_url ? `<div class="links"><span></span><a href="${esc(safeUrl(r.pdf_url))}" target="_blank" rel="noopener">募集案内PDF p.${esc(r.pdf_page)}</a></div>` : ""}`;
    $("detail").hidden = false; $("detailBody").scrollTop = 0;
    drawer.classList.add("hidden-by-detail");
    focusOn(r, true);   // シートを出してから、見えている範囲の中心にピンが来るよう寄せる
    $("detailFoot").querySelector(".official").addEventListener("click", () => { store.set("visitedOfficial", Date.now()); });
    $("detailBody").querySelectorAll("[data-pick]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); toast("提携先のリンクは準備中です（試作版）"); }));
    $("detailBody").querySelector("[data-guide]")?.addEventListener("click", () => openGuide(r.operator));
  }
  // ---- 申し込みの準備ガイド：data/guide/<運営元>.json（公式の募集案内から作ったもの）を読んで出す ----
  const GUIDE = {};
  async function openGuide(opKey) {
    const op = OPS[opKey]; if (!op) return;
    openPage("pageGuide");
    const body = $("guideBody");
    body.innerHTML = `<p class="hint">読み込み中…</p>`;
    let g = GUIDE[opKey];
    if (!g) { try { g = GUIDE[opKey] = await fetch(`data/guide/${encodeURIComponent(opKey)}.json?v=${VERSION}`).then((x) => x.ok ? x.json() : null); } catch { g = null; } }
    const name = op.long || op.label;
    if (!g) { body.innerHTML = `<h3 class="g-op">${esc(name)}</h3><p>この運営元のガイドは準備中です。申し込み方法は公式ページで確かめてください。</p><a class="btn official" href="${esc(safeUrl(op.url))}" target="_blank" rel="noopener">公式ページへ ↗</a>`; return; }
    // いま受付中・次の募集（カレンダーと同じデータ）
    const now = ROUNDS.filter((x) => x.operator === opKey && x.apply_to && new Date(x.apply_to + "T23:59:59") >= TODAY).sort((a, z) => (a.apply_from || "").localeCompare(z.apply_from || ""))[0];
    const when = now ? `<div class="g-when"><b>${esc(now.label)}</b><span>申込期間 ${esc(fmtDate(now.apply_from))}〜${esc(fmtDate(now.apply_to))}</span></div>` : "";
    const checked = (g.sources || []).map((s) => s.checked).filter(Boolean).sort().pop() || "";
    // 条件や書類の中身はここで言い換えない（間違って伝えないため）。公式のどのページを見ればよいかだけを案内する
    const link = (url, t, sub, cls) => url ? `<a class="g-link${cls ? " " + cls : ""}" href="${esc(safeUrl(url))}" target="_blank" rel="noopener"><span><b>${t}</b><small>${sub}</small></span><i>↗</i></a>` : "";
    body.innerHTML = `
      <h3 class="g-op"><i class="dot" style="--op:${colorOf(op)}"></i>${esc(name)}</h3>
      <p class="g-lead">申し込める人の条件や必要な書類は、募集ごとに変わることがあります。間違いのないよう、公式のページを直接ご案内します。</p>
      ${when}
      ${(g.how || []).length ? `<div class="g-how"><span>申し込み方法</span>${g.how.map((t) => `<b>${esc(t)}</b>`).join("")}</div>` : ""}
      <div class="g-links">
        ${link(g.docs_url, "申し込める人と必要なもの", "条件・必要な書類はこちら（公式）")}
        ${g.guide_url && g.guide_url !== g.docs_url ? link(g.guide_url, "募集案内（しおり）", "申し込む前に一度読んでおくもの（公式）") : ""}
        ${link(g.apply_url || op.url, "申し込みはこちら", "公式の受付ページへ", "main")}
      </div>
      <div class="line-cta slim"><span><b>LINE</b>で締切3日前に知らせる</span><a class="line-btn" data-line href="#">友だち追加</a></div>
      <p class="g-src">リンク先は${checked ? ` ${esc(fmtDate(checked))} に` : ""}確かめた公式のページです。開けないときや内容が変わっているときは、${esc(name)}の公式ページから探してください。</p>`;
    setupLine();
  }
  // 提携カード：上に絵（img/cards/<種類>.webp。パスやクラス名に aff を入れない（広告ブロッカーの一般規則で display:none にされ、絵が消える。2026-11-14 判明）。site.json の aff_img に載っている種類だけ。無ければ色の帯だけ）、下に名前と一言
  function affCard(kind, href, title, sub, real) {
    const p = real ? null : affPick(kind);   // 提携先が決まっていれば、その広告リンク（A8.net）に差し替える
    let pixel = "";
    if (p) { href = `https://px.a8.net/svt/ejp?a8mat=${p.a8mat}`; sub = p.sub || sub; real = true; pixel = `<img class="a8px" src="https://${p.px}.a8.net/0.gif?a8mat=${p.a8mat}" width="1" height="1" alt="">`; }
    return `<a class="card pick-${kind}" href="${esc(href)}"${real ? ` target="_blank" rel="${p ? "nofollow sponsored noopener" : "noopener"}"` : ` data-pick="${kind}"`}><span class="card-img">${(SITE.aff_img || []).includes(kind) ? `<img src="img/cards/${kind}.webp?v=${VERSION}" alt="" loading="lazy">` : ""}</span><b>${esc(title)}</b><span class="card-sub">${esc(sub)}</span><span class="card-go">見てみる ›</span>${pixel}</a>`;
  }
  // 募集の状態：いま申し込めるか・いつまでか・決め方（抽せん／先着順）・抽せん日
  function roundBox(r, rd) {
    if (!rd) return "";
    const st = isInfo(r) ? "info" : roundStatus(rd);
    const how = /先着/.test(rd.kind || rd.label || "") ? "先着順（早い者勝ち）" : /抽/.test(rd.kind || "") ? "抽せん" : (rd.kind || "");
    const howNote = rd.kind && how && rd.kind !== how ? rd.kind : "";
    let badge = "", line = "", bar = "";
    if (st === "open") {
      const left = daysLeft(rd.apply_to), total = (dayOf(rd.apply_to) - dayOf(rd.apply_from)) / 86400000 + 1, done = (TODAY - dayOf(rd.apply_from)) / 86400000 + 1;
      badge = `<span class="badge">受付中 あと${left}日</span>`;
      line = `申込期間 <b>${fmtMD(rd.apply_from)} 〜 ${fmtMD(rd.apply_to)}</b>`;
      bar = `<div class="bar"><i style="width:${Math.min(100, Math.round(done / total * 100))}%"></i></div>`;
    } else if (st === "anytime") { badge = `<span class="badge ok">いつでも申し込める</span>`; line = rd.apply_to ? `受付は <b>${fmtMD(rd.apply_to)}</b> まで` : "空きが出しだい、随時受付"; }
    else if (st === "upcoming") { badge = `<span class="badge soon">もうすぐ</span>`; line = rd.apply_from ? `申込期間 <b>${fmtMD(rd.apply_from)} 〜 ${rd.apply_to ? fmtMD(rd.apply_to) : ""}</b>` : `次の募集 ${esc(rd.expected || "は公式発表待ち")}`; }
    else if (st === "info") { badge = `<span class="badge gray">いまは募集期間外</span>`; line = rd.apply_from ? `次の募集 <b>${fmtMD(rd.apply_from)}〜</b>（この団地が出るかは募集時に公式で）` : `次の募集 ${esc(rd.expected || "は公式で")}`; }
    else { badge = `<span class="badge gray">受付終了</span>`; line = `この募集は ${rd.apply_to ? fmtMD(rd.apply_to) : ""} で締め切りました`; }
    const rowsR = [];
    if (how) rowsR.push(["決め方", esc(how)]);
    if (rd.lottery) rowsR.push(["抽せん日", fmtMD(rd.lottery)]);
    if (howNote) rowsR.push(["申込のしかた", esc(howNote)]);
    if (r._notes?.length) rowsR.push(["注意", r._notes.map(esc).join("<br>")]);
    return `<div class="round-box"><div class="rb-head">${badge}<span class="rb-name">${esc(rd.label)}</span></div><div class="rb-line">${line}</div>${bar}
      ${rowsR.length ? `<dl>${rowsR.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>` : ""}</div>`;
  }
  // 建物の情報を、読める言葉に分ける（住戸型式などの記号は出さない）
  const ERA = { S: 1925, H: 1988, R: 2018, 昭和: 1925, 平成: 1988, 令和: 2018 };
  function buildingInfo(r) {
    const nowY = TODAY.getFullYear();
    let year = "—";
    if (r.built_from) { const age = nowY - r.built_from; year = `${r.built_from}年${/〜|・/.test(r.built || "") ? "ごろ〜" : ""}（築${age}年）`; }
    const feats = [], extra = [], notes = [];
    let floors = "", floor = "";
    const toks = String(r.spec || "").split(/[・、\u3000]+|\s{1,}/).map((t) => t.trim()).filter(Boolean);
    for (const t of toks) {
      if (/バリアフリー|段差なし/.test(t)) feats.push("バリアフリー");
      else if (/車い?す/.test(t)) feats.push("車いす向け");
      else if (/風呂：?バランス釜/.test(t)) feats.push("風呂あり（バランス釜）");
      else if (/風呂あり/.test(t)) feats.push("風呂あり");
      else if (/都市ガス/.test(t)) feats.push("都市ガス");
      else if (/駐車場あり/.test(t)) feats.push(/申込済/.test(t) ? "駐車場（申込済）" : "駐車場あり");
      else if (/住戸改善|スーパーリフォーム|リフォーム/.test(t)) { const m = /\((平成|昭和|令和)?(\d+)/.exec(t); feats.push(m ? `室内リフォーム済（${m[1] ? (ERA[m[1]] + +m[2]) : ""}年）`.replace("（年）", "") : "室内リフォーム済"); }
      else if (/(\d+)階建/.test(t)) floors = `${/(\d+)階建/.exec(t)[1]}階建て`;
      else if (/受付|抽選|抽せん|追加住宅/.test(t)) notes.push(t.replace(/^(\d+)月追加住宅（(.*)）$/, "$1月に追加された住宅（$2）"));
      else if (/^総戸数/.test(t)) extra.push(t.replace("総戸数", "団地全体 ").replace("戸", "戸"));
      else if (/^共益費/.test(t)) extra.push(t.replace("共益費", "共益費 月"));
      else if (/ミニキッチン/.test(t)) extra.push(t.replace(/。$/, ""));
      // 住戸型式・A1 などの記号、棟数、構造、読み仮名は出さない
    }
    if (/階/.test(r.floor || "")) floor = r.floor.replace(/^.*\//, "");
    if (/(\d+)・?.*階建/.test(r.floor || "") && !floors) floors = (/[\d・]+階建て?/.exec(r.floor) || [""])[0];
    if (r.barrier_free && !feats.includes("バリアフリー")) feats.unshift("バリアフリー");
    r._notes = notes;
    return { year, feats: [...new Set(feats)], extra, floors, floor };
  }
  const UR_PREF = { "東京都": "tokyo", "神奈川県": "kanagawa", "埼玉県": "saitama", "千葉県": "chiba" };
  const urUrl = (r) => `https://www.ur-net.go.jp/chintai/kanto/${UR_PREF[r.pref] || ""}/`;
  function closeDetail() { $("detail").hidden = true; $("detail").classList.remove("full"); drawer.classList.remove("hidden-by-detail"); showActivePin(null); }
  // 詳細シートのつまみ：タップで全画面に広げる／戻す。上下のスワイプでも
  const dh = $("detail").querySelector(".handle");
  dh.addEventListener("click", () => $("detail").classList.toggle("full"));
  let dy0 = null;
  dh.addEventListener("pointerdown", (e) => { dy0 = e.clientY; });
  dh.addEventListener("pointerup", (e) => { if (dy0 == null) return; const dy = e.clientY - dy0; if (dy < -30) $("detail").classList.add("full"); else if (dy > 30) ($("detail").classList.contains("full") ? $("detail").classList.remove("full") : closeDetail()); dy0 = null; });
  $("detailClose").addEventListener("click", closeDetail);
  map.on("click", () => { if (!$("detail").hidden) closeDetail(); });

  // 公式ページから戻ってきたら、1回だけ通知登録を勧める
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (!store.get("visitedOfficial") || store.get("nudged") || store.get("subscribed")) return;
    store.set("nudged", true); $("nudge").hidden = false;
  });
  $("nudgeYes").addEventListener("click", () => { $("nudge").hidden = true; openPage("pageNotify"); });
  $("nudgeNo").addEventListener("click", () => { $("nudge").hidden = true; });

  /* ---------------- ページ（S5・S6・S7） ---------------- */
  function openPage(id) { closePopover(); closePages(); setTab(id === "pageCal" ? "cal" : id === "pageNotify" ? "notify" : ""); if (id === "pageCal") renderCal(); if (id === "pageAbout") renderUseLog(); $(id).hidden = false; $(id).querySelector(".page-body").scrollTop = 0; }
  function closePages() { document.querySelectorAll(".page").forEach((p) => (p.hidden = true)); if ($("popover").hidden) setTab("map"); }
  document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closePages));
  document.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => openPage(b.dataset.open)));

  /* ---------------- 募集の予定：1年の早見表（都県 → 種別で絞る。横スクロールなし） ---------------- */
  const CAL = { pref: null, hide: undefined, sel: null };   // hide: チェックを外した運営元の集合／sel: 押した月 { op, m }
  const md = (d) => `${d.getMonth() + 1}/${d.getDate()}`;
  const monthEnd = (y, m) => new Date(y, m, 0), monthStart = (y, m) => new Date(y, m - 1, 1);
  // 日付のある募集と、例年の月からの見込み（例年）を1つの並びにする
  function calEvents() {
    const ev = [];
    for (const r of ROUNDS) {
      if (r.anytime) ev.push({ op: r.operator, kind: "any", r });
      else if (r.apply_from && r.apply_to) ev.push({ op: r.operator, kind: "fix", from: dayOf(r.apply_from), to: dayOf(r.apply_to), r, anyRange: /随時|常時/.test(r.label) });
      else ev.push({ op: r.operator, kind: "unk", r });
    }
    const used = new Set();
    const parseDays = (t) => { const m = /(\d+)日〜(\d+)日/.exec(t || ""); if (m) return [+m[1], +m[2]]; if (/中旬/.test(t) && !/上旬/.test(t)) return [10, 24]; return [1, 15]; };
    for (const [k, op] of Object.entries(OPS)) {
      const sc = op.schedule || {}; if (!sc.months || !sc.months.length) continue;
      const [d1, d2] = parseDays(sc.days);
      for (let i = 0; i < 13; i++) {
        const y = TODAY.getFullYear() + Math.floor((TODAY.getMonth() + i) / 12), m = (TODAY.getMonth() + i) % 12 + 1;
        if (!sc.months.includes(m)) continue;
        if (ev.some((e) => e.op === k && e.kind === "fix" && !e.anyRange && e.from.getFullYear() === y && e.from.getMonth() + 1 === m)) continue;
        const to = new Date(y, m - 1, Math.min(d2, 28)); if (to < TODAY) continue;
        const unks = ev.filter((e) => e.op === k && e.kind === "unk" && !used.has(e));
        const unk = unks.find((e) => (e.r.expected || "").includes(`${y}年${m}月`)) || unks.find((e) => !e.r.expected || new RegExp(`(^|[^\\d])${m}月`).test(e.r.expected));
        if (unk) used.add(unk);
        ev.push({ op: k, kind: "exp", from: new Date(y, m - 1, d1), to, r: unk ? unk.r : null, how: sc.how, label: `${y}年${m}月の募集（例年の時期）` });
      }
    }
    // 例年の枠に入らなかった未発表の募集は「発表待ち」として残す（expected の「YYYY年M月」があればその月に置く）
    for (const e of ev) {
      if (e.kind !== "unk" || used.has(e)) continue;
      const m = /(\d{4})年(\d{1,2})月/.exec(e.r.expected || "");
      e.from = m ? monthStart(+m[1], +m[2]) : TODAY; e.to = m ? monthEnd(+m[1], +m[2]) : TODAY;
    }
    return ev.filter((e) => !(e.kind === "unk" && used.has(e)));
  }
  const dl = (d) => Math.round((d - TODAY) / 86400000);
  // 例年の時期（exp）と発表待ち（unk）は日付が確定していないので、今日がその中でも「受付中」にはしない（up のまま）
  const evStatus = (e) => e.kind === "any" ? "any" : e.kind === "unk" ? "up" : e.kind === "exp" ? (TODAY <= e.to ? "up" : "closed") : TODAY < e.from ? "up" : TODAY <= e.to ? "open" : "closed";
  function renderCal() {
    const stored = store.get("cal") || {};
    if (!CAL.pref) CAL.pref = (F.prefs.size === 1 ? [...F.prefs][0] : null) || stored.pref || "東京都";
    if (!["all", ...PREFS].includes(CAL.pref)) CAL.pref = "東京都";
    if (CAL.hide === undefined) CAL.hide = new Set(Array.isArray(stored.hide) ? stored.hide.filter((k) => OPS[k]) : []);   // 外した運営元は最初の1回だけ読む（空＝全部表示）
    const EV = calEvents();
    // 1月〜12月で固定。今月より前の月は「来年のその月」を見せる（今年すでに締め切った分は出さない）
    const curM = TODAY.getMonth() + 1, curY = TODAY.getFullYear();
    const months = [...Array(12)].map((_, i) => ({ m: i + 1, y: i + 1 >= curM ? curY : curY + 1 }));
    const inPref = Object.keys(OPS).filter((k) => CAL.pref === "all" || !OPS[k].pref || OPS[k].pref === CAL.pref);
    store.set("cal", { pref: CAL.pref, hide: [...CAL.hide] });
    const allIn = [...inPref].sort((a, z) => KINDS.indexOf(OPS[a].label) - KINDS.indexOf(OPS[z].label));   // この地域の運営元ぜんぶ
    const ops = allIn.filter((k) => !CAL.hide.has(k));                                                      // チェックが付いているものだけ見せる
    const nameOf = (k) => (CAL.pref !== "all" && OPS[k].label === "県営") ? "県営" : shortOp(OPS[k]);
    const countOf = (rid) => ITEMS.filter((x) => x.round_id === rid).length;
    const yearStrip = curM === 1 ? `<span>${curY}年</span>`
      : `<span class="next" style="grid-column:1/${curM}">${curY + 1}年</span><span style="grid-column:${curM}/13">${curY}年</span>`;

    let h = `<div class="cal-ctl"><label class="cal-pref">地域 <select id="calPref"><option value="all"${CAL.pref === "all" ? " selected" : ""}>1都3県すべて</option>${REGIONS.map(([n, ps]) => `<optgroup label="${esc(n)}">${ps.map((p) => PREFS.includes(p) ? `<option value="${esc(p)}"${CAL.pref === p ? " selected" : ""}>${esc(p)}</option>` : `<option disabled>${esc(p)}（準備中）</option>`).join("")}</optgroup>`).join("")}</select></label>
</div>
      ${allIn.length > 1 ? `<div class="cal-ops-h">表示する運営元（チェックで選ぶ）</div><div class="cal-ops" role="group" aria-label="表示する運営元"><label class="chip all${ops.length === allIn.length ? " on" : ""}"><input type="checkbox" data-all${ops.length === allIn.length ? " checked" : ""}>すべて</label>${allIn.map((k) => `<label class="chip${CAL.hide.has(k) ? "" : " on"}" style="--op:${colorOf(OPS[k])}"><input type="checkbox" data-op="${esc(k)}"${CAL.hide.has(k) ? "" : " checked"}><i class="dot"></i>${esc(nameOf(k))}</label>`).join("")}</div>` : ""}
      <div class="cal-grid-head"><div class="cal-years">${yearStrip}</div>
      <div class="cal-mark">${months.map(({ m }) => `<span>${m === curM ? "今月" : ""}</span>`).join("")}</div></div>`;
    if (!ops.length) h += `<p class="hint">${allIn.length ? "表示する運営元にチェックを入れてください" : "この地域の運営元はまだありません"}</p>`;
    // 各運営元：1行目に名前と「いま／次」、2行目に12個の月ブロック。押した月の中身は下に出る
    for (const k of ops) {
      const op = OPS[k], es = EV.filter((e) => e.op === k), col = colorOf(op);
      const openE = es.filter((e) => evStatus(e) === "open" && !e.anyRange).sort((a, z) => a.to - z.to);
      const upE = es.filter((e) => evStatus(e) === "up" && !e.anyRange).sort((a, z) => a.from - z.from);
      const anyE = es.find((e) => e.kind === "any" || (e.anyRange && evStatus(e) !== "closed"));
      const anyOpen = anyE && (anyE.kind === "any" || evStatus(anyE) === "open");
      let stat = "";
      if (openE.length) stat = `<span class="badge">受付中 あと${daysLeft(openE[0].r.apply_to)}日</span>`;
      else if (upE.length) { const e = upE[0]; stat = `<span class="badge ${dl(e.from) <= 30 ? "soon" : "gray"}">${e.kind === "fix" ? `${md(e.from)}から` : `次は${e.from.getMonth() + 1}月ごろ`}</span>`; }
      else if (!anyE) stat = `<span class="badge gray">時期は未発表</span>`;
      if (anyOpen) stat += `<span class="badge ok">いつでも</span>`;
      else if (anyE) stat += `<span class="badge gray">先着順は${anyE.from.getMonth() + 1}月から</span>`;
      const selM = CAL.sel?.op === k ? CAL.sel.m : null;
      h += `<div class="cal-op" style="--op:${col}" data-op="${esc(k)}"><div class="cal-head"><i class="dot"></i><b>${esc(nameOf(k))}</b>${stat}</div><div class="cal-blocks">`;
      const inMonth = (y, m) => es.filter((e) => (e.kind === "fix" || e.kind === "exp" || e.kind === "unk") && !e.anyRange && evStatus(e) !== "closed" && e.from <= monthEnd(y, m) && e.to >= monthStart(y, m));
      for (const { m, y } of months) {
        const inM = inMonth(y, m);
        const anyHere = anyE && (anyE.kind === "any" || (anyE.from <= monthEnd(y, m) && anyE.to >= monthStart(y, m)));
        let st = "";
        if (inM.some((e) => evStatus(e) === "open")) st = "open";
        else if (inM.some((e) => e.kind === "fix")) st = "fix";
        else if (inM.length) st = "exp";
        else if (anyHere) st = "any";
        const has = !!(inM.length || anyHere);
        h += `<button type="button" class="blk${st ? " " + st : ""}${m === curM ? " now" : ""}${selM === m ? " sel" : ""}" data-m="${m}" data-y="${y}"${has ? "" : " disabled"} aria-label="${m}月${st ? "：" + { open: "受付中", fix: "申込期間（確定）", exp: "例年の時期", any: "いつでも" }[st] : ""}">${m}</button>`;
      }
      h += `</div>`;
      if (selM) {
        const y = months.find((x) => x.m === selM).y;
        const inM = inMonth(y, selM), anyHere = anyE && (anyE.kind === "any" || (anyE.from <= monthEnd(y, selM) && anyE.to >= monthStart(y, selM)));
        const list = [...inM, ...(anyHere ? [anyE] : [])];
        const sc = op.schedule || {};
        const subtxt = sc.months?.length ? `例年 ${sc.months.join("・")}月${sc.days ? "（" + sc.days + "）" : ""}・${sc.how || ""}${sc.anytime_note ? "／" + sc.anytime_note : ""}` : (sc.anytime_note || sc.note || "");
        h += `<div class="cal-pop"><div class="cal-pop-h"><b>${y}年${selM}月</b><span>${esc(nameOf(k))}</span><button type="button" class="cal-pop-x" aria-label="閉じる">×</button></div>
          ${list.map((e) => evHtml(e, countOf)).join("") || `<p class="hint">この月の募集はありません</p>`}
          ${subtxt ? `<div class="cal-sub">${esc(subtxt)}</div>` : ""}<div class="cal-official"><button type="button" class="linkish" data-guide="${esc(k)}">申し込みの準備ガイド</button>　<a href="${esc(safeUrl(op.url))}" target="_blank" rel="noopener">${esc(nameOf(k))}の公式ページ ↗</a></div></div>`;
      }
      h += `</div>`;
    }
    // 凡例は運営元の色を使わない（灰色）。色は運営元ごと、形が状態
    h += `<div class="legend" style="--op:#4a5563"><span><i class="open">11</i>受付中</span><span><i class="fix">11</i>申込期間が確定</span><span><i class="exp">11</i>例年の時期（見込み）</span><span><i class="any">11</i>いつでも申し込める</span><span><i class="now">11</i>今月</span><span><i>11</i>募集なし</span></div>
      <p class="cal-note">ブロックの色は運営元ごと（名前の左の●と同じ色）。色のついた月を押すと、申込期間や抽せん日が見られます。${curM > 1 ? `左の1〜${curM - 1}月は来年（${curY + 1}年）の予定です。` : ""}${DATA_DATE ? `データは月・木の朝に自動更新（最終 ${DATA_DATE}）。` : ""}</p>
      <div class="line-cta"><span><b>LINE</b>で「募集が始まった」「締切3日前」を受け取る。見逃しゼロに</span><a class="line-btn" data-line href="#">友だち追加</a></div>
      <button type="button" class="btn ghost" id="calNotify" style="width:100%;margin-top:10px">お知らせの受け取り方を見る</button>`;
    $("calBody").innerHTML = h;
    setupLine();
    $("calPref").addEventListener("change", (e) => { CAL.pref = e.target.value; CAL.sel = null; renderCal(); });
    $("calBody").querySelectorAll(".cal-ops input[data-op]").forEach((c) => c.addEventListener("change", () => { c.checked ? CAL.hide.delete(c.dataset.op) : CAL.hide.add(c.dataset.op); CAL.sel = null; renderCal(); }));
    const allChk = $("calBody").querySelector(".cal-ops input[data-all]");
    if (allChk) allChk.addEventListener("change", () => { allIn.forEach((k) => allChk.checked ? CAL.hide.delete(k) : CAL.hide.add(k)); CAL.sel = null; renderCal(); });
    $("calBody").querySelectorAll(".blk:not([disabled])").forEach((b) => b.addEventListener("click", () => {
      const k = b.closest(".cal-op").dataset.op, m = +b.dataset.m;
      CAL.sel = (CAL.sel?.op === k && CAL.sel.m === m) ? null : { op: k, m };
      const top = $("calBody").scrollTop; renderCal(); $("calBody").scrollTop = top;
      const pop = $("calBody").querySelector(".cal-pop"); if (pop) { const r = pop.getBoundingClientRect(), br = $("calBody").getBoundingClientRect(); if (r.bottom > br.bottom) $("calBody").scrollBy({ top: Math.min(r.bottom - br.bottom + 12, r.top - br.top - 60), behavior: "smooth" }); }
    }));
    $("calBody").querySelectorAll(".cal-pop-x").forEach((b) => b.addEventListener("click", () => { CAL.sel = null; const top = $("calBody").scrollTop; renderCal(); $("calBody").scrollTop = top; }));
    $("calBody").querySelectorAll("[data-round]").forEach((b) => b.addEventListener("click", () => { F.round = b.dataset.round; F.now = false; closePages(); apply(); if (!DESKTOP.matches) drawer.classList.add("open"); }));
    $("calNotify").addEventListener("click", () => openPage("pageNotify"));
    $("calBody").querySelectorAll("[data-guide]").forEach((b) => b.addEventListener("click", () => openGuide(b.dataset.guide)));
  }
  // 1つの募集（確定・例年・いつでも）の説明と、地図で見る／公式ページ
  function evHtml(e, countOf) {
    const st = evStatus(e), r = e.r, url = safeUrl(r?.url || OPS[e.op].url);
    let title = "", sub = "", bar = "", badge = "";
    if (st === "open" && r?.apply_from && r?.apply_to) {
      const total = (e.to - e.from) / 86400000 + 1, done = (TODAY - e.from) / 86400000 + 1;
      title = r.label; badge = `<span class="badge">あと${daysLeft(r.apply_to)}日</span>`;
      sub = `申込 ${fmtMD(r.apply_from)} 〜 ${fmtMD(r.apply_to)}${r.lottery ? `・抽せん ${fmtMD(r.lottery)}` : ""}${r.units ? `・${r.units.toLocaleString("ja-JP")}戸` : ""}${r.kind ? `・${r.kind}` : ""}`;
      bar = `<div class="bar"><i style="width:${Math.min(100, Math.round((done / total) * 100))}%"></i></div>`;
    } else if (st === "any") { title = r.label; sub = r.kind || "いつでも（先着順）"; badge = `<span class="badge ok">いつでも</span>`; }
    else if (e.kind === "exp") { title = e.label; sub = `${r?.expected ? r.expected : `例年 ${md(e.from)}〜${md(e.to)}ごろ`}${e.how ? `・${e.how}` : ""}。日付は公式発表待ち`; badge = `<span class="badge gray">例年</span>`; }
    else if (e.kind === "unk") { title = r.label; sub = `${r.expected || "時期は未発表"}。日付は公式発表待ち`; badge = `<span class="badge gray">発表待ち</span>`; }
    else { title = r.label; sub = `申込 ${fmtMD(r.apply_from)} 〜 ${fmtMD(r.apply_to)}${r.lottery ? `・抽せん ${fmtMD(r.lottery)}` : ""}${r.kind ? `・${r.kind}` : ""}`; badge = `<span class="badge soon">${e.anyRange ? "先着順" : "確定"} ${daysLeft(r.apply_from)}日後から</span>`; }
    const n = r ? countOf(r.id) : 0;
    // 受付中・いつでも だけに「地図で見る」「公式ページ」。例年・発表待ちは説明だけ（公式ページは運営元ごとに1つ、下にまとめる）
    const acts = (st === "open" || st === "any")
      ? `${n ? `<button type="button" class="primary" data-round="${esc(r.id)}">地図で見る（${n.toLocaleString("ja-JP")}件）</button>` : ""}<a href="${esc(url)}" target="_blank" rel="noopener">公式ページ ↗</a>`
      : "";
    return `<div class="ev${acts ? "" : " quiet"}"><div class="row"><b>${esc(title)}</b>${badge}</div><div class="sub">${esc(sub)}${r?.note && e.kind !== "exp" ? `<br>${esc(r.note)}` : ""}</div>${bar}${acts ? `<div class="acts">${acts}</div>` : ""}</div>`;
  }

  // S6 通知登録（試作：まだ送信しない。登録内容は端末に保存するだけ）
  $("areaChips").addEventListener("click", (e) => { const c = e.target.closest(".chip"); if (!c) return; c.classList.toggle("on"); c.setAttribute("aria-pressed", c.classList.contains("on")); });
  const chosenPrefs = () => [...document.querySelectorAll("#areaChips .chip.on")].map((c) => c.dataset.pref);
  function setupLine() {
    const url = SITE.line_url || "";
    document.querySelectorAll("[data-line]").forEach((a) => {
      if (url) { a.href = url; a.target = "_blank"; a.rel = "noopener"; a.addEventListener("click", () => { store.set("subscribed", true); }); }
      else a.addEventListener("click", (e) => { e.preventDefault(); toast(SITE.line_note || "LINE公式アカウントは準備中です"); });
    });
    $("lineNote").textContent = url ? "友だち追加すると、すぐに都県を選ぶボタンが届きます。" : (SITE.line_note || "");
  }
  $("mailForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const list = store.get("subs") || []; list.push({ mail: $("mail").value, prefs: chosenPrefs(), at: new Date().toISOString() }); store.set("subs", list); store.set("subscribed", true);
    $("mail").value = ""; toast(`登録しました（${chosenPrefs().map((p) => p.replace(/[都県]$/, "")).join("・") || "地域なし"}）`);
    $("notifyProto").textContent = "試作版のため、まだお知らせは届きません。登録内容はこの端末にだけ保存しています。";
  });
  $("notifyProto").textContent = "試作版：登録の仕組みを確かめる段階です。まだお知らせは届きません。";

  // 05 価値検証：使った日と一言メモを端末に残す（送信はしない）
  const todayKey = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  (function logUse() { const log = store.get("useLog") || {}; if (!log[todayKey()]) { log[todayKey()] = { memo: "" }; store.set("useLog", log); } })();
  function renderUseLog() {
    const log = store.get("useLog") || {}; const days = Object.keys(log).sort();
    $("useLog").innerHTML = `使った日：${days.length}日` + (days.length ? "<br>" + days.map((d) => `${esc(d)}${log[d].memo ? `：${esc(log[d].memo)}` : ""}`).join("<br>") : "");
  }
  $("memoForm").addEventListener("submit", (e) => { e.preventDefault(); const log = store.get("useLog") || {}; log[todayKey()] = { memo: $("memo").value.trim() }; store.set("useLog", log); $("memo").value = ""; renderUseLog(); toast("メモを残しました"); });

  function buildAbout() {
    renderUseLog();
    if ($("ver")) $("ver").textContent = VERSION;
    if ($("dataDate")) $("dataDate").textContent = DATA_DATE || "—";
    $("aboutSources").innerHTML = Object.values(OPS).map((o) => `<li><a href="${esc(safeUrl(o.url))}" target="_blank" rel="noopener">${esc(o.long)}</a></li>`).join("");
  }

  /* ---------------- トースト ---------------- */
  let tt = null;
  function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(tt); tt = setTimeout(() => (t.hidden = true), 2600); }

  function bindUI() { /* 初期化後に必要なもの（今は apply 内で完結） */ }
})();
