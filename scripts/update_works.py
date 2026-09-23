#!/usr/bin/env python3
"""Refresh data/works.json from public DLsite ranking + work detail pages."""
from __future__ import annotations

import html as H
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "works.json"
CACHE = ROOT / "data" / "cache"
WORK_CACHE = CACHE / "works"
EMBED = ROOT / "js" / "embedded-works.js"
JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; DojinPickBot/1.0; +local; curation updater)"

# Cap unique works enriched with detail pages (runtime / politeness)
ENRICH_LIMIT = 6500
ENRICH_CAP = ENRICH_LIMIT  # alias
RANKING_PARSE_LIMIT = 100  # IDs per ranking/list page
SLEEP_MIN, SLEEP_MAX = 0.3, 0.6
CACHE_RESUME = True  # skip re-fetch if cache has parseable description
PARTIAL_SAVE_EVERY = 25
MAX_TAGS = 6

# Popularity-first: week/month/year/total + category hits, then day/sale/new.
# Verified public maniax/home ranking URLs (2026-09). Order = ingest priority.
SOURCES = [
    # === Historic famous / all-time hits (priority) ===
    ("https://www.dlsite.com/maniax/ranking/total", "ranking_total", ["featured", "ranking"], "ranking_total.html"),
    ("https://www.dlsite.com/maniax/ranking/year", "ranking_year", ["featured", "ranking"], "ranking_year.html"),
    ("https://www.dlsite.com/maniax/ranking/total/=/category/voice", "ranking_voice_total", ["featured", "genre_asmr"], "ranking_voice_total.html"),
    ("https://www.dlsite.com/maniax/ranking/year/=/category/voice", "ranking_voice_year", ["featured", "genre_asmr"], "ranking_voice_year.html"),
    ("https://www.dlsite.com/maniax/ranking/total/=/category/game", "ranking_game_total", ["featured", "genre_game"], "ranking_game_total.html"),
    ("https://www.dlsite.com/maniax/ranking/year/=/category/game", "ranking_game_year", ["featured", "genre_game"], "ranking_game_year.html"),
    ("https://www.dlsite.com/maniax/ranking/total/=/category/comic", "ranking_comic_total", ["genre_manga"], "ranking_comic_total.html"),
    ("https://www.dlsite.com/maniax/ranking/year/=/category/comic", "ranking_comic_year", ["genre_manga"], "ranking_comic_year.html"),
    ("https://www.dlsite.com/maniax/ranking/total/=/category/illust", "ranking_illust_total", ["genre_manga"], "ranking_illust_total.html"),
    ("https://www.dlsite.com/maniax/ranking/year/=/category/illust", "ranking_illust_year", ["genre_manga"], "ranking_illust_year.html"),
    # Bestsellers by download (all + category / work_type)
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100", "bestsellers_dl", ["featured", "ranking"], "bestsellers_dl.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100", "bestsellers_voice", ["featured", "genre_asmr"], "bestsellers_voice.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100", "bestsellers_game", ["featured", "genre_game"], "bestsellers_game.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100", "bestsellers_comic", ["genre_manga"], "bestsellers_comic.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100", "bestsellers_sou", ["featured", "genre_asmr"], "bestsellers_sou.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/50", "bestsellers_rpg", ["genre_game"], "bestsellers_rpg.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/50", "bestsellers_adv", ["genre_game"], "bestsellers_adv.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/50", "bestsellers_sim", ["genre_game"], "bestsellers_sim.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/50", "bestsellers_icg", ["genre_manga"], "bestsellers_icg.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/50", "bestsellers_mng", ["genre_manga"], "bestsellers_mng.html"),
    # All-ages / home floor all-time + year (iconic crossover hits)
    ("https://www.dlsite.com/home/ranking/total", "home_ranking_total", ["featured", "ranking"], "home_ranking_total.html"),
    ("https://www.dlsite.com/home/ranking/year", "home_ranking_year", ["featured", "ranking"], "home_ranking_year.html"),
    # === Recent attention + ranking tops ===
    ("https://www.dlsite.com/maniax/ranking/month", "ranking_month", ["featured", "ranking"], "ranking_month.html"),
    ("https://www.dlsite.com/maniax/ranking/week", "ranking_week", ["featured", "ranking"], "ranking_week.html"),
    ("https://www.dlsite.com/maniax/ranking/day", "ranking_day", ["featured", "ranking"], "ranking_day.html"),
    ("https://www.dlsite.com/maniax/ranking/month/=/category/voice", "ranking_voice_month", ["featured", "genre_asmr"], "ranking_voice_month.html"),
    ("https://www.dlsite.com/maniax/ranking/week/=/category/voice", "ranking_voice_week", ["genre_asmr"], "ranking_voice_week.html"),
    ("https://www.dlsite.com/maniax/ranking/day/=/category/voice", "ranking_voice_day", ["featured", "genre_asmr"], "ranking_voice_day.html"),
    ("https://www.dlsite.com/maniax/ranking/month/=/category/game", "ranking_game_month", ["genre_game"], "ranking_game_month.html"),
    ("https://www.dlsite.com/maniax/ranking/week/=/category/game", "ranking_game_week", ["genre_game"], "ranking_game_week.html"),
    ("https://www.dlsite.com/maniax/ranking/day/=/category/game", "ranking_game_day", ["genre_game"], "ranking_game_day.html"),
    ("https://www.dlsite.com/maniax/ranking/month/=/category/comic", "ranking_comic_month", ["genre_manga"], "ranking_comic_month.html"),
    ("https://www.dlsite.com/maniax/ranking/week/=/category/comic", "ranking_comic_week", ["genre_manga"], "ranking_comic_week.html"),
    ("https://www.dlsite.com/maniax/ranking/day/=/category/comic", "ranking_comic_day", ["genre_manga"], "ranking_comic_day.html"),
    # New + trending + sale
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100", "trend", ["featured"], "trend.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/50", "trend_voice", ["featured", "genre_asmr"], "trend_voice.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/50", "trend_game", ["genre_game"], "trend_game.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100", "sale_discount", ["sale"], "sale_discount.html"),
    ("https://www.dlsite.com/maniax/new", "maniax_new", ["featured"], "maniax_new.html"),
    ("https://www.dlsite.com/home/ranking/month", "home_ranking_month", ["featured"], "home_ranking_month.html"),
    ("https://www.dlsite.com/home/ranking/week", "home_ranking_week", ["featured"], "home_ranking_week.html"),
    ("https://www.dlsite.com/home/ranking/day", "home_ranking_day", ["featured"], "home_ranking_day.html"),
    # === Extra pages / releases to push unique catalog toward ENRICH_LIMIT ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/2", "bestsellers_dl_p2", ["featured", "ranking"], "bestsellers_dl_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/2", "bestsellers_voice_p2", ["featured", "genre_asmr"], "bestsellers_voice_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/2", "bestsellers_game_p2", ["featured", "genre_game"], "bestsellers_game_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/2", "bestsellers_comic_p2", ["genre_manga"], "bestsellers_comic_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/2", "bestsellers_sou_p2", ["featured", "genre_asmr"], "bestsellers_sou_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100", "bestsellers_rpg100", ["genre_game"], "bestsellers_rpg100.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100", "bestsellers_adv100", ["genre_game"], "bestsellers_adv100.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100", "bestsellers_sim100", ["genre_game"], "bestsellers_sim100.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100", "bestsellers_icg100", ["genre_manga"], "bestsellers_icg100.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100", "bestsellers_mng100", ["genre_manga"], "bestsellers_mng100.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100", "bestsellers_mov", ["featured"], "bestsellers_mov.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100", "release_new", ["featured"], "release_new.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100", "release_voice", ["featured", "genre_asmr"], "release_voice.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100", "release_game", ["genre_game"], "release_game.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100", "release_comic", ["genre_manga"], "release_comic.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/2", "trend_p2", ["featured"], "trend_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100", "trend_voice100", ["featured", "genre_asmr"], "trend_voice100.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100", "trend_game100", ["genre_game"], "trend_game100.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/2", "sale_discount_p2", ["sale"], "sale_discount_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/trend/per_page/100", "sale_trend", ["sale"], "sale_trend.html"),
    ("https://www.dlsite.com/maniax/ranking/month/=/category/illust", "ranking_illust_month", ["genre_manga"], "ranking_illust_month.html"),
    ("https://www.dlsite.com/maniax/ranking/week/=/category/illust", "ranking_illust_week", ["genre_manga"], "ranking_illust_week.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100", "home_bestsellers_dl", ["featured", "ranking"], "home_bestsellers_dl.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/2", "home_bestsellers_dl_p2", ["featured", "ranking"], "home_bestsellers_dl_p2.html"),
    ("https://www.dlsite.com/home/new", "home_new", ["featured"], "home_new.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/price_d/per_page/100", "price_desc", ["featured"], "price_desc.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/price_d/per_page/50", "price_voice", ["genre_asmr"], "price_voice.html"),

    # === Expansion toward ENRICH_LIMIT=5000 (page 3–5 + more splits) ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/3", "bestsellers_dl_p3", ["featured", "ranking"], "bestsellers_dl_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/3", "bestsellers_voice_p3", ["featured", "genre_asmr"], "bestsellers_voice_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/3", "bestsellers_game_p3", ["featured", "genre_game"], "bestsellers_game_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/3", "bestsellers_comic_p3", ["genre_manga"], "bestsellers_comic_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/3", "bestsellers_sou_p3", ["featured", "genre_asmr"], "bestsellers_sou_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/2", "bestsellers_rpg_p2", ["genre_game"], "bestsellers_rpg_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/2", "bestsellers_adv_p2", ["genre_game"], "bestsellers_adv_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/2", "bestsellers_sim_p2", ["genre_game"], "bestsellers_sim_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/2", "bestsellers_icg_p2", ["genre_manga"], "bestsellers_icg_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/2", "bestsellers_mng_p2", ["genre_manga"], "bestsellers_mng_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100/page/2", "bestsellers_mov_p2", ["featured"], "bestsellers_mov_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/2", "release_new_p2", ["featured"], "release_new_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/2", "release_voice_p2", ["featured", "genre_asmr"], "release_voice_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/2", "release_game_p2", ["genre_game"], "release_game_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100/page/2", "release_comic_p2", ["genre_manga"], "release_comic_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/3", "trend_p3", ["featured"], "trend_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/2", "trend_voice_p2", ["featured", "genre_asmr"], "trend_voice_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/2", "trend_game_p2", ["genre_game"], "trend_game_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/3", "sale_discount_p3", ["sale"], "sale_discount_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100", "sale_voice", ["sale", "genre_asmr"], "sale_voice.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100", "sale_game", ["sale", "genre_game"], "sale_game.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/comic/order/dl_d/per_page/100", "sale_comic", ["sale", "genre_manga"], "sale_comic.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/3", "home_bestsellers_dl_p3", ["featured", "ranking"], "home_bestsellers_dl_p3.html"),
    ("https://www.dlsite.com/home/fsr/=/order/trend/per_page/100", "home_trend", ["featured"], "home_trend.html"),
    ("https://www.dlsite.com/home/fsr/=/order/release_d/per_page/100", "home_release", ["featured"], "home_release.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_d/per_page/100", "price_sou100", ["genre_asmr"], "price_sou100.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_d/per_page/100", "price_game100", ["genre_game"], "price_game100.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/price_d/per_page/100", "price_mng100", ["genre_manga"], "price_mng100.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/price_d/per_page/100", "price_icg100", ["genre_manga"], "price_icg100.html"),
    ("https://www.dlsite.com/maniax/ranking/day/=/category/illust", "ranking_illust_day", ["genre_manga"], "ranking_illust_day.html"),
    # === Expansion toward ENRICH_LIMIT=5000 (page 4–5 + niche types) ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/4", "bestsellers_dl_p4", ["featured", "ranking"], "bestsellers_dl_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/5", "bestsellers_dl_p5", ["featured", "ranking"], "bestsellers_dl_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/4", "bestsellers_voice_p4", ["featured", "genre_asmr"], "bestsellers_voice_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/5", "bestsellers_voice_p5", ["featured", "genre_asmr"], "bestsellers_voice_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/4", "bestsellers_game_p4", ["featured", "genre_game"], "bestsellers_game_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/5", "bestsellers_game_p5", ["featured", "genre_game"], "bestsellers_game_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/4", "bestsellers_comic_p4", ["genre_manga"], "bestsellers_comic_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/5", "bestsellers_comic_p5", ["genre_manga"], "bestsellers_comic_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/4", "bestsellers_sou_p4", ["featured", "genre_asmr"], "bestsellers_sou_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/5", "bestsellers_sou_p5", ["featured", "genre_asmr"], "bestsellers_sou_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/3", "bestsellers_rpg_p3", ["genre_game"], "bestsellers_rpg_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/3", "bestsellers_adv_p3", ["genre_game"], "bestsellers_adv_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/3", "bestsellers_sim_p3", ["genre_game"], "bestsellers_sim_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/3", "bestsellers_icg_p3", ["genre_manga"], "bestsellers_icg_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/3", "bestsellers_mng_p3", ["genre_manga"], "bestsellers_mng_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100/page/3", "bestsellers_mov_p3", ["featured"], "bestsellers_mov_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TOOL/order/dl_d/per_page/100", "bestsellers_tool", ["genre_game"], "bestsellers_tool.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100", "bestsellers_mus", ["featured", "genre_asmr"], "bestsellers_mus.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100", "bestsellers_voice_type", ["featured", "genre_asmr"], "bestsellers_voice_type.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/3", "release_new_p3", ["featured"], "release_new_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/4", "release_new_p4", ["featured"], "release_new_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/3", "release_voice_p3", ["featured", "genre_asmr"], "release_voice_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/3", "release_game_p3", ["genre_game"], "release_game_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100/page/3", "release_comic_p3", ["genre_manga"], "release_comic_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/4", "trend_p4", ["featured"], "trend_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/3", "trend_voice_p3", ["featured", "genre_asmr"], "trend_voice_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/3", "trend_game_p3", ["genre_game"], "trend_game_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/4", "sale_discount_p4", ["sale"], "sale_discount_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/2", "sale_voice_p2", ["sale", "genre_asmr"], "sale_voice_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/2", "sale_game_p2", ["sale", "genre_game"], "sale_game_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/comic/order/dl_d/per_page/100/page/2", "sale_comic_p2", ["sale", "genre_manga"], "sale_comic_p2.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/4", "home_bestsellers_dl_p4", ["featured", "ranking"], "home_bestsellers_dl_p4.html"),
    ("https://www.dlsite.com/home/fsr/=/order/trend/per_page/100/page/2", "home_trend_p2", ["featured"], "home_trend_p2.html"),
    ("https://www.dlsite.com/home/fsr/=/order/release_d/per_page/100/page/2", "home_release_p2", ["featured"], "home_release_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_d/per_page/100/page/2", "price_sou_p2", ["genre_asmr"], "price_sou_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_d/per_page/100/page/2", "price_game_p2", ["genre_game"], "price_game_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/price_d/per_page/100/page/2", "price_mng_p2", ["genre_manga"], "price_mng_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/price_d/per_page/100/page/2", "price_icg_p2", ["genre_manga"], "price_icg_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100", "bestsellers_act", ["genre_game"], "bestsellers_act.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100", "bestsellers_sln", ["genre_game"], "bestsellers_sln.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TBL/order/dl_d/per_page/100", "bestsellers_tbl", ["genre_game"], "bestsellers_tbl.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/price_a/per_page/100", "price_asc_voice", ["genre_asmr"], "price_asc_voice.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_a/per_page/100", "price_asc_game", ["genre_game"], "price_asc_game.html"),

    # === Expansion toward ENRICH_LIMIT=5000 (page 6–8 + more niches) ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/6", "bestsellers_dl_p6", ["featured", "ranking"], "bestsellers_dl_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/7", "bestsellers_dl_p7", ["featured", "ranking"], "bestsellers_dl_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/8", "bestsellers_dl_p8", ["featured", "ranking"], "bestsellers_dl_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/6", "bestsellers_voice_p6", ["featured", "genre_asmr"], "bestsellers_voice_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/7", "bestsellers_voice_p7", ["featured", "genre_asmr"], "bestsellers_voice_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/8", "bestsellers_voice_p8", ["featured", "genre_asmr"], "bestsellers_voice_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/6", "bestsellers_game_p6", ["featured", "genre_game"], "bestsellers_game_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/7", "bestsellers_game_p7", ["featured", "genre_game"], "bestsellers_game_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/8", "bestsellers_game_p8", ["featured", "genre_game"], "bestsellers_game_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/6", "bestsellers_comic_p6", ["genre_manga"], "bestsellers_comic_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/7", "bestsellers_comic_p7", ["genre_manga"], "bestsellers_comic_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/6", "bestsellers_sou_p6", ["featured", "genre_asmr"], "bestsellers_sou_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/7", "bestsellers_sou_p7", ["featured", "genre_asmr"], "bestsellers_sou_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/8", "bestsellers_sou_p8", ["featured", "genre_asmr"], "bestsellers_sou_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/4", "bestsellers_rpg_p4", ["genre_game"], "bestsellers_rpg_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/5", "bestsellers_rpg_p5", ["genre_game"], "bestsellers_rpg_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/4", "bestsellers_adv_p4", ["genre_game"], "bestsellers_adv_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/5", "bestsellers_adv_p5", ["genre_game"], "bestsellers_adv_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/4", "bestsellers_sim_p4", ["genre_game"], "bestsellers_sim_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/4", "bestsellers_icg_p4", ["genre_manga"], "bestsellers_icg_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/5", "bestsellers_icg_p5", ["genre_manga"], "bestsellers_icg_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/4", "bestsellers_mng_p4", ["genre_manga"], "bestsellers_mng_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/5", "bestsellers_mng_p5", ["genre_manga"], "bestsellers_mng_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100/page/4", "bestsellers_mov_p4", ["featured"], "bestsellers_mov_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/2", "bestsellers_act_p2", ["genre_game"], "bestsellers_act_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/2", "bestsellers_sln_p2", ["genre_game"], "bestsellers_sln_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TBL/order/dl_d/per_page/100/page/2", "bestsellers_tbl_p2", ["genre_game"], "bestsellers_tbl_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TOOL/order/dl_d/per_page/100/page/2", "bestsellers_tool_p2", ["genre_game"], "bestsellers_tool_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/2", "bestsellers_mus_p2", ["featured", "genre_asmr"], "bestsellers_mus_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/2", "bestsellers_voice_type_p2", ["featured", "genre_asmr"], "bestsellers_voice_type_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/5", "release_new_p5", ["featured"], "release_new_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/6", "release_new_p6", ["featured"], "release_new_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/4", "release_voice_p4", ["featured", "genre_asmr"], "release_voice_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/5", "release_voice_p5", ["featured", "genre_asmr"], "release_voice_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/4", "release_game_p4", ["genre_game"], "release_game_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/5", "release_game_p5", ["genre_game"], "release_game_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100/page/4", "release_comic_p4", ["genre_manga"], "release_comic_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/5", "trend_p5", ["featured"], "trend_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/6", "trend_p6", ["featured"], "trend_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/4", "trend_voice_p4", ["featured", "genre_asmr"], "trend_voice_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/4", "trend_game_p4", ["genre_game"], "trend_game_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/5", "sale_discount_p5", ["sale"], "sale_discount_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/6", "sale_discount_p6", ["sale"], "sale_discount_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/3", "sale_voice_p3", ["sale", "genre_asmr"], "sale_voice_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/3", "sale_game_p3", ["sale", "genre_game"], "sale_game_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/comic/order/dl_d/per_page/100/page/3", "sale_comic_p3", ["sale", "genre_manga"], "sale_comic_p3.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/5", "home_bestsellers_dl_p5", ["featured", "ranking"], "home_bestsellers_dl_p5.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/6", "home_bestsellers_dl_p6", ["featured", "ranking"], "home_bestsellers_dl_p6.html"),
    ("https://www.dlsite.com/home/fsr/=/order/trend/per_page/100/page/3", "home_trend_p3", ["featured"], "home_trend_p3.html"),
    ("https://www.dlsite.com/home/fsr/=/order/release_d/per_page/100/page/3", "home_release_p3", ["featured"], "home_release_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_d/per_page/100/page/3", "price_sou_p3", ["genre_asmr"], "price_sou_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_d/per_page/100/page/3", "price_game_p3", ["genre_game"], "price_game_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/price_d/per_page/100/page/3", "price_mng_p3", ["genre_manga"], "price_mng_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/price_d/per_page/100/page/3", "price_icg_p3", ["genre_manga"], "price_icg_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/price_a/per_page/100/page/2", "price_asc_voice_p2", ["genre_asmr"], "price_asc_voice_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_a/per_page/100/page/2", "price_asc_game_p2", ["genre_game"], "price_asc_game_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100", "review_sou", ["featured", "genre_asmr"], "review_sou.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/review_d/per_page/100", "review_game", ["genre_game"], "review_game.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/review_d/per_page/100", "review_comic", ["genre_manga"], "review_comic.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/2", "review_sou_p2", ["featured", "genre_asmr"], "review_sou_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/review_d/per_page/100/page/2", "review_game_p2", ["genre_game"], "review_game_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/9", "bestsellers_dl_p9", ["featured", "ranking"], "bestsellers_dl_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/10", "bestsellers_dl_p10", ["featured", "ranking"], "bestsellers_dl_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/9", "bestsellers_voice_p9", ["featured", "genre_asmr"], "bestsellers_voice_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/9", "bestsellers_game_p9", ["featured", "genre_game"], "bestsellers_game_p9.html"),
    ("https://www.dlsite.com/books/ranking/total", "books_ranking_total", ["genre_manga"], "books_ranking_total.html"),
    ("https://www.dlsite.com/books/ranking/year", "books_ranking_year", ["genre_manga"], "books_ranking_year.html"),
    ("https://www.dlsite.com/books/ranking/month", "books_ranking_month", ["genre_manga"], "books_ranking_month.html"),
    ("https://www.dlsite.com/pro/ranking/total", "pro_ranking_total", ["featured", "genre_game"], "pro_ranking_total.html"),
    ("https://www.dlsite.com/pro/ranking/year", "pro_ranking_year", ["featured", "genre_game"], "pro_ranking_year.html"),
    ("https://www.dlsite.com/pro/ranking/month", "pro_ranking_month", ["genre_game"], "pro_ranking_month.html"),
    ("https://www.dlsite.com/girls/ranking/total", "girls_ranking_total", ["featured"], "girls_ranking_total.html"),
    ("https://www.dlsite.com/girls/ranking/year", "girls_ranking_year", ["featured"], "girls_ranking_year.html"),
    ("https://www.dlsite.com/bl/ranking/total", "bl_ranking_total", ["featured"], "bl_ranking_total.html"),
    ("https://www.dlsite.com/bl/ranking/year", "bl_ranking_year", ["featured"], "bl_ranking_year.html"),

    # === Expansion toward ENRICH_LIMIT=5000 (page 11–15 + deeper niches) ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/11", "bestsellers_dl_p11", ["featured", "ranking"], "bestsellers_dl_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/12", "bestsellers_dl_p12", ["featured", "ranking"], "bestsellers_dl_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/13", "bestsellers_dl_p13", ["featured", "ranking"], "bestsellers_dl_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/14", "bestsellers_dl_p14", ["featured", "ranking"], "bestsellers_dl_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/15", "bestsellers_dl_p15", ["featured", "ranking"], "bestsellers_dl_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/10", "bestsellers_voice_p10", ["featured", "genre_asmr"], "bestsellers_voice_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/11", "bestsellers_voice_p11", ["featured", "genre_asmr"], "bestsellers_voice_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/12", "bestsellers_voice_p12", ["featured", "genre_asmr"], "bestsellers_voice_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/13", "bestsellers_voice_p13", ["featured", "genre_asmr"], "bestsellers_voice_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/10", "bestsellers_game_p10", ["featured", "genre_game"], "bestsellers_game_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/11", "bestsellers_game_p11", ["featured", "genre_game"], "bestsellers_game_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/12", "bestsellers_game_p12", ["featured", "genre_game"], "bestsellers_game_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/13", "bestsellers_game_p13", ["featured", "genre_game"], "bestsellers_game_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/9", "bestsellers_sou_p9", ["featured", "genre_asmr"], "bestsellers_sou_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/10", "bestsellers_sou_p10", ["featured", "genre_asmr"], "bestsellers_sou_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/11", "bestsellers_sou_p11", ["featured", "genre_asmr"], "bestsellers_sou_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/12", "bestsellers_sou_p12", ["featured", "genre_asmr"], "bestsellers_sou_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/8", "bestsellers_comic_p8", ["genre_manga"], "bestsellers_comic_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/9", "bestsellers_comic_p9", ["genre_manga"], "bestsellers_comic_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/10", "bestsellers_comic_p10", ["genre_manga"], "bestsellers_comic_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/6", "bestsellers_rpg_p6", ["genre_game"], "bestsellers_rpg_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/7", "bestsellers_rpg_p7", ["genre_game"], "bestsellers_rpg_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/6", "bestsellers_adv_p6", ["genre_game"], "bestsellers_adv_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/7", "bestsellers_adv_p7", ["genre_game"], "bestsellers_adv_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/5", "bestsellers_sim_p5", ["genre_game"], "bestsellers_sim_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/6", "bestsellers_sim_p6", ["genre_game"], "bestsellers_sim_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/6", "bestsellers_icg_p6", ["genre_manga"], "bestsellers_icg_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/6", "bestsellers_mng_p6", ["genre_manga"], "bestsellers_mng_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/3", "bestsellers_act_p3", ["genre_game"], "bestsellers_act_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/3", "bestsellers_sln_p3", ["genre_game"], "bestsellers_sln_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100/page/5", "bestsellers_mov_p5", ["featured"], "bestsellers_mov_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/3", "bestsellers_mus_p3", ["featured", "genre_asmr"], "bestsellers_mus_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/3", "bestsellers_voice_type_p3", ["featured", "genre_asmr"], "bestsellers_voice_type_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/7", "release_new_p7", ["featured"], "release_new_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/8", "release_new_p8", ["featured"], "release_new_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/6", "release_voice_p6", ["featured", "genre_asmr"], "release_voice_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/7", "release_voice_p7", ["featured", "genre_asmr"], "release_voice_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/6", "release_game_p6", ["genre_game"], "release_game_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/7", "release_game_p7", ["genre_game"], "release_game_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100/page/5", "release_comic_p5", ["genre_manga"], "release_comic_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/7", "trend_p7", ["featured"], "trend_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/8", "trend_p8", ["featured"], "trend_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/5", "trend_voice_p5", ["featured", "genre_asmr"], "trend_voice_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/5", "trend_game_p5", ["genre_game"], "trend_game_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/7", "sale_discount_p7", ["sale"], "sale_discount_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/8", "sale_discount_p8", ["sale"], "sale_discount_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/4", "sale_voice_p4", ["sale", "genre_asmr"], "sale_voice_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/4", "sale_game_p4", ["sale", "genre_game"], "sale_game_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/3", "review_sou_p3", ["featured", "genre_asmr"], "review_sou_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/4", "review_sou_p4", ["featured", "genre_asmr"], "review_sou_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/review_d/per_page/100/page/3", "review_game_p3", ["genre_game"], "review_game_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/review_d/per_page/100/page/2", "review_comic_p2", ["genre_manga"], "review_comic_p2.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/7", "home_bestsellers_dl_p7", ["featured", "ranking"], "home_bestsellers_dl_p7.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/8", "home_bestsellers_dl_p8", ["featured", "ranking"], "home_bestsellers_dl_p8.html"),
    ("https://www.dlsite.com/home/fsr/=/order/trend/per_page/100/page/4", "home_trend_p4", ["featured"], "home_trend_p4.html"),
    ("https://www.dlsite.com/home/fsr/=/order/release_d/per_page/100/page/4", "home_release_p4", ["featured"], "home_release_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_d/per_page/100/page/4", "price_sou_p4", ["genre_asmr"], "price_sou_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_d/per_page/100/page/4", "price_game_p4", ["genre_game"], "price_game_p4.html"),
    ("https://www.dlsite.com/books/ranking/week", "books_ranking_week", ["genre_manga"], "books_ranking_week.html"),
    ("https://www.dlsite.com/books/ranking/day", "books_ranking_day", ["genre_manga"], "books_ranking_day.html"),
    ("https://www.dlsite.com/pro/ranking/week", "pro_ranking_week", ["genre_game"], "pro_ranking_week.html"),
    ("https://www.dlsite.com/pro/ranking/day", "pro_ranking_day", ["genre_game"], "pro_ranking_day.html"),
    ("https://www.dlsite.com/girls/ranking/month", "girls_ranking_month", ["featured"], "girls_ranking_month.html"),
    ("https://www.dlsite.com/bl/ranking/month", "bl_ranking_month", ["featured"], "bl_ranking_month.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_a/per_page/100", "price_asc_sou", ["genre_asmr"], "price_asc_sou.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/review_d/per_page/100", "review_rpg", ["genre_game"], "review_rpg.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/review_d/per_page/100", "review_adv", ["genre_game"], "review_adv.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/review_d/per_page/100", "review_icg", ["genre_manga"], "review_icg.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/review_d/per_page/100", "review_mng", ["genre_manga"], "review_mng.html"),

    # === Expansion toward ENRICH_LIMIT=5000 (page 16–20 + deeper ASMR/game/manga) ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/16", "bestsellers_dl_p16", ["featured", "ranking"], "bestsellers_dl_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/17", "bestsellers_dl_p17", ["featured", "ranking"], "bestsellers_dl_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/18", "bestsellers_dl_p18", ["featured", "ranking"], "bestsellers_dl_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/19", "bestsellers_dl_p19", ["featured", "ranking"], "bestsellers_dl_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/20", "bestsellers_dl_p20", ["featured", "ranking"], "bestsellers_dl_p20.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/14", "bestsellers_voice_p14", ["featured", "genre_asmr"], "bestsellers_voice_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/15", "bestsellers_voice_p15", ["featured", "genre_asmr"], "bestsellers_voice_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/16", "bestsellers_voice_p16", ["featured", "genre_asmr"], "bestsellers_voice_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/17", "bestsellers_voice_p17", ["featured", "genre_asmr"], "bestsellers_voice_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/14", "bestsellers_game_p14", ["featured", "genre_game"], "bestsellers_game_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/15", "bestsellers_game_p15", ["featured", "genre_game"], "bestsellers_game_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/16", "bestsellers_game_p16", ["featured", "genre_game"], "bestsellers_game_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/17", "bestsellers_game_p17", ["featured", "genre_game"], "bestsellers_game_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/13", "bestsellers_sou_p13", ["featured", "genre_asmr"], "bestsellers_sou_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/14", "bestsellers_sou_p14", ["featured", "genre_asmr"], "bestsellers_sou_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/15", "bestsellers_sou_p15", ["featured", "genre_asmr"], "bestsellers_sou_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/16", "bestsellers_sou_p16", ["featured", "genre_asmr"], "bestsellers_sou_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/11", "bestsellers_comic_p11", ["genre_manga"], "bestsellers_comic_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/12", "bestsellers_comic_p12", ["genre_manga"], "bestsellers_comic_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/8", "bestsellers_rpg_p8", ["genre_game"], "bestsellers_rpg_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/9", "bestsellers_rpg_p9", ["genre_game"], "bestsellers_rpg_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/8", "bestsellers_adv_p8", ["genre_game"], "bestsellers_adv_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/9", "bestsellers_adv_p9", ["genre_game"], "bestsellers_adv_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/7", "bestsellers_sim_p7", ["genre_game"], "bestsellers_sim_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/8", "bestsellers_sim_p8", ["genre_game"], "bestsellers_sim_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/7", "bestsellers_icg_p7", ["genre_manga"], "bestsellers_icg_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/7", "bestsellers_mng_p7", ["genre_manga"], "bestsellers_mng_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/4", "bestsellers_act_p4", ["genre_game"], "bestsellers_act_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/4", "bestsellers_sln_p4", ["genre_game"], "bestsellers_sln_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100/page/6", "bestsellers_mov_p6", ["featured"], "bestsellers_mov_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/4", "bestsellers_mus_p4", ["featured", "genre_asmr"], "bestsellers_mus_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/4", "bestsellers_voice_type_p4", ["featured", "genre_asmr"], "bestsellers_voice_type_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/9", "release_new_p9", ["featured"], "release_new_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/10", "release_new_p10", ["featured"], "release_new_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/8", "release_voice_p8", ["featured", "genre_asmr"], "release_voice_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/9", "release_voice_p9", ["featured", "genre_asmr"], "release_voice_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/8", "release_game_p8", ["genre_game"], "release_game_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/9", "release_game_p9", ["genre_game"], "release_game_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100/page/6", "release_comic_p6", ["genre_manga"], "release_comic_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/9", "trend_p9", ["featured"], "trend_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/10", "trend_p10", ["featured"], "trend_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/6", "trend_voice_p6", ["featured", "genre_asmr"], "trend_voice_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/6", "trend_game_p6", ["genre_game"], "trend_game_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/9", "sale_discount_p9", ["sale"], "sale_discount_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/10", "sale_discount_p10", ["sale"], "sale_discount_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/5", "sale_voice_p5", ["sale", "genre_asmr"], "sale_voice_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/5", "sale_game_p5", ["sale", "genre_game"], "sale_game_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/5", "review_sou_p5", ["featured", "genre_asmr"], "review_sou_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/6", "review_sou_p6", ["featured", "genre_asmr"], "review_sou_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/review_d/per_page/100/page/4", "review_game_p4", ["genre_game"], "review_game_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/review_d/per_page/100/page/3", "review_comic_p3", ["genre_manga"], "review_comic_p3.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/9", "home_bestsellers_dl_p9", ["featured", "ranking"], "home_bestsellers_dl_p9.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/10", "home_bestsellers_dl_p10", ["featured", "ranking"], "home_bestsellers_dl_p10.html"),
    ("https://www.dlsite.com/home/fsr/=/order/trend/per_page/100/page/5", "home_trend_p5", ["featured"], "home_trend_p5.html"),
    ("https://www.dlsite.com/home/fsr/=/order/release_d/per_page/100/page/5", "home_release_p5", ["featured"], "home_release_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_d/per_page/100/page/5", "price_sou_p5", ["genre_asmr"], "price_sou_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_d/per_page/100/page/5", "price_game_p5", ["genre_game"], "price_game_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/review_d/per_page/100/page/2", "review_rpg_p2", ["genre_game"], "review_rpg_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/review_d/per_page/100/page/2", "review_adv_p2", ["genre_game"], "review_adv_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/review_d/per_page/100/page/2", "review_icg_p2", ["genre_manga"], "review_icg_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/review_d/per_page/100/page/2", "review_mng_p2", ["genre_manga"], "review_mng_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_a/per_page/100/page/2", "price_asc_sou_p2", ["genre_asmr"], "price_asc_sou_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/price_a/per_page/100/page/2", "price_asc_voice_p2", ["genre_asmr"], "price_asc_voice_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_a/per_page/100/page/2", "price_asc_game_p2", ["genre_game"], "price_asc_game_p2.html"),
    ("https://www.dlsite.com/girls/ranking/week", "girls_ranking_week", ["featured"], "girls_ranking_week.html"),
    ("https://www.dlsite.com/bl/ranking/week", "bl_ranking_week", ["featured"], "bl_ranking_week.html"),
    ("https://www.dlsite.com/books/fsr/=/order/dl_d/per_page/100", "books_bestsellers_dl", ["genre_manga"], "books_bestsellers_dl.html"),
    ("https://www.dlsite.com/pro/fsr/=/order/dl_d/per_page/100", "pro_bestsellers_dl", ["featured", "genre_game"], "pro_bestsellers_dl.html"),
    # === Expansion toward ENRICH_LIMIT=5000 (page 21–25 + deeper ASMR/game/manga) ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/21", "bestsellers_dl_p21", ["featured", "ranking"], "bestsellers_dl_p21.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/22", "bestsellers_dl_p22", ["featured", "ranking"], "bestsellers_dl_p22.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/23", "bestsellers_dl_p23", ["featured", "ranking"], "bestsellers_dl_p23.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/24", "bestsellers_dl_p24", ["featured", "ranking"], "bestsellers_dl_p24.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/25", "bestsellers_dl_p25", ["featured", "ranking"], "bestsellers_dl_p25.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/18", "bestsellers_voice_p18", ["featured", "genre_asmr"], "bestsellers_voice_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/19", "bestsellers_voice_p19", ["featured", "genre_asmr"], "bestsellers_voice_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/20", "bestsellers_voice_p20", ["featured", "genre_asmr"], "bestsellers_voice_p20.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/21", "bestsellers_voice_p21", ["featured", "genre_asmr"], "bestsellers_voice_p21.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/18", "bestsellers_game_p18", ["featured", "genre_game"], "bestsellers_game_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/19", "bestsellers_game_p19", ["featured", "genre_game"], "bestsellers_game_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/20", "bestsellers_game_p20", ["featured", "genre_game"], "bestsellers_game_p20.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/21", "bestsellers_game_p21", ["featured", "genre_game"], "bestsellers_game_p21.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/17", "bestsellers_sou_p17", ["featured", "genre_asmr"], "bestsellers_sou_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/18", "bestsellers_sou_p18", ["featured", "genre_asmr"], "bestsellers_sou_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/19", "bestsellers_sou_p19", ["featured", "genre_asmr"], "bestsellers_sou_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/20", "bestsellers_sou_p20", ["featured", "genre_asmr"], "bestsellers_sou_p20.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/13", "bestsellers_comic_p13", ["genre_manga"], "bestsellers_comic_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/14", "bestsellers_comic_p14", ["genre_manga"], "bestsellers_comic_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/10", "bestsellers_rpg_p10", ["genre_game"], "bestsellers_rpg_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/11", "bestsellers_rpg_p11", ["genre_game"], "bestsellers_rpg_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/10", "bestsellers_adv_p10", ["genre_game"], "bestsellers_adv_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/11", "bestsellers_adv_p11", ["genre_game"], "bestsellers_adv_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/9", "bestsellers_sim_p9", ["genre_game"], "bestsellers_sim_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/10", "bestsellers_sim_p10", ["genre_game"], "bestsellers_sim_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/8", "bestsellers_icg_p8", ["genre_manga"], "bestsellers_icg_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/8", "bestsellers_mng_p8", ["genre_manga"], "bestsellers_mng_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/5", "bestsellers_act_p5", ["genre_game"], "bestsellers_act_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/5", "bestsellers_sln_p5", ["genre_game"], "bestsellers_sln_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100/page/7", "bestsellers_mov_p7", ["featured"], "bestsellers_mov_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/5", "bestsellers_mus_p5", ["featured", "genre_asmr"], "bestsellers_mus_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/5", "bestsellers_voice_type_p5", ["featured", "genre_asmr"], "bestsellers_voice_type_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/11", "release_new_p11", ["featured"], "release_new_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/12", "release_new_p12", ["featured"], "release_new_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/10", "release_voice_p10", ["featured", "genre_asmr"], "release_voice_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/11", "release_voice_p11", ["featured", "genre_asmr"], "release_voice_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/10", "release_game_p10", ["genre_game"], "release_game_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/11", "release_game_p11", ["genre_game"], "release_game_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100/page/7", "release_comic_p7", ["genre_manga"], "release_comic_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/11", "trend_p11", ["featured"], "trend_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/12", "trend_p12", ["featured"], "trend_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/7", "trend_voice_p7", ["featured", "genre_asmr"], "trend_voice_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/7", "trend_game_p7", ["genre_game"], "trend_game_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/11", "sale_discount_p11", ["sale"], "sale_discount_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/12", "sale_discount_p12", ["sale"], "sale_discount_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/6", "sale_voice_p6", ["sale", "genre_asmr"], "sale_voice_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/6", "sale_game_p6", ["sale", "genre_game"], "sale_game_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/7", "review_sou_p7", ["featured", "genre_asmr"], "review_sou_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/8", "review_sou_p8", ["featured", "genre_asmr"], "review_sou_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/review_d/per_page/100/page/5", "review_game_p5", ["genre_game"], "review_game_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/review_d/per_page/100/page/4", "review_comic_p4", ["genre_manga"], "review_comic_p4.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/11", "home_bestsellers_dl_p11", ["featured", "ranking"], "home_bestsellers_dl_p11.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/12", "home_bestsellers_dl_p12", ["featured", "ranking"], "home_bestsellers_dl_p12.html"),
    ("https://www.dlsite.com/home/fsr/=/order/trend/per_page/100/page/6", "home_trend_p6", ["featured"], "home_trend_p6.html"),
    ("https://www.dlsite.com/home/fsr/=/order/release_d/per_page/100/page/6", "home_release_p6", ["featured"], "home_release_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_d/per_page/100/page/6", "price_sou_p6", ["genre_asmr"], "price_sou_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_d/per_page/100/page/6", "price_game_p6", ["genre_game"], "price_game_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/review_d/per_page/100/page/3", "review_rpg_p3", ["genre_game"], "review_rpg_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/review_d/per_page/100/page/3", "review_adv_p3", ["genre_game"], "review_adv_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/review_d/per_page/100/page/3", "review_icg_p3", ["genre_manga"], "review_icg_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/review_d/per_page/100/page/3", "review_mng_p3", ["genre_manga"], "review_mng_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_a/per_page/100/page/3", "price_asc_sou_p3", ["genre_asmr"], "price_asc_sou_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/price_a/per_page/100/page/3", "price_asc_voice_p3", ["genre_asmr"], "price_asc_voice_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_a/per_page/100/page/3", "price_asc_game_p3", ["genre_game"], "price_asc_game_p3.html"),
    ("https://www.dlsite.com/girls/ranking/day", "girls_ranking_day", ["featured"], "girls_ranking_day.html"),
    ("https://www.dlsite.com/bl/ranking/day", "bl_ranking_day", ["featured"], "bl_ranking_day.html"),
    ("https://www.dlsite.com/books/fsr/=/order/dl_d/per_page/100/page/2", "books_bestsellers_dl_p2", ["genre_manga"], "books_bestsellers_dl_p2.html"),
    ("https://www.dlsite.com/pro/fsr/=/order/dl_d/per_page/100/page/2", "pro_bestsellers_dl_p2", ["featured", "genre_game"], "pro_bestsellers_dl_p2.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TBL/order/dl_d/per_page/100/page/3", "bestsellers_tbl_p3", ["genre_game"], "bestsellers_tbl_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TOOL/order/dl_d/per_page/100/page/3", "bestsellers_tool_p3", ["genre_game"], "bestsellers_tool_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/8", "trend_voice_p8", ["featured", "genre_asmr"], "trend_voice_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/8", "trend_game_p8", ["genre_game"], "trend_game_p8.html"),

    # === Expansion toward ENRICH_LIMIT=5000 (page 26–30 + deeper ASMR/game/manga) ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/26", "bestsellers_dl_p26", ["featured", "ranking"], "bestsellers_dl_p26.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/27", "bestsellers_dl_p27", ["featured", "ranking"], "bestsellers_dl_p27.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/28", "bestsellers_dl_p28", ["featured", "ranking"], "bestsellers_dl_p28.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/29", "bestsellers_dl_p29", ["featured", "ranking"], "bestsellers_dl_p29.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/30", "bestsellers_dl_p30", ["featured", "ranking"], "bestsellers_dl_p30.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/22", "bestsellers_voice_p22", ["featured", "genre_asmr"], "bestsellers_voice_p22.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/23", "bestsellers_voice_p23", ["featured", "genre_asmr"], "bestsellers_voice_p23.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/24", "bestsellers_voice_p24", ["featured", "genre_asmr"], "bestsellers_voice_p24.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/25", "bestsellers_voice_p25", ["featured", "genre_asmr"], "bestsellers_voice_p25.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/22", "bestsellers_game_p22", ["featured", "genre_game"], "bestsellers_game_p22.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/23", "bestsellers_game_p23", ["featured", "genre_game"], "bestsellers_game_p23.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/24", "bestsellers_game_p24", ["featured", "genre_game"], "bestsellers_game_p24.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/25", "bestsellers_game_p25", ["featured", "genre_game"], "bestsellers_game_p25.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/21", "bestsellers_sou_p21", ["featured", "genre_asmr"], "bestsellers_sou_p21.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/22", "bestsellers_sou_p22", ["featured", "genre_asmr"], "bestsellers_sou_p22.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/23", "bestsellers_sou_p23", ["featured", "genre_asmr"], "bestsellers_sou_p23.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/24", "bestsellers_sou_p24", ["featured", "genre_asmr"], "bestsellers_sou_p24.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/15", "bestsellers_comic_p15", ["genre_manga"], "bestsellers_comic_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/16", "bestsellers_comic_p16", ["genre_manga"], "bestsellers_comic_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/12", "bestsellers_rpg_p12", ["genre_game"], "bestsellers_rpg_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/13", "bestsellers_rpg_p13", ["genre_game"], "bestsellers_rpg_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/12", "bestsellers_adv_p12", ["genre_game"], "bestsellers_adv_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/13", "bestsellers_adv_p13", ["genre_game"], "bestsellers_adv_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/11", "bestsellers_sim_p11", ["genre_game"], "bestsellers_sim_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/12", "bestsellers_sim_p12", ["genre_game"], "bestsellers_sim_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/9", "bestsellers_icg_p9", ["genre_manga"], "bestsellers_icg_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/9", "bestsellers_mng_p9", ["genre_manga"], "bestsellers_mng_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/6", "bestsellers_act_p6", ["genre_game"], "bestsellers_act_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/6", "bestsellers_sln_p6", ["genre_game"], "bestsellers_sln_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100/page/8", "bestsellers_mov_p8", ["featured"], "bestsellers_mov_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/6", "bestsellers_mus_p6", ["featured", "genre_asmr"], "bestsellers_mus_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/6", "bestsellers_voice_type_p6", ["featured", "genre_asmr"], "bestsellers_voice_type_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/13", "release_new_p13", ["featured"], "release_new_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/14", "release_new_p14", ["featured"], "release_new_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/12", "release_voice_p12", ["featured", "genre_asmr"], "release_voice_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/13", "release_voice_p13", ["featured", "genre_asmr"], "release_voice_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/12", "release_game_p12", ["genre_game"], "release_game_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/13", "release_game_p13", ["genre_game"], "release_game_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100/page/8", "release_comic_p8", ["genre_manga"], "release_comic_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/13", "trend_p13", ["featured"], "trend_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/14", "trend_p14", ["featured"], "trend_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/9", "trend_voice_p9", ["featured", "genre_asmr"], "trend_voice_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/9", "trend_game_p9", ["genre_game"], "trend_game_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/13", "sale_discount_p13", ["sale"], "sale_discount_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/14", "sale_discount_p14", ["sale"], "sale_discount_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/7", "sale_voice_p7", ["sale", "genre_asmr"], "sale_voice_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/7", "sale_game_p7", ["sale", "genre_game"], "sale_game_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/9", "review_sou_p9", ["featured", "genre_asmr"], "review_sou_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/10", "review_sou_p10", ["featured", "genre_asmr"], "review_sou_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/review_d/per_page/100/page/6", "review_game_p6", ["genre_game"], "review_game_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/review_d/per_page/100/page/5", "review_comic_p5", ["genre_manga"], "review_comic_p5.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/13", "home_bestsellers_dl_p13", ["featured", "ranking"], "home_bestsellers_dl_p13.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/14", "home_bestsellers_dl_p14", ["featured", "ranking"], "home_bestsellers_dl_p14.html"),
    ("https://www.dlsite.com/home/fsr/=/order/trend/per_page/100/page/7", "home_trend_p7", ["featured"], "home_trend_p7.html"),
    ("https://www.dlsite.com/home/fsr/=/order/release_d/per_page/100/page/7", "home_release_p7", ["featured"], "home_release_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_d/per_page/100/page/7", "price_sou_p7", ["genre_asmr"], "price_sou_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_d/per_page/100/page/7", "price_game_p7", ["genre_game"], "price_game_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/review_d/per_page/100/page/4", "review_rpg_p4", ["genre_game"], "review_rpg_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/review_d/per_page/100/page/4", "review_adv_p4", ["genre_game"], "review_adv_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/review_d/per_page/100/page/4", "review_icg_p4", ["genre_manga"], "review_icg_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/review_d/per_page/100/page/4", "review_mng_p4", ["genre_manga"], "review_mng_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_a/per_page/100/page/4", "price_asc_sou_p4", ["genre_asmr"], "price_asc_sou_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/price_a/per_page/100/page/4", "price_asc_voice_p4", ["genre_asmr"], "price_asc_voice_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_a/per_page/100/page/4", "price_asc_game_p4", ["genre_game"], "price_asc_game_p4.html"),
    ("https://www.dlsite.com/books/fsr/=/order/dl_d/per_page/100/page/3", "books_bestsellers_dl_p3", ["genre_manga"], "books_bestsellers_dl_p3.html"),
    ("https://www.dlsite.com/pro/fsr/=/order/dl_d/per_page/100/page/3", "pro_bestsellers_dl_p3", ["featured", "genre_game"], "pro_bestsellers_dl_p3.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TBL/order/dl_d/per_page/100/page/4", "bestsellers_tbl_p4", ["genre_game"], "bestsellers_tbl_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TOOL/order/dl_d/per_page/100/page/4", "bestsellers_tool_p4", ["genre_game"], "bestsellers_tool_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/10", "trend_voice_p10", ["featured", "genre_asmr"], "trend_voice_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/10", "trend_game_p10", ["genre_game"], "trend_game_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/7", "bestsellers_voice_type_p7", ["featured", "genre_asmr"], "bestsellers_voice_type_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/7", "bestsellers_mus_p7", ["featured", "genre_asmr"], "bestsellers_mus_p7.html"),
    ("https://www.dlsite.com/girls/fsr/=/order/dl_d/per_page/100", "girls_bestsellers_dl", ["featured"], "girls_bestsellers_dl.html"),
    ("https://www.dlsite.com/bl/fsr/=/order/dl_d/per_page/100", "bl_bestsellers_dl", ["featured"], "bl_bestsellers_dl.html"),

    # === Expansion toward ENRICH_LIMIT=5500 (page 31–35 + deeper ASMR/game/manga) ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/31", "bestsellers_dl_p31", ["featured", "ranking"], "bestsellers_dl_p31.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/32", "bestsellers_dl_p32", ["featured", "ranking"], "bestsellers_dl_p32.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/33", "bestsellers_dl_p33", ["featured", "ranking"], "bestsellers_dl_p33.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/34", "bestsellers_dl_p34", ["featured", "ranking"], "bestsellers_dl_p34.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/35", "bestsellers_dl_p35", ["featured", "ranking"], "bestsellers_dl_p35.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/26", "bestsellers_voice_p26", ["featured", "genre_asmr"], "bestsellers_voice_p26.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/27", "bestsellers_voice_p27", ["featured", "genre_asmr"], "bestsellers_voice_p27.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/28", "bestsellers_voice_p28", ["featured", "genre_asmr"], "bestsellers_voice_p28.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/29", "bestsellers_voice_p29", ["featured", "genre_asmr"], "bestsellers_voice_p29.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/30", "bestsellers_voice_p30", ["featured", "genre_asmr"], "bestsellers_voice_p30.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/26", "bestsellers_game_p26", ["featured", "genre_game"], "bestsellers_game_p26.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/27", "bestsellers_game_p27", ["featured", "genre_game"], "bestsellers_game_p27.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/28", "bestsellers_game_p28", ["featured", "genre_game"], "bestsellers_game_p28.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/29", "bestsellers_game_p29", ["featured", "genre_game"], "bestsellers_game_p29.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/30", "bestsellers_game_p30", ["featured", "genre_game"], "bestsellers_game_p30.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/25", "bestsellers_sou_p25", ["featured", "genre_asmr"], "bestsellers_sou_p25.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/26", "bestsellers_sou_p26", ["featured", "genre_asmr"], "bestsellers_sou_p26.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/27", "bestsellers_sou_p27", ["featured", "genre_asmr"], "bestsellers_sou_p27.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/28", "bestsellers_sou_p28", ["featured", "genre_asmr"], "bestsellers_sou_p28.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/29", "bestsellers_sou_p29", ["featured", "genre_asmr"], "bestsellers_sou_p29.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/17", "bestsellers_comic_p17", ["genre_manga"], "bestsellers_comic_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/18", "bestsellers_comic_p18", ["genre_manga"], "bestsellers_comic_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/19", "bestsellers_comic_p19", ["genre_manga"], "bestsellers_comic_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/14", "bestsellers_rpg_p14", ["genre_game"], "bestsellers_rpg_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/14", "bestsellers_adv_p14", ["genre_game"], "bestsellers_adv_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/15", "bestsellers_rpg_p15", ["genre_game"], "bestsellers_rpg_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/15", "bestsellers_adv_p15", ["genre_game"], "bestsellers_adv_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/13", "bestsellers_sim_p13", ["genre_game"], "bestsellers_sim_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/14", "bestsellers_sim_p14", ["genre_game"], "bestsellers_sim_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/10", "bestsellers_icg_p10", ["genre_manga"], "bestsellers_icg_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/10", "bestsellers_mng_p10", ["genre_manga"], "bestsellers_mng_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/11", "bestsellers_icg_p11", ["genre_manga"], "bestsellers_icg_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/11", "bestsellers_mng_p11", ["genre_manga"], "bestsellers_mng_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/7", "bestsellers_act_p7", ["genre_game"], "bestsellers_act_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/7", "bestsellers_sln_p7", ["genre_game"], "bestsellers_sln_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/8", "bestsellers_act_p8", ["genre_game"], "bestsellers_act_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/8", "bestsellers_sln_p8", ["genre_game"], "bestsellers_sln_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100/page/9", "bestsellers_mov_p9", ["featured"], "bestsellers_mov_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/8", "bestsellers_mus_p8", ["featured", "genre_asmr"], "bestsellers_mus_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/8", "bestsellers_voice_type_p8", ["featured", "genre_asmr"], "bestsellers_voice_type_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/15", "release_new_p15", ["featured"], "release_new_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/15", "trend_p15", ["featured"], "trend_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/15", "sale_discount_p15", ["sale"], "sale_discount_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/16", "release_new_p16", ["featured"], "release_new_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/16", "trend_p16", ["featured"], "trend_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/16", "sale_discount_p16", ["sale"], "sale_discount_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/14", "release_voice_p14", ["featured", "genre_asmr"], "release_voice_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/14", "release_game_p14", ["genre_game"], "release_game_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/15", "release_voice_p15", ["featured", "genre_asmr"], "release_voice_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/15", "release_game_p15", ["genre_game"], "release_game_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100/page/9", "release_comic_p9", ["genre_manga"], "release_comic_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/11", "trend_voice_p11", ["featured", "genre_asmr"], "trend_voice_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/11", "trend_game_p11", ["genre_game"], "trend_game_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/12", "trend_voice_p12", ["featured", "genre_asmr"], "trend_voice_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/12", "trend_game_p12", ["genre_game"], "trend_game_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/8", "sale_voice_p8", ["sale", "genre_asmr"], "sale_voice_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/8", "sale_game_p8", ["sale", "genre_game"], "sale_game_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/9", "sale_voice_p9", ["sale", "genre_asmr"], "sale_voice_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/9", "sale_game_p9", ["sale", "genre_game"], "sale_game_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/11", "review_sou_p11", ["featured", "genre_asmr"], "review_sou_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/12", "review_sou_p12", ["featured", "genre_asmr"], "review_sou_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/review_d/per_page/100/page/7", "review_game_p7", ["genre_game"], "review_game_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/review_d/per_page/100/page/6", "review_comic_p6", ["genre_manga"], "review_comic_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/review_d/per_page/100/page/5", "review_rpg_p5", ["genre_game"], "review_rpg_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/review_d/per_page/100/page/5", "review_adv_p5", ["genre_game"], "review_adv_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/review_d/per_page/100/page/5", "review_icg_p5", ["genre_manga"], "review_icg_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/review_d/per_page/100/page/5", "review_mng_p5", ["genre_manga"], "review_mng_p5.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/15", "home_bestsellers_dl_p15", ["featured", "ranking"], "home_bestsellers_dl_p15.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/16", "home_bestsellers_dl_p16", ["featured", "ranking"], "home_bestsellers_dl_p16.html"),
    ("https://www.dlsite.com/home/fsr/=/order/trend/per_page/100/page/8", "home_trend_p8", ["featured"], "home_trend_p8.html"),
    ("https://www.dlsite.com/home/fsr/=/order/release_d/per_page/100/page/8", "home_release_p8", ["featured"], "home_release_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_d/per_page/100/page/8", "price_sou_p8", ["genre_asmr"], "price_sou_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_d/per_page/100/page/8", "price_game_p8", ["genre_game"], "price_game_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_a/per_page/100/page/5", "price_asc_sou_p5", ["genre_asmr"], "price_asc_sou_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/price_a/per_page/100/page/5", "price_asc_voice_p5", ["genre_asmr"], "price_asc_voice_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_a/per_page/100/page/5", "price_asc_game_p5", ["genre_game"], "price_asc_game_p5.html"),
    ("https://www.dlsite.com/books/fsr/=/order/dl_d/per_page/100/page/4", "books_bestsellers_dl_p4", ["genre_manga"], "books_bestsellers_dl_p4.html"),
    ("https://www.dlsite.com/pro/fsr/=/order/dl_d/per_page/100/page/4", "pro_bestsellers_dl_p4", ["featured", "genre_game"], "pro_bestsellers_dl_p4.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TBL/order/dl_d/per_page/100/page/5", "bestsellers_tbl_p5", ["genre_game"], "bestsellers_tbl_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TOOL/order/dl_d/per_page/100/page/5", "bestsellers_tool_p5", ["genre_game"], "bestsellers_tool_p5.html"),
    ("https://www.dlsite.com/girls/fsr/=/order/dl_d/per_page/100/page/2", "girls_bestsellers_dl_p2", ["featured"], "girls_bestsellers_dl_p2.html"),
    ("https://www.dlsite.com/bl/fsr/=/order/dl_d/per_page/100/page/2", "bl_bestsellers_dl_p2", ["featured"], "bl_bestsellers_dl_p2.html"),
    ("https://www.dlsite.com/girls/ranking/month", "girls_ranking_month", ["featured"], "girls_ranking_month.html"),
    ("https://www.dlsite.com/bl/ranking/month", "bl_ranking_month", ["featured"], "bl_ranking_month.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/9", "bestsellers_voice_type_p9", ["featured", "genre_asmr"], "bestsellers_voice_type_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/9", "bestsellers_mus_p9", ["featured", "genre_asmr"], "bestsellers_mus_p9.html"),
    # === Expansion toward ENRICH_LIMIT=6000 (page 36–40 + deeper ASMR/game/manga) ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/36", "bestsellers_dl_p36", ["featured", "ranking"], "bestsellers_dl_p36.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/37", "bestsellers_dl_p37", ["featured", "ranking"], "bestsellers_dl_p37.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/38", "bestsellers_dl_p38", ["featured", "ranking"], "bestsellers_dl_p38.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/39", "bestsellers_dl_p39", ["featured", "ranking"], "bestsellers_dl_p39.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/40", "bestsellers_dl_p40", ["featured", "ranking"], "bestsellers_dl_p40.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/31", "bestsellers_voice_p31", ["featured", "genre_asmr"], "bestsellers_voice_p31.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/32", "bestsellers_voice_p32", ["featured", "genre_asmr"], "bestsellers_voice_p32.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/33", "bestsellers_voice_p33", ["featured", "genre_asmr"], "bestsellers_voice_p33.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/34", "bestsellers_voice_p34", ["featured", "genre_asmr"], "bestsellers_voice_p34.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/35", "bestsellers_voice_p35", ["featured", "genre_asmr"], "bestsellers_voice_p35.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/31", "bestsellers_game_p31", ["featured", "genre_game"], "bestsellers_game_p31.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/32", "bestsellers_game_p32", ["featured", "genre_game"], "bestsellers_game_p32.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/33", "bestsellers_game_p33", ["featured", "genre_game"], "bestsellers_game_p33.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/34", "bestsellers_game_p34", ["featured", "genre_game"], "bestsellers_game_p34.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/35", "bestsellers_game_p35", ["featured", "genre_game"], "bestsellers_game_p35.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/30", "bestsellers_sou_p30", ["featured", "genre_asmr"], "bestsellers_sou_p30.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/31", "bestsellers_sou_p31", ["featured", "genre_asmr"], "bestsellers_sou_p31.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/32", "bestsellers_sou_p32", ["featured", "genre_asmr"], "bestsellers_sou_p32.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/33", "bestsellers_sou_p33", ["featured", "genre_asmr"], "bestsellers_sou_p33.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/34", "bestsellers_sou_p34", ["featured", "genre_asmr"], "bestsellers_sou_p34.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/20", "bestsellers_comic_p20", ["genre_manga"], "bestsellers_comic_p20.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/21", "bestsellers_comic_p21", ["genre_manga"], "bestsellers_comic_p21.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/22", "bestsellers_comic_p22", ["genre_manga"], "bestsellers_comic_p22.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/16", "bestsellers_rpg_p16", ["genre_game"], "bestsellers_rpg_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/16", "bestsellers_adv_p16", ["genre_game"], "bestsellers_adv_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/17", "bestsellers_rpg_p17", ["genre_game"], "bestsellers_rpg_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/17", "bestsellers_adv_p17", ["genre_game"], "bestsellers_adv_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/15", "bestsellers_sim_p15", ["genre_game"], "bestsellers_sim_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/16", "bestsellers_sim_p16", ["genre_game"], "bestsellers_sim_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/12", "bestsellers_icg_p12", ["genre_manga"], "bestsellers_icg_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/12", "bestsellers_mng_p12", ["genre_manga"], "bestsellers_mng_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/13", "bestsellers_icg_p13", ["genre_manga"], "bestsellers_icg_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/13", "bestsellers_mng_p13", ["genre_manga"], "bestsellers_mng_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/9", "bestsellers_act_p9", ["genre_game"], "bestsellers_act_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/9", "bestsellers_sln_p9", ["genre_game"], "bestsellers_sln_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/10", "bestsellers_act_p10", ["genre_game"], "bestsellers_act_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/10", "bestsellers_sln_p10", ["genre_game"], "bestsellers_sln_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100/page/10", "bestsellers_mov_p10", ["featured"], "bestsellers_mov_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/10", "bestsellers_mus_p10", ["featured", "genre_asmr"], "bestsellers_mus_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/10", "bestsellers_voice_type_p10", ["featured", "genre_asmr"], "bestsellers_voice_type_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/17", "release_new_p17", ["featured"], "release_new_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/17", "trend_p17", ["featured"], "trend_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/17", "sale_discount_p17", ["sale"], "sale_discount_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/18", "release_new_p18", ["featured"], "release_new_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/18", "trend_p18", ["featured"], "trend_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/18", "sale_discount_p18", ["sale"], "sale_discount_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/16", "release_voice_p16", ["featured", "genre_asmr"], "release_voice_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/16", "release_game_p16", ["genre_game"], "release_game_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/17", "release_voice_p17", ["featured", "genre_asmr"], "release_voice_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/17", "release_game_p17", ["genre_game"], "release_game_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100/page/10", "release_comic_p10", ["genre_manga"], "release_comic_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/13", "trend_voice_p13", ["featured", "genre_asmr"], "trend_voice_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/13", "trend_game_p13", ["genre_game"], "trend_game_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/14", "trend_voice_p14", ["featured", "genre_asmr"], "trend_voice_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/14", "trend_game_p14", ["genre_game"], "trend_game_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/10", "sale_voice_p10", ["sale", "genre_asmr"], "sale_voice_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/10", "sale_game_p10", ["sale", "genre_game"], "sale_game_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/11", "sale_voice_p11", ["sale", "genre_asmr"], "sale_voice_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/11", "sale_game_p11", ["sale", "genre_game"], "sale_game_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/13", "review_sou_p13", ["featured", "genre_asmr"], "review_sou_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/14", "review_sou_p14", ["featured", "genre_asmr"], "review_sou_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/review_d/per_page/100/page/8", "review_game_p8", ["genre_game"], "review_game_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/review_d/per_page/100/page/7", "review_comic_p7", ["genre_manga"], "review_comic_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/review_d/per_page/100/page/6", "review_rpg_p6", ["genre_game"], "review_rpg_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/review_d/per_page/100/page/6", "review_adv_p6", ["genre_game"], "review_adv_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/review_d/per_page/100/page/6", "review_icg_p6", ["genre_manga"], "review_icg_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/review_d/per_page/100/page/6", "review_mng_p6", ["genre_manga"], "review_mng_p6.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/17", "home_bestsellers_dl_p17", ["featured", "ranking"], "home_bestsellers_dl_p17.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/18", "home_bestsellers_dl_p18", ["featured", "ranking"], "home_bestsellers_dl_p18.html"),
    ("https://www.dlsite.com/home/fsr/=/order/trend/per_page/100/page/9", "home_trend_p9", ["featured"], "home_trend_p9.html"),
    ("https://www.dlsite.com/home/fsr/=/order/release_d/per_page/100/page/9", "home_release_p9", ["featured"], "home_release_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_d/per_page/100/page/9", "price_sou_p9", ["genre_asmr"], "price_sou_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_d/per_page/100/page/9", "price_game_p9", ["genre_game"], "price_game_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_a/per_page/100/page/6", "price_asc_sou_p6", ["genre_asmr"], "price_asc_sou_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/price_a/per_page/100/page/6", "price_asc_voice_p6", ["genre_asmr"], "price_asc_voice_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_a/per_page/100/page/6", "price_asc_game_p6", ["genre_game"], "price_asc_game_p6.html"),
    ("https://www.dlsite.com/books/fsr/=/order/dl_d/per_page/100/page/5", "books_bestsellers_dl_p5", ["genre_manga"], "books_bestsellers_dl_p5.html"),
    ("https://www.dlsite.com/pro/fsr/=/order/dl_d/per_page/100/page/5", "pro_bestsellers_dl_p5", ["featured", "genre_game"], "pro_bestsellers_dl_p5.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TBL/order/dl_d/per_page/100/page/6", "bestsellers_tbl_p6", ["genre_game"], "bestsellers_tbl_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TOOL/order/dl_d/per_page/100/page/6", "bestsellers_tool_p6", ["genre_game"], "bestsellers_tool_p6.html"),
    ("https://www.dlsite.com/girls/fsr/=/order/dl_d/per_page/100/page/3", "girls_bestsellers_dl_p3", ["featured"], "girls_bestsellers_dl_p3.html"),
    ("https://www.dlsite.com/bl/fsr/=/order/dl_d/per_page/100/page/3", "bl_bestsellers_dl_p3", ["featured"], "bl_bestsellers_dl_p3.html"),
    ("https://www.dlsite.com/girls/ranking/year", "girls_ranking_year", ["featured"], "girls_ranking_year.html"),
    ("https://www.dlsite.com/bl/ranking/year", "bl_ranking_year", ["featured"], "bl_ranking_year.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/11", "bestsellers_voice_type_p11", ["featured", "genre_asmr"], "bestsellers_voice_type_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/11", "bestsellers_mus_p11", ["featured", "genre_asmr"], "bestsellers_mus_p11.html"),
    # === Expansion toward ENRICH_LIMIT=6500 (page 41–45 + deeper ASMR/game/manga) ===
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/41", "bestsellers_dl_p41", ["featured", "ranking"], "bestsellers_dl_p41.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/42", "bestsellers_dl_p42", ["featured", "ranking"], "bestsellers_dl_p42.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/43", "bestsellers_dl_p43", ["featured", "ranking"], "bestsellers_dl_p43.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/44", "bestsellers_dl_p44", ["featured", "ranking"], "bestsellers_dl_p44.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/dl_d/per_page/100/page/45", "bestsellers_dl_p45", ["featured", "ranking"], "bestsellers_dl_p45.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/36", "bestsellers_voice_p36", ["featured", "genre_asmr"], "bestsellers_voice_p36.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/37", "bestsellers_voice_p37", ["featured", "genre_asmr"], "bestsellers_voice_p37.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/38", "bestsellers_voice_p38", ["featured", "genre_asmr"], "bestsellers_voice_p38.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/39", "bestsellers_voice_p39", ["featured", "genre_asmr"], "bestsellers_voice_p39.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/dl_d/per_page/100/page/40", "bestsellers_voice_p40", ["featured", "genre_asmr"], "bestsellers_voice_p40.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/36", "bestsellers_game_p36", ["featured", "genre_game"], "bestsellers_game_p36.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/37", "bestsellers_game_p37", ["featured", "genre_game"], "bestsellers_game_p37.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/38", "bestsellers_game_p38", ["featured", "genre_game"], "bestsellers_game_p38.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/39", "bestsellers_game_p39", ["featured", "genre_game"], "bestsellers_game_p39.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/dl_d/per_page/100/page/40", "bestsellers_game_p40", ["featured", "genre_game"], "bestsellers_game_p40.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/35", "bestsellers_sou_p35", ["featured", "genre_asmr"], "bestsellers_sou_p35.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/36", "bestsellers_sou_p36", ["featured", "genre_asmr"], "bestsellers_sou_p36.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/37", "bestsellers_sou_p37", ["featured", "genre_asmr"], "bestsellers_sou_p37.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/38", "bestsellers_sou_p38", ["featured", "genre_asmr"], "bestsellers_sou_p38.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/dl_d/per_page/100/page/39", "bestsellers_sou_p39", ["featured", "genre_asmr"], "bestsellers_sou_p39.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/23", "bestsellers_comic_p23", ["genre_manga"], "bestsellers_comic_p23.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/24", "bestsellers_comic_p24", ["genre_manga"], "bestsellers_comic_p24.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/dl_d/per_page/100/page/25", "bestsellers_comic_p25", ["genre_manga"], "bestsellers_comic_p25.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/18", "bestsellers_rpg_p18", ["genre_game"], "bestsellers_rpg_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/18", "bestsellers_adv_p18", ["genre_game"], "bestsellers_adv_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/dl_d/per_page/100/page/19", "bestsellers_rpg_p19", ["genre_game"], "bestsellers_rpg_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/dl_d/per_page/100/page/19", "bestsellers_adv_p19", ["genre_game"], "bestsellers_adv_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/17", "bestsellers_sim_p17", ["genre_game"], "bestsellers_sim_p17.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SIM/order/dl_d/per_page/100/page/18", "bestsellers_sim_p18", ["genre_game"], "bestsellers_sim_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/14", "bestsellers_icg_p14", ["genre_manga"], "bestsellers_icg_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/14", "bestsellers_mng_p14", ["genre_manga"], "bestsellers_mng_p14.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/dl_d/per_page/100/page/15", "bestsellers_icg_p15", ["genre_manga"], "bestsellers_icg_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/dl_d/per_page/100/page/15", "bestsellers_mng_p15", ["genre_manga"], "bestsellers_mng_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/11", "bestsellers_act_p11", ["genre_game"], "bestsellers_act_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/11", "bestsellers_sln_p11", ["genre_game"], "bestsellers_sln_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ACT/order/dl_d/per_page/100/page/12", "bestsellers_act_p12", ["genre_game"], "bestsellers_act_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SLN/order/dl_d/per_page/100/page/12", "bestsellers_sln_p12", ["genre_game"], "bestsellers_sln_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MOV/order/dl_d/per_page/100/page/11", "bestsellers_mov_p11", ["featured"], "bestsellers_mov_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/12", "bestsellers_mus_p12", ["featured", "genre_asmr"], "bestsellers_mus_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/12", "bestsellers_voice_type_p12", ["featured", "genre_asmr"], "bestsellers_voice_type_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/19", "release_new_p19", ["featured"], "release_new_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/19", "trend_p19", ["featured"], "trend_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/19", "sale_discount_p19", ["sale"], "sale_discount_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/release_d/per_page/100/page/20", "release_new_p20", ["featured"], "release_new_p20.html"),
    ("https://www.dlsite.com/maniax/fsr/=/order/trend/per_page/100/page/20", "trend_p20", ["featured"], "trend_p20.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/order/dl_d/per_page/100/page/20", "sale_discount_p20", ["sale"], "sale_discount_p20.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/18", "release_voice_p18", ["featured", "genre_asmr"], "release_voice_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/18", "release_game_p18", ["genre_game"], "release_game_p18.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/release_d/per_page/100/page/19", "release_voice_p19", ["featured", "genre_asmr"], "release_voice_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/release_d/per_page/100/page/19", "release_game_p19", ["genre_game"], "release_game_p19.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/release_d/per_page/100/page/11", "release_comic_p11", ["genre_manga"], "release_comic_p11.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/15", "trend_voice_p15", ["featured", "genre_asmr"], "trend_voice_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/15", "trend_game_p15", ["genre_game"], "trend_game_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/trend/per_page/100/page/16", "trend_voice_p16", ["featured", "genre_asmr"], "trend_voice_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/trend/per_page/100/page/16", "trend_game_p16", ["genre_game"], "trend_game_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/12", "sale_voice_p12", ["sale", "genre_asmr"], "sale_voice_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/12", "sale_game_p12", ["sale", "genre_game"], "sale_game_p12.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/audio/order/dl_d/per_page/100/page/13", "sale_voice_p13", ["sale", "genre_asmr"], "sale_voice_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/discount/1/work_type_category/game/order/dl_d/per_page/100/page/13", "sale_game_p13", ["sale", "genre_game"], "sale_game_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/15", "review_sou_p15", ["featured", "genre_asmr"], "review_sou_p15.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/review_d/per_page/100/page/16", "review_sou_p16", ["featured", "genre_asmr"], "review_sou_p16.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/review_d/per_page/100/page/9", "review_game_p9", ["genre_game"], "review_game_p9.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/comic/order/review_d/per_page/100/page/8", "review_comic_p8", ["genre_manga"], "review_comic_p8.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/RPG/order/review_d/per_page/100/page/7", "review_rpg_p7", ["genre_game"], "review_rpg_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ADV/order/review_d/per_page/100/page/7", "review_adv_p7", ["genre_game"], "review_adv_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/ICG/order/review_d/per_page/100/page/7", "review_icg_p7", ["genre_manga"], "review_icg_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MNG/order/review_d/per_page/100/page/7", "review_mng_p7", ["genre_manga"], "review_mng_p7.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/19", "home_bestsellers_dl_p19", ["featured", "ranking"], "home_bestsellers_dl_p19.html"),
    ("https://www.dlsite.com/home/fsr/=/order/dl_d/per_page/100/page/20", "home_bestsellers_dl_p20", ["featured", "ranking"], "home_bestsellers_dl_p20.html"),
    ("https://www.dlsite.com/home/fsr/=/order/trend/per_page/100/page/10", "home_trend_p10", ["featured"], "home_trend_p10.html"),
    ("https://www.dlsite.com/home/fsr/=/order/release_d/per_page/100/page/10", "home_release_p10", ["featured"], "home_release_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_d/per_page/100/page/10", "price_sou_p10", ["genre_asmr"], "price_sou_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_d/per_page/100/page/10", "price_game_p10", ["genre_game"], "price_game_p10.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/SOU/order/price_a/per_page/100/page/7", "price_asc_sou_p7", ["genre_asmr"], "price_asc_sou_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/audio/order/price_a/per_page/100/page/7", "price_asc_voice_p7", ["genre_asmr"], "price_asc_voice_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type_category/game/order/price_a/per_page/100/page/7", "price_asc_game_p7", ["genre_game"], "price_asc_game_p7.html"),
    ("https://www.dlsite.com/books/fsr/=/order/dl_d/per_page/100/page/6", "books_bestsellers_dl_p6", ["genre_manga"], "books_bestsellers_dl_p6.html"),
    ("https://www.dlsite.com/pro/fsr/=/order/dl_d/per_page/100/page/6", "pro_bestsellers_dl_p6", ["featured", "genre_game"], "pro_bestsellers_dl_p6.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TBL/order/dl_d/per_page/100/page/7", "bestsellers_tbl_p7", ["genre_game"], "bestsellers_tbl_p7.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/TOOL/order/dl_d/per_page/100/page/7", "bestsellers_tool_p7", ["genre_game"], "bestsellers_tool_p7.html"),
    ("https://www.dlsite.com/girls/fsr/=/order/dl_d/per_page/100/page/4", "girls_bestsellers_dl_p4", ["featured"], "girls_bestsellers_dl_p4.html"),
    ("https://www.dlsite.com/bl/fsr/=/order/dl_d/per_page/100/page/4", "bl_bestsellers_dl_p4", ["featured"], "bl_bestsellers_dl_p4.html"),
    ("https://www.dlsite.com/girls/ranking/month", "girls_ranking_month", ["featured"], "girls_ranking_month.html"),
    ("https://www.dlsite.com/bl/ranking/month", "bl_ranking_month", ["featured"], "bl_ranking_month.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/VOICE/order/dl_d/per_page/100/page/13", "bestsellers_voice_type_p13", ["featured", "genre_asmr"], "bestsellers_voice_type_p13.html"),
    ("https://www.dlsite.com/maniax/fsr/=/work_type/MUS/order/dl_d/per_page/100/page/13", "bestsellers_mus_p13", ["featured", "genre_asmr"], "bestsellers_mus_p13.html"),
]



