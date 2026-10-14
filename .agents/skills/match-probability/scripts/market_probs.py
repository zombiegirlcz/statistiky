#!/usr/bin/env python3
"""
market_probs.py — ČISTĚ HISTORICKÉ pravděpodobnosti pro VÍC trhů (bez kurzů).

PROČ: `aggregate_stats.py` umí jen 1X2 a přesné skóre (a rohy jen průměruje).
Tenhe modul počítá rozdělení (přes/pod) pro trhy, na které v datech máme
SKUTEČNÉ STATISTIKY — a to bez jakýchkoli kurzů:

  fotbal: góly, rohy, karty, střely na branku, střely, fauly,
          oba týmy skórují (BTTS), čisté konto, týmové přes/pod
  hokej:  góly, střely na branku (SOG), trestné minuty (PIM)
  tenis:  esa, celkový počet gamů (empiricky z obou hráčů)

METODA: stejná jako u gólů v `aggregate_stats.py`/`backtest.py` — týmový
průměr doma/venku + blend se vzájemnými zápasy (65/35), pak Poissonovo
rozdělení na součet. U každé lajny se navíc hlásí EMPIRICKÝ podíl z reálných
zápasů obou týmů (kontrola, jestli model neplave).

CO TO NENÍ: žádný edge proti trhu (na rohy/karty nemáme kurzy). Je to
pravděpodobnost odvozená z historie — poctivý model, ne garance.

Použití:
  python3 market_probs.py fotbal "Arsenal" "Chelsea" [--home A|B]
  python3 market_probs.py hokej  "Toronto" "Edmonton" [--home A|B]
  python3 market_probs.py tenis  "Jannik Sinner" "Carlos Alcaraz"
"""
import argparse
import os
import sys
from math import exp, factorial
from statistics import mean

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
import aggregate_stats as agg  # noqa: E402


# ---------------------------------------------------------------------------
# Pomocné
# ---------------------------------------------------------------------------
def _f(r, field):
    """Hodnota sloupce jako float (prazdne/None -> 0)."""
    v = r.get(field)
    if v in (None, ""):
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def poisson(k, lam):
    if lam <= 0:
        lam = 0.05
    return exp(-lam) * lam ** k / factorial(k)


def over_under(lam_total, line):
    """Pro total ~ Poisson(lam_total) a PULOVOU lajnu vrati (P_over, P_under)."""
    floor = int(line)  # line je x.5 -> scita se 0..floor jako "pod"
    p_under = sum(poisson(k, lam_total) for k in range(0, floor + 1))
    return 1 - p_under, p_under


def safe(x, default):
    return x if x is not None else default


# Specifikace statistiky: (domaci_sloupce, hostujici_sloupce) - scitaji se.
FOOTBALL_STATS = {
    "goly":            (("FTHG",), ("FTAG",)),
    "rohy":            (("HC",), ("AC",)),
    "karty":           (("HY", "HR"), ("AY", "AR")),
    "strely_na_branku": (("HST",), ("AST",)),
    "strely":          (("HS",), ("AS",)),
    "fauly":           (("HF",), ("AF",)),
}

# Rozumne defaulty (kdyz tym nema dost zapasu) - prumer nasi ligove sady.
FOOTBALL_DEFAULTS = {
    "goly": 1.2, "rohy": 5.0, "karty": 2.0,
    "strely_na_branku": 4.5, "strely": 12.0, "fauly": 11.0,
}

# Lajny, ktere se u kazde statistiky vypisuji.
FOOTBALL_LINES = {
    "goly": [1.5, 2.5, 3.5],
    "rohy": [8.5, 9.5, 10.5, 11.5],
    "karty": [2.5, 3.5, 4.5, 5.5],
    "strely_na_branku": [7.5, 8.5, 9.5, 10.5],
    "strely": [20.5, 24.5, 28.5],
    "fauly": [18.5, 21.5, 24.5],
}


