#!/usr/bin/env python3
"""
Sleduje PRUBEH vsech zivych NHL zapasu (nebo jen vybranych game_id) pres
oficialni NHL API (api-web.nhle.com - stejne jako update_stats.py a
goalscorer_prob.py --live) a pri kazdem novem golu posle systemovou
notifikaci na telefon pres `nh system notification` (NetHunter Unified CLI).

Text notifikace sklada AI agent `pi -p` (model deepseek-free/deepseek-chat,
zdarma) z holych faktu o golu - hrac, tym, treitna/cas, aktualni skore.

STAV JE BEZSTAVOVY MEZI BEHY (stejny vzor jako live_tennis_simulator.py) -
uz odeslane goly se zapisuji do `live_goal_watcher_seen.jsonl`, takze skript
jde spoustet opakovane (doporuceno kazdych 30-60 s v dobe zivych zapasu,
napr. pres `watch -n 60` nebo cron) a nikdy neposle stejny gol dvakrat.

Pouziti:
    python3 live_goal_watcher.py tick                      # jedno kolo - zjisti zive zapasy, posle notifikace
    python3 live_goal_watcher.py tick --games 2026020044,2026020045   # jen konkretni zapasy
    python3 live_goal_watcher.py watch --interval 60        # smycka - tickuje donekonecna kazdych N sekund
    python3 live_goal_watcher.py status                     # co uz bylo videno, bez API volani

Zavislosti: jen std knihovna + binarky `pi` a `nh`, ktere uz jsou v systemu.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_LOG = os.path.join(_SCRIPT_DIR, "live_goal_watcher_seen.jsonl")
UA = "Mozilla/5.0 (StatistikyBot live_goal_watcher)"

PERIOD_NAMES = {1: "1. tretina", 2: "2. tretina", 3: "3. tretina"}


def http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def load_seen():
    seen = set()
    if os.path.exists(SEEN_LOG):
        with open(SEEN_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    seen.add(json.loads(line)["key"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return seen


def mark_seen(key, detail):
    with open(SEEN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "ts": time.time(), **detail}, ensure_ascii=False) + "\n")


def live_game_ids():
    """Vsechny zapasy dneska s gameState LIVE nebo CRIT (kriticka faze/konec zapasu)."""
    today = time.strftime("%Y-%m-%d")
    try:
        data = http_get_json(f"https://api-web.nhle.com/v1/schedule/{today}")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"CHYBA pri stahovani rozpisu: {e}")
        return []
    ids = []
    for day in data.get("gameWeek", []):
        for g in day.get("games", []):
            if g.get("gameState") in ("LIVE", "CRIT"):
                ids.append(g["id"])
    return ids


def period_label(period_descriptor):
    num = period_descriptor.get("number")
    ptype = period_descriptor.get("periodType")
    if ptype == "OT":
        return "prodlouzeni"
    if ptype == "SO":
        return "samostatne najezdy"
    return PERIOD_NAMES.get(num, f"{num}. tretina")


def check_game(game_id, seen):
    try:
        data = http_get_json(f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  [{game_id}] CHYBA: {e}")
        return []

    away = data["awayTeam"]["abbrev"]
    home = data["homeTeam"]["abbrev"]
    roster = {r["playerId"]: f"{r['firstName']['default']} {r['lastName']['default']}" for r in data.get("rosterSpots", [])}

    new_goals = []
    for play in data.get("plays", []):
        if play.get("typeDescKey") != "goal":
            continue
        event_id = play.get("eventId")
        key = f"{game_id}:{event_id}"
        if key in seen:
            continue

        details = play.get("details", {})
        scorer_id = details.get("scoringPlayerId")
        scorer = roster.get(scorer_id, f"hrac #{scorer_id}")
        away_score = details.get("awayScore")
        home_score = details.get("homeScore")
        period = period_label(play.get("periodDescriptor", {}))
        clock = play.get("timeInPeriod", "?")

        goal_info = {
            "game_id": game_id,
            "event_id": event_id,
            "scorer": scorer,
            "away": away,
            "home": home,
            "away_score": away_score,
            "home_score": home_score,
            "period": period,
            "clock": clock,
            "key": key,
        }
        new_goals.append(goal_info)

    return new_goals


def compose_notification(goal):
    """Poskladat text notifikace pres `pi -p` (deepseek-free, zdarma).
    Pri selhani (chybi pi/API/offline) spadne na jednoduchou sablonu."""
    fact = (
        f"Gol: {goal['scorer']} ({goal['home']} vs {goal['away']}), "
        f"{goal['period']}, cas {goal['clock']}, aktualni skore {goal['away']} {goal['away_score']}:{goal['home_score']} {goal['home']}."
    )
    prompt = (
        "Z techto faktu o hokejovem golu uprav JEDNU kratkou cesky vetu (max 15 slov) "
        "pro push notifikaci na telefon - strucne, vecne, bez emoji, bez uvozovek. "
        "Vypis VYHRADNE tu jednu finalni vetu a nic jineho - zadne uvahy, poznamky, "
        "pochybnosti ani vysvetlovani postupu. Pokud si nejsi jisty detailem, "
        "vynech ho a drz se jen zadanych faktu. "
        f"Fakta: {fact}"
    )
    surname = goal["scorer"].split()[-1].lower()
    try:
        result = subprocess.run(
            ["pi", "-p", prompt, "--provider", "deepseek-free", "--model", "deepseek-chat", "--no-session"],
            capture_output=True, text=True, timeout=60,
        )
        text = result.stdout.strip().splitlines()
        # pi vypisuje i startup hlasky na stdout - vezmi posledni neprazdnou radku, co nezacina [ nebo Warning
        candidates = [l.strip() for l in text if l.strip() and not l.strip().startswith(("[", "Warning"))]
        if candidates:
            answer = candidates[-1]
            # pojistka proti modelu, ktery do odpovedi vmicha vlastni uvahu/pochybnosti
            # (napr. "Ale rozpor: ..."): overime, ze je to jedna krátka vazna veta
            # obsahujici prijmeni strelce, jinak neduverujeme a padneme na sablonu.
            looks_sane = (
                len(answer) <= 160
                and surname in answer.lower()
                and answer.count(".") <= 2
            )
            if looks_sane:
                return answer
            print(f"  (odpoved AI vypadala podezrele, pouzivam sablonu: {answer!r})")
    except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
        print(f"  (pi -p selhalo, pouzivam sablonu: {e})")
    return fact


def send_notification(title, content):
    # `nh` po vypsani potvrzeni zustava viset (interni fork na Android broadcast
    # service, ktery nikdy nezavre stdout pipe) - notifikace uz je v tu chvili
    # odeslana, takze kratky timeout a nasledny kill procesu je spravne chovani,
    # ne chyba.
    try:
        subprocess.run(["nh", "system", "notification", "-t", title, "-c", content],
                        capture_output=True, text=True, timeout=6)
        return True
    except subprocess.TimeoutExpired:
        return True  # notifikace byla s vysokou pravdepodobnosti uz odeslana pred timeoutem
    except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
        print(f"  CHYBA pri odesilani notifikace: {e}")
        return False


def tick(game_ids=None):
    if not game_ids:
        game_ids = live_game_ids()
        if not game_ids:
            print("Zadny zivy zapas prave nebezi.")
            return
    print(f"Kontroluji {len(game_ids)} zapasu: {game_ids}")
    seen = load_seen()
    total_new = 0
    for gid in game_ids:
        new_goals = check_game(gid, seen)
        for goal in new_goals:
            msg = compose_notification(goal)
            print(f"  NOVY GOL [{gid}]: {msg}")
            send_notification("Gol!", msg)
            mark_seen(goal["key"], goal)
            total_new += 1
    if total_new == 0:
        print("  zadne nove goly od posledni kontroly.")
    else:
        print(f"  odeslano {total_new} notifikaci.")


def watch(interval, game_ids=None):
    print(f"Sleduji zapasy kazdych {interval}s (Ctrl+C pro ukonceni)...")
    try:
        while True:
            tick(game_ids)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nZastaveno.")


def status():
    seen = load_seen()
    print(f"Celkem uz odeslanych golovych notifikaci: {len(seen)}")
    if os.path.exists(SEEN_LOG):
        with open(SEEN_LOG, encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-10:]:
            d = json.loads(line)
            print(f"  [{d['game_id']}] {d.get('scorer','?')} - {d.get('period','?')} ({d.get('away')} {d.get('away_score')}:{d.get('home_score')} {d.get('home')})")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_tick = sub.add_parser("tick")
    p_tick.add_argument("--games", help="carkou oddelene game_id, jinak vsechny zive")

    p_watch = sub.add_parser("watch")
    p_watch.add_argument("--interval", type=int, default=60)
    p_watch.add_argument("--games", help="carkou oddelene game_id, jinak vsechny zive")

    sub.add_parser("status")

    args = ap.parse_args()
    game_ids = [int(x) for x in args.games.split(",")] if getattr(args, "games", None) else None

    if args.cmd == "tick":
        tick(game_ids)
    elif args.cmd == "watch":
        watch(args.interval, game_ids)
    elif args.cmd == "status":
        status()


if __name__ == "__main__":
    main()
