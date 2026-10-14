#!/usr/bin/env python3
"""
wta_backtest_agent.py - rizeny test "agent vs 300 historickych WTA zapasu".

CO TOHLE JE A CO NENI
----------------------
Tohle NENI zivy sazkovy nastroj (ten uz existuje: live_tennis_simulator.py +
bet_evaluator.py, s rozpoctem 1000 fiktivnich minci na PRAVE PROBIHAJICI
zapasy). Tenhle skript je samostatny, offline TEST SCENAR: vezme 300 uz
ODEHRANYCH WTA zapasu (2021-2025), u kterych mame SKUTECNE historicke kurzy
(tenis/kurzy/wta_kurzy.csv, viz fetch_tennis_odds.py), a predklada je po
davkach 5 agentovi (= clovek/LLM v roli "pi"), ktery MUSI vsadit na vsech 5
v davce, rozhoduje o velikosti vkladu a o tom, jak rozdelit kapital mezi
jednotlive sazejici "agenty" (fund/defund z hlavni banky). Vysledky zapasu
uz zname - skript je jen SCHOVA, dokud se sazka nezalozi, aby test byl
poctivy (zadne sazeni se znalosti vysledku predem).

ZAKLADNI PRAVIDLA HRY
----------------------
  - Start: hlavni banka 1000 (fiktivnich) minci, zadni sazejici agenti.
  - 300 zapasu, davky po 5 - tj. 60 kol.
  - V KAZDEM kole je POVINNOST vsadit na VSECH 5 zapasu davky (na kteroukoli
    stranu, libovolnym agentem, libovolnou castkou >= MIN_STAKE).
  - GAME OVER kdykoli nastane jedno z:
      (a) celkovy soucet (hlavni banka + vsichni agenti) klesne na 0,
      (b) v danem kole neni mozne splnit povinnost vsadit na vsech 5 zapasu
          (zadny agent/hlavni banka nema dost na minimalni vklad) - "uvizl
          bez aktivniho tiketu".
  - CIL: po odehranem 300. (poslednim) zapase mit celkovy zustatek VYSSI
    nez startovnich 1000.

ZDROJ KURZU A MODELOVE PRAVDEPODOBNOSTI
-----------------------------------------
Pro kazdy zapas se pouzivaji SKUTECNE predzapasove kurzy (Odd_1/Odd_2 z
tenis/kurzy/wta_kurzy.csv - viz fetch_tennis_odds.py), ne dopocitany prumer -
ty u WTA 2021-2025 realne existuji. Modelova pravdepodobnost se pocita
STEJNYM cutoff-bezpecnym zpusobem jako v tennis_value_backtest.py
(forma+h2h+celkovy win rate, pouze ze zapasu PRED datem testovaneho utkani -
zadny unik informace z budoucnosti).

POCTIVE UPOZORNENI (viz CLAUDE.md / references/metodika.md): tenhle model
nema prokazanou sazkovou vyhodu nad trhem - 300 zapasu je navic maly vzorek
(velky rozptyl vysledku je u nahodnosti 1 zapasu ocekavany, ne dukaz, ze
"strategie funguje" nebo "nefunguje"). Tenhle skript je TEST prubehu/spravy
banky pod povinnosti sazet, ne dukaz sazkove vyhody.

PRIKAZY
-------
  python3 wta_backtest_agent.py init [--force]
      Postavi 300 zapasu (rovnomerne rozlozenych 2021-2025, jen zapasy s
      dost predchozi historii obou hracek) a resetuje stav (banka=1000,
      0 agentu, 0 kol). --force prepise existujici stav.

  python3 wta_backtest_agent.py status
      Prehled: kolo, kolik zapasu odehrano/zbyva, hlavni banka, agenti,
      celkovy zustatek, game_over/finished.

  python3 wta_backtest_agent.py agent create <jmeno> <castka>
  python3 wta_backtest_agent.py agent fund <id> <castka>
  python3 wta_backtest_agent.py agent defund <id> <castka>
  python3 wta_backtest_agent.py agent list

  python3 wta_backtest_agent.py tick [--bets "agent:idx:pick:stake,..."]
      Jadro hry. Bez --bets jen UKAZE aktualne otevrenou davku (bez
      vysledku) - pouzij na prvni kolo. S --bets VYHODNOTI (okamzite, vysledky
      uz zname) sazky na aktualne otevrenou davku, pripise/odecte z banky
      agentu, zkontroluje game-over podminky, posune se na dalsi davku a tu
      hned ukaze (takze typicky kolo = jedno volani s --bets).
      pick je 1 nebo 2 (hrac1/hrac2 zapasu podle poradi v davce).

  python3 wta_backtest_agent.py report
      Zaverecne shrnuti (kdyz next_idx>=300 nebo game_over): celkovy
      zustatek vs. start, uspesnost tiketu, ROI, verdikt SPLNENO/NESPLNENO.
"""
import argparse
import json
import os
import re
import sys
import time
import csv

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
_DATA_DIR = os.path.join(_SCRIPT_DIR, "..")

