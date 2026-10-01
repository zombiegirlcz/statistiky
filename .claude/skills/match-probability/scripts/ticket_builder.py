#!/usr/bin/env python3
"""
Tiket builder - z modelu (stejna h2h-blended Poissonova logika jako
backtest.py/aggregate_stats.py) postavi fotbalove sazkove tikety (SOLO i AKO
kombinace), VCETNE sazek na "prohravajici" stranu (hendikep na outsidera,
pod gólu, remiza) tam, kde je v tom hodnota (edge) proti skutecnym
historickym kurzum, ktere uz mame v datech (sloupce Avg* ve fotbal/*.csv -
prumer nekolika sazkovych kancelari, NE primo Fortuna; presne historicke
kurzy Fortuny k dispozici nemame, tohle je nejlepsi dostupna aproximace
trzni ceny v dobe zapasu).

Pravidla sazeni u Fortuny pouzita v tomhle skriptu (zdroj: ifortuna.cz
herni plan + napoveda.ifortuna.cz, viz README zminka):
  - SOLO = 1 sazkova prilezitost na tiketu.
  - AKO = 2+ prilezitosti na tiketu, ktere se NAVZAJEM NEPODPORUJI (nejde
    kombinovat napr. 1X2 + presny vysledek STEJNEHO zapasu) - vysledny kurz
    je SOUCIN vsech dilcich kurzu. Tenhle builder kombinuje vzdy jen RUZNE
    zapasy (max 1 noha na zapas), coz je vzdy v poradku.
  - Minimalni vklad na tiket je radove 10 Kc - stejne se tu pouziva jako
    spodni hranice.

DULEZITE OMEZENI (rict uzivateli na rovinu, kdyz se zepta): zadna sazkova
strategie nemuze garantovat, ze banka na konci dne neklesne pod pocatecni
castku - kazda sazka ma nenulovou sanci prohry, to je matematicka vlastnost
sazeni samotneho, ne nedostatek tohohle skriptu. Co skript realne delá:
 1) sazi jen na vybery s pocitanou hodnotou (model rika vyssi pravdepodobnost
    nez kolik rika z kurzu odvigovany trh),
 2) riskuje jen CAST denniho rozpoctu (`--risk-fraction`, default 35 %),
    zbytek zustava nevsazeny jako rezerva,
 3) `backtest` rezim pak na mnoha nezavislych dnech z historie zmeri, jak
    casto i tak dojde k poklesu pod pocatecni castku - to je poctivy cisly
    vysledek, ne slib.

Pouziti:
    python3 ticket_builder.py den 2024-03-16          # tikety na konkretni den z historie
    python3 ticket_builder.py backtest [N]            # N nahodnych dnu (default 40), zmeri uspesnost
"""
import os
import random
import sys
from collections import defaultdict
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
import backtest as bt  # noqa: E402

EDGE_MIN = 0.04          # minimalni edge (model_p - odvigovana trzni p) na zarazeni do vyberu
EDGE_MAX = 0.25          # edge nad tohle uz neni "nalezena hodnota", ale skoro jiste chyba/sum modelu - zahodit
RISK_FRACTION = 0.35     # kolik z denniho rozpoctu se smi celkem vsadit
MIN_STAKE = 10.0         # Fortuna - minimalni vklad na tiket
MIN_TEAM_MATCHES = 15    # min. pocet drivejsich zapasu KAZDEHO tymu v datech, jinak je odhad moc nespolehlivy
ODDS_RANGE = (1.25, 6.0)  # mimo tenhle rozsah kurzu uz neni edge vuci trhu duveryhodny (extremni kurzy = malo dat)


def load_clean():
    """bt.load_football_all() obcas obsahuje radky bez FTHG/FTAG (napr.
    odlozene/nedohrane zapasy v nekterych nizsich soutezich) - predict_football_match
    na nich pada, protoze pocita vysledek kazdeho drivejsiho zapasu v historii
    tymu. Tady se to filtruje jednou na zacatku, aby backtest pres desitky
    dnu nespadl uprostred na nejakem vzdalenem okraji dat."""
    return [r for r in bt.load_football_all() if r.get("FTHG") not in (None, "") and r.get("FTAG") not in (None, "")]


