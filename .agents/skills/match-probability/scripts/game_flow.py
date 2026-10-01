#!/usr/bin/env python3
"""
Herni uroven tenisu (kdo vyhraje konkretni game cislo N) a prubeh zapasu -
neco, co z obycejneho "vysledek setu" datasetu (atp/wta_matches_*.csv) nejde
spocitat, protoze tam je jen konecne skore setu, ne poradi gamu. Tohle
vyuziva Jeff Sackmannuv Match Charting Project (crowdsourced bod-po-bodu
zaznamy, viz tenis/prubeh/) - zpracovane do kompaktni tabulky "kdo podaval a
kdo vyhral kazdy game" skriptem, ktery vyrobil tyto CSV (games_m.csv,
games_w.csv, charting-*-matches.csv v tenis/prubeh/).

POZOR na pokryti: Match Charting Project je dobrovolnicky projekt, ne
kompletni archiv - pokryva cca 15-20 % profi zapasu od roku 2020, a hodne
nerovnomerne (u Sinnera/Alcaraze/Djokovice jsou stovky zapasu, u hrace
c. 150 na zebricku treba zadny). Kdyz zapas neni nachartovany, skript to
rekne rovnou - NEHADEJ misto toho z obecnych cisel, to by bylo zavadejici.

Licence dat: CC BY-NC-SA 4.0 (Jeff Sackmann / Match Charting Project
dobrovolnici) - pouze NEKOMERCNI pouziti, s uvedenim zdroje.

Metodika predikce konkretniho gamu:
    Kazdy game podava jeden hrac. Z historickych nachartovanych zapasu (pred
    datem testovaneho zapasu) se spocita:
      - hold_rate(hrac) = jak casto hrac udrzi vlastni podani
      - break_rate(hrac) = jak casto hrac prolomi souperovo podani
    Pravdepodobnost, ze podavajici vyhraje dany game, je prumer:
      (hold_rate podavajiciho + (1 - break_rate prijimajiciho)) / 2
    Kdo bude podavat v gamu 1 (a tim padem i ve vsech lichych gamech, sudy
    podava soupe) se urcuje losem na zacatku zapasu - to NEJDE predikovat
    dopredu, je to 50:50. Skript proto u budouciho zapasu da predikci PRO
    OBE varianty (kdyz zacne podavat hrac A / kdyz zacne hrac B).

Pouziti:
    python3 game_flow.py "Jannik Sinner" "Carlos Alcaraz"
"""
import csv
import glob
import os
import random
import sys
from collections import defaultdict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from aggregate_stats import fuzzy_pick  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPT_DIR))))
PRUBEH_DIR = os.path.join(BASE, "tenis", "prubeh")


def load_matches(gender):
    """gender: 'm' nebo 'w'. match_id zacina YYYYMMDD, z toho si vytahneme datum."""
    path = os.path.join(PRUBEH_DIR, f"charting-{gender}-matches.csv")
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            mid = row.get("match_id", "")
            if len(mid) < 8 or not mid[:8].isdigit():
                continue
            row["_d"] = mid[:8]
            rows.append(row)
    return rows


def load_games(gender):
    path = os.path.join(PRUBEH_DIR, f"games_{gender}.csv")
    by_match = defaultdict(list)
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            by_match[row["match_id"]].append(row)
    for mid in by_match:
        by_match[mid].sort(key=lambda r: int(r["overall_game_num"]))
    return by_match


def find_charted_match(name_a, name_b, matches_m, matches_w):
    """Vrati (match_row, gender, slot_a, slot_b) nebo None. slot_a/slot_b je
    '1' nebo '2' podle toho, jestli dany hrac byl Player 1 nebo Player 2 v
    konkretnim zapase."""
    for gender, matches in (("m", matches_m), ("w", matches_w)):
        for row in matches:
            players = [row["Player 1"], row["Player 2"]]
            ma, _ = fuzzy_pick(name_a, players, cutoff=0.6)
            mb, _ = fuzzy_pick(name_b, players, cutoff=0.6)
            if ma and mb and ma != mb:
                slot_a = "1" if ma == row["Player 1"] else "2"
                slot_b = "1" if mb == row["Player 1"] else "2"
                return row, gender, slot_a, slot_b
    return None


