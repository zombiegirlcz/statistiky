#!/usr/bin/env python3
"""
Živý TENISOVÝ agent sázející na vítěze AKTUÁLNÍHO GEMU (ne celého zápasu).

Jiný trh než `live_tennis_simulator.py` (ten sází na vítěze CELÉHO zápasu
mezi favority podle modelu i trhu). Tenhle skript sází mnohem častěji -
jeden gem trvá pár minut, zápas jich má desítky - a cíl je stejný jako
u match-level verze: ať mezi jednotlivými tikety převažuje růst nad
poklesem banky (viz `references/metodika.md`, sekce "Změna cíle").

DŮLEŽITÝ ROZDÍL OPROTI `live_tennis_simulator.py`: pro "kdo vyhraje tenhle
gem" NEEXISTUJE nezávislý skutečný trh kurzů (The Odds API nabízí nanejvýš
vítěze zápasu/setu, ne jednotlivého gemu) - nejde tedy model zkřížově
ověřit druhým zdrojem. Sází se čistě na základě historického podávacího
rate hráče (hold rate) z `game_flow.py`, přepočítaného na pravděpodobnost
výhry AKTUÁLNÍHO gemu z AKTUÁLNÍHO stavu bodů (viz `game_win_prob` níže).
To NENÍ nová informace navíc - je to stejné historické číslo jako jinde
v projektu, jen vyjádřené na úrovni bodů místo gemů/zápasů. Řekni tohle
uživateli, pokud se zeptá, "jak to ví" - neví nic, co by nevěděl i
`live_tennis_simulator.py`, jen to aplikuje častěji.

MODEL (odvozeno, ne odhadnuto): hold rate hráče na podání (např. 68 %) je
pravděpodobnost VÝHRY CELÉHO GEMU od stavu 0:0. Z toho se zpětně (binárním
hledáním) dopočítá pravděpodobnost výhry JEDNOHO BODU na podání `p`, která
při standardním tenisovém skórování (0/15/30/40, výhoda od 40:40) dává
přesně tenhle hold rate. Z `p` a AKTUÁLNÍHO stavu bodů (např. 30:40) se pak
klasickou rekurzí spočítá pravděpodobnost výhry ROZEHRANÉHO gemu. Je to
matematicky přesný přepočet stejného čísla, ne nový odhad.

TIEBREAKY SE PŘESKAKUJÍ - jiné skórování (bod po bodu, střídavé podání),
model pro normální gem na ně neplatí.

REŽIMY:
  `tick`   - JEDNO kolo: nejdřív z aktuálních dat vyhodnotí dřív podané
             tikety (porovná uložený stav gemu s aktuálním - pokud mezitím
             skončil přesně JEDEN gem, přiřadí výhru/prohru; pokud je
             nejednoznačno kolik gemů proběhlo - např. se delší dobu
             nevolalo - tiket se ZRUŠÍ jako neplatný, ne uhodne), pak hledá
             nové příležitosti a zakládá tikety. VŠE JEDNÍM VOLÁNÍM API.
  `status` - přehled banky a tiketů, BEZ volání API.

Tenhle skript je určený ke spouštění ve SMYČCE s krátkým intervalem (řádově
1-3 minuty - gem je rychlá událost). To stojí API kvótu rychleji než
`live_tennis_simulator.py` (ten stačí co 15-30 min) - hlídej `/usage` a
koordinuj se s případnými dalšími procesy používajícími stejný klíč
(`crontab -l` ukáže, jestli něco jiného běží).

ROZPOČET: VLASTNÍ, oddělená fiktivní banka 1000 mincí v
`live_game_bets_log.jsonl` (NENÍ sdílená s `live_bets_log.jsonl` od
match-level skriptu - jiná frekvence a jiná metodika, smíchání by
znehodnotilo interpretaci obou).

Použití:
    python3 live_game_bet.py tick
    python3 live_game_bet.py status
"""
import json
import os
import sys
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
import live_tennis_simulator as base  # noqa: E402 - znovu použít fetch/parse/model infrastrukturu

_DATA_DIR = os.path.join(_SCRIPT_DIR, "..")
LOG_PATH = os.path.join(_DATA_DIR, "live_game_bets_log.jsonl")

