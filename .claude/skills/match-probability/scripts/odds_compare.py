#!/usr/bin/env python3
"""
Porovna nas statisticky odhad (aggregate_stats.py) se zivymi sazkovymi kurzy
z The Odds API (the-odds-api.com) - bere prumerny kurz napric bookmakery,
prevede ho na implikovanou pravdepodobnost a odecte bookmakerskou marzi.

Proc je tohle uzitecne: nas model pocita cistě z historickych statistik a
NEUMI zohlednit cerstve zpravy (zraneni, forma z poslednich dnu, motivace) -
viz metodika.md. Trh (prumer vsech sazkaru) tohle v sobe uz ma zacenene, takze
porovnani "nas odhad vs. trh" je dobra kontrola, jestli model nejede mimo
realitu - velky rozdil (>15-20 procentnich bodu) je signal, ze se u tohohle
konkretniho zapasu deje neco, co nase data nezachycuji.

Nastaveni (jednorazove):
    1. Zalozit si zdarma ucet na https://the-odds-api.com (bez karty, 500
       kreditu/mesic zdarma, staci na desitky dotazu denne).
    2. export ODDS_API_KEY="vas_klic"

Pouziti:
    python3 odds_compare.py fotbal "Arsenal" "Chelsea"
    python3 odds_compare.py tenis "Jannik Sinner" "Carlos Alcaraz"
    python3 odds_compare.py hokej "Toronto" "Edmonton"

Omezeni: API dava jen NADCHAZEJICI/zive zapasy (ne historii na testovani) a
kurzy obvykle jen pro vyssi souteze - u nizsich anglickych/skotskych lig
(League One/Two, National League) nebo mensich evropskych lig nemusi byt
zadny bookmaker v nabidce, pak skript rekne, ze zapas nenasel.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from aggregate_stats import fuzzy_pick, load_football_rows  # noqa: E402

API_BASE = "https://api.the-odds-api.com/v4"

# DULEZITE KVULI KREDITUM: kazdy dotaz na /odds/ stoji 1 kredit ZA KAZDY
# region (napr. regions=eu,uk,us = 3 kredity za jedno volani, ne 1!). Proto
# vsude pouzivame jen jeden region ("eu" - ma nejvetsi pokryti evropskych
# lig i NHL/tenisu) a u fotbalu/hokeje se vubec nehada metodou pokus-omyl
# pres desitky moznych sport_key - misto toho primo mapujeme na konkretni
# klic, abychom spotrebovali jen 1 kredit na dotaz.
REGION = "eu"

# Nas fotbalovy soubor "2025-26_E0_Anglie_-_Premier_League.csv" ma v nazvu
# kod ligy (E0) - tahle tabulka (overena zivym dotazem na /v4/sports/) rika,
# jaky sport_key tomu na The Odds API odpovida. Ligy, ktere tam nejsou
# (EC = anglicka National League, SC1-3 = nizsi skotske ligy), bookmakeri
# bezne nenabizeji vubec - u nich skript rovnou rekne, ze trh neexistuje,
# misto aby platil kredity za marne zkouseni.
FOOTBALL_LEAGUE_TO_SPORT_KEY = {
    "E0": "soccer_epl", "E1": "soccer_efl_champ", "E2": "soccer_england_league1",
    "E3": "soccer_england_league2", "SC0": "soccer_spl",
    "D1": "soccer_germany_bundesliga", "D2": "soccer_germany_bundesliga2",
    "I1": "soccer_italy_serie_a", "I2": "soccer_italy_serie_b",
    "SP1": "soccer_spain_la_liga", "SP2": "soccer_spain_segunda_division",
    "F1": "soccer_france_ligue_one", "F2": "soccer_france_ligue_two",
    "N1": "soccer_netherlands_eredivisie", "B1": "soccer_belgium_first_div",
    "P1": "soccer_portugal_primeira_liga", "T1": "soccer_turkey_super_league",
    "G1": "soccer_greece_super_league",
}

# Tenis nema na API jeden trvaly klic (napr. "tennis_atp") - turnaje jsou
# samostatne sport_key, ktere se meni podle toho, co prave bezi (napr.
# "tennis_atp_china_open"). Proto se tam musi projit aktualni nabidka -
# ale je jich typicky jen par najednou, takze je to levne (jednotky kreditu).
TENNIS_KEYWORD = "tennis"
HOCKEY_SPORT_KEY = "icehockey_nhl"  # nase data pokryvaji jen NHL, viz README.md


def _request(path, params):
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        print("CHYBA: chybi promenna prostredi ODDS_API_KEY.")
        print("1. Zalozte si zdarma ucet na https://the-odds-api.com (bez karty)")
        print("2. export ODDS_API_KEY=\"vas_klic\"")
        sys.exit(1)
    q = dict(params)
    q["apiKey"] = api_key
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": "statistiky-match-probability/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            remaining = resp.headers.get("x-requests-remaining")
            return json.loads(resp.read().decode("utf-8")), remaining
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"CHYBA API ({e.code}): {body}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"CHYBA sitoveho pripojeni: {e}")
        sys.exit(1)


def list_sports():
    """Nic nestoji (viz docs) - pouziva se jen pro tenis, kde se musi zjistit,
    jake turnaje prave bezi."""
    data, _ = _request("/sports/", {"all": "false"})
    return data


def tennis_candidates():
    sports = list_sports()
    return [s for s in sports if TENNIS_KEYWORD in s["key"]]


def football_sport_key(name_a, name_b):
    """Najde ligovy kod (E0, I1, ...) tymu v nasich vlastnich datech a vrati
    odpovidajici sport_key - bez jedineho API dotazu navic."""
    rows = load_football_rows()
    teams = sorted({r["HomeTeam"] for r in rows} | {r["AwayTeam"] for r in rows})
    match_a, _ = fuzzy_pick(name_a, teams, cutoff=0.6)
    match_b, _ = fuzzy_pick(name_b, teams, cutoff=0.6)
    if not match_a or not match_b:
        return None, None
    # nejnovejsi zapas kteregokoliv z tymu rika, v jake lize (aktualne) hraje
    team_rows = [r for r in rows if r["HomeTeam"] in (match_a, match_b) or r["AwayTeam"] in (match_a, match_b)]
    if not team_rows:
        return None, None
    latest = max(team_rows, key=lambda r: r["_league_file"])
    league_code = latest["_league_file"].split("_")[1]
    return league_code, FOOTBALL_LEAGUE_TO_SPORT_KEY.get(league_code)


def fetch_odds(sport_key):
    data, remaining = _request(f"/sports/{sport_key}/odds/", {
        "regions": REGION, "markets": "h2h", "oddsFormat": "decimal",
    })
    return data, remaining


def find_event(events, name_a, name_b):
    """Najde udalost, kde home_team/away_team fuzzy odpovidaji oboum jmenum."""
    for ev in events:
        teams = [ev.get("home_team", ""), ev.get("away_team", "")]
        match_a, _ = fuzzy_pick(name_a, teams, cutoff=0.5)
        match_b, _ = fuzzy_pick(name_b, teams, cutoff=0.5)
        if match_a and match_b and match_a != match_b:
            return ev
    return None


def devigged_probs(event, sport_cz):
    """Prumerny kurz pres vsechny bookmakery pro kazdy vysledek, prevedeny na
    pravdepodobnost a normalizovany tak, aby soucet dal 100 % (odstraneni
    bookmakerske marze - tzv. 'overround'). Vraci dict {outcome_name: %}.

    DULEZITE: u hokeje (a tenisu) nekteri evropsti sazkari nabizeji pod
    stejnym klicem 'h2h' i trh na 'vysledek po 60 minutach zakladni hraci
    doby' se tremi moznostmi vcetne remizy (NHL fakticky remizou nikdy
    nekonci - je prodlouzeni/najezdy, viz metodika.md). Kdyby se tyhle kurzy
    smichaly s opravdovym 2-vyslednym moneyline trhem, zkreslily by prumer -
    proto se podle sportu filtruje jen na trhy se spravnym poctem vysledku."""
    expected_outcomes = 3 if sport_cz == "fotbal" else 2
    sums, counts = {}, {}
    for bm in event.get("bookmakers", []):
        for market in bm.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outcomes = market.get("outcomes", [])
            if len(outcomes) != expected_outcomes:
                continue
            for outcome in outcomes:
                name, price = outcome["name"], outcome["price"]
                if price and price > 1:
                    sums[name] = sums.get(name, 0.0) + 1.0 / price
                    counts[name] = counts.get(name, 0) + 1
    if not sums:
        return None
    avg_raw = {name: sums[name] / counts[name] for name in sums}
    total = sum(avg_raw.values())
    return {name: v / total for name, v in avg_raw.items()}


def main():
    if len(sys.argv) < 4:
        print("Pouziti: odds_compare.py [fotbal|tenis|hokej] \"Jmeno A\" \"Jmeno B\"")
        sys.exit(1)
    sport_cz, name_a, name_b = sys.argv[1], sys.argv[2], sys.argv[3]

    found_event, found_probs, found_label, remaining = None, None, None, None

    if sport_cz == "fotbal":
        league_code, sport_key = football_sport_key(name_a, name_b)
        if not sport_key:
            if league_code:
                print(f"Tym hraje ligu '{league_code}', kterou The Odds API nema v nabidce "
                      "(bezne u nizsich/mensich souteze) - kurzy nejsou k dispozici.")
            else:
                print(f"Tym(y) '{name_a}' / '{name_b}' se nenasly v nasich fotbalovych datech - "
                      "zkus presnejsi/jine jmeno (viz ../references/nazvy_tymu.md).")
            sys.exit(1)
        events, remaining = fetch_odds(sport_key)
        ev = find_event(events, name_a, name_b)
        if ev:
            found_probs = devigged_probs(ev, sport_cz)
            found_event, found_label = ev, sport_key
    elif sport_cz == "hokej":
        events, remaining = fetch_odds(HOCKEY_SPORT_KEY)
        ev = find_event(events, name_a, name_b)
        if ev:
            found_probs = devigged_probs(ev, sport_cz)
            found_event, found_label = ev, "NHL"
    elif sport_cz == "tenis":
        for sport in tennis_candidates():
            events, remaining = fetch_odds(sport["key"])
            ev = find_event(events, name_a, name_b)
            if ev:
                probs = devigged_probs(ev, sport_cz)
                if probs:
                    found_event, found_probs, found_label = ev, probs, sport["title"]
                    break
    else:
        print("Pouziti: odds_compare.py [fotbal|tenis|hokej] \"Jmeno A\" \"Jmeno B\"")
        sys.exit(1)

    if not found_event:
        print(f"Zapas '{name_a}' vs '{name_b}' se v nadchazejicich kurzech nenasel.")
        print("Bud se jeste nehraje / neni v nabidce bookmakeru, nebo nesedi jmena - "
              "zkus kratsi/jinou variantu jmena.")
        if remaining is not None:
            print(f"(kredity API zbyvajici tento mesic: {remaining})")
        sys.exit(1)

    print(f"\n=== Trh: {found_event['home_team']} vs {found_event['away_team']} "
          f"({found_label}, {found_event['commence_time']}) ===")
    print(f"(kredity API zbyvajici tento mesic: {remaining})\n")
    for name, p in sorted(found_probs.items(), key=lambda x: -x[1]):
        print(f"  {name:<30} {p:.0%}  (implikovano z prumernych kurzu, bez marze)")
    print("\nPro porovnani spust take:")
    print(f'  python3 aggregate_stats.py {sport_cz} "{name_a}" "{name_b}"')
    print("a dej vedle sebe nas odhad z historickych dat a odhad trhu vyse.")


if __name__ == "__main__":
    main()
