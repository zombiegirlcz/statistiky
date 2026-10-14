#!/usr/bin/env python3
"""
sx_tape.py — "trénink" z ŽIVÝCH sázek cizích hráčů na SX.bet (public tape).

PROČ: REST endpointy `/trades-v3` vracejí JEN MOJE vlastní sázky (vážou se na
můj API klíč) — SX.bet sázky cizích hráčů přes REST veřejně neposkytuje.
Jediný veřejný zdroj je realtime kanál Centrifugo:

    recent_trades_v3:global   (SX.bet mu říká "public tape")

Ten posílá KAŽDOU sázku, která se na burze právě uzavřela — anonymně, ale
s ligou, typem trhu, výběrem, vsazenou částkou a kurzem. Z toho se dá za pár
sekund poskládat obrázek "kam dnes teče money a za jaké kurzy".

CO TO NENÍ: identita hráče (ta v tape není) ani jeho dlouhodobé ROI (to by
chtělo /trades-v3 s KYC klíčem). Je to tok peněz v reálném čase.

Jak to funguje technicky:
  1. `GET /user/realtime-token-v3/api-key` (hlavička x-sx-api-key) → JWT token.
  2. WebSocket `wss://realtime.sx.bet/connection/websocket` (protokol Centrifugo).
  3. `{"connect": {"token": ...}}`, pak `{"subscribe": {"channel": "recent_trades_v3:global"}}`.
  4. Každá zpráva typu "push" nese jednu sázku.

Použití:
  python3 sx_tape.py digest --sekundy 25           # sbírej 25 s a vypiš digest
  python3 sx_tape.py digest --sekundy 60 --max 500
"""
import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
import sxbet_client as sx  # noqa: E402

try:
    from sx_learner import MARKET_TYPE_LABELS
except Exception:  # noqa: BLE001 - kdyby se learner neimportoval, jedeme bez popisků
    MARKET_TYPE_LABELS = {}

USDC_DECIMALS = 6


def _api_key():
    return os.environ.get("SX_API_KEY") or None


def _realtime_token():
    """JWT pro realtime WebSocket (Centrifugo)."""
    key = _api_key()
    if not key:
        raise RuntimeError(
            "Chybí SX_API_KEY — realtime token se bez něj nevydá. "
            "Klíč vygeneruj na sx.bet (Account → Overview → API Credentials)."
        )
    req = urllib.request.Request(
        sx.SX_API_BASE + sx.REALTIME_TOKEN_URL,
        headers={"x-sx-api-key": key, "User-Agent": "statistiky-sxbet/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["token"]


def _typ_label(typ):
    if typ is None:
        return "neznámý"
    return MARKET_TYPE_LABELS.get(int(typ), f"typ {typ}")


def _norm_trade(t):
    """Z tape zprávy vytáhne normalizovaný řádek, nebo None (neúplná data)."""
    try:
        stake = int(t.get("totalStake") or 0) / (10 ** USDC_DECIMALS)
    except (ValueError, TypeError):
        stake = None
    try:
        # weightedAverageOdds = implikovaná pravděpodobnost × 1e20
        p = int(t["weightedAverageOdds"]) / 1e20
        odds = (1.0 / p) if p > 0 else None
    except (KeyError, ValueError, TypeError):
        odds = None
    return {
        "liga": t.get("leagueLabel") or "neznámá",
        "sportId": t.get("sportId"),
        "typ_trhu": _typ_label(t.get("type")),
        "typ": t.get("type"),
        "zapas": f"{t.get('teamOneName')} vs {t.get('teamTwoName')}",
        "vyber": t.get("outcomeLabel"),
        "strana1": bool(t.get("isBettingOutcomeOne")),
        "parlay": bool(t.get("isParlay")),
        "stake": stake,
        "kurz": round(odds, 3) if odds else None,
        "betTime": t.get("betTime"),
        "gameTime": t.get("gameTime"),
        "eventId": t.get("eventId"),
    }


async def _collect(seconds, max_trades, verbose=False):
    tok = _realtime_token()
    rows = []
    started = time.time()
    import websockets  # lokální import, ať modul jde importovat i bez WS knihovny

    async with websockets.connect(sx.REALTIME_WS_URL, open_timeout=20) as ws:
        await ws.send(json.dumps({"id": 1, "connect": {"token": tok}}))
        await asyncio.wait_for(ws.recv(), 15)  # connect reply
        await ws.send(json.dumps({"id": 2, "subscribe": {"channel": sx.PUBLIC_TAPE_CHANNEL}}))

        deadline = started + seconds
        while time.time() < deadline and len(rows) < max_trades:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 10))
            except asyncio.TimeoutError:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            pub = (d.get("push") or {}).get("pub") or {}
            data = pub.get("data") or {}
            trade = data.get("trade")
            if not trade:
                continue
            row = _norm_trade(trade)
            rows.append(row)
            if verbose:
                print(f"  + {row['liga'][:22]:22s} {row['typ_trhu'][:18]:18s} "
                      f"{str(row['vyber'])[:24]:24s} kurz {row['kurz']} stake {row['stake']}")
    return rows, time.time() - started


