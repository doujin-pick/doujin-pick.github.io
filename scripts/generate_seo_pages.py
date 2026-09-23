#!/usr/bin/env python3
"""Generate crawlable static SEO pages from data/works.json.

Outputs:
  works/{id}.html       — per-work detail (indexable)
  tags/{slug}.html      — top tag landings
  circles/{slug}.html   — top circle guide pages (long-tail SEO)
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
WORK_CACHE = ROOT / "data" / "cache" / "works"
CONFIG_JS = ROOT / "js" / "config.js"
WORKS_DIR = ROOT / "works"
TAGS_DIR = ROOT / "tags"
CIRCLES_DIR = ROOT / "circles"
DEFAULT_SITE_URL = "https://doujin-pick.example"
SITE_NAME = "同人ピック"
TAG_PAGE_LIMIT = 60
CIRCLE_PAGE_LIMIT = 40
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
        "title": "同人ピック｜DLsite同人の人気・セールまとめ",
        "description": "同人ピックは、DLsiteの同人作品を人気・セール・ジャンルから探しやすくまとめたガイドです（18歳以上向け）。",
    },
    "explore.html": {
        "title": "すべて探す｜同人ピック",
        "description": "タイトル・サークル・タグで同人を検索。形式・セール・価格帯・並び順で絞り込めます（18歳以上）。",
    },
    "ranking.html": {
        "title": "人気ランキング｜同人ピック",
        "description": "人気の同人作品一覧です。形式やセールでも絞り込めます（18歳以上向け）。",
    },
    "sale.html": {
        "title": "セール一覧｜同人ピック",
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



def hydrate_descriptions_from_cache(works: list[dict]) -> int:
    """Restore full blurbs from work HTML cache so SEO pages stay rich after catalog truncation."""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "dojin_update_works", ROOT / "scripts" / "update_works.py"
        )
        if spec is None or spec.loader is None:
            return 0
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        extract = getattr(mod, "extract_description", None)
        if not callable(extract):
            return 0
    except Exception:
        return 0
    n = 0
    for w in works:
        wid = w.get("id") or ""
        if not wid or str(wid).startswith("SAMPLE"):
            continue
        cache_path = WORK_CACHE / f"{wid}.html"
        if not cache_path.exists():
            continue
        try:
            html_text = cache_path.read_text(encoding="utf-8", errors="replace")
            full = (extract(html_text) or "").strip()
            cur = (w.get("description") or "").strip()
            if len(full) > len(cur):
                w["description"] = full
                n += 1
        except Exception:
            continue
    return n


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


def page_title(title: str, maker: str = "") -> str:
    """{title}｜紹介・タグ・価格｜同人ピック — title first; truncate carefully."""
    site = SITE_NAME
    t = clean_text(title) or "作品"
    mid = "｜紹介・タグ・価格"
    suffix = f"｜{site}"
    # ~60–70 visible chars for SERP; keep work title as long as possible
    budget = 70
    remain = budget - len(mid) - len(suffix)
    if len(t) > max(remain, 12):
        t = t[: max(remain, 12) - 1] + "…"
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


def circle_slug(name: str) -> str:
    """Filesystem-safe slug for circle guide pages (same rules as tags)."""
    return tag_slug(name) or "circle"


def circle_href(name: str, prefix: str = "") -> str:
    slug = circle_slug(name)
    return f"{prefix}circles/{quote(slug)}.html"


def top_circles(works: list[dict], limit: int = CIRCLE_PAGE_LIMIT) -> list[tuple[str, int, list[dict]]]:
    """Return [(maker, count, works_sorted)] for top circles by work count."""
    buckets: dict[str, list[dict]] = {}
    for w in works:
        m = (w.get("maker") or "").strip()
        if not m:
            continue
        buckets.setdefault(m, []).append(w)

    def sort_key(w: dict):
        cat = w.get("category") or ""
        cat_rank = 0 if cat == "asmr" else (1 if cat == "game" else 2)
        return (cat_rank, -(w.get("discount_percent") or 0), w.get("title") or "")

    rows: list[tuple[str, int, list[dict]]] = []
    for maker, ws in buckets.items():
        ws_sorted = sorted(ws, key=sort_key)
        rows.append((maker, len(ws_sorted), ws_sorted))
    rows.sort(key=lambda x: (-x[1], x[0]))
    return rows[:limit]



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


def work_meta_description(title: str, maker: str, desc: str) -> str:
    """Meta description must start with the work title for title-query ranking."""
    t = clean_text(title) or "作品"
    m = clean_text(maker)
    body = clean_text(desc)
    head = f"{t}の紹介"
    if m:
        head += f"。サークルは{m}"
    head += "。"
    if body:
        # Avoid duplicating title if description already starts with it
        rest = body
        if rest.startswith(t):
            rest = rest[len(t):].lstrip(" 　—－|｜:：。．.")
        combined = head + rest
    else:
        combined = head + f"{SITE_NAME}の作品ページです。"
    return meta_description(combined, head, lo=60, hi=120)


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
    maker_html = (
        f'<a href="{esc(circle_href(maker, prefix="../"))}">{esc(maker)}</a>'
        if maker else "サークル未記載"
    )
    full_title = page_title(title, maker)
    desc = work_meta_description(title, maker, work.get("description") or "")
    canonical = abs_url(site_url, f"works/{wid}.html")
    image = work.get("image") or work.get("image_thumb") or ""
    cta = dlsite_cta(work)
    related = related_works(work, all_works)

    circle_other_html = ""
    if maker:
        same = [
            w for w in all_works
            if (w.get("maker") or "").strip() == maker and w.get("id") != work.get("id")
        ]
        # Prefer voice/game, then title
        def _ck(w: dict):
            cat = w.get("category") or ""
            return (0 if cat == "asmr" else 1 if cat == "game" else 2, w.get("title") or "")
        same = sorted(same, key=_ck)[:8]
        if same:
            items = []
            cards = []
            for rw in same:
                rid = rw["id"]
                rtitle = rw.get("title") or rid
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
            <h3 class="card-title"><a href="{esc(rid)}.html">{esc(rtitle)}</a></h3>
            <div class="card-meta">{format_price_html(rw)}</div>
          </div>
        </article>"""
                )
                items.append(f'<li><a href="{esc(rid)}.html">{esc(rtitle)}</a></li>')
            circle_other_html = f"""
    <section class="section work-related circle-other-works">
      <div class="container">
        <div class="section-head"><h2>このサークルの他作品</h2><a href="{esc(circle_href(maker, prefix="../"))}">サークルページ →</a></div>
        <ul class="related-title-list">
          {chr(10).join("          " + x for x in items)}
        </ul>
        <div class="grid">{chr(10).join(cards)}
        </div>
      </div>
    </section>"""

    product_ld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "description": desc,
        "sku": wid,
        "url": canonical,
        "image": image or None,
        "brand": {"@type": "Brand", "name": maker} if maker else None,
        "author": {"@type": "Organization", "name": maker} if maker else None,
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
        "author": {"@type": "Organization", "name": maker} if maker else None,
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

    # Related: card grid + plain title text links (strong internal anchor signals)
    related_html = ""
    if related:
        cards = []
        text_links = []
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
            text_links.append(f'<li><a href="{esc(rid)}.html">{esc(rtitle)}</a></li>')
        related_html = f"""
    <section class="section work-related">
      <div class="container">
        <div class="section-head"><h2>関連作品</h2><a href="../explore.html">すべて探す →</a></div>
        <ul class="related-title-list">
          {chr(10).join("          " + x for x in text_links)}
        </ul>
        <div class="grid">{chr(10).join(cards)}
        </div>
      </div>
    </section>"""

    sale_badge = '<span class="badge-sale">セール</span>' if work.get("on_sale") else ""
    price_state = "セール中" if work.get("on_sale") else "通常価格"
    raw_desc = (work.get("description") or "").strip()
    lead_bits = [f"「{title}」の紹介ページです。"]
    if maker:
        lead_bits.append(f"サークルは{maker}。")
    lead = "".join(lead_bits)
    # Short natural follow-on from description (first sentence-ish), not spammy
    if raw_desc:
        snippet = clean_text(raw_desc)
        if len(snippet) > 160:
            cut = snippet[:160]
            for sep in ("。", "！", "？", "、", " "):
                i = cut.rfind(sep)
                if i >= 60:
                    cut = cut[: i + (1 if sep in "。！？" else 0)]
                    break
            snippet = cut.rstrip() + ("…" if len(clean_text(raw_desc)) > len(cut) else "")
        lead_extra = snippet
    else:
        lead_extra = f"{type_label(work)}作品のタグ・価格情報をまとめています。"

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
          <p class="work-maker">{maker_html}</p>
          <h1 class="work-title">{esc(title)}</h1>
          <p class="work-lead">{esc(lead)}{esc(lead_extra)}</p>
          <div class="drawer-actions work-actions">
            <a class="btn-cta" href="{esc(cta)}" target="_blank" rel="noopener noreferrer">DLsiteで見る</a>
            <a class="btn" href="../explore.html">カタログへ戻る</a>
          </div>
        </div>
      </div>
      <div class="container work-sections">
        <section class="work-section" aria-labelledby="sec-price">
          <h2 id="sec-price">価格・セール</h2>
          <div class="work-price">{format_price_html(work)}</div>
          <ul class="drawer-meta-list work-meta">
            <li><span>形式</span>{esc(type_label(work))}</li>
            <li><span>作品ID</span>{esc(wid)}</li>
            <li><span>状態</span>{esc(price_state)}</li>
          </ul>
        </section>
        <section class="work-section" aria-labelledby="sec-tags">
          <h2 id="sec-tags">タグ</h2>
          <div class="drawer-tags work-tags" aria-label="ジャンルタグ">{tag_links}</div>
        </section>
        <section class="work-section" aria-labelledby="sec-content">
          <h2 id="sec-content" class="drawer-desc-title">作品の内容</h2>
          <div class="drawer-desc work-desc">
            <div class="drawer-desc-body">
{description_html(work.get("description") or "")}
            </div>
          </div>
        </section>
      </div>
    </article>
{circle_other_html}
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