def hold_break_rate(player_name, gender, matches, games, cutoff_date):
    """Projde vsechny zapasy hrace pred cutoff_date a spocita, jak casto
    udrzel vlastni podani (hold) a jak casto prolomil souperovo (break)."""
    hold_won, hold_total, break_won, break_total = 0, 0, 0, 0
    for m in matches:
        if m["_d"] >= cutoff_date:
            continue
        players = [m["Player 1"], m["Player 2"]]
        match, _ = fuzzy_pick(player_name, players, cutoff=0.6)
        if not match:
            continue
        slot = "1" if match == m["Player 1"] else "2"
        for g in games.get(m["match_id"], []):
            if g["server"] == slot:
                hold_total += 1
                hold_won += (g["winner"] == slot)
            elif g["server"] in ("1", "2"):
                break_total += 1
                break_won += (g["winner"] == slot)
    hold_rate = hold_won / hold_total if hold_total else None
    break_rate = break_won / break_total if break_total else None
    return hold_rate, break_rate, hold_total, break_total


def predict_server_win_prob(hold_rate, opp_break_rate, default=0.75):
    h = hold_rate if hold_rate is not None else default
    b = opp_break_rate if opp_break_rate is not None else (1 - default)
    return (h + (1 - b)) / 2


def reconstruct_set_and_match_winners(games_for_match):
    """Z posloupnosti gamu v jednom zapase (games_m/w.csv radky) odvodi, kdo
    vyhral kazdy set (vic vyhranych 'gamu' v danem set_num - plati i pro
    tiebreak set, protoze zalomeny tiebreak je proste jeden dalsi radek/game
    navic) a kdo vyhral cely zapas (vic setu). Vraci (set_winners: dict
    set_num->slot, match_winner: '1'/'2'/None pri nejednoznacnosti/odhlaseni)."""
    by_set = defaultdict(lambda: {"1": 0, "2": 0})
    for g in games_for_match:
        by_set[int(g["set_num"])][g["winner"]] += 1
    set_winners = {}
    for set_num, counts in by_set.items():
        if counts["1"] == counts["2"]:
            continue
        set_winners[set_num] = "1" if counts["1"] > counts["2"] else "2"
    sets_won = {"1": 0, "2": 0}
    for w in set_winners.values():
        sets_won[w] += 1
    if sets_won["1"] == sets_won["2"]:
        return set_winners, None
    match_winner = "1" if sets_won["1"] > sets_won["2"] else "2"
    return set_winners, match_winner


def build_state_win_table(matches, games, best_of_filter=None):
    """Projde VSECHNY nachartovane zapasy (dane pohlavi) a pro kazdy odehrany
    game zaznamena stav 'pred timhle gamem' z pohledu OBOU hracu - (rozdil
    vyhranych setu, rozdil vyhranych gamu v aktualnim setu) - a jestli dany
    hrac nakonec zapas vyhral. Vysledek je tabulka {(set_diff, game_diff):
    [vyhry, celkem]} - empiricka 'live' pravdepodobnost vyhry zapasu podle
    aktualniho prubehu, misto jen statickeho konce setu."""
    bo_by_match = {m["match_id"]: m.get("Best of") for m in matches}
    table = defaultdict(lambda: [0, 0])

    for match_id, g in games.items():
        if best_of_filter and bo_by_match.get(match_id) != best_of_filter:
            continue
        g = sorted(g, key=lambda r: int(r["overall_game_num"]))
        set_winners, match_winner = reconstruct_set_and_match_winners(g)
        if match_winner is None:
            continue

        sets = {"1": 0, "2": 0}
        games_in_set = {"1": 0, "2": 0}
        cur_set = None
        for row in g:
            sn = int(row["set_num"])
            if cur_set is None:
                cur_set = sn
            elif sn != cur_set:
                # novy set zacina - pripocti vyhraneho predchoziho setu a vynuluj gamy
                prev_winner = set_winners.get(cur_set)
                if prev_winner:
                    sets[prev_winner] += 1
                games_in_set = {"1": 0, "2": 0}
                cur_set = sn

            for slot in ("1", "2"):
                opp = "2" if slot == "1" else "1"
                set_diff = max(-2, min(2, sets[slot] - sets[opp]))
                game_diff = max(-6, min(6, games_in_set[slot] - games_in_set[opp]))
                key = (set_diff, game_diff)
                table[key][1] += 1
                table[key][0] += (slot == match_winner)

            games_in_set[row["winner"]] += 1
    return table