# ---------------------------------------------------------------------------
# Model: pravdepodobnosti pro trhy, pro ktere mame v datech skutecne kurzy
# ---------------------------------------------------------------------------
def goal_lambdas(all_rows, match):
    """Stejny vypocet lam_home/lam_away (tymovy prumer + h2h blend 65/35)
    jako uvnitr backtest.predict_football_match - tam se ale vraci jen
    nejpravdepodobnejsi presne skore, ne surove lambdy, a ty tu potrebujeme
    pro rozdeleni na vic trhu (pres/pod góly, hendikep)."""
    cutoff = match["_d"]
    home, away = match["HomeTeam"], match["AwayTeam"]
    past = [r for r in all_rows if r["_d"] < cutoff]
    h2h = [r for r in past if {r["HomeTeam"], r["AwayTeam"]} == {home, away}]

    def safe(v, d):
        return v if v is not None else d

    def h2h_rate(team, opponent, team_home_field, team_away_field):
        vals = []
        for r in h2h:
            if r["HomeTeam"] == team and r["AwayTeam"] == opponent:
                v = r.get(team_home_field)
            elif r["AwayTeam"] == team and r["HomeTeam"] == opponent:
                v = r.get(team_away_field)
            else:
                continue
            if v not in (None, ""):
                try:
                    vals.append(float(v))
                except ValueError:
                    pass
        return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

    h_attack = bt.team_rate(past, home, "H", "FTHG", cutoff)
    h_defense = bt.team_rate(past, home, "H", "FTAG", cutoff)
    a_attack = bt.team_rate(past, away, "A", "FTAG", cutoff)
    a_defense = bt.team_rate(past, away, "A", "FTHG", cutoff)
    lam_home = (safe(h_attack, 1.3) + safe(a_defense, 1.3)) / 2
    lam_away = (safe(a_attack, 1.1) + safe(h_defense, 1.1)) / 2
    h2h_h_goals, h2h_goals_n = h2h_rate(home, away, "FTHG", "FTAG")
    h2h_a_goals, _ = h2h_rate(away, home, "FTAG", "FTHG")
    if h2h_goals_n >= 3:
        lam_home = 0.65 * lam_home + 0.35 * h2h_h_goals
        lam_away = 0.65 * lam_away + 0.35 * h2h_a_goals
    return lam_home, lam_away


def total_goals_probs(lam_home, lam_away, line=2.5):
    lam_total = lam_home + lam_away
    thresh = int(line)  # 2.5 -> scita se 0..2 jako "pod"
    p_under = sum(bt.poisson(k, lam_total) for k in range(0, thresh + 1))
    return 1 - p_under, p_under  # (over, under)


def _ah_single_line_probs(lam_home, lam_away, line, max_goals=10):
    p_win = p_push = p_lose = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = bt.poisson(i, lam_home) * bt.poisson(j, lam_away)
            adj = (i - j) + line
            if adj > 0:
                p_win += p
            elif adj == 0:
                p_push += p
            else:
                p_lose += p
    return p_win, p_push, p_lose


def handicap_probs(lam_home, lam_away, line):
    """Vraci (pravdepodobnost ze DOMACI pokryje hendikep, push, AWAY pokryje).
    Ctvrtinove linie (napr. -1.75) se realne delí na dve sousedni pulky
    (-1.5 a -2.0) se stejnou vahou - presne jak to dela i samotna sazkovka."""
    if round(line * 4) % 2 != 0:
        lines = [line - 0.25, line + 0.25]
    else:
        lines = [line]
    wins = pushes = loses = 0.0
    for ln in lines:
        w, p, l = _ah_single_line_probs(lam_home, lam_away, ln)
        wins += w / len(lines)
        pushes += p / len(lines)
        loses += l / len(lines)
    return wins, pushes, loses


def edge_ok(edge):
    """Edge musi byt dost velky, aby stal za sazku, ale ne tak obrovsky, aby
    byl zjevne artefakt sumu modelu misto skutecne hodnoty (viz EDGE_MAX)."""
    return EDGE_MIN <= edge <= EDGE_MAX


