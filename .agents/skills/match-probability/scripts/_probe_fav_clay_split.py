#!/usr/bin/env python3
"""Sonda 7: rozbiti segmentu Clay/kurz<=1.15 na dve nahodne poloviny
+ kontrola turnaju, aby se vyloucilo, ze efekt dela par turnaju.

Spusteni: python3 _probe_fav_clay_split.py
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
                 fav_won, fav_odd, m.get("tourney") or "?"))

clay = [r for r in rows if "clay" in r[1] and r[3] <= 1.15]
print("clay cap1.15 celkem:", len(clay))


def stats(sel):
    n = len(sel)
    if n == 0:
        return n, 0.0, 0.0
    w = sum(1 for r in sel if r[2])
    staked = 100.0 * n
    ret = sum(100.0 * r[3] for r in sel if r[2])
    return n, 100.0 * w / n, (ret - staked) / staked * 100.0


random.seed(99)
idx = list(range(len(clay)))
random.shuffle(idx)
half = len(idx) // 2
a = [clay[i] for i in idx[:half]]
b = [clay[i] for i in idx[half:]]
print("\n=== nahodne poloviny ===")
for lab, s in (("A", a), ("B", b)):
    n, w, roi = stats(s)
    print("  %s  n=%3d  uspes=%.1f%%  ROI=%+.1f%%" % (lab, n, w, roi))

print("\n=== podle turnaje (jen turnaje s n>=8) ===")
byt = defaultdict(list)
for r in clay:
    byt[r[4]].append(r)
print("%-32s %4s %8s %8s" % ("turnaj", "n", "uspes", "ROI"))
for t in sorted(byt, key=lambda k: -len(byt[k])):
    s = byt[t]
    n, w, roi = stats(s)
    if n < 8:
        continue
    print("%-32s %4d %7.1f%% %+7.1f%%" % (t[:32], n, w, roi))

print("\n=== podle roku ===")
for y in sorted(set(r[0] for r in clay)):
    n, w, roi = stats([r for r in clay if r[0] == y])
    print("  %d  n=%3d  uspes=%.1f%%  ROI=%+.1f%%" % (y, n, w, roi))