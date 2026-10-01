#!/usr/bin/env python3
"""
Agreguje VSECHNA relevantni historicka data pro dva tymy/hrace z /statistiky
a spocita odhad pravdepodobnosti vysledku nadchazejiciho zapasu.

Pouziti:
    python aggregate_stats.py fotbal "Arsenal" "Chelsea" [--home A|B]
    python aggregate_stats.py tenis "Jannik Sinner" "Carlos Alcaraz"
    python aggregate_stats.py hokej "Toronto" "Edmonton" [--home A|B]

Skript necte jen "posledních par zapasu nazdarbuh" - projde VSECHNY sezonni
soubory dane sportovni slozky, najde VSECHNY zapasy, kde hraje tym/hrac A
nebo B, a z nich spocita vzajemnou bilanci, nedavnou formu a pomocne statistiky.
Vystup je surova data + jeden navrzeny odhad procent - finalni slovo (a
pripadne upraveni vah) ma Claude podle instrukci v SKILL.md.
"""
import argparse
import csv
import difflib
import glob
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPT_DIR))))
# _SCRIPT_DIR = <BASE>/.claude/skills/match-probability/scripts -> BASE = /root/statistiky

NHL_ALIASES = {
    "ANA": ["anaheim", "ducks", "ana"], "BOS": ["boston", "bruins", "bos"],
    "BUF": ["buffalo", "sabres", "buf"], "CAR": ["carolina", "hurricanes", "car"],
    "CBJ": ["columbus", "blue jackets", "cbj"], "CGY": ["calgary", "flames", "cgy"],
    "CHI": ["chicago", "blackhawks", "chi"], "COL": ["colorado", "avalanche", "avs", "col"],
    "DAL": ["dallas", "stars", "dal"], "DET": ["detroit", "red wings", "det"],
    "EDM": ["edmonton", "oilers", "edm"], "FLA": ["florida", "panthers", "fla"],
    "LAK": ["los angeles", "la kings", "kings", "lak"], "MIN": ["minnesota", "wild", "min"],
    "MTL": ["montreal", "canadiens", "habs", "mtl"], "NJD": ["new jersey", "devils", "njd"],
    "NSH": ["nashville", "predators", "preds", "nsh"], "NYI": ["ny islanders", "islanders", "nyi"],
    "NYR": ["ny rangers", "rangers", "nyr"], "OTT": ["ottawa", "senators", "sens", "ott"],
    "PHI": ["philadelphia", "flyers", "phi"], "PIT": ["pittsburgh", "penguins", "pens", "pit"],
    "SEA": ["seattle", "kraken", "sea"], "SJS": ["san jose", "sharks", "sjs"],
    "STL": ["st louis", "st. louis", "blues", "stl"], "TBL": ["tampa bay", "lightning", "tbl", "tampa"],
    "TOR": ["toronto", "maple leafs", "leafs", "tor"], "UTA": ["utah", "mammoth", "uta"],
    "VAN": ["vancouver", "canucks", "van"], "VGK": ["vegas", "golden knights", "vgk"],
    "WPG": ["winnipeg", "jets", "wpg"], "WSH": ["washington", "capitals", "caps", "wsh"],
}


def norm(s):
    return s.strip().lower()


def fmt_pct(x):
    return f"{x:.0%}" if x is not None else "n/a"


def fmt_num(x, dec=1):
    return f"{x:.{dec}f}" if x is not None else "n/a"


def resolve_nhl(name):
    n = norm(name)
    if n.upper() in NHL_ALIASES:
        return n.upper()
    for abbrev, aliases in NHL_ALIASES.items():
        if n in aliases or any(n in a or a in n for a in aliases):
            return abbrev
    return None


def fuzzy_pick(name, candidates, cutoff=0.6):
    n = norm(name)
    for c in candidates:
        if n == norm(c):
            return c, 1.0
    matches = difflib.get_close_matches(name, candidates, n=3, cutoff=cutoff)
    if matches:
        return matches[0], 1.0 - difflib.SequenceMatcher(None, norm(name), norm(matches[0])).ratio() * 0 + difflib.SequenceMatcher(None, norm(name), norm(matches[0])).ratio()
    substr = [c for c in candidates if n in norm(c) or norm(c) in n]
    if substr:
        return substr[0], 0.9
    return None, 0.0


