#!/usr/bin/env python3
"""Sonda 11: LZE "2. kolo" favorita nasadit ZIVE?

Denik: "2. kolo" trh-only favorit (cap<=1.15) ma ROI +3.6 %, P(rost50)=80 %.
Problem: Live API nema poradi kola. Ale Sackmann ma draw_size.

Postup:
  1) Ze Sackmann dat spocitej PRAVE poradi kola z draw_size + round.
  2) Baseline: trh-only favorit, cap<=1.15, ordinal==2 -> ROI (overeno drive).
  3) Zive simulovany vyber: uhadni draw_size z tier (pevna tabulka),
     spocitej ordinal z round_code, vyber ordinal==2.
  4) Zmer, jak moc se zivy vyber prekryva s pravdivym a jake ma ROI.
     Kdyz je ROI kladne a prekryv vysoký -> strategie je nasaditelna.

Tabulka draw_size podle tier (z Live API tieru):
  grand_slam=128, wta_1000=56, wta_500=32, wta_250=32, wta_125=32,
  challenger=32, itf=32
(Sackmann tourney_level: G=grand slam, PM=premier mandatory, P=premier,
 I=international, W=wta125, O=olympics, F=fed cup, D=?)

Spusteni: python3 _probe_round2_live.py
"""
import csv
import math
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

BASE = "/root/statistiky"


def sack_round_ordinal(draw_size, rnd):
    """Poradi kola z draw_size + Sackmann round stringu (1R,2R,QF,...)."""
    r = (rnd or "").strip().lower()
    if "quarter" in r:
        return math.log2(draw_size) - 3 + 1
    if "semi" in r:
        return math.log2(draw_size) - 2 + 1
    if r == "f" or "final" in r:
        return math.log2(draw_size) - 1 + 1
    if "round robin" in r:
        return None
    m = re.match(r"^r(\d+)$", r)
    if m:
        return int(m.group(1))
    return None


# Nacti Sackmann s draw_size
sack = {}
for path in sorted(__import__("glob").glob(os.path.join(BASE, "tenis", "wta_matches_*.csv"))):
    with open(path, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            ds = r.get("draw_size")
            try:
                ds = int(ds)
            except (TypeError, ValueError):
                continue
            key = (tv.sackmann_key(r.get("winner_name") or ""),
                   tv.sackmann_key(r.get("loser_name") or ""),
                   int(r.get("tourney_date") or 0))
            sack[key] = (ds, r.get("round"), r.get("tourney_level"))

with open(tv.ODDS_PATH, encoding="utf-8") as f:
    odds_rows = list(csv.DictReader(f))
joined = tv.join_matches(tv.load_sackmann_wta(), odds_rows)
print("spojenych:", len(joined))

# round_code -> cislo (jako Live API)
def code_num(rc):
    if not rc:
        return None
    rc = rc.strip().upper()
    m = re.match(r"^R(\d+)$", rc)
    if m:
        return int(m.group(1))
    return {"QF": 8, "SF": 4, "F": 2}.get(rc)


# tier -> odhad draw_size (z Live API tieru)
TIER_DRAW = {
    "grand_slam": 128, "wta_1000": 56, "wta_500": 32, "wta_250": 32,
    "wta_125": 32, "challenger_125": 32, "challenger_75": 32,
    "itf_w15": 32, "itf_m15": 32, "itf_w50": 32, "itf_m25": 32,
}

# tourney_level (Sackmann) -> odhad tieru (jen pro zivy odhad draw_size)
LEVEL_TIER = {
    "G": "grand_slam", "PM": "wta_1000", "P": "wta_500", "I": "wta_250",
    "W": "wta_125", "O": "wta_500", "F": "wta_500", "D": "wta_500",
}

rows = []  # (rok, level, round, fav_won, fav_odd, true_ordinal, est_ordinal)
for m in joined:
    o1, o2 = m["odd1"], m["odd2"]
    if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
        continue
    if o1 <= o2:
        fav_odd, fav_won = o1, m["p1_won"]
    else:
        fav_odd, fav_won = o2, not m["p1_won"]
    # najdi draw_size pro tento zapas
    key1 = (tv.sackmann_key(m["name1"]), tv.sackmann_key(m["name2"]), int(str(m["cutoff"])))
    key2 = (tv.sackmann_key(m["name2"]), tv.sackmann_key(m["name1"]), int(str(m["cutoff"])))
    ds_info = sack.get(key1) or sack.get(key2)
    if not ds_info:
        continue
    draw_size, round_str, level = ds_info
    true_o = sack_round_ordinal(draw_size, round_str)
    if true_o is None:
        continue
    # zivy odhad: round_code z round_str
    rc = None
    rs = (round_str or "").strip().lower()
    mm = re.match(r"^r(\d+)$", rs)
    if mm:
        rc = "R" + mm.group(1)
    elif "quarter" in rs:
        rc = "QF"
    elif "semi" in rs:
        rc = "SF"
    elif rs == "f" or "final" in rs:
        rc = "F"
    cn = code_num(rc)
    tier = LEVEL_TIER.get(level)
    est_draw = TIER_DRAW.get(tier) if tier else None
    est_o = None
    if cn and est_draw and est_draw >= cn:
        est_o = int(round(math.log2(est_draw) - math.log2(cn))) + 1
    rows.append((int(str(m["cutoff"])[:4]), level, rc, fav_won, fav_odd,
                 int(true_o), est_o))

print("radku s ordinal:", len(rows))


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


for CAP in (1.15, 1.20):
    cand = [r for r in rows if r[4] <= CAP]
    print(f"\n=== cap<={CAP} ===")
    # pravdivy 2. kolo
    true2 = [(r[3], r[4]) for r in cand if r[5] == 2]
    n, w, roi = stats(true2)
    print(f"PRAVDIVE 2. kolo: n={n} uspes={w:.1f}% ROI={roi:+.1f}% "
          f"P(50)={'%.0f%%' % p_up(true2) if p_up(true2) is not None else '-'}")
    # zivy odhad 2. kolo
    est2 = [(r[3], r[4]) for r in cand if r[6] == 2]
    n, w, roi = stats(est2)
    print(f"ZIVY odhad 2. kolo: n={n} uspes={w:.1f}% ROI={roi:+.1f}% "
          f"P(50)={'%.0f%%' % p_up(est2) if p_up(est2) is not None else '-'}")
    # prekryv
    tp = set(id(r) for r in cand if r[5] == 2)
    ep = set(id(r) for r in cand if r[6] == 2)
    inter = len(tp & ep)
    print(f"prekryv: pravda={len(tp)} odhad={len(ep)} prunik={inter} "
          f"({100.0*inter/max(1,len(tp)):.0f}% pravdy, "
          f"{100.0*inter/max(1,len(ep)):.0f}% odhadu)")

# Diagnostika: distribuce levelu a draw_size
from collections import Counter
print("\n=== distribuce: level -> (draw_size) ===")
lv = {}
for r in rows:
    lv.setdefault(r[1], Counter())[r[6]] += 1
for l in sorted(lv):
    print(f"  {l}: est_ordinal {dict(lv[l])}")

# Kolik pravdivych 2. kol ma est_ordinal 2 podle levelu?
print("\n=== pravda=2: rozdeleni levelu a est_ordinal ===")
lv2 = {}
for r in rows:
    if r[5] == 2:
        lv2.setdefault(r[1], Counter())[r[6]] += 1
for l in sorted(lv2):
    print(f"  {l}: est {dict(lv2[l])}")