#!/usr/bin/env python3
"""Generate crawlable static SEO pages from data/works.json.

Outputs:
  works/{id}.html       — per-work detail (indexable)
  tags/{slug}.html      — top tag landings
  robots.txt
  sitemap.xml
  js/tag-cloud-data.js
  Injects crawlable popular-tag lists into main HTML footers / explore noscript.

siteUrl resolution (absolute URLs for sitemap/canonical/OG):
  1. env SITE_URL
  2. window.DOJIN_PICK.siteUrl in js/config.js (if non-empty)
  3. default https://doujin-pick.example  (documented placeholder)
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "works.json"
CONFIG_JS = ROOT / "js" / "config.js"
WORKS_DIR = ROOT / "works"
TAGS_DIR = ROOT / "tags"
DEFAULT_SITE_URL = "https://doujin-pick.example"
SITE_NAME = "同人ピック"
TAG_PAGE_LIMIT = 40
RELATED_MIN = 3
RELATED_MAX = 6

FOOTER_START = "<!-- SEO_FOOTER_TAGS -->"
FOOTER_END = "<!-- /SEO_FOOTER_TAGS -->"
NOSCRIPT_START = "<!-- SEO_NOSCRIPT_TAGS -->"
NOSCRIPT_END = "<!-- /SEO_NOSCRIPT_TAGS -->"

MAIN_PAGES = [
    ("index.html", "home"),
    ("explore.html", "explore"),
    ("ranking.html", "ranking"),
    ("sale.html", "sale"),
    ("genre.html", "genre"),
]

PAGE_META = {
    "index.html": {
        "title": "同人ピック｜セール・ランキング・目的別で見つかる同人ガイド",
        "description": "DLsiteの同人作品を、人気・セール・ジャンルから探しやすくまとめたサイトです（18歳以上向け）。",
    },
    "explore.html": {
        "title": "すべて探す｜同人ピック",
        "description": "タイトル・サークル・タグで同人を検索。形式・セール・価格帯・並び順で絞り込めます（18歳以上）。",
    },
    "ranking.html": {
        "title": "人気｜同人ピック",
        "description": "人気の同人作品一覧です。形式やセールでも絞り込めます（18歳以上向け）。",
    },
    "sale.html": {
        "title": "セール｜同人ピック",
        "description": "割引中の同人作品を、割引率や価格帯から探せます（18歳以上）。",
    },
    "genre.html": {
        "title": "形式から探す｜同人ピック",
        "description": "マンガ/CG・ゲーム・ボイス・ASMRなど形式から同人を探す（18歳以上）。",
    },
}


def resolve_site_url() -> str:
    env = (os.environ.get("SITE_URL") or "").strip().rstrip("/")
    if env:
        return env
    if CONFIG_JS.exists():
        text = CONFIG_JS.read_text(encoding="utf-8")
        m = re.search(r'siteUrl\s*:\s*["\']([^"\']*)["\']', text)
        if m and m.group(1).strip():
            return m.group(1).strip().rstrip("/")
    return DEFAULT_SITE_URL


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def clean_text(s: str) -> str:
    t = re.sub(r"[\r\n\t]+", " ", s or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def meta_description(desc: str, fallback: str, lo: int = 80, hi: int = 120) -> str:
    t = clean_text(desc)
    if not t:
        t = clean_text(fallback)
    if len(t) <= hi:
        return t
    cut = t[:hi]
    # prefer break at punctuation / space
    for sep in ("。", "、", " ", "　"):
        i = cut.rfind(sep)
        if i >= lo - 10:
            return cut[: i + (1 if sep in "。、" else 0)].strip()
    return cut.rstrip() + "…"


def page_title(title: str, maker: str) -> str:
    """{title}｜{maker}｜同人ピック — truncate sensibly (~60–70 visible chars)."""
    site = SITE_NAME
    t = clean_text(title) or "作品"
    m = clean_text(maker)
    # Budget for full title roughly under 70 chars
    budget = 68
    suffix = f"｜{site}"
    mid = f"｜{m}" if m else ""
    remain = budget - len(suffix) - len(mid)
    if remain < 12:
        mid = ""
        remain = budget - len(suffix)
        if m:
            # shorten maker
            mk = m[:10] + ("…" if len(m) > 10 else "")
            mid = f"｜{mk}"
            remain = budget - len(suffix) - len(mid)
    if len(t) > max(remain, 8):
        t = t[: max(remain, 8) - 1] + "…"
    return f"{t}{mid}{suffix}"


def tag_slug(tag: str) -> str:
    s = (tag or "").strip()
    s = s.replace("/", "-").replace("\\", "-").replace(" ", "-")
    for c in '<>:"|?*':
        s = s.replace(c, "")
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "tag"


def tag_href(tag: str, prefix: str = "") -> str:
    """Relative href to static tag page (URL-encoded path segment)."""
    slug = tag_slug(tag)
    return f"{prefix}tags/{quote(slug)}.html"


def explore_tag_href(tag: str, prefix: str = "") -> str:
    return f"{prefix}explore.html?tag={quote(tag)}"


def type_label(work: dict) -> str:
    cat = work.get("category") or ""
    if cat == "asmr":
        return "ボイス・ASMR"
    if cat == "game":
        return "ゲーム"
    if cat == "manga_cg":
        return work.get("work_type") or "マンガ/CG"
    return work.get("work_type") or "その他"


def format_price_html(work: dict) -> str:
    price = work.get("price")
    if price is None:
        return '<span class="price">価格未取得</span>'
    p = f'{int(price):,}円'.replace(",", ",")
    # Japanese locale-ish
    p = f"{int(price):,}円"
    off = ""
    if work.get("discount_percent"):
        off = f'<span class="work-type">{int(work["discount_percent"])}%OFF</span>'
    if work.get("on_sale") and work.get("price_original"):
        was = f'{int(work["price_original"]):,}円'
        return f'<span class="price-sale">{p}</span><span class="price-was">{was}</span>{off}'
    if work.get("on_sale") and work.get("discount_percent"):
        return f'<span class="price-sale">{p}</span>{off}'
    return f'<span class="price">{p}</span>'


def description_html(desc: str) -> str:
    raw = (desc or "").strip()
    if not raw:
        return (
            '<p class="drawer-desc-empty">紹介文はまだ取得できていません。'
            "DLsiteの作品ページで詳細をご確認ください。</p>"
        )
    paras = [p.strip() for p in re.split(r"\n{2,}", raw) if p.strip()]
    out = []
    for p in paras:
        out.append("<p>" + esc(p).replace("\n", "<br>") + "</p>")
    return "\n".join(out)


def abs_url(site_url: str, path: str) -> str:
    path = path.lstrip("/")
    return f"{site_url}/{path}"


def lastmod_iso(updated_at: str | None) -> str:
    if not updated_at:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Accept ISO with offset; sitemap wants date or datetime
    try:
        # date part is enough and widely accepted
        return updated_at[:10]
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def related_works(work: dict, all_works: list[dict]) -> list[dict]:
    tags = set(work.get("tags") or [])
    if not tags:
        return []
    scored = []
    for other in all_works:
        if other.get("id") == work.get("id"):
            continue
        shared = tags & set(other.get("tags") or [])
        if shared:
            scored.append((len(shared), other))
    scored.sort(key=lambda x: (-x[0], x[1].get("title") or ""))
    picks = [w for _, w in scored[:RELATED_MAX]]
    if len(picks) < RELATED_MIN:
        return picks  # may be fewer than 3 if catalog sparse
    return picks


def dlsite_cta(work: dict) -> str:
    url = (work.get("affiliate_url") or "").strip() or (work.get("url") or "").strip()
    if not url:
        wid = work.get("id") or ""
        url = f"https://www.dlsite.com/maniax/work/=/product_id/{wid}.html"
    return url


def shell_head(
    *,
    title: str,
    description: str,
    canonical: str,
    og_type: str = "website",
    image: str = "",
    depth: int = 0,
    json_ld: list | None = None,
    indexable: bool = True,
) -> str:
    prefix = "../" * depth
    robots = "index,follow" if indexable else "noindex,nofollow"
    og_image = image or ""
    parts = [
        "<!DOCTYPE html>",
        '<html lang="ja">',
        "<head>",
        '  <meta charset="UTF-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        f'  <meta name="robots" content="{robots}">',
        '  <meta name="rating" content="adult">',
        f'  <meta name="description" content="{esc(description)}">',
        f"  <title>{esc(title)}</title>",
        f'  <link rel="canonical" href="{esc(canonical)}">',
        f'  <meta property="og:site_name" content="{esc(SITE_NAME)}">',
        f'  <meta property="og:type" content="{esc(og_type)}">',
        f'  <meta property="og:title" content="{esc(title)}">',
        f'  <meta property="og:description" content="{esc(description)}">',
        f'  <meta property="og:url" content="{esc(canonical)}">',
        f'  <meta property="og:locale" content="ja_JP">',
    ]
    if og_image:
        parts += [
            f'  <meta property="og:image" content="{esc(og_image)}">',
            '  <meta name="twitter:card" content="summary_large_image">',
            f'  <meta name="twitter:title" content="{esc(title)}">',
            f'  <meta name="twitter:description" content="{esc(description)}">',
            f'  <meta name="twitter:image" content="{esc(og_image)}">',
        ]
    else:
        parts += ['  <meta name="twitter:card" content="summary">']
    parts.append(f'  <link rel="stylesheet" href="{prefix}css/styles.css">')
    if json_ld:
        for block in json_ld:
            parts.append(
                '  <script type="application/ld+json">'
                + json.dumps(block, ensure_ascii=False, separators=(",", ":"))
                + "</script>"
            )
    parts.append("</head>")
    return "\n".join(parts)


def age_gate_html() -> str:
    return """  <div id="age-gate">
    <div class="age-panel">
      <h2>年齢確認</h2>
      <p>18歳以上ですか？</p>
      <div class="age-actions">
        <button type="button" class="btn btn-primary" id="age-yes">はい</button>
        <button type="button" class="btn" id="age-no">いいえ</button>
      </div>
    </div>
  </div>"""


def header_nav(depth: int = 0, active: str = "") -> str:
    p = "../" * depth
    def nav(key: str, href: str, label: str) -> str:
        cls = ' class="active"' if key == active else ""
        return f'<a href="{p}{href}" data-nav="{key}"{cls}>{label}</a>'
    return f"""  <header class="site-header">
    <div class="container header-inner">
      <a class="brand" href="{p}index.html">
        <span class="brand-name">{esc(SITE_NAME)}</span>
        <span class="brand-tag">同人作品ガイド</span>
      </a>
      <div class="search-wrap">
        <label class="sr-only" for="global-search">作品を検索</label>
        <div class="search-field">
          <input type="search" id="global-search" name="q" placeholder="タイトル・サークル・タグ・紹介文" autocomplete="off" enterkeyhint="search" aria-label="作品を検索">
          <kbd class="search-kbd" aria-hidden="true">/</kbd>
          <button type="button" class="search-clear" id="search-clear" aria-label="検索をクリア" hidden>×</button>
        </div>
      </div>
      <div class="header-actions">
        <a class="icon-btn" id="nav-fav" href="{p}explore.html?view=fav" aria-label="お気に入り">♥ <span class="count" data-fav-count hidden>0</span></a>
      </div>
    </div>
  </header>
  <div class="nav-bar">
    <nav class="container nav" aria-label="メイン">
      {nav("home", "index.html", "ホーム")}
      {nav("explore", "explore.html", "探す")}
      {nav("ranking", "ranking.html", "人気")}
      {nav("sale", "sale.html", "セール")}
      {nav("fav", "explore.html?view=fav", "お気に入り")}
          </nav>
  </div>"""


def footer_html(depth: int, tag_links_html: str, updated_at: str = "") -> str:
    return f"""  <footer class="site-footer">
    <div class="container">
      {FOOTER_START}
      {tag_links_html}
      {FOOTER_END}
      <div class="disclaimer">
        <p id="data-updated"></p>
        <p><strong>18歳未満の方はご利用いただけません。</strong></p>
        <p>リンク先はDLsiteです。</p>
        <p>© {esc(SITE_NAME)}</p>
      </div>
    </div>
  </footer>"""


def popular_tags_block(top_tags: list[tuple[str, int]], depth: int, heading: str = "人気タグ") -> str:
    if not top_tags:
        return ""
    p = "../" * depth
    links = []
    for tag, n in top_tags:
        href = tag_href(tag, prefix=p)
        links.append(
            f'<a class="tag" href="{esc(href)}">{esc(tag)}<small> {n}</small></a>'
        )
    return f"""      <nav class="footer-tags" aria-label="{esc(heading)}">
        <p class="footer-tags-label">{esc(heading)}</p>
        <div class="footer-tags-list">{"".join(links)}</div>
      </nav>"""


def scripts_block(depth: int = 0) -> str:
    p = "../" * depth
    return f"""  <script src="{p}js/config.js"></script>
  <script src="{p}js/embedded-works.js"></script>
  <script src="{p}js/data.js"></script>
  <script src="{p}js/filters.js"></script>
  <script src="{p}js/search.js"></script>
  <script src="{p}js/app.js"></script>"""


def cover_html(work: dict, class_name: str = "work-hero-cover") -> str:
    hi = work.get("image") or ""
    thumb = work.get("image_thumb") or ""
    title = work.get("title") or ""
    if hi:
        srcset = ""
        if thumb and thumb != hi:
            srcset = (
                f' srcset="{esc(thumb)} 240w, {esc(hi)} 800w" '
                f'sizes="(max-width:720px) 90vw, 360px"'
            )
        return (
            f'<img class="{class_name}" src="{esc(hi)}"{srcset} alt="{esc(title)}" '
            f'loading="eager" decoding="async" referrerpolicy="no-referrer">'
        )
    return (
        f'<div class="{class_name} placeholder" aria-hidden="true">'
        f"<span>{esc(title[:18])}</span></div>"
    )


def generate_work_page(
    work: dict,
    all_works: list[dict],
    site_url: str,
    top_tags: list[tuple[str, int]],
    updated_at: str,
) -> str:
    wid = work["id"]
    title = work.get("title") or wid
    maker = work.get("maker") or ""
    full_title = page_title(title, maker)
    desc = meta_description(
        work.get("description") or "",
        f"{title}（{maker}）の作品情報 — {SITE_NAME}",
    )
    canonical = abs_url(site_url, f"works/{wid}.html")
    image = work.get("image") or work.get("image_thumb") or ""
    cta = dlsite_cta(work)
    related = related_works(work, all_works)

    product_ld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "description": desc,
        "sku": wid,
        "url": canonical,
        "image": image or None,
        "brand": {"@type": "Brand", "name": maker} if maker else None,
        "category": type_label(work),
        "offers": {
            "@type": "Offer",
            "url": cta,
            "priceCurrency": "JPY",
            "price": work.get("price") if work.get("price") is not None else None,
            "availability": "https://schema.org/InStock",
            "seller": {"@type": "Organization", "name": "DLsite"},
        },
    }
    # prune Nones
    product_ld = {k: v for k, v in product_ld.items() if v is not None}
    if product_ld.get("offers"):
        product_ld["offers"] = {
            k: v for k, v in product_ld["offers"].items() if v is not None
        }

    creative_ld = {
        "@context": "https://schema.org",
        "@type": "CreativeWork",
        "name": title,
        "description": desc,
        "url": canonical,
        "image": image or None,
        "creator": {"@type": "Organization", "name": maker} if maker else None,
        "genre": (work.get("tags") or [])[:6] or None,
        "identifier": wid,
    }
    creative_ld = {k: v for k, v in creative_ld.items() if v is not None}

    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ホーム", "item": abs_url(site_url, "index.html")},
            {"@type": "ListItem", "position": 2, "name": "探す", "item": abs_url(site_url, "explore.html")},
            {"@type": "ListItem", "position": 3, "name": title, "item": canonical},
        ],
    }

    tags = (work.get("tags") or [])[:6]
    tag_bits = []
    for t in tags:
        href = explore_tag_href(t, prefix="../")
        tag_bits.append(f'<a class="tag" href="{esc(href)}">{esc(t)}</a>')
    tag_links = " ".join(tag_bits) or '<span class="tag">タグなし</span>'

    related_html = ""
    if related:
        cards = []
        for rw in related:
            rid = rw["id"]
            rtitle = rw.get("title") or rid
            rmaker = rw.get("maker") or ""
            rimg = rw.get("image_thumb") or rw.get("image") or ""
            img = (
                f'<img class="card-cover" src="{esc(rimg)}" alt="" loading="lazy" '
                f'decoding="async" referrerpolicy="no-referrer">'
                if rimg
                else f'<div class="card-cover placeholder"><span>{esc(rtitle[:12])}</span></div>'
            )
            cards.append(
                f"""        <article class="card">
          <a class="card-media" href="{esc(rid)}.html" aria-label="{esc(rtitle)}">
            {img}
          </a>
          <div class="card-body">
            <p class="card-maker">{esc(rmaker)}</p>
            <h3 class="card-title"><a href="{esc(rid)}.html">{esc(rtitle)}</a></h3>
            <div class="card-meta">{format_price_html(rw)}</div>
          </div>
        </article>"""
            )
        related_html = f"""
    <section class="section work-related">
      <div class="container">
        <div class="section-head"><h2>関連作品</h2><a href="../explore.html">すべて探す →</a></div>
        <div class="grid">{chr(10).join(cards)}
        </div>
      </div>
    </section>"""

    sale_badge = '<span class="badge-sale">セール</span>' if work.get("on_sale") else ""
    head = shell_head(
        title=full_title,
        description=desc,
        canonical=canonical,
        og_type="product",
        image=image,
        depth=1,
        json_ld=[product_ld, creative_ld, breadcrumb_ld],
        indexable=True,
    )
    tags_footer = popular_tags_block(top_tags[:16], depth=1)

    body = f"""{head}
