#!/usr/bin/env python3
"""
Pravdepodobnost, ze KONKRETNI HRAC da v nadchazejicim zapase gol (trh
"strelec golu" / "hrac da gol vcetne prodlouzeni" u sazkovych kancelari).

Model: Poissonovo rozdeleni P(alespon 1 gol) = 1 - e^-lambda, kde lambda je
strelecka frekvence (goly/zapas):
- zakladne se pocita z historickych sezonnich dat (aktualni sezona vaha 70 %,
  predchozi 30 %, pokud obe existuji)
- s --live (jen hokej) se navic stahne AKTUALNI sezonni game-log z oficialniho
  NHL API (stejne jako pouziva update_stats.py) a prolne se do odhadu -
  zachyti to i "studenou/horkou" formu z poslednich par zapasu, ktere jeste
  nejsou v lokalnich CSV (ty se aktualizuji az pres update-sport-stats skill).

DULEZITE OMEZENI (vzdy rict uzivateli):
- Model NEZOHLEDNUJE soupere (obranu/brankare), jen hracovu vlastni formu.
  Je to tedy hruby odhad, ne presna tr2nicni cena.
- Male vzorky (malo odehranych zapasu) delaji odhad nespolehlivy - skript
  na to upozorni, pokud je zapasu min nez ~10 (historie) nebo pod 3 (live).
- Fotbal: pokryti jen 11 nejvyssich evropskych lig. Hokej: cela NHL.
- --live vyzaduje pristup k internetu (api-web.nhle.com) - pokud se nepodari
  spojeni, skript to rekne a spadne zpet na cisty historicky odhad.

Pouziti:
    python3 goalscorer_prob.py fotbal "Erling Haaland"
    python3 goalscorer_prob.py hokej "William Nylander"
    python3 goalscorer_prob.py hokej "Nylander William"        # i poradi prijmeni jmeno (format tiketu)
    python3 goalscorer_prob.py hokej "William Nylander" --live  # + aktualni NHL game-log
"""
import csv
import json
import math
import os
import sys
import urllib.error
import urllib.request

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from aggregate_stats import fuzzy_pick  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPT_DIR))))

MIN_GAMES_RELIABLE = 10
MIN_LIVE_GAMES = 3
NHL_UA = "Mozilla/5.0 (StatistikyBot goalscorer_prob tool)"


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


# ---------------------------------------------------------------------------
# FOTBAL
# ---------------------------------------------------------------------------
def football_lambda(name):
    """Vrati (display_name, lambda, games_used) nebo (None, None, None)."""
    players = load_csv(os.path.join(BASE, "fotbal", "hraci", "players.csv"))
    id_key = "player_id" if players and "player_id" in players[0] else None
    name_key = "player_name" if players and "player_name" in players[0] else "name"
    names = [p[name_key] for p in players]
    match, _ = fuzzy_pick(name, names, cutoff=0.6)
    if not match:
        return None, None, None
    p = next(pp for pp in players if pp[name_key] == match)
    pid = p[id_key] if id_key else None

    staty = load_csv(os.path.join(BASE, "fotbal", "hraci", "sezonni_staty.csv"))
    my_staty = [s for s in staty if s["player_id"] == pid] if pid else \
        [s for s in staty if s.get("player_name") == match]
    my_staty.sort(key=lambda s: s["season"])
    if not my_staty:
        return match, None, None

    seasons = [(s["season"], int(s["goals"] or 0), int(s["apps"] or 0)) for s in my_staty]
    lam, games_used = weighted_rate(seasons)
    return match, lam, games_used, seasons


def show_football(name):
    result = football_lambda(name)
    match, lam, games_used = result[0], result[1], result[2]
    if match is None:
        print(f"Hrac '{name}' nenalezen ve fotbalovych datech (jen 11 nejvyssich evropskych lig).")
        return
    if lam is None:
        print(f"'{match}' nalezen, ale nema zadne sezonni staty (goly/zapasy).")
        return
    seasons = result[3]

    prob = poisson_at_least_one(lam)
    print(f"\n=== {match} - pravdepodobnost golu v zapase ===")
    for season, goals, apps in seasons[-3:]:
        print(f"  {season}: {goals} golu / {apps} startu" + (f" ({goals/apps:.3f} g/zapas)" if apps else ""))
    print(f"\nVazena strelecka frekvence: {lam:.3f} golu/zapas (z {games_used} zapasu)")
    print(f"Odhad P(da gol v zapase) = 1 - e^-{lam:.3f} = {prob*100:.1f} %")
    if games_used < MIN_GAMES_RELIABLE:
        print(f"POZOR: jen {games_used} zapasu ve vzorku - odhad je malo spolehlivy.")
    print("Pozn.: model NEZOHLEDNUJE souperovu obranu, jen hracovu vlastni formu - bereno jako hrubsi odhad, ne tr2nicni cena.")


# ---------------------------------------------------------------------------
# HOKEJ
# ---------------------------------------------------------------------------
def resolve_hockey_name(query, players):
    q_words = set(query.lower().split())
    exact_word_matches = [
        p for p in players
        if q_words <= {p["first_name"].lower(), p["last_name"].lower()}
        or q_words == set(f"{p['first_name']} {p['last_name']}".lower().split())
    ]
    if len(exact_word_matches) == 1:
        p = exact_word_matches[0]
        return p, f"{p['first_name']} {p['last_name']}"
    if len(exact_word_matches) > 1:
        active = [p for p in exact_word_matches if p.get("is_active") == "True"]
        p = active[0] if active else exact_word_matches[0]
        return p, f"{p['first_name']} {p['last_name']}"

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


