#!/usr/bin/env python3
"""Sonda: srovnání KANDIDÁTNÍCH strategií "favorit" na WTA datech, aby se
zjistilo, jestli má smysl měnit živou strategii. Měří se hlavní metrika
projektu = P(banka po 50 tiketech > start), ne jen ROI.

Kandidáti:
  A) ŽIVÁ  = model>=0.75 & trh>=0.65 & kurz<=1.60   (současná live strategie)
  B) trh-only favorit, kurz<=1.20
  C) trh-only favorit, kurz<=1.15
  D) trh-only favorit, kurz<=1.20, jen antuka
  E) trh-only favorit, kurz<=1.30, jen antuka
  F) ŽIVÁ + filtr antuka
  G) ŽIVÁ bez modelové podmínky (= trh-only), kurz<=1.30

Spusteni: python3 _probe_market_fav.py
"""
import sys, os, csv, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

sack = tv.load_sackmann_wta()
with open(tv.ODDS_PATH, encoding="utf-8") as f:
    odds_rows = list(csv.DictReader(f))
joined = tv.join_matches(sack, odds_rows)
hist = tv.History(sack)

MIN_HIST = 15
MODEL_MIN = 0.75
MARKET_MIN = 0.65

rows = []  # (year, fav_won, fav_odd, surface, model_ok)
for m in joined:
    p1, n1, n2 = tv.model_prob(hist, m["name1"], m["name2"], m["cutoff"])
    if p1 is None or n1 < MIN_HIST or n2 < MIN_HIST:
        continue
    o1, o2 = m["odd1"], m["odd2"]
    if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
        continue
    pm1, pm2, _ = tv.devig(o1, o2)
    if o1 <= o2:
        fav_odd, fav_won, p_model, p_mkt = o1, m["p1_won"], p1, pm1
    else:
        fav_odd, fav_won, p_model, p_mkt = o2, not m["p1_won"], 1 - p1, pm2
    model_ok = (p_model >= MODEL_MIN and p_mkt >= MARKET_MIN)
    year = int(str(m["cutoff"])[:4])
    rows.append((year, fav_won, fav_odd, (m.get("surface") or "").lower(), model_ok))

years = sorted(set(r[0] for r in rows))
mid = years[len(years) // 2]
print(f"Všech favoritů: {len(rows)} (roky {years}, dělící {mid})")


def stats(sel, n_boot=4000):
    if len(sel) < 25:
        return None
    n = len(sel)
    wins = sum(1 for w, _ in sel if w)
    staked = 100.0 * n
    ret = sum(100.0 * o for w, o in sel if w)
    roi = (ret - staked) / staked * 100.0
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
    return n, wins / n * 100.0, roi, up / n_boot * 100.0


CAND = {
    "A) ŽIVÁ model&trh o<=1.60": lambda r: r[4] and r[2] <= 1.60,
    "B) trh-only o<=1.20":        lambda r: r[2] <= 1.20,
    "C) trh-only o<=1.15":        lambda r: r[2] <= 1.15,
    "D) trh-only o<=1.20 clay":   lambda r: r[2] <= 1.20 and "clay" in r[3],
    "E) trh-only o<=1.30 clay":   lambda r: r[2] <= 1.30 and "clay" in r[3],
    "F) ŽIVÁ clay (o<=1.60)":     lambda r: r[4] and r[2] <= 1.60 and "clay" in r[3],
    "G) trh-only o<=1.30":        lambda r: r[2] <= 1.30,
}

random.seed(23)
for part, cond in (("CELEK", lambda y: True),
                   ("PRVNI pol.", lambda y: y < mid),
                   ("DRUHA pol.", lambda y: y >= mid)):
    sub = [r for r in rows if cond(r[0])]
    print(f"\n=== {part} (n={len(sub)}) ===")
    print("  %-30s %5s %8s %8s %9s" % ("kandidát", "n", "usp", "ROI", "P(rost)"))
    for label, pred in CAND.items():
        sel = [(r[1], r[2]) for r in sub if pred(r)]
        st = stats(sel)
        if st is None:
            print("  %-30s %5d   (málo)" % (label, len(sel)))
            continue
        n, win, roi, up = st
        print("  %-30s %5d %7.1f%% %+7.1f%% %8.1f%%" % (label, n, win, roi, up))
