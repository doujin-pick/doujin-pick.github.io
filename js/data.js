/**
 * 同人ピック — カタログローダ
 * works.json を fetch。file:// では失敗するため埋め込みフォールバックも持つ。
 */
window.DOJIN_DATA = {
  works: [],
  meta: {},
  loaded: false,

  async load() {
    try {
      const res = await fetch("data/works.json", { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const json = await res.json();
      this.works = json.works || [];
      this.meta = { updated_at: json.updated_at, live_fetch: json.live_fetch };
      this.loaded = true;
      return this.works;
    } catch (e) {
      console.warn("works.json fetch failed, using embedded seed", e);
      if (window.__DOJIN_EMBEDDED_WORKS__) {
        this.works = window.__DOJIN_EMBEDDED_WORKS__.works || [];
        this.meta = {
          updated_at: window.__DOJIN_EMBEDDED_WORKS__.updated_at,
          live_fetch: window.__DOJIN_EMBEDDED_WORKS__.live_fetch,
        };
        this.loaded = true;
        return this.works;
      }
      this.works = [];
      this.loaded = true;
      return [];
    }
  },

  bySection(section) {
    return this.works.filter((w) => (w.sections || []).includes(section));
  },

  byCategory(cat) {
    return this.works.filter((w) => w.category === cat);
  },

  onSale() {
    return this.works.filter((w) => w.on_sale);
  },
};