import tennis_value_backtest as tvb  # noqa: E402

STATE_PATH = os.path.join(_DATA_DIR, "wta_backtest_state.json")

N_MATCHES = 300
BATCH_SIZE = 5
MIN_HIST = 10          # min. odehranych zapasu obou hracek pred cutoffem
MIN_STAKE = 1.0        # nejmensi povoleny vklad na jeden tiket
STARTING_BANK = 1000.0


# --------------------------------------------------------------- stav

def _default_state():
    return {
        "main_bank": STARTING_BANK,
        "agents": {},         # id -> {name, bank, active, created_round}
        "matches": None,      # naplni init
        "tickets": [],        # historie vsech sazek
        "next_idx": 0,
        "round": 0,
        "game_over": None,
        "finished": False,
    }


def load_state():
    if not os.path.exists(STATE_PATH):
        print("CHYBA: stav neexistuje, spust nejdriv 'init'.", file=sys.stderr)
        sys.exit(1)
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(st):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or f"agent-{int(time.time())}"


def total_bankroll(st):
    return st["main_bank"] + sum(a["bank"] for a in st["agents"].values())


# --------------------------------------------------------------- init: vyber 300 zapasu

def _build_matches():
    sack = tvb.load_sackmann_wta()
    with open(tvb.ODDS_PATH, encoding="utf-8") as f:
        odds_rows = list(csv.DictReader(f))
    joined = tvb.join_matches(sack, odds_rows, verbose=False)
    hist = tvb.History(sack)

    enriched = []
    for m in joined:
        p, n1, n2 = tvb.model_prob(hist, m["name1"], m["name2"], m["cutoff"])
        if p is None or n1 < MIN_HIST or n2 < MIN_HIST:
            continue
        enriched.append({**m, "model_p1": p, "n1": n1, "n2": n2})
    enriched.sort(key=lambda m: (m["cutoff"], m["date"]))

    if len(enriched) < N_MATCHES:
        print(f"CHYBA: jen {len(enriched)} zapasu splnuje min. historii, "
              f"potrebuju {N_MATCHES}.", file=sys.stderr)
        sys.exit(1)

    last = len(enriched) - 1
    picked_idx = sorted({round(i * last / (N_MATCHES - 1)) for i in range(N_MATCHES)})
    # kolize po zaokrouhleni (nepravdepodobne, ale pro jistotu dopln) -
    # pokud chybi kusy, pridej dalsi nejblizsi nepouzite indexy
    picked_idx = list(picked_idx)
    used = set(picked_idx)
    j = 0
    while len(picked_idx) < N_MATCHES:
        if j not in used:
            picked_idx.append(j)
            used.add(j)
        j += 1
    picked_idx.sort()

    matches = []
    for idx, src_i in enumerate(picked_idx):
        m = enriched[src_i]
        q1, q2, margin = tvb.devig(m["odd1"], m["odd2"])
        matches.append({
            "idx": idx,
            "date": m["date"],
            "tourney": m["tourney"],
            "round_name": m["round"],
            "surface": m["surface"],
            "player1": m["name1"],
            "player2": m["name2"],
            "odd1": m["odd1"],
            "odd2": m["odd2"],
            "market_p1": q1,
            "market_p2": q2,
            "model_p1": m["model_p1"],
            "n1": m["n1"],
            "n2": m["n2"],
            "p1_won": bool(m["p1_won"]),
        })
    return matches


