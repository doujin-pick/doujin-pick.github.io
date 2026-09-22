#!/usr/bin/env python3
"""Generate X-ready promo post drafts from works.json into out/posts/YYYY-MM-DD.md"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "works.json"
CONFIG = ROOT / "js" / "config.js"
OUT_DIR = ROOT / "out" / "posts"
JST = timezone(timedelta(hours=9))


def load_config_affiliate_map() -> tuple[str, dict[str, str]]:
    """Best-effort parse of affiliateId and affiliateUrls from config.js"""
    text = CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else ""
    aff_id = ""
    m = re.search(r'affiliateId:\s*"([^"]*)"', text)
    if m:
        aff_id = m.group(1)
    urls: dict[str, str] = {}
    block = re.search(r"affiliateUrls:\s*\{([^}]*)\}", text, re.S)
    if block:
        for km in re.finditer(r'["\']?(RJ\d+)["\']?\s*:\s*["\'](https?://[^"\']+)["\']', block.group(1)):
            u = km.group(2)
            if "例" in u or "..." in u or "発行" in u:
                continue
            urls[km.group(1)] = u
    return aff_id, urls


def affiliate_url(work: dict, aff_map: dict[str, str]) -> str:
    """Mirror js/config.js affiliateUrl helper — no invented query params."""
    if (work.get("affiliate_url") or "").strip():
        return work["affiliate_url"].strip()
    wid = work.get("id") or ""
    if wid in aff_map:
        return aff_map[wid]
    return work.get("url") or "https://www.dlsite.com/maniax/"


def pick_works(works: list[dict], n: int = 5) -> list[dict]:
    # Prefer non-sample, mix sale + ranking + asmr
    scored = []
    for w in works:
        if w.get("sample"):
            continue
        score = 0
        if w.get("on_sale"):
            score += 3
        if "featured" in (w.get("sections") or []):
            score += 2
        if "ranking" in (w.get("sections") or []):
            score += 2
        if w.get("category") == "asmr":
            score += 1
        scored.append((score, w))
    scored.sort(key=lambda x: -x[0])
    picked = [w for _, w in scored[:n]]
    if len(picked) < n:
        for w in works:
            if w not in picked:
                picked.append(w)
            if len(picked) >= n:
                break
    return picked[:n]


def format_post(work: dict, link: str, idx: int) -> str:
    price = ""
    if work.get("price") is not None:
        price = f"{work['price']:,}円"
        if work.get("discount_percent"):
            price += f"（{work['discount_percent']}%OFF）"
    lines = [
        f"【同人ピック #{idx}】{work.get('title', '')}",
    ]
    if work.get("maker"):
        lines.append(f"Circle: {work['maker']}")
    if price:
        lines.append(f"💰 {price}")
    if work.get("on_sale"):
        lines.append("🔥 セール中")
    tags = " ".join(f"#{t.replace(' ', '')}" for t in (work.get("tags") or [])[:3] if t)
    if tags:
        lines.append(tags)
    lines += [
        "",
        "⚠️ 18歳未満閲覧禁止",
        "#DLsite #同人",
        link,
    ]
    return "\n".join(lines)


def main() -> int:
    if not DATA.exists():
        print("Missing data/works.json — run update_works.py first")
        return 1
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    works = payload.get("works") or []
    aff_id, aff_map = load_config_affiliate_map()
    today = datetime.now(JST).strftime("%Y-%m-%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    picks = pick_works(works, 5)

    parts = [
        f"# 同人ピック 投稿ドラフト — {today} (JST)",
        "",
        f"- works in catalog: {len(works)}",
        f"- affiliateId set: {'yes' if aff_id else 'no (using plain work URLs unless per-work dlaf.jp)'}",
        f"- affiliateUrls mapped: {len(aff_map)}",
        "",
        "各投稿を X にコピーして利用。リンクは作品ページURL（設定済みなら dlaf.jp）を使用。",
        "",
    ]
    for i, w in enumerate(picks, 1):
        link = affiliate_url(w, aff_map)
        parts.append(f"## Post {i}")
        parts.append("")
        parts.append("```")
        parts.append(format_post(w, link, i))
        parts.append("```")
        parts.append("")

    out_path = OUT_DIR / f"{today}.md"
    out_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {out_path} ({len(picks)} posts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
