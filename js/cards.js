/* 文字のページ（記事・倍率）用：提携カードと LINE のリンクを data/partners.json・data/site.json から出す。押された回数は gtag に送る（gtag が無くても落ちない） */
(() => {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const track = (name, params) => { try { window.gtag?.("event", name, params); } catch (e) { /* 計測は本体の動きを止めない */ } };
  const PAGE = location.pathname;
  // 種類ごとの標準の見出し（提携先が決まっていれば提携先の名前と一言に差し替わる）
  const UR_PREF = { "東京都": "tokyo", "神奈川県": "kanagawa", "埼玉県": "saitama", "千葉県": "chiba" };
  const DEFAULTS = (pref, city) => ({
    move: ["引っ越し見積もり", "複数社を一括で比べる"],
    net: ["ネット回線", "入居日に合わせて開通"],
    power: ["電気・ガス", "まとめて申し込み"],
    ur: [`UR賃貸（${pref.replace(/[都県]$/, "")}）`, "礼金・仲介手数料なし。空き部屋を探す"],
    rent: ["家賃の安い賃貸", `${city || pref.replace(/[都県]$/, "")}の近くで探す`],
  });
  Promise.all([
    fetch("/data/partners.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    fetch("/data/site.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
  ]).then(([P, S]) => {
    const pick = (kind) => ((P && P.cards && P.cards[kind]) || [])
      .filter((c) => c.status === "active" && /^[A-Z0-9+]+$/.test(c.a8mat || "") && /^www\d+$/.test(c.px || ""))
      .sort((a, z) => z.score - a.score)[0] || null;
    const card = (kind, pref, city) => {
      const d = DEFAULTS(pref, city)[kind]; if (!d) return "";
      let [title, sub] = d, href = "", rel = "noopener", pixel = "", partner = "";
      if (kind === "ur") { href = `https://www.ur-net.go.jp/chintai/kanto/${UR_PREF[pref] || "tokyo"}/`; partner = "UR都市機構"; }
      else {
        const p = pick(kind); if (!p) return "";   // 提携先が無い種類は出さない（準備中の枠は置かない）
        href = `https://px.a8.net/svt/ejp?a8mat=${p.a8mat}`; sub = p.sub || sub; rel = "nofollow sponsored noopener"; partner = p.name;
        pixel = `<img class="a8px" src="https://${p.px}.a8.net/0.gif?a8mat=${p.a8mat}" width="1" height="1" alt="">`;
      }
      const img = (S.aff_img || []).includes(kind) ? `<img src="/img/cards/${kind}.webp?v=${encodeURIComponent(S.version || "")}" alt="" loading="lazy">` : "";
      return `<a class="card pick-${kind}" href="${esc(href)}" target="_blank" rel="${rel}" data-kind="${esc(kind)}" data-partner="${esc(partner)}"><span class="card-img">${img}</span><b>${esc(title)}</b><span class="card-sub">${esc(sub)}</span><span class="card-go">見てみる ›</span>${pixel}</a>`;
    };
    document.querySelectorAll(".pick-cards").forEach((box) => {
      const pref = box.dataset.pref || "東京都", city = box.dataset.city || "";
      box.innerHTML = (box.dataset.kinds || "").split(",").map((k) => card(k.trim(), pref, city)).join("");
      if (!box.children.length) box.closest(".pick-sec")?.remove();
      box.querySelectorAll("a[data-kind]").forEach((a) => a.addEventListener("click", () => track("partner_click", { kind: a.dataset.kind, partner: a.dataset.partner, page: PAGE })));
    });
    document.querySelectorAll("[data-line]").forEach((a) => {
      if (S.line_url) { a.href = S.line_url; a.target = "_blank"; a.rel = "noopener"; a.addEventListener("click", () => track("line_click", { place: "article", page: PAGE })); }
      else a.closest(".line-cta")?.remove();
    });
  });
})();