def cmd_init(args):
    if os.path.exists(STATE_PATH) and not args.force:
        print(f"Stav uz existuje ({STATE_PATH}). Pouzij --force pro reset.")
        sys.exit(1)
    print("Stavim 300 zapasu (spojovani kurzu + vypocet modelu, chvili to trva)...")
    matches = _build_matches()
    st = _default_state()
    st["matches"] = matches
    save_state(st)
    dates = [m["date"] for m in matches]
    print(f"Hotovo: {len(matches)} zapasu, rozsah {dates[0]} .. {dates[-1]}.")
    print(f"Hlavni banka: {STARTING_BANK:.0f}. Zadni agenti. Spust 'agent create' a pak 'tick'.")


# --------------------------------------------------------------- agent prikazy

def cmd_agent(args):
    st = load_state()
    if args.action == "create":
        amount = float(args.amount)
        if amount <= 0 or amount > st["main_bank"] + 1e-9:
            print(f"CHYBA: v hlavni bance je jen {st['main_bank']:.2f}.")
            sys.exit(1)
        aid = _slug(args.name)
        base = aid
        i = 2
        while aid in st["agents"]:
            aid = f"{base}-{i}"
            i += 1
        st["agents"][aid] = {"name": args.name, "bank": amount, "active": True,
                              "created_round": st["round"]}
        st["main_bank"] -= amount
        save_state(st)
        print(f"Vytvoren agent '{aid}' ({args.name}), banka {amount:.2f}. "
              f"Hlavni banka ted {st['main_bank']:.2f}.")
    elif args.action in ("fund", "defund"):
        aid, amount = args.name, float(args.amount)
        if aid not in st["agents"]:
            print(f"CHYBA: agent '{aid}' neexistuje.")
            sys.exit(1)
        if amount <= 0:
            print("CHYBA: castka musi byt kladna.")
            sys.exit(1)
        if args.action == "fund":
            if amount > st["main_bank"] + 1e-9:
                print(f"CHYBA: v hlavni bance je jen {st['main_bank']:.2f}.")
                sys.exit(1)
            st["main_bank"] -= amount
            st["agents"][aid]["bank"] += amount
        else:
            if amount > st["agents"][aid]["bank"] + 1e-9:
                print(f"CHYBA: agent ma jen {st['agents'][aid]['bank']:.2f}.")
                sys.exit(1)
            st["agents"][aid]["bank"] -= amount
            st["main_bank"] += amount
        save_state(st)
        print(f"OK. Hlavni banka {st['main_bank']:.2f}, agent '{aid}' "
              f"{st['agents'][aid]['bank']:.2f}.")
    elif args.action == "list":
        print(f"Hlavni banka: {st['main_bank']:.2f}")
        for aid, a in st["agents"].items():
            znak = "+" if a["active"] else "-"
            print(f"  [{znak}] {aid:<16} {a['name']:<24} banka {a['bank']:>10.2f}")
        print(f"Celkem (hlavni+agenti): {total_bankroll(st):.2f}")


# --------------------------------------------------------------- zobrazeni davky

def _format_batch(st, lo, hi):
    lines = []
    for m in st["matches"][lo:hi]:
        lines.append(
            f"  idx {m['idx']:>3}  {m['date']}  {m['surface']:<6} {m['round_name']:<14} "
            f"{m['tourney'][:28]:<28}\n"
            f"       1) {m['player1']:<22} kurz {m['odd1']:<5.2f} trh {m['market_p1']*100:4.1f}%  "
            f"model {m['model_p1']*100:4.1f}%  (n={m['n1']})\n"
            f"       2) {m['player2']:<22} kurz {m['odd2']:<5.2f} trh {m['market_p2']*100:4.1f}%  "
            f"model {(1-m['model_p1'])*100:4.1f}%  (n={m['n2']})"
        )
    return "\n".join(lines)


def _print_status_line(st):
    print(f"[kolo {st['round']}] odehrano {st['next_idx']}/{N_MATCHES} zapasu | "
          f"hlavni banka {st['main_bank']:.2f} | agenti {sum(a['bank'] for a in st['agents'].values()):.2f} "
          f"| CELKEM {total_bankroll(st):.2f}" +
          (f" | GAME OVER: {st['game_over']}" if st["game_over"] else "") +
          (" | HOTOVO" if st["finished"] else ""))