def _venue_rates(rows, team, venue, spec):
    """Prumer 'for' a 'against' pro tym na danem hristi. Vraci (for, against, n)."""
    home_f, away_f = spec
    f_vals, a_vals = [], []
    for r in rows:
        if r.get("HomeTeam") == team and venue == "H":
            f_vals.append(sum(_f(r, x) for x in home_f))
            a_vals.append(sum(_f(r, x) for x in away_f))
        elif r.get("AwayTeam") == team and venue == "A":
            f_vals.append(sum(_f(r, x) for x in away_f))
            a_vals.append(sum(_f(r, x) for x in home_f))
    return (mean(f_vals) if f_vals else None,
            mean(a_vals) if a_vals else None,
            len(f_vals))


def _h2h_rates(h2h_rows, home_team, spec):
    """Prumerne hodnoty pro home_team a jeho soupere ve vzajemnych zapasech."""
    home_f, away_f = spec
    h_vals, a_vals = [], []
    for r in h2h_rows:
        if r.get("HomeTeam") == home_team:
            h_vals.append(sum(_f(r, x) for x in home_f))
            a_vals.append(sum(_f(r, x) for x in away_f))
        else:
            h_vals.append(sum(_f(r, x) for x in away_f))
            a_vals.append(sum(_f(r, x) for x in home_f))
    return h_vals, a_vals


def predict_lambdas(rows, home_team, away_team, h2h_rows, spec, default):
    """Vrati (lam_home, lam_away) pro danou statistiku - tymovy prumer
    doma/venku + blend s h2h (65/35), stejne jako u golu."""
    h_for, h_against, _ = _venue_rates(rows, home_team, "H", spec)
    a_for, a_against, _ = _venue_rates(rows, away_team, "A", spec)
    lam_h = (safe(h_for, default) + safe(a_against, default)) / 2
    lam_a = (safe(a_for, default) + safe(h_against, default)) / 2

    if len(h2h_rows) >= 3:
        h_vals, a_vals = _h2h_rates(h2h_rows, home_team, spec)
        if h_vals:
            lam_h = 0.65 * lam_h + 0.35 * mean(h_vals)
        if a_vals:
            lam_a = 0.65 * lam_a + 0.35 * mean(a_vals)
    return lam_h, lam_a


def empirical_overs(all_team_rows, spec, lines):
    """Empiricky podil zapasu NAD lajnou - ze VSECH zapasu obou tymu
    (celkovy soucet statistiky v zapase). Kontrola modelu."""
    totals = []
    for r in all_team_rows:
        home_f, away_f = spec
        totals.append(sum(_f(r, x) for x in home_f) + sum(_f(r, x) for x in away_f))
    out = {}
    for line in lines:
        if totals:
            over = sum(1 for t in totals if t > line) / len(totals)
            out[line] = (over, len(totals))
        else:
            out[line] = (None, 0)
    return out


