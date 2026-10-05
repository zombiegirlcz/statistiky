#!/usr/bin/env python3
"""
server.py — HTTP REST API nad daty /statistiky, napojené na pi agenta.

Co to je
--------
Malý Flask server, který na jednom místě vystaví to, co už v repu existuje:

  1. PŘÍMÁ DATA (rychlé, deterministické, neplatí se za to API kvóta):
     - /api/sx/markets    aktivní trhy na SX.bet (vítěz, sety, góly, handicap, poločas, třetiny…)
     - /api/sx/odds       VŠECHNY trhy ke konkrétnímu zápasu (odmaržované pravděpodobnosti + kurzy)
     - /api/matches       nadcházející zápasy s kurzy (The Odds API — fallback)
     - /api/odds          odvigované tržní pravděpodobnosti konkrétního zápasu (The Odds API — fallback)
     - /api/probability   náš model z historických dat (aggregate_stats.py)

     Primární zdroj kurzů je SX.bet (zdarma, bez API klíče, víc trhů).
     The Odds API je jen fallback pro sporty/ligy, které SX.bet nenabízí.

  2. PI AGENT (pomalejší, ale "chytřejší" — použije skill match-probability):
     - /api/tickets       složí nejlepší možné tikety z aktuální nabídky
     - /api/agent         obecný dotaz na agenta (volný prompt)

Server je bezstavový — všechna logika zůstává ve skriptech ve
`.agents/skills/match-probability/scripts/`, server je jen tenká vrstva,
která je volá. Nemění žádná data, jen čte.

Spuštění
--------
    cd /root/statistiky && source ~/.env
    python3 server.py                 # bind 0.0.0.0:8000
    SPORTS_PORT=9000 python3 server.py

    # nebo přes přiložený start.sh (najde LAN IP, spustí na pozadí)
    ./server.sh [port]

POZOR na bezpečnost: server NEMÁ autentizaci a umí spouštět pi agenta
(s bash přístupem). Bind na 0.0.0.0 znamená, že ho uvidí kdokoli na stejné
síti. Používej jen v důvěryhodné síti (Wi-Fi/hotspot), nikdy ho nevystavuj
do internetu bez reverzní proxy s autentizací.

Endpointy
---------
GET  /health
GET  /api/sx/markets?sport=tenis|fotbal|hokej[&market=vitez|set|goly|handicap|polocas|tretiny|gemy|sety|1x2][&limit=40]
GET  /api/sx/odds?sport=...&a=...&b=...[&market=...][&live=true]
GET  /api/matches?sport=tenis|fotbal|hokej[&liga=E0]
GET  /api/odds?sport=...&a=...&b=...
GET  /api/sx/trades?dny=14&limit=100
GET  /api/learner/digest?sekundy=25
POST /api/probability   {"sport":"fotbal","a":"Arsenal","b":"Chelsea","home":"A"}
POST /api/run           {"skript":"replay","args":["--rok","2024"],"timeout":900}
POST /api/tickets       {"sport":"tenis","budget":1000,"max_legs":3,"trenink":true,"poznamka":"..."}
POST /api/agent         {"prompt":"..."}
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, ".agents", "skills", "match-probability", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

WEB_DIR = os.path.join(BASE_DIR, "web")

# pi binárka — výchozí 'pi' ze systémového PATH (nebo PI_BIN z ~/.env)
PI_BIN = os.environ.get("PI_BIN", "pi")
PI_TIMEOUT = int(os.environ.get("PI_TIMEOUT", "600"))

ALLOWED_SPORTS = ("fotbal", "tenis", "hokej")

# SX.bet sportId (viz sxbet_client.py)
SX_SPORT_ID = {"tenis": 6, "fotbal": 5, "hokej": 2}

# Lidské názvy skupin trhů na SX.bet → seznam typů (viz _markets.md).
# Server díky tomu vystaví víc než jen vítěze zápasu.
SX_MARKET_GROUPS = {
    "tenis": {
        "vitez":      {52, 226},
        "set":        {202, 203, 204},          # vítěz 1./2./3. setu
        "gemy":       {201, 166},              # AH na gemy / O-U gamů
        "sety":       {165, 866},              # celkový počet setů / set spread
    },
    "fotbal": {
        "vitez":      {52, 226},
        "1x2":        {1},
        "goly":       {2, 28},                 # přes/pod góly
        "handicap":   {3},
        "polocas":    {63, 77, 53},            # 12 poločas / O-U poločas / AH poločas
    },
    "hokej": {
        "vitez":      {52, 226},
        "goly":       {2, 28},                 # přes/pod včetně prodloužení
        "handicap":   {3, 342},
        "tretiny":    {202, 203, 204, 21, 45, 46, 64, 65, 66},
    },
}

# Whitelist výpočtů/simulací, které smí /api/run spustit. Klíč = jméno pro API,
# hodnota = cesta ke skriptu RELATIVNĚ ke SCRIPTS_DIR. Argumenty se předávají
# jako seznam (žádný shell), takže nejde propašovat shell injection.
BACKTEST_SCRIPTS = {
    "backtest":          "backtest.py",
    "tennis-value":      "tennis_value_backtest.py",
    "inplay-timing":     "inplay_timing_backtest.py",
    "replay":            "replay_backtest.py",
    "replay-variants":   "replay_variants.py",
    "replay-model-only": "replay_model_only.py",
    "composer":          "composer_learner.py",
    "ticket-builder":    "ticket_builder.py",
    "fav-prohra":        os.path.join("..", "backtest_fav_prohra.py"),
    "aggregate":         "aggregate_stats.py",
    "market-probs":      "market_probs.py",
    "tape-collect":      "tape_archiver.py",
    "tape-settle":       "tape_archiver.py",
    "tape-report":       "tape_archiver.py",
    "player-profile":    "player_profile.py",
    "game-flow":         "game_flow.py",
    "odds-compare":      "odds_compare.py",
}

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------
# Registry běžícího pi agenta, aby ho šlo z jiného requestu přerušit.
# Flask jede s threaded=True, takže /api/interrupt běží paralelně s během agenta.
_PROC_LOCK = threading.Lock()
_PROC = {"p": None}


def _run(cmd, timeout=120, cwd=SCRIPTS_DIR, track=False):
    """Spustí příkaz a vrátí (rc, stdout, stderr, interrupted).

    Když `track=True`, proces se zaregistruje do globálního registru, aby ho
    šlo přes /api/interrupt zabít (i s celou skupinou potomků, protože si pi
    spouští vlastní podprocesy). Nikdy nevyhazuje výjimku kvůli rc.
    """
    try:
        if not track:
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
            return p.returncode, p.stdout, p.stderr, False

        # Tracked varianta: start_new_session=True → vlastní procesní skupina,
        # takže killpg zabije i děti (pi → bash → python skripty).
        p = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        with _PROC_LOCK:
            _PROC["p"] = p
        try:
            out, err = p.communicate(timeout=timeout)
            return p.returncode, out, err, False
        except subprocess.TimeoutExpired:
            _kill_proc(p)
            out, err = p.communicate()
            return 124, out, (err or "") + f"\n[timeout po {timeout}s]", False
        finally:
            with _PROC_LOCK:
                if _PROC["p"] is p:
                    _PROC["p"] = None
    except FileNotFoundError as e:
        return 127, "", f"příkaz nenalezen: {e}", False


def _kill_proc(p):
    """Zabije proces i celou jeho skupinu (SIGKILL), potichu když už neběží."""
    if p is None or p.poll() is not None:
        return False
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            p.kill()
        except OSError:
            pass
    return True


def interrupt_agent():
    """Přeruší běžícího pi agenta. Vrací True, když něco běželo a bylo zabito."""
    with _PROC_LOCK:
        p = _PROC.get("p")
    return _kill_proc(p)


def agent_running():
    with _PROC_LOCK:
        p = _PROC.get("p")
    return bool(p is not None and p.poll() is None)


def run_pi(prompt, timeout=None):
    """Spustí pi agenta non-interaktivně (`-p`) s povolenými nástroji.

    Formát volání je ověřený (viz deploy/tick.sh): `pi -p <prompt> --tools ...`.
    Agent běží v adresáři scripts, takže vidí všechny sázející skripty.

    POZOR: `--tools bash` NESTAČÍ. Agent při stavbě tiketu potřebuje i `read`
    (přečíst SKILL.md a references/metodika.md), případně `edit`/`write`.
    S povoleným jen `bash` model napsal tool call jako TEXT místo aby ho
    zavolal, a volání pak viselo (ověřeno živě 2026-10-05).
    """
    if not prompt or not prompt.strip():
        return {"ok": False, "error": "prázdný prompt"}
    rc, out, err, _interrupted = _run(
        [PI_BIN, "-p", prompt, "--tools", "bash,read,edit,write"],
        timeout=timeout or PI_TIMEOUT, track=True,
    )
    # rc < 0 = zabito signálem (SIGKILL = -9) → přerušeno uživatelem.
    was_interrupted = rc is not None and rc < 0
    return {
        "ok": rc == 0,
        "rc": rc,
        "interrupted": was_interrupted,
        "stdout": out,
        "stderr": err,
        "pozn": "Přerušeno uživatelem (proces zabit)." if was_interrupted else None,
    }


def _sport_key_for_football_league(code):
    """Mapování ligového kódu z názvu našeho CSV (E0, I1, ...) na sport_key
    The Odds API — sdílí tabulku s odds_compare.py, ať není duplikace.
    (Fallback, když SX.bet daný zápas nenabízí.)"""
    import odds_compare as oc
    return oc.FOOTBALL_LEAGUE_TO_SPORT_KEY.get(code)


# ---------------------------------------------------------------------------
# SX.bet — primární zdroj kurzů (více trhů než The Odds API)
# ---------------------------------------------------------------------------
def _sx_group_types(sport, group):
    """Vrátí množinu typů trhů pro daný sport a skupinu (nebo všechny)."""
    groups = SX_MARKET_GROUPS.get(sport, {})
    if group in (None, "", "all"):
        out = set()
        for v in groups.values():
            out |= v
        return out
    return groups.get(group, set())


def _sx_market_dict(m, with_odds=True):
    """Převede surový SX.bet trh na JSON-friendly dict (+ odmaržované probs)."""
    import sxbet_client as sx
    d = {
        "marketHash": m.get("marketHash"),
        "typ": m.get("type"),
        "liga": m.get("leagueLabel"),
        "zacatek": m.get("gameTime"),
        "live": m.get("liveEnabled"),
        "strana1": m.get("outcomeOneName") or m.get("teamOneName"),
        "strana2": m.get("outcomeTwoName") or m.get("teamTwoName"),
        "line": m.get("line"),
    }
    if with_odds:
        odds = sx.market_odds(m["marketHash"])
        if "outcomeOne" in odds and "outcomeTwo" in odds:
            dev = sx.devigged_probs(m["marketHash"])
            d["kurz1"] = round(odds["outcomeOne"][0], 3)
            d["kurz2"] = round(odds["outcomeTwo"][0], 3)
            d["p1"] = round(dev["outcomeOne"], 4) if dev else round(odds["outcomeOne"][1], 4)
            d["p2"] = round(dev["outcomeTwo"], 4) if dev else round(odds["outcomeTwo"][1], 4)
            d["likvidita1"] = round(odds["outcomeOne"][2], 2)
            d["likvidita2"] = round(odds["outcomeTwo"][2], 2)
        else:
            d["kurz1"] = d["kurz2"] = None
    return d


def _digest_do_textu(d):
    """Převede digest z veřejného SX.bet tape (sx_tape.digest) na text pro prompt."""
    if not d:
        return "(žádný tréninkový digest)"
    lines = [
        f"Zdroj: {d.get('zdroj', '?')} za {d.get('okno_sekund')} s.",
        f"Zachyceno {d.get('pocet_trades', 0)} sázek, celkem "
        f"{d.get('celkem_stake_usdc', 0)} USDC.",
    ]
    if d.get("podil_stake_strana1") is not None:
        lines.append(f"Podíl money na stranu 1 (outcomeOne): {d['podil_stake_strana1']:.0%}.")
    for x in (d.get("podle_typu_trhu") or [])[:6]:
        lines.append(f"  trh {x.get('typ_trhu')}: n={x.get('n')}, "
                     f"{x.get('stake_usdc')} USDC, prům. kurz {x.get('prum_kurz')}")
    for x in (d.get("podle_ligy") or [])[:6]:
        lines.append(f"  liga {x.get('liga')}: n={x.get('n')}, {x.get('stake_usdc')} USDC")
    for p in d.get("pouceni") or []:
        lines.append(f"• {p}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# / — webové UI (tmavý motiv) pro stavbu tiketů
# ---------------------------------------------------------------------------
@app.get("/")
@app.get("/app")
def index():
    if not os.path.exists(os.path.join(WEB_DIR, "index.html")):
        return jsonify({"ok": True, "service": "statistiky-server", "pozn": "web/index.html nenalezen",
                        "endpoints": [r.rule for r in app.url_map.iter_rules() if r.rule.startswith("/api")]}), 200
    return send_from_directory(WEB_DIR, "index.html")


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "statistiky-server",
        "scripts_dir": SCRIPTS_DIR,
        "pi_bin": PI_BIN,
        "sports": list(ALLOWED_SPORTS),
        "bookmaker": os.environ.get("BOOKMAKER", "sxbet_sim"),
        "zdroj_kurzu": "sxbet (primární) + oddsapi (fallback)",
        "skripty_pro_run": sorted(BACKTEST_SCRIPTS),
        "sx_market_groups": {
            sport: {grp: sorted(types) for grp, types in groups.items()}
            for sport, groups in SX_MARKET_GROUPS.items()
        },
    })


# ---------------------------------------------------------------------------
# /api/matches — nadcházející zápasy s kurzy
# ---------------------------------------------------------------------------
@app.get("/api/matches")
def matches():
    sport = (request.args.get("sport") or "").strip().lower()
    if sport not in ALLOWED_SPORTS:
        return jsonify({"ok": False, "error": f"sport musí být jeden z {ALLOWED_SPORTS}"}), 400

    import odds_compare as oc

    events = []
    label = None
    try:
        if sport == "hokej":
            data, remaining = oc.fetch_odds(oc.HOCKEY_SPORT_KEY)
            events = data
            label = "NHL"
        elif sport == "tenis":
            remaining = None
            for s in oc.tennis_candidates():
                data, remaining = oc.fetch_odds(s["key"])
                if data:
                    events = data
                    label = s["title"]
                    break
        else:  # fotbal
            liga = (request.args.get("liga") or "").strip()
            if liga:
                key = _sport_key_for_football_league(liga)
                if not key:
                    return jsonify({"ok": False, "error": f"ligový kód '{liga}' nemá sport_key"}), 400
                data, remaining = oc.fetch_odds(key)
                events = data
                label = liga
            else:
                return jsonify({
                    "ok": False,
                    "error": "u fotbalu je potřeba zadat &liga=<kód> (E0, I1, SP1, ...)",
                }), 400
    except SystemExit as e:  # odds_compare při chybě API volá sys.exit
        return jsonify({"ok": False, "error": f"odds API selhalo (exit {e.code})"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    out = []
    for ev in events or []:
        out.append({
            "home": ev.get("home_team"),
            "away": ev.get("away_team"),
            "commence_time": ev.get("commence_time"),
            "n_bookmakers": len(ev.get("bookmakers", [])),
        })
    return jsonify({"ok": True, "sport": sport, "liga": label, "pocet": len(out), "zapasy": out})


# ---------------------------------------------------------------------------
# /api/odds — odvigované tržní pravděpodobnosti konkrétního zápasu
# ---------------------------------------------------------------------------
@app.get("/api/odds")
def odds():
    sport = (request.args.get("sport") or "").strip().lower()
    a = (request.args.get("a") or "").strip()
    b = (request.args.get("b") or "").strip()
    if sport not in ALLOWED_SPORTS or not a or not b:
        return jsonify({"ok": False, "error": "potřeba sport, a, b"}), 400

    import odds_compare as oc

    try:
        if sport == "fotbal":
            _code, key = oc.football_sport_key(a, b)
            if not key:
                return jsonify({"ok": False, "error": "ligu zápasu nelze určit / není v Odds API"}), 404
            events, remaining = oc.fetch_odds(key)
        elif sport == "hokej":
            events, remaining = oc.fetch_odds(oc.HOCKEY_SPORT_KEY)
        else:
            events, remaining = [], None
            for s in oc.tennis_candidates():
                evs, remaining = oc.fetch_odds(s["key"])
                events.extend(evs or [])
        ev = oc.find_event(events, a, b)
        if not ev:
            return jsonify({"ok": False, "error": "zápas se v nadcházejících kurzech nenašel"}), 404
        probs = oc.devigged_probs(ev, sport)
    except SystemExit as e:
        return jsonify({"ok": False, "error": f"odds API selhalo (exit {e.code})"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({
        "ok": True,
        "zapas": f"{ev.get('home_team')} vs {ev.get('away_team')}",
        "commence_time": ev.get("commence_time"),
        "trh_pravdepodobnosti": probs,
        "kredity_zbyva": remaining,
        "pozn": "toto je The Odds API fallback; pro víc trhů použij /api/sx/odds",
    })


# ---------------------------------------------------------------------------
# /api/sx/markets — aktivní trhy na SX.bet (VÍC než jen vítěz zápasu)
# ---------------------------------------------------------------------------
@app.get("/api/sx/markets")
def sx_markets():
    sport = (request.args.get("sport") or "").strip().lower()
    if sport not in ALLOWED_SPORTS:
        return jsonify({"ok": False, "error": f"sport musí být jeden z {ALLOWED_SPORTS}"}), 400
    group = (request.args.get("market") or "all").strip().lower()
    try:
        limit = min(int(request.args.get("limit", 40)), 200)
    except ValueError:
        limit = 40

    import sxbet_client as sx
    types = _sx_group_types(sport, group)
    if not types:
        return jsonify({"ok": False, "error": f"neznámá skupina '{group}' pro {sport}",
                        "dostupne": list(SX_MARKET_GROUPS.get(sport, {}))}), 400

    try:
        markets = sx.active_markets(sport_ids=[SX_SPORT_ID[sport]], only_main_line=True, max_pages=8)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 502

    out = []
    for m in markets:
        if m.get("type") not in types:
            continue
        out.append(_sx_market_dict(m))
        if len(out) >= limit:
            break

    return jsonify({
        "ok": True, "zdroj": "sxbet", "sport": sport, "skupina": group,
        "pocet": len(out), "trhy": out,
        "pozn": "p1/p2 = odmaržovaná pravděpodobnost, kurz1/2 = aktuální taker kurz, "
                "likvidita = kolik USDC je v nejlepší úrovni booku",
    })


# ---------------------------------------------------------------------------
# /api/sx/odds — všechny trhy ke KONKRÉTNÍMU zápasu/páru
# ---------------------------------------------------------------------------
@app.get("/api/sx/odds")
def sx_odds():
    sport = (request.args.get("sport") or "").strip().lower()
    a = (request.args.get("a") or "").strip()
    b = (request.args.get("b") or "").strip()
    if sport not in ALLOWED_SPORTS or not a or not b:
        return jsonify({"ok": False, "error": "potřeba sport, a, b"}), 400
    group = (request.args.get("market") or "all").strip().lower()
    live = request.args.get("live")
    live_only = None if live is None else live.lower() in ("1", "true", "yes")

    import sxbet_client as sx
    sid = SX_SPORT_ID[sport]
    types = _sx_group_types(sport, group)
    if not types:
        return jsonify({"ok": False, "error": f"neznámá skupina '{group}' pro {sport}",
                        "dostupne": list(SX_MARKET_GROUPS.get(sport, {}))}), 400

    try:
        allm = sx.active_markets(sport_ids=[sid], live_only=live_only, max_pages=10)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 502

    # najdi event (sportXEventId), kde figurují obě jména
    event_ids, label = set(), None
    for m in allm:
        t1, t2 = m.get("teamOneName", ""), m.get("teamTwoName", "")
        if ((sx._name_match(a, t1) and sx._name_match(b, t2)) or
                (sx._name_match(a, t2) and sx._name_match(b, t1))):
            event_ids.add(m.get("sportXEventId"))
            label = m.get("leagueLabel") or label
    if not event_ids:
        return jsonify({"ok": False, "error": "zápas na SX.bet nenalezen (jiná jména / není v nabídce)"}), 404

    out = []
    for m in allm:
        if m.get("sportXEventId") not in event_ids or m.get("type") not in types:
            continue
        out.append(_sx_market_dict(m))
    out.sort(key=lambda d: (d.get("typ") or 0, d.get("line") or 0))
    return jsonify({
        "ok": True, "zdroj": "sxbet", "zapas": f"{a} vs {b}", "liga": label,
        "skupina": group, "pocet_trhu": len(out), "trhy": out,
    })


# ---------------------------------------------------------------------------
# /api/probability — náš model z historických dat
# ---------------------------------------------------------------------------
@app.post("/api/probability")
def probability():
    data = request.get_json(silent=True) or {}
    sport = (data.get("sport") or "").strip().lower()
    a = (data.get("a") or "").strip()
    b = (data.get("b") or "").strip()
    if sport not in ALLOWED_SPORTS or not a or not b:
        return jsonify({"ok": False, "error": "potřeba sport, a, b"}), 400

    cmd = [sys.executable, "aggregate_stats.py", sport, a, b]
    home = data.get("home")
    if home in ("A", "B"):
        cmd += ["--home", home]
    rc, out, err, _ = _run(cmd, timeout=180)
    return jsonify({"ok": rc == 0, "rc": rc, "vystup": out, "stderr": err})


# ---------------------------------------------------------------------------
# /api/tickets — nejlepší možné tikety (přes pi agenta)
# ---------------------------------------------------------------------------
@app.post("/api/tickets")
def tickets():
    data = request.get_json(silent=True) or {}
    sport = (data.get("sport") or "všechny sporty").strip().lower()
    budget = data.get("budget", 1000)
    max_legs = data.get("max_legs", 3)
    poznamka = (data.get("poznamka") or "").strip()

    # --- "trénink" před stavbou: živý tape SX.bet (sázky cizích hráčů) ---
    digest_txt = ""
    if data.get("trenink", True):
        try:
            import sx_tape
            d = sx_tape.digest(seconds=int(data.get("tape_sekundy", 20)),
                               max_trades=int(data.get("tape_max", 300)))
            digest_txt = _digest_do_textu(d)
        except Exception as e:  # noqa: BLE001 - trénink nesmí shodit stavbu tiketu
            digest_txt = f"(tréninkový digest z veřejného tape se nepodařilo sestavit: {e})"

    prompt = (
        f"Sestav nejlepší možné sázkové tikety. Sport: {sport}. "
        f"Denní rozpočet: {budget} Kč. Maximálně {max_legs} nohou v AKO kombinaci. "
        "ZDROJ KURZŮ JE SX.bet (ne The Odds API) — nabízí víc trhů než jen vítěze "
        "zápasu: vítěz, vítěz setu/třetiny, přes/pod góly, asijský handicap, počet "
        "gamů/setů, poločas. Použij sxbet_client.py (match_winner_markets, "
        "set_winner_markets, active_markets, market_odds, devigged_probs). "
        "Postupuj podle skillu match-probability: zjisti aktuální nabídku zápasů "
        "a kurzů na SX.bet, spočítej náš model z historických dat "
        "(aggregate_stats.py — vítěz/přesné skóre; market_probs.py — rohy, karty, "
        "střely, fauly, SOG, PIM, esa, gemy; player_profile.py — profil hráče), "
        "najdi hodnotové příležitosti (edge modelu proti odmaržovanému trhu) a "
        "postav z nich SÓLO i AKO tikety. "
        "Dodrž pravidla AKO (různé zápasy, kurz = součin). "
        "U trhů, pro které nemáme historické kurzy k backtestu (hokej, většina "
        "tenisu, poločas, třetiny, rohy, karty), buď poctivý, že edge není ověřený. "
        "DŮLEŽITÉ VÝHRADY K MODELU (řekni je uživateli, pokud tiket obsahuje tyto "
        "trhy): PIM (trestné minuty) model systematicky NADHODNOCUJE — na lajně "
        "18.5 dává přes 48 %, ale empiricky je to jen 30 % (nejsou Poissonovsky "
        "rozdělené). Karty jsou taky mírně nadstřelené (model 82 % vs. empiricky "
        "74 % na 2.5). Góly, rohy, střely, SOG, esa naopak sedí dobře. PIM a karty "
        "nikdy nepoužívej jako rovnocenný podklad pro tiket — vždy k nim přidej "
        "výhradu nebo použij empirický sloupec z market_probs.py. "
        "Buď poctivý i o riziku: AKO kombinace v našich backtestech prohrávaly, "
        "nepředstírej jistotu. "
        "Výstup vrať strukturovaně: seznam tiketů (typ, nohy s popisem, kurz, vklad) "
        "a krátké odůvodnění u každé nohy (model % vs. trh %). "
        "Nic nesázej reálně — BOOKMAKER=sxbet_sim, jde jen o návrh tiketů."
    )
    if digest_txt:
        prompt += (
            "\n\n--- TRÉNINK: ŽIVÝ TAPE SX.BET (sázky cizích hráčů, anonymní) ---\n"
            + digest_txt
            + "\n--- konec tréninku. Použij jako kontext (kam teče money), "
              "nepřebírej slepě. ---"
        )
    if poznamka:
        prompt += f" Doplňující požadavek uživatele: {poznamka}"

    result = run_pi(prompt)
    return jsonify(result), (200 if result.get("ok") else 502)


# ---------------------------------------------------------------------------
# /api/agent — obecný dotaz na pi agenta
# ---------------------------------------------------------------------------
@app.post("/api/interrupt")
def interrupt():
    """Přeruší právě běžícího pi agenta (SIGKILL celé procesní skupiny).
    UI tohle volá tlačítkem „Přerušit“. Když nic neběží, vrátí running=false."""
    was_running = agent_running()
    killed = interrupt_agent()
    return jsonify({
        "ok": True,
        "was_running": was_running,
        "killed": killed,
        "pozn": "Agent přerušen." if killed else "Nic neběželo.",
    })


@app.get("/api/status")
def status():
    """Lehký dotaz pro UI — běží právě agent? Nestojí nic (jen RAM)."""
    return jsonify({"ok": True, "agent_running": agent_running()})


@app.post("/api/agent")
def agent():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"ok": False, "error": "potřeba prompt"}), 400
    result = run_pi(prompt, timeout=data.get("timeout"))
    return jsonify(result), (200 if result.get("ok") else 502)


# ---------------------------------------------------------------------------
# /api/run — spuštění whitelistovaných výpočtů a simulací (backtesty, replay…)
# ---------------------------------------------------------------------------
@app.post("/api/run")
def run_script():
    data = request.get_json(silent=True) or {}
    skript = (data.get("skript") or "").strip()
    if skript not in BACKTEST_SCRIPTS:
        return jsonify({"ok": False, "error": f"neznámý skript '{skript}'",
                        "dostupne": sorted(BACKTEST_SCRIPTS)}), 400
    args = data.get("args") or []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return jsonify({"ok": False, "error": "args musí být seznam řetězců"}), 400
    for a in args:
        if a.startswith("/") or ".." in a:
            return jsonify({"ok": False, "error": f"argument '{a}' není povolen"}), 400
    try:
        timeout = int(data.get("timeout", 900))
    except (TypeError, ValueError):
        timeout = 900
    # tape-* aliasy: archiver potřebuje podpříkaz jako první argument
    _TAPE_SUB = {"tape-collect": "collect", "tape-settle": "settle", "tape-report": "report"}
    extra = [_TAPE_SUB[skript]] if skript in _TAPE_SUB and (not args or args[0] not in ("collect", "settle", "report")) else []
    rc, out, err, _ = _run([sys.executable, BACKTEST_SCRIPTS[skript], *extra, *args], timeout=timeout)
    return jsonify({"ok": rc == 0, "rc": rc, "skript": skript, "args": args,
                    "vystup": out[-40000:], "stderr": err[-8000:]})


# ---------------------------------------------------------------------------
# /api/sx/trades — MOJE sázky (V3 váže query endpointy na API klíč)
# ---------------------------------------------------------------------------
@app.get("/api/sx/trades")
def sx_trades_endpoint():
    import sxbet_client as sx
    try:
        dny = min(int(request.args.get("dny", 14)), 3650)
        limit = min(int(request.args.get("limit", 100)), 1000)
    except ValueError:
        dny, limit = 14, 100
    try:
        ts = sx.trades(start_date=int(time.time()) - dny * 86400,
                       page_size=min(limit, 100), max_pages=max(1, limit // 100))
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    out = []
    for t in ts[:limit]:
        out.append({
            "kurz": (lambda o: round(o, 3) if o else None)(sx.trade_decimal_odds(t)),
            "vyhral": sx.trade_won(t),
            "vsazeno_usdc": sx.trade_stake_nominal(t),
            "marketHash": t.get("marketHash"),
            "status": t.get("status"),
            "betTime": t.get("betTime"),
        })
    return jsonify({"ok": True, "zdroj": "sxbet /trades-v3 (jen moje sázky)",
                    "dny": dny, "pocet": len(out), "trades": out})


# ---------------------------------------------------------------------------
# /api/learner/digest — trénink z ŽIVÉHO veřejného tape (sázky cizích hráčů)
# ---------------------------------------------------------------------------
@app.get("/api/learner/digest")
def learner_digest():
    try:
        sekundy = min(int(request.args.get("sekundy", 25)), 120)
        max_trades = min(int(request.args.get("max_trades", 400)), 2000)
    except ValueError:
        return jsonify({"ok": False, "error": "sekundy/max_trades musí být čísla"}), 400
    try:
        import sx_tape
        d = sx_tape.digest(seconds=sekundy, max_trades=max_trades)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify({"ok": True, **d})


# ---------------------------------------------------------------------------
# /api/tape/digest — alias na learner/digest (živý tape cizích sázek)
# ---------------------------------------------------------------------------
@app.get("/api/tape/digest")
def tape_digest():
    return learner_digest()


def main():
    port = int(os.environ.get("SPORTS_PORT", "8000"))
    host = os.environ.get("SPORTS_HOST", "0.0.0.0")
    print(f"statistiky-server: http://{host}:{port}")
    print(f"  scripts: {SCRIPTS_DIR}")
    print(f"  pi:      {PI_BIN}")
    print("  POZOR: bez autentizace, jen pro důvěryhodnou síť.")
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()