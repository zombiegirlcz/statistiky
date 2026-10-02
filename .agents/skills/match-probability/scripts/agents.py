#!/usr/bin/env python3
"""
agents.py — registr sázejících agentů a hlavní (uživatelské) banky.

Každý agent má:
  * id        — krátký slug (např. 'match-fav', 'gem-agr-2')
  * name      — zobrazované jméno
  * strategy  — 'match_fav' (vítěz zápasu, silný favorit), 'gem' (vítěz gemu),
                'gem_aggr' (agresivní gem, celá banka)
  * bank      — kolik mincí je agentovi PŘIDĚLENO (alokace z hlavní banky)
  * log       — cesta k jsonl logu tiketů agenta (relativní k ..)
  * active    — jestli ho má cron/executor spouštět

HLAVNÍ BANKA (user_bank): virtuální rozpočet, ze kterého se agentům přiděluje.
Soubor `agents.json` v adresáři skillu (..). Peníze se mezi user_bank a agenty
přesouvají operacemi fund/defund — nikdy nevznikají ani nemizí.

Tenhle modul je jediné místo, kde se s registrem manipuluje; main.py ho jen
volá. Drží se principu projektu: JSON soubor = jediný zdroj pravdy, skripty
jsou bezstavové.
"""
import json
import os
import re
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_SCRIPT_DIR, "..")
REGISTRY_PATH = os.path.join(_DATA_DIR, "agents.json")
AGENTS_DIR = os.path.join(_DATA_DIR, "agents")

STARTING_USER_BANK = 10000.0  # výchozí hlavní banka

# Každá strategie má:
#   nazev    - popis do menu
#   log      - výchozí log (jen pro zakládání; agent si nese vlastní)
#   mod/tick - které funkce executor.py volá (jen dokumentačně)
#   defaults - výchozí LADITELNÉ parametry (config). Klíče odpovídají
#              konstantám v sázecích modulech; executor je z nich nastavuje.
#   popisky  - český popisek + rozsah pro každý config klíč (pro TUI).
STRATEGIE = {
    "match_fav": {
        "nazev": "Match-level: silný favorit (vítěz celého zápasu)",
        "log": "live_bets_log.jsonl",
        "mod": "live_tennis_simulator",
        "tick": "watch",
        "defaults": {
            "stake_pct": 0.02, "min_stake": 10.0, "max_exposure_pct": 0.25,
            "fav_model_min": 0.75, "fav_market_min": 0.65, "fav_max_odds": 1.60,
        },
        "popisky": {
            "stake_pct": ("Vklad jako podíl banky", 0.001, 1.0, "např. 0.02 = 2 %"),
            "min_stake": ("Minimální vklad (mincí)", 1, 100000, ""),
            "max_exposure_pct": ("Max. podíl banky v souběžných tiketech", 0.01, 1.0, ""),
            "fav_model_min": ("Min. šance podle modelu", 0.01, 1.0, "např. 0.75"),
            "fav_market_min": ("Min. šance podle trhu", 0.01, 1.0, "např. 0.65"),
            "fav_max_odds": ("Max. kurz", 1.01, 100.0, "nad tímhle se nesází"),
        },
    },
    "gem": {
        "nazev": "Gem-level: vítěz aktuálního gemu",
        "log": "live_game_bets_log.jsonl",
        "mod": "live_game_bet",
        "tick": "tick",
        "defaults": {
            "stake_pct": 0.02, "min_stake": 10.0, "max_exposure_pct": 0.50,
            "game_fav_min": 0.70,
        },
        "popisky": {
            "stake_pct": ("Vklad jako podíl banky", 0.001, 1.0, "např. 0.02 = 2 %"),
            "min_stake": ("Minimální vklad (mincí)", 1, 100000, ""),
            "max_exposure_pct": ("Max. podíl banky v souběžných tiketech", 0.01, 1.0, ""),
            "game_fav_min": ("Min. pravděpodobnost výhry gemu", 0.01, 1.0, "např. 0.70"),
        },
    },
    "gem_aggr": {
        "nazev": "Gem-level AGRESIVNÍ: celá banka na gem",
        "log": "live_game_bet_aggressive_log.jsonl",
        "mod": "live_game_bet",
        "tick": "agresivni-tick",
        "defaults": {
            "stake_fraction": 1.00, "profit_target": 6000.0,
            "trailing_stop": 1000.0, "min_stake": 10.0, "game_fav_min": 0.70,
        },
        "popisky": {
            "stake_fraction": ("Podíl banky na tiket (1.0 = celá)", 0.01, 1.0, ""),
            "profit_target": ("Cílový násobek startu (mincí)", 10, 1000000, "ochranná fáze"),
            "trailing_stop": ("Stop: pokles od vrcholu (mincí)", 1, 1000000, ""),
            "min_stake": ("Minimální vklad (mincí)", 1, 100000, ""),
            "game_fav_min": ("Min. pravděpodobnost výhry gemu", 0.01, 1.0, "např. 0.70"),
        },
    },
    "set_fav": {
        "nazev": "Set-level: silný favorit na vítěze AKTUÁLNÍHO setu",
        "log": "live_set_bets_log.jsonl",
        "mod": "live_tennis_simulator",
        "tick": "set-watch",
        "defaults": {
            "stake_pct": 0.02, "min_stake": 10.0, "max_exposure_pct": 0.25,
            "set_fav_model_min": 0.62, "set_fav_market_min": 0.55, "set_fav_max_odds": 2.00,
        },
        "popisky": {
            "stake_pct": ("Vklad jako podíl banky", 0.001, 1.0, "např. 0.02 = 2 %"),
            "min_stake": ("Minimální vklad (mincí)", 1, 100000, ""),
            "max_exposure_pct": ("Max. podíl banky v souběžných tiketech", 0.01, 1.0, ""),
            "set_fav_model_min": ("Min. šance na výhru setu dle modelu", 0.01, 1.0, "např. 0.62"),
            "set_fav_market_min": ("Min. šance na výhru setu dle trhu", 0.01, 1.0, "např. 0.55"),
            "set_fav_max_odds": ("Max. kurz", 1.01, 100.0, "nad tímhle se nesází"),
        },
    },
}


