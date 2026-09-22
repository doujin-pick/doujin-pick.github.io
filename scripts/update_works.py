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
ENRICH_LIMIT = 2500
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

    # === Expansion toward ENRICH_LIMIT=2500 (page 3–5 + more splits) ===
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
    # === Expansion toward ENRICH_LIMIT=2500 (page 4–5 + niche types) ===
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
        if prev and prev.get("affiliate_url"):
            w["affiliate_url"] = prev["affiliate_url"]
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
