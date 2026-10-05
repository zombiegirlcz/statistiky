#!/usr/bin/env python3
"""
tape_archiver.py — archivace sázek z veřejného SX.bet tape + jejich výsledků.

PROČ: Jediná veřejná data o sázkách cizích hráčů jsou realtime kanál
`recent_trades_v3:global`. Ten nese sázku anonymně (bez adresy sázkaře), ale
s `tradeId` a `marketHash`. Z `marketHash` se přes REST `/markets/find` DÁ
zpětně dohledat výsledek (outcome 1/2 + skóre). Tím vzniká archiv
"sázka → její výsledek", ze kterého jde spočítat, jestli se směr velkých
peněz trefuje častěji, než říká jejich kurz.

CO TO ZKOUŠÍ (a co to NENÍ):
  * Hypotéza: velké jednotlivé sázky (> ~500 USDC) vyhrávají častěji, než
    jejich implikovaná pravděpodobnost (1/kurz) → na burze jsou informovaní
    hráči a jejich směr má hodnotu.
  * NENÍ to identita hráče — tape ji nemá. Je to jen tok peněz + výsledek.
  * Data se musí NASBÍRAT: tape je živý tok, ne historie. Realisticky
    týdny běhu, než jsou čísla použitelná (stovky uzavřených sázek minimum).

PAST: STŘEPY. Jeden velký příkaz se v tape rozpadá na mnoho drobných sázek
(stejný marketHash + stejná strana + stejný stake, v rozestupu sekund).
Bez ošetření by se z jednoho velkého hráče staly stovky "malých". Report
proto sázky seskupuje do "fillů" (viz `--okno-strepy`).

SOUBORY (vedle skriptu, ve složce match-probability/):
  tape_archive.jsonl     — každá sázka: tradeId, marketHash, strana, stake,
                           kurz, čas, liga, trh + doplněný výsledek (outcome)

Použití:
  python3 tape_archiver.py collect --sekundy 300      # sbírej z tape
  python3 tape_archiver.py settle                     # doplň výsledky
  python3 tape_archiver.py report                     # analýza velké vs. malé
  python3 tape_archiver.py run --sekundy 300          # collect + settle
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
import sxbet_client as sx  # noqa: E402

try:
    from sx_learner import MARKET_TYPE_LABELS
except Exception:  # noqa: BLE001
    MARKET_TYPE_LABELS = {}

_ARCHIVE = os.path.join(os.path.dirname(_SCRIPT_DIR), "tape_archive.jsonl")


def _typ_label(typ):
    if typ is None:
        return "neznámý"
    return MARKET_TYPE_LABELS.get(int(typ), f"typ {typ}")


# ---------------------------------------------------------------------------
# Načtení / zápis archivu
# ---------------------------------------------------------------------------
def _load():
    if not os.path.exists(_ARCHIVE):
        return []
    out = []
    with open(_ARCHIVE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _save(rows):
    """Zapíše celý archiv atomicky (temp + rename), ať se nikdy nerozbije."""
    tmp = _ARCHIVE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, _ARCHIVE)


# ---------------------------------------------------------------------------
# Sběr z tape
# ---------------------------------------------------------------------------
def _radek_z_trade(t):
    """Normalizuje raw tape trade na řádek archivu (jen co v tape reálně je)."""
    try:
        stake = int(t.get("totalStake") or 0) / 1e6
    except (ValueError, TypeError):
        stake = None
    try:
        p = int(t["weightedAverageOdds"]) / 1e20
        odds = (1.0 / p) if p > 0 else None
    except (KeyError, ValueError, TypeError):
        odds = None
    return {
        "tradeId": t.get("tradeId"),
        "marketHash": t.get("marketHash"),
        "eventId": t.get("eventId"),
        "typ": t.get("type"),
        "typ_trhu": _typ_label(t.get("type")),
        "liga": t.get("leagueLabel"),
        "zapas": f"{t.get('teamOneName')} vs {t.get('teamTwoName')}",
        "vyber": t.get("outcomeLabel"),
        "strana1": bool(t.get("isBettingOutcomeOne")),
        "stake": stake,
        "kurz": round(odds, 4) if odds else None,
        "betTime": t.get("betTime"),
        "gameTime": t.get("gameTime"),
        "parlay": bool(t.get("isParlay")),
        "outcome": None,        # doplní settle
        "vyhral": None,         # True/False/None (void)
    }


async def _collect(seconds, max_trades, verbose=False):
    import urllib.request
    import websockets
    # realtime token se vrací MIMO obálku {status,data}, proto vlastní request
    req = urllib.request.Request(
        sx.SX_API_BASE + sx.REALTIME_TOKEN_URL,
        headers={"x-sx-api-key": sx._sx_api_key(), "User-Agent": "statistiky-tape/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        tok = json.loads(r.read().decode("utf-8"))["token"]

    rows, started = [], time.time()
    async with websockets.connect(sx.REALTIME_WS_URL, open_timeout=20) as ws:
        await ws.send(json.dumps({"id": 1, "connect": {"token": tok}}))
        await asyncio.wait_for(ws.recv(), 15)
        await ws.send(json.dumps({"id": 2, "subscribe": {"channel": sx.PUBLIC_TAPE_CHANNEL}}))
        deadline = started + seconds
        while time.time() < deadline and len(rows) < max_trades:
            rem = deadline - time.time()
            if rem <= 0:
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(rem, 10))
            except asyncio.TimeoutError:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            tr = (((d.get("push") or {}).get("pub") or {}).get("data") or {}).get("trade")
            if not tr:
                continue
            row = _radek_z_trade(tr)
            if row["tradeId"]:
                rows.append(row)
                if verbose:
                    print(f"  + {row['liga']} | {row['typ_trhu']} | {row['vyber']} "
                          f"| {row['stake']:.2f} USDC @ {row['kurz']}")
    return rows, time.time() - started


def cmd_collect(seconds, max_trades, verbose=False):
    existing = _load()
    seen = {r.get("tradeId") for r in existing}
    print(f"Archiv: {len(existing)} záznamů. Sbírám {seconds} s z tape…")
    rows, elapsed = asyncio.run(_collect(seconds, max_trades, verbose=verbose))
    new = [r for r in rows if r["tradeId"] not in seen]
    _save(existing + new)
    print(f"  zachyceno {len(rows)}, nových {len(new)} (duplicit {len(rows) - len(new)}), "
          f"celkem v archivu {len(existing) + len(new)}, za {elapsed:.1f} s")
    return len(new)


# ---------------------------------------------------------------------------
# Settlement — doplnění výsledků přes /markets/find
# ---------------------------------------------------------------------------
def _settle_batch(rows):
    """Doplní `outcome`/`vyhral` záznamům, jejichž marketHash už je uzavřený.

    Volá /markets/find po dávkách max 30 hashů (limit API). Vrací počet
