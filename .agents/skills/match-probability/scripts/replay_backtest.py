#!/usr/bin/env python3
"""replay_backtest.py - "stroj casu": posle model zpet v case na zapasy,
u kterych ZNAME vysledek, a necha ho sazet presne stejnou strategii jako
zivy simulátor (silny favorit + stupnovane sazeni dle jistoty).

Proc: zivy simulátor ceka na dohrani zapasu (banka se hybe pomalu). Tohle
prehraje tisice HISTORICKYCH zapasu (WTA 2021-2025, zname vitez i kurz)
behem sekund, takze okamzite vidis, jak by si strategie vedla - vcetne
tutovek all-in.

NENI to novy model - pouziva presne ty same funkce a prahy jako
live_tennis_simulator (FAV_MODEL_MIN, FAV_MARKET_MIN, FAV_MAX_ODDS,
stake_tier). Je to jen zrychleny prehravac toho sameho rozhodovani.

Pouziti:
  python3 replay_backtest.py                 # vsechna leta, banka 1000
  python3 replay_backtest.py --rok 2024      # jen rok 2024
  python3 replay_backtest.py --banka 1000 --min-hist 15
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv  # noqa: E402
import live_tennis_simulator as sim  # noqa: E402 - SAME prahy + stake_tier


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rok", type=int, default=None)
    ap.add_argument("--banka", type=float, default=1000.0)
    ap.add_argument("--min-hist", type=int, default=15)
    args = ap.parse_args()

    if not os.path.exists(tv.ODDS_PATH):
        print("CHYBA: chybi %s (spust fetch_tennis_odds.py)" % tv.ODDS_PATH)
        sys.exit(1)

    sack = tv.load_sackmann_wta()
    with open(tv.ODDS_PATH, encoding="utf-8") as f:
        odds_rows = list(csv.DictReader(f))
    if args.rok:
        odds_rows = [r for r in odds_rows if r["Date"][:4] == str(args.rok)]

    joined = tv.join_matches(sack, odds_rows)
    joined.sort(key=lambda m: m["cutoff"])
    hist = tv.History(sack)

    F_MODEL = sim.FAV_MODEL_MIN
    F_MARKET = sim.FAV_MARKET_MIN
    F_ODDS = sim.FAV_MAX_ODDS

    bank = args.banka
    start = bank
    peak = bank
    n_eval = n_bets = n_wins = 0
    n_lock = n_strong = n_std = 0
    staked = returned = 0.0
    busted_at = None

    for m in joined:
        p1, n1, n2 = tv.model_prob(hist, m["name1"], m["name2"], m["cutoff"])
        if p1 is None or n1 < args.min_hist or n2 < args.min_hist:
            continue
        o1, o2 = m["odd1"], m["odd2"]
        if not (tv.ODDS_MIN <= o1 <= tv.ODDS_MAX and tv.ODDS_MIN <= o2 <= tv.ODDS_MAX):
            continue
        p_mkt1, p_mkt2, _ = tv.devig(o1, o2)
        n_eval += 1

        # vyber favorita: model I trh se musi shodnout (jako zivy simulátor)
        pick = None
        for name, p_model, p_mkt, odds, won in (
            (m["name1"], p1, p_mkt1, o1, m["p1_won"]),
            (m["name2"], 1 - p1, p_mkt2, o2, not m["p1_won"]),
        ):
            if p_model >= F_MODEL and p_mkt >= F_MARKET and odds <= F_ODDS:
                pick = (name, p_model, p_mkt, odds, won)
                break
        if pick is None:
            continue

        name, p_model, p_mkt, odds, won = pick
        pct, tier = sim.stake_tier(p_model, p_mkt, odds)
        stake = round(bank * pct)
        if stake < sim.MIN_STAKE or stake > bank:
            continue

        n_bets += 1
        staked += stake
        if tier.startswith("TUTOVKA"):
            n_lock += 1
        elif tier == "silny favorit":
            n_strong += 1
        else:
            n_std += 1

        if won:
            n_wins += 1
            returned += stake * odds
            bank += stake * (odds - 1)
        else:
            bank -= stake
        if bank > peak:
            peak = bank
        if bank < sim.MIN_STAKE:
            busted_at = m["date"]
            break

    print("=" * 64)
    print("STROJ CASU: prehrani historickych WTA zapasu" + (f" (rok {args.rok})" if args.rok else ""))
    print("=" * 64)
    print(f"Hodnocenych zapasu (dost historie): {n_eval}")
    print(f"Vsazenych tiketu:                   {n_bets}")
    print(f"  z toho TUTOVEK (all-in):          {n_lock}")
    print(f"  z toho silnych favoritu (10%):    {n_strong}")
    print(f"  z toho standard (2%):             {n_std}")
    if n_bets:
        print(f"Uspesnost:                          {n_wins}/{n_bets} = {100.0*n_wins/n_bets:.1f} %")
        print(f"ROI:                                {(returned-staked)/staked*100.0:+.1f} %")
    print("-" * 64)
    print(f"Banka start:  {start:.0f}")
    print(f"Banka ted:    {bank:.0f}  ({bank-start:+.0f})")
    print(f"Vrchol banky: {peak:.0f}")
    if busted_at:
        print(f"!! BANKA VYNULOVANA (all-in tutovka prohrala) dne {busted_at}")
    print("=" * 64)


if __name__ == "__main__":
    main()
