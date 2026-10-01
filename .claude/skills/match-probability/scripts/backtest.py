#!/usr/bin/env python3
"""
Backtest: na vzorku jiz odehranych zapasu simuluje, co by model predpovedel
PRED zapasem (pouzije jen data s datem drive nez testovany zapas), a porovna
to se skutecnym vysledkem - presne skore, vic rohu, vic karet (fotbal) /
vic strel na branku, vic trestnych minut (hokej) / presny pomer setu, esa,
dvojchyby (tenis).

Testovaci vzorek je NAHODNY napric celym obdobim (ne jen poslednich N zapasu) -
"poslednich N" se v praxi casto nachumeli kolem jedne udalosti (play-off serie,
jeden turnaj) a zkresli vysledek. Nahodny vzorek (pevne seed kvuli
opakovatelnosti) dava poctivejsi odhad skutecne presnosti.

Pouziti:
    python3 backtest.py fotbal [N]   # N = pocet nahodne vybranych zapasu (default 40)
    python3 backtest.py hokej [N]    # default 30
    python3 backtest.py tenis [N]    # default 30
"""
import csv
import glob
import os
import random
import sys
from datetime import datetime
from math import exp, factorial

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPT_DIR))))


def poisson(k, lam):
    if lam <= 0:
        lam = 0.05
    return exp(-lam) * lam ** k / factorial(k)


def best_score(lambda_a, lambda_b, max_goals=6):
    best, best_p = (0, 0), -1
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson(i, lambda_a) * poisson(j, lambda_b)
            if p > best_p:
                best_p, best = p, (i, j)
    return best


