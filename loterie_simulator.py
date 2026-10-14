#!/usr/bin/env python3
"""loterie_simulator.py - simulator hry Lucky Six (Fortuna).

PRAVIDLA (z loterie.md):
  * Vyberes 6 cisel z 48.
  * V kazdem kole se postupne losuje 35 z 48 cisel.
  * Vyhravas, jakmile se vylosuje VSECH 6 tvych cisel (v ramci tech 35).
  * Cim drive padne 6. spravne cislo, tim vyssi nasobek vkladu.
  * Nasobky podle poradi 6. spravneho cisla - viz MULT nize.

Tenhle skript meri:
  1. Jak casto se trefi vsech 6 cisel (hit rate).
  2. Jake je rozdeleni poradi 6. spravneho cisla.
  3. Ocekavany nasobek a ROI (navratnost) pri flat vkladu.
  4. Presnou pravdepodobnost a EV (analyticky, kombinatorika) pro kontrolu.

Pouziti:
  python3 loterie_simulator.py                # 2 000 000 simulovanych losovani
  python3 loterie_simulator.py 1000000        # jiny pocet
  python3 loterie_simulator.py --seed 42      # reprodukovatelne
"""
import argparse
import random
from collections import Counter
from math import comb

# Nasobek vkladu podle PORADI, ve kterem padne 6. spravne cislo.
# OVERENO z oficialniho Herniho planu Fortuna CR (PDF z ifortuna.cz,
# file/658301651f48d321062d1d89), clanek 6.7 "Lucky six online" -
# tabulka "VYHERNI NASOBEK podle PORADI VYLOSOVANI POSLEDNIHO ZE VSECH
# CISEL TIPOVANYCH SAZEJICIM".
#
# Kontrola: RTP z teto tabulky = 75.87 %, coz PRESNE odpovida clanku 6.8
# herniho planu: "Vyse Vyherni jistiny pro Ciselnou loterii Lucky six
# online cini v dlouhodobem prumeru 75,87 %."
#
# (Drivejsi tabulka z napovedy v aplikaci byla pro jinou/EUR verzi hry:
#  min 3 EUR, RTP 85,87-99,63 %, s bonusovym kolem, ktere cesky plan
#  v Lucky Six vubec neobsahuje.)
MULT = {
    6: 10000, 7: 7500, 8: 5000, 9: 2000, 10: 1000,
    11: 500, 12: 200, 13: 100, 14: 70, 15: 50,
    16: 40, 17: 30, 18: 25, 19: 20, 20: 17,
    21: 15, 22: 14, 23: 13, 24: 12, 25: 11,
    26: 10, 27: 9, 28: 8, 29: 7, 30: 6,
    31: 5, 32: 4, 33: 3, 34: 2, 35: 1,
}

TOTAL = 48        # z kolika cisel se losuje
PICK = 6          # kolik cisel si vyberes
DRAWN = 35        # kolik cisel se vylosuje v kole
STAKE = 20.0      # vklad v Kc (minimum u Fortuny)


def analytic_hit_prob():
    """Presna pravdepodobnost, ze vsech 6 cisel je mezi 35 vylosovanymi.

    = C(42, 29) / C(48, 35) = C(42, 13) / C(48, 13)
    (nasich 6 musi byt ve vybranych 35; ekvivalentne zadne z nasich 6 neni
     mezi 13 nevylosovanymi).
    """
    return comb(TOTAL - PICK, DRAWN - PICK) / comb(TOTAL, DRAWN)


def analytic_pos_dist():
    """Presne rozdeleni poradi (6..35) 6. spravneho cisla.

    P(pos6 = p) = [P(v prvnich p-1 je prave 5 nasich)] * [p-ty tah je nas posledni]
                = C(6,5) * C(42, p-6) / C(48, p-1) * 1/(48-(p-1))
    """
    dist = {}
    for p in range(PICK, DRAWN + 1):
        num = comb(PICK, PICK - 1) * comb(TOTAL - PICK, (p - 1) - (PICK - 1))
        den = comb(TOTAL, p - 1)
        dist[p] = (num / den) * (1.0 / (TOTAL - (p - 1)))
    return dist


def simulate(n, seed=None):
    rng = random.Random(seed)
    all_nums = list(range(1, TOTAL + 1))
    hits = 0
    order_hist = Counter()
    mult_sum = 0.0
    returned = 0.0
    for _ in range(n):
        my = rng.sample(all_nums, PICK)
        my_set = set(my)
        draw = rng.sample(all_nums, DRAWN)
        seen = 0
        pos6 = None
        for i, d in enumerate(draw, start=1):
            if d in my_set:
                seen += 1
                if seen == PICK:
                    pos6 = i
                    break
        if pos6 is not None:
            hits += 1
            order_hist[pos6] += 1
            mult_sum += MULT[pos6]
            returned += STAKE * MULT[pos6]
    return {"n": n, "hits": hits, "order_hist": order_hist,
            "mult_sum": mult_sum, "returned": returned,
            "staked": STAKE * n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=2_000_000)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    p = analytic_hit_prob()
    dist = analytic_pos_dist()
    ev_mult = sum(dist[pos] * MULT[pos] for pos in dist)   # E[vyhra_bez_jednotky]
    analytic_roi = (ev_mult - 1.0) * 100.0

    print("=" * 70)
    print("LUCKY SIX - simulator (6 cisel z 48, losuje se 35 z 48)")
    print("=" * 70)
    print(f"Presna pravdepodobnost trefy vsech 6 cisel:  {p:.8f}")
    print(f"  = 1 z {1/p:,.1f} losovani   =  {p*100:.5f} %")
    print(f"Analyticky ocekavany nasobek vkladu:        {ev_mult:.5f}x")
    print(f"Analyticke ROI:                             {analytic_roi:+.3f} %")
    print()

    res = simulate(args.n, seed=args.seed)
    n = res["n"]; hits = res["hits"]
    print(f"Simulovano losovani:        {n:,}")
    print(f"Trefeno vsech 6 cisel:      {hits:,}  ({100.0*hits/n:.5f} %)")
    print(f"  ocekavano dle teorie:     {p*n:,.1f}")
    print()

    print("Rozdeleni podle PORADI, ve kterem padlo 6. spravne cislo:")
    print(f"  {'poradi':>6} {'sim pocet':>11} {'sim podil':>11} {'teorie':>11} {'nasobek':>8}")
    for pos in range(PICK, DRAWN + 1):
        c = res["order_hist"].get(pos, 0)
        sim_p = (100.0 * c / hits) if hits else 0.0
        theo_p = 100.0 * dist[pos] / p if p else 0.0
        print(f"  {pos:>6} {c:>11,} {sim_p:>10.3f}% {theo_p:>10.3f}% {MULT[pos]:>7}x")
    print()

    avg_mult = (res["mult_sum"] / hits) if hits else 0.0
    roi = (res["returned"] - res["staked"]) / res["staked"] * 100.0
    ev_per_bet = (res["returned"] - res["staked"]) / n

    print(f"Vklad na kolo:              {STAKE:.0f} Kc")
    print(f"Prumerny nasobek vyhry:     {avg_mult:,.2f}x")
    print(f"Vsazeno celkem:             {res['staked']:,.0f} Kc")
    print(f"Vraceno celkem:             {res['returned']:,.0f} Kc")
    print(f"ROI (navratnost):           {roi:+.3f} %")
    print(f"Ocekavana zmena na kolo:    {ev_per_bet:+.3f} Kc")
    print("=" * 70)


if __name__ == "__main__":
    main()