GAME_FAV_MIN = 0.70      # bez nezávislého trhu je práh přísnější než u match-level (0,75/0,65)
STARTING_BANK = 1000.0
STAKE_PCT = 0.02
MIN_STAKE = 10.0
MAX_EXPOSURE_PCT = 0.50  # gemy se vyhodnocují rychle, tolerujeme víc souběžných tiketů


# ---------------------------------------------------------------------------
# Model: pravděpodobnost výhry ROZEHRANÉHO gemu z bodového skóre
# ---------------------------------------------------------------------------
_PT = {"0": 0, "15": 1, "30": 2, "40": 3, "AD": 4, "A": 4}


def _game_win_prob_from_points(p, a, b, memo):
    """p = pravděpodobnost výhry JEDNOHO bodu na podání. (a, b) = body
    podávajícího/přijímajícího na škále 0/15/30/40/výhoda (0-4)."""
    if a - b >= 2 and a >= 4:
        return 1.0
    if b - a >= 2 and b >= 4:
        return 0.0
    if a == b and a >= 3:
        denom = 1 - 2 * p * (1 - p)
        return (p * p / denom) if denom > 1e-9 else 0.5
    key = (a, b)
    if key in memo:
        return memo[key]
    res = p * _game_win_prob_from_points(p, a + 1, b, memo) + \
        (1 - p) * _game_win_prob_from_points(p, a, b + 1, memo)
    memo[key] = res
    return res


_P_CACHE = {}


def _invert_hold_to_point_p(hold_rate):
    """Najde p (pravděpodobnost výhry bodu na podání), které při skóre 0:0
    dá přesně zadaný hold rate (binární hledání - funkce je monotónní)."""
    key = round(hold_rate, 4)
    if key in _P_CACHE:
        return _P_CACHE[key]
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if _game_win_prob_from_points(mid, 0, 0, {}) < hold_rate:
            lo = mid
        else:
            hi = mid
    p = (lo + hi) / 2
    _P_CACHE[key] = p
    return p


def game_win_prob(hold_rate, points_server, points_returner):
    """Pravděpodobnost, že PODÁVAJÍCÍ vyhraje PRÁVĚ ROZEHRANÝ gem, ořezaná
    stejnou podlahou/stropem jako match-level model (viz live_tennis_simulator.
    MIN_PROB/MAX_PROB)."""
    p = _invert_hold_to_point_p(hold_rate)
    a, b = _PT.get(points_server), _PT.get(points_returner)
    if a is None or b is None:
        return None  # neznámý formát bodů (např. tiebreak - viz volající kód)
    raw = _game_win_prob_from_points(p, a, b, {})
    return min(base.MAX_PROB, max(base.MIN_PROB, raw))


# ---------------------------------------------------------------------------
# Log a banka (stejný vzor jako live_tennis_simulator.py, ale VLASTNÍ soubor)
# ---------------------------------------------------------------------------
def load_log():
    return base._load_jsonl(LOG_PATH)


def append_log(entry):
    base._append_jsonl(LOG_PATH, entry)


def rewrite_log(entries):
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def current_bank(log):
    bank = STARTING_BANK
    for e in log:
        if e["status"] == "won":
            bank += e["stake"] * (e["odds"] - 1)
        elif e["status"] == "lost":
            bank -= e["stake"]
        # "void" (zrušeno - nejednoznačný průběh) banku nemění
    return bank


def pending_exposure(log):
    return sum(e["stake"] for e in log if e["status"] == "pending")


def next_stake(log):
    bank = current_bank(log)
    if bank < MIN_STAKE:
        return None, f"rozpočet vyčerpán (banka {bank:.0f} mincí)"
    exposure = pending_exposure(log)
    if exposure >= bank * MAX_EXPOSURE_PCT:
        return None, f"strop souběžné expozice ({exposure:.0f} mincí)"
    stake = max(MIN_STAKE, round(bank * STAKE_PCT))
    free = min(bank - exposure, bank * MAX_EXPOSURE_PCT - exposure)
    if stake > free:
        return None, f"na tiket by zbylo jen {free:.0f} mincí"
    return stake, None