doplněných.
    """
    bez = [r for r in rows if r.get("outcome") is None and r.get("marketHash")]
    if not bez:
        return 0
    hashes = sorted({r["marketHash"] for r in bez})
    info = {}
    for i in range(0, len(hashes), 30):
        chunk = hashes[i:i + 30]
        try:
            d = sx._get("/markets/find", {"marketHashes": ",".join(chunk)})
        except Exception as e:  # noqa: BLE001
            print(f"  [settle] chyba u dávky {i//30}: {str(e)[:120]}")
            continue
        for m in d.get("data") or []:
            if m.get("marketHash"):
                info[m["marketHash"]] = m
    n = 0
    for r in bez:
        m = info.get(r["marketHash"])
        if not m:
            continue
        oc = m.get("outcome")
        if oc in (None, 0):      # neuzavřeno / void
            continue
        r["outcome"] = oc
        r["vyhral"] = (oc == 1) == bool(r.get("strana1"))
        r["score"] = (m.get("teamOneScore"), m.get("teamTwoScore"))
        n += 1
    return n


def cmd_settle():
    rows = _load()
    if not rows:
        print("Archiv je prázdný — nejdřív `collect`.")
        return
    before = sum(1 for r in rows if r.get("vyhral") is not None)
    n = _settle_batch(rows)
    _save(rows)
    after = sum(1 for r in rows if r.get("vyhral") is not None)
    print(f"Archiv: {len(rows)} záznamů. Vyhodnoceno nově: {n} "
          f"(celkem {after}/{len(rows)}, dřív {before}).")


# ---------------------------------------------------------------------------
# Report — velké vs. malé sázky
# ---------------------------------------------------------------------------
def _grupuj_strepy(rows, okno=180):
    """Spojí střepy jednoho velkého příkazu do jednoho 'fillu'.

    Stejný marketHash + stejná strana + stejný stake v rozestupu <= okno s
    = jeden příkaz (rozdělený na střepy). Bez toho by jeden velký hráč
    vypadal jako stovky malých sázek a statistika by lhala.

    POZOR: bez identity hráče nelze odlišit dva RŮZNÉ hráče, kteří ve stejnou
    chvíli vsadili stejný stake na stejný trh — ti splynou. Je to známé
    omezení, ne chyba.
    """
    def _t(r):
        try:
            return time.mktime(time.strptime(r["betTime"][:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:  # noqa: BLE001
            return 0
    rows = sorted([r for r in rows], key=_t)
    fills, cur = [], None
    for r in rows:
        if (cur and r["marketHash"] == cur["marketHash"]
                and r["strana1"] == cur["strana1"]
                and r["stake"] == cur["stake"]
                and (_t(r) - _t(cur["clenove"][-1])) <= okno):
            cur["clenove"].append(r)
            cur["stake"] = (cur["stake"] or 0) + (r["stake"] or 0)
        else:
            cur = {"clenove": [r], "marketHash": r["marketHash"], "strana1": r["strana1"],
                   "stake": r["stake"], "kurz": r["kurz"], "liga": r["liga"],
                   "typ_trhu": r["typ_trhu"], "vyhral": r.get("vyhral"), "n": 1}
            fills.append(cur)
    for f in fills:
        f["n"] = len(f["clenove"])
        # výsledek fillu: bereme první vyhodnocený střep (všechny jsou stejný trh+strana)
        v = next((c.get("vyhral") for c in f["clenove"] if c.get("vyhral") is not None), None)
        f["vyhral"] = v
    return fills


def cmd_report(okno=180):
    rows = _load()
    if not rows:
        print("Archiv je prázdný — nejdřív `collect` + `settle`.")
        return
    zname = [r for r in rows if r.get("vyhral") is not None and r.get("kurz")]
    fills = _grupuj_strepy(rows, okno)
    fzname = [f for f in fills if f.get("vyhral") is not None and f.get("kurz")]

    print("=" * 66)
    print("ARCHIV SÁZEK Z TAPE — analýza")
    print("=" * 66)
    print(f"Záznamů celkem:            {len(rows)}")
    print(f"  z toho vyhodnocených:    {len(zname)}")
    print(f"  střepů (raw záznamů):    {len(rows)}")
    print(f"  fillů (po spojení):      {len(fills)}")
    print(f"  vyhodnocených fillů:     {len(fzname)}")
    if len(zname) < 200:
        print()
        print("POZOR: vzorek je malý (<200 vyhodnocených). Čísla níže ber jako")
        print("orientační, ne jako důkaz. Nech archiver běžet dýl.")
    print()

    def _pasma(data, klic):
        pasma = [(0, 50), (50, 200), (200, 500), (500, 2000), (2000, 1e18)]
        out = []
        for lo, hi in pasma:
            grp = [r for r in data if r[klic] is not None and lo <= r[klic] < hi]
            if not grp:
                continue
            n = len(grp)
            vyhr = sum(1 for r in grp if r["vyhral"])
            skut = vyhr / n
            impl = sum(1.0 / r["kurz"] for r in grp) / n   # průměrná implikovaná p
            staked = sum(r["stake"] for r in grp)
            returned = sum(r["stake"] * r["kurz"] for r in grp if r["vyhral"])
            roi = (returned - staked) / staked if staked else 0
            label = f"{lo:g}-{hi:g}" if hi < 1e18 else f"{lo:g}+"
            out.append((label, n, skut, impl, skut - impl, roi))
        return out

    print("--- PODLE VELIKOSTI SÁZKY (filly, po spojení střepů) ---")
    print(f"{'USDC':>12} | {'n':>5} | {'skutečná':>9} | {'trh (1/kurz)':>12} | {'rozdíl':>7} | {'ROI':>7}")
    for label, n, skut, impl, rozdil, roi in _pasma(fzname, "stake"):
        print(f"{label:>12} | {n:>5} | {skut:>8.1%} | {impl:>11.1%} | {rozdil:>+6.1%} | {roi:>+6.1%}")
    print()
    print("Výklad: 'rozdíl' = skutečná úspěšnost mínus implikovaná z kurzu.")
    print("  > 0 znamená, že tahle velikost sázky vyhrává častěji, než trh říká")
    print("  (= informovaný směr). < 0 znamená, že prodělává i proti trhu.")
    print()

    # podle trhu
    print("--- PODLE TYPU TRHU (filly) ---")
    by_typ = defaultdict(list)
    for f in fzname:
        by_typ[f.get("typ_trhu") or "?"] .append(f)
    print(f"{'trh':>22} | {'n':>5} | {'skutečná':>9} | {'trh':>7} | {'rozdíl':>7}")
    for typ, grp in sorted(by_typ.items(), key=lambda kv: -len(kv[1]))[:12]:
        n = len(grp)
        skut = sum(1 for r in grp if r["vyhral"]) / n
        impl = sum(1.0 / r["kurz"] for r in grp) / n
        print(f"{typ:>22} | {n:>5} | {skut:>8.1%} | {impl:>6.1%} | {skut - impl:>+6.1%}")
    print()
    print(f"Soubor archivu: {_ARCHIVE}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mod", required=True)
    c = sub.add_parser("collect"); c.add_argument("--sekundy", type=int, default=300)
    c.add_argument("--max", type=int, default=5000); c.add_argument("--verbose", action="store_true")
    sub.add_parser("settle")
    r = sub.add_parser("report"); r.add_argument("--okno-strepy", type=int, default=180)
    run = sub.add_parser("run"); run.add_argument("--sekundy", type=int, default=300)
    run.add_argument("--max", type=int, default=5000); run.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.mod == "collect":
        cmd_collect(args.sekundy, args.max, args.verbose)
    elif args.mod == "settle":
        cmd_settle()
    elif args.mod == "report":
        cmd_report(args.okno_strepy)
    elif args.mod == "run":
        cmd_collect(args.sekundy, args.max, args.verbose)
        cmd_settle()


if __name__ == "__main__":
    main()
