#!/usr/bin/env python3
"""Sonda 14: trh-only strategie PRIMO z kurzy CSV (bez Sackmann joinu).

MOTIVACE
Kurzy CSV (tenis/kurzy/wta_kurzy.csv) obsahuje samotny sloupec `Round`
("1st Round", "2nd Round", ...), `Surface`, `Tournament`, `Date`,
`Best of`, `Rank_1`, `Rank_2`, `Odd_1`, `Odd_2`, `Winner`. Pro trh-only
strategie (bez modelu) NEPOTREBUJEME Sackmann join - muzeme testovat
primo na kurzech, coz je rychlejsi, nezávislé na fuzzy matchingu jmen
a vetsi (11730 radku).

CIL
1) Zreplikovat nalez "2. kolo trh-only favorit, kurz<=1.15, ROI +5.95 %"
   PRIMO z kurzy CSV - ma-li sonda pravdu, cisla musi sedet.
2) Zjistit, jestli existuji DALSI zive-odvoditelne filtry, ktere drzi:
   - Best of (5 = grand slam muzi / GS zeny? u WTA vzdy 3, takze ne)
   - Rank gap (favorit rank vyrazne lepsi nez underdog)
   - Tournament-level proxy pres pocet hracu / jmeno turnaje
3) OOS split po letech + bootstrap CI + permutacni p.

Vse FLAT vklad 100, banka start 10000.

Spusteni: python3 _probe_round_direct.py
"""
import csv
import os
import random
import re
from collections import Counter, defaultdict

BASE = "/root/statistiky"
ODDS_PATH = os.path.join(BASE, "tenis", "kurzy", "wta_kurzy.csv")

ODDS_MIN, ODDS_MAX = 1.01, 30.0


