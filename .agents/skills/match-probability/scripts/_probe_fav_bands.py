#!/usr/bin/env python3
"""Sonda: jemne kurzove prahy na tržniho favorita + vliv modelove podminky.

Nalez z prvni sondy (2026-10-02): model filtr ZHORSuje uspesnost i ROI.
Cil = podil rostoucich tiketu, takze hledame jen podle trhu (kurz favorita).

Spusteni: python3 _probe_fav_bands.py
"""
import sys, csv, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

sack = tv.load_sackmann_wta()
with open(tv.ODDS_PATH, encoding="utf-8") as f:
    odds_rows = list(csv.DictReader(f))
joined = tv.join_matches(sack, odds_rows, verbose=True)
hist = tv.History(sack)
print("spojeno zapasu:", len(joined))

MIN_HIST = 15
odds_bands = [1.05, 1.08, 1.10, 1.12, 1.15, 1.18, 1.20, 1.25, 1.30, 1.40]

# [n, wins, staked, returned]
res = {b: [0, 0, 0.0, 0.0] for b in odds_bands}
res_m = {b: [0, 0, 0.0, 0.0] for b in odds_bands}   # + model>=0.5
res_hi = {b: [0, 0, 0.0, 0.0] for b in odds_bands}  # + model>=0.75

for m in joined:
    p1, n1, n2 = tv.model_prob(hist, m["name1"], m["name2"], m["cutoff"])
    if p1 is None or n1 < MIN_HIST or n2 < MIN_HIST:
        continue
    o1, o2 = m["odd1"], m["odd2"]
    if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
        continue
    if o1 <= o2:
        fav_odd, fav_won, p_fav = o1, m["p1_won"], p1
    else:
        fav_odd, fav_won, p_fav = o2, not m["p1_won"], 1 - p1
    for b in odds_bands:
        if fav_odd <= b:
            for d, ok in ((res, True), (res_m, p_fav >= 0.5), (res_hi, p_fav >= 0.75)):
                if not ok:
                    continue
                x = d[b]
                x[0] += 1
                x[1] += 1 if fav_won else 0
                x[2] += 100.0
                x[3] += 100.0 * fav_odd if fav_won else 0


def line(label, d):
    print("%-14s %7s %9s %9s" % (label, "sazek", "uspesnost", "ROI"))
    print("-" * 44)
    for b in odds_bands:
        n, w, s, r = d[b]
        if n < 30:
            print("  kurz<=%-6.2f %7d   (malo)" % (b, n))
            continue
        print("  kurz<=%-6.2f %7d %7.1f %% %+7.1f %%" % (b, n, 100.0 * w / n, (r - s) / s * 100.0))
    print()


line("BEZ modelu", res)
line("model>=0.50", res_m)
line("model>=0.75", res_hi)