#!/usr/bin/env python3
"""
Pravdepodobnost, ze KONKRETNI HRAC da v nadchazejicim zapase gol (trh
"strelec golu" / "hrac da gol vcetne prodlouzeni" u sazkovych kancelari).

Model: Poissonovo rozdeleni z hracovy VLASTNI sezonni strelecke frekvence
(goly / odehrane zapasy), vazene pres posledni 1-2 sezony (aktualni sezona
vaha 70 %, predchozi 30 %, pokud obe existuji). P(alespon 1 gol) = 1 - e^-lambda.

DULEZITE OMEZENI (vzdy rict uzivateli):
- Model NEZOHLEDNUJE soupere (obranu/brankare), jen hracovu vlastni formu.
  Je to tedy hruby odhad, ne presna tr2nicni cena - u sazkovych kancelari
  se do kurzu promita i sila souperovy obrany, forma branka8e, ocekavany
  pocet startu v sestave atd., coz tenhle skript nevidi.
- Male vzorky (malo odehranych zapasu v sezone) delaji odhad nespolehlivy -
  skript na to upozorni, pokud je zapasu min nez ~10.
- Fotbal: pokryti jen 11 nejvyssich evropskych lig (viz player_profile.py).
  Hokej: cela NHL.

Pouziti:
    python3 goalscorer_prob.py fotbal "Erling Haaland"
    python3 goalscorer_prob.py hokej "William Nylander"
    python3 goalscorer_prob.py hokej "Nylander William"   # i v poradi prijmeni jmeno (format tiketu)
"""
import csv
import glob
import math
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from aggregate_stats import fuzzy_pick  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPT_DIR))))

MIN_GAMES_RELIABLE = 10


