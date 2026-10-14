#!/usr/bin/env python3
"""Sonda 3: segmentace tržního favorita s NÍZKÝM kurzem (bez modelu).

Predchozi sonda: nejlepsi pasmo je kurz<=1.15 (uspesnost 89.7 %, ROI -0.8 %).
Tady hledam, jestli nejaky povrch/kolo ma ROI vyrazne lepsi (i kladne),
nebo jestli je marze rozprostrena rovnomerne.

Spusteni: python3 _probe_fav_segments.py
"""
import sys, csv, os
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

sack = tv.load_sackmann_wta()
with open(tv.ODDS_PATH, encoding="utf-8") as f:
    odds_rows = list(csv.DictReader(f))
joined = tv.join_matches(sack, odds_rows)
hist = tv.History(sack)

MIN_HIST = 15
ODDS_CAP = 1.20   # zkoumej jen silne favority

# dimenze -> [n, wins, staked, returned]
by_surface = defaultdict(lambda: [0, 0, 0.0, 0.0])
by_round = defaultdict(lambda: [0, 0, 0.0, 0.0])
by_band = defaultdict(lambda: [0, 0, 0.0, 0.0])   # jemnejsi kurzova pasma

for m in joined:
    p1, n1, n2 = tv.model_prob(hist, m["name1"], m["name2"], m["cutoff"])
    if p1 is None or n1 < MIN_HIST or n2 < MIN_HIST:
        continue
    o1, o2 = m["odd1"], m["odd2"]
    if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
        continue
    if o1 <= o2:
        fav_odd, fav_won = o1, m["p1_won"]
    else:
        fav_odd, fav_won = o2, not m["p1_won"]
    if fav_odd > ODDS_CAP:
        continue
    for d, key in (
        (by_surface, m["surface"] or "?"),
        (by_round, m["round"] or "?"),
        (by_band, "<=1.10" if fav_odd <= 1.10 else ("<=1.15" if fav_odd <= 1.15 else "<=1.20")),
    ):
        x = d[key]
        x[0] += 1
        x[1] += 1 if fav_won else 0
        x[2] += 100.0
        x[3] += 100.0 * fav_odd if fav_won else 0


def dump(title, d, min_n=40):
    print("=== %s (kurz<=%.2f, bez modelu) ===" % (title, ODDS_CAP))
    print("%-14s %7s %9s %9s" % (title, "sazek", "uspesnost", "ROI"))
    print("-" * 44)
    for key in sorted(d, key=lambda k: -d[k][0]):
        n, w, s, r = d[key]
        if n < min_n:
            print("  %-12s %7d   (malo)" % (key, n))
            continue
        print("  %-12s %7d %7.1f %% %+7.1f %%" % (key, n, 100.0 * w / n, (r - s) / s * 100.0))
    print()


dump("POVRCH", by_surface)
dump("KOLO", by_round)
dump("KURZOVE PASMO", by_band, min_n=10)