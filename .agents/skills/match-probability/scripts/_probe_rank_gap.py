#!/usr/bin/env python3
"""Sonda: ranking-gap favorit (živě odvoditelný filtr).

MOTIVACE: 2026-10-07 deník našel, že "2. kolo" favorit (trh-only, kurz<=1.15)
má ROI +3.6 %, P(růst50)=80 %. ALE nejde nasadit živě, protože Live Tennis
API nevrací pořadí kola (jen round_code = R16/R32..., ne velikost pavouka).

Alternativa, která JE živě odvoditelná: Live API vrací players.p1.ranking
a players.p2.ranking. Sackmann CSV má winner_rank / loser_rank.

Otázka: existuje kombinace (kurz favorita, ranking-gap), která má kladné
ROI / vysoké P(růst50) a je robustní (rok po roku, OOS split)?

Spuštění: cd scripts && python3 _probe_rank_gap.py
"""
import sys, os, csv, glob, random
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

BASE = "/root/statistiky"


def load_sackmann_with_rank():
    rows = []
    for path in sorted(glob.glob(os.path.join(BASE, "tenis", "wta_matches_*.csv"))):
        with open(path, encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                w, l, d = r.get("winner_name"), r.get("loser_name"), r.get("tourney_date")
                if not (w and l and d):
                    continue
                try:
                    di = int(d)
                except ValueError:
                    continue
                wr = r.get("winner_rank") or ""
                lr = r.get("loser_rank") or ""
                try:
                    wr = int(wr)
                except (ValueError, TypeError):
                    wr = None
                try:
                    lr = int(lr)
                except (ValueError, TypeError):
                    lr = None
                rows.append({
                    "d": di, "w": w, "l": l,
                    "surface": r.get("surface", ""),
                    "tourney": r.get("tourney_name", ""),
                    "score": r.get("score", ""),
                    "best_of": r.get("best_of", "3"),
                    "wrank": wr, "lrank": lr,
                })
    rows.sort(key=lambda r: r["d"])
    return rows


def join_with_rank(sack_rows, odds_rows):
    """Vlastní obdoba tv.join_matches, ale přenáší i rankingy obou hráčů."""
    by_pair = defaultdict(list)
    for r in sack_rows:
        ka, kb = tv.sackmann_key(r["w"]), tv.sackmann_key(r["l"])
        if not ka or not kb:
            continue
        by_pair[tuple(sorted((ka, kb)))].append(r)

    out = []
    for o in odds_rows:
        k1, k2 = tv.odds_key(o["Player_1"]), tv.odds_key(o["Player_2"])
        if not k1 or not k2 or k1 == k2:
            continue
        cands = by_pair.get(tuple(sorted((k1, k2))))
        if not cands:
            continue
        md = tv.date_to_int(o["Date"])
        lo = tv.shift_days(md, -tv.WINDOW_AFTER_DAYS)
        hi = tv.shift_days(md, tv.WINDOW_BEFORE_DAYS)
        inwin = [c for c in cands if lo <= c["d"] <= hi]
        if not inwin:
            continue
        if len(inwin) > 1:
            inwin.sort(key=lambda c: abs(c["d"] - md))
            if abs(inwin[0]["d"] - md) == abs(inwin[1]["d"] - md):
                continue
        s = inwin[0]
        wk = tv.odds_key(o["Winner"])
        if wk == k1:
            p1_won = True
        elif wk == k2:
            p1_won = False
        else:
            continue
        sack_winner_key = tv.sackmann_key(s["w"])
        if (sack_winner_key == k1) != p1_won:
            continue
        # rank podle toho, kdo je kdo v odds datech (Player_1 = p1)
        if sack_winner_key == k1:
            rank1, rank2 = s["wrank"], s["lrank"]
        else:
            rank1, rank2 = s["lrank"], s["wrank"]
        out.append({
            "cutoff": s["d"],
            "name1": o["Player_1"], "name2": o["Player_2"],
            "p1_won": p1_won,
            "odd1": float(o["Odd_1"]), "odd2": float(o["Odd_2"]),
            "surface": s["surface"], "tourney": s["tourney"],
            "round": o.get("Round", ""),
            "rank1": rank1, "rank2": rank2,
        })
    return out


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
    print("%-38s %6d %8.1f%% %+8.1f%% %8s" % (
        label, n, w, roi, "%.0f%%" % u if u is not None else "-"))


def main():
    sack = load_sackmann_with_rank()
    with open(tv.ODDS_PATH, encoding="utf-8") as f:
        odds_rows = list(csv.DictReader(f))
    joined = join_with_rank(sack, odds_rows)
    print("spojeno zapasu:", len(joined))

    # sestav radky: favorit = nizsi kurz
    rows = []  # (rok, fav_won, fav_odd, fav_rank, dog_rank, surface)
    missing_rank = 0
    for m in joined:
        o1, o2 = m["odd1"], m["odd2"]
        if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
            continue
        if o1 <= o2:
            fav_won, fav_odd = m["p1_won"], o1
            fav_rank, dog_rank = m["rank1"], m["rank2"]
        else:
            fav_won, fav_odd = (not m["p1_won"]), o2
            fav_rank, dog_rank = m["rank2"], m["rank1"]
        if fav_rank is None:
            missing_rank += 1
            fav_rank = None
        rows.append((int(str(m["cutoff"])[:4]), fav_won, fav_odd,
                     fav_rank, dog_rank, (m.get("surface") or "").lower()))
    print("radku celkem:", len(rows), " bez ranku favorita:", missing_rank)

    years = sorted(set(r[0] for r in rows))
    mid = years[len(years) // 2]
    print("roky:", years, "delic:", mid)

    def sel(pred):
        return [(r[1], r[2]) for r in rows if pred(r)]

    print("\n=== 1) BASELINE: trh-only favorit, kurz<=1.20 ===")
    print("%-38s %6s %9s %9s %8s" % ("kandidat", "n", "uspes", "ROI", "P(50)"))
    line("vsechny (cap 1.20)", sel(lambda r: r[2] <= 1.20))
    line("  s rankem favorita", sel(lambda r: r[2] <= 1.20 and r[3] is not None))

    print("\n=== 2) RANKING FAVORITA (max cislo ranku = min kvalita) ===")
    for rk in (10, 20, 30, 50, 75, 100, 150):
        line("fav rank<=%d, cap<=1.20" % rk,
             sel(lambda r, rk=rk: r[2] <= 1.20 and r[3] is not None and r[3] <= rk))

    print("\n=== 3) RANKING-GAP: dog_rank / fav_rank >= X (favorit je rade niz) ===")
    for gap in (2, 3, 5, 8, 12, 20, 40):
        line("gap>=%d, cap<=1.20" % gap,
             sel(lambda r, g=gap: r[2] <= 1.20 and r[3] and r[4] and r[4] >= g * r[3]))

    print("\n=== 4) KOMBINACE: fav rank<=50 A gap>=5, cap<=1.20 ===")
    line("rank<=50 & gap>=5",
         sel(lambda r: r[2] <= 1.20 and r[3] is not None and r[3] <= 50
             and r[4] and r[4] >= 5 * r[3]))
    line("rank<=100 & gap>=5",
         sel(lambda r: r[2] <= 1.20 and r[3] is not None and r[3] <= 100
             and r[4] and r[4] >= 5 * r[3]))

    print("\n=== 5) RANKING-GAP a KURZ (gap>=5) ===")
    for cap in (1.10, 1.15, 1.20, 1.30, 1.40):
        line("gap>=5, cap<=%.2f" % cap,
             sel(lambda r, c=cap: r[2] <= c and r[3] and r[4] and r[4] >= 5 * r[3]))

    print("\n=== 6) OOS split pro nejlepsi kandidaty ===")
    cands = [
        ("rank<=50, cap1.20",
         lambda r: r[2] <= 1.20 and r[3] is not None and r[3] <= 50),
        ("gap>=5, cap1.20",
         lambda r: r[2] <= 1.20 and r[3] and r[4] and r[4] >= 5 * r[3]),
        ("gap>=8, cap1.20",
         lambda r: r[2] <= 1.20 and r[3] and r[4] and r[4] >= 8 * r[3]),
        ("rank<=50 & gap>=5",
         lambda r: r[2] <= 1.20 and r[3] is not None and r[3] <= 50
             and r[4] and r[4] >= 5 * r[3]),
    ]
    for label, pred in cands:
        print("-- %s --" % label)
        line("  cele", sel(pred))
        line("  prvni pol.", [(r[1], r[2]) for r in rows if pred(r) and r[0] < mid])
        line("  druha pol.", [(r[1], r[2]) for r in rows if pred(r) and r[0] >= mid])

    print("\n=== 7) ROK PO ROKU (nejlepsi kandidat rank<=50 cap1.20) ===")
    for y in years:
        line("rok %d" % y,
             [(r[1], r[2]) for r in rows
              if r[0] == y and r[2] <= 1.20 and r[3] is not None and r[3] <= 50])


if __name__ == "__main__":
    main()