DLSITE_BOILER = re.compile(
    r"「DLsite[^」]*」[^。]*。?|"
    r"お気に入りの作品をすぐダウンロードできてすぐ楽しめる！|"
    r"毎日更新しているのであなたが探している作品にきっと出会えます。|"
    r"国内最大級の二次元総合ダウンロードショップ「DLsite」！",
    re.S,
)


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.8", "Accept": "text/html"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def abs_img(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://img.dlsite.jp" + url
    return url


def to_hires_image(url: str | None) -> str | None:
    """Prefer full main image over 240x240 resize thumbs."""
    if not url:
        return None
    u = abs_img(url) or url
    # resize/..._img_main_240x240.webp → modpub/..._img_main.jpg
    if "/resize/images2/" in u:
        u = u.replace("/resize/images2/", "/modpub/images2/")
    elif "/modpub/images2/" not in u and "/images2/" in u:
        u = u.replace("/images2/", "/modpub/images2/", 1)
    u = re.sub(r"_img_main_\d+x\d+\.(?:webp|jpg|jpeg|png)", "_img_main.jpg", u, flags=re.I)
    # leftover webp main → jpg (modpub usually has jpg)
    u = re.sub(r"(_img_main)\.webp$", r"\1.jpg", u, flags=re.I)
    return u