def cmd_status(args):
    st = load_state()
    _print_status_line(st)
    for aid, a in st["agents"].items():
        znak = "+" if a["active"] else "-"
        print(f"  [{znak}] {aid:<16} {a['name']:<24} banka {a['bank']:>10.2f}")


# --------------------------------------------------------------- tick (jadro)

def _parse_bets(spec, st, lo, hi):
    """'agent:idx:pick:stake,...' -> list dict. Validuje proti otevrene davce."""
    bets = []
    if not spec:
        return bets
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        if len(parts) != 4:
            print(f"CHYBA: neplatny format sazky '{chunk}' (cekam agent:idx:pick:stake).")
            sys.exit(1)
        aid, idx_s, pick_s, stake_s = parts
        if aid not in st["agents"]:
            print(f"CHYBA: agent '{aid}' neexistuje.")
            sys.exit(1)
        idx = int(idx_s)
        if not (lo <= idx < hi):
            print(f"CHYBA: idx {idx} neni v otevrene davce [{lo},{hi}).")
            sys.exit(1)
        pick = int(pick_s)
        if pick not in (1, 2):
            print(f"CHYBA: pick musi byt 1 nebo 2 (dostal jsem {pick_s}).")
            sys.exit(1)
        stake = float(stake_s)
        if stake < MIN_STAKE:
            print(f"CHYBA: vklad {stake} je pod minimem {MIN_STAKE}.")
            sys.exit(1)
        bets.append({"agent": aid, "idx": idx, "pick": pick, "stake": stake})
    return bets


def cmd_tick(args):
    st = load_state()
    if st["finished"] or st["game_over"]:
        print("Hra uz skoncila - spust 'report'.")
        _print_status_line(st)
        return

    lo, hi = st["next_idx"], min(st["next_idx"] + BATCH_SIZE, N_MATCHES)

    if not args.bets:
        print(f"Otevrena davka (kolo {st['round']}), zapasy {lo}-{hi - 1} "
              f"(sazky jeste NEJSOU zadane):")
        print(_format_batch(st, lo, hi))
        print("\nPovinnost: zadej sazku na VSECH 5 idx nez spustis tick --bets.")
        return

    bets = _parse_bets(args.bets, st, lo, hi)
    covered = {b["idx"] for b in bets}
    missing = [i for i in range(lo, hi) if i not in covered]
    if missing:
        print(f"CHYBA: povinnost vsadit na vsech 5 zapasu davky, chybi idx {missing}.")
        sys.exit(1)

    # over kryti stakes PRED jakymkoli odectenim (atomicky, aby se banka
    # nezacala menit a pak spadla na chybe v poli sazek)
    potreba = {}
    for b in bets:
        potreba[b["agent"]] = potreba.get(b["agent"], 0.0) + b["stake"]
    for aid, suma in potreba.items():
        if suma > st["agents"][aid]["bank"] + 1e-9:
            print(f"CHYBA: agent '{aid}' ma jen {st['agents'][aid]['bank']:.2f}, "
                  f"ale sazky na nej zadavaji {suma:.2f}.")
            sys.exit(1)

    # odecti vklady a rovnou vyhodnot (vysledek uz zname)
    by_idx = {m["idx"]: m for m in st["matches"]}
    results = []
    for b in bets:
        m = by_idx[b["idx"]]
        st["agents"][b["agent"]]["bank"] -= b["stake"]
        p1_won = m["p1_won"]
        picked_p1 = (b["pick"] == 1)
        won = (picked_p1 == p1_won)
        odds_used = m["odd1"] if picked_p1 else m["odd2"]
        payout = b["stake"] * odds_used if won else 0.0
        if won:
            st["agents"][b["agent"]]["bank"] += payout
        ticket = {**b, "round": st["round"], "odds": odds_used, "won": won,
                  "payout": payout, "winner": m["player1"] if p1_won else m["player2"]}
        st["tickets"].append(ticket)
        results.append(ticket)

    st["next_idx"] = hi
    st["round"] += 1

    # vysledky kola
    print(f"--- vysledky kola (zapasy {lo}-{hi - 1}) ---")
    for t in results:
        m = by_idx[t["idx"]]
        vyber = m["player1"] if t["pick"] == 1 else m["player2"]
        znak = "VYHRA" if t["won"] else "prohra"
        print(f"  idx {t['idx']:>3}  [{t['agent']}] {vyber:<22} za {t['stake']:>8.2f} "
              f"@ {t['odds']:.2f}  -> {znak:<7} (vitez: {t['winner']})  "
              f"{'+' if t['won'] else ''}{t['payout'] - t['stake']:+.2f}")

    # game-over kontrola (a)
    if total_bankroll(st) <= 1e-9:
        st["game_over"] = "bankrot - celkovy zustatek klesl na 0"

    # game-over kontrola (b): je mozne splnit povinnost v DALSIM kole?
    if not st["game_over"] and hi < N_MATCHES:
        nejvetsi_banka = max([st["main_bank"]] + [a["bank"] for a in st["agents"].values()] or [0])
        # min. potreba: 5 ruznych sazek, kazda >= MIN_STAKE, od jednoho nebo
        # vice agentu - staci, aby SOUCET vsech sazejicich bank stacil na
        # 5x MIN_STAKE a aspon jeden agent existoval.
        if not st["agents"] or sum(a["bank"] for a in st["agents"].values()) < BATCH_SIZE * MIN_STAKE - 1e-9:
            st["game_over"] = ("uvizl - zadny aktivni tiket neni mozny "
                                "(agenti nemaji dost na povinnych 5 sazek)")

    if hi >= N_MATCHES:
        st["finished"] = True

    save_state(st)
    print()
    _print_status_line(st)

    if st["game_over"] or st["finished"]:
        print("\nSpust 'report' pro zaverecne shrnuti.")
        return

    lo2, hi2 = st["next_idx"], min(st["next_idx"] + BATCH_SIZE, N_MATCHES)
    print(f"\nDalsi otevrena davka (kolo {st['round']}), zapasy {lo2}-{hi2 - 1}:")
    print(_format_batch(st, lo2, hi2))