def analyze_football(name_a, name_b, home_side="A"):
    rows = agg.load_football_rows()
    teams = agg.all_football_teams(rows)
    team_a, sa = agg.fuzzy_pick(name_a, teams)
    team_b, sb = agg.fuzzy_pick(name_b, teams)
    if not team_a or not team_b:
        return f"CHYBA: tym nenalezen ('{name_a}'->{team_a}, '{name_b}'->{team_b})."

    home_team, away_team = (team_a, team_b) if home_side != "B" else (team_b, team_a)
    all_team_rows = [r for r in rows if r.get("HomeTeam") in (team_a, team_b) or r.get("AwayTeam") in (team_a, team_b)]
    h2h = [r for r in rows if {r.get("HomeTeam"), r.get("AwayTeam")} == {team_a, team_b}]

    lines_out = []
    lines_out.append(f"=== FOTBAL: {home_team} (domaci) vs {away_team} (hoste) ===")
    lines_out.append(f"Vzajemnych zapasu: {len(h2h)} | zapasu obou tymu celkem: {len(all_team_rows)}")
    lines_out.append("")

    lambdas = {}
    for stat, spec in FOOTBALL_STATS.items():
        lh, la = predict_lambdas(rows, home_team, away_team, h2h, spec, FOOTBALL_DEFAULTS[stat])
        lambdas[stat] = (lh, la)
        lt = lh + la
        lines_out.append(f"--- {stat.upper()} (ocekavano {lh:.2f} + {la:.2f} = {lt:.2f}) ---")
        emp = empirical_overs(all_team_rows, spec, FOOTBALL_LINES[stat])
        for line in FOOTBALL_LINES[stat]:
            p_over, p_under = over_under(lt, line)
            e_over, en = emp[line]
            emp_txt = f" | empiricky z {en} zapasu: {e_over:.0%}" if e_over is not None else ""
            lines_out.append(f"   {line}: přes {p_over:.0%} / pod {p_under:.0%}{emp_txt}")
        lines_out.append("")

    # BTTS + clean sheet z gólových lambd
    lh, la = lambdas["goly"]
    p_h0 = poisson(0, lh)
    p_a0 = poisson(0, la)
    btts = (1 - p_h0) * (1 - p_a0)
    lines_out.append("--- OBA TYMY SKORUJI (BTTS) ---")
    lines_out.append(f"   ano {btts:.0%} / ne {1 - btts:.0%}")
    lines_out.append(f"   {home_team} ciste konto: {p_a0:.0%} | {away_team} ciste konto: {p_h0:.0%}")
    return "\n".join(lines_out)


# ---------------------------------------------------------------------------
# HOKEJ
# ---------------------------------------------------------------------------
HOCKEY_STATS = {
    "goly":  (("home_score",), ("away_score",)),
    "sog":   (("home_sog",), ("away_sog",)),
    "pim":   (("home_pim",), ("away_pim",)),
}
HOCKEY_DEFAULTS = {"goly": 3.0, "sog": 30.0, "pim": 8.0}
HOCKEY_LINES = {"goly": [4.5, 5.5, 6.5], "sog": [56.5, 60.5, 64.5], "pim": [10.5, 14.5, 18.5]}


def analyze_hockey(name_a, name_b, home_side="A"):
    rows = agg.load_hockey_rows()
    ab_a = agg.resolve_nhl(name_a)
    ab_b = agg.resolve_nhl(name_b)
    if not ab_a or not ab_b:
        return f"CHYBA: NHL tym nenalezen ('{name_a}'->{ab_a}, '{name_b}'->{ab_b})."

    home_ab, away_ab = (ab_a, ab_b) if home_side != "B" else (ab_b, ab_a)
    # prevod na jednotny tvar (domaci/hostujici sloupce) - pouzijeme docasne aliasy
    norm_rows = []
    for r in rows:
        norm_rows.append({
            "HomeTeam": r["home_team"], "AwayTeam": r["away_team"],
            "home_score": r["home_score"], "away_score": r["away_score"],
            "home_sog": r.get("home_sog"), "away_sog": r.get("away_sog"),
            "home_pim": r.get("home_pim"), "away_pim": r.get("away_pim"),
        })
    all_rows = [r for r in norm_rows if r["HomeTeam"] in (ab_a, ab_b) or r["AwayTeam"] in (ab_a, ab_b)]
    h2h = [r for r in norm_rows if {r["HomeTeam"], r["AwayTeam"]} == {ab_a, ab_b}]

    out = [f"=== HOKEJ (NHL): {home_ab} (domaci) vs {away_ab} (hoste) ===",
           f"Vzajemnych zapasu: {len(h2h)} | zapasu obou tymu celkem: {len(all_rows)}", ""]
    for stat, spec in HOCKEY_STATS.items():
        lh, la = predict_lambdas(norm_rows, home_ab, away_ab, h2h, spec, HOCKEY_DEFAULTS[stat])
        lt = lh + la
        out.append(f"--- {stat.upper()} (ocekavano {lh:.2f} + {la:.2f} = {lt:.2f}) ---")
        emp = empirical_overs(all_rows, spec, HOCKEY_LINES[stat])
        for line in HOCKEY_LINES[stat]:
            p_over, p_under = over_under(lt, line)
            e_over, en = emp[line]
            emp_txt = f" | empiricky z {en} zapasu: {e_over:.0%}" if e_over is not None else ""
            out.append(f"   {line}: přes {p_over:.0%} / pod {p_under:.0%}{emp_txt}")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# TENIS
