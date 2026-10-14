#!/usr/bin/env python3
"""
bookmaker.py — jednotné rozhraní pro zdroj kurzů + podávání sázek.

Cíl (přání uživatele): nasměrovat simulátor na SX.bet (kurzy zdarma přes API,
navíc umí reálné sázení) a udělat to tak, aby později bylo JEDNODUCHÉ přepnout
ze simulace na reálné sázení — ideálně změnou jedné proměnné.

Přepínač: proměnná prostředí BOOKMAKER (v ~/.env), hodnoty:
  * "sxbet_sim"  (VÝCHOZÍ) — čte ŽIVÉ KURZY ze SX.bet, ale sází "na papír"
                             (fiktivní banka, reálná sázka se NEPOSÍLÁ).
  * "sxbet_real"           — čte kurzy ze SX.bet A posílá REÁLNOU sázku
                             (vyžaduje SXBET_PRIVATE_KEY, SXBET_TAKER_ADDRESS,
                             USDC na SX Network; viz sxbet_client.place_order).
  * "oddsapi"              — starý zdroj (The Odds API, jen čtení kurzů) —
                             fallback, když SX.bet nemá daný zápas.

DŮLEŽITÉ OMEZENÍ (říkám na rovinu): SX.bet nabízí trhy na VÍTĚZE ZÁPASU a na
sety/hry, ale NE na vítěze JEDNOTLIVÉHO GEMU. Proto:
  - match-level agent (match_fav) MŮŽE jet přes SX.bet (trh type 52/226),
  - gem-level agenti (gem, gem_aggr) přes SX.bet jet NEMOHOU (žádný trh) —
    pro ně zůstává starý zdroj živých kurzů, případně se přeskočí.

Rozhraní (co používají sázecí skripty):
  get_market_probs(name1, name2) -> (probs, best_odds)   # jako dřív
  place_bet(name1, name2, pick, odds, stake, market=None) -> dict
      # v sim režimu jen zaloguje "papírovou" sázku a vrátí {'mode':'sim',...}
      # v real režimu pošle skutečnou sázku na SX.bet
  source_name() -> str
  is_real() -> bool
"""
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

import sxbet_client as sx  # noqa: E402


def mode():
    """Aktivní režim: sxbet_sim (výchozí), sxbet_real, oddsapi."""
    return os.environ.get("BOOKMAKER", "sxbet_sim").strip().lower()


def is_real():
    return mode() == "sxbet_real"


# Strategie, které UMÍ reálně sázet přes SX.bet (mají trh na vítěze zápasu).
# Gem-level strategie (gem, gem_aggr) sázejí na vítěze GEMU, což SX.bet
# nenabízí — reálně je sázet NELZE, v real režimu se musí přeskočit.
REAL_CAPABLE_STRATEGIES = {"match_fav", "set_fav"}


def strategy_can_bet_real(strategy):
    """True, když daná strategie umí reálnou sázku na SX.bet."""
    return strategy in REAL_CAPABLE_STRATEGIES


def source_name():
    return {
        "sxbet_sim": "SX.bet (kurzy živě, sázky na papír)",
        "sxbet_real": "SX.bet (kurzy živě, sázky REÁLNÉ)",
        "oddsapi": "The Odds API (jen kurzy)",
    }.get(mode(), mode())


# ---------------------------------------------------------------------------
# Kurzy
# ---------------------------------------------------------------------------
def get_market_info(name1, name2, sport="tenis"):
    """Vrátí (probs, best_odds, market, source) na JEDEN dotaz.

    probs      = {jméno: odmaržovaná pravděpodobnost}
    best_odds  = {jméno: nejlepší desetinný kurz}
    market     = záznam SX.bet trhu (marketHash pro reálnou sázku) nebo None
    source     = "sxbet" | "oddsapi" | None
    """
    m = mode()
    if m in ("sxbet_sim", "sxbet_real"):
        try:
            probs, best, market = sx.probs_for_match(name1, name2)
            if probs:
                return probs, best, market, "sxbet"
        except Exception as e:
            print(f"  [bookmaker] SX.bet chyba: {e}")
        # fallback na Odds API, když SX.bet nemá zápas
        m = "oddsapi"
    if m == "oddsapi":
        probs, best = _oddsapi_probs(name1, name2)
        return probs, best, None, "oddsapi"
    return None, None, None, None


