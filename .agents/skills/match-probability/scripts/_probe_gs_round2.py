#!/usr/bin/env python3
"""Sonda 13: FOKUS - grand slam "2. kolo" (zive odvoditelne) favorit.

Ze sondy 12 vzeslo, ze segment {est_ordinal==2} je celkove nesig (perm p=0.12),
ale rozpad podle tieru ukazal silny kontrast:
  grand_slam: ROI +5.95 % (n=102, cap 1.15)
  wta_1000:   ROI -4.81 % (n=53)
Ostatni mirne kladne.

Tato sonda testuje vyhradne grand_slam 2. kolo (zive: tier=grand_slam,
round_code=R64) s OOS, po rocich, cap citlivosti a permutaci.

Spusteni: python3 _probe_gs_round2.py
"""
import csv
import glob
import math
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

BASE = "/root/statistiky"
TIER_DRAW = {"grand_slam": 128, "wta_1000": 56, "wta_500": 32, "wta_250": 32,
             "wta_125": 32}
LEVEL_TIER = {"G": "grand_slam", "PM": "wta_1000", "P": "wta_500", "I": "wta_250",
              "W": "wta_125"}


def code_num(rc):
    if not rc:
        return None
    m = re.match(r"^R(\d+)$", rc.strip().upper())
    if m:
        return int(m.group(1))
    return {"QF": 8, "SF": 4, "F": 2}.get(rc.strip().upper())


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

rows = []  # (rok, tier, est_o, fav_won, fav_odd)
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
    rs = (round_str or "").strip().lower()
    rc = "R" + re.match(r"^r(\d+)$", rs).group(1) if re.match(r"^r(\d+)$", rs) else \
        ("QF" if "quarter" in rs else "SF" if "semi" in rs else
         "F" if rs in ("f",) or "final" in rs else None)
    cn = code_num(rc)
    tier = LEVEL_TIER.get(level)
    est_draw = TIER_DRAW.get(tier) if tier else None
    est_o = None
    if cn and est_draw and est_draw >= cn:
        est_o = int(round(math.log2(est_draw) - math.log2(cn))) + 1
    rows.append((int(str(m["cutoff"])[:4]), tier, est_o, fav_won, fav_odd))

years = sorted(set(r[0] for r in rows))
mid = years[len(years) // 2]


def stats(sel):
    n = len(sel)
    if n == 0:
        return 0.0, 0.0
    w = sum(1 for won, _ in sel if won)
    staked = 100.0 * n
    ret = sum(100.0 * o for won, o in sel if won)
    return 100.0 * w / n, (ret - staked) / staked * 100.0


def p_up(sel, n_boot=6000, n_ticket=50, stake=100.0, start=10000.0, seed=7):
    if len(sel) < 15:
        return None
    random.seed(seed)
    n = len(sel)
    up = sum(1 for _ in range(n_boot)
             if _bank(sel, n, n_ticket, stake, start) > start)
    return 100.0 * up / n_boot


def _bank(sel, n, n_ticket, stake, start):
    bank = start
    for _ in range(n_ticket):
        won, odd = sel[random.randrange(n)]
        bank -= stake
        if won:
            bank += stake * odd
    return bank


def boot_ci(sel, n_boot=6000, seed=11):
    if len(sel) < 15:
        return None
    random.seed(seed)
    n = len(sel)
    rois = []
    for _ in range(n_boot):
        s = [sel[random.randrange(n)] for _ in range(n)]
        staked = 100.0 * len(s)
        ret = sum(100.0 * o for won, o in s if won)
        rois.append((ret - staked) / staked * 100.0)
    rois.sort()
    return rois[int(0.025 * n_boot)], rois[int(0.975 * n_boot)]


def perm_p(sel, pool, n_perm=6000, seed=13):
    if len(sel) < 15:
        return None
    random.seed(seed)
    n = len(sel)
    st = 100.0 * n
    obs = (sum(100.0 * o for won, o in sel if won) - st) / st
    ge = 0
    for _ in range(n_perm):
        s = [pool[random.randrange(len(pool))] for _ in range(n)]
        st = 100.0 * n
        if (sum(100.0 * o for won, o in s if won) - st) / st >= obs:
            ge += 1
    return ge / n_perm


for CAP in (1.10, 1.15, 1.20):
    cand = [r for r in rows if r[4] <= CAP and r[1] == "grand_slam" and r[2] == 2]
    sel = [(r[3], r[4]) for r in cand]
    pool = [(r[3], r[4]) for r in rows if r[4] <= CAP and r[1] == "grand_slam"]
    w, roi = stats(sel)
    print(f"\n=== GS 2. kolo, cap<={CAP}: n={len(sel)} uspes={w:.1f}% "
          f"ROI={roi:+.2f}% P(50)={p_up(sel)}%")
    ci = boot_ci(sel)
    if ci:
        print(f"    bootstrap CI: [{ci[0]:+.2f}%, {ci[1]:+.2f}%]")
    pp = perm_p(sel, pool)
    if pp is not None:
        print(f"    perm p (vs GS pool cap): {pp:.4f}")
    for lab, cond in (("1.pol", lambda r: r[0] < mid), ("2.pol", lambda r: r[0] >= mid)):
        s = [(r[3], r[4]) for r in cand if cond(r)]
        ww, rr = stats(s)
        print(f"    {lab}: n={len(s)} uspes={ww:.1f}% ROI={rr:+.2f}%")
    print("    rok:", end="")
    for y in years:
        s = [(r[3], r[4]) for r in cand if r[0] == y]
        ww, rr = stats(s)
        print(f"  {y}:n={len(s)}/{rr:+.1f}%", end="")
    print()