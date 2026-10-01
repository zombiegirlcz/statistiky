#!/usr/bin/env python3
"""
Vyhodnocovač fiktivních tenisových sázek z `live_tennis_simulator.py`.

Dělá dvě věci:
  1. Dotáhne skutečné výsledky zápasů, na které jsou nevyřízené tikety
     (Live Tennis API), označí je jako výhru/prohru a PŘIPÍŠE DO BANKY.
  2. Vypíše poctivý přehled - hlavně PODÍL ROSTOUCÍCH TIKETŮ (cíl strategie
     "silný favorit" v live_tennis_simulator.py, viz jeho docstring), dál
     vývoj banky, ROI a rozpad podle kurzových pásem.

Banka startuje na 1000 fiktivních mincí a nikde se neukládá jako číslo -
vždy se dopočítá z `live_bets_log.jsonl` (výhra: +vklad*(kurz-1),
prohra: -vklad). Ten log je jediný zdroj pravdy, NIKDY ho needituj ručně.

Režimy:
    python3 bet_evaluator.py vyhodnot   # dotáhne výsledky z API + vypíše přehled
    python3 bet_evaluator.py report     # jen přehled, BEZ volání API (nestojí kvótu)

Kvóta: `vyhodnot` spotřebuje 1 volání Live Tennis API za každý nevyřízený
tiket (free tier má 100 volání/den). `report` nespotřebuje nic.

POZOR na interpretaci: strategie "silný favorit" cílí na vysoký PODÍL
vyhraných (= rostoucích) tiketů, ne na porážku trhu - to se u malého vzorku
projeví rychle (vysoká úspěšnost je vidět i po desítkách tiketů). ALE ani
vysoký podíl výher neznamená kladné ROI ani zaručený dlouhodobý růst -
sázková marže zůstává v kurzu i u favoritů. Klesající banka i při vysoké
úspěšnosti (jedna velká prohra smaže víc malých výher) je legitimní
výsledek, ne chyba k opravení. Viz references/metodika.md pro poctivý
backtest, který ukázal, že tenhle model nemá nad trhem žádnou prokázanou
výhodu - jen vysokou úspěšnost u bezpečných favoritů.
"""
import os
import sys
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
import live_tennis_simulator as sim  # noqa: E402

# Kolik tiketů je potřeba, aby mělo smysl mluvit o výsledku jinak než "šum"
N_MEANINGFUL = 100


def settle_pending():
    """Projde nevyřízené tikety, u dohraných zápasů určí vítěze a zapíše
    výsledek. Vrátí počet vyhodnocených tiketů."""
    log = sim.load_log()
    pending = [e for e in log if e["status"] == "pending"]
    if not pending:
        print("Žádné nevyřízené tikety.\n")
        return 0

    print(f"Nevyřízených tiketů: {len(pending)} - zjišťuji výsledky...\n")
    n_settled = 0
    bank_running = sim.current_bank(log)
    for e in pending:
        m = sim.fetch_match(e["match_id"])
        # OVĚŘENO na skutečném dokončeném zápase (id 196994, 1. 10. 2026):
        # "status": "completed", "outcome": "completed" (ŘETĚZEC, ne objekt!),
        # vítěz je v TOP-LEVEL poli "winner": 2 (ČÍSLO 1 nebo 2 = p1/p2).
        winner_slot = m.get("winner")
        if m.get("status") != "completed" or winner_slot not in (1, 2, "1", "2"):
            state = m.get("status", "?")
            print(f"  [čeká] {e['player1']} vs {e['player2']} - zápas je ve stavu "
                  f"'{state}', vítěz ještě není známý")
            continue
        winner_name = (m["players"]["p1"]["name"] if winner_slot in (1, "1")
                       else m["players"]["p2"]["name"])
        e["status"] = "won" if winner_name == e["pick"] else "lost"
        e["resolved_at"] = datetime.now(timezone.utc).isoformat()
        e["actual_winner"] = winner_name
        # kolik to udělalo s bankou
        e["profit"] = round(e["stake"] * (e["odds"] - 1) if e["status"] == "won"
                            else -e["stake"], 2)
        n_settled += 1
        mark = "VÝHRA" if e["status"] == "won" else "PROHRA"
        print(f"  [{mark:<6}] {e['player1']} vs {e['player2']} - tiket na {e['pick']} "
              f"@ {e['odds']}, vyhrál {winner_name} ({e['profit']:+.0f} mincí)")

        bank_before = bank_running
        bank_running += e["profit"]
        emoji = "📈" if e["profit"] > 0 else "📉"
        sim.notify(
            f"{emoji} Tiket {mark.lower()}: {e['pick']}",
            f"{e['player1']} vs {e['player2']} @ {e['odds']}\n"
            f"Banka: {bank_before:.0f} -> {bank_running:.0f} mincí ({e['profit']:+.0f})",
        )

    if n_settled:
        sim.rewrite_log(log)
    print(f"\nVyhodnoceno nových tiketů: {n_settled}\n")
    return n_settled


def _band(value, edges, labels):
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


def _sparkline(values):
    """Jednoduchý ASCII graf vývoje banky (bez externích knihoven)."""
    if len(values) < 2:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return blocks[0] * len(values)
    return "".join(blocks[int((v - lo) / (hi - lo) * (len(blocks) - 1))] for v in values)