def to_thumb_image(url: str | None, work_id: str) -> str | None:
    """Optional small thumb; derive from hi-res path when possible."""
    hi = to_hires_image(url)
    if not hi:
        return None
    m = re.search(
        rf"(https://img\.dlsite\.jp)/(?:modpub/)?images2/(work/doujin/RJ\d+)/({re.escape(work_id)}_img_main)\.(?:jpg|jpeg|png|webp)",
        hi,
        re.I,
    )
    if m:
        return f"{m.group(1)}/resize/images2/{m.group(2)}/{m.group(3)}_240x240.webp"
    # generic replace
    t = re.sub(r"/modpub/images2/", "/resize/images2/", hi)
    t = re.sub(r"_img_main\.(?:jpg|jpeg|png|webp)$", "_img_main_240x240.webp", t, flags=re.I)
    return t


def parse_ranking(html: str, source_label: str, section_hints: list[str]) -> list[dict]:
    works: list[dict] = []
    seen: set[str] = set()
    ids: list[tuple[str, int]] = []
    for m in re.finditer(r"/work/=/product_id/(RJ\d+)\.html", html):
        rid = m.group(1)
        if rid not in seen:
            seen.add(rid)
            ids.append((rid, m.start()))

    makers_all = re.findall(r'/circle/profile/=/maker_id/[^"\']+"[^>]*>([^<]+)', html)

    for idx, (rid, pos) in enumerate(ids[:RANKING_PARSE_LIMIT]):
        window = html[max(0, pos - 500) : pos + 2500]
        titles = re.findall(rf"product_id/{rid}\.html[^>]*>([^<]{{4,150}})</a>", window)
        title = None
        for t in titles:
            t = H.unescape(t.strip())
            if t and "カート" not in t and "お気に入り" not in t:
                title = t
                break
        if not title:
            continue

        img = None
        im = re.search(
            rf"//img\.dlsite\.jp/resize/images2/work/doujin/RJ\d+/{rid}_img_main_240x240\.(?:webp|jpg)",
            window,
        )
        if not im:
            im = re.search(rf"//img\.dlsite\.jp/[^\"']+{rid}_img_main[^\"']*", window)
        if im:
            img = abs_img(im.group(0))

        price = None
        pm = re.search(r"work_price[^>]*>\s*([\d,]+)", window)
        if pm:
            price = int(pm.group(1).replace(",", ""))
        price_orig = None
        om = re.search(r"(?:work_price_rest|type_salesPrice|strike)[^>]*>\s*([\d,]+)", window)
        if om:
            price_orig = int(om.group(1).replace(",", ""))
        discount = None
        dm = re.search(r"(\d+)\s*%\s*OFF", window)
        if dm:
            discount = int(dm.group(1))

        maker = None
        mm = re.search(r'/circle/profile/=/maker_id/[^"\']+"[^>]*>([^<]+)', window)
        if mm:
            maker = H.unescape(mm.group(1).strip())
        elif idx < len(makers_all):
            maker = H.unescape(makers_all[idx].strip())

        tags: list[str] = []
        for tm in re.findall(r'/genre/[^"\']+"[^>]*>([^<]+)', window):
            t = H.unescape(tm.strip())
            if t and t not in tags and len(t) < 30:
                tags.append(t)
        tags = tags[:MAX_TAGS]

        wtype = "同人"
        ctx = html[max(0, pos - 2000) : pos + 200]
        for label in [
            "ボイス・ASMR",
            "マンガ",
            "CG・イラスト",
            "ロールプレイング",
            "シミュレーション",
            "アクション",
            "デジタルノベル",
        ]:
            if label in window or label in ctx:
                wtype = label
                break

        category = "game"
        if "ASMR" in wtype or "ボイス" in wtype or any("ASMR" in t for t in tags):
            category = "asmr"
        elif "マンガ" in wtype or "CG" in wtype:
            category = "manga_cg"

        hi = to_hires_image(img)
        works.append(
            {
                "id": rid,
                "title": title,
                "maker": maker or "不明",
                "price": price,
                "price_original": price_orig,
                "discount_percent": discount,
                "on_sale": bool(discount),
                "tags": tags,
                "work_type": wtype,
                "category": category,
                "image": hi or img,
                "image_thumb": to_thumb_image(img or hi, rid),
                "description": "",
                "url": f"https://www.dlsite.com/maniax/work/=/product_id/{rid}.html",
                "affiliate_url": "",
                "sections": list(section_hints),
                "sample": False,
                "source": source_label,
            }
        )
    return works