def query_state(table, set_diff, game_diff, min_n=20):
    set_diff = max(-2, min(2, set_diff))
    game_diff = max(-6, min(6, game_diff))
    wins, total = table.get((set_diff, game_diff), [0, 0])
    if total >= min_n:
        return wins / total, total
    # fallback: siri okoli (jen podle set_diff, bez ohledu na presny game_diff)
    w2, t2 = 0, 0
    for (sd, gd), (w, t) in table.items():
        if sd == set_diff:
            w2 += w
            t2 += t
    if t2:
        return w2 / t2, t2
    return None, 0


def print_zvrat_table(gender_label, table):
    print(f"\n=== Pravdepodobnost vyhry zapasu podle aktualniho stavu ({gender_label}) ===")
    print(f"{'sety (rozdil)':<15}{'gamy v setu (rozdil)':<22}{'P(vyhra zapasu)':<18}{'n (vzorek)'}")
    interesting = [
        (-1, -2, "prohral 1. set, prohrava 0:2 ve 2. setu"),
        (-1, 0, "prohral 1. set, zacatek 2. setu (0:0)"),
        (0, 0, "vyrovnano, zacatek setu"),
        (0, -4, "prohrava 1:4/0:4 v rozhodujicim/aktualnim setu"),
        (-1, 5, "prohral 1. set, ale vede 5:1 ve 2. setu"),
        (1, 2, "vede 1:0 na sety, vede 2:0 v gamu"),
    ]
    for sd, gd, label in interesting:
        p, n = query_state(table, sd, gd)
        p_str = f"{p:.0%}" if p is not None else "n/a"
        print(f"{sd:+d}{'':<14}{gd:+d}{'':<21}{p_str:<18}{n}   {label}")