def candidate_legs(all_rows, match):
    """Vsechny sazkove prilezitosti tohohle zapasu, kde ma model edge >=
    EDGE_MIN proti odvigovanemu trhu. Projizdi VSECHNY vysledky kazdeho
    trhu (vyhra/remiza/prohra, pres/pod, hendikep na obe strany) - takze
    sem spadne stejne snadno sazka na favorita jako na outsidera/hendikep,
    podle toho, kde skutecne vychazi hodnota."""
    legs = []
    home, away = match["HomeTeam"], match["AwayTeam"]

    # Pojistka proti nespolehlivym odhadum: nove postoupene/malo zahrane tymy
    # (napr. Almere City v prvni sezone v Eredivisie) maji tak malo zapasu v
    # datech, ze prumery jsou siroky sum, ktery pak vyjde jako "obrovska
    # hodnota" proti trhu - ve skutecnosti je to chyba modelu, ne skutecna
    # mispricing. Bez tyhle kontroly skript sazel na St Johnstone/Vizela s
    # "EV +180 %", coz je naprosto nerealisticke.
    cutoff = match["_d"]
    past_all = [r for r in all_rows if r["_d"] < cutoff]
    home_n = sum(1 for r in past_all if r["HomeTeam"] == home or r["AwayTeam"] == home)
    away_n = sum(1 for r in past_all if r["HomeTeam"] == away or r["AwayTeam"] == away)
    if home_n < MIN_TEAM_MATCHES or away_n < MIN_TEAM_MATCHES:
        return []

    pred = bt.predict_football_match(all_rows, match)
    p_home, p_draw, p_away = pred["p_home"], pred["p_draw"], pred["p_away"]

    def addleg(market, selection, label, model_p, odds):
        if odds is None or model_p is None:
            return
        if not (ODDS_RANGE[0] <= odds <= ODDS_RANGE[1]):
            return
        legs.append({
            "match": f"{home} - {away}", "market": market, "selection": selection,
            "label": label, "model_p": model_p, "odds": odds,
            "ev": model_p * odds - 1,
        })

    # --- 1X2 ---
    try:
        oH, oD, oA = float(match["AvgH"]), float(match["AvgD"]), float(match["AvgA"])
        overround = 1 / oH + 1 / oD + 1 / oA
        fair = {"H": (1 / oH) / overround, "D": (1 / oD) / overround, "A": (1 / oA) / overround}
        for sel, model_p, odds, label in (
            ("H", p_home, oH, f"{home} vyhraje"),
            ("D", p_draw, oD, "Remíza"),
            ("A", p_away, oA, f"{away} vyhraje"),
        ):
            if edge_ok(model_p - fair[sel]):
                addleg("1X2", sel, label, model_p, odds)
    except (KeyError, ValueError, ZeroDivisionError):
        pass

    # --- Pres/pod 2.5 golu ---
    lam_home, lam_away = goal_lambdas(all_rows, match)
    try:
        oOv, oUn = float(match["Avg>2.5"]), float(match["Avg<2.5"])
        p_over, p_under = total_goals_probs(lam_home, lam_away, 2.5)
        overround = 1 / oOv + 1 / oUn
        fair_over, fair_under = (1 / oOv) / overround, (1 / oUn) / overround
        if edge_ok(p_over - fair_over):
            addleg("OU2.5", "OVER", f"{home} - {away}: přes 2.5 gólu", p_over, oOv)
        if edge_ok(p_under - fair_under):
            addleg("OU2.5", "UNDER", f"{home} - {away}: pod 2.5 gólu", p_under, oUn)
    except (KeyError, ValueError, ZeroDivisionError):
        pass

    # --- Asijsky hendikep ---
    try:
        ah_line = float(match["AHh"])
        oAHH, oAHA = float(match["AvgAHH"]), float(match["AvgAHA"])
        p_home_cov, _p_push, p_away_cov = handicap_probs(lam_home, lam_away, ah_line)
        overround = 1 / oAHH + 1 / oAHA
        fair_h, fair_a = (1 / oAHH) / overround, (1 / oAHA) / overround
        if edge_ok(p_home_cov - fair_h):
            addleg("AH", "HOME", f"{home} hendikep {ah_line:+.2f}", p_home_cov, oAHH)
        if edge_ok(p_away_cov - fair_a):
            addleg("AH", "AWAY", f"{away} hendikep {-ah_line:+.2f}", p_away_cov, oAHA)
    except (KeyError, ValueError, ZeroDivisionError):
        pass

    return legs


