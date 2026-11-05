/* 住まいのSmiley 試作版（静的サイト・ビルドなし） */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const yen = (n) => (n == null ? "—" : n.toLocaleString("ja-JP"));
  const norm = (s) => String(s || "").normalize("NFKC").toLowerCase().replace(/\s+/g, "");
  const PAGE = 50;
  const DESKTOP = window.matchMedia("(min-width: 900px)");
  const TODAY = new Date(); TODAY.setHours(0, 0, 0, 0);
  const dayOf = (s) => { const d = new Date(s + "T00:00:00"); return d; };
  const daysLeft = (s) => Math.round((dayOf(s) - TODAY) / 86400000);
  const fmtMD = (s) => { const d = dayOf(s); return `${d.getMonth() + 1}/${d.getDate()}（${"日月火水木金土"[d.getDay()]}）`; };
  const store = { get: (k) => { try { return JSON.parse(localStorage.getItem("smiley:" + k)); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem("smiley:" + k, JSON.stringify(v)); } catch {} } };

  let OPS = {}, ROUNDS = [], ITEMS = [], byId = new Map(), markers = new Map();
  let filtered = [], shown = 0, activeId = null;
  const F = { now: true, prefs: new Set(), cities: new Set(), rentMax: null, layouts: new Set(), ops: new Set(), single: false, ev: false, q: "", round: null,
    builtFrom: null, areaMin: null, ratioMax: null, walkMax: null, noBus: false, bf: false, priority: false, unitsMin: null, vacant: false, cats: new Set() };
  const RESET = () => Object.assign(F, { prefs: new Set(), cities: new Set(), rentMax: null, layouts: new Set(), ops: new Set(), single: false, ev: false, q: "", round: null, now: true, builtFrom: null, areaMin: null, ratioMax: null, walkMax: null, noBus: false, bf: false, priority: false, unitsMin: null, vacant: false, cats: new Set() });
  const LAYOUTS = ["1DK", "1LDK", "2K", "2DK", "2LDK", "3DK", "3LDK", "4DK"];

  /* ---------------- 地図 ---------------- */
  const map = L.map("map", { zoomControl: false, zoomSnap: 0.5, maxZoom: 17, tap: true, attributionControl: true });
  map.fitBounds([[35.45, 139.1], [35.92, 139.95]]);
  L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
    maxZoom: 18, updateWhenZooming: false, attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">国土地理院</a>',
  }).addTo(map);
  L.control.zoom({ position: "topright", zoomInTitle: "拡大", zoomOutTitle: "縮小" }).addTo(map);

  // 境界（都内の色分け。関東全体の境界は工程06で）
  const PALETTE = ["#c9dbf3", "#cfe9d4", "#f7dfc0", "#e8d3eb", "#cde9ec"];
  ["bmask", "bfill", "bline", "blabel"].forEach((n, i) => { const p = map.createPane(n); p.style.zIndex = [210, 220, 380, 390][i]; p.style.pointerEvents = "none"; });
  fetch("data/boundaries.json").then((r) => r.json()).then((B) => {
    L.geoJSON(B.wards, { pane: "bfill", interactive: false, stroke: false, style: (f) => ({ fillColor: PALETTE[f.properties.c % 5], fillOpacity: 0.45 }) }).addTo(map);
    L.geoJSON(B.wards, { pane: "bline", interactive: false, fill: false, style: { color: "#fff", weight: 1.6, opacity: 1 } }).addTo(map);
    L.geoJSON(B.outline, { pane: "bline", interactive: false, fill: false, style: { color: "#34475f", weight: 2, opacity: 0.8 } }).addTo(map);
    const labels = L.layerGroup(B.wards.features.map((f) => L.marker(f.properties.label, {
      pane: "blabel", interactive: false, keyboard: false,
      icon: L.divIcon({ className: "ward-label" + (f.properties.name.endsWith("区") ? " ku" : ""), html: `<span>${esc(f.properties.name)}</span>`, iconSize: [0, 0] }),
    })));
    const onZoom = () => { const z = map.getZoom(); z >= 10 ? labels.addTo(map) : labels.remove(); map.getContainer().classList.toggle("hide-ku", z < 10.5); map.getContainer().classList.toggle("labels-small", z < 11); };
    map.on("zoomend", onZoom); onZoom();
  }).catch(() => {});

  const cluster = L.markerClusterGroup({
    showCoverageOnHover: false, spiderfyOnMaxZoom: true, chunkedLoading: true,
    maxClusterRadius: (z) => (z >= 15 ? 36 : 56),
    iconCreateFunction(c) {
      const n = c.getChildCount(); const size = n < 10 ? 36 : n < 100 ? 44 : 52; const cls = n < 10 ? "s" : n < 100 ? "m" : "l";
      return L.divIcon({ html: `<div class="cluster ${cls}" style="width:${size}px;height:${size}px">${n}</div>`, className: "", iconSize: [size, size] });
    },
  });
  map.addLayer(cluster);
  const pinIcon = (r, active) => L.divIcon({ className: "pin-icon", html: `<div class="pin${active ? " active" : ""}" style="--op:${OPS[r.operator].color}"></div>`, iconSize: [24, 24], iconAnchor: [12, 30] });

  // 現在地
  let meMarker = null;
  $("btnLocate").addEventListener("click", () => {
    if (!navigator.geolocation) return toast("この端末では現在地を取得できません");
    $("btnLocate").classList.add("busy");
    map.locate({ setView: true, maxZoom: 14, enableHighAccuracy: true, timeout: 12000 });
  });
  map.on("locationfound", (e) => {
    $("btnLocate").classList.remove("busy");
    const icon = L.divIcon({ className: "", html: '<div class="me-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });
    if (meMarker) meMarker.setLatLng(e.latlng); else meMarker = L.marker(e.latlng, { icon, keyboard: false, interactive: false, zIndexOffset: 1000 }).addTo(map);
  });
  map.on("locationerror", () => { $("btnLocate").classList.remove("busy"); toast("現在地を取得できませんでした。位置情報の利用を許可してください。"); });

  /* ---------------- データ ---------------- */
  Promise.all([fetch("data/rounds.json").then((r) => r.json()), fetch("data/listings.json").then((r) => r.json())])
    .then(([rd, ld]) => init(rd, ld))
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

  function init(rd, ld) {
    OPS = rd.operators; ROUNDS = rd.rounds; ITEMS = ld.items;
    const roundById = new Map(ROUNDS.map((r) => [r.id, r]));
    ITEMS.forEach((r) => {
      byId.set(r.id, r);
      r._round = roundById.get(r.round_id) || null;
      r._status = r._round ? roundStatus(r._round) : "open";
      r._search = norm([r.name, r.address, r.access, r.city, r.stations.join(" ")].join(" "));
      r._opLabel = OPS[r.operator]?.label || r.operator;
    });
    buildAbout();
    const params = new URLSearchParams(location.search);
    if (params.get("round") && roundById.has(params.get("round"))) { F.round = params.get("round"); F.now = false; }
    bindUI();
    apply();
  }

  /* ---------------- 絞り込み ---------------- */
  function matches(r) {
    if (F.round) { if (r.round_id !== F.round) return false; }
    else if (F.now && !(r._status === "open" || r._status === "anytime")) return false;
    if (F.prefs.size && !F.prefs.has(r.pref)) return false;
    if (F.cities.size && !F.cities.has(r.city)) return false;
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
    if (F.cats.size && !F.cats.has(r.category)) return false;
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
    renderMarkers(); shown = 0; $("list").innerHTML = ""; renderMore(); renderCount(); renderChips();
  }
  function renderCount() {
    const n = filtered.length;
    const roundLabel = F.round ? (ROUNDS.find((r) => r.id === F.round)?.label || "") : "";
    $("count").innerHTML = `${n.toLocaleString("ja-JP")}件${roundLabel ? `<small>${esc(roundLabel)}</small>` : F.now ? "<small>今募集中</small>" : ""}`;
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
    li.innerHTML = `<b>${esc(r.name)}</b><span class="rent">¥${yen(r.rent_min)}〜</span>
      <span class="sub"><span class="tag" style="--op:${OPS[r.operator].color}">${esc(r._opLabel)}</span>${esc(r.layout)} ${esc(r.area_text)}㎡・${esc(walk)}${ratio}${r.single_ok ? "・単身可" : ""}</span>`;
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

  /* ---------------- チップ ---------------- */
  function renderChips() {
    const set = (k, txt) => { const c = document.querySelector(`.chip[data-chip="${k}"]`); c.classList.toggle("set", !!txt); c.querySelector(".v").textContent = txt || ""; };
    document.querySelector('.chip[data-chip="now"]').classList.toggle("on", F.now && !F.round);
    document.querySelector('.chip[data-chip="now"]').setAttribute("aria-pressed", F.now && !F.round);
    const area = F.cities.size ? (F.cities.size <= 2 ? [...F.cities].join("・") : `${F.cities.size}か所`) : F.prefs.size ? [...F.prefs].map((p) => p.replace(/[都県]$/, "")).join("・") : "";
    set("area", area);
    set("rent", F.rentMax != null ? `〜${(F.rentMax / 10000)}万円` : "");
    set("layout", F.layouts.size ? [...F.layouts].join("・") : "");
    set("op", F.ops.size ? [...F.ops].map((o) => OPS[o].long.replace(/住宅.*$/, "")).join("・") : "");
    set("built", F.builtFrom != null ? `${F.builtFrom}年〜` : "");
    const moreN = [F.areaMin != null, F.ratioMax != null, F.walkMax != null, F.noBus, F.bf, F.priority, F.unitsMin != null, F.vacant, F.cats.size > 0].filter(Boolean).length;
    set("more", moreN ? `${moreN}` : "");
    for (const k of ["single", "ev"]) { const c = document.querySelector(`.chip[data-chip="${k}"]`); c.classList.toggle("on", F[k]); c.setAttribute("aria-pressed", F[k]); }
    const any = F.prefs.size || F.cities.size || F.rentMax != null || F.layouts.size || F.ops.size || F.single || F.ev || F.round || F.q || F.builtFrom != null || moreN;
    $("chipReset").hidden = !any;
    document.documentElement.style.setProperty("--chips-h", $("chips").offsetHeight + "px");
  }
  window.addEventListener("resize", () => document.documentElement.style.setProperty("--chips-h", $("chips").offsetHeight + "px"));
  $("chips").addEventListener("click", (e) => {
    const c = e.target.closest(".chip"); if (!c) return;
    const k = c.dataset.chip;
    if (k === "now") { F.now = !F.now; F.round = null; apply(); return; }
    if (k === "single" || k === "ev") { F[k] = !F[k]; apply(); return; }
    if (c.id === "chipReset") { RESET(); $("q").value = ""; $("qClear").hidden = true; apply(); return; }
    openPopover(k);
  });
  $("chipReset").addEventListener("click", () => {});

  /* ---------------- 絞り込みのシート ---------------- */
  let popKey = null;
  const TITLES = { area: "地域", rent: "家賃の上限", layout: "間取り", op: "運営元", built: "築年", more: "もっと条件" };
  const selectRow = (label, options, cur, onChange) => {
    const g = document.createElement("div"); g.className = "opt-group"; g.innerHTML = `<h4>${esc(label)}</h4>`;
    const row = document.createElement("div"); row.className = "rent-row"; const sel = document.createElement("select");
    sel.innerHTML = options.map(([v, l]) => `<option value="${v}"${String(cur ?? "") === String(v) ? " selected" : ""}>${esc(l)}</option>`).join("");
    sel.addEventListener("change", () => onChange(sel.value === "" ? null : Number(sel.value)));
    row.appendChild(sel); g.appendChild(row); return g;
  };
  const toggleRow = (label, opts) => group(label, opts.map(([k, l]) => opt(l, F[k], () => { F[k] = !F[k]; })));
  function openPopover(k) {
    popKey = k; $("popTitle").textContent = TITLES[k]; const b = $("popBody"); b.innerHTML = "";
    if (k === "area") {
      const prefs = ["東京都", "神奈川県", "埼玉県", "千葉県"];
      b.appendChild(group("都県（いくつでも）", prefs.map((p) => opt(p.replace(/[都県]$/, ""), F.prefs.has(p), () => { F.prefs.has(p) ? F.prefs.delete(p) : F.prefs.add(p); }))));
      const counts = new Map(); ITEMS.forEach((r) => { if (r._status === "open" || r._status === "anytime") counts.set(r.city, (counts.get(r.city) || 0) + 1); });
      const cities = [...counts.keys()].sort((a, b) => (b.endsWith("区") - a.endsWith("区")) || counts.get(b) - counts.get(a));
      b.appendChild(group("区市町村（いくつでも）", cities.map((c) => opt(`${c} ${counts.get(c)}`, F.cities.has(c), () => { F.cities.has(c) ? F.cities.delete(c) : F.cities.add(c); }))));
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
      const ops = Object.keys(OPS);
      b.appendChild(group("いくつでも", ops.map((o) => opt(OPS[o].long, F.ops.has(o), () => { F.ops.has(o) ? F.ops.delete(o) : F.ops.add(o); }))));
    } else if (k === "built") {
      const y = new Date().getFullYear();
      b.appendChild(selectRow("この年より新しい建物", [["", "指定なし"], ...[2015, 2010, 2005, 2000, 1995, 1990, 1985, 1980, 1975, 1970].map((v) => [v, `${v}年以降（築${y - v}年以内）`])], F.builtFrom, (v) => { F.builtFrom = v; }));
      const h = document.createElement("p"); h.className = "hint"; h.textContent = "並び替えで「築年が新しい順／古い順」も選べます。"; b.appendChild(h);
    } else if (k === "more") {
      const cats = [...new Set(ITEMS.map((r) => r.category))];
      b.appendChild(group("募集の種類", cats.map((c) => opt(c, F.cats.has(c), () => { F.cats.has(c) ? F.cats.delete(c) : F.cats.add(c); }))));
      b.appendChild(selectRow("広さ", [["", "指定なし"], [30, "30㎡以上"], [35, "35㎡以上"], [40, "40㎡以上"], [50, "50㎡以上"], [60, "60㎡以上"]], F.areaMin, (v) => { F.areaMin = v; }));
      b.appendChild(selectRow("前回の倍率", [["", "指定なし"], [1, "1倍以下（ほぼ当たる）"], [3, "3倍以下"], [5, "5倍以下"], [10, "10倍以下"]], F.ratioMax, (v) => { F.ratioMax = v; }));
      b.appendChild(selectRow("駅から", [["", "指定なし"], [5, "徒歩5分以内"], [10, "徒歩10分以内"], [15, "徒歩15分以内"]], F.walkMax, (v) => { F.walkMax = v; }));
      b.appendChild(selectRow("募集戸数", [["", "指定なし"], [2, "2戸以上"], [5, "5戸以上"], [10, "10戸以上"]], F.unitsMin, (v) => { F.unitsMin = v; }));
      b.appendChild(toggleRow("そのほか", [["noBus", "バス便は除く"], ["bf", "バリアフリー"], ["priority", "優遇抽せんあり"], ["vacant", "いま空きあり"]]));
    }
    $("popover").hidden = false; $("scrim").hidden = false;
  }
  function group(title, opts) { const g = document.createElement("div"); g.className = "opt-group"; g.innerHTML = `<h4>${esc(title)}</h4>`; const grid = document.createElement("div"); grid.className = "opt-grid"; opts.forEach((o) => grid.appendChild(o)); g.appendChild(grid); return g; }
  function opt(label, on, toggle) { const btn = document.createElement("button"); btn.type = "button"; btn.className = "opt"; btn.textContent = label; btn.setAttribute("aria-pressed", on); btn.addEventListener("click", () => { toggle(); btn.setAttribute("aria-pressed", btn.getAttribute("aria-pressed") !== "true"); }); return btn; }
  function closePopover() { $("popover").hidden = true; $("scrim").hidden = true; }
  $("popDone").addEventListener("click", () => { closePopover(); apply(); });
  $("popClose").addEventListener("click", () => { closePopover(); apply(); });
  $("scrim").addEventListener("click", () => { closePopover(); apply(); });
  $("popClear").addEventListener("click", () => {
    if (popKey === "area") { F.prefs.clear(); F.cities.clear(); } if (popKey === "rent") F.rentMax = null; if (popKey === "layout") F.layouts.clear(); if (popKey === "op") F.ops.clear();
    if (popKey === "built") F.builtFrom = null;
    if (popKey === "more") Object.assign(F, { areaMin: null, ratioMax: null, walkMax: null, noBus: false, bf: false, priority: false, unitsMin: null, vacant: false, cats: new Set() });
    closePopover(); apply();
  });

  /* ---------------- 検索 ---------------- */
  let qt = null;
  $("q").addEventListener("input", () => { clearTimeout(qt); $("qClear").hidden = !$("q").value; qt = setTimeout(() => { F.q = norm($("q").value); apply(); if (!DESKTOP.matches && F.q) $("drawer").classList.add("open"); }, 200); });
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
    if (fromList && r.lat != null) { map.setView([r.lat, r.lon], Math.max(map.getZoom(), 15), { animate: true }); }
    else if (r.lat != null && !DESKTOP.matches) { map.panTo([r.lat, r.lon - 0], { animate: true }); }
    const rd = r._round;
    const deadline = rd && rd.apply_to ? `${fmtMD(rd.apply_to)}まで${daysLeft(rd.apply_to) >= 0 ? `<span class="deadline">あと${daysLeft(rd.apply_to)}日</span>` : ""}` : rd && rd.anytime ? "いつでも（先着順）" : "—";
    const gq = encodeURIComponent(`${r.pref}${r.address}`);
    const rows = [
      ["締切", deadline],
      ["抽せん日", rd && rd.lottery ? fmtMD(rd.lottery) : "—"],
      ["最寄駅", esc(r.access)],
      ["入居できる人", esc(r.persons || "—")],
      ["建物", `${esc(r.built || "—")}・エレベーター${r.elevator ? "有" : "無"}${r.barrier_free ? "・バリアフリー" : ""}${r.spec && !r.barrier_free ? "・" + esc(r.spec) : ""}`],
    ];
    if (r.floor) rows.push(["対象階", esc(r.floor)]);
    if (r.accident) rows.push(["事故内容", esc(r.accident)]);
    if (r.priority_lottery) rows.push(["優遇", "優遇抽せんあり"]);
    $("detailBody").innerHTML = `
      <h2>${esc(r.name)}</h2>
      <p class="addr"><span class="tag" style="--op:${OPS[r.operator].color}">${esc(r._opLabel)}</span><span class="tag cat">${esc(r.category)}</span>${esc(r.pref)}${esc(r.address)}</p>
      <div class="kv-grid">
        <div class="kv"><div class="k">家賃（月）</div><div class="v">¥${yen(r.rent_min)}〜${yen(r.rent_max)}</div></div>
        <div class="kv"><div class="k">間取り・広さ</div><div class="v">${esc(r.layout)} <small>${esc(r.area_text)}㎡</small></div></div>
        <div class="kv"><div class="k">募集戸数</div><div class="v">${r.units ?? "—"}戸${r.vacant_now != null ? `<small> いま空き${r.vacant_now}</small>` : ""}</div></div>
        <div class="kv"><div class="k">前回倍率</div><div class="v">${r.ratio_prev != null ? `${r.ratio_prev}倍` : "—"}</div></div>
      </div>
      <table>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</table>
      <p class="cards-h">当選したら</p>
      <div class="cards">
        <a class="card" href="#" data-aff="move"><b>引っ越し見積もり</b><span>複数社を一括で比べる</span></a>
        <a class="card" href="#" data-aff="net"><b>ネット回線</b><span>入居日に合わせて開通</span></a>
        <a class="card" href="#" data-aff="power"><b>電気・ガス</b><span>まとめて申し込み</span></a>
      </div>
      <p class="cards-h">落選したら、今すぐ入れる家</p>
      <div class="cards">
        <a class="card" href="${esc(urUrl(r))}" target="_blank" rel="noopener"><b>UR賃貸（${esc(r.pref.replace(/[都県]$/, ""))}）</b><span>礼金・仲介手数料なし。空き部屋を探す</span></a>
        <a class="card" href="#" data-aff="rent"><b>家賃の安い賃貸</b><span>${esc(r.city)}の近くで探す</span></a>
      </div>
      <p class="hint">提携先のリンクは準備中です。いまは各サービスの入口に飛びます。</p>`;
    $("detailFoot").innerHTML = `
      <div class="btn-row">
        <a class="btn ghost gmap" href="https://www.google.com/maps/search/?api=1&query=${gq}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true" width="18" height="18"><path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6a2.5 2.5 0 0 1 0 5.5z" fill="currentColor"/></svg>Googleマップ</a>
        <a class="btn official" href="${esc(r.official_url)}" target="_blank" rel="noopener">公式ページで申し込む ↗</a>
      </div>
      ${r.pdf_url ? `<div class="links"><span></span><a href="${esc(r.pdf_url)}" target="_blank" rel="noopener">募集案内PDF p.${esc(r.pdf_page)}</a></div>` : ""}`;
    $("detail").hidden = false; $("detailBody").scrollTop = 0;
    drawer.classList.add("hidden-by-detail");
    $("detailFoot").querySelector(".official").addEventListener("click", () => { store.set("visitedOfficial", Date.now()); });
    $("detailBody").querySelectorAll("[data-aff]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); toast("提携先のリンクは準備中です（試作版）"); }));
  }
  const UR_PREF = { "東京都": "tokyo", "神奈川県": "kanagawa", "埼玉県": "saitama", "千葉県": "chiba" };
  const urUrl = (r) => `https://www.ur-net.go.jp/chintai/kanto/${UR_PREF[r.pref] || ""}/`;
  function closeDetail() { $("detail").hidden = true; drawer.classList.remove("hidden-by-detail"); }
  $("detailClose").addEventListener("click", closeDetail);
  map.on("click", () => { if (!$("detail").hidden) closeDetail(); $("menu").hidden = true; });

  // 公式ページから戻ってきたら、1回だけ通知登録を勧める
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (!store.get("visitedOfficial") || store.get("nudged") || store.get("subscribed")) return;
    store.set("nudged", true); $("nudge").hidden = false;
  });
  $("nudgeYes").addEventListener("click", () => { $("nudge").hidden = true; openPage("pageNotify"); });
  $("nudgeNo").addEventListener("click", () => { $("nudge").hidden = true; });

  /* ---------------- ページ（S5・S6・S7） ---------------- */
  function openPage(id) { closePopover(); $("menu").hidden = true; if (id === "pageCal") renderCal(); $(id).hidden = false; $(id).querySelector(".page-body").scrollTop = 0; }
  function closePages() { document.querySelectorAll(".page").forEach((p) => (p.hidden = true)); }
  document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closePages));
  $("btnCal").addEventListener("click", () => openPage("pageCal"));
  $("btnMenu").addEventListener("click", () => { $("menu").hidden = !$("menu").hidden; });
  $("menu").addEventListener("click", (e) => { const b = e.target.closest("[data-open]"); if (b) openPage(b.dataset.open); });

  function renderCal() {
    const open = ROUNDS.filter((r) => roundStatus(r) === "open");
    const anytime = ROUNDS.filter((r) => roundStatus(r) === "anytime");
    const up = ROUNDS.filter((r) => roundStatus(r) === "upcoming");
    const ev = (r) => {
      const st = roundStatus(r); const op = OPS[r.operator];
      let sub = "", bar = "", badge = "";
      if (st === "open") {
        const total = (dayOf(r.apply_to) - dayOf(r.apply_from)) / 86400000 + 1, done = (TODAY - dayOf(r.apply_from)) / 86400000 + 1;
        sub = `申込 ${fmtMD(r.apply_from)} 〜 ${fmtMD(r.apply_to)}${r.lottery ? `・抽せん ${fmtMD(r.lottery)}` : ""}${r.units ? `・${r.units.toLocaleString("ja-JP")}戸` : ""}`;
        bar = `<div class="bar"><i style="width:${Math.min(100, Math.round((done / total) * 100))}%"></i></div>`;
        badge = `<span class="badge">あと${daysLeft(r.apply_to)}日</span>`;
      } else if (st === "anytime") { sub = r.kind || "いつでも"; badge = `<span class="badge ok">いつでも</span>`; }
      else { sub = `${esc(r.expected || "")}${r.kind ? `・${esc(r.kind)}` : ""}`; }
      const n = ITEMS.filter((x) => x.round_id === r.id).length;
      const acts = st === "open" || (st === "anytime" && n)
        ? `<button type="button" class="primary" data-round="${esc(r.id)}">地図で見る${n ? `（${n.toLocaleString("ja-JP")}件）` : ""}</button><a href="${esc(r.url)}" target="_blank" rel="noopener">公式ページ ↗</a>`
        : `<a href="${esc(r.url)}" target="_blank" rel="noopener">公式ページ ↗</a>`;
      return `<div class="ev" style="--op:${op.color}"><div class="row"><b>${esc(r.label)}</b>${badge}</div><div class="sub">${sub}${r.note ? `<br>${esc(r.note)}` : ""}</div>${bar}<div class="acts">${acts}</div></div>`;
    };
    $("calBody").innerHTML = `
      <p class="tl-h">今募集中</p><div class="tl">${open.map(ev).join("") || '<div class="ev"><div class="sub">今は募集中のものがありません</div></div>'}</div>
      <p class="tl-h">いつでも申し込めるもの</p><div class="tl">${anytime.map(ev).join("")}</div>
      <p class="tl-h">これから</p><div class="tl">${up.map(ev).join("")}</div>
      <button type="button" class="btn ghost" id="calNotify" style="width:100%;margin-top:16px">募集が始まったら知らせる</button>`;
    $("calBody").querySelectorAll("[data-round]").forEach((b) => b.addEventListener("click", () => { F.round = b.dataset.round; F.now = false; closePages(); apply(); if (!DESKTOP.matches) drawer.classList.add("open"); }));
    $("calNotify").addEventListener("click", () => openPage("pageNotify"));
  }

  // S6 通知登録（試作：まだ送信しない。登録内容は端末に保存するだけ）
  $("areaChips").addEventListener("click", (e) => { const c = e.target.closest(".chip"); if (!c) return; c.classList.toggle("on"); c.setAttribute("aria-pressed", c.classList.contains("on")); });
  const chosenPrefs = () => [...document.querySelectorAll("#areaChips .chip.on")].map((c) => c.dataset.pref);
  $("btnLine").addEventListener("click", (e) => { e.preventDefault(); toast("LINE公式アカウントは準備中です（試作版）"); });
  $("mailForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const list = store.get("subs") || []; list.push({ mail: $("mail").value, prefs: chosenPrefs(), at: new Date().toISOString() }); store.set("subs", list); store.set("subscribed", true);
    $("mail").value = ""; toast(`登録しました（${chosenPrefs().map((p) => p.replace(/[都県]$/, "")).join("・") || "地域なし"}）`);
    $("notifyProto").textContent = "試作版のため、まだお知らせは届きません。登録内容はこの端末にだけ保存しています。";
  });
  $("notifyProto").textContent = "試作版：登録の仕組みを確かめる段階です。まだお知らせは届きません。";

  function buildAbout() {
    $("aboutSources").innerHTML = Object.values(OPS).map((o) => `<li><a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.long)}</a></li>`).join("");
  }

  /* ---------------- トースト ---------------- */
  let tt = null;
  function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(tt); tt = setTimeout(() => (t.hidden = true), 2600); }

  function bindUI() { /* 初期化後に必要なもの（今は apply 内で完結） */ }
})();