def load_rows():
    rows = []
    with open(ODDS_PATH, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                o1 = float(r.get("Odd_1") or 0)
                o2 = float(r.get("Odd_2") or 0)
                date = r.get("Date") or ""
                year = int(date[:4]) if date[:4].isdigit() else None
            except ValueError:
                continue
            if not (ODDS_MIN <= o1 <= ODDS_MAX and ODDS_MIN <= o2 <= ODDS_MAX):
                continue
            if not year:
                continue
            rnd = (r.get("Round") or "").strip()
            surf = (r.get("Surface") or "").strip().lower()
            best_of = (r.get("Best of") or "").strip()
            tour = (r.get("Tournament") or "").strip()
            winner = (r.get("Winner") or "").strip()
            if not winner:
                continue
            if o1 <= o2:
                fav_odd, fav_side, fav_won = o1, 1, winner == (r.get("Player_1") or "").strip()
            else:
                fav_odd, fav_side, fav_won = o2, 2, winner == (r.get("Player_2") or "").strip()
            try:
                rank1 = int(r.get("Rank_1") or 0)
                rank2 = int(r.get("Rank_2") or 0)
            except ValueError:
                rank1 = rank2 = 0
            fav_rank = rank1 if fav_side == 1 else rank2
            und_rank = rank2 if fav_side == 1 else rank1
            rows.append({
                "year": year, "round": rnd, "surface": surf, "best_of": best_of,
                "tourney": tour, "fav_odd": fav_odd, "fav_won": fav_won,
                "fav_rank": fav_rank, "und_rank": und_rank,
            })
    return rows


# round label -> ordinal (1-based poradi kola)
def round_ordinal(rnd):
    r = rnd.strip().lower()
    m = re.match(r"^(\d+)(?:st|nd|rd|th)\s+round", r)
    if m:
        return int(m.group(1))
    if "qualif" in r:
        return 0
    if "round robin" in r:
        return None
    if "quarter" in r:
        return 90  # kvartfinaly = ordinal >= 5, ale neni to fixni cislo
    if "semi" in r:
        return 91
    if r == "final" or "final" in r and "qual" not in r:
        return 92
    return None


def stats(sel):
    n = len(sel)
    if n == 0:
        return 0, 0.0, 0.0
    w = sum(1 for s in sel if s["fav_won"])
    staked = 100.0 * n
    ret = sum(100.0 * s["fav_odd"] for s in sel if s["fav_won"])
    return n, 100.0 * w / n, (ret - staked) / staked * 100.0


def p_up(sel, n_boot=4000, n_ticket=50, stake=100.0, start=10000.0, seed=7):
    if len(sel) < 15:
        return None
    random.seed(seed)
    n = len(sel)
    up = 0
    for _ in range(n_boot):
        bank = start
        for _ in range(n_ticket):
            s = sel[random.randrange(n)]
            bank -= stake
            if s["fav_won"]:
                bank += stake * s["fav_odd"]
        if bank > start:
            up += 1
    return 100.0 * up / n_boot


def boot_ci(sel, n_boot=4000, seed=11):
    if len(sel) < 15:
        return None
    random.seed(seed)
    n = len(sel)
    rois = []
    for _ in range(n_boot):
        s = [sel[random.randrange(n)] for _ in range(n)]
        staked = 100.0 * len(s)
        ret = sum(100.0 * x["fav_odd"] for x in s if x["fav_won"])
        rois.append((ret - staked) / staked * 100.0)
    rois.sort()
    return rois[int(0.025 * n_boot)], rois[int(0.975 * n_boot)]


def perm_p(sel, pool, n_perm=4000, seed=13):
    if len(sel) < 15 or len(pool) < len(sel):
        return None
    random.seed(seed)
    n = len(sel)
    st = 100.0 * n
    obs = (sum(100.0 * x["fav_odd"] for x in sel if x["fav_won"]) - st) / st
    ge = 0
    for _ in range(n_perm):
        s = [pool[random.randrange(len(pool))] for _ in range(n)]
        st = 100.0 * n
        if (sum(100.0 * x["fav_odd"] for x in s if x["fav_won"]) - st) / st >= obs:
            ge += 1
    return ge / n_perm


def report(label, cand, pool, years):
    n, usp, roi = stats(cand)
    if n == 0:
        print(f"{label:55s} n=0")
        return
    pu = p_up(cand)
    ci = boot_ci(cand)
    pp = perm_p(cand, pool)
    print(f"{label:55s} n={n:4d} usp={usp:5.1f}% ROI={roi:+6.2f}% "
          f"P50={('%5.1f%%' % pu) if pu is not None else '  n/a'}"
          f"{('  CI[%+.1f,%+.1f]' % ci) if ci else ''}"
          f"{('  p=%.3f' % pp) if pp is not None else ''}")


def main():
    rows = load_rows()
    print(f"nacteno {len(rows)} zapasu s kurzy (WTA)")
    print(f"roky: {sorted(set(r['year'] for r in rows))}")
    print(f"kola (top): {Counter(r['round'] for r in rows).most_common(8)}")
    print(f"povrchy: {Counter(r['surface'] for r in rows)}")
    print(f"best of: {Counter(r['best_of'] for r in rows)}")
    print()

    years = sorted(set(r["year"] for r in rows))
    mid = years[len(years) // 2]

    print("=" * 100)
    print("A) ZREPLIKOVANI NALEZU: trh-only favorit, kurz<=1.15, podle poradi kola")
    print("=" * 100)
    for cap in (1.10, 1.15, 1.20):
        pool = [r for r in rows if r["fav_odd"] <= cap]
        for ordi in (1, 2, 3, 4):
            cand = [r for r in pool if round_ordinal(r["round"]) == ordi]
            report(f"cap<={cap} ordinal=={ordi}", cand, pool, years)

    print()
    print("=" * 100)
    print("B) OOS + rok pro nejlepsi kandidaty (ordinal==2, cap<=1.15)")
    print("=" * 100)
    pool = [r for r in rows if r["fav_odd"] <= 1.15]
    cand = [r for r in pool if round_ordinal(r["round"]) == 2]
    n, usp, roi = stats(cand)
    print(f"cele: n={n} usp={usp:.1f}% ROI={roi:+.2f}%")
    for lab, cond in (("1.pol", lambda r: r["year"] < mid),
                      ("2.pol", lambda r: r["year"] >= mid)):
        s = [r for r in cand if cond(r)]
        nn, uu, rr = stats(s)
        print(f"  {lab}: n={nn} usp={uu:.1f}% ROI={rr:+.2f}%")
    for y in years:
        s = [r for r in cand if r["year"] == y]
        nn, uu, rr = stats(s)
        print(f"  {y}: n={nn} usp={uu:.1f}% ROI={rr:+.2f}%")

    print()
    print("=" * 100)
    print("C) DALSI ZIVE-ODVODITELNE FILTRY na ordinal==2, cap<=1.15")
    print("=" * 100)
    base2 = cand
    for surf in ("clay", "hard", "grass", "carpet"):
        s = [r for r in base2 if r["surface"] == surf]
        report(f"ordinal==2, {surf}", s, pool, years)
    # rank gap: favorit rank <= 20 a underdog rank >= 50
    s = [r for r in base2 if 0 < r["fav_rank"] <= 20 and r["und_rank"] >= 50]
    report("ordinal==2, fav_rank<=20 & und_rank>=50", s, pool, years)
    s = [r for r in base2 if 0 < r["fav_rank"] <= 10]
    report("ordinal==2, fav_rank<=10", s, pool, years)
    s = [r for r in base2 if 0 < r["fav_rank"] <= 30 and r["und_rank"] >= 30]
    report("ordinal==2, fav_rank<=30 & und_rank>=30", s, pool, years)
    s = [r for r in base2 if r["fav_rank"] >= 60 and r["und_rank"] >= 60]
    report("ordinal==2, oba ranky >=60 (male turnaje)", s, pool, years)
    s = [r for r in base2 if r["fav_rank"] <= 40 and r["und_rank"] <= 40]
    report("ordinal==2, oba ranky <=40 (velke turnaje)", s, pool, years)

    print()
    print("=" * 100)
    print("D) DVOJITY FILTR: ordinal in (2) a povrch, ale pro vsechny capy")
    print("=" * 100)
    for cap in (1.15, 1.20, 1.30):
        pool2 = [r for r in rows if r["fav_odd"] <= cap]
        for surf in ("clay", "hard"):
            s = [r for r in pool2 if round_ordinal(r["round"]) == 2
                 and r["surface"] == surf]
            report(f"cap<={cap} ordinal==2 & {surf}", s, pool2, years)


if __name__ == "__main__":
    main()