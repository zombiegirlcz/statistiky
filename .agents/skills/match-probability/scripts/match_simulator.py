#!/usr/bin/env python3
"""
Monte Carlo simulator zapasu - nad stejnymi Poissonovymi parametry (lam_home/
lam_away), jake uz pocita aggregate_stats.py pro "nejpravdepodobnejsi presne
skore". Rozdil je, ze tady se misto jednoho analytickeho vypoctu N-krat (napr.
20000x) nahodi konkretni skore z Poissonova rozdeleni a spocita se, jak casto
se ktere skore (a vysledek W/D/L) ve simulaci objevilo - z toho vyjde histogram
nejcastejsich vysledku, ne jen jedno "nejpravdepodobnejsi" cislo.

Pouziti:
    python3 match_simulator.py fotbal "Arsenal" "Chelsea" [--home A|B] [--n 20000] [--json]
    python3 match_simulator.py hokej "Toronto" "Edmonton" [--home A|B] [--n 20000] [--json]

Hokej nema remizu (NHL vzdy ma viteze diky prodlouzeni/nazvakum) - pri shode
gólu v simulaci se vitez simuluje 50:50 (prodlouzeni/nazvaky jsou v datech
i realite blizko mince).
"""
import argparse
import json
import os
import random
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
import aggregate_stats as ag  # noqa: E402


def _poisson_sample(lam, rng):
    """Knuthuv algoritmus - staci, zadna externi zavislost (numpy neni k dispozici)."""
    l_val = 2.718281828459045 ** -lam
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= l_val:
            return k - 1


def football_lambdas(name_a, name_b, home_side):
    """Vytahne lam_home/lam_away + rozpoznana jmena tymu - stejna logika jako
    uvnitr aggregate_stats.analyze_football (goals_for_against + h2h blending),
    jen bez textoveho reportu."""
    rows = ag.load_football_rows()
    teams = ag.all_football_teams(rows)
    team_a, score_a = ag.fuzzy_pick(name_a, teams)
    team_b, score_b = ag.fuzzy_pick(name_b, teams)
    if not team_a or not team_b:
        return {"error": f"nenalezen tym: '{name_a}' -> {team_a}, '{name_b}' -> {team_b}"}

    def team_matches(team):
        return [r for r in rows if r["HomeTeam"] == team or r["AwayTeam"] == team]

    m_a = team_matches(team_a)
    m_b = team_matches(team_b)
    h2h = [r for r in rows if {r["HomeTeam"], r["AwayTeam"]} == {team_a, team_b}]
    home_team, away_team = (team_a, team_b) if home_side != "B" else (team_b, team_a)

    def goals_for_against(team, matches, venue):
        gf, ga = [], []
        for r in matches:
            if venue == "H" and r["HomeTeam"] == team:
                gf.append(int(r["FTHG"])); ga.append(int(r["FTAG"]))
            elif venue == "A" and r["AwayTeam"] == team:
                gf.append(int(r["FTAG"])); ga.append(int(r["FTHG"]))
        return (sum(gf) / len(gf) if gf else None), (sum(ga) / len(ga) if ga else None)

    def safe(x, d):
        return x if x is not None else d

    h_attack, h_defense = goals_for_against(home_team, m_a if home_team == team_a else m_b, "H")
    a_attack, a_defense = goals_for_against(away_team, m_b if away_team == team_b else m_a, "A")
    lam_home = (safe(h_attack, 1.3) + safe(a_defense, 1.3)) / 2
    lam_away = (safe(a_attack, 1.1) + safe(h_defense, 1.1)) / 2

    if len(h2h) >= 3:
        h2h_home_goals = [int(r["FTHG"]) if r["HomeTeam"] == home_team else int(r["FTAG"]) for r in h2h]
        h2h_away_goals = [int(r["FTAG"]) if r["HomeTeam"] == home_team else int(r["FTHG"]) for r in h2h]
        lam_home = 0.65 * lam_home + 0.35 * (sum(h2h_home_goals) / len(h2h_home_goals))
        lam_away = 0.65 * lam_away + 0.35 * (sum(h2h_away_goals) / len(h2h_away_goals))

    return {"home_team": home_team, "away_team": away_team, "lam_home": lam_home, "lam_away": lam_away,
            "n_matches_a": len(m_a), "n_matches_b": len(m_b), "n_h2h": len(h2h)}