def load_csv(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def poisson_at_least_one(lam):
    return 1 - math.exp(-lam)


def weighted_rate(seasons_goals_games):
    """seasons_goals_games: list of (season_str, goals, games), sorted nejstarsi->nejnovejsi."""
    seasons_goals_games = [s for s in seasons_goals_games if s[2] > 0]
    if not seasons_goals_games:
        return None, 0
    last_two = seasons_goals_games[-2:]
    if len(last_two) == 2:
        (_, g_prev, n_prev), (_, g_cur, n_cur) = last_two
        rate_prev = g_prev / n_prev
        rate_cur = g_cur / n_cur
        lam = 0.7 * rate_cur + 0.3 * rate_prev
        games_used = n_cur + n_prev
    else:
        _, g_cur, n_cur = last_two[0]
        lam = g_cur / n_cur
        games_used = n_cur
    return lam, games_used


def show_football(name):
    players = load_csv(os.path.join(BASE, "fotbal", "hraci", "players.csv"))
    id_key = "player_id" if players and "player_id" in players[0] else None
    name_key = "player_name" if players and "player_name" in players[0] else "name"
    names = [p[name_key] for p in players]
    match, _ = fuzzy_pick(name, names, cutoff=0.6)
    if not match:
        print(f"Hrac '{name}' nenalezen ve fotbalovych datech (jen 11 nejvyssich evropskych lig).")
        return
    p = next(pp for pp in players if pp[name_key] == match)
    pid = p[id_key] if id_key else None

    staty = load_csv(os.path.join(BASE, "fotbal", "hraci", "sezonni_staty.csv"))
    my_staty = [s for s in staty if s["player_id"] == pid] if pid else \
        [s for s in staty if s.get("player_name") == match]
    my_staty.sort(key=lambda s: s["season"])
    if not my_staty:
        print(f"'{match}' nalezen, ale nema zadne sezonni staty (goly/zapasy).")
        return

    seasons = [(s["season"], int(s["goals"] or 0), int(s["apps"] or 0)) for s in my_staty]
    lam, games_used = weighted_rate(seasons)
    if lam is None:
        print(f"'{match}': k dispozici jen sezony s 0 starty, nelze spocitat.")
        return

    prob = poisson_at_least_one(lam)
    print(f"\n=== {match} - pravdepodobnost golu v zapase ===")
    for season, goals, apps in seasons[-3:]:
        print(f"  {season}: {goals} golu / {apps} startu" + (f" ({goals/apps:.3f} g/zapas)" if apps else ""))
    print(f"\nVazena strelecka frekvence: {lam:.3f} golu/zapas (z {games_used} zapasu)")
    print(f"Odhad P(da gol v zapase) = 1 - e^-{lam:.3f} = {prob*100:.1f} %")
    if games_used < MIN_GAMES_RELIABLE:
        print(f"POZOR: jen {games_used} zapasu ve vzorku - odhad je malo spolehlivy.")
    print("Pozn.: model NEZOHLEDNUJE souperovu obranu, jen hracovu vlastni formu - bereno jako hrubsi odhad, ne tr2nicni cena.")


def resolve_hockey_name(query, players):
    q_words = set(query.lower().split())
    # 1) presne: vsechna slova dotazu se musi objevit v jmene/prijmeni hrace (v libovolnem poradi)
    exact_word_matches = [
        p for p in players
        if q_words <= {p["first_name"].lower(), p["last_name"].lower()}
        or q_words == set(f"{p['first_name']} {p['last_name']}".lower().split())
    ]
    if len(exact_word_matches) == 1:
        p = exact_word_matches[0]
        return p, f"{p['first_name']} {p['last_name']}"
    if len(exact_word_matches) > 1:
        # preferuj aktivniho hrace, pokud jde rozlisit
        active = [p for p in exact_word_matches if p.get("is_active") == "True"]
        p = active[0] if active else exact_word_matches[0]
        return p, f"{p['first_name']} {p['last_name']}"

    # 2) fuzzy fallback pres difflib, zkus poradi "Jmeno Prijmeni" i "Prijmeni Jmeno"
    cand_fwd = [f"{p['first_name']} {p['last_name']}" for p in players]
    cand_rev = [f"{p['last_name']} {p['first_name']}" for p in players]
    match, _ = fuzzy_pick(query, cand_fwd, cutoff=0.6)
    if match:
        idx = cand_fwd.index(match)
        return players[idx], match
    match, _ = fuzzy_pick(query, cand_rev, cutoff=0.6)
    if match:
        idx = cand_rev.index(match)
        return players[idx], cand_fwd[idx]
    return None, None


def show_hockey(name):
    players = load_csv(os.path.join(BASE, "hokej", "hraci", "hraci.csv"))
    p, display_name = resolve_hockey_name(name, players)
    if not p:
        print(f"Hrac '{name}' nenalezen v hokejovych datech (NHL).")
        return
    pid = p["player_id"]

    staty = load_csv(os.path.join(BASE, "hokej", "hraci", "sezonni_staty_hraci.csv"))
    my_staty = [s for s in staty if s["player_id"] == pid and "playoff" not in s["season"].lower()]
    my_staty.sort(key=lambda s: s["season"])
    if not my_staty:
        print(f"'{display_name}' nalezen, ale nema zadne sezonni staty (goly/zapasy).")
        return

    seasons = [(s["season"], int(float(s["goals"] or 0)), int(float(s["games"] or 0))) for s in my_staty]
    lam, games_used = weighted_rate(seasons)
    if lam is None:
        print(f"'{display_name}': k dispozici jen sezony s 0 zapasy, nelze spocitat.")
        return

    prob = poisson_at_least_one(lam)
    print(f"\n=== {display_name} - pravdepodobnost golu v zapase (vcetne prodlouzeni) ===")
    for season, goals, games in seasons[-3:]:
        print(f"  {season}: {goals} golu / {games} zapasu" + (f" ({goals/games:.3f} g/zapas)" if games else ""))
    print(f"\nVazena strelecka frekvence: {lam:.3f} golu/zapas (z {games_used} zapasu)")
    print(f"Odhad P(da gol v zapase) = 1 - e^-{lam:.3f} = {prob*100:.1f} %")
    if games_used < MIN_GAMES_RELIABLE:
        print(f"POZOR: jen {games_used} zapasu ve vzorku - odhad je malo spolehlivy.")
    print("Pozn.: model NEZOHLEDNUJE souperovu obranu/brankare, jen hracovu vlastni formu - bereno jako hrubsi odhad, ne tr2nicni cena.")


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("fotbal", "hokej"):
        print(__doc__)
        sys.exit(1)
    sport, name = sys.argv[1], sys.argv[2]
    if sport == "fotbal":
        show_football(name)
    else:
        show_hockey(name)


if __name__ == "__main__":
    main()
