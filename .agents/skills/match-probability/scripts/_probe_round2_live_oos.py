#!/usr/bin/env python3
"""Sonda 12: ZIVE odvoditelny "2. kolo" (z tier + round_code) - je robustni?

Nalez ze sondy 11: selection {est_ordinal==2} odvozeny POUZE z zive
dostupnych poli (tier -> odhad draw_size, round_code -> cislo kola) dal
pri cap<=1.15 ROI +2.6 %, P(rost50)=73 %, n=286. To je PRIMO nasaditelne
(na rozdil od Sackmann "2nd Round", ktery zivy neni).

Tato sonda overuje robustnost:
  - OOS split (prvni vs druha polovina let)
  - rok po roku
  - podle tieru (odkud signal pochazi)
  - citlivost na cap
  - bootstrap CI + permutacni p-hodnota (neni to artefakt mnoha rezu?)

Spusteni: python3 _probe_round2_live_oos.py
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

TIER_DRAW = {
    "grand_slam": 128, "wta_1000": 56, "wta_500": 32, "wta_250": 32,
    "wta_125": 32, "challenger_125": 32, "challenger_75": 32,
    "itf_w15": 32, "itf_m15": 32, "itf_w50": 32, "itf_m25": 32,
}
LEVEL_TIER = {
    "G": "grand_slam", "PM": "wta_1000", "P": "wta_500", "I": "wta_250",
    "W": "wta_125", "O": "wta_500", "F": "wta_500", "D": "wta_500",
}


def code_num(rc):
    if not rc:
        return None
    rc = rc.strip().upper()
    m = re.match(r"^R(\d+)$", rc)
    if m:
        return int(m.group(1))
    return {"QF": 8, "SF": 4, "F": 2}.get(rc)


# nacti draw_size/level z Sackmann (klic = hraci + datum turnaje)
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

rows = []  # (rok, level, tier, round_code, fav_won, fav_odd, est_ordinal)
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
    rc = None
    mm = re.match(r"^r(\d+)$", rs)
    if mm:
        rc = "R" + mm.group(1)
    elif "quarter" in rs:
        rc = "QF"
    elif "semi" in rs:
        rc = "SF"
    elif rs == "f" or "final" in rs:
        rc = "F"
    cn = code_num(rc)
    tier = LEVEL_TIER.get(level)
    est_draw = TIER_DRAW.get(tier) if tier else None
    est_o = None
    if cn and est_draw and est_draw >= cn:
        est_o = int(round(math.log2(est_draw) - math.log2(cn))) + 1
    rows.append((int(str(m["cutoff"])[:4]), level, tier, rc, fav_won,
                 fav_odd, est_o))

print("radku:", len(rows))
years = sorted(set(r[0] for r in rows))
mid = years[len(years) // 2]
print("roky:", years, "delic:", mid)


def stats(sel):
    n = len(sel)
    if n == 0:
        return n, 0.0, 0.0
    w = sum(1 for won, _ in sel if won)
    staked = 100.0 * n
    ret = sum(100.0 * o for won, o in sel if won)
    return n, 100.0 * w / n, (ret - staked) / staked * 100.0


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


def boot_ci(sel, n_boot=4000, seed=11):
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


def perm_p(sel, n_perm=4000, seed=13):
    """p-hodnota: jak casto nahodny vyber stejne velikosti (z cele populace
    cap<=X) ma ROI >= pozorovane."""
    if len(sel) < 15:
        return None
    random.seed(seed)
    n = len(sel)
    obs_staked = 100.0 * n
    obs_ret = sum(100.0 * o for won, o in sel if won)
    obs_roi = (obs_ret - obs_staked) / obs_staked
    ge = 0
    for _ in range(n_perm):
        s = [pool[random.randrange(len(pool))] for _ in range(n)]
        staked = 100.0 * n
        ret = sum(100.0 * o for won, o in s if won)
        if (ret - staked) / staked >= obs_roi:
            ge += 1
    return ge / n_perm


for CAP in (1.10, 1.15, 1.20):
    print(f"\n{'='*60}\nCAP = {CAP}  (selection: est_ordinal==2)\n{'='*60}")
    pool = [(r[4], r[5]) for r in rows if r[5] <= CAP]  # pro permutaci
    cand = [r for r in rows if r[5] <= CAP and r[6] == 2]
    sel = [(r[4], r[5]) for r in cand]
    n, w, roi = stats(sel)
    print(f"celkem: n={n} uspes={w:.1f}% ROI={roi:+.2f}% P(50)={p_up(sel)}%")
    ci = boot_ci(sel)
    if ci:
        print(f"  bootstrap 95% CI ROI: [{ci[0]:+.2f}%, {ci[1]:+.2f}%]")
    pp = perm_p(sel)
    if pp is not None:
        print(f"  permutacni p (vs cely pool cap): {pp:.4f}")
    # OOS
    for lab, cond in (("1. polovina", lambda r: r[0] < mid),
                      ("2. polovina", lambda r: r[0] >= mid)):
        s = [(r[4], r[5]) for r in cand if cond(r)]
        nn, ww, rr = stats(s)
        print(f"  {lab}: n={nn} uspes={ww:.1f}% ROI={rr:+.2f}% P(50)={p_up(s)}%")
    # rok po roku
    print("  rok po roku:")
    for y in years:
        s = [(r[4], r[5]) for r in cand if r[0] == y]
        nn, ww, rr = stats(s)
        print(f"    {y}: n={nn} uspes={ww:.1f}% ROI={rr:+.2f}%")
    # podle tieru
    print("  podle tieru:")
    tiers = sorted(set(r[2] for r in cand))
    for t in tiers:
        s = [(r[4], r[5]) for r in cand if r[2] == t]
        nn, ww, rr = stats(s)
        print(f"    {t}: n={nn} uspes={ww:.1f}% ROI={rr:+.2f}%")