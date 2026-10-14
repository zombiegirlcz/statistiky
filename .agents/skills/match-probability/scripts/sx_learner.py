#!/usr/bin/env python3
"""
sx_learner.py — statistiky sázek na SX.bet z V3 query endpointu `/trades-v3`.

!!! POZOR — PŘEČTI, NEŽ TO POUŽIJEŠ !!!
V3 query endpointy (`/trades-v3`, `/fills-v3`, `/positions-v3`) jsou VÁZANÉ
NA MŮJ API KLÍČ a vracejí POUZE MOJI VLASTNÍ aktivitu. Sázky cizích hráčů
tudy NEZÍSKÁŠ — SX.bet je přes REST veřejně neposkytuje (ověřeno živě
2026-10-05: 200 + prázdný seznam i za 1000 dní; V2 `/trades` už je mrtvý, 404).

PRO SÁZKY CIZÍCH HRÁČŮ POUŽIJ `sx_tape.py` — ten čte veřejný realtime kanál
`recent_trades_v3:global` (Centrifugo WebSocket), který posílá každou sázku
na burze anonymně (liga, trh, výběr, stake, kurz) v reálném čase. To je
jediný veřejný zdroj cizích sázek, který SX.bet má.

Tenhe modul je tedy užitečný jen pro MOJE vlastní sázky (ROI, pásma kurzů,
typy trhů) — pro trénink před stavbou tiketu slouží `sx_tape.py`.

Hlavička: `x-sx-api-key` (V2 měla `X-Api-Key`). Datum: ISO 8601 (ne unix).

Použití:
  python3 sx_learner.py digest --dny 30 --max-trades 500   # MOJE sázky
"""
import argparse
import json
import os
import sys
from collections import defaultdict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
import sxbet_client as sx  # noqa: E402


# Typy trhů (viz sx-bet-api-docs/_markets.md) → lidský název
MARKET_TYPE_LABELS = {
    1: "1X2", 52: "12 (vítěz)", 226: "12 vč. prodloužení", 88: "kdo postoupí",
    3: "asijský handicap", 201: "AH na gemy", 342: "AH vč. prodloužení",
    2: "přes/pod", 835: "asijské přes/pod", 28: "přes/pod vč. prodloužení",
    29: "přes/pod kol", 166: "přes/pod gamů", 1536: "přes/pod map",
    274: "vítěz turnaje",
    202: "vítěz 1. periody/setu", 203: "vítěz 2. periody/setu",
    204: "vítěz 3. periody/setu", 205: "vítěz 4. periody",
    866: "set spread", 165: "přes/pod setů",
    53: "AH poločas", 63: "12 poločas", 77: "přes/pod poločas",
    64: "AH 1. třetina", 65: "AH 2. třetina", 66: "AH 3. třetina",
    21: "přes/pod 1. třetina", 45: "přes/pod 2. třetina", 46: "přes/pod 3. třetina",
}

PASMA = ((1.0, 1.2), (1.2, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 1e9))


def _typ_label(typ):
    if typ is None:
        return "neznámý"
    return MARKET_TYPE_LABELS.get(int(typ), f"typ {typ}")


def _pasmo(odds):
    for lo, hi in PASMA:
        if lo <= odds < hi:
            return f"{lo:g}-{hi:g}" if hi < 1e9 else f"{lo:g}+"
    return "?"


