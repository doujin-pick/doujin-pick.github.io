/**
 * 同人ピック — ブラウザ側の X 投稿文ジェネレータ（管理用）
 * 本番の自動投稿下書きは scripts/generate_posts.py を使用。
 */
window.DOJIN_PROMO = {
  buildPost(work, index) {
    const cfg = window.DOJIN_PICK || {};
    const link =
      cfg.affiliateUrl && typeof cfg.affiliateUrl === "function"
        ? cfg.affiliateUrl(work.url, work.id, work.affiliate_url)
        : work.url;
    const price =
      work.price != null
        ? work.price.toLocaleString("ja-JP") + "円" + (work.discount_percent ? `（${work.discount_percent}%OFF）` : "")
        : "";
    const lines = [
      `【同人ピック】${work.title}`,
      work.maker ? `Circle: ${work.maker}` : null,
      price ? `💰 ${price}` : null,
      work.on_sale ? "🔥 セール中" : null,
      "",
      "18歳未満閲覧禁止 / #DLsite #同人",
      link,
    ].filter((x) => x !== null);
    return lines.join("\n");
  },

  mount(works) {
    const box = document.getElementById("promo-box");
    if (!box || !works || !works.length) return;
    const pick = works.slice(0, 5);
    box.innerHTML =
      `<h3 class="promo-title">本日の投稿ドラフト（コピー用）</h3>` +
      pick
        .map((w, i) => {
          const text = this.buildPost(w, i);
          return `<div class="promo-card"><pre class="promo-text">${escape(text)}</pre>
            <button type="button" class="btn-copy" data-i="${i}">コピー</button></div>`;
        })
        .join("");
    const texts = pick.map((w, i) => this.buildPost(w, i));
    box.querySelectorAll(".btn-copy").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const i = +btn.dataset.i;
        try {
          await navigator.clipboard.writeText(texts[i]);
          btn.textContent = "コピー済み";
          setTimeout(() => (btn.textContent = "コピー"), 1500);
        } catch (_) {
          btn.textContent = "選択してコピー";
        }
      });
    });
    function escape(s) {
      return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }
  },
};
