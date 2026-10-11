#!/usr/bin/env python3
"""Sonda 10: ktere ROUND_CODE segmenty jsou ZIVE odvoditelne A profitabilni?

Nalez z deniku: "2. kolo" favorit ma ROI +3.6 %, ale poradi kola nejde zive
odvodit (chybi draw_size). QF/SF/F maji ale FIXNI round_code bez ohledu na
velikost pavouka -> jsou zive odvoditelne PRIMO.

Tato sonda testuje TRH-ONLY favorita (bez modelu) po segmentech round_code
(1R/2R/3R/4R/QF/SF/F) s ruznymi kurzovymi capy, vc. OOS splitu.

Klicove cisla: ROI, uspesnost, P(rost banky po 50 tiketech).
Vklady FLAT 100, kurzovy cap dle varianty.

Spusteni: python3 _probe_round_code_segments.py
"""
import csv
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

sack = tv.load_sackmann_wta()
with open(tv.ODDS_PATH, encoding="utf-8") as f:
    odds_rows = list(csv.DictReader(f))
joined = tv.join_matches(sack, odds_rows)
print("spojenych zapasu:", len(joined))


def to_code(rnd):
    r = (rnd or "").strip().lower()
    if r.startswith("r") and r[1:].isdigit():
        return "R" + r[1:]
    if "quarter" in r:
        return "QF"
    if "semi" in r:
        return "SF"
    if r == "f" or "final" in r:
        return "F"
    if "round robin" in r:
        return "RR"
    return "?"


rows = []
for m in joined:
    o1, o2 = m["odd1"], m["odd2"]
    if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
        continue
    if o1 <= o2:
        fav_odd, fav_won = o1, m["p1_won"]
    else:
        fav_odd, fav_won = o2, not m["p1_won"]
    rows.append((int(str(m["cutoff"])[:4]), to_code(m.get("round")),
                 (m.get("surface") or "").lower(), fav_won, fav_odd))

years = sorted(set(r[0] for r in rows))
mid = years[len(years) // 2]
print("celkem:", len(rows), "roky:", years, "delic:", mid)


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


for CAP in (1.15, 1.20, 1.25):
    cand = [r for r in rows if r[4] <= CAP]
    print(f"\n=== trh-only favorit, kurz<={CAP}, podle round_code ===")
    print("%-6s %6s %9s %9s %9s %9s %9s" % ("code", "n", "uspes", "ROI",
                                            "P(50)", "ROI1", "ROI2"))
    for code in ("R128", "R64", "R32", "R16", "QF", "SF", "F", "RR"):
        sel = [(r[3], r[4]) for r in cand if r[1] == code]
        n, w, roi = stats(sel)
        u = p_up(sel)
        s1 = [(r[3], r[4]) for r in cand if r[1] == code and r[0] < mid]
        s2 = [(r[3], r[4]) for r in cand if r[1] == code and r[0] >= mid]
        _, _, roi1 = stats(s1)
        _, _, roi2 = stats(s2)
        print("%-6s %6d %8.1f%% %+8.1f%% %9s %+8.1f%% %+8.1f%%" % (
            code, n, w, roi, "%.0f%%" % u if u is not None else "-", roi1, roi2))

# Kombinace zive odvoditelnych "pozdnich kol"
for CAP in (1.15, 1.20):
    cand = [r for r in rows if r[4] <= CAP]
    for label, codes in (("QF+SF+F", {"QF", "SF", "F"}),
                         ("R16+QF+SF+F", {"R16", "QF", "SF", "F"}),
                         ("SF+F", {"SF", "F"})):
        sel = [(r[3], r[4]) for r in cand if r[1] in codes]
        n, w, roi = stats(sel)
        u = p_up(sel)
        print(f"[cap {CAP}] {label}: n={n} uspes={w:.1f}% ROI={roi:+.1f}% "
              f"P(50)={'%.0f%%' % u if u is not None else '-'}")