def effective_config(agent, reg_dict=None):
    """Sloučí výchozí parametry strategie s tím, co má agent uložené
    v `config`. Co uživatel nezměnil, zůstane default. Vrací plný dict."""
    defaults = dict(STRATEGIE[agent["strategy"]]["defaults"])
    ulozene = agent.get("config") or {}
    defaults.update({k: v for k, v in ulozene.items() if k in defaults})
    return defaults


def _vychozi_registry():
    """Základní registr odpovídající stavu před zavedením správy agentů:
    tři už existující banky + volná hlavní banka."""
    return {
        "user_bank": STARTING_USER_BANK,
        "agents": [
            {"id": "match-fav", "name": "Match-level favorit", "strategy": "match_fav",
             "bank": 1000.0, "log": STRATEGIE["match_fav"]["log"], "active": True,
             "created_at": None},
            {"id": "gem", "name": "Gem-level", "strategy": "gem",
             "bank": 1000.0, "log": STRATEGIE["gem"]["log"], "active": True,
             "created_at": None},
            {"id": "gem-agr", "name": "Gem-level agresivní", "strategy": "gem_aggr",
             "bank": 1000.0, "log": STRATEGIE["gem_aggr"]["log"], "active": True,
             "created_at": None},
        ],
    }


def load_registry():
    try:
        with open(REGISTRY_PATH) as f:
            reg = json.load(f)
        reg.setdefault("user_bank", STARTING_USER_BANK)
        reg.setdefault("agents", [])
        return reg
    except FileNotFoundError:
        return _vychozi_registry()
    except Exception:
        return _vychozi_registry()


def save_registry(reg):
    tmp = REGISTRY_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, REGISTRY_PATH)


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or f"agent-{int(time.time())}"


def unikatni_id(reg, zaklad):
    ids = {a["id"] for a in reg["agents"]}
    if zaklad not in ids:
        return zaklad
    i = 2
    while f"{zaklad}-{i}" in ids:
        i += 1
    return f"{zaklad}-{i}"


