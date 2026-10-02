#!/usr/bin/env python3
"""Sonda 4: Monte Carlo banka po N tiketech pro různé strategie.

Cíl není ROI, ale PODÍL ROSTOUCÍCH BANK po 50 tiketech.
Porovnává několik strategií výběru favorita:
  A) kurz<=1.60 (baseline match_fav)
  B) kurz<=1.15
  C) kurz<=1.10
  D) kurz<=1.15 AND povrch=Clay
  E) kurz<=1.15 AND kolo=2nd Round
  F) kurz<=1.20 AND kurz>1.10  (pásmo 1.10-1.15)

Pro každou strategii se bootstrapem (10k vzorků, výběr 50 sázek s opakováním)
spočítá: P(banka > start), medián ROI, 5./95. percentil.

Vklady jsou FLAT (100 mincí), start 10 000 -> poměr platí i pro % vklad.

Spusteni: python3 _probe_fav_bank.py
"""
import sys, csv, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

sack = tv.load_sackmann_wta()
with open(tv.ODDS_PATH, encoding="utf-8") as f:
    odds_rows = list(csv.DictReader(f))
joined = tv.join_matches(sack, odds_rows)
hist = tv.History(sack)

MIN_HIST = 15

# strategie -> seznam (won, odds)
strategie = {
    "A kurz<=1.60": [],
    "B kurz<=1.15": [],
    "C kurz<=1.10": [],
    "D kurz<=1.15 Clay": [],
    "E kurz<=1.15 2ndRound": [],
    "F 1.10<kurz<=1.15": [],
    "G kurz<=1.15 noModel": [],
}

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
    surf = (m.get("surface") or "").lower()
    rnd = (m.get("round") or "").lower()

    if fav_odd <= 1.60:
        strategie["A kurz<=1.60"].append((fav_won, fav_odd))
    if fav_odd <= 1.15:
        strategie["B kurz<=1.15"].append((fav_won, fav_odd))
        strategie["G kurz<=1.15 noModel"].append((fav_won, fav_odd))
        if "clay" in surf:
            strategie["D kurz<=1.15 Clay"].append((fav_won, fav_odd))
        if "2nd" in rnd:
            strategie["E kurz<=1.15 2ndRound"].append((fav_won, fav_odd))
    if fav_odd <= 1.10:
        strategie["C kurz<=1.10"].append((fav_won, fav_odd))
    if 1.10 < fav_odd <= 1.15:
        strategie["F 1.10<kurz<=1.15"].append((fav_won, fav_odd))

random.seed(42)
N_BOOT = 10000
N_TICKET = 50
STAKE = 100.0
START = 10000.0

print("%-24s %7s %8s %8s %8s %8s" % ("strategie", "sazek", "uspes", "P(rost)", "median", "5%"))
print("-" * 70)
for name, bets in strategie.items():
    if len(bets) < 20:
        print("%-24s %7d   (malo)" % (name, len(bets)))
        continue
    n = len(bets)
    wins = sum(1 for w, _ in bets if w)
    up = 0
    ros = []
    for _ in range(N_BOOT):
        bank = START
        for _ in range(N_TICKET):
            won, odd = bets[random.randrange(n)]
            bank -= STAKE
            if won:
                bank += STAKE * odd
        ro = (bank - START) / START * 100.0
        ros.append(ro)
        if bank > START:
            up += 1
    ros.sort()
    print("%-24s %7d %7.1f%% %7.1f%% %+7.1f%% %+7.1f%%" % (
        name, n, 100.0 * wins / n, 100.0 * up / N_BOOT,
        ros[N_BOOT // 2], ros[int(N_BOOT * 0.05)]))