# ---------------------------------------------------------------------------
def _parse_total_games(score):
    """Ze zapisu '7-6(5) 6-4' secte vsechny gemy obou hracu."""
    import re
    total = 0
    found = False
    for m in re.finditer(r"(\d+)-(\d+)", score or ""):
        total += int(m.group(1)) + int(m.group(2))
        found = True
    return total if found else None


def analyze_tennis(name_a, name_b):
    rows = agg.load_tennis_rows()
    names = sorted({r.get("winner_name", "") for r in rows} | {r.get("loser_name", "") for r in rows})
    pa, sa = agg.fuzzy_pick(name_a, names)
    pb, sb = agg.fuzzy_pick(name_b, names)
    if not pa or not pb:
        return f"CHYBA: hrac nenalezen ('{name_a}'->{pa}, '{name_b}'->{pb})."

    def player_rows(name):
        return [r for r in rows if r.get("winner_name") == name or r.get("loser_name") == name]

    def ace_rate(name):
        vals = []
        for r in player_rows(name):
            if r.get("winner_name") == name:
                vals.append(_f(r, "w_ace"))
            else:
                vals.append(_f(r, "l_ace"))
        return vals

    def total_games(name):
        vals = []
        for r in player_rows(name):
            g = _parse_total_games(r.get("score"))
            if g:
                vals.append(g)
        return vals

    aces_a, aces_b = ace_rate(pa), ace_rate(pb)
    games_a, games_b = total_games(pa), total_games(pb)

    out = [f"=== TENIS: {pa} vs {pb} ===",
           f"Zapasu v datech: {pa} {len(player_rows(pa))}, {pb} {len(player_rows(pb))}", ""]

    # ESA - nejdriv per-hrac (empiricky), pak SOUCET v zapase jako Poisson(la+lb)
    out.append("--- ESA (nejdriv kazdy hrac zvlast, empiricky) ---")
    if aces_a and aces_b:
        la, lb = mean(aces_a), mean(aces_b)
        out.append(f"   prumer {pa}: {la:.1f} esa/zapas (n={len(aces_a)})")
        out.append(f"   prumer {pb}: {lb:.1f} esa/zapas (n={len(aces_b)})")
        lam_total = la + lb
        out.append(f"   ocekavany SOUCET v zapase (Poisson): {lam_total:.1f}")
        for line in (9.5, 12.5, 15.5, 18.5):
            p_over, p_under = over_under(lam_total, line)
            out.append(f"   {line}: přes {p_over:.0%} / pod {p_under:.0%}")
        out.append("   (POZOR: soucet je model Poisson ze dvou prumeru, ne primy pocet - "
                   "bod-po-bodu esa nemame, jen zapasove soucty kazdeho hrace zvlast)")
    else:
        out.append("   (zadna data o esech)")
    out.append("")

    # CELKOVY POCET GAMU
    all_games = games_a + games_b
    out.append("--- CELKOVY POCET GAMU (empiricky) ---")
    if all_games:
        out.append(f"   prumer {mean(all_games):.1f} gamu/zapas (n={len(all_games)})")
        for line in (20.5, 22.5, 24.5):
            over = sum(1 for v in all_games if v > line) / len(all_games)
            out.append(f"   {line}: přes {over:.0%} / pod {1 - over:.0%}")
    else:
        out.append("   (zadna data o gamy)")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sport", choices=["fotbal", "tenis", "hokej"])
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--home", choices=["A", "B"], default="A")
    args = ap.parse_args()
    if args.sport == "fotbal":
        print(analyze_football(args.a, args.b, args.home))
    elif args.sport == "hokej":
        print(analyze_hockey(args.a, args.b, args.home))
    else:
        print(analyze_tennis(args.a, args.b))


if __name__ == "__main__":
    main()