def _agreguj(radky, klic):
    skup = defaultdict(list)
    for r in radky:
        skup[r[klic]].append(r)
    out = []
    for k, rs in skup.items():
        stakes = [x["stake"] for x in rs if x["stake"]]
        kurzy = [x["kurz"] for x in rs if x["kurz"]]
        out.append({
            klic: k,
            "n": len(rs),
            "stake_usdc": round(sum(stakes), 2) if stakes else None,
            "prum_kurz": round(sum(kurzy) / len(kurzy), 3) if kurzy else None,
        })
    out.sort(key=lambda d: -(d["stake_usdc"] or 0))
    return out


def _pouceni(radky, podle_ligy, podle_typu):
    p = []
    if not radky:
        p.append("Za sledované okno nepřišla žádná sázka — zkus delší --sekundy "
                 "(tape je živý tok, ne historie).")
        return p
    total = sum(r["stake"] for r in radky if r["stake"])
    p.append(f"Za okno se vsadilo {len(radky)} sázek v celkové hodnotě "
             f"{total:.0f} USDC.")
    if podle_typu:
        top = podle_typu[0]
        p.append(f"Nejvíc peněz šlo do trhu '{top['typ_trhu']}' "
                 f"({top['stake_usdc']:.0f} USDC, průměrný kurz {top['prum_kurz']}).")
    if podle_ligy:
        top = podle_ligy[0]
        p.append(f"Nejaktivnější liga: {top['liga']} "
                 f"({top['n']} sázek, {top['stake_usdc']:.0f} USDC).")
    velke = sorted([r for r in radky if r["stake"]], key=lambda r: -r["stake"])[:3]
    if velke:
        p.append("Největší jednotlivé sázky: " + "; ".join(
            f"{v['zapas']} → {v['vyber']} ({v['stake']:.0f} USDC @ {v['kurz']})"
            for v in velke) + ".")
    p.append("Pozor: tape ukazuje, KAM teče money, ne jestli ten sázkař vydělává. "
             "Dav může sázet špatně — je to kontext, ne signál k slepému kopírování.")
    return p


def digest(seconds=25, max_trades=400, verbose=False):
    rows, elapsed = asyncio.run(_collect(seconds, max_trades, verbose=verbose))
    podle_ligy = _agreguj(rows, "liga")
    podle_typu = _agreguj(rows, "typ_trhu")
    podle_vyberu = _agreguj(rows, "vyber")[:15]
    # kolik money šlo na "stranu 1" vs "stranu 2"
    s1 = sum(r["stake"] for r in rows if r["stake"] and r["strana1"])
    s2 = sum(r["stake"] for r in rows if r["stake"] and not r["strana1"])
    return {
        "zdroj": "sxbet realtime " + sx.PUBLIC_TAPE_CHANNEL + " (veřejný tape, anonymní)",
        "okno_sekund": round(elapsed, 1),
        "pocet_trades": len(rows),
        "celkem_stake_usdc": round(sum(r["stake"] for r in rows if r["stake"]), 2),
        "podil_stake_strana1": round(s1 / (s1 + s2), 3) if (s1 + s2) else None,
        "podle_ligy": podle_ligy[:15],
        "podle_typu_trhu": podle_typu,
        "podle_vyberu": podle_vyberu,
        "nejnovejsi": rows[-5:],
        "pouceni": _pouceni(rows, podle_ligy, podle_typu),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mod", nargs="?", default="digest", choices=["digest"])
    ap.add_argument("--sekundy", type=int, default=25)
    ap.add_argument("--max", type=int, default=400)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    d = digest(args.sekundy, args.max, verbose=args.verbose)
    print(json.dumps(d, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()