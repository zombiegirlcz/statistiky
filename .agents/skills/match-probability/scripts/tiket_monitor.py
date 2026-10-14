#!/usr/bin/env python3
"""
Monitor stavu VÍCESPORTOVNÍHO tiketu (Maxikombi/AKO), kde ne všechny nohy
mají v /statistiky nebo u dostupných API živý zdroj dat (viz README.md -
pokrytí je jen NHL + 22 evropských top-lig + ATP/WTA; KHL, VHL, finský/
švédský hokej, česká 2. liga a ASEAN fotbal pokrytí NEMAJÍ).

Pro každou nohu tiketu se definuje typ:
  - "tenis_vitez"   - živě sledovatelné přes Live Tennis API (LIVE_TENNIS_API_KEY),
                       stejný zdroj jako live_tennis_simulator.py
  - "sx_odds"       - SX.bet nabízí živé kurzy na dané straně (ne přímo výsledek,
                       ale pohyb kurzu k extrému je silný signál blížícího se konce)
  - "bez_zdroje"    - žádný automatizovaný zdroj (KHL/VHL/finský/švédský hokej,
                       česká 2. liga, ASEAN fotbal...) - nutná ruční kontrola

Použití:
    python3 tiket_monitor.py pridej --skupina B --typ tenis_vitez --hrac1 "Ann Li" --hrac2 "Elina Svitolina" --tip 2
    python3 tiket_monitor.py pridej --skupina H --typ sx_odds --sport fotbal --a "IF Gnistan" --b "Inter Turku"
    python3 tiket_monitor.py pridej --skupina A --typ bez_zdroje --popis "Buriram Utd. vs Borneo Samarinda - vysledek 1"
    python3 tiket_monitor.py tick        # jedno kolo kontroly vsech skupin, posle notifikace na zmeny
    python3 tiket_monitor.py watch --interval 60
    python3 tiket_monitor.py status
"""
import argparse
import json
import os
import subprocess
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

STATE_PATH = os.path.join(_SCRIPT_DIR, "tiket_monitor_state.json")


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"skupiny": {}}
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_notification(title, content):
    try:
        subprocess.run(["nh", "system", "notification", "-t", title, "-c", content],
                        capture_output=True, text=True, timeout=6)
    except subprocess.TimeoutExpired:
        pass
    except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
        print(f"  CHYBA pri odesilani notifikace: {e}")


# ---------------------------------------------------------------------------
# pridej — zaregistruje jednu nohu tiketu do sledovani
# ---------------------------------------------------------------------------
def cmd_pridej(args):
    state = load_state()
    leg = {"typ": args.typ, "stav": "ceka", "vysledek": None}
    if args.typ == "tenis_vitez":
        leg.update({"hrac1": args.hrac1, "hrac2": args.hrac2, "tip": args.tip,
                    "popis": f"{args.hrac1} vs {args.hrac2}, tip vitez {args.tip}"})
    elif args.typ == "sx_odds":
        leg.update({"sport": args.sport, "a": args.a, "b": args.b,
                    "popis": f"{args.a} vs {args.b} ({args.sport}, SX.bet kurzy)"})
    elif args.typ == "bez_zdroje":
        leg.update({"popis": args.popis or "(bez popisu)"})
    else:
        print(f"Neznamy typ '{args.typ}'. Pouzij: tenis_vitez | sx_odds | bez_zdroje")
        return
    state["skupiny"][args.skupina] = leg
    save_state(state)
    print(f"Skupina {args.skupina} pridana: {leg['popis']}")


# ---------------------------------------------------------------------------
# kontrola jednotlivych typu noh
# ---------------------------------------------------------------------------
def _check_tenis(leg):
    import live_tennis_simulator as lts
    try:
        matches = lts.fetch_live_matches()
    except SystemExit:
        # _live_api_request pri chybe (kvota, sit...) vola sys.exit(1) misto
        # vyjimky - monitor se tim nesmi zabit, jen tenhle tick pro tuhle nohu vynecha.
        return None, "Live Tennis API momentalne nedostupne (kvota/sit) - zkus pozdeji"
    except Exception as e:  # noqa: BLE001
        return None, f"chyba Live Tennis API: {e}"

    def norm(s):
        return s.lower().replace(".", "").strip()

    h1, h2 = norm(leg["hrac1"]), norm(leg["hrac2"])
    for m in matches:
        p1 = norm(m.get("player1", {}).get("name", ""))
        p2 = norm(m.get("player2", {}).get("name", ""))
        if (h1 in p1 or p1 in h1) and (h2 in p2 or p2 in h2):
            status = m.get("status")
            sc = m.get("score") or {}
            sets = sc.get("sets", [0, 0])
            info = f"stav setu {sets[0]}:{sets[1]}, API status={status}"
            if status == "finished":
                winner = 1 if sets[0] > sets[1] else 2
                return ("vyhrano" if str(winner) == str(leg["tip"]) else "prohrano"), info
            return "bezi", info
    # nenalezeno mezi zivymi - bud jeste nezacalo, nebo uz skoncilo a zmizelo z /matches?status=live
    return None, "zapas prave neni mezi zivymi (jeste nezacal, nebo API uz ho prestalo hlasit jako live)"