# ---------------------------------------------------------------------------
# FOTBAL
# ---------------------------------------------------------------------------
def load_football_rows():
    rows = []
    for path in sorted(glob.glob(os.path.join(BASE, "fotbal", "*.csv"))):
        season = os.path.basename(path).split("_")[0]
        with open(path, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                if not row.get("HomeTeam"):
                    continue
                row["_season"] = season
                row["_league_file"] = os.path.basename(path)
                rows.append(row)
    return rows


def all_football_teams(rows):
    teams = set()
    for r in rows:
        teams.add(r["HomeTeam"]); teams.add(r["AwayTeam"])
    return sorted(teams)


def analyze_football(name_a, name_b, home_side):
    rows = load_football_rows()
    teams = all_football_teams(rows)
    team_a, score_a = fuzzy_pick(name_a, teams)
    team_b, score_b = fuzzy_pick(name_b, teams)
    report = []
    if not team_a or not team_b:
        report.append(f"CHYBA: nepodarilo se jednoznacne najit tym(y) v datech.")
        report.append(f"  '{name_a}' -> {team_a} (shoda {score_a:.2f})")
        report.append(f"  '{name_b}' -> {team_b} (shoda {score_b:.2f})")
        report.append(f"Dostupne tymy (vzorek): {teams[:30]}")
        return "\n".join(report)

    def team_matches(team):
        return [r for r in rows if r["HomeTeam"] == team or r["AwayTeam"] == team]

    def result_for(team, r):
        if r["HomeTeam"] == team:
            gf, ga = int(r["FTHG"]), int(r["FTAG"])
            venue = "H"
        else:
            gf, ga = int(r["FTAG"]), int(r["FTHG"])
            venue = "A"
        res = "W" if gf > ga else ("D" if gf == ga else "L")
        return res, venue, gf, ga

    m_a = sorted(team_matches(team_a), key=lambda r: (r["_season"], r.get("Date", "")))
    m_b = sorted(team_matches(team_b), key=lambda r: (r["_season"], r.get("Date", "")))
    h2h = [r for r in rows if {r["HomeTeam"], r["AwayTeam"]} == {team_a, team_b}]
    h2h = sorted(h2h, key=lambda r: (r["_season"], r.get("Date", "")))

    def summarize(team, matches):
        results = [result_for(team, r) for r in matches]
        n = len(results)
        w = sum(1 for res, *_ in results if res == "W")
        d = sum(1 for res, *_ in results if res == "D")
        l = sum(1 for res, *_ in results if res == "L")
        gf = sum(x[2] for x in results)
        ga = sum(x[3] for x in results)
        home_results = [res for res, v, *_ in results if v == "H"]
        away_results = [res for res, v, *_ in results if v == "A"]
        hw = home_results.count("W") / len(home_results) if home_results else None
        aw = away_results.count("W") / len(away_results) if away_results else None
        recent = results[-10:]
        recent_wr = sum(1 for res, *_ in recent if res == "W") / len(recent) if recent else 0
        # prumerne rohy a strely, pokud sloupce existuji
        corners = []
        for r in matches:
            if r["HomeTeam"] == team and r.get("HC"):
                corners.append(int(r["HC"]))
            elif r["AwayTeam"] == team and r.get("AC"):
                corners.append(int(r["AC"]))
        avg_corners = sum(corners) / len(corners) if corners else None
        return {
            "n": n, "w": w, "d": d, "l": l, "win_rate": w / n if n else 0,
            "gf_avg": gf / n if n else 0, "ga_avg": ga / n if n else 0,
            "home_win_rate": hw, "away_win_rate": aw,
            "recent10_form": "".join(res for res, *_ in recent),
            "recent10_win_rate": recent_wr,
            "avg_corners": avg_corners,
        }

    sa = summarize(team_a, m_a)
    sb = summarize(team_b, m_b)

    h2h_a_wins = sum(1 for r in h2h if result_for(team_a, r)[0] == "W")
    h2h_b_wins = sum(1 for r in h2h if result_for(team_b, r)[0] == "W")
    h2h_draws = len(h2h) - h2h_a_wins - h2h_b_wins

    league_draw_rates = {}
    by_file = {}
    for r in rows:
        by_file.setdefault(r["_league_file"], []).append(r)
    # pouzijeme draw rate ze souboru, kde A nebo B hraji nejcasteji
    relevant_files = {r["_league_file"] for r in m_a + m_b}
    all_draw_rows = [r for f in relevant_files for r in by_file[f]]
    league_draw_rate = (sum(1 for r in all_draw_rows if r["FTR"] == "D") / len(all_draw_rows)) if all_draw_rows else 0.25

    home_team, away_team = (team_a, team_b) if home_side != "B" else (team_b, team_a)
    home_stats, away_stats = (sa, sb) if home_side != "B" else (sb, sa)

    def safe(x, default=0.4):
        return x if x is not None else default

    score_home = 0.4 * home_stats["recent10_win_rate"] + 0.3 * safe(home_stats["home_win_rate"]) + 0.3 * (h2h_a_wins / len(h2h) if h2h and home_team == team_a else (h2h_b_wins / len(h2h) if h2h and home_team == team_b else home_stats["win_rate"]))
    score_away = 0.4 * away_stats["recent10_win_rate"] + 0.3 * safe(away_stats["away_win_rate"]) + 0.3 * (h2h_b_wins / len(h2h) if h2h and away_team == team_b else (h2h_a_wins / len(h2h) if h2h and away_team == team_a else away_stats["win_rate"]))
    draw_component = league_draw_rate

    total = score_home + score_away + draw_component
    pct_home = round(100 * score_home / total)
    pct_away = round(100 * score_away / total)
    pct_draw = 100 - pct_home - pct_away

    report.append(f"=== FOTBAL: {team_a} vs {team_b} ===")
    report.append(f"Domaci tym pro tento vypocet: {home_team} (predpoklad podle poradi zadani, lze zmenit --home)")
    report.append("")
    report.append(f"[{team_a}] celkem {sa['n']} zapasu v datech | W{sa['w']}-D{sa['d']}-L{sa['l']} (win rate {sa['win_rate']:.0%})")
    report.append(f"  prumer branek: {sa['gf_avg']:.2f} vstrelenych / {sa['ga_avg']:.2f} obdrzenych | prumer rohu: {fmt_num(sa['avg_corners'])}")
    report.append(f"  doma win rate: {fmt_pct(sa['home_win_rate'])}, venku win rate: {fmt_pct(sa['away_win_rate'])}")
    report.append(f"  posledni forma (10 zapasu, nejnovejsi vpravo): {sa['recent10_form']} (win rate {sa['recent10_win_rate']:.0%})")
    report.append("")
    report.append(f"[{team_b}] celkem {sb['n']} zapasu v datech | W{sb['w']}-D{sb['d']}-L{sb['l']} (win rate {sb['win_rate']:.0%})")
    report.append(f"  prumer branek: {sb['gf_avg']:.2f} vstrelenych / {sb['ga_avg']:.2f} obdrzenych | prumer rohu: {fmt_num(sb['avg_corners'])}")
    report.append(f"  doma win rate: {fmt_pct(sb['home_win_rate'])}, venku win rate: {fmt_pct(sb['away_win_rate'])}")
    report.append(f"  posledni forma (10 zapasu, nejnovejsi vpravo): {sb['recent10_form']} (win rate {sb['recent10_win_rate']:.0%})")
    report.append("")
    report.append(f"Vzajemne zapasy v datech: {len(h2h)}x | {team_a} vyhral {h2h_a_wins}x, remiza {h2h_draws}x, {team_b} vyhral {h2h_b_wins}x")
    for r in h2h[-5:]:
        report.append(f"  {r['_season']} {r.get('Date','?')}: {r['HomeTeam']} {r['FTHG']}:{r['FTAG']} {r['AwayTeam']}")
    report.append(f"Prumerna remizovost v relevantnich souteznich (zdroj pro draw %): {league_draw_rate:.0%}")
    report.append("")
    report.append("=== ODHAD (navrh, Claude muze dle SKILL.md jemne doladit) ===")
    report.append(f"{home_team} (domaci) {pct_home}% / Remiza {pct_draw}% / {away_team} (hoste) {pct_away}%")
    return "\n".join(report)


# ---------------------------------------------------------------------------
# TENIS
# ---------------------------------------------------------------------------
def load_tennis_rows():
    rows = []
    for path in sorted(glob.glob(os.path.join(BASE, "tenis", "*_matches_*.csv"))):
        tour = "ATP" if "atp" in os.path.basename(path) else "WTA"
        with open(path, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                row["_tour"] = tour
                row["_file"] = os.path.basename(path)
                rows.append(row)
    return rows


def analyze_tennis(name_a, name_b):
    rows = load_tennis_rows()
    names = set()
    for r in rows:
        if r.get("winner_name"):
            names.add(r["winner_name"])
        if r.get("loser_name"):
            names.add(r["loser_name"])
    names = sorted(names)
    player_a, score_a = fuzzy_pick(name_a, names)
    player_b, score_b = fuzzy_pick(name_b, names)
    if not player_a or not player_b:
        return (f"CHYBA: nepodarilo se najit hrace.\n"
                f"  '{name_a}' -> {player_a} (shoda {score_a:.2f})\n"
                f"  '{name_b}' -> {player_b} (shoda {score_b:.2f})")

    def player_matches(name):
        return [r for r in rows if r.get("winner_name") == name or r.get("loser_name") == name]

    def chrono_key(r):
        return (r.get("tourney_date", ""), r.get("match_num", "0"))

    m_a = sorted(player_matches(player_a), key=chrono_key)
    m_b = sorted(player_matches(player_b), key=chrono_key)
    h2h = sorted([r for r in rows if {r.get("winner_name"), r.get("loser_name")} == {player_a, player_b}], key=chrono_key)

    def summarize(name, matches):
        n = len(matches)
        wins = sum(1 for r in matches if r.get("winner_name") == name)
        recent = matches[-15:]
        recent_wins = sum(1 for r in recent if r.get("winner_name") == name)
        aces, df_, svpt, firstwon = [], [], [], []
        for r in matches:
            won = r.get("winner_name") == name
            prefix = "w_" if won else "l_"
            try:
                aces.append(int(r[prefix + "ace"]))
                df_.append(int(r[prefix + "df"]))
            except (ValueError, KeyError):
                pass
        return {
            "n": n, "wins": wins, "win_rate": wins / n if n else 0,
            "recent_n": len(recent), "recent_wins": recent_wins,
            "recent_win_rate": recent_wins / len(recent) if recent else 0,
            "avg_ace": sum(aces) / len(aces) if aces else None,
            "avg_df": sum(df_) / len(df_) if df_ else None,
        }

    sa = summarize(player_a, m_a)
    sb = summarize(player_b, m_b)
    h2h_a = sum(1 for r in h2h if r.get("winner_name") == player_a)
    h2h_b = len(h2h) - h2h_a

    h2h_rate_a = h2h_a / len(h2h) if h2h else sa["win_rate"]
    h2h_rate_b = h2h_b / len(h2h) if h2h else sb["win_rate"]

    score_a_val = 0.5 * sa["recent_win_rate"] + 0.3 * h2h_rate_a + 0.2 * sa["win_rate"]
    score_b_val = 0.5 * sb["recent_win_rate"] + 0.3 * h2h_rate_b + 0.2 * sb["win_rate"]
    total = score_a_val + score_b_val
    pct_a = round(100 * score_a_val / total) if total else 50
    pct_b = 100 - pct_a

    report = []
    report.append(f"=== TENIS: {player_a} vs {player_b} ===")
    report.append("")
    report.append(f"[{player_a}] celkem {sa['n']} zapasu v datech (2021-2026), win rate {sa['win_rate']:.0%}")
    report.append(f"  poslednich {sa['recent_n']} zapasu: {sa['recent_wins']} vyher ({sa['recent_win_rate']:.0%})")
    report.append(f"  prumer es: {fmt_num(sa['avg_ace'])}, prumer dvojchyb: {fmt_num(sa['avg_df'])}")
    report.append("")
    report.append(f"[{player_b}] celkem {sb['n']} zapasu v datech (2021-2026), win rate {sb['win_rate']:.0%}")
    report.append(f"  poslednich {sb['recent_n']} zapasu: {sb['recent_wins']} vyher ({sb['recent_win_rate']:.0%})")
    report.append(f"  prumer es: {fmt_num(sb['avg_ace'])}, prumer dvojchyb: {fmt_num(sb['avg_df'])}")
    report.append("")
    report.append(f"Vzajemne zapasy v datech: {len(h2h)}x | {player_a} {h2h_a}:{h2h_b} {player_b}")
    for r in h2h[-5:]:
        report.append(f"  {r.get('tourney_date')} {r.get('tourney_name')} ({r.get('round')}): {r['winner_name']} por. {r['loser_name']} {r.get('score')}")
    report.append("")
    report.append("=== ODHAD (navrh, Claude muze dle SKILL.md jemne doladit) ===")
    report.append(f"{player_a} {pct_a}% / {player_b} {pct_b}%")
    return "\n".join(report)


# ---------------------------------------------------------------------------
# HOKEJ
# ---------------------------------------------------------------------------
def load_hockey_rows():
    rows = []
    for path in sorted(glob.glob(os.path.join(BASE, "hokej", "NHL_*.csv"))):
        with open(path, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                row["_season"] = os.path.basename(path)
                rows.append(row)
    return rows


def analyze_hockey(name_a, name_b, home_side):
    rows = load_hockey_rows()
    abbrev_a = resolve_nhl(name_a)
    abbrev_b = resolve_nhl(name_b)
    if not abbrev_a or not abbrev_b:
        return (f"CHYBA: nepodarilo se najit NHL tym.\n"
                f"  '{name_a}' -> {abbrev_a}\n  '{name_b}' -> {abbrev_b}\n"
                f"Dostupne zkratky: {sorted(NHL_ALIASES.keys())}")

    def team_matches(ab):
        return [r for r in rows if r["home_team"] == ab or r["away_team"] == ab]

    def result_for(ab, r):
        is_home = r["home_team"] == ab
        gf = int(r["home_score"] if is_home else r["away_score"])
        ga = int(r["away_score"] if is_home else r["home_score"])
        return ("W" if gf > ga else "L"), ("H" if is_home else "A"), gf, ga

    m_a = sorted(team_matches(abbrev_a), key=lambda r: (r["_season"], r["date"]))
    m_b = sorted(team_matches(abbrev_b), key=lambda r: (r["_season"], r["date"]))
    h2h = sorted([r for r in rows if {r["home_team"], r["away_team"]} == {abbrev_a, abbrev_b}], key=lambda r: (r["_season"], r["date"]))

    def summarize(ab, matches):
        results = [result_for(ab, r) for r in matches]
        n = len(results)
        w = sum(1 for res, *_ in results if res == "W")
        home_r = [res for res, v, *_ in results if v == "H"]
        away_r = [res for res, v, *_ in results if v == "A"]
        hw = home_r.count("W") / len(home_r) if home_r else None
        aw = away_r.count("W") / len(away_r) if away_r else None
        recent = results[-15:]
        recent_wr = sum(1 for res, *_ in recent if res == "W") / len(recent) if recent else 0
        sog = []
        for r in matches:
            is_home = r["home_team"] == ab
            val = r.get("home_sog") if is_home else r.get("away_sog")
            if val:
                try:
                    sog.append(int(val))
                except ValueError:
                    pass
        return {
            "n": n, "w": w, "win_rate": w / n if n else 0,
            "home_win_rate": hw, "away_win_rate": aw,
            "recent15_form": "".join(res for res, *_ in recent),
            "recent15_win_rate": recent_wr,
            "avg_sog": sum(sog) / len(sog) if sog else None,
        }

    sa = summarize(abbrev_a, m_a)
    sb = summarize(abbrev_b, m_b)
    h2h_a_wins = sum(1 for r in h2h if result_for(abbrev_a, r)[0] == "W")
    h2h_b_wins = len(h2h) - h2h_a_wins

    home_ab, away_ab = (abbrev_a, abbrev_b) if home_side != "B" else (abbrev_b, abbrev_a)
    home_stats, away_stats = (sa, sb) if home_side != "B" else (sb, sa)

    def safe(x, d=0.5):
        return x if x is not None else d

    h2h_rate_home = (h2h_a_wins / len(h2h) if h2h and home_ab == abbrev_a else (h2h_b_wins / len(h2h) if h2h else home_stats["win_rate"]))
    h2h_rate_away = (h2h_b_wins / len(h2h) if h2h and away_ab == abbrev_b else (h2h_a_wins / len(h2h) if h2h else away_stats["win_rate"]))

    score_home = 0.45 * home_stats["recent15_win_rate"] + 0.25 * safe(home_stats["home_win_rate"]) + 0.30 * h2h_rate_home
    score_away = 0.45 * away_stats["recent15_win_rate"] + 0.25 * safe(away_stats["away_win_rate"]) + 0.30 * h2h_rate_away
    total = score_home + score_away
    pct_home = round(100 * score_home / total) if total else 50
    pct_away = 100 - pct_home

    report = []
    report.append(f"=== HOKEJ (NHL): {abbrev_a} vs {abbrev_b} ===")
    report.append(f"Domaci tym pro tento vypocet: {home_ab} (predpoklad podle poradi zadani, lze zmenit --home)")
    report.append("")
    report.append(f"[{abbrev_a}] celkem {sa['n']} zapasu | win rate {sa['win_rate']:.0%} | prumer strel na branku {fmt_num(sa['avg_sog'])}")
    report.append(f"  doma win rate: {fmt_pct(sa['home_win_rate'])}, venku win rate: {fmt_pct(sa['away_win_rate'])}")
    report.append(f"  poslednich 15 zapasu forma: {sa['recent15_form']} (win rate {sa['recent15_win_rate']:.0%})")
    report.append("")
    report.append(f"[{abbrev_b}] celkem {sb['n']} zapasu | win rate {sb['win_rate']:.0%} | prumer strel na branku {fmt_num(sb['avg_sog'])}")
    report.append(f"  doma win rate: {fmt_pct(sb['home_win_rate'])}, venku win rate: {fmt_pct(sb['away_win_rate'])}")
    report.append(f"  poslednich 15 zapasu forma: {sb['recent15_form']} (win rate {sb['recent15_win_rate']:.0%})")
    report.append("")
    report.append(f"Vzajemne zapasy v datech: {len(h2h)}x | {abbrev_a} vyhral {h2h_a_wins}x, {abbrev_b} vyhral {h2h_b_wins}x")
    for r in h2h[-5:]:
        report.append(f"  {r['date']}: {r['away_team']} {r['away_score']}:{r['home_score']} {r['home_team']}")
    report.append("")
    report.append("=== ODHAD (navrh, Claude muze dle SKILL.md jemne doladit) ===")
    report.append(f"{home_ab} (domaci) {pct_home}% / {away_ab} (hoste) {pct_away}%")
    return "\n".join(report)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sport", choices=["fotbal", "tenis", "hokej"])
    ap.add_argument("team_a")
    ap.add_argument("team_b")
    ap.add_argument("--home", choices=["A", "B"], default="A", help="Ktery tym/hrac hraje doma (vychozi: A)")
    args = ap.parse_args()

    if args.sport == "fotbal":
        print(analyze_football(args.team_a, args.team_b, args.home))
    elif args.sport == "tenis":
        print(analyze_tennis(args.team_a, args.team_b))
    elif args.sport == "hokej":
        print(analyze_hockey(args.team_a, args.team_b, args.home))


if __name__ == "__main__":
    sys.exit(main())