def run_flow_backtest(n=40, seed=42):
    """POCTIVY test: nahodne vybere n nachartovanych zapasu (napric obema
    pohlavimi), a pro KAZDY game v kazdem zapase predikuje vitěze jen z dat
    pred datem zapasu (presne jako skutecna predpoved dopredu - server pro
    dany game se bere ze skutecneho prubehu, protoze to je verejne znama
    informace pred zapasem/gamem, ne vysledek, ktery bychom nemeli znat)."""
    matches_m, matches_w = load_matches("m"), load_matches("w")
    games_m, games_w = load_games("m"), load_games("w")

    pool = []
    for gender, matches, games in (("m", matches_m, games_m), ("w", matches_w, games_w)):
        for m in matches:
            if m["_d"] < "20220101":
                continue
            g = games.get(m["match_id"])
            if g and len(g) >= 6:
                pool.append((gender, m, g))

    rng = random.Random(seed)
    sample = rng.sample(pool, min(n, len(pool)))
    sample.sort(key=lambda x: x[1]["_d"])

    hits, server_hits, total = 0, 0, 0
    for gender, m, g in sample:
        matches = matches_m if gender == "m" else matches_w
        games = games_m if gender == "m" else games_w
        cutoff = m["_d"]
        p1, p2 = m["Player 1"], m["Player 2"]
        hold1, break1, _, _ = hold_break_rate(p1, gender, matches, games, cutoff)
        hold2, break2, _, _ = hold_break_rate(p2, gender, matches, games, cutoff)
        p1_prob = predict_server_win_prob(hold1, break2)
        p2_prob = predict_server_win_prob(hold2, break1)
        for row in g:
            server, winner = row["server"], row["winner"]
            if server not in ("1", "2"):
                continue
            p_win = p1_prob if server == "1" else p2_prob
            pred_winner = server if p_win >= 0.5 else ("2" if server == "1" else "1")
            hits += (pred_winner == winner)
            server_hits += (server == winner)
            total += 1

    print(f"\n=== PRUBEH ZAPASU (herni uroven): {len(sample)} zapasu, {total} jednotlivych gamu ===")
    print(f"Presnost nasi predikce (hold/break prumer):  {hits}/{total} = {hits/total:.1%}")
    print(f"Baseline 'podavajici vzdy vyhraje svuj game': {server_hits}/{total} = {server_hits/total:.1%}")
    print("(nas model se lisi od baseline jen u gamu, kde je vyzyvatel/returner historicky "
          "nadprumerne silny v brejcich - u vetsiny gamu podavajici proste vyhraje, "
          "protoze drzeni podani je v profi tenise kolem 65-85 %)")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
        run_flow_backtest(n)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--zvrat":
        matches_m, matches_w = load_matches("m"), load_matches("w")
        games_m, games_w = load_games("m"), load_games("w")
        table_m = build_state_win_table(matches_m, games_m)
        table_w = build_state_win_table(matches_w, games_w)
        print_zvrat_table("ATP", table_m)
        print_zvrat_table("WTA", table_w)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--state":
        # --state <sety_pro_mne> <sety_pro_soupere> <gamy_pro_mne> <gamy_pro_soupere> [m|w]
        sp, so, gp, go = (int(x) for x in sys.argv[2:6])
        gender = sys.argv[6] if len(sys.argv) > 6 else "m"
        matches = load_matches(gender)
        games = load_games(gender)
        table = build_state_win_table(matches, games)
        p, n = query_state(table, sp - so, gp - go)
        label = "ATP" if gender == "m" else "WTA"
        if p is None:
            print(f"Nedostatek dat pro tento stav ({label}).")
        else:
            print(f"Stav sety {sp}:{so}, gamy {gp}:{go} ({label}): "
                  f"P(vyhra zapasu) = {p:.0%}  (vzorek n={n})")
        return
    if len(sys.argv) < 3:
        print('Pouziti: game_flow.py "Hrac A" "Hrac B"')
        print('         game_flow.py --backtest [N]')
        print('         game_flow.py --zvrat')
        print('         game_flow.py --state <sety_moje> <sety_souperovy> <gamy_moje> <gamy_souperovy> [m|w]')
        sys.exit(1)
    name_a, name_b = sys.argv[1], sys.argv[2]

    matches_m, matches_w = load_matches("m"), load_matches("w")
    found = find_charted_match(name_a, name_b, matches_m, matches_w)
    if not found:
        print(f"Zapas '{name_a}' vs '{name_b}' neni v Match Charting Project (nenachartovany).")
        print("Tohle pokryva jen cca 15-20 % profi zapasu, hlavne u top hracu - u mene "
              "sledovanych hracu/zapasu proste tahle urovn detailu neni k dispozici.")
        print("Obecnou pravdepodobnost vitezstvi spocita aggregate_stats.py z hlavniho datasetu.")
        sys.exit(1)

    match_row, gender, slot_a, slot_b = found
    matches = matches_m if gender == "m" else matches_w
    games = load_games(gender)
    cutoff = match_row["_d"]

    hold_a, break_a, ha_n, ba_n = hold_break_rate(name_a, gender, matches, games, cutoff)
    hold_b, break_b, hb_n, bb_n = hold_break_rate(name_b, gender, matches, games, cutoff)

    print(f"\n=== Nalezen nachartovany zapas: {match_row['Player 1']} vs {match_row['Player 2']} "
          f"({match_row.get('Tournament', '?')}, {cutoff}) ===")
    print(f"{name_a}: drzeni podani {hold_a:.0%} (z {ha_n} gamu), brejky {break_a:.0%} (z {ba_n} gamu)"
          if hold_a is not None else f"{name_a}: nedostatek historickych dat, pouzit odhad")
    print(f"{name_b}: drzeni podani {hold_b:.0%} (z {hb_n} gamu), brejky {break_b:.0%} (z {bb_n} gamu)"
          if hold_b is not None else f"{name_b}: nedostatek historickych dat, pouzit odhad")

    p_a_holds = predict_server_win_prob(hold_a, break_b)
    p_b_holds = predict_server_win_prob(hold_b, break_a)
    print(f"\nKdyz podava {name_a}: vyhraje svuj game s pravdepodobnosti {p_a_holds:.0%}")
    print(f"Kdyz podava {name_b}: vyhraje svuj game s pravdepodobnosti {p_b_holds:.0%}")
    print("\nKdo podava jako prvni (game 1, 3, 5, 7...) se losuje tesne pred zapasem - "
          "to z historickych dat predikovat nejde, je to 50:50. Jakmile se to vi, aplikuj "
          "cisla vyse: licha cisla gamu = podavajici v gamu 1, suda = druhy hrac.")


if __name__ == "__main__":
    main()