def add_agent(name, strategy, amount, reg=None):
    """Založí nového agenta s danou strategií a přidělí mu `amount` z hlavní
    banky. Nový agent dostane vlastní log v agents/<id>.jsonl."""
    reg = reg or load_registry()
    if strategy not in STRATEGIE:
        raise ValueError(f"neznámá strategie: {strategy}")
    if amount <= 0:
        raise ValueError("částka musí být kladná")
    if amount > reg["user_bank"] + 1e-9:
        raise ValueError(f"v hlavní bance není dost: {reg['user_bank']:.0f} < {amount:.0f}")

    aid = unikatni_id(reg, _slug(name))
    log_name = os.path.join("agents", f"{aid}.jsonl")
    os.makedirs(AGENTS_DIR, exist_ok=True)
    open(os.path.join(_DATA_DIR, log_name), "a").close()

    reg["agents"].append({
        "id": aid, "name": name, "strategy": strategy,
        "bank": float(amount), "log": log_name, "active": True,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config": {},
    })
    reg["user_bank"] -= amount
    save_registry(reg)
    return aid


def fund_agent(aid, amount, reg=None):
    """Přesune `amount` z hlavní banky agentovi."""
    reg = reg or load_registry()
    a = _najdi(reg, aid)
    if amount <= 0:
        raise ValueError("částka musí být kladná")
    if amount > reg["user_bank"] + 1e-9:
        raise ValueError(f"v hlavní bance není dost: {reg['user_bank']:.0f} < {amount:.0f}")
    reg["user_bank"] -= amount
    a["bank"] += amount
    save_registry(reg)


def defund_agent(aid, amount, reg=None):
    """Přesune `amount` z agenta zpět do hlavní banky (nejvýš kolik má alokováno)."""
    reg = reg or load_registry()
    a = _najdi(reg, aid)
    if amount <= 0:
        raise ValueError("částka musí být kladná")
    if amount > a["bank"] + 1e-9:
        raise ValueError(f"agent má alokováno jen {a['bank']:.0f}")
    a["bank"] -= amount
    reg["user_bank"] += amount
    save_registry(reg)


def remove_agent(aid, reg=None, vratit=True):
    """Odstraní agenta; jeho alokaci vrátí do hlavní banky (vratit=True)."""
    reg = reg or load_registry()
    a = _najdi(reg, aid)
    if vratit:
        reg["user_bank"] += a["bank"]
    reg["agents"] = [x for x in reg["agents"] if x["id"] != aid]
    save_registry(reg)


def set_active(aid, active, reg=None):
    reg = reg or load_registry()
    _najdi(reg, aid)["active"] = bool(active)
    save_registry(reg)


def set_config(aid, klic, hodnota, reg=None):
    """Uloží jeden laditelný parametr agenta (validuje proti STRATEGIE)."""
    reg = reg or load_registry()
    a = _najdi(reg, aid)
    defaults = STRATEGIE[a["strategy"]]["defaults"]
    if klic not in defaults:
        raise ValueError(f"neznámý parametr {klic} pro strategii {a['strategy']}")
    a.setdefault("config", {})
    a["config"][klic] = hodnota
    save_registry(reg)


def reset_config(aid, reg=None):
    """Vymaže uživatelské úpravy configu (zpět na defaulty strategie)."""
    reg = reg or load_registry()
    _najdi(reg, aid)["config"] = {}
    save_registry(reg)


def _najdi(reg, aid):
    for a in reg["agents"]:
        if a["id"] == aid:
            return a
    raise KeyError(f"agent '{aid}' neexistuje")


def log_path(agent):
    """Absolutní cesta k logu agenta."""
    p = agent["log"]
    return p if os.path.isabs(p) else os.path.join(_DATA_DIR, p)


def souhrn():
    """Vrátí dict: user_bank, alokovano (součet bank agentů), celkem."""
    reg = load_registry()
    alok = sum(a["bank"] for a in reg["agents"])
    return {"user_bank": reg["user_bank"], "alokovano": alok,
            "celkem": reg["user_bank"] + alok, "n_agentu": len(reg["agents"])}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        save_registry(_vychozi_registry())
        print(f"Registr vytvořen: {REGISTRY_PATH}")
    else:
        s = souhrn()
        print(f"Hlavní banka: {s['user_bank']:.0f}")
        print(f"Alokováno agentům: {s['alokovano']:.0f} ({s['n_agentu']} agentů)")
        print(f"Celkem: {s['celkem']:.0f}")
        for a in load_registry()["agents"]:
            print(f"  [{a['id']:<12}] {a['name']:<26} {a['strategy']:<10} {a['bank']:>8.0f}")