def generate_circle_page(
    maker: str,
    count: int,
    works: list[dict],
    site_url: str,
    top_tags: list[tuple[str, int]],
    updated_at: str,
    slug: str | None = None,
) -> str:
    slug = slug or circle_slug(maker)
    full_title = f"{maker}のおすすめ同人｜{SITE_NAME}"
    desc = meta_description(
        f"{maker}の同人作品おすすめ（{count}件）。ボイス・ASMRやゲームを中心に、{SITE_NAME}で紹介しています。",
        f"{maker} — {SITE_NAME}",
        lo=40,
        hi=120,
    )
    canonical = abs_url(site_url, f"circles/{slug}.html")
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
        "about": {"@type": "Organization", "name": maker},
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
            {"@type": "ListItem", "position": 2, "name": "サークル", "item": abs_url(site_url, "index.html") + "#circles-section"},
            {"@type": "ListItem", "position": 3, "name": maker, "item": canonical},
        ],
    }

    cards = []
    for w in works:
        wid = w["id"]
        wtitle = w.get("title") or wid
        wimg = w.get("image_thumb") or w.get("image") or ""
        img = (
            f'<img class="card-cover" src="{esc(wimg)}" alt="" loading="lazy" '
            f'decoding="async" referrerpolicy="no-referrer">'
            if wimg
            else f'<div class="card-cover placeholder"><span>{esc(wtitle[:12])}</span></div>'
        )
        sale = ""
        if w.get("on_sale"):
            if w.get("discount_percent"):
                sale = f'<span class="badge-sale">{int(w["discount_percent"])}%OFF</span>'
            else:
                sale = '<span class="badge-sale">セール</span>'
        cta = dlsite_cta(w)
        cards.append(
            f"""        <article class="card">
          <a class="card-media" href="../works/{esc(wid)}.html" aria-label="{esc(wtitle)}">
            {img}{sale}
          </a>
          <div class="card-body">
            <h2 class="card-title"><a href="../works/{esc(wid)}.html">{esc(wtitle)}</a></h2>
            <div class="card-meta">{format_price_html(w)} <span class="work-type">{esc(type_label(w))}</span></div>
            <div class="card-open"><a class="btn-cta" href="{esc(cta)}" target="_blank" rel="noopener noreferrer">DLsiteで見る</a></div>
          </div>
        </article>"""
        )

    voice_n = sum(1 for w in works if w.get("category") == "asmr")
    game_n = sum(1 for w in works if w.get("category") == "game")
    focus_bits = []
    if voice_n:
        focus_bits.append(f"ボイス・ASMR {voice_n}件")
    if game_n:
        focus_bits.append(f"ゲーム {game_n}件")
    focus = "、".join(focus_bits) if focus_bits else "同人作品"
    intro = (
        f"{maker}の同人作品を、{SITE_NAME}がカタログからピックアップしています。"
        f"掲載は{count}件（{focus}）。気になる作品は各ページからDLsiteで詳細・購入できます。"
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
    tags_footer = popular_tags_block(top_tags[:16], depth=1, heading="人気タグ")

    return f"""{head}
<body data-page="circle" data-circle="{esc(maker)}">
{age_gate_html()}
{header_nav(depth=1, active="explore")}
  <main>
    <div class="container page-hero circle-page-hero">
      <nav class="breadcrumb" aria-label="パンくず">
        <a href="../index.html">ホーム</a>
        <span aria-hidden="true">/</span>
        <a href="../index.html#circles-section">サークル</a>
        <span aria-hidden="true">/</span>
        <span>{esc(maker)}</span>
      </nav>
      <h1>{esc(maker)}のおすすめ同人</h1>
      <p class="lede">{esc(intro)}</p>
      <p class="circle-works-count">{count}件の作品</p>
    </div>
    <section class="section" style="padding-top:0.5rem">
      <div class="container">
        <div class="grid">
{chr(10).join(cards)}
        </div>
        <p style="margin-top:1.25rem">
          <a class="btn-cta" href="../explore.html?q={quote(maker)}">カタログで「{esc(maker)}」を探す</a>
        </p>
      </div>
    </section>
  </main>
{footer_html(1, tags_footer, updated_at)}
{scripts_block(1)}
</body>
</html>
"""


def write_llms_txt(site_url: str) -> None:
    """Optional llms.txt for AI/crawler discoverability (skip-safe if unused)."""
    text = f"""# 同人ピック
> DLsiteの同人作品を、人気・セール・ジャンルから探しやすくまとめたガイド（18歳以上向け）

サイト名: {SITE_NAME}
URL: {site_url}/
Sitemap: {site_url}/sitemap.xml

## 主要ページ
- [ホーム]({site_url}/index.html): おすすめ・人気・セールの入口
- [探す]({site_url}/explore.html): タイトル・サークル・タグ検索
- [人気]({site_url}/ranking.html): 人気ランキング
- [セール]({site_url}/sale.html): 割引中の作品

## 作品ページ
各作品は {site_url}/works/{{id}}.html （紹介・タグ・価格）

## サークルガイド
主要サークルは {site_url}/circles/{{slug}}.html （サークルのおすすめ同人）
"""
    (ROOT / "llms.txt").write_text(text, encoding="utf-8")


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
    circle_slugs: list[str] | None = None,
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
    for slug in circle_slugs or []:
        urls.append((abs_url(site_url, f"circles/{slug}.html"), lm, "0.65"))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f"  <!-- siteUrl={site_url} ; path-only mirrors: /index.html /explore.html /works/{{id}}.html /tags/{{slug}}.html /circles/{{slug}}.html -->",
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

        # Homepage brand SEO: H1「同人ピック」, intro, JSON-LD, crawlable work links
        if fname == "index.html":
            text = ensure_homepage_brand_seo(text, site_url, _INDEX_WORKS_CACHE)

        path.write_text(text, encoding="utf-8")


def ensure_homepage_brand_seo(text: str, site_url: str, works: list[dict] | None = None) -> str:
    """Visible brand H1/intro + WebSite/Organization JSON-LD + noscript title links."""
    # H1 must contain exact 同人ピック
    h1_block = (
        '<h1 class="home-title">'
        '<span class="home-title-brand nowrap">同人ピック</span>'
        '<span class="home-title-sub">'
        '<span class="nowrap">気になる同人を、</span><wbr>'
        '<span class="nowrap">かんたんに見つける</span>'
        "</span></h1>\n"
        '          <p class="lede">'
        '<span class="lede-line nowrap">人気・セール・形式から、同人をかんたんに。</span>\n'
        '          <span class="lede-line nowrap">気になる作品を見つけて、購入はDLsiteで。</span></p>'
    )
    text2, n = re.subn(
        r"<h1\b[^>]*>.*?</h1>\s*<p class=\"lede\">.*?</p>",
        h1_block,
        text,
        count=1,
        flags=re.S,
    )
    if n:
        text = text2
    else:
        # Fallback: inject after home-intro-grid / ja-wrap opening
        text = re.sub(
            r'(<div class="(?:container )?home-intro-grid">\s*<div(?: class="ja-wrap")?>)',
            r"\1\n          " + h1_block,
            text,
            count=1,
        )

    website_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": abs_url(site_url, "index.html"),
        "description": PAGE_META["index.html"]["description"],
        "inLanguage": "ja",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": abs_url(site_url, "explore.html") + "?q={search_term_string}",
            },
            "query-input": "required name=search_term_string",
        },
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": abs_url(site_url, "index.html"),
        },
    }
    org_ld = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": SITE_NAME,
        "url": abs_url(site_url, "index.html"),
    }
    ld_scripts = (
        '  <script type="application/ld+json">'
        + json.dumps(website_ld, ensure_ascii=False, separators=(",", ":"))
        + "</script>\n"
        + '  <script type="application/ld+json">'
        + json.dumps(org_ld, ensure_ascii=False, separators=(",", ":"))
        + "</script>"
    )
    text = re.sub(
        r'\n\s*<script type="application/ld\+json">.*?</script>',
        "",
        text,
        flags=re.S,
    )
    if "</head>" in text:
        text = text.replace("</head>", ld_scripts + "\n</head>", 1)

    works = works or []
    featured = [w for w in works if "featured" in (w.get("sections") or [])]
    ranking = [w for w in works if "ranking" in (w.get("sections") or [])]
    ordered = featured + ranking + works
    seen: set[str] = set()
    links: list[str] = []
    for w in ordered:
        wid = w.get("id")
        if not wid or wid in seen:
            continue
        seen.add(wid)
        t = w.get("title") or wid
        links.append(f'<li><a href="works/{esc(wid)}.html">{esc(t)}</a></li>')
        if len(links) >= 24:
            break
    if links:
        block = (
            "<!-- SEO_HOME_WORK_LINKS -->\n"
            '<noscript class="seo-home-works"><div class="container">'
            "<h2>掲載作品</h2><ul>"
            + "".join(links)
            + "</ul></div></noscript>\n"
            "<!-- /SEO_HOME_WORK_LINKS -->"
        )
        if "<!-- SEO_HOME_WORK_LINKS -->" in text and "<!-- /SEO_HOME_WORK_LINKS -->" in text:
            text = re.sub(
                re.escape("<!-- SEO_HOME_WORK_LINKS -->")
                + r".*?"
                + re.escape("<!-- /SEO_HOME_WORK_LINKS -->"),
                block,
                text,
                count=1,
                flags=re.S,
            )
        else:
            text = text.replace("</main>", f"    {block}\n  </main>", 1)

    # Crawlable circle guide links on home
    circles = top_circles(works, CIRCLE_PAGE_LIMIT)
    if circles:
        cards = []
        for maker, n, ws in circles:
            thumbs = []
            for w in ws[:3]:
                src_img = w.get("image_thumb") or w.get("image") or ""
                if src_img:
                    thumbs.append(
                        f'<img src="{esc(src_img)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">'
                    )
            cards.append(
                f'<a class="circle-card" href="{esc(circle_href(maker))}">'
                f"<strong>{esc(maker)}</strong>"
                f"<span>{n}作品</span>"
                f'<div class="circle-thumbs">{"".join(thumbs)}</div>'
                f"</a>"
            )
        circle_block = (
            "<!-- SEO_HOME_CIRCLES -->\n"
            f'<div class="circle-grid" id="circle-grid">{"".join(cards)}</div>\n'
            "<!-- /SEO_HOME_CIRCLES -->"
        )
        if "<!-- SEO_HOME_CIRCLES -->" in text and "<!-- /SEO_HOME_CIRCLES -->" in text:
            text = re.sub(
                re.escape("<!-- SEO_HOME_CIRCLES -->")
                + r".*?"
                + re.escape("<!-- /SEO_HOME_CIRCLES -->"),
                circle_block,
                text,
                count=1,
                flags=re.S,
            )
        elif 'id="circle-grid"' in text:
            text = re.sub(
                r'<div class="circle-grid" id="circle-grid">.*?</div>',
                f'<div class="circle-grid" id="circle-grid">{"".join(cards)}</div>',
                text,
                count=1,
                flags=re.S,
            )

    return text


