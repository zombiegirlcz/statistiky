#!/usr/bin/env python3
"""Sonda 14: je "2. kolo" na grand slamech SPECIALNI, nebo je to jen
"brzke kolo GS" (1./2./3.)?

Kontrola proti overfittingu: kdyz je signal z GS-2nd-round, musi byt
specificky pro 2. kolo, ne pro vsechna rana kola GS. Jinak je to jen
"GS + silny favorit" a "2. kolo" je nahodny rez.

Testuji GS po kolech (1R/2R/3R/4R+) s cap<=1.15 a cap<=1.20, OOS split.
Soucasne kontroluji, kolik GS R64 zapasu vubec je, a jak vypada
distribuce kurz u favorita.

Spusteni: python3 _probe_gs_rounds.py
"""
import csv
import glob
import math
import os
import random
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

BASE = "/root/statistiky"

sack = {}
for path in sorted(glob.glob(os.path.join(BASE, "tenis", "wta_matches_*.csv"))):
    with open(path, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try:
                ds = int(r.get("draw_size") or 0)
            except ValueError:
                continue
            if not ds:
                continue
            w = tv.sackmann_key(r.get("winner_name") or "")
            l = tv.sackmann_key(r.get("loser_name") or "")
            d = int(r.get("tourney_date") or 0)
            sack[(w, l, d)] = (ds, r.get("round"), r.get("tourney_level"))

with open(tv.ODDS_PATH, encoding="utf-8") as f:
    odds_rows = list(csv.DictReader(f))
joined = tv.join_matches(tv.load_sackmann_wta(), odds_rows)

rows = []  # (rok, level, round_str, fav_won, fav_odd)
for m in joined:
    o1, o2 = m["odd1"], m["odd2"]
    if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
        continue
    if o1 <= o2:
        fav_odd, fav_won = o1, m["p1_won"]
    else:
        fav_odd, fav_won = o2, not m["p1_won"]
    d = int(str(m["cutoff"]))
    info = sack.get((tv.sackmann_key(m["name1"]), tv.sackmann_key(m["name2"]), d)) \
        or sack.get((tv.sackmann_key(m["name2"]), tv.sackmann_key(m["name1"]), d))
    if not info:
        continue
    _ds, round_str, level = info
    rows.append((int(str(m["cutoff"])[:4]), level, (round_str or "").strip().lower(),
                 fav_won, fav_odd))

years = sorted(set(r[0] for r in rows))
mid = years[len(years) // 2]
print("roky:", years, "delic:", mid)


def stats(sel):
    n = len(sel)
    if n == 0:
        return 0.0, 0.0
    w = sum(1 for won, _ in sel if won)
    staked = 100.0 * n
    ret = sum(100.0 * o for won, o in sel if won)
    return 100.0 * w / n, (ret - staked) / staked * 100.0


def p_up(sel, n_boot=4000, n_ticket=50, stake=100.0, start=10000.0, seed=7):
    if len(sel) < 15:
        return None
    random.seed(seed)
    n = len(sel)
    up = 0
    for _ in range(n_boot):
        bank = start
        for _ in range(n_ticket):
            won, odd = sel[random.randrange(n)]
            bank -= stake
            if won:
                bank += stake * odd
        if bank > start:
            up += 1
    return 100.0 * up / n_boot


for CAP in (1.15, 1.20):
    print(f"\n===== GS, cap<={CAP}, podle kola (Sackmann round string) =====")
    cand = [r for r in rows if r[4] <= CAP and r[1] == "G"]
    print(f"GS zapasu s fav<={CAP}: {len(cand)}")
    for rnd in ("r128", "r64", "r32", "r16", "qf", "sf", "f"):
        sel = [(r[3], r[4]) for r in cand if r[2] == rnd]
        w, roi = stats(sel)
        u = p_up(sel)
        s1 = [(r[3], r[4]) for r in cand if r[2] == rnd and r[0] < mid]
        s2 = [(r[3], r[4]) for r in cand if r[2] == rnd and r[0] >= mid]
        _, roi1 = stats(s1)
        _, roi2 = stats(s2)
        print(f"  {rnd:>5}: n={len(sel):4d} uspes={w:5.1f}% ROI={roi:+6.2f}% "
              f"P(50)={'%.0f%%' % u if u is not None else '  - ':>5} "
              f"| 1.pol {roi1:+6.2f}% / 2.pol {roi2:+6.2f}%")

    # Kontrola: vsechna rana kola GS dohromady (r128+r64+r32)
    for lab, codes in (("GS r128+r64+r32", {"r128", "r64", "r32"}),
                       ("GS r64 only (2. kolo)", {"r64"}),
                       ("GS r32 only (3. kolo)", {"r32"})):
        sel = [(r[3], r[4]) for r in cand if r[2] in codes]
        w, roi = stats(sel)
        u = p_up(sel)
        print(f"  [{lab}] n={len(sel)} ROI={roi:+.2f}% P(50)={u}")

# Distribuce kur u GS R64 favoritu
print("\n=== distribuce kur u GS R64 favoritu ===")
gs64 = [r[4] for r in rows if r[1] == "G" and r[2] == "r64"]
c = Counter()
for o in gs64:
    if o <= 1.10:
        c["<=1.10"] += 1
    elif o <= 1.15:
        c["1.10-1.15"] += 1
    elif o <= 1.20:
        c["1.15-1.20"] += 1
    elif o <= 1.30:
        c["1.20-1.30"] += 1
    elif o <= 1.50:
        c["1.30-1.50"] += 1
    else:
        c[">1.50"] += 1
print(" ", dict(c), " celkem GS R64:", len(gs64))