def html_to_plain(fragment: str) -> str:
    """Strip dangerous HTML; keep paragraph breaks from <br>/<p>."""
    text = fragment
    text = re.sub(r"(?i)<script[^>]*>.*?</script>", "", text, flags=re.S)
    text = re.sub(r"(?i)<style[^>]*>.*?</style>", "", text, flags=re.S)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)</h[1-6]\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = H.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_description(html: str) -> str:
    parts: list[str] = []
    # Prefer official intro blocks inside work_parts_container (keep heading+body order)
    start = html.find('class="work_parts_container"')
    if start >= 0:
        end_candidates = [
            html.find('id="work_review"', start),
            html.find('class="work_review"', start),
            html.find('id="work_rating"', start),
            html.find('<!-- /work_right', start),
        ]
        ends = [e for e in end_candidates if e > start]
        end = min(ends) if ends else start + 100000
        area = html[start:end]
        for block in re.finditer(
            r'<div class="work_parts\b[^"]*"[^>]*>(.*?)(?=<div class="work_parts\b|$)',
            area,
            re.S,
        ):
            chunk = block.group(0)
            hm = re.search(r'class="work_parts_heading"[^>]*>(.*?)</h[1-6]>', chunk, re.S | re.I)
            texts = re.findall(
                r'class="work_parts_multitype_item type_text"[^>]*>(.*?)</div>\s*</div>',
                chunk,
                re.S | re.I,
            )
            if not texts:
                texts = re.findall(r"<p[^>]*>(.*?)</p>", chunk, re.S | re.I)
            bodies = [html_to_plain(t) for t in texts]
            bodies = [b for b in bodies if b]
            body = "\n\n".join(bodies)
            heading = html_to_plain(hm.group(1)) if hm else ""
            if heading and body:
                parts.append(f"【{heading}】\n\n{body}")
            elif body:
                parts.append(body)
            elif heading and len(heading) < 80:
                parts.append(f"【{heading}】")
            if sum(len(p) for p in parts) > 4200:
                break
        if not parts:
            for pm in re.finditer(r"<p[^>]*>(.*?)</p>", area, re.S | re.I):
                plain = html_to_plain(pm.group(1))
                if plain and len(plain) > 20:
                    parts.append(plain)
                if sum(len(p) for p in parts) > 3500:
                    break

    text = "\n\n".join(parts).strip()
    if len(text) < 40:
        # Fallback: og:description minus DLsite boilerplate
        om = re.search(r'property="og:description"\s+content="([^"]*)"', html)
        if not om:
            om = re.search(r'name="description"\s+content="([^"]*)"', html)
        if om:
            text = DLSITE_BOILER.sub("", H.unescape(om.group(1))).strip()
            text = re.sub(r"\s{2,}", " ", text)
    # Soft cap for JSON size
    if len(text) > 4500:
        text = text[:4500].rsplit("\n", 1)[0].strip() + "…"
    return text


