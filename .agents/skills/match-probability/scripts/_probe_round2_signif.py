#!/usr/bin/env python3
"""Sonda 10: je edge "2nd round, trh-only favorit" statisticky realny?

Kontext: _probe_round2_oos.py nasel u 2. kola (kurz<=1.20, n=619):
  uspesnost 89.3 %, ROI +1.3 %, P(rost50)=61 %;
pri cap<=1.15 (n=370): 93.8 %, ROI +3.6 %, P(50)=80 %.
Pozor - testovali jsme HODNE rezu (kola x povrchy x capy), takze cast
"nejlepsiho segmentu" muze byt mnohonasobne srovnani (overfitting).

Tato sonda proto dela:
  1. bootstrap 95% CI pro ROI u 2nd/cap1.15 a 2nd/cap1.20
  2. permutacni test: jak casto nahodny vyber stejne velikosti (z celeho
     souboru favoritu) da ROI >= pozorovane? (= p-hodnota)
  3. kontrola mnohonasobneho srovnani: rozdeleni ROI nahodnych rezu
  4. reprodukce: 2nd-round efekt podle jinych rezu (clay/ne-clay, roky)

Spusteni: python3 _probe_round2_signif.py
"""
import sys, csv, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

sack = tv.load_sackmann_wta()
with open(tv.ODDS_PATH, encoding="utf-8") as f:
    odds_rows = list(csv.DictReader(f))
joined = tv.join_matches(sack, odds_rows)

rows = []
for m in joined:
    o1, o2 = m["odd1"], m["odd2"]
    if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
        continue
    if o1 <= o2:
        fav_odd, fav_won = o1, m["p1_won"]
    else:
        fav_odd, fav_won = o2, not m["p1_won"]
    rows.append({"year": int(str(m["cutoff"])[:4]),
                 "surface": (m.get("surface") or "").lower(),
                 "round": (m.get("round") or ""),
                 "won": fav_won, "odd": fav_odd})


def is_2nd(r):
    return "2nd" in r["round"].lower()


def roi(sel):
    n = len(sel)
    if n == 0:
        return 0.0
    staked = 100.0 * n
    ret = sum(100.0 * r["odd"] for r in sel if r["won"])
    return (ret - staked) / staked * 100.0


def success(sel):
    n = len(sel)
    return 100.0 * sum(1 for r in sel if r["won"]) / n if n else 0.0


def boot_ci(sel, n_boot=10000, seed=1):
    random.seed(seed)
    n = len(sel)
    out = []
    for _ in range(n_boot):
        s = [sel[random.randrange(n)] for _ in range(n)]
        out.append(roi(s))
    out.sort()
    return out[int(0.025 * n_boot)], out[int(0.975 * n_boot)]


def perm_p(sel, pool, n_iter=20000, seed=2):
    random.seed(seed)
    n = len(sel)
    obs = roi(sel)
    ge = 0
    for _ in range(n_iter):
        s = [pool[random.randrange(len(pool))] for _ in range(n)]
        if roi(s) >= obs:
            ge += 1
    return obs, 100.0 * ge / n_iter


pool = [r for r in rows if r["odd"] <= 1.20]
print("pool favoritu kurz<=1.20:", len(pool), " ROI celeho poolu: %+.2f%%" % roi(pool))

print("\n=== 1) bootstrap 95%% CI ROI ===")
for cap, label in ((1.15, "2nd, cap<=1.15"), (1.20, "2nd, cap<=1.20")):
    sel = [r for r in pool if r["odd"] <= cap and is_2nd(r)]
    lo, hi = boot_ci(sel)
    print("%-16s n=%4d  uspes=%.1f%%  ROI=%+.2f%%  CI95=[%+.2f%%, %+.2f%%]"
          % (label, len(sel), success(sel), roi(sel), lo, hi))

print("\n=== 2) permutacni p-hodnota (vyber z poolu kurz<=1.20) ===")
for cap, label in ((1.15, "2nd, cap<=1.15"), (1.20, "2nd, cap<=1.20")):
    sel = [r for r in pool if r["odd"] <= cap and is_2nd(r)]
    obs, p = perm_p(sel, pool)
    print("%-16s ROI=%+.2f%%  p(ROI>=obs)=%.3f" % (label, obs, p / 100.0))

print("\n=== 3) kontrola mnohonasobneho srovnani ===")
random.seed(3)
sel2 = [r for r in pool if is_2nd(r)]
n_slice = len(sel2)
better = 0
rois = []
for _ in range(5000):
    s = [pool[random.randrange(len(pool))] for _ in range(n_slice)]
    v = roi(s)
    rois.append(v)
    if v >= roi(sel2):
        better += 1
rois.sort()
print("2nd cap1.20: n=%d ROI=%+.2f%%" % (n_slice, roi(sel2)))
print("nahodne rezy n=%d: median ROI=%+.2f%%, p95=%+.2f%%"
      % (n_slice, rois[2500], rois[4750]))
print("podil nahodnych rezu s ROI >= pozorovane: %.1f%%" % (100.0 * better / 5000))

print("\n=== 4) rezy 2nd cap1.20 podle povrchu a roku ===")
sel2b = [r for r in pool if r["odd"] <= 1.20 and is_2nd(r)]
for lab, cond in (("clay", lambda r: "clay" in r["surface"]),
                  ("ne-clay", lambda r: "clay" not in r["surface"])):
    s = [r for r in sel2b if cond(r)]
    print("  %-8s n=%4d uspes=%.1f%% ROI=%+.2f%%" % (lab, len(s), success(s), roi(s)))
for y in sorted(set(r["year"] for r in sel2b)):
    s = [r for r in sel2b if r["year"] == y]
    print("  %-8d n=%4d uspes=%.1f%% ROI=%+.2f%%" % (y, len(s), success(s), roi(s)))