# ---------------------------------------------------------------------------
# FOTBAL
# ---------------------------------------------------------------------------
def load_football_all():
    rows = []
    for path in sorted(glob.glob(os.path.join(BASE, "fotbal", "*.csv"))):
        league_file = os.path.basename(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                if not row.get("HomeTeam") or not row.get("Date"):
                    continue
                try:
                    row["_d"] = datetime.strptime(row["Date"], "%d/%m/%Y")
                except ValueError:
                    continue
                row["_league_file"] = league_file
                rows.append(row)
    return rows


def pick_football_testset(rows, n, seed=42):
    """Nahodny vzorek napric celym obdobim (ne jen poslednich N zapasu), aby
    se predeslo zkresleni z toho, ze se 'nejnovejsi' zapasy chumeli kolem
    jedne souteze/tydne. Prvnich par mesicu historie (2021) se preskakuje,
    aby mel kazdy testovany zapas aspon rok predchozich dat k dispozici."""
    complete = [r for r in rows if all(r.get(c) not in (None, "") for c in
                ("FTHG", "FTAG", "FTR", "HC", "AC", "HY", "AY", "HR", "AR"))
                and r["_d"] >= datetime(2022, 7, 1)]
    rng = random.Random(seed)
    sample = rng.sample(complete, min(n, len(complete)))
    sample.sort(key=lambda r: r["_d"])
    return sample


def team_rate(rows, team, venue, field, cutoff):
    """Prumer hodnoty `field` pro `team` jako 'H' nebo 'A' pred datem cutoff.
    Nektere starsi sezony/souteze (napr. nizsi anglicke ligy pred rokem 2022)
    nemaji vsechny sloupce (chybi HC/AC/HS/AS) - takove radky preskocime."""
    vals = []
    for r in rows:
        if r["_d"] >= cutoff:
            continue
        val = None
        if venue == "H" and r["HomeTeam"] == team:
            val = r.get(field)
        elif venue == "A" and r["AwayTeam"] == team:
            val = r.get(field)
        if val not in (None, ""):
            try:
                vals.append(float(val))
            except ValueError:
                pass
    return sum(vals) / len(vals) if vals else None


def predict_football_match(all_rows, match):
    cutoff = match["_d"]
    home, away = match["HomeTeam"], match["AwayTeam"]
    past = [r for r in all_rows if r["_d"] < cutoff]

    def safe(v, d):
        return v if v is not None else d

    # vyhra/remiza/prohra - zjednodusena verze stejne logiky jako aggregate_stats.py
    def team_matches(team):
        return [r for r in past if r["HomeTeam"] == team or r["AwayTeam"] == team]

    def result_for(team, r):
        if r["HomeTeam"] == team:
            gf, ga = float(r["FTHG"]), float(r["FTAG"])
        else:
            gf, ga = float(r["FTAG"]), float(r["FTHG"])
        return "W" if gf > ga else ("D" if gf == ga else "L")

    m_home = sorted(team_matches(home), key=lambda r: r["_d"])
    m_away = sorted(team_matches(away), key=lambda r: r["_d"])
    recent_home = m_home[-10:]
    recent_away = m_away[-10:]
    form_home = sum(1 for r in recent_home if result_for(home, r) == "W") / len(recent_home) if recent_home else 0.4
    form_away = sum(1 for r in recent_away if result_for(away, r) == "W") / len(recent_away) if recent_away else 0.4
    hwr = safe(team_rate(past, home, "H", "FTHG", cutoff) is not None and
               (sum(1 for r in m_home if r["HomeTeam"] == home and result_for(home, r) == "W") /
                max(1, sum(1 for r in m_home if r["HomeTeam"] == home))), 0.4)
    awr = safe((sum(1 for r in m_away if r["AwayTeam"] == away and result_for(away, r) == "W") /
                max(1, sum(1 for r in m_away if r["AwayTeam"] == away))), 0.3)
    h2h = [r for r in past if {r["HomeTeam"], r["AwayTeam"]} == {home, away}]
    h2h_home_wr = (sum(1 for r in h2h if result_for(home, r) == "W") / len(h2h)) if h2h else form_home
    h2h_away_wr = (sum(1 for r in h2h if result_for(away, r) == "W") / len(h2h)) if h2h else form_away

    score_home = 0.4 * form_home + 0.3 * hwr + 0.3 * h2h_home_wr
    score_away = 0.4 * form_away + 0.3 * awr + 0.3 * h2h_away_wr
    league_past = [r for r in past if r["_league_file"] == match["_league_file"]]
    draw_rate = (sum(1 for r in league_past if r["FTR"] == "D") / len(league_past)) if league_past else 0.25
    total = score_home + score_away + draw_rate
    p_home, p_draw, p_away = score_home / total, draw_rate / total, score_away / total
    pred_outcome = max((("H", p_home), ("D", p_draw), ("A", p_away)), key=lambda x: x[1])[0]

    # presne skore (Poisson)
    h_attack = team_rate(past, home, "H", "FTHG", cutoff)
    h_defense = team_rate(past, home, "H", "FTAG", cutoff)
    a_attack = team_rate(past, away, "A", "FTAG", cutoff)
    a_defense = team_rate(past, away, "A", "FTHG", cutoff)
    lam_home = (safe(h_attack, 1.3) + safe(a_defense, 1.3)) / 2
    lam_away = (safe(a_attack, 1.1) + safe(h_defense, 1.1)) / 2
    pred_score = best_score(lam_home, lam_away)

    # rohy
    h_corners = safe(team_rate(past, home, "H", "HC", cutoff), 5.0)
    a_corners = safe(team_rate(past, away, "A", "AC", cutoff), 5.0)
    corner_pick = "home" if h_corners - a_corners > 0.5 else ("away" if a_corners - h_corners > 0.5 else "vyrovnano")

    # karty (zlute+cervene)
    def cards_rate(team, venue, yc, rc):
        vals = []
        for r in past:
            if venue == "H" and r["HomeTeam"] == team:
                vals.append(float(r.get(yc, 0) or 0) + float(r.get(rc, 0) or 0))
            elif venue == "A" and r["AwayTeam"] == team:
                vals.append(float(r.get(yc, 0) or 0) + float(r.get(rc, 0) or 0))
        return sum(vals) / len(vals) if vals else 2.0

    h_cards = cards_rate(home, "H", "HY", "HR")
    a_cards = cards_rate(away, "A", "AY", "AR")
    card_pick = "home" if h_cards - a_cards > 0.3 else ("away" if a_cards - h_cards > 0.3 else "vyrovnano")

    return {
        "outcome": pred_outcome, "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
        "score": pred_score, "corner_pick": corner_pick, "card_pick": card_pick,
    }


def actual_football(match):
    ftr = match["FTR"]
    hc, ac = float(match["HC"]), float(match["AC"])
    hy, ay = float(match.get("HY", 0) or 0), float(match.get("AY", 0) or 0)
    hr, ar = float(match.get("HR", 0) or 0), float(match.get("AR", 0) or 0)
    corner_actual = "home" if hc > ac else ("away" if ac > hc else "vyrovnano")
    card_actual = "home" if (hy + hr) > (ay + ar) else ("away" if (ay + ar) > (hy + hr) else "vyrovnano")
    return {
        "outcome": ftr, "score": (int(float(match["FTHG"])), int(float(match["FTAG"]))),
        "corner_pick": corner_actual, "card_pick": card_actual,
    }


def run_football_backtest(n):
    rows = load_football_all()
    testset = pick_football_testset(rows, n)
    results = []
    for m in testset:
        pred = predict_football_match(rows, m)
        act = actual_football(m)
        results.append({
            "date": m["Date"], "home": m["HomeTeam"], "away": m["AwayTeam"],
            "pred": pred, "actual": act,
        })
    return results


# ---------------------------------------------------------------------------
# HOKEJ
# ---------------------------------------------------------------------------
def load_hockey_all():
    rows = []
    for path in sorted(glob.glob(os.path.join(BASE, "hokej", "NHL_*.csv"))):
        with open(path, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                if not row.get("date"):
                    continue
                row["_d"] = row["date"]  # ISO string, lze porovnavat primo
                rows.append(row)
    return rows


def pick_hockey_testset(rows, n, seed=42):
    complete = [r for r in rows if all(r.get(c) not in (None, "") for c in
                ("home_score", "away_score", "home_sog", "away_sog", "home_pim", "away_pim"))
                and r["_d"] >= "2022-08-01"]
    rng = random.Random(seed)
    sample = rng.sample(complete, min(n, len(complete)))
    sample.sort(key=lambda r: r["_d"])
    return sample


def nhl_team_rate(rows, team, venue, field, cutoff):
    vals = []
    for r in rows:
        if r["_d"] >= cutoff:
            continue
        if venue == "home" and r["home_team"] == team:
            try:
                vals.append(float(r[field]))
            except (ValueError, TypeError):
                pass
        elif venue == "away" and r["away_team"] == team:
            try:
                vals.append(float(r[field]))
            except (ValueError, TypeError):
                pass
    return sum(vals) / len(vals) if vals else None


def predict_hockey_match(all_rows, match):
    cutoff = match["_d"]
    home, away = match["home_team"], match["away_team"]
    past = [r for r in all_rows if r["_d"] < cutoff]

    def safe(v, d):
        return v if v is not None else d

    def team_matches(team):
        return [r for r in past if r["home_team"] == team or r["away_team"] == team]

    def win_for(team, r):
        is_home = r["home_team"] == team
        gf = float(r["home_score"] if is_home else r["away_score"])
        ga = float(r["away_score"] if is_home else r["home_score"])
        return gf > ga

    m_home = team_matches(home)
    m_away = team_matches(away)
    recent_home = sorted(m_home, key=lambda r: r["_d"])[-15:]
    recent_away = sorted(m_away, key=lambda r: r["_d"])[-15:]
    form_home = sum(1 for r in recent_home if win_for(home, r)) / len(recent_home) if recent_home else 0.5
    form_away = sum(1 for r in recent_away if win_for(away, r)) / len(recent_away) if recent_away else 0.5
    home_only = [r for r in m_home if r["home_team"] == home]
    away_only = [r for r in m_away if r["away_team"] == away]
    hwr = (sum(1 for r in home_only if win_for(home, r)) / len(home_only)) if home_only else form_home
    awr = (sum(1 for r in away_only if win_for(away, r)) / len(away_only)) if away_only else form_away
    h2h = [r for r in past if {r["home_team"], r["away_team"]} == {home, away}]
    h2h_home_wr = (sum(1 for r in h2h if win_for(home, r)) / len(h2h)) if h2h else form_home
    h2h_away_wr = (sum(1 for r in h2h if win_for(away, r)) / len(h2h)) if h2h else form_away

    score_home = 0.45 * form_home + 0.25 * hwr + 0.30 * h2h_home_wr
    score_away = 0.45 * form_away + 0.25 * awr + 0.30 * h2h_away_wr
    total = score_home + score_away
    p_home = score_home / total if total else 0.5
    pred_outcome = "home" if p_home >= 0.5 else "away"

    h_attack = nhl_team_rate(past, home, "home", "home_score", cutoff)
    h_defense = nhl_team_rate(past, home, "home", "away_score", cutoff)
    a_attack = nhl_team_rate(past, away, "away", "away_score", cutoff)
    a_defense = nhl_team_rate(past, away, "away", "home_score", cutoff)
    lam_home = (safe(h_attack, 3.0) + safe(a_defense, 3.0)) / 2
    lam_away = (safe(a_attack, 2.8) + safe(h_defense, 2.8)) / 2
    pred_score = best_score(lam_home, lam_away, max_goals=8)

    h_sog = safe(nhl_team_rate(past, home, "home", "home_sog", cutoff), 30.0)
    a_sog = safe(nhl_team_rate(past, away, "away", "away_sog", cutoff), 30.0)
    sog_pick = "home" if h_sog - a_sog > 1 else ("away" if a_sog - h_sog > 1 else "vyrovnano")

    h_pim = safe(nhl_team_rate(past, home, "home", "home_pim", cutoff), 8.0)
    a_pim = safe(nhl_team_rate(past, away, "away", "away_pim", cutoff), 8.0)
    pim_pick = "home" if h_pim - a_pim > 1 else ("away" if a_pim - h_pim > 1 else "vyrovnano")

    return {
        "outcome": pred_outcome, "p_home": p_home, "score": pred_score,
        "sog_pick": sog_pick, "pim_pick": pim_pick,
    }


def actual_hockey(match):
    hs, as_ = float(match["home_score"]), float(match["away_score"])
    outcome = "home" if hs > as_ else "away"
    h_sog, a_sog = float(match["home_sog"]), float(match["away_sog"])
    h_pim, a_pim = float(match["home_pim"]), float(match["away_pim"])
    sog_actual = "home" if h_sog > a_sog else ("away" if a_sog > h_sog else "vyrovnano")
    pim_actual = "home" if h_pim > a_pim else ("away" if a_pim > h_pim else "vyrovnano")
    return {"outcome": outcome, "score": (int(hs), int(as_)), "sog_pick": sog_actual, "pim_pick": pim_actual}


def run_hockey_backtest(n):
    rows = load_hockey_all()
    testset = pick_hockey_testset(rows, n)
    results = []
    for m in testset:
        pred = predict_hockey_match(rows, m)
        act = actual_hockey(m)
        results.append({
            "date": m["date"], "home": m["home_team"], "away": m["away_team"],
            "pred": pred, "actual": act,
        })
    return results


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------
def summarize(results, sport):
    n = len(results)
    outcome_hits = sum(1 for r in results if r["pred"]["outcome"] == r["actual"]["outcome"])
    score_hits = sum(1 for r in results if r["pred"]["score"] == r["actual"]["score"])

    print(f"\n=== {sport.upper()}: {n} otestovanych zapasu ===\n")
    header = f"{'datum':<11}{'domaci':<22}{'hoste':<22}{'predikce':<10}{'skutecnost':<12}{'presne skore P/S'}"
    print(header)
    print("-" * len(header))
    for r in results:
        p, a = r["pred"], r["actual"]
        score_mark = "OK" if p["score"] == a["score"] else "-"
        print(f"{r['date']:<11}{r['home'][:20]:<22}{r['away'][:20]:<22}{p['outcome']:<10}{a['outcome']:<12}"
              f"{p['score'][0]}:{p['score'][1]} / {a['score'][0]}:{a['score'][1]}  [{score_mark}]")

    print(f"\nPresnost vysledku (vyhra/remiza/prohra): {outcome_hits}/{n} = {outcome_hits/n:.0%}")
    print(f"Presnost presneho skore:                 {score_hits}/{n} = {score_hits/n:.0%}")

    if sport == "fotbal":
        corner_hits = sum(1 for r in results if r["pred"]["corner_pick"] == r["actual"]["corner_pick"])
        card_hits = sum(1 for r in results if r["pred"]["card_pick"] == r["actual"]["card_pick"])
        print(f"Presnost 'kdo mel vic rohu':              {corner_hits}/{n} = {corner_hits/n:.0%}")
        print(f"Presnost 'kdo mel vic karet':             {card_hits}/{n} = {card_hits/n:.0%}")
    else:
        sog_hits = sum(1 for r in results if r["pred"]["sog_pick"] == r["actual"]["sog_pick"])
        pim_hits = sum(1 for r in results if r["pred"]["pim_pick"] == r["actual"]["pim_pick"])
        print(f"Presnost 'kdo mel vic strel na branku':   {sog_hits}/{n} = {sog_hits/n:.0%}")
        print(f"Presnost 'kdo mel vic trestnych minut':   {pim_hits}/{n} = {pim_hits/n:.0%}")

    # nahodny baseline pro srovnani
    if sport == "fotbal":
        print("\n(Pro srovnani: nahodne hadani vysledku H/D/A ~33%, presne skore ~ 5-10%, "
              "vic rohu/karet (2 varianty + remiza) ~40-45%.)")
    else:
        print("\n(Pro srovnani: nahodne hadani vysledku (2 varianty) ~50%, presne skore ~ 5-8%, "
              "vic strel/trestnych minut (2 varianty + remiza) ~45%.)")


# ---------------------------------------------------------------------------
# TENIS
# ---------------------------------------------------------------------------
BAD_SCORE_MARKERS = ("RET", "W/O", "DEF", "ABN")


def load_tennis_all():
    rows = []
    for path in sorted(glob.glob(os.path.join(BASE, "tenis", "*_matches_*.csv"))):
        with open(path, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                if not row.get("winner_name") or not row.get("tourney_date"):
                    continue
                row["_d"] = row["tourney_date"]  # YYYYMMDD string, lze porovnavat primo
                rows.append(row)
    return rows


def sets_count(score, winner_sets=True):
    """Spocita sety vyhrane vitezem/porazenym ze zapisu typu '7-6(5) 6-4'."""
    if any(m in score for m in BAD_SCORE_MARKERS):
        return None
    parts = score.split()
    w, l = 0, 0
    for p in parts:
        p = p.split("(")[0]
        if "-" not in p:
            return None
        try:
            a, b = (int(x) for x in p.split("-"))
        except ValueError:
            return None
        if a > b:
            w += 1
        else:
            l += 1
    return (w, l) if winner_sets else (l, w)


def pick_tennis_testset(rows, n, seed=42):
    complete = []
    for r in rows:
        if r["_d"] < "20220101":
            continue
        sc = sets_count(r.get("score", ""))
        if sc is None:
            continue
        if not r.get("w_ace") or not r.get("l_ace"):
            continue
        r["_sets"] = sc
        complete.append(r)
    rng = random.Random(seed)
    sample = rng.sample(complete, min(n, len(complete)))
    sample.sort(key=lambda r: (r["_d"], r.get("match_num", "0")))
    return sample


def player_rate(rows, player, field, cutoff, as_winner_field, as_loser_field):
    vals = []
    for r in rows:
        if r["_d"] >= cutoff:
            continue
        if r["winner_name"] == player and r.get(as_winner_field) not in (None, ""):
            try:
                vals.append(float(r[as_winner_field]))
            except ValueError:
                pass
        elif r["loser_name"] == player and r.get(as_loser_field) not in (None, ""):
            try:
                vals.append(float(r[as_loser_field]))
            except ValueError:
                pass
    return sum(vals) / len(vals) if vals else None


def predict_tennis_match(all_rows, match, p1, p2):
    cutoff = match["_d"]
    past = [r for r in all_rows if r["_d"] < cutoff]

    def matches_of(player):
        return [r for r in past if r["winner_name"] == player or r["loser_name"] == player]

    m1 = sorted(matches_of(p1), key=lambda r: (r["_d"], r.get("match_num", "0")))
    m2 = sorted(matches_of(p2), key=lambda r: (r["_d"], r.get("match_num", "0")))
    recent1, recent2 = m1[-15:], m2[-15:]
    form1 = sum(1 for r in recent1 if r["winner_name"] == p1) / len(recent1) if recent1 else 0.5
    form2 = sum(1 for r in recent2 if r["winner_name"] == p2) / len(recent2) if recent2 else 0.5
    overall1 = sum(1 for r in m1 if r["winner_name"] == p1) / len(m1) if m1 else 0.5
    overall2 = sum(1 for r in m2 if r["winner_name"] == p2) / len(m2) if m2 else 0.5
    h2h = [r for r in past if {r["winner_name"], r["loser_name"]} == {p1, p2}]
    h2h1 = (sum(1 for r in h2h if r["winner_name"] == p1) / len(h2h)) if h2h else overall1
    h2h2 = (sum(1 for r in h2h if r["winner_name"] == p2) / len(h2h)) if h2h else overall2

    score1 = 0.5 * form1 + 0.3 * h2h1 + 0.2 * overall1
    score2 = 0.5 * form2 + 0.3 * h2h2 + 0.2 * overall2
    total = score1 + score2
    p_win1 = score1 / total if total else 0.5
    pred_winner = p1 if p_win1 >= 0.5 else p2

    ace1 = player_rate(past, p1, "ace", cutoff, "w_ace", "l_ace")
    ace2 = player_rate(past, p2, "ace", cutoff, "w_ace", "l_ace")
    ace_pick = "p1" if (ace1 or 0) - (ace2 or 0) > 0.5 else ("p2" if (ace2 or 0) - (ace1 or 0) > 0.5 else "vyrovnano")

    df1 = player_rate(past, p1, "df", cutoff, "w_df", "l_df")
    df2 = player_rate(past, p2, "df", cutoff, "w_df", "l_df")
    df_pick = "p1" if (df1 or 0) - (df2 or 0) > 0.5 else ("p2" if (df2 or 0) - (df1 or 0) > 0.5 else "vyrovnano")

    # nejcastejsi pomer setu pro dany pocet setu (best_of) mezi vsemi historickymi zapasy
    best_of = match.get("best_of", "3")
    same_bo = [r for r in past if r.get("best_of") == best_of and r.get("_sets") is None]
    patterns = {}
    for r in past:
        if r.get("best_of") != best_of:
            continue
        sc = sets_count(r.get("score", ""))
        if sc is None:
            continue
        patterns[sc] = patterns.get(sc, 0) + 1
    pred_margin = max(patterns, key=patterns.get) if patterns else ((2, 0) if best_of == "3" else (3, 1))

    return {
        "pred_winner": pred_winner, "p_win1": p_win1, "ace_pick": ace_pick,
        "df_pick": df_pick, "pred_margin": pred_margin,
    }


def run_tennis_backtest(n):
    rows = load_tennis_all()
    testset = pick_tennis_testset(rows, n)
    results = []
    for m in testset:
        p1, p2 = m["winner_name"], m["loser_name"]
        pred = predict_tennis_match(rows, m, p1, p2)
        actual_winner = m["winner_name"]
        actual = {
            "winner": actual_winner, "margin": m["_sets"],
            "ace_pick": "p1" if float(m["w_ace"]) > float(m["l_ace"]) else ("p2" if float(m["l_ace"]) > float(m["w_ace"]) else "vyrovnano"),
            "df_pick": "p1" if float(m["w_df"]) > float(m["l_df"]) else ("p2" if float(m["l_df"]) > float(m["w_df"]) else "vyrovnano"),
        }
        results.append({"date": m["_d"], "p1": p1, "p2": p2, "pred": pred, "actual": actual})
    return results


def summarize_tennis(results):
    n = len(results)
    print(f"\n=== TENIS: {n} otestovanych zapasu ===\n")
    header = f"{'turnaj':<11}{'hrac 1':<22}{'hrac 2':<22}{'tip vitez':<22}{'skutecny vitez':<22}{'sety P/S'}"
    print(header)
    print("-" * len(header))
    winner_hits = margin_hits = 0
    for r in results:
        p, a = r["pred"], r["actual"]
        w_ok = p["pred_winner"] == a["winner"]
        m_ok = w_ok and p["pred_margin"] == a["margin"]
        winner_hits += w_ok
        margin_hits += m_ok
        print(f"{r['date']:<11}{r['p1'][:20]:<22}{r['p2'][:20]:<22}{p['pred_winner'][:20]:<22}"
              f"{a['winner'][:20]:<22}{p['pred_margin'][0]}:{p['pred_margin'][1]} / {a['margin'][0]}:{a['margin'][1]}"
              f"  [{'OK' if m_ok else '-'}]")

    ace_hits = sum(1 for r in results if r["pred"]["ace_pick"] == r["actual"]["ace_pick"])
    df_hits = sum(1 for r in results if r["pred"]["df_pick"] == r["actual"]["df_pick"])

    print(f"\nPresnost vitez zapasu:                    {winner_hits}/{n} = {winner_hits/n:.0%}")
    print(f"Presnost presny pomer setu:                {margin_hits}/{n} = {margin_hits/n:.0%}")
    print(f"Presnost 'kdo mel vic es':                 {ace_hits}/{n} = {ace_hits/n:.0%}")
    print(f"Presnost 'kdo mel vic dvojchyb':           {df_hits}/{n} = {df_hits/n:.0%}")
    print("\n(Pro srovnani: nahodne hadani vitez ~50%, presny pomer setu ~35-50% "
          "(malo moznych kombinaci u best-of-3), vic es/dvojchyb (2 varianty + remiza) ~45%.)")


def main():
    sport = sys.argv[1] if len(sys.argv) > 1 else "fotbal"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else (40 if sport == "fotbal" else 30)
    if sport == "fotbal":
        results = run_football_backtest(n)
        summarize(results, "fotbal")
    elif sport == "hokej":
        results = run_hockey_backtest(n)
        summarize(results, "hokej")
    elif sport == "tenis":
        results = run_tennis_backtest(n)
        summarize_tennis(results)
    else:
        print("Pouziti: backtest.py [fotbal|hokej|tenis] [pocet_zapasu]")


if __name__ == "__main__":
    main()