def report():
    log = sim.load_log()
    if not log:
        print("Zatím žádné tikety - spusť nejdřív "
              "'python3 live_tennis_simulator.py watch'.")
        return

    settled = [e for e in log if e["status"] in ("won", "lost")]
    pending = [e for e in log if e["status"] == "pending"]
    won = [e for e in settled if e["status"] == "won"]

    bank = sim.current_bank(log)
    exposure = sim.pending_exposure(log)
    staked = sum(e["stake"] for e in settled)
    returned = sum(e["stake"] * e["odds"] for e in won)
    roi = (returned - staked) / staked if staked else 0.0

    print("=" * 66)
    print("PŘEHLED FIKTIVNÍCH TENISOVÝCH SÁZEK (strategie: silný favorit)")
    print("=" * 66)
    if settled:
        up_share = len(won) / len(settled)
        trend = "PŘEVAŽUJE RŮST" if up_share > 0.5 else (
            "PŘEVAŽUJE POKLES" if up_share < 0.5 else "VYROVNANÉ")
        print(f"Podíl rostoucích tiketů (výher): {up_share:>6.1%}  -> {trend}")
        print(f"  ({len(won)} roste / {len(settled) - len(won)} klesá "
              f"z {len(settled)} vyhodnocených)")
    print()
    print(f"Rozpočet na start:    {sim.STARTING_BANK:>10.0f} mincí")
    print(f"Banka teď:            {bank:>10.0f} mincí  "
          f"({bank - sim.STARTING_BANK:+.0f})")
    print(f"Vázáno v nevyřízených:{exposure:>10.0f} mincí ({len(pending)} tiketů)")
    print()
    print(f"Tiketů celkem:        {len(log):>10}")
    print(f"  vyhodnocených:      {len(settled):>10}  "
          f"(výhra {len(won)}, prohra {len(settled) - len(won)})")
    if settled:
        print(f"  vsazeno / vráceno:  {staked:>10.0f} / {returned:.0f} mincí")
        print(f"  ROI:                {roi:>+9.1%}  (poctivé měřítko peněz - "
              f"i vysoký podíl výher může dát záporné ROI)")
        avg_odds = sum(e["odds"] for e in settled) / len(settled)
        print(f"  průměrný kurz:      {avg_odds:>10.2f}")

    if len(settled) >= 2:
        print("\nVÝVOJ BANKY (chronologicky podle vyhodnocení)")
        chron = sorted(settled, key=lambda e: e.get("resolved_at", e["logged_at"]))
        running = sim.STARTING_BANK
        curve = [running]
        for e in chron:
            running += (e["stake"] * (e["odds"] - 1) if e["status"] == "won"
                        else -e["stake"])
            curve.append(running)
        print(f"  {_sparkline(curve)}")
        print(f"  {curve[0]:.0f} -> {curve[-1]:.0f} mincí "
              f"(nejvýš {max(curve):.0f}, nejníž {min(curve):.0f})")
        print("  posledních 10 tiketů:")
        for e, b in list(zip(chron, curve[1:]))[-10:]:
            mark = "V" if e["status"] == "won" else "P"
            print(f"    [{mark}] {e['pick'][:22]:<22} @ {e['odds']:>5.2f}  -> banka {b:.0f}")

    if len(settled) >= 5:
        print("\nROZPAD PODLE KURZU")
        _breakdown(settled, lambda e: _band(
            e["odds"], [1.5, 2.5, 4.0], ["pod 1,50", "1,50-2,49", "2,50-3,99", "4,00+"]))

    print("\n" + "-" * 66)
    if len(settled) < N_MEANINGFUL:
        print(f"POZOR: vyhodnocených tiketů je {len(settled)}, to je málo na "
              f"spolehlivý podíl výher. I u skutečných favoritů se pár desítek")
        print(f"tiketů může sejít příznivěji nebo hůř, než je jejich dlouhodobá")
        print(f"úspěšnost. Spolehlivější obrázek dá řádově {N_MEANINGFUL}+ tiketů.")
    else:
        print(f"Vzorek {len(settled)} tiketů už dává slušnou představu o podílu výher.")
        print("Neupravuj parametry dodatečně tak, aby výsledek vyšel hezky -")
        print("tím se měření znehodnotí.")
    print("Mince jsou FIKTIVNÍ. I strategie se spoustou výherních tiketů může mít")
    print("záporné ROI (jedna velká prohra smaže víc malých výher) a žádná")
    print("strategie nemůže zaručit, že banka neklesne pod startovní hodnotu.")
    print("-" * 66)


def _breakdown(settled, keyfn):
    groups = {}
    for e in settled:
        groups.setdefault(keyfn(e), []).append(e)
    for label in sorted(groups):
        g = groups[label]
        w = [e for e in g if e["status"] == "won"]
        st = sum(e["stake"] for e in g)
        rt = sum(e["stake"] * e["odds"] for e in w)
        r = (rt - st) / st if st else 0.0
        print(f"  {label:<12} n={len(g):<4} úspěšnost {len(w) / len(g):>5.0%}  "
              f"ROI {r:>+7.1%}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "vyhodnot"
    if mode == "vyhodnot":
        settle_pending()
        report()
    elif mode == "report":
        report()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