# ---------------------------------------------------------------------------
# Stavba tiketu z rozpoctu na den
# ---------------------------------------------------------------------------
def build_tickets(day_legs, budget=1000.0, risk_fraction=RISK_FRACTION, max_legs_combo=3):
    """Rozdeleni rozpoctu mezi SOLO a AKO NENI 50:50 - backtest (viz metodika.md)
    ukazal, ze AKO kombinace tri noh systematicky prohravaji (kazda jednotliva
    noha ma sice edge, ale jejich nejistoty se v kombinaci NASOBI, takze skutecna
    sanze na trefeni cele kombinace je mnohem nizsi, nez kolik by naznacoval
    soucet jednotlivych edge). SOLO tikety v testu vychazely temer na nulu
    (ROI blizko 0 %), AKO prohraly prakticky kazdou sazku - proto dostava AKO
    jen mensi cast rizikoveho rozpoctu (je to spis "los do loterie", ne hlavni
    strategie)."""
    if not day_legs:
        return []
    day_legs = sorted(day_legs, key=lambda l: l["ev"], reverse=True)
    risk_budget = budget * risk_fraction

    solo_candidates = [l for l in day_legs if l["model_p"] >= 0.55][:1]

    used_matches = set()
    combo_legs = []
    for l in day_legs:
        if l["match"] in used_matches:
            continue
        combo_legs.append(l)
        used_matches.add(l["match"])
        if len(combo_legs) == max_legs_combo:
            break
    has_combo = len(combo_legs) >= 2

    tickets = []
    if not solo_candidates and not has_combo:
        return []
    if solo_candidates and has_combo:
        solo_stake = risk_budget * 0.7
        ako_stake = risk_budget * 0.3
    elif solo_candidates:
        solo_stake = risk_budget
        ako_stake = 0
    else:
        solo_stake = 0
        ako_stake = risk_budget
    solo_stake = max(MIN_STAKE, round(solo_stake / 5) * 5) if solo_candidates else 0
    ako_stake = max(MIN_STAKE, round(ako_stake / 5) * 5) if has_combo else 0

    if solo_candidates:
        leg = solo_candidates[0]
        tickets.append({"typ": "SÓLO", "legy": [leg], "kurz": round(leg["odds"], 2), "vklad": solo_stake})
    if has_combo:
        kurz = 1.0
        for l in combo_legs:
            kurz *= l["odds"]
        tickets.append({"typ": "AKO", "legy": combo_legs, "kurz": round(kurz, 2), "vklad": ako_stake})

    total_staked = sum(t["vklad"] for t in tickets)
    if total_staked > budget:
        scale = budget / total_staked
        for t in tickets:
            t["vklad"] = round(t["vklad"] * scale, 2)

    return tickets


# ---------------------------------------------------------------------------
# Vyhodnoceni proti skutecnym vysledkum
# ---------------------------------------------------------------------------
def evaluate_leg(leg, match):
    fthg, ftag = float(match["FTHG"]), float(match["FTAG"])
    if leg["market"] == "1X2":
        actual = "H" if fthg > ftag else ("A" if ftag > fthg else "D")
        return actual == leg["selection"]
    if leg["market"] == "OU2.5":
        total = fthg + ftag
        return total > 2.5 if leg["selection"] == "OVER" else total < 2.5
    if leg["market"] == "AH":
        ah_line = float(match["AHh"])
        margin = fthg - ftag
        adj = (margin + ah_line) if leg["selection"] == "HOME" else (-margin - ah_line)
        if adj > 0:
            return True
        if adj == 0:
            return "PUSH"
        return False
    return False


def evaluate_ticket(ticket, actual_by_match):
    effective_odds = 1.0
    all_push = True
    for leg in ticket["legy"]:
        match = actual_by_match[leg["match"]]
        result = evaluate_leg(leg, match)
        if result == "PUSH":
            continue
        all_push = False
        if result is False:
            return 0.0, "PROHRA"
        effective_odds *= leg["odds"]
    if all_push:
        return ticket["vklad"], "VRÁCENO (push)"
    payout = round(ticket["vklad"] * effective_odds, 2)
    return payout, "VÝHRA"


