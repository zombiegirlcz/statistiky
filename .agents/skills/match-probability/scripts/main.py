#!/usr/bin/env python3
"""
main.py — interaktivní TUI pro správu sázejících agentů (match-probability).

Postaveno na InquirerPy (menu, číselné vstupy, potvrzovací dialogy):

  📊  DASHBOARD   — živý přehled (banky agentů, hlavní banka, cron, živé
                    zápasy, poslední tikety). Vykresluje se přes curses.
  💰  HLAVNÍ BANKA — uživatelův rozpočet; odsud se přiděluje agentům.
  🤖  AGENTI      — seznam agentů; u každého lze vložit další částku, vybrat
                    část zpět, zapnout/vypnout, zobrazit tikety, smazat.
  ➕  NOVÝ AGENT  — založí agenta s libovolnou částkou a strategií
                    (match_fav / gem / gem_aggr) z hlavní banky.

Stav agentů a hlavní banky žije v `../agents.json` (modul agents.py = jediný
zdroj pravdy). Součet alokací agentů + volná hlavní banka = celkem; peníze se
jen přesouvají, nevznikají ani nemizí.

Spuštění:
  cd /root/statistiky/.agents/skills/match-probability/scripts
  source /root/.env
  python3 main.py
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
_DATA_DIR = os.path.join(_SCRIPT_DIR, "..")

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from InquirerPy.prompts.list import InquirerPyListControl as _ListControl
from prompt_toolkit.formatted_text import ANSI as _ANSI, to_formatted_text as _to_ft


def A(text):
    """Označí řetězec s ANSI barvami pro InquirerPy.

    InquirerPy sám o sobě buď vykreslí ANSI escape kódy jako doslovné znaky
    ('^[[32m'), nebo při předání objektu ANSI() spadne na .split(). Proto
    vracíme obyčejný řetězec a níže monkey-patchujeme ListPrompt, aby ho
    převedl na fragmenty (skutečné barvy)."""
    return text


def _barevne_fragmenty(text):
    """Převede řetězec s ANSI kódy na fragmenty pro prompt_toolkit."""
    if isinstance(text, str) and "\x1b[" in text:
        return list(_to_ft(_ANSI(text)))
    return [("", text)]


def _lp_normal(self, choice):
    d = [("", len(self._pointer) * " "),
         ("class:marker", self._marker if choice["enabled"] else self._marker_pl)]
    if isinstance(choice["value"], Separator):
        d.append(("class:separator", choice["name"]))
    else:
        d.extend(_barevne_fragmenty(choice["name"]))
    return d


def _lp_hover(self, choice):
    d = [("class:pointer", self._pointer),
         ("class:marker", self._marker if choice["enabled"] else self._marker_pl),
         ("[SetCursorPosition]", "")]
    d.extend(_barevne_fragmenty(choice["name"]))
    return d


# InquirerPy bere choice["name"] a strká ho rovnou do prompt_toolkit, který
# ANSI kódy neumí - přepíšeme obě vykreslovací metody NA KONTROLE (ne na
# promptu - tam metody nejsou, jsou na InquirerPyListControl).
_ListControl._get_normal_text = _lp_normal
_ListControl._get_hover_text = _lp_hover

import agents as reg
import live_tennis_simulator as base
import live_game_bet as gem

MATCH_LOG = base.LOG_PATH
PROGRESS_LOG = base.PROGRESS_PATH
GEM_LOG = gem.LOG_PATH
AGGR_LOG = gem.AGGR_LOG_PATH
RUN_LOG = os.path.join(_SCRIPT_DIR, "run_until_midnight.log")

C = "\033[36m"; G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; D = "\033[90m"; Z = "\033[0m"
B = "\033[1m"


# ---------------------------------------------------------------------------
# Načítání logů / pomocné
# ---------------------------------------------------------------------------
def _load_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except FileNotFoundError:
        pass
    return out


def _bank_from_log(log, strategy):
    """Aktuální banka agenta z jeho logu (stejná logika jako sázecí skripty)."""
    if strategy == "gem_aggr":
        return gem._replay_aggressive(log)["bank"]
    return base.current_bank(log)


def _fmt(x):
    return f"{x:,.0f}".replace(",", " ")


def agent_rows():
    """Vrátí seznam (agent_dict, aktualni_banka, won, lost, pend)."""
    rows = []
    for a in reg.load_registry()["agents"]:
        log = _load_jsonl(reg.log_path(a))
        won = sum(1 for e in log if e.get("status") == "won")
        lost = sum(1 for e in log if e.get("status") == "lost")
        pend = sum(1 for e in log if e.get("status") == "pending")
        rows.append((a, _bank_from_log(log, a["strategy"]), won, lost, pend))
    return rows


def _ago(ts):
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        s = (datetime.now(timezone.utc) - dt).total_seconds()
        if s < 60:
            return f"{int(s)}s"
        if s < 3600:
            return f"{int(s // 60)}m"
        return f"{int(s // 3600)}h{int((s % 3600) // 60)}m"
    except Exception:
        return "?"


def header():
    s = reg.souhrn()
    print()
    print(f"  {B}{C}══════════════════════════════════════════════════════════════{Z}")
    print(f"  {B}{C}  LIVE BETTING — správa agentů{Z}")
    print(f"  {B}{C}══════════════════════════════════════════════════════════════{Z}")
    print(f"  {B}Hlavní banka uživatele:{Z} {G}{_fmt(s['user_bank'])} mincí{Z}")
    print(f"  {D}Alokováno agentům: {_fmt(s['alokovano'])}  ·  "
          f"Celkem (banka + agenti): {_fmt(s['celkem'])}{Z}")
    print()


# ---------------------------------------------------------------------------
# 1) DASHBOARD (curses)
# ---------------------------------------------------------------------------
def dashboard():
    """Živý curses dashboard; q = zpět do menu."""
    import curses

    CT, CO, CW, CD = 1, 2, 3, 4
    REFRESH = 2.0

    def _add(win, y, x, text, attr=0):
        h, w = win.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        try:
            win.addstr(y, x, text[:max(0, w - x - 1)], attr)
        except curses.error:
            pass

    def running_agents():
        vzory = [("executor (cron)", "executor.py"),
                 ("watch", "live_tennis_simulator.py watch"),
                 ("gem tick", "live_game_bet.py tick"),
                 ("gem agresivni", "live_game_bet.py agresivni-tick")]
        try:
            out = subprocess.run(["pgrep", "-af", "python3"],
                                 capture_output=True, text=True, timeout=5).stdout
        except Exception:
            out = ""
        return [(lbl, any(pat in ln for ln in out.splitlines())) for lbl, pat in vzory]

    def live_matches():
        last = {}
        for r in _load_jsonl(PROGRESS_LOG):
            mid = r.get("match_id")
            if mid is None:
                continue
            prev = last.get(mid)
            if prev is None or (r.get("ts") or "") >= (prev.get("ts") or ""):
                last[mid] = r
        out = [r for r in last.values() if not r.get("stale")]
        out.sort(key=lambda r: (r.get("ts") or ""), reverse=True)
        return out

    def recent_bets(limit=12):
        bets = []
        for src, log in [("zápas", _load_jsonl(MATCH_LOG)),
                         ("gem", _load_jsonl(GEM_LOG)),
                         ("AGR", _load_jsonl(AGGR_LOG))]:
            for e in log:
                bets.append((src, e))
        bets.sort(key=lambda t: t[1].get("logged_at") or "", reverse=True)
        return bets[:limit]

    def draw(scr, scroll):
        scr.erase()
        h, w = scr.getmaxyx()
        _add(scr, 0, 0, "  LIVE BETTING DASHBOARD  ·  [q] zpět do menu  ".ljust(w - 1),
             curses.color_pair(CT) | curses.A_BOLD)
        _add(scr, 1, 0, f"  čas: {datetime.now():%Y-%m-%d %H:%M:%S}   auto-refresh {REFRESH:.0f}s",
             curses.color_pair(CD))
        y = 3
        _add(scr, y, 0, "┌─ BANKY AGENTŮ " + "─" * (w - 18), curses.color_pair(CT))
        y += 1
        for a, banka, won, lost, pend in agent_rows():
            strat = reg.STRATEGIE[a["strategy"]]["nazev"].split(":")[0]
            pnl = banka - a["bank"]
            attr = curses.color_pair(CO) if pnl >= 0 else curses.color_pair(CW)
            _add(scr, y, 2,
                 f"{a['id']:<12} {strat:<10} banka {_fmt(banka):>8} "
                 f"(alok {_fmt(a['bank'])}, P/L {pnl:+.0f})  V{won}/P{lost}/~{pend}"
                 + ("" if a["active"] else "  [VYPNUT]"), attr)
            y += 1
        s = reg.souhrn()
        _add(scr, y, 2, f"HL. BANKA uživatele: {_fmt(s['user_bank'])}  "
                        f"(alokováno {_fmt(s['alokovano'])}, celkem {_fmt(s['celkem'])})",
             curses.color_pair(CT))
        y += 2
        _add(scr, y, 0, "┌─ AGENTI & CRON " + "─" * (w - 18), curses.color_pair(CT))
        y += 1
        for lbl, running in running_agents():
            attr = curses.color_pair(CO) if running else curses.color_pair(CD)
            _add(scr, y, 2, f"{lbl:<16} {'● běží' if running else '○ neběží'}", attr)
            y += 1
        try:
            has = "cron_tick.sh" in subprocess.run(["crontab", "-l"], capture_output=True,
                                                   text=True, timeout=5).stdout
        except Exception:
            has = False
        try:
            last = datetime.fromtimestamp(os.path.getmtime(RUN_LOG)).strftime("%H:%M:%S")
        except Exception:
            last = "nikdy"
        _add(scr, y, 2, f"cron_tick.sh: {'naplánován' if has else 'NENÍ'}   poslední log {last}",
             curses.color_pair(CO if has else CW))
        y += 2
        ms = live_matches()
        _add(scr, y, 0, f"┌─ ŽIVÉ ZÁPASY ({len(ms)}) " + "─" * (w - 22), curses.color_pair(CT))
        y += 1
        avail = max(0, h - y - 8)
        for m in ms[scroll:scroll + avail]:
            sets = m.get("sets") or [0, 0]
            games = m.get("games") or [0, 0]
            pts = m.get("points") or ["0", "0"]
            mp = m.get("model_p1")
            mps = f"{mp*100:>3.0f}/{(1-mp)*100:>3.0f}%" if isinstance(mp, (int, float)) else "málo dat"
            _add(scr, y, 2, f"[{m.get('ts','')[11:19]}] {m.get('tournament','?')[:18]:<18} "
                            f"{m.get('player1','?')[:16]:<16} vs {m.get('player2','?')[:16]:<16} "
                            f"{sets[0]}:{sets[1]} {games[0]}:{games[1]} ({pts[0]}:{pts[1]}) model {mps}")
            y += 1
        y += 1
        _add(scr, y, 0, "┌─ POSLEDNÍ TIKETY " + "─" * (w - 20), curses.color_pair(CT))
        y += 1
        for src, e in recent_bets():
            st = e.get("status", "?")
            ic = {"won": "✔", "lost": "✘", "pending": "…", "void": "∅"}.get(st, "?")
            attr = {"won": curses.color_pair(CO), "lost": curses.color_pair(CW)}.get(st, 0)
            _add(scr, y, 2, f"{ic} [{src:<4}] {e.get('logged_at','')[11:19]} "
                            f"{e.get('player1','?')[:14]:<14} vs {e.get('player2','?')[:14]:<14} "
                            f"na {e.get('pick','?')[:16]:<16} @ {e.get('odds',0):<5} "
                            f"vklad {e.get('stake',0):>6.0f} ({_ago(e.get('logged_at'))})", attr)
            y += 1
        _add(scr, h - 1, 0, " [q] zpět  [↑/↓] posun zápasů ".ljust(w - 1), curses.color_pair(CT))
        scr.refresh()

    def run(scr):
        curses.curs_set(0)
        scr.nodelay(True)
        scr.timeout(int(REFRESH * 1000))
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(CT, curses.COLOR_CYAN, -1)
        curses.init_pair(CO, curses.COLOR_GREEN, -1)
        curses.init_pair(CW, curses.COLOR_RED, -1)
        curses.init_pair(CD, curses.COLOR_WHITE, -1)
        scroll = 0
        while True:
            draw(scr, scroll)
            ch = scr.getch()
            if ch in (ord("q"), ord("Q")):
                break
            elif ch == curses.KEY_DOWN:
                scroll += 1
            elif ch == curses.KEY_UP:
                scroll = max(0, scroll - 1)
            elif ch == curses.KEY_NPAGE:
                scroll += 10
            elif ch == curses.KEY_PPAGE:
                scroll = max(0, scroll - 10)

    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# 2) HLAVNÍ BANKA
# ---------------------------------------------------------------------------
def menu_hlavni_banka():
    while True:
        s = reg.souhrn()
        header()
        volba = inquirer.select(
            message="Hlavní banka — co chceš?",
            choices=[
                Choice("vlozit", "➕  Vložit mince do hlavní banky"),
                Choice("vybrat", "➖  Vybrat mince z hlavní banky"),
                Choice("zpet", "←  Zpět do menu"),
            ], qmark="💰").execute()
        if volba == "zpet":
            return
        if volba == "vlozit":
            castka = inquirer.number(message="Kolik mincí vložit?",
                                     min_allowed=1, float_allowed=False).execute()
            if castka:
                r = reg.load_registry()
                r["user_bank"] += float(castka)
                reg.save_registry(r)
                print(f"  {G}✔ Vloženo {_fmt(float(castka))} mincí do hlavní banky.{Z}")
                time.sleep(1)
        elif volba == "vybrat":
            if s["user_bank"] <= 0:
                print(f"  {Y}Hlavní banka je prázdná.{Z}")
                time.sleep(1)
                continue
            castka = inquirer.number(message="Kolik mincí vybrat?",
                                     min_allowed=1, max_allowed=int(s["user_bank"]),
                                     float_allowed=False).execute()
            if castka:
                r = reg.load_registry()
                r["user_bank"] -= float(castka)
                reg.save_registry(r)
                print(f"  {G}✔ Vybráno {_fmt(float(castka))} mincí z hlavní banky.{Z}")
                time.sleep(1)


# ---------------------------------------------------------------------------
# 3) AGENTI
# ---------------------------------------------------------------------------
def menu_agenti():
    rows = agent_rows()
    if not rows:
        print(f"  {Y}Žádní agenti.{Z}")
        time.sleep(1)
        return

    choices = []
    for a, banka, won, lost, pend in rows:
        strat = reg.STRATEGIE[a["strategy"]]["nazev"].split(":")[0]
        pnl = banka - a["bank"]
        barva = G if pnl >= 0 else R
        popis = (f"{a['id']:<12} {strat:<10} banka {barva}{_fmt(banka):>8}{Z} "
                 f"(alok {_fmt(a['bank'])}, {barva}{pnl:+.0f}{Z}) V{won}/P{lost}/~{pend}"
                 + ("" if a["active"] else f" {Y}[VYPNUT]{Z}"))
        choices.append(Choice(a["id"], A(popis)))
    choices.append(Separator())
    choices.append(Choice("__zpet__", "←  Zpět do menu"))

    aid = inquirer.select(message="Vyber agenta:", choices=choices, qmark="🤖").execute()
    if aid == "__zpet__":
        return
    agent_menu(aid)


def agent_menu(aid):
    while True:
        r = reg.load_registry()
        a = next((x for x in r["agents"] if x["id"] == aid), None)
        if a is None:
            print(f"  {R}Agent {aid} už neexistuje.{Z}")
            time.sleep(1)
            return
        log = _load_jsonl(reg.log_path(a))
        banka = _bank_from_log(log, a["strategy"])
        won = sum(1 for e in log if e.get("status") == "won")
        lost = sum(1 for e in log if e.get("status") == "lost")
        pend = sum(1 for e in log if e.get("status") == "pending")

        header()
        strat = reg.STRATEGIE[a["strategy"]]["nazev"]
        print(f"  {B}Agent:{Z} {a['name']}  {D}({a['id']}){Z}")
        print(f"  Strategie: {strat}")
        print(f"  Alokováno: {_fmt(a['bank'])} mincí   ·   Aktuální banka z logu: "
              f"{G if banka >= a['bank'] else R}{_fmt(banka)}{Z}")
        print(f"  Tikety: V{won} / P{lost} / ~{pend}   ·   stav: "
              f"{'aktivní' if a['active'] else Y + 'VYPNUT' + Z}")
        print()

        volba = inquirer.select(
            message="Co s agentem?",
            choices=[
                Choice("fund", "➕  Vložit libovolnou částku do agenta (z hlavní banky)"),
                Choice("defund", "➖  Vybrat částku zpět do hlavní banky"),
                Choice("toggle", f"⏻  {'Vypnout' if a['active'] else 'Zapnout'} agenta"),
                Choice("config", "⚙️  Nastavit parametry strategie"),
                Choice("bets", "📜  Zobrazit poslední tikety agenta"),
                Choice("delete", "🗑  Smazat agenta (zbytek zpět do hlavní banky)"),
                Choice("zpet", "←  Zpět"),
            ], qmark="🤖").execute()

        if volba == "zpet":
            return
        elif volba == "fund":
            s = reg.souhrn()
            if s["user_bank"] <= 0:
                print(f"  {Y}Hlavní banka je prázdná — nejdřív do ní vlož.{Z}")
                time.sleep(1.2)
                continue
            castka = inquirer.number(
                message=f"Kolik mincí vložit agentovi {a['id']}? (v hlavní bance {_fmt(s['user_bank'])})",
                min_allowed=1, max_allowed=int(s["user_bank"]), float_allowed=False).execute()
            if castka:
                try:
                    reg.fund_agent(aid, float(castka))
                    print(f"  {G}✔ Přidáno {_fmt(float(castka))} mincí agentovi {aid}.{Z}")
                except ValueError as e:
                    print(f"  {R}✘ {e}{Z}")
                time.sleep(1)
        elif volba == "defund":
            if a["bank"] <= 0:
                print(f"  {Y}Agent nemá co vrátit.{Z}")
                time.sleep(1)
                continue
            castka = inquirer.number(
                message=f"Kolik mincí vybrat agentovi {a['id']}? (alokováno {_fmt(a['bank'])})",
                min_allowed=1, max_allowed=int(a["bank"]), float_allowed=False).execute()
            if castka:
                try:
                    reg.defund_agent(aid, float(castka))
                    print(f"  {G}✔ Vybráno {_fmt(float(castka))} mincí zpět do hlavní banky.{Z}")
                except ValueError as e:
                    print(f"  {R}✘ {e}{Z}")
                time.sleep(1)
        elif volba == "toggle":
            reg.set_active(aid, not a["active"])
            print(f"  {G}✔ Agent {aid} {'zapnut' if not a['active'] else 'vypnut'}.{Z}")
            time.sleep(1)
        elif volba == "config":
            menu_config(aid)
        elif volba == "bets":
            _vypis_tikety(log)
        elif volba == "delete":
            if inquirer.confirm(
                    message=f"Smazat agenta {a['id']}? Zbylých {_fmt(a['bank'])} mincí se vrátí do hlavní banky.",
                    default=False).execute():
                reg.remove_agent(aid, vratit=True)
                print(f"  {G}✔ Agent {aid} smazán.{Z}")
                time.sleep(1)
                return


def menu_config(aid):
    """Interaktivní editor laditelných parametrů agenta."""
    while True:
        r = reg.load_registry()
        a = next((x for x in r["agents"] if x["id"] == aid), None)
        if a is None:
            return
        cfg = reg.effective_config(a)
        meta = reg.STRATEGIE[a["strategy"]]["popisky"]
        defaults = reg.STRATEGIE[a["strategy"]]["defaults"]

        header()
        print(f"  {B}Parametry agenta {a['id']}{Z}  "
              f"{D}(strategie {a['strategy']}){Z}\n")
        choices = []
        for klic, hodnota in cfg.items():
            popis, lo, hi, poznamka = meta[klic]
            zmeneno = a.get("config", {}).get(klic) is not None
            znak = f"{Y}*{Z}" if zmeneno else " "
            choices.append(Choice(
                klic,
                A(f"{znak} {popis:<42} {G}{hodnota}{Z}  {D}(default {defaults[klic]}) {poznamka}{Z}")))
        choices.append(Separator())
        choices.append(Choice("__reset__", "↺  Vrátit vše na výchozí hodnoty strategie"))
        choices.append(Choice("__zpet__", "←  Zpět"))

        volba = inquirer.select(message="Který parametr upravit?", choices=choices, qmark="⚙️").execute()
        if volba == "__zpet__":
            return
        if volba == "__reset__":
            reg.reset_config(aid)
            print(f"  {G}✔ Parametry vráceny na výchozí.{Z}")
            time.sleep(1)
            continue

        popis, lo, hi, poznamka = meta[volba]
        nova = inquirer.number(
            message=f"{popis} (rozsah {lo}–{hi}):",
            default=float(cfg[volba]), min_allowed=lo, max_allowed=hi,
            float_allowed=True).execute()
        if nova is not None:
            reg.set_config(aid, volba, float(nova))
            print(f"  {G}✔ {volba} = {nova}{Z}")
            time.sleep(1)


def _vypis_tikety(log, limit=20):
    header()
    print(f"  {B}Posledních {min(limit, len(log))} tiketů:{Z}\n")
    for e in log[-limit:]:
        st = e.get("status", "?")
        ic = {"won": f"{G}✔{Z}", "lost": f"{R}✘{Z}", "pending": "…", "void": "∅"}.get(st, "?")
        print(f"   {ic} {e.get('logged_at','')[11:19]} "
              f"{e.get('player1','?')[:20]:<20} vs {e.get('player2','?')[:20]:<20} "
              f"na {e.get('pick','?')[:20]:<20} @ {e.get('odds',0):<5} "
              f"vklad {e.get('stake',0):>6.0f}  ({st})")
    print()
    inquirer.text(message="Enter pro pokračování", default="").execute()


# ---------------------------------------------------------------------------
# 4) NOVÝ AGENT
# ---------------------------------------------------------------------------
def menu_novy_agent():
    s = reg.souhrn()
    header()
    if s["user_bank"] < 10:
        print(f"  {Y}V hlavní bance není dost mincí (min. 10).{Z}")
        time.sleep(1.5)
        return

    jmeno = inquirer.text(message="Jméno nového agenta:", default="").execute().strip()
    if not jmeno:
        print(f"  {Y}Zrušeno — prázdné jméno.{Z}")
        time.sleep(1)
        return

    strategie = inquirer.select(
        message="Strategie:",
        choices=[Choice(k, A(f"{v['nazev']}  {D}[{k}]{Z}")) for k, v in reg.STRATEGIE.items()],
        qmark="🎯").execute()

    castka = inquirer.number(
        message=f"Počáteční částka pro agenta (z hlavní banky {_fmt(s['user_bank'])}):",
        min_allowed=1, max_allowed=int(s["user_bank"]), float_allowed=False).execute()
    if not castka:
        print(f"  {Y}Zrušeno.{Z}")
        time.sleep(1)
        return

    try:
        aid = reg.add_agent(jmeno, strategie, float(castka))
    except ValueError as e:
        print(f"  {R}✘ {e}{Z}")
        time.sleep(1.5)
        return

    print(f"  {G}✔ Agent '{jmeno}' ({aid}) založen se strategií {strategie} "
          f"a částkou {_fmt(float(castka))} mincí.{Z}")
    time.sleep(1.5)


# ---------------------------------------------------------------------------
# HLAVNÍ MENU
# ---------------------------------------------------------------------------
def hlavni_menu():
    while True:
        header()
        volba = inquirer.select(
            message="Co chceš dělat?",
            choices=[
                Choice("dash", "📊  Dashboard (živý přehled)"),
                Choice("banka", "💰  Hlavní banka uživatele"),
                Choice("agenti", "🤖  Agenti (vložit/vybrat částku, správa)"),
                Choice("novy", "➕  Založit nového agenta"),
                Separator(),
                Choice("konec", "👋  Konec"),
            ], qmark="🎲").execute()

        if volba == "dash":
            dashboard()
        elif volba == "banka":
            menu_hlavni_banka()
        elif volba == "agenti":
            menu_agenti()
        elif volba == "novy":
            menu_novy_agent()
        elif volba == "konec":
            print(f"\n  {C}Ahoj!{Z}\n")
            return


if __name__ == "__main__":
    try:
        hlavni_menu()
    except KeyboardInterrupt:
        print("\n  Přerušeno.")