<body data-page="work" data-work-id="{esc(wid)}">
{age_gate_html()}
{header_nav(depth=1, active="explore")}
  <main>
    <div class="container">
      <nav class="breadcrumb" aria-label="パンくず">
        <a href="../index.html">ホーム</a>
        <span aria-hidden="true">/</span>
        <a href="../explore.html">探す</a>
        <span aria-hidden="true">/</span>
        <span>{esc(title)}</span>
      </nav>
    </div>
    <article class="work-page">
      <div class="container work-layout">
        <div class="work-media">
          {cover_html(work)}
          {sale_badge}
        </div>
        <div class="work-main">
          <p class="work-maker">{esc(maker or "サークル未記載")}</p>
          <h1 class="work-title">{esc(title)}</h1>
          <div class="work-price">{format_price_html(work)}</div>
          <ul class="drawer-meta-list work-meta">
            <li><span>形式</span>{esc(type_label(work))}</li>
            <li><span>作品ID</span>{esc(wid)}</li>
            <li><span>状態</span>{"セール中" if work.get("on_sale") else "通常価格"}</li>
          </ul>
          <div class="drawer-tags work-tags" aria-label="ジャンルタグ">{tag_links}</div>
          <div class="drawer-actions work-actions">
            <a class="btn-cta" href="{esc(cta)}" target="_blank" rel="noopener noreferrer">DLsiteで見る</a>
            <a class="btn" href="../explore.html">カタログへ戻る</a>
          </div>
        </div>
      </div>
      <div class="container">
        <div class="drawer-desc work-desc">
          <h2 class="drawer-desc-title">作品紹介</h2>
          <div class="drawer-desc-body">
{description_html(work.get("description") or "")}
          </div>
        </div>
      </div>
    </article>
{related_html}
  </main>
{footer_html(1, tags_footer, updated_at)}
{scripts_block(1)}
</body>
</html>
"""
    return body


def generate_tag_page(
    tag: str,
    count: int,
    works: list[dict],
    site_url: str,
    top_tags: list[tuple[str, int]],
    updated_at: str,
    slug: str | None = None,
) -> str:
    slug = slug or tag_slug(tag)
    full_title = f"{tag}の同人作品｜{SITE_NAME}"
    desc = meta_description(
        f"「{tag}」タグの同人作品一覧（{count}件）。{SITE_NAME}で形式やセール条件と合わせて探せます。",
        f"{tag} — {SITE_NAME}",
        lo=40,
        hi=120,
    )
    canonical = abs_url(site_url, f"tags/{slug}.html")
    # Prefer first work image as OG
    image = ""
    for w in works:
        image = w.get("image") or w.get("image_thumb") or ""
        if image:
            break

    item_list = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": full_title,
        "description": desc,
        "url": canonical,
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(works),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "url": abs_url(site_url, f"works/{w['id']}.html"),
                    "name": w.get("title") or w["id"],
                }
                for i, w in enumerate(works[:50])
            ],
        },
    }
    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ホーム", "item": abs_url(site_url, "index.html")},
            {"@type": "ListItem", "position": 2, "name": "探す", "item": abs_url(site_url, "explore.html")},
            {"@type": "ListItem", "position": 3, "name": tag, "item": canonical},
        ],
    }

    cards = []
    for w in works:
        wid = w["id"]
        wtitle = w.get("title") or wid
        wmaker = w.get("maker") or ""
        wimg = w.get("image_thumb") or w.get("image") or ""
        img = (
            f'<img class="card-cover" src="{esc(wimg)}" alt="" loading="lazy" '
            f'decoding="async" referrerpolicy="no-referrer">'
            if wimg
            else f'<div class="card-cover placeholder"><span>{esc(wtitle[:12])}</span></div>'
        )
        sale = '<span class="badge-sale">セール</span>' if w.get("on_sale") else ""
        cards.append(
            f"""        <article class="card">
          <a class="card-media" href="../works/{esc(wid)}.html" aria-label="{esc(wtitle)}">
            {img}{sale}
          </a>
          <div class="card-body">
            <p class="card-maker">{esc(wmaker)}</p>
            <h2 class="card-title"><a href="../works/{esc(wid)}.html">{esc(wtitle)}</a></h2>
            <div class="card-meta">{format_price_html(w)} <span class="work-type">{esc(type_label(w))}</span></div>
          </div>
        </article>"""
        )

    head = shell_head(
        title=full_title,
        description=desc,
        canonical=canonical,
        og_type="website",
        image=image,
        depth=1,
        json_ld=[item_list, breadcrumb_ld],
        indexable=True,
    )
    tags_footer = popular_tags_block(
        [(t, n) for t, n in top_tags if t != tag][:16], depth=1, heading="ほかの人気タグ"
    )

    return f"""{head}
