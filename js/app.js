/**
 * 同人ピック — メイン UI
 */
(function () {
  const AGE_KEY = "dojin_pick_age_ok";
  const FAV_KEY = "dojin_pick_favs";
  const RECENT_KEY = "dojin_pick_recent";
  const RECENT_MAX = 12;

  const cfg = () => window.DOJIN_PICK || {};
  const F = () => window.DOJIN_FILTERS;
  let state = null;
  let allWorks = [];
  let searchApi = null;

  function affiliateHref(work) {
    const c = cfg();
    if (typeof c.affiliateUrl === "function") {
      return c.affiliateUrl(work.url, work.id, work.affiliate_url);
    }
    return work.url;
  }

  /** Crawlable work detail path (SEO). Root pages → works/{id}.html; under /works/ → {id}.html */
  function workPageHref(id) {
    const path = location.pathname || "";
    if (/\/works\//.test(path)) return `${id}.html`;
    if (/\/tags\//.test(path) || /\/circles\//.test(path)) return `../works/${id}.html`;
    return `works/${id}.html`;
  }

  function circlePageHref(slug) {
    const path = location.pathname || "";
    if (/\/works\//.test(path) || /\/tags\//.test(path) || /\/circles\//.test(path)) {
      return `../circles/${encodeURIComponent(slug)}.html`;
    }
    return `circles/${encodeURIComponent(slug)}.html`;
  }

  function circleSlug(name) {
    return String(name || "")
      .trim()
      .replace(/[\\/]/g, "-")
      .replace(/\s+/g, "-")
      .replace(/[<>:"|?*]/g, "")
      .replace(/-{2,}/g, "-")
      .replace(/^-|-$/g, "") || "circle";
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function loadJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return fallback;
      return JSON.parse(raw);
    } catch (_) {
      return fallback;
    }
  }

  function saveJson(key, val) {
    try {
      localStorage.setItem(key, JSON.stringify(val));
    } catch (_) {}
  }

  function getFavs() {
    const v = loadJson(FAV_KEY, []);
    return Array.isArray(v) ? v : [];
  }

  function setFavs(ids) {
    saveJson(FAV_KEY, ids);
    updateFavCount();
  }

  function isFav(id) {
    return getFavs().includes(id);
  }

  function toggleFav(id) {
    const favs = getFavs();
    const i = favs.indexOf(id);
    if (i >= 0) favs.splice(i, 1);
    else favs.unshift(id);
    setFavs(favs);
    return favs.includes(id);
  }

  function getRecent() {
    const v = loadJson(RECENT_KEY, []);
    return Array.isArray(v) ? v : [];
  }

  function pushRecent(id) {
    let ids = getRecent().filter((x) => x !== id);
    ids.unshift(id);
    if (ids.length > RECENT_MAX) ids = ids.slice(0, RECENT_MAX);
    saveJson(RECENT_KEY, ids);
    renderRecent();
  }

  function updateFavCount() {
    const n = getFavs().length;
    document.querySelectorAll("[data-fav-count]").forEach((el) => {
      el.textContent = String(n);
      el.hidden = n === 0;
    });
  }

  function formatPrice(work) {
    if (work.price == null) return `<span class="price">価格未取得</span>`;
    const p = work.price.toLocaleString("ja-JP") + "円";
    const off =
      work.discount_percent
        ? `<span class="work-type">${work.discount_percent}%OFF</span>`
        : "";
    if (work.on_sale && work.price_original) {
      return `<span class="price-sale">${p}</span><span class="price-was">${work.price_original.toLocaleString("ja-JP")}円</span>${off}`;
    }
    if (work.on_sale && work.discount_percent) {
      return `<span class="price-sale">${p}</span>${off}`;
    }
    return `<span class="price">${p}</span>`;
  }

  function coverHtml(work, className) {
    const cls = className || "card-cover";
    const hi = work.image || "";
    const thumb = work.image_thumb || "";
    if (hi) {
      const srcset =
        thumb && thumb !== hi
          ? ` srcset="${escapeHtml(thumb)} 240w, ${escapeHtml(hi)} 800w" sizes="(max-width:720px) 45vw, 220px"`
          : "";
      return `<img class="${cls}" src="${escapeHtml(hi)}"${srcset} alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.style.display='none';var n=this.nextElementSibling;if(n)n.style.display='flex'">
        <div class="${cls} placeholder" style="display:none" aria-hidden="true"><span>${escapeHtml((work.title || "").slice(0, 18))}</span></div>`;
    }
    return `<div class="${cls} placeholder" aria-hidden="true"><span>${escapeHtml((work.title || "").slice(0, 18))}</span></div>`;
  }

  function typeLabel(work) {
    if (work.category === "asmr") return "ボイス・ASMR";
    if (work.category === "game") return "ゲーム";
    if (work.category === "manga_cg") return work.work_type || "マンガ/CG";
    return work.work_type || "その他";
  }

  function cardHtml(work) {
    const tags = (work.tags || [])
      .slice(0, 3)
      .map((t) => `<button type="button" class="tag tag-btn" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</button>`)
      .join("");
    const sample = work.sample ? `<span class="badge-sample">サンプル</span>` : "";
    const sale = work.on_sale
      ? `<span class="badge-sale">${work.discount_percent ? escapeHtml(String(work.discount_percent)) + "%OFF" : "セール"}</span>`
      : "";
    const favOn = isFav(work.id);
    const href = workPageHref(work.id);
    return `
      <article class="card" data-id="${escapeHtml(work.id)}">
        <a class="card-media" href="${escapeHtml(href)}" aria-label="${escapeHtml(work.title)} の詳細">
          ${coverHtml(work)}
          ${sale}${sample}
        </a>
        <button type="button" class="fav-btn${favOn ? " is-on" : ""}" data-fav="${escapeHtml(work.id)}" aria-label="${favOn ? "お気に入り解除" : "お気に入りに追加"}" aria-pressed="${favOn}">${favOn ? "♥" : "♡"}</button>
        <div class="card-body">
          <p class="card-maker">${escapeHtml(work.maker || "")}</p>
          <h3 class="card-title"><a href="${escapeHtml(href)}">${escapeHtml(work.title)}</a></h3>
          <div class="card-meta">${formatPrice(work)} <span class="work-type">${escapeHtml(typeLabel(work))}</span></div>
          <div class="card-tags">${tags}</div>
        </div>
      </article>`;
  }

  function renderInto(selector, works, emptyMsg) {
    const el = document.querySelector(selector);
    if (!el) return;
    if (!works || !works.length) {
      el.innerHTML = emptyMsg || defaultEmptyHtml();
      return;
    }
    el.innerHTML = works.map(cardHtml).join("");
  }

  function defaultEmptyHtml() {
    const suggestions = [
      { label: "セール中", href: F().exploreHref({ sale: true }) },
      { label: "ゲーム", href: F().exploreHref({ type: "game" }) },
      { label: "ボイス・ASMR", href: F().exploreHref({ type: "voice" }) },
      { label: "マンガ/CG", href: F().exploreHref({ type: "manga_cg" }) },
      { label: "〜1000円", href: F().exploreHref({ price: "under1000" }) },
    ];
    return `<div class="empty">
      <strong>該当する作品がありません</strong>
      条件をゆるめるか、下の候補を試してください。
      <div class="suggestions">${suggestions
        .map((s) => `<a class="chip" href="${s.href}">${escapeHtml(s.label)}</a>`)
        .join("")}</div>
    </div>`;
  }

  function showAffBanner() {
    const bar = document.getElementById("aff-banner");
    if (bar) {
      bar.hidden = true;
      bar.textContent = "";
    }
  }

  function setupAgeGate() {
    const modal = document.getElementById("age-gate");
    if (!modal) return;
    try {
      if (localStorage.getItem(AGE_KEY) === "1") {
        modal.hidden = true;
        return;
      }
    } catch (_) {}
    modal.hidden = false;
    const ok = document.getElementById("age-yes");
    const no = document.getElementById("age-no");
    if (ok) {
      ok.addEventListener("click", () => {
        try {
          localStorage.setItem(AGE_KEY, "1");
        } catch (_) {}
        modal.hidden = true;
      });
    }
    if (no) {
      no.addEventListener("click", () => {
        modal.innerHTML =
          '<div class="age-panel"><h2>ご利用いただけません</h2><p>18歳未満の方は閲覧できません。</p></div>';
      });
    }
  }

  function setActiveNav() {
    const path = (location.pathname.split("/").pop() || "index.html").toLowerCase();
    const page = document.body.dataset.page || "";
    document.querySelectorAll(".nav a[data-nav]").forEach((a) => {
      const key = a.getAttribute("data-nav");
      let on = false;
      if (key === "home" && (path === "" || path === "index.html" || page === "home")) on = true;
      else if (key === "explore" && (page === "explore" || path === "explore.html" || path === "ranking.html" || path === "sale.html" || path === "genre.html")) on = true;
      else if (key === "fav" && state && state.view === "fav") on = true;
      else if (path === key + ".html" || page === key) on = true;
      a.classList.toggle("active", on);
    });
    const favLink = document.getElementById("nav-fav");
    if (favLink) favLink.classList.toggle("is-active", !!(state && state.view === "fav"));
  }

  /* —— Drawer —— */
  function ensureDrawer() {
    if (document.getElementById("work-drawer")) return;
    const backdrop = document.createElement("div");
    backdrop.id = "drawer-backdrop";
    backdrop.className = "drawer-backdrop";
    backdrop.tabIndex = -1;
    const drawer = document.createElement("aside");
    drawer.id = "work-drawer";
    drawer.className = "drawer";
    drawer.setAttribute("role", "dialog");
    drawer.setAttribute("aria-modal", "true");
    drawer.setAttribute("aria-label", "作品詳細");
    drawer.innerHTML = `
      <div class="drawer-handle">
        <span class="grab" aria-hidden="true"></span>
        <button type="button" class="drawer-close" id="drawer-close" aria-label="閉じる">×</button>
      </div>
      <div class="drawer-body" id="drawer-body"></div>`;
    document.body.appendChild(backdrop);
    document.body.appendChild(drawer);
    backdrop.addEventListener("click", closeDrawer);
    document.getElementById("drawer-close").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && drawer.classList.contains("is-open")) {
        e.preventDefault();
        closeDrawer();
      }
    });
  }

  function formatDescriptionHtml(desc) {
    const raw = String(desc || "").trim();
    if (!raw) {
      return `<p class="drawer-desc-empty">紹介文はまだ取得できていません。DLsiteの作品ページで詳細をご確認ください。</p>`;
    }
    const paras = raw.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
    return paras
      .map((p) => `<p>${escapeHtml(p).replace(/\n/g, "<br>")}</p>`)
      .join("");
  }

  function openDrawer(work) {
    ensureDrawer();
    pushRecent(work.id);
    const drawer = document.getElementById("work-drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    const body = document.getElementById("drawer-body");
    const href = affiliateHref(work);
    const pageHref = workPageHref(work.id);
    const favOn = isFav(work.id);
    const tags = (work.tags || [])
      .slice(0, 6)
      .map((t) => `<button type="button" class="tag tag-btn" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</button>`)
      .join("");
    body.innerHTML = `
      ${coverHtml(work, "drawer-cover")}
      <p class="drawer-maker">${escapeHtml(work.maker || "サークル未記載")}</p>
      <h2 class="drawer-title">${escapeHtml(work.title)}</h2>
      <div class="drawer-price">${formatPrice(work)}</div>
      <ul class="drawer-meta-list">
        <li><span>形式</span>${escapeHtml(typeLabel(work))}</li>
        <li><span>作品ID</span>${escapeHtml(work.id)}</li>
        <li><span>状態</span>${work.on_sale ? "セール中" : "通常価格"}</li>
      </ul>
      <div class="drawer-tags" aria-label="ジャンルタグ">${tags || '<span class="tag">タグなし</span>'}</div>
      <div class="drawer-desc">
        <h3 class="drawer-desc-title">作品紹介</h3>
        <div class="drawer-desc-body">${formatDescriptionHtml(work.description)}</div>
      </div>
      <div class="drawer-actions">
        <a class="btn-cta" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">DLsiteで見る</a>
        <a class="btn" href="${escapeHtml(pageHref)}">作品ページ</a>
        <button type="button" class="btn" data-fav="${escapeHtml(work.id)}" aria-pressed="${favOn}">${favOn ? "♥ お気に入り済み" : "♡ お気に入りに追加"}</button>
      </div>`;
    drawer.classList.add("is-open");
    backdrop.classList.add("is-open");
    document.body.classList.add("is-drawer-open");
    document.getElementById("drawer-close").focus();
  }

  function closeDrawer() {
    const drawer = document.getElementById("work-drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    if (drawer) drawer.classList.remove("is-open");
    if (backdrop) backdrop.classList.remove("is-open");
    document.body.classList.remove("is-drawer-open");
  }

  function findWork(id) {
    return allWorks.find((w) => w.id === id);
  }

  function applyTagFilter(tag) {
    const t = (tag || "").trim();
    if (!t) return;
    state.tag = state.tag === t ? "" : t;
    closeDrawer();
    const page = document.body.dataset.page;
    if (page !== "explore") {
      location.href = F().exploreHref({
        tag: state.tag,
        type: state.type,
        sale: state.sale,
        price: state.price,
        sort: state.sort,
        view: state.view,
        q: state.q,
      });
      return;
    }
    F().writeToUrl(state, false);
    syncFilterChips();
    setActiveNav();
    refreshCatalog();
    renderTagCloud();
  }

  function bindCardEvents(root) {
    const scope = root || document;
    scope.addEventListener("click", (e) => {
      const tagBtn = e.target.closest("[data-tag]");
      if (tagBtn) {
        e.preventDefault();
        e.stopPropagation();
        applyTagFilter(tagBtn.getAttribute("data-tag"));
        return;
      }
      const fav = e.target.closest("[data-fav]");
      if (fav) {
        e.preventDefault();
        e.stopPropagation();
        const id = fav.getAttribute("data-fav");
        const on = toggleFav(id);
        document.querySelectorAll(`[data-fav="${CSS.escape(id)}"]`).forEach((btn) => {
          btn.classList.toggle("is-on", on);
          btn.setAttribute("aria-pressed", String(on));
          if (btn.classList.contains("fav-btn")) btn.textContent = on ? "♥" : "♡";
          else btn.textContent = on ? "♥ お気に入り済み" : "♡ お気に入りに追加";
          btn.setAttribute("aria-label", on ? "お気に入り解除" : "お気に入りに追加");
        });
        if (state && state.view === "fav") refreshCatalog();
        return;
      }
      const open = e.target.closest("[data-open]");
      if (open) {
        e.preventDefault();
        const work = findWork(open.getAttribute("data-open"));
        if (work) openDrawer(work);
      }
    });
  }

  function renderRecent() {
    const wrap = document.getElementById("recent-wrap");
    const strip = document.getElementById("recent-strip");
    if (!strip) return;
    const ids = getRecent();
    const works = ids.map(findWork).filter(Boolean);
    if (!works.length) {
      if (wrap) wrap.hidden = true;
      strip.innerHTML = "";
      return;
    }
    if (wrap) wrap.hidden = false;
    strip.innerHTML = works
      .map((w) => {
        const img = w.image
          ? `<img src="${escapeHtml(w.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" width="42" height="42">`
          : `<span class="ph">cover</span>`;
        return `<button type="button" class="recent-chip" data-open="${escapeHtml(w.id)}">${img}<span class="rt">${escapeHtml(w.title)}</span></button>`;
      })
      .join("");
  }

  /* —— Filter UI —— */
  function syncFilterChips() {
    document.querySelectorAll("[data-filter]").forEach((el) => {
      const key = el.getAttribute("data-filter");
      const val = el.getAttribute("data-value") || "";
      let on = false;
      if (key === "type") on = state.type === val;
      else if (key === "sale") on = state.sale === (val === "1");
      else if (key === "price") on = state.price === val;
      else if (key === "sort") on = state.sort === val;
      else if (key === "view") on = state.view === val;
      else if (key === "tag") on = state.tag === val;
      el.classList.toggle("is-on", on);
      el.setAttribute("aria-pressed", String(on));
    });
    const countEl = document.getElementById("result-count");
    if (countEl && document.body.dataset.page === "explore") {
      /* updated in refreshCatalog */
    }
  }

  function setupFilters() {
    document.querySelectorAll("[data-filter]").forEach((el) => {
      el.addEventListener("click", () => {
        const key = el.getAttribute("data-filter");
        const val = el.getAttribute("data-value") || "";
        if (key === "type") state.type = state.type === val ? "" : val;
        else if (key === "sale") state.sale = !state.sale;
        else if (key === "price") state.price = state.price === val ? "" : val;
        else if (key === "sort") state.sort = val || "popular";
        else if (key === "view") state.view = state.view === val ? "" : val;
        else if (key === "tag") state.tag = state.tag === val ? "" : val;
        F().writeToUrl(state, false);
        syncFilterChips();
        setActiveNav();
        refreshCatalog();
      });
    });

    const mob = document.getElementById("filter-mobile-toggle");
    const rows = document.getElementById("filter-rows");
    if (mob && rows) {
      mob.addEventListener("click", () => {
        const open = rows.classList.toggle("is-open");
        mob.setAttribute("aria-expanded", String(open));
        mob.textContent = open ? "絞り込みを閉じる" : "絞り込み・並べ替え";
      });
    }
  }

  function refreshCatalog() {
    const page = document.body.dataset.page || "home";
    if (page === "explore") {
      const list = F().apply(allWorks, state, getFavs());
      const countEl = document.getElementById("result-count");
      if (countEl) {
        countEl.innerHTML = `<strong>${list.length}</strong> / ${allWorks.length} 件`;
      }
      const heading = document.getElementById("explore-heading");
      if (heading) {
        if (state.view === "fav") heading.textContent = "お気に入り";
        else if (state.tag) heading.textContent = "タグ: " + state.tag;
        else if (state.sale && !state.type && !state.q) heading.textContent = "セール中の作品";
        else if (state.sort === "popular" && !state.sale && !state.type && !state.q && !state.price)
          heading.textContent = document.body.dataset.preset === "ranking" ? "人気の作品" : "すべて探す";
        else heading.textContent = "探す";
      }
      renderTagCloud();
      let empty = defaultEmptyHtml();
      if (state.view === "fav") {
        empty = `<div class="empty"><strong>お気に入りはまだ空です</strong>カード右上の ♡ を押すとここに溜まります。<div class="suggestions"><a class="chip" href="explore.html">カタログへ</a></div></div>`;
      }
      renderInto("#grid-main", list, empty);
      syncFilterChips();
    }
  }

  function applyPresetFromPage() {
    const page = document.body.dataset.page;
    const preset = document.body.dataset.preset;
    // If URL already has params, prefer them; else apply page preset
    const params = new URLSearchParams(location.search);
    const hasParams = [...params.keys()].some((k) => ["q", "type", "sale", "price", "sort", "view", "g", "tag"].includes(k));
    if (hasParams) return;
    if (page === "explore" && preset === "ranking") {
      state.sort = "popular";
    } else if (page === "explore" && preset === "sale") {
      state.sale = true;
      state.sort = "discount";
    } else if (page === "explore" && preset === "genre") {
      /* genre chips handle via g= already in readFromUrl */
    }
  }

  function renderTagCloud() {
    const el = document.getElementById("tag-cloud");
    if (!el || !F().popularTags) return;
    const popular = F().popularTags(allWorks, 20);
    if (!popular.length) {
      el.innerHTML = "";
      el.hidden = true;
      return;
    }
    el.hidden = false;
    const clear = state.tag
      ? `<button type="button" class="chip" data-filter="tag" data-value="" aria-pressed="false">タグ解除</button>`
      : "";
    el.innerHTML =
      `<span class="filter-label">よく使われるタグ</span>` +
      clear +
      popular
        .map(
          ({ tag, count }) =>
            `<button type="button" class="chip tag-cloud-chip${state.tag === tag ? " is-on" : ""}" data-filter="tag" data-value="${escapeHtml(tag)}" aria-pressed="${state.tag === tag}">${escapeHtml(tag)} <small>${count}</small></button>`
        )
        .join("");
    // re-bind filter clicks for dynamically added chips
    el.querySelectorAll("[data-filter]").forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-filter");
        const val = btn.getAttribute("data-value") || "";
        if (key === "tag") state.tag = state.tag === val ? "" : val;
        F().writeToUrl(state, false);
        syncFilterChips();
        refreshCatalog();
      });
    });
  }

  function categoryPriority(w) {
    if (w.category === "asmr") return 0;
    if (w.category === "game") return 1;
    return 2;
  }

  function pickFeatured(D) {
    let featured = D.bySection("featured");
    if (featured.length < 4) featured = allWorks.slice();
    const scored = featured.slice().sort((a, b) => {
      const pc = categoryPriority(a) - categoryPriority(b);
      if (pc) return pc;
      return (b.discount_percent || 0) - (a.discount_percent || 0);
    });
    // Prefer voice+game in the hero slot and companions
    const voice = scored.filter((w) => w.category === "asmr");
    const game = scored.filter((w) => w.category === "game");
    const other = scored.filter((w) => w.category !== "asmr" && w.category !== "game");
    const merged = [];
    const seen = new Set();
    function push(list) {
      for (const w of list) {
        if (seen.has(w.id)) continue;
        seen.add(w.id);
        merged.push(w);
      }
    }
    // Interleave voice/game for denser monetization-aligned hero
    const max = Math.max(voice.length, game.length);
    for (let i = 0; i < max; i++) {
      if (i < voice.length) push([voice[i]]);
      if (i < game.length) push([game[i]]);
    }
    push(other);
    return merged;
  }

  function renderCoverCollage(works) {
    const el = document.getElementById("cover-collage");
    if (!el) return;
    const picks = (works || []).filter((w) => w.image_thumb || w.image).slice(0, 18);
    if (!picks.length) {
      el.innerHTML = "";
      return;
    }
    el.innerHTML = picks
      .map((w) => {
        const src = w.image_thumb || w.image;
        const href = workPageHref(w.id);
        return `<a href="${escapeHtml(href)}" title="${escapeHtml(w.title || "")}" aria-label="${escapeHtml(w.title || "")}">
          <img src="${escapeHtml(src)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">
        </a>`;
      })
      .join("");
  }

  function renderCircleGrid(works) {
    const el = document.getElementById("circle-grid");
    if (!el) return;
    // If SEO generator already injected static cards, keep them (crawlable).
    if (el.querySelector(".circle-card")) return;
    const counts = new Map();
    const samples = new Map();
    for (const w of works) {
      const m = (w.maker || "").trim();
      if (!m) continue;
      counts.set(m, (counts.get(m) || 0) + 1);
      if (!samples.has(m)) samples.set(m, []);
      if (samples.get(m).length < 3 && (w.image_thumb || w.image)) {
        samples.get(m).push(w.image_thumb || w.image);
      }
    }
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ja")).slice(0, 12);
    el.innerHTML = top
      .map(([name, n]) => {
        const slug = circleSlug(name);
        const thumbs = (samples.get(name) || [])
          .map((src) => `<img src="${escapeHtml(src)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">`)
          .join("");
        return `<a class="circle-card" href="${escapeHtml(circlePageHref(slug))}">
          <strong>${escapeHtml(name)}</strong>
          <span>${n}作品</span>
          <div class="circle-thumbs">${thumbs}</div>
        </a>`;
      })
      .join("");
  }

  function renderHome() {
    const D = window.DOJIN_DATA;
    const featured = pickFeatured(D);
    renderInto("#grid-featured", featured.slice(0, 5));
    renderCoverCollage(featured.concat(D.byCategory("asmr"), D.byCategory("game")));

    renderInto("#grid-genre-voice", D.byCategory("asmr").slice(0, 8));
    renderInto("#grid-genre-game", D.byCategory("game").slice(0, 8));

    let sale = D.onSale().length ? D.onSale() : D.bySection("sale");
    const saleSorted = sale.slice().sort((a, b) => (b.discount_percent || 0) - (a.discount_percent || 0));
    renderInto("#grid-sale", saleSorted.slice(0, 8));

    const popular = allWorks.slice(0, 8);
    renderInto("#grid-popular", popular);

    renderInto("#grid-genre-manga", D.byCategory("manga_cg").slice(0, 6));
    renderCircleGrid(allWorks);
    renderRecent();
  }

  function onSearchChange(q) {
    state.q = (q || "").trim();
    const page = document.body.dataset.page;
    if (page === "explore") {
      F().writeToUrl(state, true);
      refreshCatalog();
    }
  }

  function onSearchSubmit(q) {
    state.q = (q || "").trim();
    const page = document.body.dataset.page;
    if (page !== "explore") {
      location.href = F().exploreHref({
        q: state.q,
        type: state.type,
        sale: state.sale,
        price: state.price,
        sort: state.sort,
        view: state.view,
        tag: state.tag,
      });
      return;
    }
    F().writeToUrl(state, true);
    refreshCatalog();
  }

  async function boot() {
    setupAgeGate();
    showAffBanner();
    ensureDrawer();
    bindCardEvents(document);
    updateFavCount();

    state = F().readFromUrl();
    applyPresetFromPage();

    searchApi = window.DOJIN_SEARCH.mount({ onChange: onSearchChange, onSubmit: onSearchSubmit });
    if (searchApi) searchApi.setValue(state.q);

    setupFilters();
    setActiveNav();
    syncFilterChips();

    const loading = document.getElementById("grid-main");
    if (loading && document.body.dataset.page === "explore") {
      loading.innerHTML = `<p class="loading">読み込み中…</p>`;
    }

    try {
      await window.DOJIN_DATA.load();
    } catch (e) {
      if (loading) {
        loading.innerHTML = `<div class="error-box"><strong>データを読めませんでした</strong>時間をおいて再度お試しください。</div>`;
      }
      return;
    }

    allWorks = window.DOJIN_DATA.works || [];
    if (!allWorks.length) {
      document.querySelectorAll(".grid").forEach((el) => {
        el.innerHTML = `<div class="empty"><strong>作品データが空です</strong>しばらくしてから再度お試しください。</div>`;
      });
    }

    const page = document.body.dataset.page || "home";
    if (page === "home") renderHome();
    else if (page === "explore") {
      F().writeToUrl(state, true);
      refreshCatalog();
      renderRecent();
    } else if (page === "about") {
      renderRecent();
    }

    const stamp = document.getElementById("data-updated");
    if (stamp && window.DOJIN_DATA.meta.updated_at) {
      stamp.textContent =
        "データ更新: " + window.DOJIN_DATA.meta.updated_at.replace("T", " ").slice(0, 19) + " JST";
    }

    if (window.DOJIN_PROMO && typeof window.DOJIN_PROMO.mount === "function") {
      window.DOJIN_PROMO.mount(allWorks);
    }

    window.addEventListener("popstate", () => {
      state = F().readFromUrl();
      if (searchApi) searchApi.setValue(state.q);
      syncFilterChips();
      setActiveNav();
      if (document.body.dataset.page === "explore") refreshCatalog();
    });
  }

  window.DOJIN_APP = {
    affiliateHref,
    cardHtml,
    workPageHref,
    circlePageHref,
    circleSlug,
    renderInto,
    boot,
    openDrawer,
    closeDrawer,
    toggleFav,
  };
  document.addEventListener("DOMContentLoaded", boot);
})();