def _check_sx(leg):
    import sxbet_client as sx
    sid = {"fotbal": 5, "tenis": 6, "hokej": 2}.get(leg["sport"])
    if sid is None:
        return None, f"neznamy sport '{leg['sport']}'"
    try:
        markets = sx.active_markets(sport_ids=[sid], max_pages=15)
    except Exception as e:  # noqa: BLE001
        return None, f"chyba SX.bet API: {e}"

    for m in markets:
        t1, t2 = (m.get("teamOneName") or ""), (m.get("teamTwoName") or "")
        if leg["a"].lower() in t1.lower() and leg["b"].lower() in t2.lower():
            try:
                odds = sx.market_odds(m["marketHash"])
            except Exception:  # noqa: BLE001
                return "bezi", "trh nalezen, kurzy se nepodarilo nacist"
            o1, o2 = odds.get("outcomeOne"), odds.get("outcomeTwo")
            if o1 and o2:
                return "bezi", f"zivy kurz {t1} {o1[0]:.2f} - {t2} {o2[0]:.2f}"
            return "bezi", "trh nalezen, bez kurzu"
    # trh zmizel z aktivnich = zapas pravdepodobne skoncil a byl vyrovnan
    return None, "trh uz neni mezi aktivnimi na SX.bet (pravdepodobne dohrano - over vysledek rucne)"


def check_leg(skupina, leg):
    if leg["typ"] == "tenis_vitez":
        return _check_tenis(leg)
    if leg["typ"] == "sx_odds":
        return _check_sx(leg)
    return None, "bez automatizovaneho zdroje - zkontroluj rucne"


# ---------------------------------------------------------------------------
# tick / watch / status
# ---------------------------------------------------------------------------
def tick():
    state = load_state()
    if not state["skupiny"]:
        print("Zadne skupiny nejsou registrovany - pouzij 'pridej'.")
        return
    changed = False
    for skupina, leg in state["skupiny"].items():
        novy_stav, info = check_leg(skupina, leg)
        stary_stav = leg.get("stav")
        print(f"  [{skupina}] {leg['popis']}: {info or '(bez informace)'}")
        if novy_stav and novy_stav != stary_stav:
            leg["stav"] = novy_stav
            changed = True
            if novy_stav in ("vyhrano", "prohrano"):
                vysledek = "VYHRANO ✅" if novy_stav == "vyhrano" else "PROHRANO ❌"
                msg = f"Skupina {skupina}: {leg['popis']} -> {vysledek}"
                print(f"  >>> {msg}")
                send_notification("Tiket - zmena", msg)
            elif novy_stav == "bezi" and stary_stav == "ceka":
                msg = f"Skupina {skupina}: {leg['popis']} prave zacal"
                send_notification("Tiket - start", msg)
    if changed:
        save_state(state)


def watch(interval):
    print(f"Sleduji tiket kazdych {interval}s (Ctrl+C pro ukonceni)...")
    try:
        while True:
            tick()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nZastaveno.")


def status():
    state = load_state()
    if not state["skupiny"]:
        print("Zadne skupiny nejsou registrovany.")
        return
    vyhrano = prohrano = ceka = bezi = 0
    for skupina, leg in sorted(state["skupiny"].items()):
        stav = leg.get("stav", "ceka")
        znak = {"vyhrano": "✅", "prohrano": "❌", "bezi": "🔴", "ceka": "⏳"}.get(stav, "?")
        print(f"  [{skupina}] {znak} {leg['popis']} (typ={leg['typ']}, stav={stav})")
        if stav == "vyhrano":
            vyhrano += 1
        elif stav == "prohrano":
            prohrano += 1
        elif stav == "bezi":
            bezi += 1
        else:
            ceka += 1
    print(f"\nSouhrn: {vyhrano} vyhrano, {prohrano} prohrano, {bezi} bezi, {ceka} ceka/bez zdroje")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("pridej")
    p_add.add_argument("--skupina", required=True)
    p_add.add_argument("--typ", required=True, choices=["tenis_vitez", "sx_odds", "bez_zdroje"])
    p_add.add_argument("--hrac1")
    p_add.add_argument("--hrac2")
    p_add.add_argument("--tip")
    p_add.add_argument("--sport")
    p_add.add_argument("--a")
    p_add.add_argument("--b")
    p_add.add_argument("--popis")

    p_tick = sub.add_parser("tick")
    p_watch = sub.add_parser("watch")
    p_watch.add_argument("--interval", type=int, default=60)
    sub.add_parser("status")

    args = ap.parse_args()
    if args.cmd == "pridej":
        cmd_pridej(args)
    elif args.cmd == "tick":
        tick()
    elif args.cmd == "watch":
        watch(args.interval)
    elif args.cmd == "status":
        status()


if __name__ == "__main__":
    main()
