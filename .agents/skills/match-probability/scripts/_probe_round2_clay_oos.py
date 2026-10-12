#!/usr/bin/env python3
"""Sonda 15: je "2. kolo + antuka + kurz<=1.15" robustni, nebo overfit?

Sonda 14 (_probe_round_direct.py) nasla:
  ordinal==2, cap<=1.15: n=462 ROI=+2.69% P50=80.7% p=0.033
  ordinal==2 & clay:     n=125 ROI=+6.00% P50=97.3% CI[+2.3,+9.1] p=0.009

Tato sonda overuje:
1) OOS split + rok po roku pro segment {ordinal==2, clay, cap<=1.15}
2) Rozpad podle turnaju: je +6% hnane jedinym turnajem (Roland Garros)?
3) Je to jen jinak vyjadreny rank-gap, nebo ma "2. kolo + antuka" vlastni
   informaci? (parovany test s ohledem na rank)
4) Citlivost na cap (1.10 / 1.15 / 1.20) u segmentu ordinal==2 & clay
5) Nahodny baseline: 1000 nahodnych segmentu stejne velikosti -> jak casto
   dosahne ROI >= +6 %? (multiplicta komparace)

Spusteni: python3 _probe_round2_clay_oos.py
"""
import csv
import os
import random
import re
from collections import Counter, defaultdict

BASE = "/root/statistiky"
ODDS_PATH = os.path.join(BASE, "tenis", "kurzy", "wta_kurzy.csv")


