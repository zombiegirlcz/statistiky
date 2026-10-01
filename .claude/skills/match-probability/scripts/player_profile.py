#!/usr/bin/env python3
"""
Profil jednoho hrace/hrace - vek, pozice, aktualni klub, sezonni staty
(starty/goly/asistence/karty), kompletni prestupova historie (fotbal) nebo
tym po sezonach (hokej). Doplnuje aggregate_stats.py (ten pocita
pravdepodobnost VYSLEDKU zapasu) o pohled na JEDNOTLIVCE.

Pouziti:
    python3 player_profile.py fotbal "Erling Haaland"
    python3 player_profile.py hokej "Connor McDavid"

Zdroje a omezeni: viz README.md - fotbal pokryva jen 11 nejvyssich
evropskych lig (Transfermarkt data, aktualni k 6.7.2026), hokej jen NHL
(NHL stats API, prubezne aktualni).
"""
import csv
import glob
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from aggregate_stats import fuzzy_pick  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPT_DIR))))


def load_csv(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def show_football(name):
    players = load_csv(os.path.join(BASE, "fotbal", "hraci", "players.csv"))
    names = [p["name"] for p in players]
    match, score = fuzzy_pick(name, names, cutoff=0.6)
    if not match:
        print(f"Hrac '{name}' nenalezen ve fotbalovych datech (jen 11 nejvyssich evropskych lig).")
        return
    p = next(pp for pp in players if pp["name"] == match)

    print(f"\n=== {p['name']} ===")
    dob = p["date_of_birth"][:10] if p["date_of_birth"] else "?"
    print(f"Narozen: {dob}  |  Narodnost: {p['nationality']}  |  Pozice: {p['position']} ({p['sub_position']})")
    print(f"Vyska: {p['height_cm']} cm  |  Silnejsi noha: {p['foot']}")
    print(f"Aktualni klub: {p['current_club']} ({p['current_club_competition']})")
    if p["market_value_eur"]:
        print(f"Trzni hodnota: {int(p['market_value_eur']):,} EUR (max: {int(p['highest_market_value_eur'] or 0):,} EUR)".replace(",", " "))
    if p["intl_caps"]:
        print(f"Reprezentace: {p['intl_caps']} startu, {p['intl_goals'] or 0} golu")

    staty = load_csv(os.path.join(BASE, "fotbal", "hraci", "sezonni_staty.csv"))
    my_staty = [s for s in staty if s["player_id"] == p["player_id"]]
    my_staty.sort(key=lambda s: s["season"])
    if my_staty:
        print(f"\nSezonni staty:")
        print(f"{'sezona':<10}{'soutez':<8}{'klub':<25}{'S':<5}{'G':<5}{'A':<5}{'ZK':<5}{'CK':<4}{'min'}")
        for s in my_staty:
            print(f"{s['season']:<10}{s['league']:<8}{s['club'][:23]:<25}{s['apps']:<5}{s['goals']:<5}"
                  f"{s['assists']:<5}{s['yellow_cards']:<5}{s['red_cards']:<4}{s['minutes']}")

    transfers = load_csv(os.path.join(BASE, "fotbal", "hraci", "transfers.csv"))
    my_transfers = [t for t in transfers if t["player_id"] == p["player_id"]]
    my_transfers.sort(key=lambda t: t["transfer_date"])
    if my_transfers:
        print(f"\nPrestupy:")
        for t in my_transfers:
            fee = f"{int(float(t['fee_eur'])):,} EUR".replace(",", " ") if t["fee_eur"] else "neuvedeno/volny prestup"
            print(f"  {t['transfer_date']}: {t['from_club']} -> {t['to_club']}  ({fee})")


def show_hockey(name):
    bio_path = os.path.join(BASE, "hokej", "hraci", "hraci.csv")
    if not os.path.exists(bio_path):
        print("Hokejova hracska data jeste nejsou k dispozici.")
        return
    bios = load_csv(bio_path)
    full_names = {f"{b['first_name']} {b['last_name']}".strip(): b for b in bios}
    match, score = fuzzy_pick(name, list(full_names.keys()), cutoff=0.6)
    if not match:
        print(f"Hrac '{name}' nenalezen v hokejovych datech (jen NHL).")
        return
    b = full_names[match]

    print(f"\n=== {match} ===")
    print(f"Narozen: {b['birth_date']}  |  Zeme: {b['birth_country']}  |  Pozice: {b['position']}")
    print(f"Vyska: {b['height_cm']} cm  |  Vaha: {b['weight_kg']} kg  |  Drzi hul/lapacku: {b['shoots_catches']}")
    print(f"Aktualni tym: {b['current_team']}  |  Aktivni: {b['is_active']}")
    if b["draft_year"]:
        print(f"Draft: {b['draft_year']}, kolo {b['draft_round']}, celkove poradi {b['draft_overall']}")

    staty_path = os.path.join(BASE, "hokej", "hraci", "sezonni_staty_hraci.csv")
    staty = load_csv(staty_path)
    my_staty = [s for s in staty if s["player_id"] == b["player_id"]]
    if my_staty:
        print(f"\nSezonni staty (pole hracu):")
        print(f"{'sezona':<16}{'tym':<10}{'Z':<5}{'G':<5}{'A':<5}{'B':<5}{'+/-':<5}{'TM':<4}{'strely'}")
        for s in sorted(my_staty, key=lambda s: s["season"]):
            print(f"{s['season']:<16}{s['team']:<10}{s['games']:<5}{s['goals']:<5}{s['assists']:<5}"
                  f"{s['points']:<5}{s['plus_minus']:<5}{s['pim']:<4}{s['shots']}")
    else:
        golmani_path = os.path.join(BASE, "hokej", "hraci", "sezonni_staty_brankari.csv")
        golmani = load_csv(golmani_path)
        my_golmani = [s for s in golmani if s["player_id"] == b["player_id"]]
        if my_golmani:
            print(f"\nSezonni staty (brankar):")
            print(f"{'sezona':<16}{'tym':<10}{'Z':<5}{'V':<5}{'P':<5}{'OTL':<5}{'GAA':<7}{'SV%':<7}{'shutouty'}")
            for s in sorted(my_golmani, key=lambda s: s["season"]):
                print(f"{s['season']:<16}{s['team']:<10}{s['games']:<5}{s['wins']:<5}{s['losses']:<5}"
                      f"{s['ot_losses']:<5}{s['goals_against_avg']:<7}{s['save_pct']:<7}{s['shutouts']}")


def main():
    if len(sys.argv) < 3:
        print('Pouziti: player_profile.py [fotbal|hokej] "Jmeno hrace"')
        sys.exit(1)
    sport, name = sys.argv[1], sys.argv[2]
    if sport == "fotbal":
        show_football(name)
    elif sport == "hokej":
        show_hockey(name)
    else:
        print('Pouziti: player_profile.py [fotbal|hokej] "Jmeno hrace"')


if __name__ == "__main__":
    main()
