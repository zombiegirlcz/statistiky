#!/usr/bin/env python3
"""Sonda 6: robustnost segmentu Clay u silneho favorita.

Sonda 5 (OOS) naznacila, ze u tržniho favorita s kurzem <= 1.15 drzi
segment Clay v obou polovinach (P(rost) 76 % / 85 %), zatimco baseline
(=vsechny povrchy) druhou polovinu neudrzi (74 % / 35 %).

Tady to overuji PRISNEJI, aby se vyloucil overfitting:
  1. rok po roku (2021..2025) - uspesnost i ROI na Clay
  2. ruzne kurzove capy (1.10 / 1.15 / 1.20 / 1.25) - je vysledek citlivy na cap?
  3. Monte Carlo P(rost banky) po 50 tiketech pro kazdou variantu
  4. kontrola: kolik sazek v kazde bunce (aby to nebyl sum z 20 pripadu)

Vse bez modelu (model filtr se uz prokazal jako skodlivy).
Vklady FLAT 100, start 10 000.

Spusteni: python3 _probe_fav_clay_robust.py
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

# (rok, povrch_lower, fav_won, fav_odd)
rows = []
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
    rows.append((int(str(m["cutoff"])[:4]), (m.get("surface") or "").lower(),
                 fav_won, fav_odd))

print("celkem kandidatu:", len(rows))


def stats(sel):
    n = len(sel)
    if n == 0:
        return n, 0.0, 0.0
    w = sum(1 for won, _ in sel if won)
    staked = 100.0 * n
    ret = sum(100.0 * odd for won, odd in sel if won)
    return n, 100.0 * w / n, (ret - staked) / staked * 100.0


def mc_up(sel, n_boot=5000, n_ticket=50, stake=100.0, start=10000.0, seed=11):
    if len(sel) < 20:
        return None
    random.seed(seed)
    n = len(sel)
    up = 0
    ros = []
    for _ in range(n_boot):
        bank = start
        for _ in range(n_ticket):
            won, odd = sel[random.randrange(n)]
            bank -= stake
            if won:
                bank += stake * odd
        ro = (bank - start) / start * 100.0
        ros.append(ro)
        if bank > start:
            up += 1
    ros.sort()
    return 100.0 * up / n_boot, ros[n_boot // 2]


print("\n=== 1) CLAY rok po roku (bez kurzoveho capu, jen Clay) ===")
print("%-8s %6s %9s %9s %9s" % ("rok", "n", "uspes", "ROI", "P(rost50)"))
for y in sorted(set(r[0] for r in rows)):
    sel = [(r[2], r[3]) for r in rows if r[0] == y and "clay" in r[1]]
    n, w, roi = stats(sel)
    up = mc_up(sel)
    up_s = "%.0f%%" % up[0] if up else "-"
    print("%-8d %6d %8.1f%% %+8.1f%% %9s" % (y, n, w, roi, up_s))

print("\n=== 2) CLAY + ruzne kurzove capy (vsechny roky) ===")
print("%-10s %6s %9s %9s %9s" % ("cap", "n", "uspes", "ROI", "P(rost50)"))
for cap in (1.10, 1.15, 1.20, 1.25, 1.30):
    sel = [(r[2], r[3]) for r in rows if "clay" in r[1] and r[3] <= cap]
    n, w, roi = stats(sel)
    up = mc_up(sel)
    up_s = "%.0f%%" % up[0] if up else "-"
    print("<= %-7.2f %6d %8.1f%% %+8.1f%% %9s" % (cap, n, w, roi, up_s))

print("\n=== 3) SROVNANI segmentu pri capu 1.15 ===")
print("%-16s %6s %9s %9s %9s" % ("segment", "n", "uspes", "ROI", "P(rost50)"))
for label, cond in (
    ("Vsechny povrchy", lambda r: True),
    ("Clay", lambda r: "clay" in r[1]),
    ("Hard", lambda r: "hard" in r[1]),
    ("Grass", lambda r: "grass" in r[1]),
    ("NE Clay", lambda r: "clay" not in r[1]),
):
    sel = [(r[2], r[3]) for r in rows if r[3] <= 1.15 and cond(r)]
    n, w, roi = stats(sel)
    up = mc_up(sel)
    up_s = "%.0f%%" % up[0] if up else "-"
    print("%-16s %6d %8.1f%% %+8.1f%% %9s" % (label, n, w, roi, up_s))

print("\n=== 4) CLAY vs NE-CLAY: rozdil P(rost) - test stability ===")
# bootstrap rozdil P(rost) mezi Clay a NE-Clay (cap 1.15)
clay = [(r[2], r[3]) for r in rows if "clay" in r[1] and r[3] <= 1.15]
nonclay = [(r[2], r[3]) for r in rows if "clay" not in r[1] and r[3] <= 1.15]


def p_up(sel, n_boot=3000, seed=5):
    random.seed(seed)
    n = len(sel)
    up = 0
    for _ in range(n_boot):
        bank = 10000.0
        for _ in range(50):
            won, odd = sel[random.randrange(n)]
            bank -= 100.0
            if won:
                bank += 100.0 * odd
        if bank > 10000.0:
            up += 1
    return 100.0 * up / n_boot


print("Clay   n=%d  P(rost)=%.1f%%" % (len(clay), p_up(clay)))
print("NE-Clay n=%d P(rost)=%.1f%%" % (len(nonclay), p_up(nonclay)))