def hockey_lambdas(name_a, name_b, home_side):
    rows = ag.load_hockey_rows()
    abbrev_a = ag.resolve_nhl(name_a)
    abbrev_b = ag.resolve_nhl(name_b)
    if not abbrev_a or not abbrev_b:
        return {"error": f"nenalezen tym NHL: '{name_a}' -> {abbrev_a}, '{name_b}' -> {abbrev_b}"}

    def team_matches(ab):
        return [r for r in rows if r["home_team"] == ab or r["away_team"] == ab]

    m_a = team_matches(abbrev_a)
    m_b = team_matches(abbrev_b)
    h2h = [r for r in rows if {r["home_team"], r["away_team"]} == {abbrev_a, abbrev_b}]
    home_ab, away_ab = (abbrev_a, abbrev_b) if home_side != "B" else (abbrev_b, abbrev_a)

    def goals_for_against(ab, matches, venue):
        gf, ga = [], []
        for r in matches:
            if venue == "home" and r["home_team"] == ab:
                gf.append(int(r["home_score"])); ga.append(int(r["away_score"]))
            elif venue == "away" and r["away_team"] == ab:
                gf.append(int(r["away_score"])); ga.append(int(r["home_score"]))
        return (sum(gf) / len(gf) if gf else None), (sum(ga) / len(ga) if ga else None)

    def safe(x, d):
        return x if x is not None else d

    h_attack, h_defense = goals_for_against(home_ab, m_a if home_ab == abbrev_a else m_b, "home")
    a_attack, a_defense = goals_for_against(away_ab, m_b if away_ab == abbrev_b else m_a, "away")
    lam_home = (safe(h_attack, 3.0) + safe(a_defense, 3.0)) / 2
    lam_away = (safe(a_attack, 2.8) + safe(h_defense, 2.8)) / 2

    if len(h2h) >= 3:
        h2h_home_goals = [int(r["home_score"]) if r["home_team"] == home_ab else int(r["away_score"]) for r in h2h]
        h2h_away_goals = [int(r["away_score"]) if r["home_team"] == home_ab else int(r["home_score"]) for r in h2h]
        lam_home = 0.65 * lam_home + 0.35 * (sum(h2h_home_goals) / len(h2h_home_goals))
        lam_away = 0.65 * lam_away + 0.35 * (sum(h2h_away_goals) / len(h2h_away_goals))

    return {"home_team": home_ab, "away_team": away_ab, "lam_home": lam_home, "lam_away": lam_away,
            "n_matches_a": len(m_a), "n_matches_b": len(m_b), "n_h2h": len(h2h)}


def run_simulation(sport, name_a, name_b, home_side="A", n=20000, seed=None):
    if sport == "fotbal":
        info = football_lambdas(name_a, name_b, home_side)
        has_draw = True
    elif sport == "hokej":
        info = hockey_lambdas(name_a, name_b, home_side)
        has_draw = False
    else:
        return {"ok": False, "error": "simulator podporuje jen 'fotbal' nebo 'hokej' (tenis ma jiny format skore - sety, ne goly)"}

    if "error" in info:
        return {"ok": False, "error": info["error"]}

    rng = random.Random(seed)
    lam_home, lam_away = info["lam_home"], info["lam_away"]
    scores = {}
    home_wins = draws = away_wins = 0
    for _ in range(n):
        gh = _poisson_sample(lam_home, rng)
        ga = _poisson_sample(lam_away, rng)
        key = (gh, ga)
        scores[key] = scores.get(key, 0) + 1
        if gh > ga:
            home_wins += 1
        elif gh < ga:
            away_wins += 1
        else:
            if has_draw:
                draws += 1
            else:
                # NHL: pri shode v regulaci rozhoduje prodlouzeni/nazvaky - 50:50
                if rng.random() < 0.5:
                    home_wins += 1
                else:
                    away_wins += 1

    top = sorted(scores.items(), key=lambda kv: -kv[1])[:8]
    top_scores = [{"home_goals": gh, "away_goals": ga, "count": c, "pct": round(100 * c / n, 1)}
                  for (gh, ga), c in top]

    return {
        "ok": True, "sport": sport, "n": n,
        "home_team": info["home_team"], "away_team": info["away_team"],
        "lam_home": round(lam_home, 3), "lam_away": round(lam_away, 3),
        "n_matches_a": info["n_matches_a"], "n_matches_b": info["n_matches_b"], "n_h2h": info["n_h2h"],
        "top_scores": top_scores,
        "nejcastejsi_vysledek": f"{top_scores[0]['home_goals']}:{top_scores[0]['away_goals']}" if top_scores else None,
        "outcome_pct": {
            "home": round(100 * home_wins / n, 1),
            "draw": round(100 * draws / n, 1) if has_draw else None,
            "away": round(100 * away_wins / n, 1),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Monte Carlo simulace zapasu (fotbal/hokej)")
    parser.add_argument("sport", choices=["fotbal", "hokej"])
    parser.add_argument("team_a")
    parser.add_argument("team_b")
    parser.add_argument("--home", choices=["A", "B"], default="A")
    parser.add_argument("--n", type=int, default=20000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_simulation(args.sport, args.team_a, args.team_b, args.home, args.n)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return

    if not result["ok"]:
        print(f"CHYBA: {result['error']}")
        sys.exit(1)

    print(f"=== Monte Carlo simulace ({result['n']}x): {result['home_team']} vs {result['away_team']} ===")
    print(f"Ocekavane goly (lambda): {result['home_team']} {result['lam_home']}, {result['away_team']} {result['lam_away']}")
    print(f"Pocet zapasu v historii: {result['home_team']} {result['n_matches_a']}, {result['away_team']} {result['n_matches_b']}, vzajemne {result['n_h2h']}")
    print()
    op = result["outcome_pct"]
    if op["draw"] is not None:
        print(f"Vysledek ze simulace: {result['home_team']} {op['home']}% / Remiza {op['draw']}% / {result['away_team']} {op['away']}%")
    else:
        print(f"Vysledek ze simulace: {result['home_team']} {op['home']}% / {result['away_team']} {op['away']}%")
    print()
    print("Nejcastejsi skore v simulaci (top 8):")
    for s in result["top_scores"]:
        print(f"  {s['home_goals']}:{s['away_goals']}  -  {s['pct']}% ({s['count']}x z {result['n']})")


if __name__ == "__main__":
    main()