# --------------------------------------------------------------- report

def cmd_report(args):
    st = load_state()
    total = total_bankroll(st)
    n = len(st["tickets"])
    wins = sum(1 for t in st["tickets"] if t["won"])
    staked = sum(t["stake"] for t in st["tickets"])
    returned = sum(t["payout"] for t in st["tickets"])
    roi = (returned - staked) / staked * 100.0 if staked else 0.0

    print("=== ZAVERECNE SHRNUTI: agent vs 300 historickych WTA zapasu ===")
    print(f"Odehrano zapasu: {st['next_idx']}/{N_MATCHES}  (kol: {st['round']})")
    print(f"Tiketu celkem: {n}  vyhranych: {wins} ({100.0 * wins / n:.1f} %)" if n else "Tiketu celkem: 0")
    print(f"Vsazeno celkem: {staked:.2f}  vraceno: {returned:.2f}  ROI: {roi:+.1f} %")
    print(f"Start: {STARTING_BANK:.0f}  Konec: {total:.2f}  "
          f"({'+' if total >= STARTING_BANK else ''}{total - STARTING_BANK:+.2f})")
    if st["game_over"]:
        print(f"GAME OVER: {st['game_over']}")
        print("VERDIKT: NESPLNENO (hra skoncila predcasne)")
    elif st["finished"] and total > STARTING_BANK:
        print("VERDIKT: SPLNENO (zustatek po 300. zapase vyssi nez start)")
    elif st["finished"]:
        print("VERDIKT: NESPLNENO (odehrano vsech 300, ale zustatek <= start)")
    else:
        print("VERDIKT: hra jeste bezi (neni odehrano vsech 300 ani game over)")
    print()
    print("Agenti:")
    print(f"  hlavni banka: {st['main_bank']:.2f}")
    for aid, a in st["agents"].items():
        print(f"  {aid:<16} {a['name']:<24} {a['bank']:>10.2f}")


# --------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("agent")
    p.add_argument("action", choices=["create", "fund", "defund", "list"])
    p.add_argument("name", nargs="?")
    p.add_argument("amount", nargs="?")
    p.set_defaults(func=cmd_agent)

    p = sub.add_parser("status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("tick")
    p.add_argument("--bets", default=None)
    p.set_defaults(func=cmd_tick)

    p = sub.add_parser("report")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args()
    if args.cmd == "agent" and args.action == "list":
        pass
    elif args.cmd == "agent" and args.name is None:
        ap.error("agent prikaz potrebuje jmeno/id")
    args.func(args)


if __name__ == "__main__":
    main()
