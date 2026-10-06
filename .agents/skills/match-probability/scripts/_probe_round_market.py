#!/usr/bin/env python3
"""Sonda 8: je efekt "trh-only favorit na antuce" ve skutecnosti efekt KOLA?

Predchozi nalez (2026-10-05): trh-only favorit, kurz<=1.20, antuka mel
jedine kladne ROI (+0.9 %) a P(rost) 58 %. Otazka: neni to nahodou tim,
ze antukove turnaje maji jiny mix kol? Nebo je naopak kolo silnejsi filtr?

Testuji trh-only favorita (bez modelu) v rezu:
  - kolo (1st Round / 2nd Round / 3rd+ / QF+)
  - povrch (clay / hard / grass / ne-clay)
  - kombinace kolo x povrch
  - OOS: prvni vs druha polovina let
Metrika: uspesnost, ROI, P(rost banky po 50 tiketech).

Vklady FLAT 100, start 10 000, kurzovy cap 1.20 (dle predchozi sondy).

Spusteni: python3 _probe_round_market.py
"""
import sys, csv, os, random
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

sack = tv.load_sackmann_wta()
with open(tv.ODDS_PATH, encoding="utf-8") as f:
    odds_rows = list(csv.DictReader(f))
joined = tv.join_matches(sack, odds_rows)
hist = tv.History(sack)
MIN_HIST = 15

# (rok, povrch, kolo, fav_won, fav_odd)
rows = []
for m in joined:
    o1, o2 = m["odd1"], m["odd2"]
    if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
        continue
    if o1 <= o2:
        fav_odd, fav_won = o1, m["p1_won"]
    else:
        fav_odd, fav_won = o2, not m["p1_won"]
    rows.append((int(str(m["cutoff"])[:4]), (m.get("surface") or "").lower(),
                 (m.get("round") or ""), fav_won, fav_odd))

years = sorted(set(r[0] for r in rows))
mid = years[len(years) // 2]
print("celkem:", len(rows), "roky:", years, "delic:", mid)


def round_bucket(r):
    rl = r.lower()
    if "1st" in rl:
        return "1st"
    if "2nd" in rl:
        return "2nd"
    if "3rd" in rl or "4th" in rl:
        return "3rd/4th"
    if "quarter" in rl:
        return "QF"
    if "semi" in rl:
        return "SF"
    if "final" in rl:
        return "F"
    if "round robin" in rl:
        return "RR"
    return "?"


def stats(sel):
    n = len(sel)
    if n == 0:
        return n, 0.0, 0.0
    w = sum(1 for won, _ in sel if won)
    staked = 100.0 * n
    ret = sum(100.0 * o for won, o in sel if won)
    return n, 100.0 * w / n, (ret - staked) / staked * 100.0


def p_up(sel, n_boot=4000, n_ticket=50, stake=100.0, start=10000.0, seed=7):
    if len(sel) < 20:
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


CAP = 1.20
cand = [r for r in rows if r[4] <= CAP]
print("\n=== trh-only favorit, kurz<=%.2f, podle KOLA ===" % CAP)
print("%-10s %6s %9s %9s %9s" % ("kolo", "n", "uspes", "ROI", "P(rost50)"))
for rnd in ("1st", "2nd", "3rd/4th", "QF", "SF", "F", "RR"):
    sel = [(r[3], r[4]) for r in cand if round_bucket(r[2]) == rnd]
    n, w, roi = stats(sel)
    u = p_up(sel)
    print("%-10s %6d %8.1f%% %+8.1f%% %9s" % (rnd, n, w, roi,
          "%.0f%%" % u if u is not None else "-"))

print("\n=== trh-only favorit, kurz<=%.2f, podle POVRCHU ===" % CAP)
print("%-10s %6s %9s %9s %9s" % ("povrch", "n", "uspes", "ROI", "P(rost50)"))
for surf in ("clay", "hard", "grass"):
    sel = [(r[3], r[4]) for r in cand if surf in r[1]]
    n, w, roi = stats(sel)
    u = p_up(sel)
    print("%-10s %6d %8.1f%% %+8.1f%% %9s" % (surf, n, w, roi,
          "%.0f%%" % u if u is not None else "-"))

print("\n=== KOLO x POVRCH (clay vs ne-clay), kurz<=%.2f ===" % CAP)
print("%-12s %-14s %6s %9s %9s %9s" % ("kolo", "povrch", "n", "uspes", "ROI", "P(50)"))
for rnd in ("1st", "2nd", "3rd/4th", "QF", "SF", "F"):
    for lab, cond in (("clay", lambda r: "clay" in r[1]),
                      ("ne-clay", lambda r: "clay" not in r[1])):
        sel = [(r[3], r[4]) for r in cand if round_bucket(r[2]) == rnd and cond(r)]
        n, w, roi = stats(sel)
        u = p_up(sel)
        print("%-12s %-14s %6d %8.1f%% %+8.1f%% %9s" % (rnd, lab, n, w, roi,
              "%.0f%%" % u if u is not None else "-"))

print("\n=== OOS kontrola nejlepsich kandidatu (prvni vs druha polovina let) ===")
cands = {
    "clay o<=1.20":            lambda r: "clay" in r[1],
    "clay, ne 1st round":      lambda r: "clay" in r[1] and round_bucket(r[2]) != "1st",
    "ne-clay, QF+":            lambda r: "clay" not in r[1] and round_bucket(r[2]) in ("QF", "SF", "F"),
    "clay, QF+":               lambda r: "clay" in r[1] and round_bucket(r[2]) in ("QF", "SF", "F"),
    "vse <=1.20":              lambda r: True,
}
print("%-24s %-12s %5s %8s %8s %8s" % ("kandidat", "obdobi", "n", "uspes", "ROI", "P(50)"))
for lab, pred in cands.items():
    for plab, ycond in (("prvni", lambda y: y < mid), ("druha", lambda y: y >= mid)):
        sel = [(r[3], r[4]) for r in cand if pred(r) and ycond(r[0])]
        n, w, roi = stats(sel)
        u = p_up(sel)
        print("%-24s %-12s %5d %7.1f%% %+7.1f%% %8s" % (lab, plab, n, w, roi,
              "%.0f%%" % u if u is not None else "-"))