def extract_tags(html: str) -> list[str]:
    tags: list[str] = []
    # Official genre list inside main_genre under ジャンル
    gm = re.search(r">ジャンル</th>\s*<td>(.*?)</td>", html, re.S)
    block = gm.group(1) if gm else ""
    if not block:
        # fallback: any /genre/NNNN/ links near work detail
        block = html
    for tm in re.findall(r'/genre/\d+/[^"\']*"[^>]*>([^<]+)</a>', block):
        t = H.unescape(tm.strip())
        if t and t not in tags and 1 < len(t) < 40:
            tags.append(t)
    # Situation-like options from work form icons (音声あり etc.) — light add
    for sm in re.findall(
        r'/works/type/=/work_type/[^"\']+"[^>]*>\s*<span[^>]*title="([^"]+)"',
        html,
    ):
        t = H.unescape(sm.strip())
        if t and t not in tags and len(t) < 30 and t not in ("ロールプレイング", "マンガ", "CG・イラスト"):
            # keep work_type separate; skip duplicates of form
            pass
    for sm in re.findall(
        r'options/[A-Z0-9]+/from/icon\.work"[^>]*>\s*<span[^>]*title="([^"]+)"',
        html,
    ):
        t = H.unescape(sm.strip())
        if t and t not in tags and 1 < len(t) < 30:
            tags.append(t)
    return tags[:6]