# Filled in main() before patch_main_pages
_INDEX_WORKS_CACHE: list[dict] = []


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


def sync_circle_dir(slugs: set[str]) -> None:
    CIRCLES_DIR.mkdir(parents=True, exist_ok=True)
    wanted = {f"{s}.html" for s in slugs}
    for existing in CIRCLES_DIR.glob("*.html"):
        if existing.name not in wanted:
            existing.unlink()


def main() -> int:
    if not DATA.exists():
        print(f"Missing {DATA}", file=sys.stderr)
        return 1
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    works = payload.get("works") or []
    hydrated = hydrate_descriptions_from_cache(works)
    if hydrated:
        print(f"[seo] hydrated {hydrated} descriptions from work cache")
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

    # Circle guide pages (top N by work count)
    CIRCLES_DIR.mkdir(parents=True, exist_ok=True)
    circle_slugs: list[str] = []
    circle_slug_set: set[str] = set()
    for maker, n, matched in top_circles(works, CIRCLE_PAGE_LIMIT):
        slug = circle_slug(maker)
        base = slug
        i = 2
        while slug in circle_slug_set:
            slug = f"{base}-{i}"
            i += 1
        circle_slug_set.add(slug)
        page = generate_circle_page(maker, n, matched, site_url, top_tags, updated_at, slug=slug)
        (CIRCLES_DIR / f"{slug}.html").write_text(page, encoding="utf-8")
        circle_slugs.append(slug)
    sync_circle_dir(circle_slug_set)

    write_robots(site_url)
    url_count = write_sitemap(site_url, works, tag_slugs, updated_at, circle_slugs)
    write_tag_cloud_js(top_tags)
    write_llms_txt(site_url)
    global _INDEX_WORKS_CACHE
    _INDEX_WORKS_CACHE = works
    patch_main_pages(site_url, top_tags, updated_at)

    print(
        f"SEO: {len(works)} work pages, {len(tag_slugs)} tag pages, "
        f"{len(circle_slugs)} circle pages, sitemap urls={url_count}, siteUrl={site_url}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
