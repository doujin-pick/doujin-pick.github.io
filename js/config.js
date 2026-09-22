/**
 * 同人ピック — サイト設定（運営者向け）
 *
 * DLsite 公式シェア／トラッキングリンクは dlaf.jp ドメインを使用。
 * 公式「リンク作成」で発行した URL のみを貼ること。クエリパラメータを自作しない。
 *
 * 使い方:
 * 1. affiliateId … 管理用メモ（任意）
 * 2. affiliateUrls[productId] … 作品ごとの dlaf.jp URL（推奨）
 * 3. affiliateBase … 任意。将来用プレースホルダ
 * 4. siteUrl … このサイトの公開 URL（OGP・投稿末尾用）
 *
 * 未設定時は通常の dlsite.com 作品 URL を開く（訪問者向けバナーは出さない）。
 */
window.DOJIN_PICK = {
  siteName: "同人ピック",
  tagline: "DLsiteの同人を、探しやすくまとめる",
  affiliateId: "", // 例: "your_aff_id"
  // 作品ごとの dlaf.jp URL（リンク作成で発行したものだけ貼る）
  affiliateUrls: {},
  affiliateBase: "", // 未使用（自作パラメータ禁止）。必要なら公式手順に従って設定
  // 公開URL（末尾スラッシュなし）。sitemap/canonical/OGP用。未設定時 SEO 生成は https://doujin-pick.example
  // または環境変数 SITE_URL でも可。
  siteUrl: "https://doujin-pick.github.io",
  /**
   * URL 解決
   * - work.affiliate_url または affiliateUrls[id] があればそれを返す（dlaf.jp）
   * - なければ通常の dlsite.com 作品 URL
   */
  affiliateUrl: function (workUrl, productId, workAffiliateUrl) {
    const map = this.affiliateUrls || {};
    if (workAffiliateUrl && String(workAffiliateUrl).trim()) {
      return String(workAffiliateUrl).trim();
    }
    if (productId && map[productId]) {
      return map[productId];
    }
    return workUrl;
  },
  isAffiliateConfigured: function () {
    const id = (this.affiliateId || "").trim();
    const map = this.affiliateUrls || {};
    const hasMap = Object.keys(map).length > 0;
    const base = (this.affiliateBase || "").trim();
    return Boolean(id || hasMap || base);
  },
};