<body data-page="tag" data-tag="{esc(tag)}">
{age_gate_html()}
{header_nav(depth=1, active="explore")}
  <main>
    <div class="container page-hero">
      <nav class="breadcrumb" aria-label="パンくず">
        <a href="../index.html">ホーム</a>
        <span aria-hidden="true">/</span>
        <a href="../explore.html">探す</a>
        <span aria-hidden="true">/</span>
        <span>{esc(tag)}</span>
      </nav>
      <h1>タグ：{esc(tag)}</h1>
      <p>{count}件の作品。<a href="{esc(explore_tag_href(tag, prefix="../"))}">絞り込みで探す</a></p>
    </div>
    <section class="section" style="padding-top:0.5rem">
      <div class="container">
        <div class="grid">
{chr(10).join(cards)}
        </div>
      </div>
    </section>
  </main>
{footer_html(1, tags_footer, updated_at)}
{scripts_block(1)}
</body>
</html>
"""


def write_robots(site_url: str) -> None:
    sitemap = abs_url(site_url, "sitemap.xml")
    text = f"""# 同人ピック robots.txt
User-agent: *
Allow: /
Disallow: /scripts/
Disallow: /data/

# Absolute sitemap (set SITE_URL or js/config.js siteUrl before deploy)
Sitemap: {sitemap}
"""
    (ROOT / "robots.txt").write_text(text, encoding="utf-8")


def write_sitemap(
    site_url: str,
    works: list[dict],
    tag_slugs: list[str],
    updated_at: str,
) -> int:
    lm = lastmod_iso(updated_at)
    urls: list[tuple[str, str, str]] = []
    # path, lastmod, priority
    static = [
        ("index.html", "1.0"),
        ("explore.html", "0.9"),
        ("ranking.html", "0.8"),
        ("sale.html", "0.8"),
        ("genre.html", "0.7"),
    ]
    for path, pri in static:
        urls.append((abs_url(site_url, path), lm, pri))
    for w in works:
        urls.append((abs_url(site_url, f"works/{w['id']}.html"), lm, "0.8"))
    for slug in tag_slugs:
        urls.append((abs_url(site_url, f"tags/{slug}.html"), lm, "0.6"))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f"  <!-- siteUrl={site_url} ; path-only mirrors: /index.html /explore.html /works/{{id}}.html /tags/{{slug}}.html -->",
    ]
    for loc, lastmod, pri in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{esc(loc)}</loc>")
        lines.append(f"    <lastmod>{esc(lastmod)}</lastmod>")
        lines.append(f"    <priority>{pri}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    lines.append("")
    (ROOT / "sitemap.xml").write_text("\n".join(lines), encoding="utf-8")
    return len(urls)


def write_tag_cloud_js(top_tags: list[tuple[str, int]]) -> None:
    payload = [{"tag": t, "count": n, "slug": tag_slug(t)} for t, n in top_tags]
    text = (
        "/** Auto-generated by scripts/generate_seo_pages.py — do not edit */\n"
        "window.DOJIN_TAG_CLOUD = "
        + json.dumps(payload, ensure_ascii=False)
        + ";\n"
    )
    (ROOT / "js" / "tag-cloud-data.js").write_text(text, encoding="utf-8")


def patch_main_pages(site_url: str, top_tags: list[tuple[str, int]], updated_at: str) -> None:
    """Remove noindex, improve head meta/OG, inject footer + explore noscript tags."""
    footer_inner = popular_tags_block(top_tags[:24], depth=0)
    noscript_links = []
    for tag, n in top_tags[:40]:
        noscript_links.append(
            f'<li><a href="{esc(tag_href(tag))}">{esc(tag)}</a>（{n}）</li>'
        )
    noscript_block = (
        f"{NOSCRIPT_START}\n"
        f'<noscript class="seo-tag-noscript"><div class="container">'
        f"<h2>人気タグ</h2><ul>{''.join(noscript_links)}</ul></div></noscript>\n"
        f"{NOSCRIPT_END}"
    )

    for fname, _page in MAIN_PAGES:
        path = ROOT / fname
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        meta = PAGE_META.get(fname, {})
        title = meta.get("title") or f"{fname}｜{SITE_NAME}"
        description = meta.get("description") or f"{SITE_NAME}"
        canonical = abs_url(site_url, fname)

        # robots → indexable
        text = re.sub(
            r'<meta\s+name="robots"\s+content="[^"]*"\s*/?>',
            '<meta name="robots" content="index,follow">',
            text,
            count=1,
        )
        if 'name="robots"' not in text:
            text = text.replace(
                '<meta charset="UTF-8">',
                '<meta charset="UTF-8">\n  <meta name="robots" content="index,follow">',
                1,
            )

        # rating
        if 'name="rating"' not in text:
            text = text.replace(
                '<meta name="robots" content="index,follow">',
                '<meta name="robots" content="index,follow">\n  <meta name="rating" content="adult">',
                1,
            )

        # description
        if re.search(r'<meta\s+name="description"', text):
            text = re.sub(
                r'<meta\s+name="description"\s+content="[^"]*"\s*/?>',
                f'<meta name="description" content="{esc(description)}">',
                text,
                count=1,
            )
        else:
            text = text.replace(
                '<meta name="robots" content="index,follow">',
                f'<meta name="robots" content="index,follow">\n  <meta name="description" content="{esc(description)}">',
                1,
            )

        # title
        text = re.sub(r"<title>[^<]*</title>", f"<title>{esc(title)}</title>", text, count=1)

        # canonical + og block: replace existing SEO_HEAD markers or insert before stylesheet
        seo_head = "\n".join(
            [
                f'  <link rel="canonical" href="{esc(canonical)}">',
                f'  <meta property="og:site_name" content="{esc(SITE_NAME)}">',
                '  <meta property="og:type" content="website">',
                f'  <meta property="og:title" content="{esc(title)}">',
                f'  <meta property="og:description" content="{esc(description)}">',
                f'  <meta property="og:url" content="{esc(canonical)}">',
                '  <meta property="og:locale" content="ja_JP">',
                '  <meta name="twitter:card" content="summary">',
                f'  <meta name="twitter:title" content="{esc(title)}">',
                f'  <meta name="twitter:description" content="{esc(description)}">',
            ]
        )
        # strip previous generated head bits (canonical/og/twitter) to avoid dupes
        text = re.sub(r'\n\s*<link rel="canonical"[^>]*>', "", text)
        text = re.sub(r'\n\s*<meta property="og:[^"]+" content="[^"]*"\s*/?>', "", text)
        text = re.sub(r'\n\s*<meta name="twitter:[^"]+" content="[^"]*"\s*/?>', "", text)

        if "css/styles.css" in text:
            text = text.replace(
                '  <link rel="stylesheet" href="css/styles.css">',
                seo_head + '\n  <link rel="stylesheet" href="css/styles.css">',
                1,
            )

        # Ensure tag-cloud-data.js is loaded on explore (before app.js)
        if fname == "explore.html" and "tag-cloud-data.js" not in text:
            text = text.replace(
                '<script src="js/app.js"></script>',
                '<script src="js/tag-cloud-data.js"></script>\n  <script src="js/app.js"></script>',
                1,
            )

        # Footer tags injection — rewrite whole footer to keep markup valid
        footer_html_block = (
            '  <footer class="site-footer">\n'
            '    <div class="container">\n'
            f"      {FOOTER_START}\n"
            f"{footer_inner}\n"
            f"      {FOOTER_END}\n"
            '      <div class="disclaimer">\n'
            '      <p id="data-updated"></p>\n'
            '      <p><strong>18歳未満の方はご利用いただけません。</strong></p>\n'
            '      <p>リンク先はDLsiteです。</p>\n'
            '      <p>© 同人ピック</p>\n'
            '      </div>\n'
            '    </div>\n'
            '  </footer>'
        )
        if re.search(r'<footer class="site-footer">.*?</footer>', text, flags=re.S):
            text = re.sub(
                r'<footer class="site-footer">.*?</footer>',
                footer_html_block,
                text,
                count=1,
                flags=re.S,
            )


        # Explore noscript crawlable list
        if fname == "explore.html":
            if NOSCRIPT_START in text and NOSCRIPT_END in text:
                text = re.sub(
                    re.escape(NOSCRIPT_START) + r".*?" + re.escape(NOSCRIPT_END),
                    noscript_block,
                    text,
                    count=1,
                    flags=re.S,
                )
            else:
                text = text.replace(
                    "<main>",
                    f"<main>\n    {noscript_block}",
                    1,
                )

        path.write_text(text, encoding="utf-8")


def sync_work_dir(works: list[dict]) -> None:
    WORKS_DIR.mkdir(parents=True, exist_ok=True)
    wanted = {f"{w['id']}.html" for w in works}
    for existing in WORKS_DIR.glob("*.html"):
        if existing.name not in wanted:
            existing.unlink()


def sync_tag_dir(slugs: set[str]) -> None:
    TAGS_DIR.mkdir(parents=True, exist_ok=True)
    wanted = {f"{s}.html" for s in slugs}
    for existing in TAGS_DIR.glob("*.html"):
        if existing.name not in wanted:
            existing.unlink()


def main() -> int:
    if not DATA.exists():
        print(f"Missing {DATA}", file=sys.stderr)
        return 1
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    works = payload.get("works") or []
    updated_at = payload.get("updated_at") or ""
    site_url = resolve_site_url()

    counter: Counter[str] = Counter()
    for w in works:
        for t in w.get("tags") or []:
            if t and str(t).strip():
                counter[str(t).strip()] += 1
    top_tags = counter.most_common(TAG_PAGE_LIMIT)

    WORKS_DIR.mkdir(parents=True, exist_ok=True)
    TAGS_DIR.mkdir(parents=True, exist_ok=True)

    # Work pages
    for w in works:
        html_out = generate_work_page(w, works, site_url, top_tags, updated_at)
        (WORKS_DIR / f"{w['id']}.html").write_text(html_out, encoding="utf-8")
    sync_work_dir(works)

    # Tag pages
    tag_slugs: list[str] = []
    slug_set: set[str] = set()
    for tag, n in top_tags:
        slug = tag_slug(tag)
        # avoid collisions
        base = slug
        i = 2
        while slug in slug_set:
            slug = f"{base}-{i}"
            i += 1
        slug_set.add(slug)
        # if collision renamed, still use tag_slug in href via mapping — keep simple: first wins
        matched = [w for w in works if tag in (w.get("tags") or [])]
        page = generate_tag_page(tag, n, matched, site_url, top_tags, updated_at, slug=slug)
        (TAGS_DIR / f"{slug}.html").write_text(page, encoding="utf-8")
        tag_slugs.append(slug)
    sync_tag_dir(slug_set)

    write_robots(site_url)
    url_count = write_sitemap(site_url, works, tag_slugs, updated_at)
    write_tag_cloud_js(top_tags)
    patch_main_pages(site_url, top_tags, updated_at)

    print(
        f"SEO: {len(works)} work pages, {len(tag_slugs)} tag pages, "
        f"sitemap urls={url_count}, siteUrl={site_url}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