def extract_work_fields(html: str, rid: str) -> dict:
    out: dict = {}

    # Title
    tm = re.search(r'id="work_name"[^>]*>([^<]+)</h1>', html)
    if tm:
        out["title"] = H.unescape(tm.group(1).strip())

    # Maker
    mm = re.search(
        r'class="maker_name"[^>]*>.*?/circle/profile/=/maker_id/[^"\']+"[^>]*>([^<]+)',
        html,
        re.S,
    )
    if not mm:
        mm = re.search(r'/circle/profile/=/maker_id/[^"\']+"[^>]*>([^<]+)', html)
    if mm:
        out["maker"] = H.unescape(mm.group(1).strip())

    # Price
    pm = re.search(r'itemprop="price"\s+content="(\d+)"', html)
    if pm:
        out["price"] = int(pm.group(1))
    # official / ga4
    om = re.search(r'data-official_price="(\d+)"', html)
    if om:
        out["price_original"] = int(om.group(1))
    dm = re.search(r'data-price="(\d+)"[^>]*data-official_price="(\d+)"', html)
    if dm:
        sale_p, off_p = int(dm.group(1)), int(dm.group(2))
        # ga4 data-price sometimes excl tax; prefer itemprop
        if off_p > (out.get("price") or sale_p):
            out["price_original"] = off_p
            if out.get("price") and off_p > out["price"]:
                out["discount_percent"] = int(round(100 * (1 - out["price"] / off_p)))
                out["on_sale"] = out["discount_percent"] > 0

    if out.get("price") and out.get("price_original") and out["price_original"] > out["price"]:
        out["discount_percent"] = int(round(100 * (1 - out["price"] / out["price_original"])))
        out["on_sale"] = out["discount_percent"] > 0
    elif out.get("discount_percent"):
        out["on_sale"] = True

    # Work type from icon
    wt = re.search(
        r'/works/type/=/work_type/[^"\']+"[^>]*>\s*<span[^>]*title="([^"]+)"[^>]*>',
        html,
    )
    if wt:
        out["work_type"] = H.unescape(wt.group(1).strip())

    # Hi-res image
    img = None
    for pat in [
        rf'property="og:image"\s+content="([^"]*{rid}_img_main[^"]*)"',
        rf'itemprop="image"\s+content="([^"]*{rid}_img_main[^"]*)"',
        rf'data-src="(//img\.dlsite\.jp/(?:modpub/)?images2/work/doujin/RJ\d+/{rid}_img_main\.(?:jpg|webp))"',
        rf'(//img\.dlsite\.jp/modpub/images2/work/doujin/RJ\d+/{rid}_img_main\.(?:jpg|webp))',
    ]:
        im = re.search(pat, html, re.I)
        if im:
            img = abs_img(im.group(1))
            break
    if img:
        out["image"] = to_hires_image(img)
        out["image_thumb"] = to_thumb_image(img, rid)

    # First sample image (optional)
    sm = re.search(
        rf'data-src="(//img\.dlsite\.jp/[^"]*{rid}_img_smp1\.(?:jpg|webp))"',
        html,
        re.I,
    )
    if sm:
        out["image_sample"] = abs_img(sm.group(1))

    out["description"] = extract_description(html)
    out["tags"] = extract_tags(html)[:MAX_TAGS]

    # Category refinement
    wtype = out.get("work_type") or ""
    tags = out.get("tags") or []
    if any(x in wtype for x in ("ボイス", "ASMR", "音声")) or any("ASMR" in t for t in tags):
        out["category"] = "asmr"
    elif any(x in wtype for x in ("マンガ", "CG", "イラスト")):
        out["category"] = "manga_cg"
    elif any(x in wtype for x in ("ロール", "シミュ", "アクション", "アドベン", "デジタルノベル", "パズル")):
        out["category"] = "game"

    return out


