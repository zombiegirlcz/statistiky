#!/usr/bin/env python3
"""
Živý TENISOVÝ in-play simulátor - sleduje průběh KAŽDÉHO právě běžícího
zápasu a staví na ně FIKTIVNÍ tikety (žádné skutečné peníze, rozpočet je
1000 vymyšlených "mincí").

Je to výhradně tenisový nástroj. Fotbalová obdoba (na historických datech)
je `ticket_builder.py`, ta s tímhle nijak nesouvisí.

ZDROJE DAT (všechno skutečná data, nic simulovaného):
  - Live Tennis API (livetennisapi.com, klíč LIVE_TENNIS_API_KEY v ~/.env) -
    právě probíhající zápasy včetně skóre na úrovni GEMŮ i BODŮ a informace,
    kdo podává.
  - The Odds API (the-odds-api.com, klíč ODDS_API_KEY v ~/.env) - skutečné
    živé sázkové kurzy (pokrytí je menší než u Live Tennis API, hlavně
    ATP/WTA tour, ne Challenger/ITF).
  - Vlastní historická data (tenis/prubeh/, Match Charting Project) přes
    game_flow.py - hold/break rate hráčů.

REŽIMY:
  1. `watch`   - hlavní režim. Stáhne VŠECHNY živé zápasy, u každého zapíše
                 snímek stavu do live_progress_log.jsonl, porovná ho
                 s minulým snímkem a vypíše, CO SE MEZITÍM STALO (brejk,
                 uzavřený set, tiebreak, setbol/mečbol, výrazný posun
                 pravděpodobnosti, změna favorita). Kde zároveň vidí
                 hodnotu proti skutečným kurzům a má volný rozpočet,
                 založí fiktivní tiket.
  2. `scan`    - jen alias na `watch` (zpětná kompatibilita).
  3. `status`  - rychlý přehled banky a tiketů, BEZ volání API.

Vyhodnocování sázek a připisování do banky dělá SAMOSTATNÝ skript
`bet_evaluator.py` (spouštěj ho zvlášť, viz AGENT_NAVOD.md).

ROZPOČET: 1000 fiktivních mincí. Vklad je STAKE_PCT z aktuální banky
(minimálně MIN_STAKE), a zároveň platí strop na souběžnou expozici
(MAX_EXPOSURE_PCT) - když je v nevyřízených tiketech už moc peněz, nové
se nezakládají. Banka se nikdy nepočítá odhadem, vždy se dopočítá z logu.

DŮLEŽITÁ OMEZENÍ (poctivé nálezy z dřívějšího ladění):
  - Mince jsou FIKTIVNÍ. Skript neovládá žádný sázkový účet a nikdy
    nevsadí skutečné peníze.
  - Model pracuje na úrovni gemů (hold/break rate), ne bod po bodu -
    nevidí aktuální zranění, únavu ani počasí. Proto má pravděpodobnost
    podlahu a strop (MIN_PROB/MAX_PROB), aby nikdy netvrdil "100 % jisté".
  - MIN_HOLD_N chrání proti nesmyslným odhadům u málo zaznamenaných hráčů.
  - EDGE_MAX chrání proti tomu, aby se obrovský rozdíl vůči trhu bral jako
    "objevená hodnota" - častěji je to známka zastaralého nebo špatně
    přečteného skóre. Přesně tohle se stalo u zápasu Bublik-Mensik
    1. 10. 2026, kde špatně čtená struktura pole "games" vyrobila zdánlivý
    edge přes 50 procentních bodů (viz references/metodika.md).
  - NIKDY nesmí vzniknout "trh" jako zpožděná kopie vlastního modelu - to je
    tautologie, která vyrobí zisk i při nulové předvídací schopnosti (viz
    metodika.md). Tenhle skript proto porovnává výhradně se skutečnými kurzy.

Použití:
    python3 live_tennis_simulator.py watch
    python3 live_tennis_simulator.py status
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
import game_flow as gf  # noqa: E402
import odds_compare as oc  # noqa: E402

LIVE_API_BASE = "https://api.livetennisapi.com/api/public/v1"
_DATA_DIR = os.path.join(_SCRIPT_DIR, "..")
LOG_PATH = os.path.join(_DATA_DIR, "live_bets_log.jsonl")
PROGRESS_PATH = os.path.join(_DATA_DIR, "live_progress_log.jsonl")

MIN_HOLD_N = 20          # min. počet dřívějších podávacích gemů KAŽDÉHO hráče
EDGE_MIN = 0.06          # min. rozdíl model vs. trh na založení tiketu
EDGE_MAX = 0.25          # nad tohle je rozdíl podezřelý (zastaralá data), ne hodnota
MIN_PROB = 0.02          # nikdy netvrdit míň než 2 % - skutečná míra skreče/walkoveru
MAX_PROB = 0.98          # je v našich datech 3,59 % všech zápasů (30 885 zápasů)

STARTING_BANK = 1000.0   # rozpočet ve fiktivních mincích
STAKE_PCT = 0.02         # vklad = 2 % aktuální banky
MIN_STAKE = 10.0         # pod tohle se nesází (odpovídá minimálnímu vkladu u sázkovek)
MAX_EXPOSURE_PCT = 0.25  # max. podíl banky vázaný v nevyřízených tiketech zároveň

BIG_PROB_SHIFT = 0.10    # od jakého posunu pravděpodobnosti to hlásit jako událost


# ---------------------------------------------------------------------------
# Live Tennis API
# ---------------------------------------------------------------------------
def _live_api_request(path, params=None):
    api_key = os.environ.get("LIVE_TENNIS_API_KEY")
    if not api_key:
        print("CHYBA: chybí proměnná prostředí LIVE_TENNIS_API_KEY (viz ~/.env).")
        sys.exit(1)
    import urllib.parse
    q = urllib.parse.urlencode(params or {})
    url = f"{LIVE_API_BASE}{path}" + (f"?{q}" if q else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"CHYBA Live Tennis API ({e.code}): {body}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"CHYBA síťového připojení (Live Tennis API): {e}")
        sys.exit(1)


def fetch_live_matches():
    data = _live_api_request("/matches", {"status": "live", "limit": 100})
    return data.get("data", [])


def fetch_match(match_id):
    return _live_api_request(f"/matches/{match_id}")


# ---------------------------------------------------------------------------
# Čtení skóre z API (pozor na strukturu, snadno se přečte špatně)
# ---------------------------------------------------------------------------
def parse_score(sc, best_of_5=False):
    """Vytáhne ze 'score' aktuální stav. DŮLEŽITÉ: pole "games" je
    [gemy_hráče_1_po_setech, gemy_hráče_2_po_setech], tedy indexované
    NEJDŘÍV HRÁČEM, PAK SETEM - není to [skóre_1._setu, skóre_2._setu].
    Aktuální rozehraný set je proto poslední index v KAŽDÉM z těch dvou
    seznamů. Ověřeno na dokončeném zápase id 196994 (games=[[2,3],[6,6]],
    sets=[0,2] -> 1. set 2:6, 2. set 3:6, sedí)."""
    sets_a, sets_b = sc["sets"][0], sc["sets"][1]
    games = sc.get("games") or [[0], [0]]
    ga = games[0][-1] if games[0] else 0
    gb = games[1][-1] if games[1] else 0
    return {
        "sets": [sets_a, sets_b],
        "games": [ga, gb],
        "points": list(sc.get("points") or ["0", "0"]),
        "server": sc.get("server"),
        "is_tiebreak": bool(sc.get("is_tiebreak")),
        "sets_to_win": 3 if best_of_5 else 2,
    }


_POINT_RANK = {"0": 0, "15": 1, "30": 2, "40": 3, "AD": 4, "A": 4}


def _point_rank(p):
    if p in _POINT_RANK:
        return _POINT_RANK[p]
    try:
        return int(p)  # tiebreak se počítá normálními čísly
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Model: match_win_prob s PODLAHOU/STROPEM
# ---------------------------------------------------------------------------
def _match_win_prob_raw(hold_a, hold_b, sa, sb, ga, gb, a_serves, sets_to_win=2):
    memo = {}

    def rec(sa, sb, ga, gb, a_serves):
        if sa == sets_to_win:
            return 1.0
        if sb == sets_to_win:
            return 0.0
        key = (sa, sb, ga, gb, a_serves)
        if key in memo:
            return memo[key]
        if ga >= 6 and ga - gb >= 2:
            res = rec(sa + 1, sb, 0, 0, a_serves)
        elif gb >= 6 and gb - ga >= 2:
            res = rec(sa, sb + 1, 0, 0, a_serves)
        elif ga == 7:
            res = rec(sa + 1, sb, 0, 0, a_serves)
        elif gb == 7:
            res = rec(sa, sb + 1, 0, 0, a_serves)
        elif ga == 6 and gb == 6:
            p_tb_a = min(0.95, max(0.05, 0.5 + 0.5 * (hold_a - hold_b)))
            res = p_tb_a * rec(sa + 1, sb, 0, 0, not a_serves) + \
                  (1 - p_tb_a) * rec(sa, sb + 1, 0, 0, not a_serves)
        else:
            p_server = hold_a if a_serves else hold_b
            if a_serves:
                res = p_server * rec(sa, sb, ga + 1, gb, not a_serves) + \
                      (1 - p_server) * rec(sa, sb, ga, gb + 1, not a_serves)
            else:
                res = p_server * rec(sa, sb, ga, gb + 1, not a_serves) + \
                      (1 - p_server) * rec(sa, sb, ga + 1, gb, not a_serves)
        memo[key] = res
        return res

    return rec(sa, sb, ga, gb, a_serves)


def match_win_prob(hold_a, hold_b, sa, sb, ga, gb, a_serves, sets_to_win=2):
    """Jako _match_win_prob_raw, ale s podlahou a stropem.

    Důvod: samotná kombinatorika považuje stav typu 6:0 6:5 za jistotu
    (pravděpodobnost prakticky 0 nebo 1), jenže ve skutečném zápase se MŮŽE
    STÁT cokoliv - zranění, nevolnost, odstoupení, diskvalifikace. V našich
    datech (tenis/atp_matches_202*.csv + wta_matches_202*.csv, 30 885 zápasů)
    končí 3,59 % všech zápasů skrečí, walkoverem nebo diskvalifikací, a potkat
    to může i vedoucího hráče. Jako podlahu/strop proto bereme zhruba polovinu
    toho čísla (2 %) - hrubý, ale daty podložený odhad, ne číslo z hlavy."""
    raw = _match_win_prob_raw(hold_a, hold_b, sa, sb, ga, gb, a_serves, sets_to_win)
    return min(MAX_PROB, max(MIN_PROB, raw))


# ---------------------------------------------------------------------------
# Hold/break rate hráčů (z game_flow.py / Match Charting Project)
# ---------------------------------------------------------------------------
_CACHE = {}


def get_hold_rate(player_name, gender_code):
    """gender_code: 'men' nebo 'women' (jak to vrací Live Tennis API). Načtená
    data se cachují v rámci jednoho běhu - během jednoho `watch` se ptáme na
    desítky hráčů ze stejných souborů."""
    g = "m" if gender_code == "men" else "w"
    if g not in _CACHE:
        _CACHE[g] = (gf.load_matches(g), gf.load_games(g))
    matches, games = _CACHE[g]
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    hold, _break, n_hold, _n_break = gf.hold_break_rate(player_name, g, matches, games, today)
    return hold, n_hold


# ---------------------------------------------------------------------------
# Živé tržní kurzy (The Odds API) - volitelné, zápas nemusí být v nabídce
# ---------------------------------------------------------------------------
_ODDS_CACHE = None


def _all_tennis_events():
    """Stáhne události ze všech právě běžících tenisových turnajů jednou za běh
    (šetří kredity Odds API - dřív se stahovalo zvlášť pro každý zápas)."""
    global _ODDS_CACHE
    if _ODDS_CACHE is not None:
        return _ODDS_CACHE
    _ODDS_CACHE = []
    if not os.environ.get("ODDS_API_KEY"):
        return _ODDS_CACHE
    try:
        sports = oc.tennis_candidates()
    except SystemExit:
        return _ODDS_CACHE
    for s in sports:
        try:
            data, _ = oc.fetch_odds(s["key"])
        except SystemExit:
            continue
        _ODDS_CACHE.extend(data)
    return _ODDS_CACHE


def get_market_probs(name1, name2):
    """Vrátí (probs_dict, best_odds_dict), nebo (None, None), pokud zápas není
    v nabídce žádného právě běžícího tenisového turnaje na Odds API."""
    ev = oc.find_event(_all_tennis_events(), name1, name2)
    if not ev:
        return None, None
    probs = oc.devigged_probs(ev, "tenis")
    if not probs:
        return None, None
    best = {}
    for bm in ev.get("bookmakers", []):
        for mk in bm.get("markets", []):
            if mk["key"] == "h2h" and len(mk["outcomes"]) == 2:
                for o in mk["outcomes"]:
                    best[o["name"]] = max(best.get(o["name"], 0), o["price"])
    return probs, best


# ---------------------------------------------------------------------------
# Logy (JSONL - jeden řádek = jeden záznam)
# ---------------------------------------------------------------------------
def _load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # poškozený řádek radši přeskočit než spadnout
    return out


def _append_jsonl(path, entry):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_log():
    return _load_jsonl(LOG_PATH)


def append_log(entry):
    _append_jsonl(LOG_PATH, entry)


def rewrite_log(entries):
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def last_snapshots():
    """Poslední zaznamenaný snímek pro každý zápas (podle match_id)."""
    snaps = {}
    for row in _load_jsonl(PROGRESS_PATH):
        snaps[row["match_id"]] = row
    return snaps


# ---------------------------------------------------------------------------
# Rozpočet
# ---------------------------------------------------------------------------
def current_bank(log):
    """Banka se VŽDY dopočítá z logu - nikde se neukládá žádné 'aktuální' číslo,
    jediný zdroj pravdy je live_bets_log.jsonl."""
    bank = STARTING_BANK
    for e in log:
        if e["status"] == "won":
            bank += e["stake"] * (e["odds"] - 1)
        elif e["status"] == "lost":
            bank -= e["stake"]
    return bank


def pending_exposure(log):
    """Kolik mincí je zrovna vázáno v nevyřízených tiketech."""
    return sum(e["stake"] for e in log if e["status"] == "pending")


def next_stake(log):
    """Vrátí (vklad, důvod_zamítnutí). Vklad je None, když se sázet nemá."""
    bank = current_bank(log)
    if bank < MIN_STAKE:
        return None, f"rozpočet vyčerpán (banka {bank:.0f} mincí)"
    exposure = pending_exposure(log)
    if exposure >= bank * MAX_EXPOSURE_PCT:
        return None, (f"strop souběžné expozice ({exposure:.0f} z max "
                      f"{bank * MAX_EXPOSURE_PCT:.0f} mincí už je v nevyřízených tiketech)")
    stake = max(MIN_STAKE, round(bank * STAKE_PCT))
    free = min(bank - exposure, bank * MAX_EXPOSURE_PCT - exposure)
    if stake > free:
        return None, f"na tiket by zbylo jen {free:.0f} mincí (potřeba {stake:.0f})"
    return stake, None


# ---------------------------------------------------------------------------
# Detekce událostí ("co se stalo od minule")
# ---------------------------------------------------------------------------
def detect_events(prev, cur, name1, name2):
    """Porovná minulý a současný snímek a vrátí seznam slovně popsaných
    událostí. prev může být None (zápas vidíme poprvé)."""
    names = (name1, name2)
    if prev is None:
        return [f"poprvé viděn (sety {cur['sets'][0]}:{cur['sets'][1]}, "
                f"gemy {cur['games'][0]}:{cur['games'][1]})"]

    ev = []
    ps, cs = prev["sets"], cur["sets"]
    pg, cg = prev["games"], cur["games"]

    # uzavřený set
    for i in (0, 1):
        if cs[i] > ps[i]:
            ev.append(f"{names[i]} získal {cs[0] + cs[1]}. set "
                      f"({pg[0]}:{pg[1]}) - stav na sety {cs[0]}:{cs[1]}")

    # odehrané gemy v rozehraném setu (jen když se set nezměnil)
    if cs == ps:
        for i in (0, 1):
            if cg[i] > pg[i]:
                prev_server = prev.get("server")
                won_by_slot = i + 1
                if prev_server in (1, 2) and prev_server != won_by_slot:
                    ev.append(f"BREJK pro {names[i]} ({cg[0]}:{cg[1]})")
        if cg == [6, 6] and pg != [6, 6]:
            ev.append("tiebreak")

    # setbol / mečbol v právě hraném gemu
    sb = _break_point_label(cur, names)
    if sb:
        ev.append(sb)

    # výrazný posun pravděpodobnosti
    pp, cp = prev.get("model_p1"), cur.get("model_p1")
    if pp is not None and cp is not None:
        if abs(cp - pp) >= BIG_PROB_SHIFT:
            ev.append(f"posun šance {name1}: {pp:.0%} -> {cp:.0%}")
        if (pp - 0.5) * (cp - 0.5) < 0:
            ev.append(f"změna favorita na {name1 if cp > 0.5 else name2}")

    return ev


def _break_point_label(cur, names):
    """Vrátí 'mečbol pro X' / 'setbol pro X', pokud právě nastal, jinak None.
    Je to odhad ze stavu bodů - u tiebreaku se nepočítá přesně, proto se tam
    hlásí jen obecně."""
    pts = cur.get("points") or []
    if len(pts) != 2:
        return None
    r0, r1 = _point_rank(pts[0]), _point_rank(pts[1])
    if r0 is None or r1 is None or r0 == r1:
        return None
    lead = 0 if r0 > r1 else 1
    other = 1 - lead
    if cur.get("is_tiebreak") or cur["games"] == [6, 6]:
        # v tiebreaku stačí 7 bodů s odstupem 2
        if max(r0, r1) >= 6 and abs(r0 - r1) >= 1:
            return f"setbol/mečbol pro {names[lead]} v tiebreaku ({pts[0]}:{pts[1]})"
        return None
    if max(r0, r1) < 3:  # ani jeden nemá 40 ani výhodu
        return None
    g_lead, g_other = cur["games"][lead], cur["games"][other]
    wins_set = (g_lead + 1 >= 6 and g_lead + 1 - g_other >= 2)
    if not wins_set:
        return None
    if cur["sets"][lead] == cur["sets_to_win"] - 1:
        return f"MEČBOL pro {names[lead]} ({pts[0]}:{pts[1]}, gemy {g_lead}:{g_other})"
    return f"setbol pro {names[lead]} ({pts[0]}:{pts[1]}, gemy {g_lead}:{g_other})"


# ---------------------------------------------------------------------------
# Hlavní režim: watch
# ---------------------------------------------------------------------------
def cmd_watch():
    log = load_log()
    already_logged_ids = {e["match_id"] for e in log}
    prev_snaps = last_snapshots()
    matches = fetch_live_matches()
    singles = [m for m in matches
               if not m.get("is_doubles") and m.get("draw") == "singles"]
    print(f"Živých zápasů: {len(matches)} (z toho dvouhry: {len(singles)})")

    bank = current_bank(log)
    exposure = pending_exposure(log)
    print(f"Banka: {bank:.0f} mincí (start {STARTING_BANK:.0f}), "
          f"vázáno v nevyřízených tiketech: {exposure:.0f}\n")

    n_tracked = n_nodata = n_nomkt = n_bets = 0
    ts = datetime.now(timezone.utc).isoformat()

    for m in singles:
        sc = m.get("score") or {}
        if not sc.get("sets"):
            continue
        p1, p2 = m["players"]["p1"], m["players"]["p2"]
        name1, name2 = p1["name"], p2["name"]
        gender = m.get("gender", "men")
        cur = parse_score(sc, best_of_5=(m.get("format") == "BO5"))

        # model (když máme dost dat na OBA hráče)
        hold1, n1 = get_hold_rate(name1, gender)
        hold2, n2 = get_hold_rate(name2, gender)
        have_model = (hold1 is not None and hold2 is not None
                      and n1 >= MIN_HOLD_N and n2 >= MIN_HOLD_N)
        if have_model:
            cur["model_p1"] = match_win_prob(
                hold1, hold2, cur["sets"][0], cur["sets"][1],
                cur["games"][0], cur["games"][1],
                cur["server"] == 1, cur["sets_to_win"])
        else:
            cur["model_p1"] = None
            n_nodata += 1

        prev = prev_snaps.get(m["id"])
        events = detect_events(prev, cur, name1, name2)
        n_tracked += 1

        # SLEDOVÁNÍ PRŮBĚHU: zapisuje se u každého zápasu, i bez modelu a kurzů
        snapshot = {
            "match_id": m["id"], "ts": ts, "tournament": m.get("tournament"),
            "player1": name1, "player2": name2, "gender": gender,
            "sets": cur["sets"], "games": cur["games"], "points": cur["points"],
            "server": cur["server"], "is_tiebreak": cur["is_tiebreak"],
            "sets_to_win": cur["sets_to_win"],
            "model_p1": round(cur["model_p1"], 4) if cur["model_p1"] is not None else None,
            "events": events,
            "stale": bool(sc.get("stale")),
        }
        _append_jsonl(PROGRESS_PATH, snapshot)

        head = (f"{name1} vs {name2} [{m.get('tournament', '?')}] "
                f"sety {cur['sets'][0]}:{cur['sets'][1]}, "
                f"gemy {cur['games'][0]}:{cur['games'][1]}, "
                f"body {cur['points'][0]}:{cur['points'][1]}")
        if cur["model_p1"] is not None:
            head += f" | model: {cur['model_p1']:.0%} / {1 - cur['model_p1']:.0%}"
        else:
            head += " | model: málo historických dat"
        print(head)
        for e in events:
            print(f"      - {e}")

        # --- sázková část (jen pokud máme model i skutečné kurzy) ---
        if not have_model or m["id"] in already_logged_ids or sc.get("stale"):
            continue
        probs, best_odds = get_market_probs(name1, name2)
        if not probs or probs.get(name1) is None or probs.get(name2) is None:
            n_nomkt += 1
            continue

        p1_model = cur["model_p1"]
        edge1 = p1_model - probs[name1]
        edge2 = (1 - p1_model) - probs[name2]
        pick = None
        if EDGE_MIN <= edge1 <= EDGE_MAX and name1 in best_odds:
            pick = (name1, best_odds[name1], edge1, p1_model)
        elif EDGE_MIN <= edge2 <= EDGE_MAX and name2 in best_odds:
            pick = (name2, best_odds[name2], edge2, 1 - p1_model)
        if not pick:
            continue

        stake, reason = next_stake(log)
        if stake is None:
            print(f"      ! hodnota na {pick[0]} @ {pick[1]} (edge {pick[2]:+.0%}), "
                  f"ale tiket se nezakládá: {reason}")
            continue

        name, odds, edge, model_p = pick
        entry = {
            "match_id": m["id"], "logged_at": ts, "tournament": m.get("tournament"),
            "player1": name1, "player2": name2, "pick": name, "odds": odds,
            "edge": round(edge, 4), "model_p": round(model_p, 4),
            "market_p": round(probs[name], 4),
            "score_at_bet": (f"sety {cur['sets'][0]}:{cur['sets'][1]}, "
                             f"gemy {cur['games'][0]}:{cur['games'][1]}"),
            "stake": stake, "status": "pending",
        }
        append_log(entry)
        log.append(entry)
        n_bets += 1
        print(f"      => TIKET na {name} @ {odds} (edge {edge:+.0%}), vklad {stake:.0f} mincí")

    print(f"\nSledováno zápasů: {n_tracked}")
    print(f"  bez modelu (málo historických dat na hráče): {n_nodata}")
    print(f"  bez živých kurzů v nabídce: {n_nomkt}")
    print(f"Nových fiktivních tiketů: {n_bets}")
    log = load_log()
    print(f"Banka: {current_bank(log):.0f} mincí, "
          f"nevyřízeno {sum(1 for e in log if e['status'] == 'pending')} tiketů "
          f"({pending_exposure(log):.0f} mincí vázáno)")
    print("\nVyhodnocení dohraných zápasů spusť zvlášť: python3 bet_evaluator.py vyhodnot")


def cmd_status():
    log = load_log()
    if not log:
        print("Zatím žádné tikety (spusť nejdřív 'watch').")
    else:
        won = sum(1 for e in log if e["status"] == "won")
        lost = sum(1 for e in log if e["status"] == "lost")
        pend = sum(1 for e in log if e["status"] == "pending")
        print(f"Tiketů celkem: {len(log)} (výhra {won}, prohra {lost}, nevyřízeno {pend})")
        print(f"Banka: {current_bank(log):.0f} mincí (start {STARTING_BANK:.0f}), "
              f"vázáno {pending_exposure(log):.0f}")
        print("\nPosledních 5 tiketů:")
        for e in log[-5:]:
            print(f"  [{e['status']:<8}] {e['player1']} vs {e['player2']} - na {e['pick']} "
                  f"@ {e['odds']} (edge {e['edge']:+.0%}) při {e.get('score_at_bet', '?')}")
    snaps = last_snapshots()
    if snaps:
        print(f"\nSledovaných zápasů v průběhovém logu: {len(snaps)} "
              f"({len(_load_jsonl(PROGRESS_PATH))} snímků celkem)")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode in ("watch", "scan"):
        cmd_watch()
    elif mode == "status":
        cmd_status()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
