#!/usr/bin/env python3
"""
executor.py — univerzální spouštěč AKTIVNÍCH agentů z `../agents.json`.

Jediné místo, které ví, jak propojit registr agentů (agents.py) se
skutečnými sázecími skripty. Cron i ruční spuštění volají jen tenhle skript;
ten si přečte registry, pro každého agenta s `active: true` nastaví
odpovídající modulové konstanty (banka, vklad, prahy) z jeho konfigurace
a spustí příslušnou strategii s agentovým vlastním logem.

Mapování strategie -> akce:
  match_fav  -> live_tennis_simulator: nejdřív settlement (bet_evaluator),
                pak watch (vítěz celého zápasu, silný favorit)
  gem        -> live_game_bet.cmd_tick (vítěz aktuálního gemu)
  gem_aggr   -> live_game_bet.cmd_aggressive_tick (celá banka na gem)

Bez aktivních agentů nedělá nic (a nic nestojí na API kvótě).
"""
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

import agents as reg                      # noqa: E402
import live_tennis_simulator as base      # noqa: E402
import live_game_bet as gem               # noqa: E402
import bookmaker as bm                    # noqa: E402


def _run_match_fav(a, cfg):
    base.LOG_PATH = reg.log_path(a)
    base.STARTING_BANK = float(a["bank"])
    base.STAKE_PCT = float(cfg["stake_pct"])
    base.MIN_STAKE = float(cfg["min_stake"])
    base.MAX_EXPOSURE_PCT = float(cfg["max_exposure_pct"])
    base.FAV_MODEL_MIN = float(cfg["fav_model_min"])
    base.FAV_MARKET_MIN = float(cfg["fav_market_min"])
    base.FAV_MAX_ODDS = float(cfg["fav_max_odds"])
    # settlement dohraných tiketů (bet_evaluator používá sim.LOG_PATH)
    import bet_evaluator as ev
    ev.settle_pending()
    base.cmd_watch()


def _run_gem(a, cfg):
    gem.LOG_PATH = reg.log_path(a)
    gem.STARTING_BANK = float(a["bank"])
    gem.STAKE_PCT = float(cfg["stake_pct"])
    gem.MIN_STAKE = float(cfg["min_stake"])
    gem.MAX_EXPOSURE_PCT = float(cfg["max_exposure_pct"])
    gem.GAME_FAV_MIN = float(cfg["game_fav_min"])
    gem.cmd_tick()


def _run_gem_aggr(a, cfg):
    gem.AGGR_LOG_PATH = reg.log_path(a)
    gem.STARTING_BANK = float(a["bank"])
    gem.AGGR_STAKE_FRACTION = float(cfg["stake_fraction"])
    gem.AGGR_PROFIT_TARGET = float(cfg["profit_target"])
    gem.AGGR_TRAILING_STOP = float(cfg["trailing_stop"])
    gem.AGGR_MIN_STAKE = float(cfg["min_stake"])
    gem.MIN_STAKE = float(cfg["min_stake"])
    gem.GAME_FAV_MIN = float(cfg["game_fav_min"])
    gem.cmd_aggressive_tick()


_RUNNERY = {
    "match_fav": _run_match_fav,
    "gem": _run_gem,
    "gem_aggr": _run_gem_aggr,
}


def run_all(only=None):
    r = reg.load_registry()
    akt = [a for a in r["agents"] if a.get("active") and (only is None or a["id"] == only)]
    if not akt:
        print("Žádní aktivní agenti (vše vypnuto v agents.json).")
        return 0
    print(f"Spouštím aktivní agenty: {len(akt)}")
    for a in akt:
        cfg = reg.effective_config(a, r)
        run = _RUNNERY.get(a["strategy"])
        print(f"\n===== agent {a['id']} ({a['strategy']}) "
              f"banka {a['bank']:.0f} log {os.path.basename(a['log'])} =====")
        if run is None:
            print(f"  neznámá strategie: {a['strategy']}")
            continue
        # V REÁLNÉM režimu nelze sázet gem strategie (SX.bet nemá trh na gem)
        # — v sim režimu v pořádku (jen papírové tikety).
        if bm.is_real() and not bm.strategy_can_bet_real(a["strategy"]):
            print(f"  PŘESKOČENO: strategie '{a['strategy']}' neumí reálné sázení "
                  f"na SX.bet (chybí trh na vítěze gemu).")
            continue
        try:
            run(a, cfg)
        except SystemExit as e:
            print(f"  (agent {a['id']} ukončen: {e})")
        except Exception as e:
            print(f"  CHYBA u agenta {a['id']}: {e}")
    return 0


def main():
    only = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--only" else None
    sys.exit(run_all(only))


if __name__ == "__main__":
    main()
