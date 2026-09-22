/**
 * 同人ピック — URL 連動フィルタ／ソート
 */
(function () {
  const TYPE_MAP = {
    manga: { label: "マンガ", match: (w) => w.category === "manga_cg" && /マンガ/.test(w.work_type || "") },
    cg: { label: "CG", match: (w) => w.category === "manga_cg" && !/マンガ/.test(w.work_type || "") },
    manga_cg: { label: "マンガ/CG", match: (w) => w.category === "manga_cg" },
    game: { label: "ゲーム", match: (w) => w.category === "game" },
    voice: { label: "ボイス・ASMR", match: (w) => w.category === "asmr" },
    other: {
      label: "その他",
      match: (w) => !["manga_cg", "game", "asmr"].includes(w.category),
    },
  };

  const PRICE_MAP = {
    under1000: { label: "〜1000円", match: (w) => w.price != null && w.price <= 1000 },
    mid: { label: "1000–3000円", match: (w) => w.price != null && w.price > 1000 && w.price <= 3000 },
    over3000: { label: "3000円+", match: (w) => w.price != null && w.price > 3000 },
  };

  function defaults() {
    return { q: "", type: "", sale: false, price: "", sort: "popular", view: "", tag: "" };
  }

  function readFromUrl() {
    const p = new URLSearchParams(location.search);
    const state = defaults();
    state.q = (p.get("q") || "").trim();
    state.type = p.get("type") || "";
    state.sale = p.get("sale") === "1";
    state.price = p.get("price") || "";
    state.sort = p.get("sort") || "popular";
    state.view = p.get("view") || "";
    state.tag = (p.get("tag") || "").trim();
    // legacy genre.html?g=
    const g = p.get("g");
    if (g && !state.type) {
      if (g === "asmr") state.type = "voice";
      else if (g === "manga") state.type = "manga_cg";
      else if (g === "game") state.type = "game";
    }
    return state;
  }

  function writeToUrl(state, replace) {
    const p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.type) p.set("type", state.type);
    if (state.sale) p.set("sale", "1");
    if (state.price) p.set("price", state.price);
    if (state.sort && state.sort !== "popular") p.set("sort", state.sort);
    if (state.view) p.set("view", state.view);
    if (state.tag) p.set("tag", state.tag);
    const qs = p.toString();
    const url = qs ? location.pathname + "?" + qs + location.hash : location.pathname + location.hash;
    if (replace) history.replaceState(null, "", url);
    else history.pushState(null, "", url);
  }

  function normalize(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/[ァ-ン]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0x60));
  }

  function matchesQuery(work, q) {
    if (!q) return true;
    const n = normalize(q);
    const hay = normalize(
      [
        work.title,
        work.maker,
        work.work_type,
        work.category,
        work.description,
        ...(work.tags || []),
      ].join(" ")
    );
    return n.split(/\s+/).filter(Boolean).every((token) => hay.includes(token));
  }

  function matchesTag(work, tag) {
    if (!tag) return true;
    const n = normalize(tag);
    return (work.tags || []).some((t) => normalize(t) === n || normalize(t).includes(n));
  }

  function apply(works, state, favIds) {
    let list = works.slice();
    if (state.view === "fav") {
      const set = new Set(favIds || []);
      list = list.filter((w) => set.has(w.id));
    }
    list = list.filter((w) => matchesQuery(w, state.q));
    list = list.filter((w) => matchesTag(w, state.tag));
    if (state.type && TYPE_MAP[state.type]) {
      list = list.filter(TYPE_MAP[state.type].match);
    }
    if (state.sale) list = list.filter((w) => w.on_sale);
    if (state.price && PRICE_MAP[state.price]) {
      list = list.filter(PRICE_MAP[state.price].match);
    }
    list = sortList(list, state.sort, works);
    return list;
  }

  function sortList(list, sort, original) {
    const idx = new Map(original.map((w, i) => [w.id, i]));
    const copy = list.slice();
    if (sort === "price_asc") {
      copy.sort((a, b) => {
        const pa = a.price == null ? Infinity : a.price;
        const pb = b.price == null ? Infinity : b.price;
        return pa - pb || (idx.get(a.id) - idx.get(b.id));
      });
    } else if (sort === "discount") {
      copy.sort((a, b) => {
        const da = a.discount_percent || 0;
        const db = b.discount_percent || 0;
        return db - da || (idx.get(a.id) - idx.get(b.id));
      });
    } else if (sort === "new") {
      copy.sort((a, b) => (idx.get(b.id) - idx.get(a.id)) || String(b.id).localeCompare(String(a.id)));
    } else {
      copy.sort((a, b) => idx.get(a.id) - idx.get(b.id));
    }
    return copy;
  }

  function exploreHref(partial) {
    const s = Object.assign(defaults(), partial || {});
    const p = new URLSearchParams();
    if (s.q) p.set("q", s.q);
    if (s.type) p.set("type", s.type);
    if (s.sale) p.set("sale", "1");
    if (s.price) p.set("price", s.price);
    if (s.sort && s.sort !== "popular") p.set("sort", s.sort);
    if (s.view) p.set("view", s.view);
    if (s.tag) p.set("tag", s.tag);
    const qs = p.toString();
    return "explore.html" + (qs ? "?" + qs : "");
  }

  function popularTags(works, limit) {
    const counts = new Map();
    (works || []).forEach((w) => {
      (w.tags || []).forEach((t) => {
        if (!t || t === "サンプル") return;
        counts.set(t, (counts.get(t) || 0) + 1);
      });
    });
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ja"))
      .slice(0, limit || 24)
      .map(([tag, count]) => ({ tag, count }));
  }

  window.DOJIN_FILTERS = {
    TYPE_MAP,
    PRICE_MAP,
    defaults,
    readFromUrl,
    writeToUrl,
    apply,
    matchesQuery,
    matchesTag,
    exploreHref,
    popularTags,
  };
})();