def fetch_live_game_log(player_id, max_games=15):
    """Stahne aktualni sezonni game-log z oficialniho NHL API.
    Vraci (goals, games, recent_games_detail) nebo (None, None, None) pri chybe."""
    url = f"https://api-web.nhle.com/v1/player/{player_id}/game-log/now"
    req = urllib.request.Request(url, headers={"User-Agent": NHL_UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"  (live fetch selhal: {e})")
        return None, None, None

    games = data.get("gameLog", [])
    if not games:
        return 0, 0, []
    goals = sum(g.get("goals", 0) for g in games)
    detail = [(g.get("gameDate"), g.get("opponentAbbrev"), g.get("goals", 0)) for g in games[:max_games]]
    return goals, len(games), detail


def hockey_lambda(name, live=False):
    """Vrati dict s vysledky, nebo None pokud hrac nenalezen."""
    players = load_csv(os.path.join(BASE, "hokej", "hraci", "hraci.csv"))
    p, display_name = resolve_hockey_name(name, players)
    if not p:
        return None
    pid = p["player_id"]

    staty = load_csv(os.path.join(BASE, "hokej", "hraci", "sezonni_staty_hraci.csv"))
    my_staty = [s for s in staty if s["player_id"] == pid and "playoff" not in s["season"].lower()]
    my_staty.sort(key=lambda s: s["season"])
    seasons = [(s["season"], int(float(s["goals"] or 0)), int(float(s["games"] or 0))) for s in my_staty]
    hist_lam, hist_games = weighted_rate(seasons)

    live_goals = live_games = None
    live_detail = []
    if live:
        live_goals, live_games, live_detail = fetch_live_game_log(pid)

    # blend: pokud mame zivy odhad s dost zapasy, prolneme ho do historicke vahy
    lam = hist_lam
    if live_goals is not None and live_games and live_games >= MIN_LIVE_GAMES:
        live_rate = live_goals / live_games
        if hist_lam is not None:
            # live forma dostava vetsi vahu, cim vic zapasu uz ma (max 50 %)
            w_live = min(0.5, live_games / 20)
            lam = (1 - w_live) * hist_lam + w_live * live_rate
        else:
            lam = live_rate

    return {
        "display_name": display_name,
        "player_id": pid,
        "seasons": seasons,
        "hist_lam": hist_lam,
        "hist_games": hist_games,
        "live_goals": live_goals,
        "live_games": live_games,
        "live_detail": live_detail,
        "lam": lam,
    }


def show_hockey(name, live=False):
    r = hockey_lambda(name, live=live)
    if r is None:
        print(f"Hrac '{name}' nenalezen v hokejovych datech (NHL).")
        return
    if r["lam"] is None:
        print(f"'{r['display_name']}': nelze spocitat, chybi historicka i ziva data.")
        return

    prob = poisson_at_least_one(r["lam"])
    print(f"\n=== {r['display_name']} - pravdepodobnost golu v zapase (vcetne prodlouzeni) ===")
    for season, goals, games in r["seasons"][-3:]:
        print(f"  {season}: {goals} golu / {games} zapasu" + (f" ({goals/games:.3f} g/zapas)" if games else ""))

    if live:
        if r["live_games"]:
            print(f"\nZiva aktualni sezona (NHL API): {r['live_goals']} golu / {r['live_games']} zapasu")
            print("Poslednich zapasu:")
            for d, opp, g in r["live_detail"]:
                znacka = f"GOL x{g}" if g else "bez golu"
                print(f"  {d}  vs {opp}  {znacka}")
            if r["live_games"] < MIN_LIVE_GAMES:
                print(f"  POZOR: jen {r['live_games']} zivych zapasu - do odhadu se zatim moc nepromita.")
        else:
            print("\nZiva data se nepodarilo stahnout nebo sezona jeste nema zadne zapasy - pouzit jen historicky odhad.")

    print(f"\nVysledna strelecka frekvence pouzita pro odhad: {r['lam']:.3f} golu/zapas")
    print(f"Odhad P(da gol v zapase) = 1 - e^-{r['lam']:.3f} = {prob*100:.1f} %")
    if (r["hist_games"] or 0) < MIN_GAMES_RELIABLE and not (r["live_games"] and r["live_games"] >= MIN_LIVE_GAMES):
        print(f"POZOR: maly vzorek dat - odhad je malo spolehlivy.")
    print("Pozn.: model NEZOHLEDNUJE souperovu obranu/brankare, jen hracovu vlastni formu - bereno jako hrubsi odhad, ne tr2nicni cena.")


def main():
    args = [a for a in sys.argv[1:] if a != "--live"]
    live = "--live" in sys.argv
    if len(args) != 2 or args[0] not in ("fotbal", "hokej"):
        print(__doc__)
        sys.exit(1)
    sport, name = args
    if sport == "fotbal":
        if live:
            print("Pozn.: --live je zatim jen pro hokej (oficialni NHL API), u fotbalu se ignoruje.")
        show_football(name)
    else:
        show_hockey(name, live=live)


if __name__ == "__main__":
    main()
