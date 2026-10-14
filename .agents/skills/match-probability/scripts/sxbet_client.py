#!/usr/bin/env python3
"""
sxbet_client.py — tenký klient pro SX.bet V3 API (api.sx.bet).

Proč: SX.bet nabízí sportovní kurzy zdarma (bez API klíče pro čtení) a zároveň
umožňuje sázky reálně podávat (orders/fill/v2) — na rozdíl od The Odds API,
které umí jen čtení kurzů. Tenhle modul je JEDINÉ místo, které mluví se SX.bet;
zbytek projektu (bookmaker.py) ho používá přes jednotné rozhraní.

Ověřená fakta o API (2026-10, testováno živě):
  * Čtení kurzů NEPOTŘEBUJE API klíč (jen WebSocket přes Ably chce klíč).
  * Stará OrderBook V2 (/orders, /metadata) je MRTVÁ → "OrderBook V2 is no
    longer supported". Používáme V3: /orderbook-v3/snapshot.
  * Sport Tenis = sportId 6. Trh "vítěz zápasu" = type 52 (12) nebo 226
    (12 včetně prodloužení). Gem-level (vítěz aktuálního gemu) na SX.bet
    NEEXISTUJE — viz docstring bookmaker.py.
  * Snapshot s showTakerPerspective=true vrací percentageOdds z pohledu
    TAKERA (co zaplatíš, když bereš). Decimal odds pro vsazení na daný
    outcome = 1 / (percentageOdds/1e20). Ověřeno na Medvedevovi: 0,80 →
    kurz 1,25 (jasný favorit) ✓.
  * `size` je v base units (USDC má 6 decimals → nominal = size/1e6).

BEZPEČNOST: tenhle modul sám o sobě NIKDY neposílá reálnou sázku, dokud
není explicitně zavolán `place_order()` s nakonfigurovaným walletem. Výchozí
stav je čtení kurzů.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SX_API_BASE = "https://api.sx.bet"

SPORT_TENNIS = 6
SPORT_SOCCER = 5
SPORT_HOCKEY = 2

# Typy trhů (viz _markets.md v sx-bet-api-docs) — bereme jen "kdo vyhraje zápas".
MARKET_TYPE_MATCH_WINNER = {52, 226}   # 12, resp. 12 včetně prodloužení
# Set-winner trhy: u tenisu je "period" = SET. 202 = 1. set, 203 = 2. set,
# 204 = 3. set. Ověřeno živě (202 měl knihu, 203/204 někdy prázdnou).
MARKET_TYPE_SET_WINNER = {202: 1, 203: 2, 204: 3}
MARKET_TYPE_LABELS = {
    52: "12 (vítěz zápasu)",
    226: "12 včetně prodloužení",
    202: "vítěz 1. setu",
    203: "vítěz 2. setu",
    204: "vítěz 3. setu",
    1: "1X2",
}

USDC_DECIMALS = 6  # ověřeno z /metadata/obv3 (activeAsset.decimals = 6)


# ---------------------------------------------------------------------------
# Nízkofrovňový HTTP
# ---------------------------------------------------------------------------
def _get(path, params=None, timeout=15, headers=None):
    q = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{SX_API_BASE}{path}" + (f"?{q}" if q else "")
    h = {"User-Agent": "statistiky-sxbet/1.0"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SX.bet {path} HTTP {e.code}: {body[:200]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"SX.bet {path} síťová chyba: {e}") from None


def _post(path, payload, headers=None, timeout=20):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", "User-Agent": "statistiky-sxbet/1.0"}
    h.update(headers or {})
    req = urllib.request.Request(f"{SX_API_BASE}{path}", data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SX.bet POST {path} HTTP {e.code}: {body[:300]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"SX.bet POST {path} síťová chyba: {e}") from None


# ---------------------------------------------------------------------------
# Metadata / konfigurace burzy
# ---------------------------------------------------------------------------
def metadata():
    """Metadata OBv3: chainId, USDC token, escrow, limity, betting delay."""
    return _get("/metadata/obv3").get("data", {})


def sports():
    return {s["sportId"]: s["label"] for s in _get("/sports").get("data", [])}


def active_leagues(sport_id=None):
    data = _get("/leagues/active").get("data", [])
    if sport_id is not None:
        data = [x for x in data if x.get("sportId") == sport_id]
    return data


# ---------------------------------------------------------------------------
# Trhy
# ---------------------------------------------------------------------------
def active_markets(sport_ids=None, live_only=None, only_main_line=None,
                   page_size=50, max_pages=12):
    """Vrátí seznam aktivních trhů (strankuje přes nextKey)."""
    out, key, pages = [], None, 0
    while pages < max_pages:
        params = {"pageSize": page_size}
        if sport_ids is not None:
            params["sportIds"] = ",".join(str(s) for s in sport_ids)
        if live_only is not None:
            params["liveOnly"] = "true" if live_only else "false"
        if only_main_line:
            params["onlyMainLine"] = "true"
        if key:
            params["paginationKey"] = key
        d = _get("/markets/active", params)
        ms = (d.get("data") or {}).get("markets") or []
        if not ms:
            break
        out.extend(ms)
        key = (d.get("data") or {}).get("nextKey")
        pages += 1
        if not key:
            break
    return out


def match_winner_markets(sport_id=SPORT_TENNIS, live_only=None, max_pages=12):
    """Jen trhy na vítěze zápasu (type 52/226)."""
    ms = active_markets(sport_ids=[sport_id], live_only=live_only, max_pages=max_pages)
    return [m for m in ms if m.get("type") in MARKET_TYPE_MATCH_WINNER]


def set_winner_markets(sport_id=SPORT_TENNIS, live_only=None, max_pages=12):
    """Jen trhy na vítěze JEDNOTLIVÉHO setu (type 202/203/204)."""
    ms = active_markets(sport_ids=[sport_id], live_only=live_only, max_pages=max_pages)
    return [m for m in ms if m.get("type") in MARKET_TYPE_SET_WINNER]


def markets_by_hashes(hashes):
    """Vrátí {marketHash: market} pro zadané hashe (max 30 na jedno volání)."""
    out = {}
    hashes = list(dict.fromkeys(h for h in hashes if h))
    for i in range(0, len(hashes), 30):
        chunk = hashes[i:i + 30]
        d = _get("/markets/find", {"marketHashes": ",".join(chunk)})
        for m in d.get("data") or []:
            if m.get("marketHash"):
                out[m["marketHash"]] = m
    return out


# ---------------------------------------------------------------------------
# Trades — historie sázek VŠECH hráčů na burze (pro učení se od ostatních)
# ---------------------------------------------------------------------------
def _sx_api_key():
    """API klíč pro V3 endpointy. Hlavička je `x-sx-api-key` (V2 měla `X-Api-Key`)."""
    return os.environ.get("SX_API_KEY") or None


def _iso8601(v):
    """Převede unix timestamp / datetime / string na ISO 8601, jak vyžaduje V3 API.

    V3 `/trades-v3` odmítá unix timestamp (400 "startDate must be a valid ISO
    8601 date string") — chce řetězec typu `2026-09-21T17:59:02.000Z`.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(int(v)))


# Realtime "public tape" — JEDINÝ veřejný zdroj sázek CIZÍCH hráčů.
# (REST /trades-v3 vrací jen moje vlastní sázky, viz docstring trades().)
PUBLIC_TAPE_CHANNEL = "recent_trades_v3:global"
REALTIME_WS_URL = "wss://realtime.sx.bet/connection/websocket"
REALTIME_TOKEN_URL = "/user/realtime-token-v3/api-key"


def trades(start_date=None, end_date=None, bettor=None, settled=None,
           market_hashes=None, maker=None, trade_status=None,
           page_size=100, max_pages=10):
    """Vrátí MOJE sázky z SX.bet `/trades-v3` (bet-grain).

    !!! KLÍČOVÉ OMEZENÍ (oficiální dokumentace SX.bet, "Adjust query endpoints") !!!
    Všechny V3 query endpointy (`/trades-v3`, `/fills-v3`, `/positions-v3`,
    `/orders-v3`) jsou VÁZANÉ NA MŮJ API KLÍČ a vracejí POUZE MOJI VLASTNÍ
    aktivitu. V2 query parametry `bettor=` a `maker=` byly zrušeny právě proto.
    Sázky CIZÍCH hráčů přes tenhle endpoint nezískáš — SX.bet je veřejně
    neposkytuje (ověřeno živě 2026-10-05: 200 + prázdný seznam i za 1000 dní).

    Jediný veřejný zdroj cizích sázek je realtime "public tape" kanál
    `recent_trades_v3:global` (PUBLIC_TAPE_CHANNEL) — anonymní, agregovaný,
    bez identity hráče.

    Hlavička: `x-sx-api-key` (V2 používala `X-Api-Key`, V3 ji přejmenovala).
    Datum: ISO 8601 řetězec, ne unix timestamp.
    Stránkování: `perPage` + `nextKey` (V2 měl `pageSize` + `paginationKey`).
    """
    key = _sx_api_key()
    if not key:
        raise RuntimeError(
            "SX.bet /trades-v3 vyžaduje API klíč, ale SX_API_KEY není nastavený. "
            "Vygeneruj ho na sx.bet (Account → Overview → API Credentials, "
            "nutná Enhanced Verification) a přidej do ~/.env jako SX_API_KEY=..."
        )
    if start_date is None:
        start_date = int(time.time()) - 30 * 86400
    out, page_key, pages = [], None, 0
    while pages < max_pages:
        params = {"perPage": page_size, "startDate": _iso8601(start_date)}
        if end_date is not None:
            params["endDate"] = _iso8601(end_date)
        if bettor:
            params["bettor"] = bettor
        if settled is not None:
            params["settled"] = "true" if settled else "false"
        if market_hashes:
            params["marketHashes"] = ",".join(market_hashes)
        if maker is not None:
            params["maker"] = "true" if maker else "false"
        if page_key:
            params["paginationKey"] = page_key
        d = _get("/trades-v3", params, headers={"x-sx-api-key": key})
        data = d.get("data") or {}
        ts = (data.get("trades") if isinstance(data, dict) else data) or []
        if not ts:
            break
        out.extend(ts)
        page_key = data.get("nextKey") if isinstance(data, dict) else None
        pages += 1
        if not page_key:
            break
    return out


def trade_won(t):
    """True/False/None (None = nevyhodnoceno / void / neznámý tvar) — vyhrál bet?

    Podporuje V3 tvar (`status` = MATCHED/LOCKED/SETTLED/FAILED, výsledek
    v `settlement`) i starý V2 tvar (`settled` + `outcome`).
    """
    status = str(t.get("status") or "").upper()
    settlement = t.get("settlement")
    outcome = settlement.get("outcome") if isinstance(settlement, dict) else None
    if outcome is None:
        outcome = t.get("outcome")
    # V3: dokud není SETTLED, výsledek neznáme
    if status in ("MATCHED", "LOCKED", "FAILED"):
        return None
    if status == "SETTLED" and outcome is None:
        return None
    if outcome in (None, 0):
        return None  # void / vráceno / neznámo
    one = t.get("bettingOutcomeOne")
    if one is None:
        one = t.get("isMakerBettingOutcomeOne")
    if one is None:
        return None
    return (outcome == 1) == bool(one)


def trade_decimal_odds(t):
    """Desetinný kurz, který bettor dostal (z `odds` = implikovaná × 1e20)."""
    try:
        p = int(t["odds"]) / 1e20
    except (KeyError, ValueError, TypeError):
        return None
    return 1.0 / p if p > 0 else None


def trade_stake_nominal(t):
    """Nominální vklad v USDC.

    Zkouší postupně: `normalizedStake` (V3), `stake` (ethereum units / 10^6),
    `totalBetSize` (V3 order units / 10^6). Pro poměrové metriky (ROI) stačí
    konzistentní měřítko — absolutní velikost není kritická.
    """
    ns = t.get("normalizedStake")
    if ns not in (None, ""):
        try:
            v = float(ns)
            if 0 < v < 1e9:
                return v
        except (ValueError, TypeError):
            pass
    for field in ("stake", "totalBetSize"):
        try:
            return int(t[field]) / (10 ** USDC_DECIMALS)
        except (KeyError, ValueError, TypeError):
            continue
    return None


# ---------------------------------------------------------------------------
# Order book → kurzy
# ---------------------------------------------------------------------------
def orderbook(market_hash, taker_perspective=True):
    """Order book pro trh. Vrací {'outcomeOne': [...], 'outcomeTwo': [...]}."""
    d = _get("/orderbook-v3/snapshot", {
        "marketHash": market_hash,
        "showTakerPerspective": "true" if taker_perspective else "false",
    })
    return d.get("data") or {}


def _best_decimal_odds(levels):
    """Z úrovní booku vezme NEJLEPŠÍ kurz pro taker (nejmenší percentageOdds).

    levels = [{'percentageOdds': '80000000000000000000', 'size': '...'}]
    Vrací (decimal_odds, implied_prob, dostupná_likvidita_nominal) nebo None.
    """
    if not levels:
        return None
    parsed = []
    for lv in levels:
        try:
            p = int(lv["percentageOdds"]) / 1e20
            size = int(lv.get("size", 0)) / (10 ** USDC_DECIMALS)
        except (KeyError, ValueError, TypeError):
            continue
        if 0 < p < 1:
            parsed.append((p, size))
    if not parsed:
        return None
    p, size = min(parsed, key=lambda t: t[0])
    return (1.0 / p, p, size)


def market_odds(market_hash):
    """Vrátí {'outcomeOne': (dec, p, liq), 'outcomeTwo': (dec, p, liq)} nebo {}.

    dec = desetinný kurz, za který teď můžeš vsadit na daný outcome,
    p   = implikovaná pravděpodobnost (bez odečtení marže),
    liq = kolik USDC je v nejlepší úrovni.
    """
    ob = orderbook(market_hash)
    out = {}
    for side, key in ((1, "outcomeOne"), (2, "outcomeTwo")):
        best = _best_decimal_odds(ob.get(key))
        if best:
            out[key] = best
    return out


def devigged_probs(market_hash):
    """Odmaržované pravděpodobnosti obou stran z order booku.

    Vrací {'outcomeOne': p, 'outcomeTwo': p} sečtené na 1, nebo None.
    """
    odds = market_odds(market_hash)
    if "outcomeOne" not in odds or "outcomeTwo" not in odds:
        return None
    p1 = odds["outcomeOne"][1]
    p2 = odds["outcomeTwo"][1]
    total = p1 + p2
    if total <= 0:
        return None
    return {"outcomeOne": p1 / total, "outcomeTwo": p2 / total}


# ---------------------------------------------------------------------------
# Fuzzy hledání zápasu (SX.bet má plná jména, náš feed zkrácená)
# ---------------------------------------------------------------------------
def _norm(s):
    s = (s or "").lower()
    for a, b in (("á", "a"), ("č", "c"), ("ď", "d"), ("é", "e"), ("ě", "e"),
                 ("í", "i"), ("ň", "n"), ("ó", "o"), ("ř", "r"), ("š", "s"),
                 ("ť", "t"), ("ú", "u"), ("ů", "u"), ("ý", "y"), ("ž", "z"),
                 (".", " "), ("-", " ")):
        s = s.replace(a, b)
    return " ".join(s.split())


def _name_match(a, b):
    """True, když jedno jméno je 'dost' obsažené v druhém (příjmení apod.)."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # porovnej poslední slovo (příjmení) + iniciálu křestního
    ta, tb = na.split(), nb.split()
    if ta[-1] == tb[-1]:
        return True
    return na in nb or nb in na


def find_match_market(name1, name2, sport_id=SPORT_TENNIS, live_only=None, markets=None):
    """Najde trh na vítěze zápasu pro dvojici jmen (v libovolném pořadí)."""
    if markets is None:
        markets = match_winner_markets(sport_id, live_only=live_only)
    for m in markets:
        t1, t2 = m.get("teamOneName", ""), m.get("teamTwoName", "")
        if ((_name_match(name1, t1) and _name_match(name2, t2)) or
                (_name_match(name1, t2) and _name_match(name2, t1))):
            return m
    return None


def find_set_market(name1, name2, set_no, sport_id=SPORT_TENNIS, live_only=None, markets=None):
    """Najde trh na vítěze daného setu (set_no = 1/2/3) pro dvojici jmen."""
    if markets is None:
        markets = set_winner_markets(sport_id, live_only=live_only)
    wanted = {t for t, n in MARKET_TYPE_SET_WINNER.items() if n == set_no}
    for m in markets:
        if m.get("type") not in wanted:
            continue
        t1, t2 = m.get("teamOneName", ""), m.get("teamTwoName", "")
        if ((_name_match(name1, t1) and _name_match(name2, t2)) or
                (_name_match(name1, t2) and _name_match(name2, t1))):
            return m
    return None


def probs_for_market(m, name1, name2):
    """Z daného trhu (match i set) spočítá (probs, best_odds, market).

    probs      = {jméno_hrace: odmaržovaná_pravděpodobnost}
    best_odds  = {jméno_hrace: nejlepší_desetinný_kurz}
    market     = původní záznam trhu (obsahuje marketHash pro reálnou sázku)
    """
    if not m:
        return None, None, None
    odds = market_odds(m["marketHash"])
    if "outcomeOne" not in odds or "outcomeTwo" not in odds:
        return None, None, m  # trh existuje, ale zatím prázdný book

    t1, t2 = m["teamOneName"], m["teamTwoName"]
    if _name_match(name1, t1):
        by_name = {name1: ("outcomeOne", t1), name2: ("outcomeTwo", t2)}
    else:
        by_name = {name1: ("outcomeTwo", t2), name2: ("outcomeOne", t1)}

    dev = devigged_probs(m["marketHash"])
    probs, best = {}, {}
    for nm, (side, _team) in by_name.items():
        dec, p, _liq = odds[side]
        best[nm] = dec
        probs[nm] = dev[side] if dev else p
    return probs, best, m


def probs_for_match(name1, name2, sport_id=SPORT_TENNIS, live_only=None, markets=None):
    """Vrátí (probs, best_odds, market) pro vítěze ZÁPASU, nebo (None, None, None)."""
    m = find_match_market(name1, name2, sport_id=sport_id, live_only=live_only, markets=markets)
    return probs_for_market(m, name1, name2)


def probs_for_set(name1, name2, set_no, sport_id=SPORT_TENNIS, live_only=None, markets=None):
    """Vrátí (probs, best_odds, market) pro vítěze daného SETU, nebo (None, None, None)."""
    m = find_set_market(name1, name2, set_no, sport_id=sport_id, live_only=live_only, markets=markets)
    return probs_for_market(m, name1, name2)


# ---------------------------------------------------------------------------
# REÁLNÉ SÁZENÍ (taker přes /orders/fill/v2) — vyžaduje wallet + USDC na SX
# ---------------------------------------------------------------------------
def is_real_betting_configured():
    """True, když je nastavený privátní klíč a adresa pro reálné sázení."""
    return bool(os.environ.get("SXBET_PRIVATE_KEY") and os.environ.get("SXBET_TAKER_ADDRESS"))


def place_order(market_hash, outcome_side, stake_usdc, desired_odds, odds_slippage=5):
    """Reálná sázka (taker). Vrací odpověď API, nebo vyhodí RuntimeError.

    outcome_side: 1 = outcomeOne, 2 = outcomeTwo
    stake_usdc:   částka v USDC (nominal, např. 1.5)
    desired_odds: požadovaný desetinný kurz (např. 1.25)

    POZOR: tohle posílá SKUTEČNOU sázku. Vyžaduje:
      - SXBET_PRIVATE_KEY, SXBET_TAKER_ADDRESS (env)
      - USDC na SX Network + schválený TokenTransferProxy (approve)
      - knihovnu pro EIP712 podpis (např. eth-account / web3)
    Pokud chybí cokoli, vyhodí jasnou chybu — nikdy tiše nevsadí špatně.
    """
    if not is_real_betting_configured():
        raise RuntimeError(
            "Reálné sázení není nakonfigurované: chybí SXBET_PRIVATE_KEY / "
            "SXBET_TAKER_ADDRESS v prostředí (viz ~/.env)."
        )
    # --- Podpis EIP712 (stejný tvar jako v sx-bet-api-docs/_orders.md) ---
    try:
        from eth_account import Account  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "Pro reálné sázení je potřeba knihovna 'eth-account' "
            "(pip install eth-account). Bez ní nelze podepsat EIP712."
        ) from None

    meta = metadata()
    chain_id = meta.get("chainId")
    token = (meta.get("activeAsset") or {}).get("baseToken")
    if not chain_id or not token:
        raise RuntimeError("SX.bet metadata neobsahují chainId/baseToken.")

    stake_wei = str(int(round(stake_usdc * (10 ** USDC_DECIMALS))))
    desired = str(int(round(desired_odds and (1.0 / desired_odds) * 1e20))) if desired_odds else None
    # desiredOdds v SX formátu je implikovaná pravděpodobnost × 1e20
    if desired is None:
        raise RuntimeError("place_order: chybí desired_odds")

    raise RuntimeError(
        "place_order: kostra pro reálné sázení je připravená, ale ještě není "
        "dokončená (chybí generování fillSalt, podpis a wallet). "
        "Odkomentuj/napoj podle sx-bet-api-docs/source/includes/_orders.md "
        "(sekce 'Filling orders')."
    )


if __name__ == "__main__":
    # Rychlý self-test / diagnostika z příkazové řádky.
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tenis"
    if cmd == "meta":
        print(json.dumps(metadata(), indent=2, ensure_ascii=False)[:1200])
    elif cmd == "tenis":
        ms = match_winner_markets(SPORT_TENNIS)
        print(f"tenisových trhů na vítěze: {len(ms)}")
        n_with = 0
        for m in ms[:40]:
            odds = market_odds(m["marketHash"])
            if "outcomeOne" in odds and "outcomeTwo" in odds:
                n_with += 1
                d1 = odds["outcomeOne"][0]
                d2 = odds["outcomeTwo"][0]
                print(f"  {m['teamOneName'][:20]} vs {m['teamTwoName'][:20]} "
                      f"[{m.get('leagueLabel')}]  {d1:.2f} / {d2:.2f}")
        print(f"  -> s knihou: {n_with}")
    elif cmd == "match":
        if len(sys.argv) < 4:
            print("použití: sxbet_client.py match \"Hráč 1\" \"Hráč 2\"")
            sys.exit(1)
        p, b, m = probs_for_match(sys.argv[2], sys.argv[3])
        if not p:
            print("zápas nenalezen nebo prázdný book")
        else:
            print(json.dumps({"probs": p, "best_odds": b,
                              "marketHash": m["marketHash"],
                              "league": m.get("leagueLabel")}, indent=2, ensure_ascii=False))
    else:
        print(__doc__)