def stahni_trades(dny=30, max_trades=500, page_size=100):
    """Stáhne uzavřené trades za posledních `dny` dní (max `max_trades`)."""
    import time
    start = int(time.time()) - dny * 86400
    trades = sx.trades(start_date=start, settled=True, page_size=page_size,
                       max_pages=max(1, max_trades // page_size))
    return trades[:max_trades]


def _obohat_markety(trades):
    hashes = [t.get("marketHash") for t in trades if t.get("marketHash")]
    try:
        return sx.markets_by_hashes(hashes)
    except Exception as e:  # noqa: BLE001 - digest nesmí spadnout kvůli obohacení
        print(f"[sx_learner] markety se nepodařilo dotáhnout: {e}", file=sys.stderr)
        return {}


def _radek(t, markety):
    """Převede jeden trade na normalizovaný řádek, nebo None (nevyhodnoceno)."""
    won = sx.trade_won(t)
    odds = sx.trade_decimal_odds(t)
    if won is None or odds is None:
        return None
    stake = sx.trade_stake_nominal(t)
    if not stake or stake <= 0:
        stake = 1.0
    m = markety.get(t.get("marketHash")) or {}
    return {
        "bettor": t.get("bettor"),
        "maker": bool(t.get("maker")),
        "won": won,
        "odds": odds,
        "stake": stake,
        "profit": stake * (odds - 1) if won else -stake,
        "sport": m.get("sportLabel") or "neznámý",
        "typ_trhu": _typ_label(m.get("type")),
        "liga": m.get("leagueLabel") or "neznámá",
    }


def _agreguj(radky):
    n = len(radky)
    if n == 0:
        return {"n": 0}
    staked = sum(r["stake"] for r in radky)
    profit = sum(r["profit"] for r in radky)
    wins = sum(1 for r in radky if r["won"])
    return {
        "n": n,
        "win_rate": round(wins / n, 4),
        "avg_kurz": round(sum(r["odds"] for r in radky) / n, 3),
        "vsazeno": round(staked, 2),
        "zisk": round(profit, 2),
        "roi": round(profit / staked, 4) if staked else None,
    }


def _rozpad(radky, klic):
    skup = defaultdict(list)
    for r in radky:
        skup[r[klic]].append(r)
    out = []
    for k, rs in sorted(skup.items(), key=lambda kv: -len(kv[1])):
        agg = _agreguj(rs)
        agg[klic] = k
        out.append(agg)
    return out


def _sharpi(radky, min_sazek=20):
    podle = defaultdict(list)
    for r in radky:
        if r["bettor"]:
            podle[r["bettor"]].append(r)
    out = []
    for bettor, rs in podle.items():
        if len(rs) < min_sazek:
            continue
        agg = _agreguj(rs)
        if agg.get("roi") is None:
            continue
        out.append({
            "bettor": bettor,
            "n": agg["n"],
            "win_rate": agg["win_rate"],
            "roi": agg["roi"],
            "avg_kurz": agg["avg_kurz"],
            "vsazeno": agg["vsazeno"],
            "podil_maker": round(sum(1 for r in rs if r["maker"]) / len(rs), 3),
            "sporty": sorted({r["sport"] for r in rs}),
        })
    out.sort(key=lambda d: (-d["roi"], -d["n"]))
    return out


def _pouceni(radky, sharpi, agregat_pasma):
    p = []
    if radky:
        vyhr = sum(1 for r in radky if r["won"])
        p.append(f"Celkově uzavřených sázek ve vzorku: {len(radky)}, "
                 f"úspěšnost {vyhr / len(radky):.0%}.")
    if sharpi:
        top = sharpi[0]
        p.append(f"Nejlepší 'sharp' hráč: {str(top['bettor'])[:10]}… s ROI "
                 f"{top['roi']:+.1%} z {top['n']} sázek (průměrný kurz {top['avg_kurz']}).")
    ztratove = [x for x in agregat_pasma
                if x.get("roi") is not None and x["roi"] < -0.05]
    if ztratove:
        p.append("Pásma kurzů s výrazně záporným ROI (opatrnost): "
                 + ", ".join(x["pasmo"] for x in ztratove) + ".")
    if not sharpi:
        p.append("Ve vzorku není bettor s dost velkým počtem sázek a kladným ROI — "
                 "z trhu teď nelze vyčíst spolehlivý 'sharp' signál.")
    p.append("Pozor: jde o statistiku reálných sázek na burze, ne o garanci. "
             "I kladné ROI u malého vzorku může být náhoda.")
    return p


def digest(dny=30, max_trades=500):
    trades = stahni_trades(dny, max_trades)
    markety = _obohat_markety(trades)
    radky = [r for r in (_radek(t, markety) for t in trades) if r]
    radky.sort(key=lambda r: r["odds"])

    pasma = defaultdict(list)
    for r in radky:
        pasma[_pasmo(r["odds"])].append(r)
    agregat_pasma = []
    for lo, hi in PASMA:
        key = f"{lo:g}-{hi:g}" if hi < 1e9 else f"{lo:g}+"
        agg = _agreguj(pasma.get(key, []))
        agg["pasmo"] = key
        agregat_pasma.append(agg)

    sharpi = _sharpi(radky)
    return {
        "zdroj": "sxbet /trades (reálné uzavřené sázky VŠECH hráčů)",
        "obdobi_dny": dny,
        "pocet_trades_stazeno": len(trades),
        "pocet_vyhodnocenych": len(radky),
        "pocet_bettoru": len({r["bettor"] for r in radky if r["bettor"]}),
        "agregat": _agreguj(radky),
        "podle_pasma_kurzu": agregat_pasma,
        "podle_sportu": _rozpad(radky, "sport"),
        "podle_typu_trhu": _rozpad(radky, "typ_trhu"),
        "sharpi": sharpi[:20],
        "pouceni": _pouceni(radky, sharpi, agregat_pasma),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mod", nargs="?", default="digest", choices=["digest"])
    ap.add_argument("--dny", type=int, default=30)
    ap.add_argument("--max-trades", type=int, default=500)
    args = ap.parse_args()
    d = digest(args.dny, args.max_trades)
    print(json.dumps(d, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
