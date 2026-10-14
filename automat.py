#!/usr/bin/env python3
"""
automat.py — klasický 3válcový výherní automat (3x3, 5 linií).

LOGIKA (věrná skutečnému automatu):
  * Každý válec má PEVNÝ PRUH symbolů (jako fyzický pás).
  * Zatočení = náhodná pozice na pruhu → zobrazí se 3 po sobě jdoucí symboly.
  * Výherní linie (5): horní řada, prostřední, dolní, dvě diagonály.
  * Výhra = 3 stejné symboly na linii zleva doprava.
  * WILD (🃏) nahrazuje jakýkoli symbol.
  * SCATTER (🎁) platí kdekoliv (ne na linii) — 3 scatter = velká výhra.

Použití:
  python3 automat.py                 # simulace 1 000 000 zatočení → RTP
  python3 automat.py 500000          # jiný počet
  python3 automat.py --seed 42       # reprodukovatelné
  python3 automat.py --spin 100      # zahraje 100 zatočení s výpisem
"""
import argparse
import random
from collections import Counter

# ---------------------------------------------------------------------------
# SYMBOLY — klíč → (emoji, násobek při 3 na linii, je_wild, je_scatter)
# ---------------------------------------------------------------------------
SYMBOLS = {
    "cherry":  ("🍒", 5,   False, False),
    "lemon":   ("🍋", 8,   False, False),
    "orange":  ("🍊", 12,  False, False),
    "grape":   ("🍇", 20,  False, False),
    "bell":    ("🔔", 40,  False, False),
    "star":    ("⭐", 80,  False, False),
    "seven":   ("7️⃣", 200, False, False),
    "diamond": ("💎", 500, False, False),
    "wild":    ("🃏", 1000, True,  False),   # nahrazuje cokoli
    "scatter": ("🎁", 0,   False, True),    # platí kdekoliv
}

# Násobek za SCATTER kdekoliv (počet scatterů → násobek celkového vkladu)
SCATTER_PAY = {3: 10, 2: 1}

# ---------------------------------------------------------------------------
# PRUHY VÁLCŮ — pevné pořadí symbolů (jako fyzický pás na válci)
# Čím vzácnější symbol, tím méněkrát je na pruhu.
# ---------------------------------------------------------------------------
def _strip(weights):
    """Sestaví pruh z {symbol: počet} a zamíchá (fixně, ne při každém zatočení)."""
    s = []
    for sym, n in weights.items():
        s += [sym] * n
    random.Random(1234).shuffle(s)   # fixní pruh — jako skutečný válec
    return s

# Každý válec má mírně jiné složení (jako skutečné automaty)
REEL_WEIGHTS = [
    # válec 1 (více levných, méně drahých)
    {"cherry": 7, "lemon": 6, "orange": 5, "grape": 4, "bell": 3,
     "star": 2, "seven": 1, "diamond": 1, "wild": 1, "scatter": 2},
    # válec 2
    {"cherry": 7, "lemon": 6, "orange": 5, "grape": 4, "bell": 3,
     "star": 2, "seven": 1, "diamond": 1, "wild": 1, "scatter": 2},
    # válec 3 (méně wildů → wild jen na 1-2)
    {"cherry": 8, "lemon": 7, "orange": 6, "grape": 5, "bell": 4,
     "star": 2, "seven": 1, "diamond": 1, "wild": 1, "scatter": 2},
]
# PEVNE PRUHY (konkretni usporadani dava stabilni RTP ~96-97 %;
# poradi na valci ovlivnuje vysledek, proto je zamceno - viz poznamka).
REELS = [["diamond", "wild", "cherry", "lemon", "grape", "orange", "orange", "orange", "cherry", "cherry", "cherry", "lemon", "lemon", "grape", "cherry", "star", "scatter", "scatter", "orange", "grape", "cherry", "bell", "orange", "cherry", "lemon", "bell", "lemon", "bell", "star", "grape", "lemon", "seven"], ["lemon", "orange", "cherry", "bell", "cherry", "orange", "cherry", "orange", "seven", "bell", "lemon", "orange", "grape", "lemon", "lemon", "grape", "orange", "star", "wild", "lemon", "lemon", "scatter", "scatter", "bell", "grape", "cherry", "grape", "star", "cherry", "cherry", "cherry", "diamond"], ["cherry", "bell", "bell", "cherry", "orange", "scatter", "lemon", "orange", "cherry", "grape", "orange", "lemon", "grape", "wild", "orange", "cherry", "cherry", "star", "lemon", "lemon", "grape", "lemon", "cherry", "bell", "orange", "grape", "grape", "cherry", "orange", "seven", "scatter", "lemon", "bell", "star", "diamond", "cherry", "lemon"]]
REEL_LEN = [len(r) for r in REELS]

# ---------------------------------------------------------------------------
# VÝHERNÍ LINIE — (řádek pro válec 1, 2, 3), řádky 0-2 (0=horní)
# ---------------------------------------------------------------------------
PAYLINES = [
    (1, 1, 1),   # prostřední řada
    (0, 0, 0),   # horní řada
    (2, 2, 2),   # dolní řada
    (0, 1, 2),   # diagonála ↘
    (2, 1, 0),   # diagonála ↗
]


def spin(rng=None):
    """Zatočí všemi válci. Vrátí mřížku [válec][řádek] = symbol."""
    rng = rng or random
    grid = []
    for reel in REELS:
        n = len(reel)
        stop = rng.randrange(n)
        # 3 viditelné symboly: stop, stop+1, stop+2 (s obtočením)
        grid.append([reel[(stop + i) % n] for i in range(3)])
    return grid


def _symbol_na(grid, reel, row):
    return grid[reel][row]