def load_rows():
    rows = []
    with open(ODDS_PATH, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                o1 = float(r.get("Odd_1") or 0)
                o2 = float(r.get("Odd_2") or 0)
                date = r.get("Date") or ""
                year = int(date[:4]) if date[:4].isdigit() else None
            except ValueError:
                continue
            if not (1.01 <= o1 <= 30.0 and 1.01 <= o2 <= 30.0):
                continue
            if not year:
                continue
            winner = (r.get("Winner") or "").strip()
            if not winner:
                continue
            if o1 <= o2:
                fav_odd, fav_side, fav_won = o1, 1, winner == (r.get("Player_1") or "").strip()
            else:
                fav_odd, fav_side, fav_won = o2, 2, winner == (r.get("Player_2") or "").strip()
            try:
                rank1 = int(r.get("Rank_1") or 0)
                rank2 = int(r.get("Rank_2") or 0)
            except ValueError:
                rank1 = rank2 = 0
            fav_rank = rank1 if fav_side == 1 else rank2
            und_rank = rank2 if fav_side == 1 else rank1
            rows.append({
                "year": year, "round": (r.get("Round") or "").strip(),
                "surface": (r.get("Surface") or "").strip().lower(),
                "tourney": (r.get("Tournament") or "").strip(),
                "fav_odd": fav_odd, "fav_won": fav_won,
                "fav_rank": fav_rank, "und_rank": und_rank,
            })
    return rows


def round_ordinal(rnd):
    r = rnd.strip().lower()
    m = re.match(r"^(\d+)(?:st|nd|rd|th)\s+round", r)
    if m:
        return int(m.group(1))
    if "qualif" in r:
        return 0
    if "quarter" in r:
        return 90
    if "semi" in r:
        return 91
    if "final" in r:
        return 92
    return None


def stats(sel):
    n = len(sel)
    if n == 0:
        return 0, 0.0, 0.0
    w = sum(1 for s in sel if s["fav_won"])
    staked = 100.0 * n
    ret = sum(100.0 * s["fav_odd"] for s in sel if s["fav_won"])
    return n, 100.0 * w / n, (ret - staked) / staked * 100.0


def boot_ci(sel, n_boot=6000, seed=11):
    if len(sel) < 15:
        return None
    random.seed(seed)
    n = len(sel)
    rois = []
    for _ in range(n_boot):
        s = [sel[random.randrange(n)] for _ in range(n)]
        staked = 100.0 * len(s)
        ret = sum(100.0 * x["fav_odd"] for x in s if x["fav_won"])
        rois.append((ret - staked) / staked * 100.0)
    rois.sort()
    return rois[int(0.025 * n_boot)], rois[int(0.975 * n_boot)]


def main():
    rows = load_rows()
    years = sorted(set(r["year"] for r in rows))
    mid = years[len(years) // 2]
    print(f"nacteno {len(rows)} zapasu, roky {years}, mid-split={mid}\n")

    # 1) definice kandidata
    seg = [r for r in rows if round_ordinal(r["round"]) == 2
           and r["surface"] == "clay" and r["fav_odd"] <= 1.15]
    print("=" * 100)
    print("1) KANDIDAT: ordinal==2 & clay & cap<=1.15")
    print("=" * 100)
    n, u, roi = stats(seg)
    print(f"cele: n={n} usp={u:.1f}% ROI={roi:+.2f}%")
    for lab, cond in (("1.pol (< %d)" % mid, lambda r: r["year"] < mid),
                      ("2.pol (>= %d)" % mid, lambda r: r["year"] >= mid)):
        s = [r for r in seg if cond(r)]
        nn, uu, rr = stats(s)
        ci = boot_ci(s)
        print(f"  {lab}: n={nn} usp={uu:.1f}% ROI={rr:+.2f}%"
              + (f" CI[{ci[0]:+.2f},{ci[1]:+.2f}]" if ci else ""))
    print("  po letech:")
    for y in years:
        s = [r for r in seg if r["year"] == y]
        nn, uu, rr = stats(s)
        print(f"    {y}: n={nn} usp={uu:.1f}% ROI={rr:+.2f}%")

    # 2) rozpad podle turnaju
    print()
    print("=" * 100)
    print("2) ROZPAD PODLE TURNAJU (je to jen jeden turnaj?)")
    print("=" * 100)
    per_tour = defaultdict(list)
    for r in seg:
        per_tour[r["tourney"]].append(r)
    for t, rs in sorted(per_tour.items(), key=lambda kv: -len(kv[1])):
        nn, uu, rr = stats(rs)
        print(f"  {t[:50]:50s} n={nn:3d} ROI={rr:+6.2f}% usp={uu:5.1f}%")

    # 3) rank-gap kontrola: rozdeli segment podle rank gapu
    print()
    print("=" * 100)
    print("3) RANK-GAP KONTROLA: je '2. kolo + antuka' jen jinak psany rank-gap?")
    print("=" * 100)
    for lo, hi in ((1, 50), (51, 200), (201, 10000)):
        s = [r for r in seg if lo <= (r["und_rank"] or 0) <= hi]
        nn, uu, rr = stats(s)
        print(f"  und_rank v [{lo},{hi}]: n={nn} ROI={rr:+.2f}%")
    print()
    # srovnani: rank-gap samotny (bez 2. kola), clay, cap<=1.15
    alt = [r for r in rows if r["surface"] == "clay" and r["fav_odd"] <= 1.15
           and 0 < r["fav_rank"] <= 20 and r["und_rank"] >= 50
           and round_ordinal(r["round"]) != 2]
    nn, uu, rr = stats(alt)
    print(f"  KONTROLA: clay cap<=1.15 fav<=20 und>=50, MIMO 2. kolo: "
          f"n={nn} ROI={rr:+.2f}%")
    alt2 = [r for r in rows if r["surface"] == "clay" and r["fav_odd"] <= 1.15
            and round_ordinal(r["round"]) == 2]
    nn, uu, rr = stats(alt2)
    print(f"  SROVNANI: clay cap<=1.15, 2. kolo, JAKYKOLI rank: n={nn} ROI={rr:+.2f}%")

    # 4) citlivost na cap
    print()
    print("=" * 100)
    print("4) CITLIVOST NA CAP: ordinal==2 & clay")
    print("=" * 100)
    for cap in (1.05, 1.10, 1.15, 1.20, 1.25, 1.30):
        s = [r for r in rows if round_ordinal(r["round"]) == 2
             and r["surface"] == "clay" and r["fav_odd"] <= cap]
        nn, uu, rr = stats(s)
        ci = boot_ci(s)
        print(f"  cap<={cap}: n={nn} usp={uu:.1f}% ROI={rr:+.2f}%"
              + (f" CI[{ci[0]:+.2f},{ci[1]:+.2f}]" if ci else ""))

    # 5) permutacni kontrola: nahodne segmenty stejne velikosti
    print()
    print("=" * 100)
    print("5) PERMUTACNI KONTROLA: 5000 nahodnych segmentu velikosti n=%d" % n)
    print("   (pool = vsechny clay zapasy s kurzy, bez filtru na kolo/rank)")
    print("=" * 100)
    pool = [r for r in rows if r["surface"] == "clay"]
    random.seed(23)
    st_obs = 100.0 * n
    obs = (sum(100.0 * x["fav_odd"] for x in seg if x["fav_won"]) - st_obs) / st_obs
    ge = 0
    NITER = 5000
    for _ in range(NITER):
        s = [pool[random.randrange(len(pool))] for _ in range(n)]
        st = 100.0 * n
        if (sum(100.0 * x["fav_odd"] for x in s if x["fav_won"]) - st) / st >= obs:
            ge += 1
    print(f"   pozorovane ROI={obs*100:+.2f}%; nahodnych segmentu s ROI >= to: "
          f"{ge}/{NITER} = {100.0*ge/NITER:.2f}%")
    print(f"   -> cim mensi, tim mensi riziko, ze jde o luck v ramci antuky")


if __name__ == "__main__":
    main()