# ---------------------------------------------------------------------------
# Rezimy
# ---------------------------------------------------------------------------
def print_ticket(t):
    print(f"  [{t['typ']}] kurz {t['kurz']}, vklad {t['vklad']:.0f} Kč, možná výhra {t['vklad'] * t['kurz']:.0f} Kč")
    for l in t["legy"]:
        print(f"      - {l['label']}  (model {l['model_p']:.0%}, kurz {l['odds']}, EV {l['ev']:+.0%})")


def cmd_den(date_str):
    all_rows = load_clean()
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    matches = [r for r in all_rows if r["_d"].date() == target
               and all(r.get(c) not in (None, "") for c in
                       ("FTHG", "FTAG", "AvgH", "AvgD", "AvgA", "Avg>2.5", "Avg<2.5", "AHh", "AvgAHH", "AvgAHA"))]
    if not matches:
        print(f"Pro {date_str} nejsou v datech zapasy s kompletnimi kurzy "
              f"(bud se v ten den nehralo v nasich 22 ligach, nebo je to datum MIMO uz odehrane "
              f"zapasy - tenhle rezim umi jen historicke dny, kde uz mame kurzy i vysledek).")
        return
    day_legs = []
    for m in matches:
        day_legs.extend(candidate_legs(all_rows, m))
    tickets = build_tickets(day_legs, budget=1000.0)
    print(f"=== {date_str} — {len(matches)} zápasů s kurzy, denní rozpočet 1000 Kč ===")
    if not tickets:
        print("Žádná sázková příležitost nesplnila minimální hodnotu (edge) - dnes se raději nesází.")
        return
    for t in tickets:
        print_ticket(t)
    actual_by_match = {f"{m['HomeTeam']} - {m['AwayTeam']}": m for m in matches}
    print("\n--- vyhodnocení proti skutečným výsledkům ---")
    staked = payout = 0.0
    for t in tickets:
        p, status = evaluate_ticket(t, actual_by_match)
        staked += t["vklad"]
        payout += p
        print(f"  {t['typ']} (vklad {t['vklad']:.0f} Kč): {status}, výplata {p:.0f} Kč")
    end_bank = 1000.0 - staked + payout
    print(f"\nVsazeno celkem {staked:.0f} Kč, výplata {payout:.0f} Kč, konečná banka {end_bank:.0f} Kč "
          f"({'POD 1000' if end_bank < 1000 else 'na/nad 1000'})")