def fetch_work_page(rid: str) -> tuple[str | None, str]:
    """Return (html, url_used). Try maniax then home."""
    urls = [
        f"https://www.dlsite.com/maniax/work/=/product_id/{rid}.html",
        f"https://www.dlsite.com/home/work/=/product_id/{rid}.html",
    ]
    last_err = ""
    for url in urls:
        try:
            html = fetch(url)
            if "work_name" in html or rid in html:
                return html, url
            last_err = "unexpected page"
        except Exception as e:
            last_err = str(e)
            continue
    print(f"[warn] work {rid}: {last_err}", file=sys.stderr)
    return None, urls[0]


def enrich_work(work: dict, *, force_refetch: bool = False) -> dict:
    rid = work["id"]
    if work.get("sample") or not rid.startswith("RJ"):
        return work
    WORK_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = WORK_CACHE / f"{rid}.html"
    html = None
    used_url = work.get("url") or f"https://www.dlsite.com/maniax/work/=/product_id/{rid}.html"
    if CACHE_RESUME and not force_refetch and cache_path.exists():
        try:
            cached = cache_path.read_text(encoding="utf-8", errors="replace")
            # Resume only when cache already yields a usable description
            probe = extract_description(cached)
            if len(probe.strip()) >= 40:
                html = cached
                print(f"[cache] {rid}", flush=True)
        except Exception:
            html = None
    if html is None:
        html, used_url = fetch_work_page(rid)
        if not html:
            return work
        cache_path.write_text(html, encoding="utf-8")
    fields = extract_work_fields(html, rid)
    for k, v in fields.items():
        if v is None or v == "" or v == []:
            continue
        # Prefer filling thin descriptions; never shrink a longer existing blurb
        if k == "description":
            old_d = (work.get("description") or "").strip()
            new_d = v.strip() if isinstance(v, str) else ""
            if old_d and len(old_d) >= len(new_d) and len(old_d) >= 40:
                continue
        if k == "tags":
            old_t = work.get("tags") or []
            if old_t and (not v or len(old_t) >= len(v)):
                # keep existing if new empty/shorter; still allow upgrade to fuller tag set
                if len(old_t) > len(v or []):
                    continue
        work[k] = v
    if used_url and ("maniax" in used_url or "home" in used_url):
        work["url"] = used_url
    # Ensure image is hi-res even if only ranking thumb existed
    if work.get("image"):
        work["image"] = to_hires_image(work["image"])
        if not work.get("image_thumb"):
            work["image_thumb"] = to_thumb_image(work["image"], rid)
    return work