def get_set_market_info(name1, name2, set_no, sport="tenis"):
    """Kurzy na vítěze JEDNOTLIVÉHO setu (SX.bet trhy 202/203/204).

    Vrací (probs, best_odds, market, source) nebo (None, None, None, None).
    The Odds API set markets NEMÁ, takže fallback na oddsapi tady neexistuje.
    """
    if mode() in ("sxbet_sim", "sxbet_real"):
        try:
            probs, best, market = sx.probs_for_set(name1, name2, set_no)
            if probs:
                return probs, best, market, "sxbet"
        except Exception as e:
            print(f"  [bookmaker] SX.bet set chyba: {e}")
    return None, None, None, None


def market_by_hash(market_hash):
    """Vrátí záznam trhu z SX.bet podle marketHash (pro settlement reálných sázek)."""
    for m in sx.match_winner_markets(max_pages=12):
        if m.get("marketHash") == market_hash:
            return m
    return None


def get_market_probs(name1, name2, sport="tenis"):
    """Zpětně kompatibilní varianta — jen (probs, best_odds)."""
    probs, best, _market, _src = get_market_info(name1, name2, sport)
    return probs, best


def _oddsapi_probs(name1, name2):
    """Starý zdroj — The Odds API (jen čtení)."""
    try:
        import live_tennis_simulator as base
        return base.get_market_probs(name1, name2)
    except Exception as e:
        print(f"  [bookmaker] Odds API chyba: {e}")
        return None, None


def outcome_side_for(pick_name, market):
    """Vrátí 1 (outcomeOne) nebo 2 (outcomeTwo) pro daný hráčský výběr.

    Používá se pro reálnou sázku na SX.bet (viz sxbet_client.place_order).
    """
    if not market:
        return None
    return 1 if sx._name_match(pick_name, market.get("teamOneName", "")) else 2


def find_market(name1, name2, sport="tenis"):
    """Vrátí záznam trhu na SX.bet (obsahuje marketHash) nebo None."""
    _p, _b, market, _src = get_market_info(name1, name2, sport)
    return market


# ---------------------------------------------------------------------------
# Sázení
# ---------------------------------------------------------------------------
def place_bet(name1, name2, pick, odds, stake, market=None, outcome_side=None):
    """Podá sázku podle aktivního režimu.

    V 'sxbet_sim'  → jen vrátí potvrzení "papírové" sázky (nic se neposílá).
    V 'sxbet_real' → pošle REÁLNOU sázku na SX.bet přes orders/fill/v2.

    stake je ve fiktivních mincích (sim) nebo v USDC (real) — volající rozhoduje.
    """
    if mode() == "sxbet_real":
        if market is None or outcome_side is None:
            raise RuntimeError(
                "place_bet (real): chybí market/outcome_side — nelze poslat "
                "reálnou sázku bez marketHash a strany."
            )
        resp = sx.place_order(
            market_hash=market["marketHash"],
            outcome_side=outcome_side,
            stake_usdc=stake,
            desired_odds=odds,
        )
        return {"mode": "real", "response": resp}

    # sim / oddsapi → papírová sázka
    return {"mode": "sim", "note": "fiktivní sázka, reálný účet nedotčen"}


if __name__ == "__main__":
    print(f"režim: {mode()}  ({source_name()})")
    print(f"reálné sázení nakonfigurováno: {sx.is_real_betting_configured()}")
    print(f"strategie schopné reálné sázky: {sorted(REAL_CAPABLE_STRATEGIES)}")
    if len(sys.argv) >= 3:
        p, b = get_market_probs(sys.argv[1], sys.argv[2])
        print("probs:", p)
        print("odds:", b)