# ---------------------------------------------------------------------------
# Vyhodnocení dřívějších tiketů z AKTUÁLNÍHO snímku (žádné extra volání API)
# ---------------------------------------------------------------------------
def _settle_one(entry, live_by_id):
    m = live_by_id.get(entry["match_id"])
    if m is None:
        return False  # zápas už není v živé nabídce (skončil úplně) - vyřeší se jinde/později
    sc = m.get("score") or {}
    if not sc.get("sets"):
        return False
    cur = base.parse_score(sc, best_of_5=(m.get("format") == "BO5"))
    was = entry["state_at_bet"]

    if cur["sets"] != was["sets"]:
        # set se mezitím uzavřel - pokud to byl PRÁVĚ TEN set, ve kterém se
        # sázelo, poslední gem setu vždy vyhrává vítěz setu (tím se set
        # uzavírá) - jinak (uplynulo víc než jeden set) je to nejednoznačné
        if cur["sets"][0] + cur["sets"][1] != was["sets"][0] + was["sets"][1] + 1:
            entry["status"] = "void"
            entry["void_reason"] = "mezitím skončilo víc než jeden set - nejde přiřadit vítěze gemu"
        else:
            set_winner_slot = 1 if cur["sets"][0] > was["sets"][0] else 2
            winner_name = m["players"]["p1"]["name"] if set_winner_slot == 1 else m["players"]["p2"]["name"]
            entry["status"] = "won" if winner_name == entry["pick"] else "lost"
            entry["actual_winner"] = winner_name
        entry["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return True

    if cur["between_sets"] or was.get("between_sets"):
        return False  # čekáme, až se rozehraje normální gem

    da = cur["games"][0] - was["games"][0]
    db = cur["games"][1] - was["games"][1]
    if da == 0 and db == 0:
        return False  # gem ještě neskončil
    if (da, db) not in ((1, 0), (0, 1)):
        entry["status"] = "void"
        entry["void_reason"] = f"mezitím proběhlo víc gemů naráz ({was['games']} -> {cur['games']})"
        entry["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return True

    winner_slot = 1 if da == 1 else 2
    winner_name = m["players"]["p1"]["name"] if winner_slot == 1 else m["players"]["p2"]["name"]
    entry["status"] = "won" if winner_name == entry["pick"] else "lost"
    entry["actual_winner"] = winner_name
    entry["resolved_at"] = datetime.now(timezone.utc).isoformat()
    return True


# ---------------------------------------------------------------------------
# Hlavní režim
# ---------------------------------------------------------------------------
def cmd_tick():
    log = load_log()
    matches = base.fetch_live_matches()
    live_by_id = {m["id"]: m for m in matches}

    # 1) vyhodnocení dřívějších tiketů (bez dalšího volání API)
    pending = [e for e in log if e["status"] == "pending"]
    n_settled = 0
    bank_running = current_bank(log)
    for e in pending:
        if _settle_one(e, live_by_id):
            n_settled += 1
            print(f"  [{e['status']:<5}] {e['player1']} vs {e['player2']} - "
                  f"tiket na {e['pick']} ({e.get('void_reason') or e.get('actual_winner', '')})")
            if e["status"] in ("won", "lost"):
                profit = e["stake"] * (e["odds"] - 1) if e["status"] == "won" else -e["stake"]
                bank_before = bank_running
                bank_running += profit
                emoji = "📈" if profit > 0 else "📉"
                base.notify(
                    f"{emoji} Gem {'vyhrán' if e['status'] == 'won' else 'prohrán'}: {e['pick']}",
                    f"{e['player1']} vs {e['player2']} @ {e['odds']}\n"
                    f"Banka: {bank_before:.0f} -> {bank_running:.0f} mincí ({profit:+.0f})",
                )
    if n_settled:
        rewrite_log(log)
    log = load_log()

    # 2) hledání nových příležitostí
    already_pending_ids = {e["match_id"] for e in log if e["status"] == "pending"}
    singles = [m for m in matches
               if not m.get("is_doubles") and m.get("draw") == "singles"]
    n_checked = n_skip_data = n_skip_tb = n_bets = 0

    for m in singles:
        if m["id"] in already_pending_ids:
            continue  # na zápas max. jeden otevřený tiket na gem zároveň
        sc = m.get("score") or {}
        if not sc.get("sets") or sc.get("stale"):
            continue
        cur = base.parse_score(sc, best_of_5=(m.get("format") == "BO5"))
        if cur["is_tiebreak"] or cur["games"] == [6, 6] or cur["between_sets"]:
            n_skip_tb += 1
            continue

        p1, p2 = m["players"]["p1"], m["players"]["p2"]
        name1, name2 = p1["name"], p2["name"]
        gender = m.get("gender", "men")
        a_serves = (cur["server"] == 1)
        server_name = name1 if a_serves else name2
        hold, n_hold = base.get_hold_rate(server_name, gender)
        n_checked += 1
        if hold is None or n_hold < base.MIN_HOLD_N:
            n_skip_data += 1
            continue

        pts = cur["points"]
        p_server, p_returner = (pts[0], pts[1]) if a_serves else (pts[1], pts[0])
        p_win = game_win_prob(hold, p_server, p_returner)
        if p_win is None or p_win < GAME_FAV_MIN:
            continue

        stake, reason = next_stake(log)
        if stake is None:
            print(f"      ! {server_name} na podání vede gem (p={p_win:.0%}), "
                  f"ale tiket se nezakládá: {reason}")
            continue

        odds = round(1 / p_win, 2)  # fiktivní "fér" kurz (bez marže) - viz AGENT_NAVOD.md
        entry = {
            "match_id": m["id"], "logged_at": datetime.now(timezone.utc).isoformat(),
            "tournament": m.get("tournament"), "player1": name1, "player2": name2,
            "pick": server_name, "odds": odds, "model_p": round(p_win, 4),
            "score_at_bet": (f"sety {cur['sets'][0]}:{cur['sets'][1]}, "
                             f"gemy {cur['games'][0]}:{cur['games'][1]}, "
                             f"body {pts[0]}:{pts[1]}"),
            "state_at_bet": {"sets": cur["sets"], "games": cur["games"],
                             "between_sets": cur["between_sets"]},
            "stake": stake, "status": "pending",
        }
        append_log(entry)
        log.append(entry)
        n_bets += 1
        print(f"      => TIKET na gem pro {server_name} @ {odds} (p={p_win:.0%}), "
              f"vklad {stake:.0f} mincí [{name1} vs {name2}]")

    log = load_log()
    print(f"\nZkontrolováno na podání: {n_checked} (bez dost dat: {n_skip_data}, "
          f"přeskočeno tiebreak/mezi sety: {n_skip_tb})")
    print(f"Vyhodnoceno dřívějších tiketů: {n_settled}, nových tiketů: {n_bets}")
    print(f"Banka: {current_bank(log):.0f} mincí (start {STARTING_BANK:.0f}), "
          f"nevyřízeno {sum(1 for e in log if e['status'] == 'pending')} tiketů")


def cmd_status():
    log = load_log()
    if not log:
        print("Zatím žádné tikety (spusť nejdřív 'tick').")
        return
    won = sum(1 for e in log if e["status"] == "won")
    lost = sum(1 for e in log if e["status"] == "lost")
    void = sum(1 for e in log if e["status"] == "void")
    pend = sum(1 for e in log if e["status"] == "pending")
    settled = won + lost
    print(f"Tiketů celkem: {len(log)} (výhra {won}, prohra {lost}, "
          f"zrušeno {void}, nevyřízeno {pend})")
    if settled:
        print(f"Podíl rostoucích tiketů: {won/settled:.1%} ({won}/{settled})")
    print(f"Banka: {current_bank(log):.0f} mincí (start {STARTING_BANK:.0f})")
    print("\nPosledních 8 tiketů:")
    for e in log[-8:]:
        print(f"  [{e['status']:<8}] {e['player1']} vs {e['player2']} - na {e['pick']} "
              f"@ {e['odds']} (p={e['model_p']:.0%}) při {e.get('score_at_bet', '?')}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode == "tick":
        cmd_tick()
    elif mode == "status":
        cmd_status()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
