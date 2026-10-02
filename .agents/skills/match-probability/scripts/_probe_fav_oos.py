#!/usr/bin/env python3
"""Sonda 5: OUT-OF-SAMPLE validace segmentu (Clay / 2nd Round) z sondy 4.

Sonda 4 nasla, ze u silnych favoritu (kurz<=1.15) ma segment
  Clay      P(rost banky po 50 tiketech) = 82 %
  2nd Round P(rost) = 77 %
oproti baseline (vsechny povrchy/kola) 42 %.

To muze byt overfitting. Tady rozdelime data na dve poloviny podle roku
(podle data zapasu) a kazdou strategii vyhodnotime na OBOU zvlast.
Segment, ktery funguje v obou polovinach, ma sanci byt realny.

Spusteni: python3 _probe_fav_oos.py
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

# sesbirej vsechny kandidaty s rokem
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
    if fav_odd > 1.15:
        continue
    year = int(str(m["cutoff"])[:4])
    rows.append((year, fav_won, fav_odd,
                 (m.get("surface") or "").lower(),
                 (m.get("round") or "").lower()))

years = sorted(set(r[0] for r in rows))
print("roky:", years)
mid = years[len(years) // 2]
print("delici rok:", mid, "(prvni pol. < %d, druha >= %d)" % (mid, mid))


def evaluate(sel, label):
    """sel = seznam (won, odd); spocti P(rost) bootstrapem."""
    if len(sel) < 25:
        print("  %-22s %5d   (malo)" % (label, len(sel)))
        return
    n = len(sel)
    wins = sum(1 for w, _ in sel if w)
    up = 0
    ros = []
    for _ in range(5000):
        bank = 10000.0
        for _ in range(50):
            won, odd = sel[random.randrange(n)]
            bank -= 100.0
            if won:
                bank += 100.0 * odd
        ro = (bank - 10000.0) / 100.0
        ros.append(ro)
        if bank > 10000.0:
            up += 1
    ros.sort()
    print("  %-22s %5d %6.1f%% %7.1f%% %+7.1f%%" % (
        label, n, 100.0 * wins / n, 100.0 * up / 5000.0, ros[2500]))


random.seed(7)
for part, cond in (("PRVNI polovina", lambda y: y < mid),
                   ("DRUHA polovina", lambda y: y >= mid)):
    print("\n=== %s ===" % part)
    sub = [r for r in rows if cond(r[0])]
    evaluate([(r[1], r[2]) for r in sub], "VSECHNY (baseline)")
    evaluate([(r[1], r[2]) for r in sub if "clay" in r[3]], "Clay")
    evaluate([(r[1], r[2]) for r in sub if "hard" in r[3]], "Hard")
    evaluate([(r[1], r[2]) for r in sub if "grass" in r[3]], "Grass")
    evaluate([(r[1], r[2]) for r in sub if "2nd" in r[4]], "2nd Round")
    evaluate([(r[1], r[2]) for r in sub if "1st" in r[4]], "1st Round")
    evaluate([(r[1], r[2]) for r in sub if "clay" in r[3] or "2nd" in r[4]], "Clay NEBO 2nd")