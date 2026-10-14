#!/usr/bin/env python3
"""maxa_sestka.py — model hry Maxa Šestka (Maxa, dříve Korunka).

PRAVIDLA (dle maxa.cz a encyklopediehazardu.cz, ověřeno):
  * V osudí je 49 míčků, losuje se 6 čísel. Losování probíhá 2x denně
    (odpolední 14:10, večerní 18:10) za účasti státního notáře.
  * Hráč tipuje 6 čísel.
  * Výhry jsou PEVNÉ (nedělí se mezi výherce) podle počtu trefených čísel:
        6 → 5 000 000 Kč   (tiket 35 Kč; tiket 70 Kč → 10 000 000 Kč)
        5 →   250 000 Kč
        4 →     2 500 Kč
        3 →       500 Kč
        2 →        35 Kč   (= vratka vkladu)
        0–1 →         0 Kč
  * Marketing Maxy tvrdí „největší podíl na výhrách ze všech loterií v ČR",
    ale spočítané RTP je ~59,6 % — tedy MÉNĚ než Lucky Six (75,87 %).

Ověřeno: RTP = 59,57 %.
"""
from math import comb

TOTAL = 49          # míčků v osudí
PICK = 6            # kolik čísel tipuje hráč
DRAWN = 6           # kolik čísel se losuje
STAKE = 35.0        # základní tiket (Kč); 70 Kč = dvojnásobné výhry

# Pevné výhry pro základní tiket 35 Kč
VYHRY = {6: 5_000_000, 5: 250_000, 4: 2_500, 3: 500, 2: 35, 1: 0, 0: 0}

# Násobek vkladu podle počtu tref (nezávislý na výši tiketu — 35 i 70 Kč
# škálují lineárně, takže poměr je stejný)
MULT = {k: v / STAKE for k, v in VYHRY.items()}

# Losování 2x denně -> převod kol na dny/roky
LOSOVANI_DENNE = 2


def analytic_dist():
    """P(přesně k trefených čísel) = C(6,k) * C(43, 6-k) / C(49, 6)."""
    return {
        k: comb(PICK, k) * comb(TOTAL - PICK, DRAWN - k) / comb(TOTAL, DRAWN)
        for k in range(PICK + 1)
    }


def analytic_ev(stake=STAKE):
    """Očekávaný výnos (Kč) na jeden tiket při daném vkladu."""
    dist = analytic_dist()
    return sum(dist[k] * VYHRY[k] for k in dist) * (stake / STAKE)


def analytic_rtp():
    """RTP = EV / vklad (nezávislé na výši vkladu)."""
    return analytic_ev(STAKE) / STAKE


def p_jackpot():
    return 1.0 / comb(TOTAL, DRAWN)


def draw(rng=None):
    """Vylosuje 6 čísel ze 49 (v pořadí)."""
    import random
    rng = rng or random
    return rng.sample(range(1, TOTAL + 1), DRAWN)


def vyhodnot(moje, draw):
    """Vrátí počet trefených čísel (0..6)."""
    return len(set(moje) & set(draw))


def payout(matches, stake):
    """Výhra v Kč pro daný počet tref a vklad."""
    return stake * MULT[matches]


def simulate_until_jackpot(stake=STAKE, max_rounds=500_000_000, seed=None,
                           chunk=2_000_000, progress_cb=None,
                           progress_every_chunks=5):
    """Simuluje kola, dokud hráč netrefí všech 6 čísel (hlavní výhru).

    K návratovému slovníku:
      rounds        – kol bylo odehráno do jackpotu (včetně)
      total_staked  – celkem vsazeno (Kč)
      total_returned– celkem vráceno (Kč), včetně jackpotu
      tiers         – počty výher podle tref 2/3/4/5 (jackpot zvlášť)
      hit           – True pokud jackpot padl do max_rounds
      bank          – zůstatek (total_returned - total_staked)
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    rounds = 0
    total_staked = 0.0
    total_returned = 0.0
    tiers = {2: 0, 3: 0, 4: 0, 5: 0}
    jackpot_rounds = None
    chunks_done = 0

    while rounds < max_rounds:
        n = min(chunk, max_rounds - rounds)
        draws = rng.hypergeometric(PICK, TOTAL - PICK, DRAWN, size=n)
        hit_idx = np.flatnonzero(draws == 6)

        if hit_idx.size:
            stop = int(hit_idx[0]) + 1
            seg = draws[:stop]
        else:
            stop = n
            seg = draws

        seg_staked = stop * stake
        seg_returned = 0.0
        for k in (2, 3, 4, 5):
            c = int(np.count_nonzero(seg == k))
            tiers[k] += c
            seg_returned += c * stake * MULT[k]

        total_staked += seg_staked
        total_returned += seg_returned
        rounds += stop
        chunks_done += 1

        if hit_idx.size:
            total_returned += stake * MULT[6]   # jackpot
            jackpot_rounds = rounds
            if progress_cb:
                progress_cb(rounds, total_staked, total_returned, tiers, True)
            break

        if progress_cb and chunks_done % progress_every_chunks == 0:
            progress_cb(rounds, total_staked, total_returned, tiers, False)

    return {
        "rounds": rounds,
        "total_staked": total_staked,
        "total_returned": total_returned,
        "tiers": tiers,
        "hit": jackpot_rounds is not None,
        "jackpot_rounds": jackpot_rounds,
        "bank": total_returned - total_staked,
    }


if __name__ == "__main__":
    dist = analytic_dist()
    print("Maxa Šestka — 6 z 49")
    print(f"RTP = {analytic_rtp()*100:.2f} %")
    print(f"P(jackpot 6/6) = {p_jackpot():.8f}  = 1 z {1/p_jackpot():,.0f}")
    for k in range(6, -1, -1):
        print(f"  {k} tref: P={dist[k]:.6%}  výhra {VYHRY[k]:,} Kč")