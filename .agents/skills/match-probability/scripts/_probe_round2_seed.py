#!/usr/bin/env python3
"""Sonda 16: je "2. kolo" efekt vlastne jen efekt NASZENYCH hracek (bye)?

Motivace (denik 2026-10-07, priorita 2): 2. kolo favorit ma ROI +3.6 %
(cap<=1.15), na antuce +6 %. Mechanismus muze byt: nasazene hracky maji
v 1. kole bye, do 2. kola vstupuji cerstve a proti slabsimu souperi.
Pokud ano, zivy filtr NEPOTREBUJE znalost velikosti pavouka -- staci
fav_rank (resp. seed) <= 8, coz Live API dava.

Tato sonda testuje na WTA kurzy CSV (ma Round i Rank_1/Rank_2):
A) 2. kolo & cap<=1.15 rozdelene podle fav_rank pasem (<=4, <=8, 9-20, >20)
B) stejna rank pasma MIMO 2. kolo -> pridava 2. kolo informaci nad rank?
C) na antuce zvlast
D) OOS split (1./2. polovina let) pro nejlepsi rank pasmo
E) rozpad podle turnaje

Vklady FLAT 100. Vysledek: ROI, uspesnost, bootstrap CI, P(50).

Spusteni: python3 _probe_round2_seed.py
"""
import csv
import os
import random
import re

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
            if not (1.01 <= o1 <= 30.0 and 1.01 <= o2 <= 30.0) or not year:
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


def p_up(sel, n_boot=4000, n_ticket=50, stake=100.0, start=10000.0, seed=7):
    if len(sel) < 20:
        return None
    random.seed(seed)
    n = len(sel)
    up = 0
    for _ in range(n_boot):
        bank = start
        for _ in range(n_ticket):
            s = sel[random.randrange(n)]
            bank -= stake
            if s["fav_won"]:
                bank += stake * s["fav_odd"]
        if bank > start:
            up += 1
    return 100.0 * up / n_boot


BANDS = [(1, 4, "rank<=4"), (5, 8, "rank 5-8"), (9, 20, "rank 9-20"),
         (21, 10000, "rank>20"), (1, 8, "rank<=8"), (1, 20, "rank<=20")]


def report(label, sel):
    n, u, roi = stats(sel)
    ci = boot_ci(sel)
    pu = p_up(sel)
    ci_s = f" CI[{ci[0]:+.2f},{ci[1]:+.2f}]" if ci else ""
    pu_s = f" P50={pu:.0f}%" if pu is not None else ""
    print(f"  {label:24s} n={n:4d} usp={u:5.1f}% ROI={roi:+6.2f}%{ci_s}{pu_s}")


def main():
    rows = load_rows()
    years = sorted(set(r["year"] for r in rows))
    mid = years[len(years) // 2]
    print(f"nacteno {len(rows)} zapasu, roky {years}, mid={mid}\n")

    r2 = [r for r in rows if round_ordinal(r["round"]) == 2 and r["fav_odd"] <= 1.15]
    print("=" * 90)
    print("A) 2. KOLO & cap<=1.15 podle fav_rank (hypoteza: efekt je z nasazenych)")
    print("=" * 90)
    for lo, hi, lab in BANDS:
        report(lab, [r for r in r2 if lo <= (r["fav_rank"] or 0) <= hi])

    print()
    print("=" * 90)
    print("B) STEJNA rank pasma MIMO 2. kolo & cap<=1.15 (kontrola: pridava 2.kolo info?)")
    print("=" * 90)
    non2 = [r for r in rows if round_ordinal(r["round"]) != 2 and r["fav_odd"] <= 1.15]
    for lo, hi, lab in BANDS:
        report(lab, [r for r in non2 if lo <= (r["fav_rank"] or 0) <= hi])

    print()
    print("=" * 90)
    print("C) ANTUKA: 2. kolo & cap<=1.15 podle fav_rank")
    print("=" * 90)
    r2c = [r for r in r2 if r["surface"] == "clay"]
    for lo, hi, lab in BANDS:
        report(lab, [r for r in r2c if lo <= (r["fav_rank"] or 0) <= hi])
    print("  -- antuka MIMO 2. kolo:")
    n2c = [r for r in non2 if r["surface"] == "clay"]
    for lo, hi, lab in BANDS:
        report(lab, [r for r in n2c if lo <= (r["fav_rank"] or 0) <= hi])

    print()
    print("=" * 90)
    print("D) OOS pro kandidata: 2. kolo & cap<=1.15 & fav_rank<=8 (vsechny povrchy)")
    print("=" * 90)
    k = [r for r in r2 if 1 <= (r["fav_rank"] or 0) <= 8]
    report("cele", k)
    for lab, cond in (("1.pol (<%d)" % mid, lambda r: r["year"] < mid),
                      ("2.pol (>=%d)" % mid, lambda r: r["year"] >= mid)):
        report(lab, [r for r in k if cond(r)])
    for y in years:
        report(str(y), [r for r in k if r["year"] == y])

    print()
    print("=" * 90)
    print("E) ROZPAD kandidata fav_rank<=8 & 2.kolo podle turnaje")
    print("=" * 90)
    from collections import defaultdict
    per = defaultdict(list)
    for r in k:
        per[r["tourney"]].append(r)
    for t, rs in sorted(per.items(), key=lambda kv: -len(kv[1])):
        n, u, roi = stats(rs)
        print(f"  {t[:52]:52s} n={n:3d} ROI={roi:+6.2f}%")


if __name__ == "__main__":
    main()