#!/usr/bin/env python3
"""Sonda 9: je "2. kolo" robustni strategie? (navazani na _probe_round_market.py)

Predchozi nalez (2026-10-06): trh-only favorit, kurz<=1.20, 2. kolo turnaje
mel nejlepsi segment napric vsemi rezy:
  - 2nd round: n=619, 89.3 %, ROI +1.3 %, P(rost50)=61 %
  - 1st round: n=870, 87.5 %, ROI -1.1 %, P(50)=43 %
  - 3rd/4th:   n=229, 80.8 %, ROI -8.4 %, P(50)=8 %
A 2nd round drzelo na obou površích (clay +2.2 %, ne-clay +1.0 %).
Antuka sama (vsechna kola) mela jen +0.9 % (drivejsi nalez) - takze 2. kolo
muze byt SKUTECNY filtr, ne antuka.

POZOR na indexy: radek = (rok, povrch, kolo, turnaj, fav_won, fav_odd),
takze kurz je r[5], ne r[4]. (V _probe_round_market.py bylo bez turnaje.)

Overuje robustnost 2. kola:
  1. rok po roku  2. OOS split  3. citlivost na kurzovy cap 1.10..1.50
  4. 2nd x povrch  5. koncentrace podle turnaje  6. 2nd vs ostatni kola
  7. cap<=1.15/1.20 OOS detail

Vklady FLAT 100, start 10 000. Metrika P(rost50) = P(banka po 50 tiketech
> start), bootstrap 4000x, seed 7.

Spusteni: python3 _probe_round2_oos.py
"""
import sys, csv, os, random
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

sack = tv.load_sackmann_wta()
with open(tv.ODDS_PATH, encoding="utf-8") as f:
    odds_rows = list(csv.DictReader(f))
joined = tv.join_matches(sack, odds_rows)

# (rok, povrch, kolo, turnaj, fav_won, fav_odd)
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
                 (m.get("round") or ""), (m.get("tourney") or ""),
                 fav_won, fav_odd))

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


def line(label, sel):
    n, w, roi = stats(sel)
    u = p_up(sel)
    print("%-34s %6d %8.1f%% %+8.1f%% %9s" % (
        label, n, w, roi, "%.0f%%" % u if u is not None else "-"))


def bets(sel_rows):
    """z radku (fav_won, fav_odd) na seznam (won, odd)."""
    return [(r[4], r[5]) for r in sel_rows]


CAP = 1.20
cand2 = [r for r in rows if r[5] <= CAP and round_bucket(r[2]) == "2nd"]

print("\n=== 1) 2. kolo, cap %.2f, ROK PO ROKU ===" % CAP)
print("%-34s %6s %9s %9s %9s" % ("kandidat", "n", "uspes", "ROI", "P(50)"))
for y in years:
    line("2nd round %d" % y, bets([r for r in cand2 if r[0] == y]))

print("\n=== 2) 2. kolo, OOS split (prvni vs druha polovina let) ===")
print("%-34s %6s %9s %9s %9s" % ("kandidat", "n", "uspes", "ROI", "P(50)"))
line("2nd, prvni polovina", bets([r for r in cand2 if r[0] < mid]))
line("2nd, druha polovina", bets([r for r in cand2 if r[0] >= mid]))

print("\n=== 3) 2. kolo, citlivost na KURZOVY CAP ===")
print("%-34s %6s %9s %9s %9s" % ("kandidat", "n", "uspes", "ROI", "P(50)"))
for cap in (1.10, 1.15, 1.20, 1.25, 1.30, 1.40, 1.50):
    line("2nd, cap<=%.2f" % cap,
         bets([r for r in rows if r[5] <= cap and round_bucket(r[2]) == "2nd"]))

print("\n=== 4) 2. kolo x POVRCH (pridava antuka neco?) ===")
print("%-34s %6s %9s %9s %9s" % ("kandidat", "n", "uspes", "ROI", "P(50)"))
line("2nd, clay", bets([r for r in cand2 if "clay" in r[1]]))
line("2nd, ne-clay", bets([r for r in cand2 if "clay" not in r[1]]))
line("2nd, hard", bets([r for r in cand2 if "hard" in r[1]]))
line("2nd, grass", bets([r for r in cand2 if "grass" in r[1]]))

print("\n=== 5) 2. kolo podle TURNAJE (jen turnaje s n>=8) ===")
print("%-34s %6s %9s %9s %9s" % ("turnaj", "n", "uspes", "ROI", "P(50)"))
by_t = defaultdict(list)
for r in cand2:
    by_t[r[3]].append((r[4], r[5]))
for t, sel in sorted(by_t.items(), key=lambda kv: -len(kv[1])):
    if len(sel) >= 8:
        n, w, roi = stats(sel)
        print("%-34s %6d %8.1f%% %+8.1f%% %9s" % (t[:34], n, w, roi, "-"))

print("\n=== 6) KONTROLA: 2nd vs ostatni kola, cap %.2f ===" % CAP)
print("%-34s %6s %9s %9s %9s" % ("kandidat", "n", "uspes", "ROI", "P(50)"))
line("2nd round", bets(cand2))
for rnd in ("1st", "3rd/4th", "QF", "SF", "F"):
    line("%s round" % rnd,
         bets([r for r in rows if r[5] <= CAP and round_bucket(r[2]) == rnd]))

print("\n=== 7) 2. kolo: OOS detail pro cap<=1.15 a cap<=1.20 ===")
for cap in (1.15, 1.20):
    print("-- cap<=%.2f --" % cap)
    c = [r for r in rows if r[5] <= cap and round_bucket(r[2]) == "2nd"]
    line("  cele", bets(c))
    line("  prvni", bets([r for r in c if r[0] < mid]))
    line("  druha", bets([r for r in c if r[0] >= mid]))