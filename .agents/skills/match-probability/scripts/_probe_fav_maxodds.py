#!/usr/bin/env python3
"""Sonda: jak presne dopadá ŽIVÁ strategie "silný favorit" na historických
datech, a jak citlivá je na MAX kurz (FAV_MAX_ODDS) a na povrch.

Motivace: probe_fav_segments ukázal, že při kurzu <=1.20 má antuka ROI +0.9 %,
2. kolo +1.2 %, kurz <=1.15 +1.1 %, ale Hard -3.2 %, Grass -4.1 %.
Živá strategie ale používá FAV_MAX_ODDS=1.60 -> sází i do pásma, kde je
ROI horší. Tahle sonda ověří:
  1) jak vypadá skutečná živá podmínka (model>=0.75 & trh>=0.65) na datech,
  2) co udělá zpřísnění max kurzu (1.15/1.20/1.30/1.40/1.60),
  3) co udělá navíc filtr na povrch (jen antuka).
Vše měřeno na dvou polovinách let (OOS) i celku.

Spusteni: python3 _probe_fav_maxodds.py
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

# nasbírej kandidáty, kteří projdou živou podmínkou (model i trh souhlasí)
rows = []
for m in joined:
    p1, n1, n2 = tv.model_prob(hist, m["name1"], m["name2"], m["cutoff"])
    if p1 is None or n1 < MIN_HIST or n2 < MIN_HIST:
        continue
    o1, o2 = m["odd1"], m["odd2"]
    if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
        continue
    pm1, pm2, _ = tv.devig(o1, o2)
    # strana 1
    cands = []
    if p1 >= MODEL_MIN and pm1 >= MARKET_MIN:
        cands.append((o1, m["p1_won"]))
    # strana 2
    if (1 - p1) >= MODEL_MIN and pm2 >= MARKET_MIN:
        cands.append((o2, not m["p1_won"]))
    if not cands:
        continue
    fav_odd, fav_won = cands[0]  # nemůže nastat obojí zároveň
    year = int(str(m["cutoff"])[:4])
    rows.append((year, fav_won, fav_odd, (m.get("surface") or "").lower()))

years = sorted(set(r[0] for r in rows))
mid = years[len(years) // 2]
print(f"Kandidátů projivších živou podmínkou: {len(rows)} (roky {years}, dělící {mid})")


def roi_and_up(sel, n_boot=4000):
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


def show(label, sel):
    r = roi_and_up(sel)
    if r is None:
        print("  %-30s %5d   (málo)" % (label, len(sel)))
        return
    n, win, roi, up = r
    print("  %-30s %5d  usp %5.1f%%  ROI %+6.1f%%  P(rost) %5.1f%%" % (label, n, win, roi, up))


random.seed(11)
for part, cond in (("CELEK", lambda y: True),
                   ("PRVNI pol.", lambda y: y < mid),
                   ("DRUHA pol.", lambda y: y >= mid)):
    sub = [r for r in rows if cond(r[0])]
    print(f"\n=== {part} (n={len(sub)}) ===")
    for cap in (1.15, 1.20, 1.30, 1.40, 1.60, 99.0):
        sel = [(w, o) for _, w, o, _ in sub if o <= cap]
        show(f"max kurz {cap:.2f}" if cap < 90 else "bez limitu kurzu", sel)
    print("  --- navíc filtr antuka (clay) ---")
    for cap in (1.30, 1.60, 99.0):
        sel = [(w, o) for _, w, o, s in sub if o <= cap and "clay" in s]
        show(f"clay, max kurz {cap:.2f}" if cap < 90 else "clay, bez limitu", sel)
    print("  --- ostatní povrchy pro srovnání (bez limitu) ---")
    for surf in ("hard", "grass"):
        sel = [(w, o) for _, w, o, s in sub if surf in s]
        show(surf, sel)