def _vyhodnot_linii(grid, line):
    """Vyhodnotí jednu linii. Vrátí (násobek, popis) nebo (0, None)."""
    syms = [_symbol_na(grid, i, line[i]) for i in range(3)]
    # najdi základní symbol (ne wild)
    zaklad = None
    for s in syms:
        if not SYMBOLS[s][2]:   # není wild
            zaklad = s
            break
    if zaklad is None:
        zaklad = "wild"          # všechny tři wild
    # ověř, že všechny jsou zaklad nebo wild
    for s in syms:
        if s != zaklad and not SYMBOLS[s][2]:
            return 0, None
    mult = SYMBOLS[zaklad][1]
    return mult, syms


def vyhodnot(grid, stake_per_line=1.0):
    """Vyhodnotí celou mřížku. Vrátí (výhra, seznam detailů, počet scatterů)."""
    vyhra = 0.0
    detaily = []
    for line in PAYLINES:
        mult, syms = _vyhodnot_linii(grid, line)
        if mult:
            v = mult * stake_per_line
            vyhra += v
            detaily.append((line, mult, syms, v))
    # scatter — kdekoliv v mřížce
    vsechny = [s for reel in grid for s in reel]
    sc = sum(1 for s in vsechny if SYMBOLS[s][3])
    if sc in SCATTER_PAY:
        v = SCATTER_PAY[sc] * stake_per_line * len(PAYLINES)
        vyhra += v
        detaily.append(("scatter", sc, None, v))
    return vyhra, detaily, sc


def simulate(n, stake_total=5.0, seed=None):
    """Simuluje n zatočení. stake_total = celkový vklad na zatočení (rozdělený
    mezi linie). Vrací statistiky RTP."""
    rng = random.Random(seed)
    per_line = stake_total / len(PAYLINES)
    staked = 0.0
    returned = 0.0
    hits = 0
    sym_hits = Counter()
    scatter_hits = Counter()
    for _ in range(n):
        g = spin(rng)
        v, det, sc = vyhodnot(g, per_line)
        staked += stake_total
        returned += v
        if v > 0:
            hits += 1
        for line, mult, syms, vv in det:
            if line == "scatter":
                scatter_hits[sc] += 1
            else:
                zaklad = next((s for s in syms if not SYMBOLS[s][2]), "wild")
                sym_hits[zaklad] += 1
    return {
        "n": n, "staked": staked, "returned": returned,
        "rtp": returned / staked if staked else 0,
        "hit_rate": hits / n if n else 0,
        "sym_hits": sym_hits, "scatter_hits": scatter_hits,
    }


def zobraz(grid, vyhra=0.0, detaily=None):
    """Textový výpis mřížky (3x3)."""
    print("  ┌─────┬─────┬─────┐")
    for r in range(3):
        row = "  │"
        for c in range(3):
            row += f"  {SYMBOLS[grid[c][r]][0]}  │"
        print(row)
        if r < 2:
            print("  ├─────┼─────┼─────┤")
    print("  └─────┴─────┴─────┘")


def hraj(n=100, stake=5.0, seed=None):
    """Interaktivní/zábavní režim: n zatočení s výpisem."""
    rng = random.Random(seed)
    bank = 1000.0
    per_line = stake / len(PAYLINES)
    print(f"  Start bank: {bank:.0f} Kč · vklad/zatočení: {stake:.0f} Kč\n")
    for i in range(1, n + 1):
        g = spin(rng)
        v, det, sc = vyhodnot(g, per_line)
        bank += v - stake
        znamenko = "✔" if v > 0 else "✘"
        barva = "\033[32m" if v > 0 else "\033[31m"
        print(f"  {i:>3}. {znamenko} výhra {barva}{v:>8.2f}\033[0m Kč   bank {bank:>9.2f} Kč")
        if v > 0 and (v >= stake * 20 or i <= 3):
            zobraz(g)
            for line, mult, syms, vv in det:
                if line == "scatter":
                    print(f"       🎁 SCATTER ×{sc} → {vv:.2f} Kč")
                else:
                    em = " ".join(SYMBOLS[s][0] for s in syms)
                    print(f"       linie {line} {em} → {mult}× → {vv:.2f} Kč")
        if bank < stake:
            print(f"\n  BANKROT v {i}. zatočení.")
            break
    print(f"\n  Konec bank: {bank:.2f} Kč ({bank-1000:+.2f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=1_000_000)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--spin", type=int, default=0, help="zahraj N zatočení s výpisem")
    args = ap.parse_args()

    print("=" * 66)
    print("AUTOMAT 3x3 — 5 linií, wild 🃏, scatter 🎁")
    print("=" * 66)
    print(f"Délky válců: {REEL_LEN}")
    print(f"Linie: {len(PAYLINES)}  ·  symbolů: {len(SYMBOLS)}")
    print()

    if args.spin:
        hraj(args.spin, seed=args.seed)
        return

    res = simulate(args.n, stake_total=5.0, seed=args.seed)
    print(f"Simulováno zatočení:  {res['n']:,}")
    print(f"Vsazeno:              {res['staked']:,.0f} Kč")
    print(f"Vráceno:              {res['returned']:,.0f} Kč")
    print(f"RTP:                  {res['rtp']*100:.2f} %")
    print(f"Hit rate (něco vyhrálo): {res['hit_rate']*100:.2f} %")
    print()
    print("Výhry podle symbolu:")
    for sym, c in res["sym_hits"].most_common():
        print(f"  {SYMBOLS[sym][0]} {sym:<8} {c:>10,}")
    print("Scatter:")
    for k in sorted(res["scatter_hits"]):
        print(f"  🎁 ×{k}  {res['scatter_hits'][k]:>10,}")
    print("=" * 66)


if __name__ == "__main__":
    main()