def cmd_backtest(n=40, seed=7):
    all_rows = load_clean()
    complete = [r for r in all_rows if r["_d"] >= datetime(2022, 7, 1)
                and all(r.get(c) not in (None, "") for c in
                        ("FTHG", "FTAG", "AvgH", "AvgD", "AvgA", "Avg>2.5", "Avg<2.5", "AHh", "AvgAHH", "AvgAHA"))]
    by_day = defaultdict(list)
    for r in complete:
        by_day[r["_d"].date()].append(r)
    candidate_days = [d for d, ms in by_day.items() if len(ms) >= 3]
    rng = random.Random(seed)
    days = sorted(rng.sample(candidate_days, min(n, len(candidate_days))))

    results = []
    for d in days:
        matches = by_day[d]
        day_legs = []
        for m in matches:
            day_legs.extend(candidate_legs(all_rows, m))
        tickets = build_tickets(day_legs, budget=1000.0)
        actual_by_match = {f"{m['HomeTeam']} - {m['AwayTeam']}": m for m in matches}
        staked = payout = 0.0
        outcomes = []
        for t in tickets:
            p, status = evaluate_ticket(t, actual_by_match)
            staked += t["vklad"]
            payout += p
            outcomes.append((t, p, status))
        end_bank = 1000.0 - staked + payout
        results.append({"day": d, "n_matches": len(matches), "tickets": outcomes,
                         "staked": staked, "payout": payout, "end_bank": end_bank})

    days_with_tickets = [r for r in results if r["tickets"]]
    print(f"=== Backtest tiket builderu: {len(results)} náhodných dnů (seed={seed}), "
          f"z toho {len(days_with_tickets)} mělo aspoň 1 tiket ===\n")

    for r in days_with_tickets[:15]:
        print(f"{r['day']} ({r['n_matches']} zápasů s kurzy):")
        for t, p, status in r["tickets"]:
            print(f"  [{t['typ']}] kurz {t['kurz']}, vklad {t['vklad']:.0f} Kč -> {status}, výplata {p:.0f} Kč")
        print(f"  => konečná banka dne: {r['end_bank']:.0f} Kč\n")
    if len(days_with_tickets) > 15:
        print(f"... a dalších {len(days_with_tickets) - 15} dnů (souhrn níže zahrnuje všechny)\n")

    if not days_with_tickets:
        print("Žádný den nevygeneroval tiket - EDGE_MIN je možná nastaven moc přísně.")
        return

    total_staked = sum(r["staked"] for r in days_with_tickets)
    total_payout = sum(r["payout"] for r in days_with_tickets)

    by_type = defaultdict(lambda: {"staked": 0.0, "payout": 0.0, "win": 0, "lose": 0, "push": 0})
    for r in days_with_tickets:
        for t, p, status in r["tickets"]:
            bt_ = by_type[t["typ"]]
            bt_["staked"] += t["vklad"]
            bt_["payout"] += p
            if status == "VÝHRA":
                bt_["win"] += 1
            elif "push" in status:
                bt_["push"] += 1
            else:
                bt_["lose"] += 1
    print("=== ROZPAD PODLE TYPU TIKETU ===")
    for typ, s in by_type.items():
        n = s["win"] + s["lose"] + s["push"]
        roi_t = (s["payout"] - s["staked"]) / s["staked"] if s["staked"] else 0
        print(f"{typ}: {n} tiketů, výhry {s['win']} ({s['win']/n:.0%}), prohry {s['lose']}, push {s['push']}, "
              f"vsazeno {s['staked']:.0f} Kč, vyplaceno {s['payout']:.0f} Kč, ROI {roi_t:+.1%}")
    print()

    below_1000 = sum(1 for r in days_with_tickets if r["end_bank"] < 1000.0 - 1e-6)
    above_1000 = sum(1 for r in days_with_tickets if r["end_bank"] > 1000.0 + 1e-6)
    flat_1000 = len(days_with_tickets) - below_1000 - above_1000
    avg_end = sum(r["end_bank"] for r in days_with_tickets) / len(days_with_tickets)
    worst = min(r["end_bank"] for r in days_with_tickets)
    best = max(r["end_bank"] for r in days_with_tickets)
    roi = (total_payout - total_staked) / total_staked if total_staked else 0

    print("=== SOUHRN ===")
    print(f"Dní s tiketem: {len(days_with_tickets)} / {len(results)}")
    print(f"Vsazeno celkem: {total_staked:.0f} Kč, vyplaceno celkem: {total_payout:.0f} Kč, ROI: {roi:+.1%}")
    print(f"Průměrná konečná banka dne (start 1000 Kč): {avg_end:.0f} Kč")
    print(f"Nejhorší den: {worst:.0f} Kč, nejlepší den: {best:.0f} Kč")
    print(f"Dní POD 1000 Kč: {below_1000} ({below_1000/len(days_with_tickets):.0%})  |  "
          f"Dní NAD 1000 Kč: {above_1000} ({above_1000/len(days_with_tickets):.0%})  |  "
          f"beze změny: {flat_1000}")
    print(f"\n(Poznámka: riskuje se jen {RISK_FRACTION:.0%} denního rozpočtu najednou (= strop ztráty "
          f"na den je cca {1000*RISK_FRACTION:.0f} Kč, ne celých 1000), přesto se banka POD 1000 Kč "
          f"dostala v {below_1000/len(days_with_tickets):.0%} dní - to je matematicky nevyhnutelné, "
          f"žádná sázka nemůže mít jistou výhru.)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "den" and len(sys.argv) >= 3:
        cmd_den(sys.argv[2])
    elif mode == "backtest":
        n = int(sys.argv[2]) if len(sys.argv) >= 3 else 40
        cmd_backtest(n)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