def merge_preserve_affiliates(new_works: list[dict], old_works: list[dict]) -> list[dict]:
    old_map = {w.get("id"): w for w in old_works if w.get("id")}
    out = []
    for w in new_works:
        prev = old_map.get(w["id"])
        if prev:
            if prev.get("affiliate_url"):
                w["affiliate_url"] = prev["affiliate_url"]
            # Prefer longer descriptions from prior enrichment
            old_d = (prev.get("description") or "").strip()
            new_d = (w.get("description") or "").strip()
            if old_d and len(old_d) > len(new_d):
                w["description"] = prev["description"]
            old_t = prev.get("tags") or []
            new_t = w.get("tags") or []
            if old_t and len(old_t) > len(new_t):
                w["tags"] = old_t[:MAX_TAGS]
            if prev.get("image") and (
                not w.get("image")
                or ("240x240" in (w.get("image") or "") and "240x240" not in (prev.get("image") or ""))
            ):
                w["image"] = prev["image"]
            if prev.get("image_thumb") and not w.get("image_thumb"):
                w["image_thumb"] = prev["image_thumb"]
        out.append(w)
    return out


def enrich_sections(works: list[dict]) -> None:
    sale_n = 0
    for w in works:
        if w.get("on_sale") and sale_n < 40:
            if "sale" not in w["sections"]:
                w["sections"].append("sale")
            sale_n += 1
        if w["category"] == "asmr" and "genre_asmr" not in w["sections"]:
            w["sections"].append("genre_asmr")
        if w["category"] == "manga_cg" and "genre_manga" not in w["sections"]:
            w["sections"].append("genre_manga")
        if w["category"] == "game" and "genre_game" not in w["sections"]:
            w["sections"].append("genre_game")


def placeholders(n: int) -> list[dict]:
    hubs = [
        ("サンプル枠・週間ランキング", "https://www.dlsite.com/maniax/ranking/week", "ranking"),
        ("サンプル枠・セール", "https://www.dlsite.com/maniax/", "sale"),
        ("サンプル枠・ASMR", "https://www.dlsite.com/maniax/works/type/=/work_type/SOU", "genre_asmr"),
        ("サンプル枠・マンガ", "https://www.dlsite.com/maniax/works/type/=/work_type/MNG", "genre_manga"),
        ("サンプル枠・ゲーム", "https://www.dlsite.com/maniax/works/type/=/work_type/RPG", "genre_game"),
    ]
    out = []
    for i in range(n):
        h = hubs[i % len(hubs)]
        out.append(
            {
                "id": f"SAMPLE{i+1:02d}",
                "title": f"【サンプル枠】{h[0]}",
                "maker": "サンプル",
                "price": None,
                "price_original": None,
                "discount_percent": None,
                "on_sale": False,
                "tags": ["サンプル"],
                "work_type": "サンプル",
                "category": "game",
                "image": None,
                "image_thumb": None,
                "description": "",
                "url": h[1],
                "affiliate_url": "",
                "sections": ["featured", h[2]],
                "sample": True,
                "source": "placeholder",
            }
        )
    return out



def clamp_work_tags(works: list[dict]) -> None:
    for w in works:
        tags = w.get("tags") or []
        if isinstance(tags, list) and len(tags) > MAX_TAGS:
            w["tags"] = tags[:MAX_TAGS]


def write_embed(payload: dict) -> None:
    EMBED.write_text(
        "window.__DOJIN_EMBEDDED_WORKS__ = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )


def take_balanced(items: list[dict], cap: int = ENRICH_LIMIT) -> list[dict]:
    """Keep popularity order (SOURCES first-seen) with a light category floor."""
    buckets = {"game": [], "asmr": [], "manga_cg": [], "other": []}
    for w in items:
        buckets.get(w.get("category") or "other", buckets["other"]).append(w)
    # Soft floors so UI genre pages aren't empty; then fill by popularity order
    floor_n = max(20, min(80, cap // 6))
    plan = [("game", floor_n), ("asmr", floor_n), ("manga_cg", floor_n)]
    out: list[dict] = []
    seen: set[str] = set()
    for cat, n in plan:
        for w in buckets.get(cat, [])[:n]:
            if w["id"] not in seen:
                out.append(w)
                seen.add(w["id"])
    # Remainder: original popularity order (week/month/year/total first)
    for w in items:
        if len(out) >= cap:
            break
        if w["id"] not in seen:
            out.append(w)
            seen.add(w["id"])
    return out[:cap]


def main() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    WORK_CACHE.mkdir(parents=True, exist_ok=True)
    old_works: list[dict] = []
    if DATA.exists():
        try:
            old_works = json.loads(DATA.read_text(encoding="utf-8")).get("works") or []
        except Exception:
            old_works = []

    collected: list[dict] = []
    existing_ids: set[str] = set()
    live_ok = False
    errors: list[str] = []

    def apply_source_category(w: dict, label: str) -> None:
        if any(k in label for k in ("voice", "sou", "audio", "asmr")):
            w["category"] = "asmr"
            if "genre_asmr" not in w["sections"]:
                w["sections"].append("genre_asmr")
        elif any(k in label for k in ("comic", "illust", "icg", "mng", "manga")):
            w["category"] = "manga_cg"
            if "genre_manga" not in w["sections"]:
                w["sections"].append("genre_manga")
        elif any(k in label for k in ("game", "rpg", "adv", "sim")):
            w["category"] = "game"
            if "genre_game" not in w["sections"]:
                w["sections"].append("genre_game")
        elif "sale" in label or "discount" in label:
            if "sale" not in w["sections"]:
                w["sections"].append("sale")

    for url, label, sections, cache_name in SOURCES:
        try:
            html = fetch(url)
            (CACHE / cache_name).write_text(html, encoding="utf-8")
            parsed = parse_ranking(html, label, sections)
            live_ok = True
            for w in parsed:
                apply_source_category(w, label)
                if w["id"] in existing_ids:
                    for ow in collected:
                        if ow["id"] == w["id"]:
                            for s in w["sections"]:
                                if s not in ow["sections"]:
                                    ow["sections"].append(s)
                            apply_source_category(ow, label)
                            # Prefer non-empty ranking price/title if missing
                            if not ow.get("price") and w.get("price"):
                                ow["price"] = w["price"]
                            if (not ow.get("image")) and w.get("image"):
                                ow["image"] = w["image"]
                            break
                    continue
                existing_ids.add(w["id"])
                collected.append(w)
            print(f"[ok] {label}: {len(parsed)} works (unique so far {len(collected)})")
            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
        except (urllib.error.URLError, TimeoutError, Exception) as e:
            errors.append(f"{label}: {e}")
            print(f"[warn] {label} failed: {e}", file=sys.stderr)

    print(f"[info] collected unique before balance: {len(collected)}")
    collected = take_balanced(collected, ENRICH_LIMIT)
    print(f"[info] after balance/cap={ENRICH_LIMIT}: {len(collected)}")

    if len(collected) < 12:
        print("[info] filling placeholders to reach 12")
        for p in placeholders(12 - len(collected)):
            if p["id"] not in existing_ids:
                collected.append(p)

    def build_payload(works: list[dict], enriched_n: int) -> dict:
        return {
            "updated_at": datetime.now(JST).isoformat(),
            "live_fetch": live_ok,
            "enrich_limit": ENRICH_LIMIT,
            "enriched_count": enriched_n,
            "sources": [s[1] for s in SOURCES],
            "affiliate_note": (
                "Operator-only: paste per-work dlaf.jp URLs into affiliate_url "
                "or js/config.js affiliateUrls. Do not invent query params."
            ),
            "errors": errors,
            "works": works,
        }

    def save_progress(works: list[dict], enriched_n: int, note: str = "") -> None:
        clamp_work_tags(works)
        enrich_sections(works)
        merged = merge_preserve_affiliates(works, old_works)
        payload = build_payload(merged, enriched_n)
        DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        write_embed(payload)
        if note:
            print(f"[save] {note}: {len(merged)} works → {DATA}", flush=True)

    # Detail enrichment
    enriched_n = 0
    fetched_n = 0
    try:
        for i, w in enumerate(collected):
            if w.get("sample"):
                continue
            try:
                cache_path = WORK_CACHE / f"{w['id']}.html"
                had_good_cache = False
                if CACHE_RESUME and cache_path.exists():
                    try:
                        cached = cache_path.read_text(encoding="utf-8", errors="replace")
                        if len(extract_description(cached).strip()) >= 40:
                            had_good_cache = True
                    except Exception:
                        pass
                enrich_work(w)
                desc_ok = len((w.get("description") or "").strip()) >= 20
                tags_ok = bool(w.get("tags"))
                if desc_ok or tags_ok:
                    enriched_n += 1
                print(
                    f"[enrich] {i+1}/{len(collected)} {w['id']}: "
                    f"tags={len(w.get('tags') or [])} desc={len(w.get('description') or '')} "
                    f"img={'hi' if w.get('image') and '240x240' not in (w.get('image') or '') else w.get('image')}"
                    f"{' [cached]' if had_good_cache else ''}",
                    flush=True,
                )
                if not had_good_cache:
                    fetched_n += 1
                    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
            except Exception as e:
                errors.append(f"enrich {w.get('id')}: {e}")
                print(f"[warn] enrich {w.get('id')}: {e}", file=sys.stderr)
                # Still polite pause on errors that may be rate limits
                time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
            if (i + 1) % PARTIAL_SAVE_EVERY == 0:
                save_progress(collected, enriched_n, f"partial {i+1}/{len(collected)}")
    except KeyboardInterrupt:
        errors.append("interrupted")
        print("[warn] interrupted — saving partial progress", file=sys.stderr)
        save_progress(collected, enriched_n, "interrupted")
        return 1

    clamp_work_tags(collected)
    enrich_sections(collected)
    collected = merge_preserve_affiliates(collected, old_works)
    payload = build_payload(collected, enriched_n)
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_embed(payload)
    desc_n = sum(1 for w in collected if len((w.get("description") or "").strip()) >= 20)
    tags_n = sum(1 for w in collected if w.get("tags"))
    print(f"Wrote {len(collected)} works → {DATA} (enriched≈{enriched_n}, desc≥20={desc_n}, tags={tags_n}, net_fetches≈{fetched_n})")
    print(f"live_fetch={live_ok} updated_at={payload['updated_at']}")
    # Crawlable work/tag pages + sitemap (idempotent)
    try:
        from subprocess import run
        seo = ROOT / "scripts" / "generate_seo_pages.py"
        if seo.exists():
            r = run([sys.executable, str(seo)], cwd=str(ROOT))
            if r.returncode != 0:
                print("[warn] generate_seo_pages.py failed", file=sys.stderr)
        else:
            print("[warn] generate_seo_pages.py missing — skip SEO", file=sys.stderr)
    except Exception as e:
        print(f"[warn] SEO generate: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
