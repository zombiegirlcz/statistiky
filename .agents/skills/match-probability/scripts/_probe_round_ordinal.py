#!/usr/bin/env python3
"""Sonda 9: lze ZIVĚ odvodit POŘADÍ KOLA z (tier, round_code)?

Denik 2026-10-07 nasel silny signal: "2. kolo" favorit (trh-only, kurz<=1.15)
ma ROI +3.6 %, P(rost50)=80 %. Problem: Live Tennis API vraci jen round_code
(R64/R32/R16/QF/SF/F), NE poradi kola. Poradi zavisi na velikosti pavouka.

Hypoteza: poradi_kola = log2(draw_size) - log2(round_code_num) + 1.

V Sackmannovych datech (wta_matches_*.csv) MAME draw_size i round, takze
overime:
  (a) jaky je typicky draw_size pro kazdou uroven turnaje (tier/level)
  (b) jak presne se z (tier, round_code) trefi poradi kola
  (c) kolik je urovni, kde je to nejednoznacne

Metrika: uspesnost mapovani (tier,round_code)->poradi na historickych datech.

Spusteni: python3 _probe_round_ordinal.py
"""
import csv
import glob
import os
import re
from collections import defaultdict, Counter

BASE = "/root/statistiky"


def round_code_num(rc):
    """R64->64, R32->32, R16->16, QF->8, SF->4, F->2, RR->None."""
    if not rc:
        return None
    rc = rc.strip().upper()
    m = re.match(r"^R(\d+)$", rc)
    if m:
        return int(m.group(1))
    return {"QF": 8, "SF": 4, "F": 2}.get(rc)


def sackmann_round_to_code(rnd):
    """Sackmann 'round' -> round_code jako v Live API."""
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
    return None


# ---------------------------------------------------------------------------
# 1) Nacti Sackmann data: (tourney_level, round_code, draw_size) pocetnosti
# ---------------------------------------------------------------------------
rows = []
for path in sorted(glob.glob(os.path.join(BASE, "tenis", "wta_matches_*.csv"))):
    with open(path, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            ds = r.get("draw_size")
            lvl = r.get("tourney_level")
            rc = sackmann_round_to_code(r.get("round"))
            if not ds or not lvl or not rc:
                continue
            try:
                ds = int(ds)
            except ValueError:
                continue
            rows.append((lvl, rc, ds))

print("celkem radku s draw_size+level+round:", len(rows))

# 2) draw_size per level
print("\n=== draw_size podle tourney_level (Sackmann) ===")
by_level = defaultdict(Counter)
for lvl, rc, ds in rows:
    by_level[lvl][ds] += 1
for lvl in sorted(by_level):
    top = by_level[lvl].most_common(6)
    print(f"  {lvl:>8}: " + ", ".join(f"{d}({c})" for d, c in top))

# 3) Overeni ordinal vzorce: log2(draw_size)-log2(code_num)+1
#    Spravne poradi (Sackmann round): 1R..4R, QF=5? Zalezi na pavouku.
#    Pouzijeme prave draw_size, at je ordinal konzistentni:
#    ordinal(draw, code) = log2(draw) - log2(code) + 1
import math


def ordinal(draw, code):
    cn = round_code_num(code)
    if not cn or draw < cn:
        return None
    return int(round(math.log2(draw) - math.log2(cn))) + 1


# Rozdeleni: pro kazdy (level, code) zjisti, jake ordinal dostaneme pro
# kazdou velikost pavouka - hledame, kde je (level, code) -> ordinal
# jednoznacne.
print("\n=== (level, code) -> ordinal(y) pres vsechny draw_size ===")
lc = defaultdict(set)
for lvl, rc, ds in rows:
    o = ordinal(ds, rc)
    if o is not None:
        lc[(lvl, rc)].add(o)

multi = 0
total = 0
for key in sorted(lc):
    total += 1
    if len(lc[key]) > 1:
        multi += 1
print(f"  (level,code) kombinaci: {total}, z toho viceznacnych: {multi}")

# 4) Presnost: pro dominantni draw_size per (level, code) spocitej ordinal
#    a srovnej s pravdivym ordinal z draw_size. (Jen kontrola konzistence.)
print("\n=== OVERENI: (level,code) -> odhad ordinal z dominantniho draw_size ===")
dom = {}
for lvl, rc, ds in rows:
    dom.setdefault((lvl, rc), Counter())[ds] += 1

hits = miss = skipped = 0
miss_detail = Counter()
for lvl, rc, ds in rows:
    true_o = ordinal(ds, rc)
    if true_o is None:
        skipped += 1
        continue
    dom_ds = dom[(lvl, rc)].most_common(1)[0][0]
    est_o = ordinal(dom_ds, rc)
    if est_o == true_o:
        hits += 1
    else:
        miss += 1
        miss_detail[(lvl, rc, ds, true_o, est_o)] += 1

print(f"  presne: {hits}, chybne: {miss}, preskoceno: {skipped}")
print(f"  presnost: {100.0*hits/max(1,hits+miss):.1f} %")
print("  nejcastejsi chyby (level, code, draw, true_o, est_o -> pocet):")
for (lvl, rc, ds, to, eo), c in miss_detail.most_common(12):
    print(f"    {lvl} {rc} draw={ds} true={to} est={eo} -> {c}")