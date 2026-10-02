#!/usr/bin/env python3
"""
cli.py — komplexní CLI nástroj pro správu tenisového sázejícího agenta.

Příkazy:
  agent         — správa agentů (list, create, fund, defund, toggle, remove)
  bank          — správa hlavní banky (deposit, withdraw, status)
  run           — spustit sázkový cyklus (watch + vyhodnotit)
  upcoming      — zobrazit nadcházející zápasy a predikce
  results       — zobrazit výsledky a statistiku tiketů
  status        — přehled banky, agentů a nedávných tiketů
  tui           — spustit interaktivní TUI (main.py)

Příklad:
  python3 cli.py status
  python3 cli.py agent list
  python3 cli.py agent create "Nový agent" match_fav 500
  python3 cli.py bank deposit 1000
  python3 cli.py run --agent match-fav
  python3 cli.py upcoming --sport tenis
  python3 cli.py results --limit 10
  python3 cli.py tui
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
_DATA_DIR = os.path.join(_SCRIPT_DIR, "..")

import agents as reg
import live_tennis_simulator as sim
import bet_evaluator as ev
import executor

C = "\033[36m"; G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; D = "\033[90m"; Z = "\033[0m"
B = "\033[1m"


# ============================================================================
# BANK COMMANDS
# ============================================================================
def cmd_bank_status(args):
    """Zobrazit stav hlavní banky a alokace agentů."""
    s = reg.souhrn()
    print(f"\n{B}💰 STAV BANKY{Z}")
    print(f"  Hlavní banka:        {G}{s['user_bank']:>10.2f}{Z} mincí")
    print(f"  Alokováno agentům:   {C}{s['alokovano']:>10.2f}{Z} mincí ({s['n_agentu']} agentů)")
    print(f"  {B}Celkem:{Z}              {B}{s['celkem']:>10.2f}{Z} mincí\n")


def cmd_bank_deposit(args):
    """Vložit mince do hlavní banky."""
    if args.amount <= 0:
        print(f"{R}Chyba: Částka musí být kladná.{Z}")
        return 1
    try:
        r = reg.load_registry()
        r["user_bank"] += float(args.amount)
        reg.save_registry(r)
        print(f"{G}✔ Vloženo {args.amount:.2f} mincí do hlavní banky.{Z}")
        cmd_bank_status(args)
        return 0
    except Exception as e:
        print(f"{R}Chyba: {e}{Z}")
        return 1


def cmd_bank_withdraw(args):
    """Vybrat mince z hlavní banky."""
    if args.amount <= 0:
        print(f"{R}Chyba: Částka musí být kladná.{Z}")
        return 1
    try:
        r = reg.load_registry()
        if args.amount > r["user_bank"] + 1e-9:
            print(f"{R}Chyba: V hlavní bance není dost. Máte: {r['user_bank']:.2f}{Z}")
            return 1
        r["user_bank"] -= float(args.amount)
        reg.save_registry(r)
        print(f"{G}✔ Vybráno {args.amount:.2f} mincí z hlavní banky.{Z}")
        cmd_bank_status(args)
        return 0
    except Exception as e:
        print(f"{R}Chyba: {e}{Z}")
        return 1


# ============================================================================
# AGENT COMMANDS
# ============================================================================
def cmd_agent_list(args):
    """Zobrazit seznam všech agentů."""
    r = reg.load_registry()
    if not r["agents"]:
        print(f"{Y}Žádní agenti. Vytvořte nového: cli.py agent create ...{Z}")
        return 0

    print(f"\n{B}🤖 SEZNAM AGENTŮ{Z}\n")
    print(f"  {'ID':<14} {'Jméno':<24} {'Strategie':<12} {'Banka':<10} {'Status':<8}")
    print("  " + "─" * 68)
    for a in r["agents"]:
        status = f"{G}aktivní{Z}" if a.get("active") else f"{Y}vypnuto{Z}"
        print(f"  {a['id']:<14} {a['name']:<24} {a['strategy']:<12} {a['bank']:>9.0f}  {status}")
    print()


def cmd_agent_create(args):
    """Vytvořit nového agenta."""
    if args.amount <= 0:
        print(f"{R}Chyba: Částka musí být kladná.{Z}")
        return 1
    if args.strategy not in reg.STRATEGIE:
        strats = ", ".join(sorted(reg.STRATEGIE.keys()))
        print(f"{R}Chyba: Neznámá strategie. Dostupné: {strats}{Z}")
        return 1

    try:
        aid = reg.add_agent(args.name, args.strategy, args.amount)
        print(f"{G}✔ Vytvořen agent '{aid}' ({args.name}) se strategií {args.strategy}{Z}")
        print(f"  Alokováno: {args.amount:.2f} mincí")
        return 0
    except Exception as e:
        print(f"{R}Chyba: {e}{Z}")
        return 1


def cmd_agent_fund(args):
    """Přidat mince agentovi z hlavní banky."""
    if args.amount <= 0:
        print(f"{R}Chyba: Částka musí být kladná.{Z}")
        return 1
    try:
        reg.fund_agent(args.aid, args.amount)
        a = reg.load_registry()["agents"]
        agent = next((x for x in a if x["id"] == args.aid), None)
        if agent:
            print(f"{G}✔ Vloženo {args.amount:.2f} mincí agentovi {args.aid}{Z}")
            print(f"  Nová alokace: {agent['bank']:.0f} mincí")
        return 0
    except Exception as e:
        print(f"{R}Chyba: {e}{Z}")
        return 1


def cmd_agent_defund(args):
    """Vybrat mince od agenta zpět do hlavní banky."""
    if args.amount <= 0:
        print(f"{R}Chyba: Částka musí být kladná.{Z}")
        return 1
    try:
        reg.defund_agent(args.aid, args.amount)
        a = reg.load_registry()["agents"]
        agent = next((x for x in a if x["id"] == args.aid), None)
        if agent:
            print(f"{G}✔ Vybráno {args.amount:.2f} mincí od agenta {args.aid}{Z}")
            print(f"  Zbývající alokace: {agent['bank']:.0f} mincí")
        return 0
    except Exception as e:
        print(f"{R}Chyba: {e}{Z}")
        return 1


def cmd_agent_toggle(args):
    """Zapnout/vypnout agenta."""
    try:
        r = reg.load_registry()
        agent = next((x for x in r["agents"] if x["id"] == args.aid), None)
        if not agent:
            print(f"{R}Chyba: Agent '{args.aid}' neexistuje.{Z}")
            return 1

        new_state = not agent.get("active", True)
        reg.set_active(args.aid, new_state)
        state_str = f"{G}aktivní{Z}" if new_state else f"{Y}vypnuto{Z}"
        print(f"{G}✔ Agent '{args.aid}' je nyní {state_str}.")
        return 0
    except Exception as e:
        print(f"{R}Chyba: {e}{Z}")
        return 1


def cmd_agent_remove(args):
    """Odstranit agenta (vrátit jeho alokaci do hlavní banky)."""
    try:
        r = reg.load_registry()
        agent = next((x for x in r["agents"] if x["id"] == args.aid), None)
        if not agent:
            print(f"{R}Chyba: Agent '{args.aid}' neexistuje.{Z}")
            return 1

        if not args.force:
            print(f"{Y}Opravdu smazat agenta '{args.aid}'? ({agent['bank']:.0f} mincí bude vráceno do hlavní banky){Z}")
            response = input("Potvrdit (ano/ne): ").strip().lower()
            if response not in ["ano", "yes", "y"]:
                print(f"{Y}Zrušeno.{Z}")
                return 0

        reg.remove_agent(args.aid, vratit=True)
        print(f"{G}✔ Agent '{args.aid}' byl smazán a jeho banka vrácena.{Z}")
        return 0
    except Exception as e:
        print(f"{R}Chyba: {e}{Z}")
        return 1


# ============================================================================
# RUN COMMANDS
# ============================================================================
def cmd_run(args):
    """Spustit sázkový cyklus (watch + vyhodnotit)."""
    try:
        if args.agent:
            print(f"{C}▶ Spouštím agenta '{args.agent}'...{Z}")
            exit_code = executor.run_all(only=args.agent)
        else:
            print(f"{C}▶ Spouštím všechny aktivní agenty...{Z}")
            exit_code = executor.run_all()
        return exit_code
    except Exception as e:
        print(f"{R}Chyba: {e}{Z}")
        return 1


# ============================================================================
# STATUS COMMAND
# ============================================================================
def cmd_status(args):
    """Zobrazit celkový přehled stavu banky, agentů a nedávných tiketů."""
    # Banka
    cmd_bank_status(args)

    # Agenti
    cmd_agent_list(args)

    # Nedávné tikety
    print(f"{B}📋 NEDÁVNÉ TIKETY (posledních 5){Z}\n")
    try:
        r = reg.load_registry()
        all_tickets = []

        for agent in r["agents"]:
            log_path = reg.log_path(agent)
            if os.path.exists(log_path):
                try:
                    with open(log_path) as f:
                        for line in f:
                            try:
                                ticket = json.loads(line)
                                ticket["_agent_id"] = agent["id"]
                                all_tickets.append(ticket)
                            except json.JSONDecodeError:
                                pass
                except Exception:
                    pass

        # Seřadit podle času
        all_tickets.sort(key=lambda t: t.get("created_at", ""), reverse=True)

        if not all_tickets:
            print(f"  {D}Žádné tikety.{Z}\n")
        else:
            for ticket in all_tickets[:5]:
                created = ticket.get("created_at", "?")
                status = ticket.get("status", "?")
                player_1 = ticket.get("player_1", "?")
                player_2 = ticket.get("player_2", "?")
                odds = ticket.get("odds", 0)
                stake = ticket.get("stake", 0)
                agent_id = ticket.get("_agent_id", "?")

                status_color = G if status == "won" else (R if status == "lost" else Y)
                print(f"  {created} {agent_id:<12} {player_1} vs {player_2}")
                print(f"    Status: {status_color}{status}{Z} | Kurz: {odds:.2f} | Vklad: {stake:.0f}")
    except Exception as e:
        print(f"  {D}Chyba při načítání tiketů: {e}{Z}")

    print()


# ============================================================================
# UPCOMING COMMAND
# ============================================================================
def cmd_upcoming(args):
    """Zobrazit nadcházející zápasy (jen info, bez sázení)."""
    print(f"\n{B}📅 NADCHÁZEJÍCÍ ZÁPASY{Z}\n")
    print(f"{Y}Tato funkce zatím není plně implementována.{Z}")
    print(f"Zápasy se načítají v {C}live_tennis_simulator.py watch{Z} během běhu agenta.\n")
    return 0


# ============================================================================
# RESULTS COMMAND
# ============================================================================
def cmd_results(args):
    """Zobrazit výsledky tiketů a statistiku."""
    print(f"\n{B}📊 VÝSLEDKY TIKETŮ{Z}\n")

    limit = args.limit or 20
    total_tickets = 0
    won_tickets = 0
    lost_tickets = 0
    total_stake = 0
    total_win = 0

    try:
        r = reg.load_registry()
        all_tickets = []

        for agent in r["agents"]:
            log_path = reg.log_path(agent)
            if os.path.exists(log_path):
                try:
                    with open(log_path) as f:
                        for line in f:
                            try:
                                ticket = json.loads(line)
                                ticket["_agent_id"] = agent["id"]
                                all_tickets.append(ticket)
                            except json.JSONDecodeError:
                                pass
                except Exception:
                    pass

        # Seřadit podle času (novější první)
        all_tickets.sort(key=lambda t: t.get("created_at", ""), reverse=True)

        # Limitovat na požadovaný počet
        for ticket in all_tickets[:limit]:
            created = ticket.get("created_at", "?")
            status = ticket.get("status", "?")
            player_1 = ticket.get("player_1", "?")
            player_2 = ticket.get("player_2", "?")
            odds = ticket.get("odds", 0)
            stake = ticket.get("stake", 0)
            agent_id = ticket.get("_agent_id", "?")

            status_color = G if status == "won" else (R if status == "lost" else Y)
            print(f"  {created} {agent_id:<12} {player_1} vs {player_2}")
            print(f"    Status: {status_color}{status}{Z} | Kurz: {odds:.2f} | Vklad: {stake:.0f}")

            if status == "won":
                won_tickets += 1
            elif status == "lost":
                lost_tickets += 1
            total_stake += stake
            total_tickets += 1

        # Statistika
        print(f"\n{B}Statistika:{Z}")
        print(f"  Tiketů zobrazeno: {total_tickets}")
        print(f"  Vítězů: {G}{won_tickets}{Z}, Proher: {R}{lost_tickets}{Z}")
        print(f"  Celkový vklad: {total_stake:.0f} mincí")
        if total_tickets > 0:
            win_rate = (won_tickets / total_tickets) * 100
            print(f"  Procento výher: {win_rate:.1f}%")
        print()

    except Exception as e:
        print(f"  {R}Chyba: {e}{Z}\n")

    return 0


# ============================================================================
# TUI COMMAND
# ============================================================================
def cmd_tui(args):
    """Spustit interaktivní TUI (main.py)."""
    try:
        subprocess.run([sys.executable, "main.py"], check=True)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"{R}Chyba: TUI skončil s chybou ({e.returncode}){Z}")
        return e.returncode
    except Exception as e:
        print(f"{R}Chyba: {e}{Z}")
        return 1


# ============================================================================
# MAIN
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Komplexní CLI pro správu tenisového sázejícího agenta",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Příklady:
  %(prog)s status                              — zobrazit přehled
  %(prog)s agent list                          — seznam agentů
  %(prog)s agent create "Nový" match_fav 500   — vytvořit agenta
  %(prog)s bank deposit 1000                   — vložit do banky
  %(prog)s run --agent match-fav               — spustit agenta
  %(prog)s results --limit 10                  — posledních 10 tiketů
  %(prog)s tui                                 — spustit interaktivní menu
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Příkazy")

    # ========== BANK ==========
    bank_parser = subparsers.add_parser("bank", help="Správa hlavní banky")
    bank_sub = bank_parser.add_subparsers(dest="bank_cmd")

    bank_sub.add_parser("status", help="Zobrazit stav banky")

    bank_deposit = bank_sub.add_parser("deposit", help="Vložit mince")
    bank_deposit.add_argument("amount", type=float, help="Částka k vložení")

    bank_withdraw = bank_sub.add_parser("withdraw", help="Vybrat mince")
    bank_withdraw.add_argument("amount", type=float, help="Částka k vzetí")

    # ========== AGENT ==========
    agent_parser = subparsers.add_parser("agent", help="Správa agentů")
    agent_sub = agent_parser.add_subparsers(dest="agent_cmd")

    agent_sub.add_parser("list", help="Zobrazit seznam agentů")

    agent_create = agent_sub.add_parser("create", help="Vytvořit nového agenta")
    agent_create.add_argument("name", help="Jméno agenta")
    agent_create.add_argument("strategy", help="Strategie (match_fav/gem/gem_aggr)")
    agent_create.add_argument("amount", type=float, help="Počáteční alokace (mincí)")

    agent_fund = agent_sub.add_parser("fund", help="Přidat mince agentovi")
    agent_fund.add_argument("aid", help="ID agenta")
    agent_fund.add_argument("amount", type=float, help="Částka k přidání")

    agent_defund = agent_sub.add_parser("defund", help="Vybrat mince od agenta")
    agent_defund.add_argument("aid", help="ID agenta")
    agent_defund.add_argument("amount", type=float, help="Částka k vzetí")

    agent_toggle = agent_sub.add_parser("toggle", help="Zapnout/vypnout agenta")
    agent_toggle.add_argument("aid", help="ID agenta")

    agent_remove = agent_sub.add_parser("remove", help="Smazat agenta")
    agent_remove.add_argument("aid", help="ID agenta")
    agent_remove.add_argument("--force", action="store_true", help="Nepotvrzovat smazání")

    # ========== RUN ==========
    run_parser = subparsers.add_parser("run", help="Spustit sázkový cyklus")
    run_parser.add_argument("--agent", help="Spustit jen konkrétního agenta (ID)")

    # ========== STATUS ==========
    subparsers.add_parser("status", help="Celkový přehled")

    # ========== UPCOMING ==========
    subparsers.add_parser("upcoming", help="Nadcházející zápasy")

    # ========== RESULTS ==========
    results_parser = subparsers.add_parser("results", help="Výsledky tiketů")
    results_parser.add_argument("--limit", type=int, default=20, help="Počet tiketů (default: 20)")

    # ========== TUI ==========
    subparsers.add_parser("tui", help="Spustit interaktivní menu")

    args = parser.parse_args()

    # Dispatch
    if args.command == "bank":
        if args.bank_cmd == "status":
            return cmd_bank_status(args)
        elif args.bank_cmd == "deposit":
            return cmd_bank_deposit(args)
        elif args.bank_cmd == "withdraw":
            return cmd_bank_withdraw(args)
        else:
            bank_parser.print_help()
            return 0

    elif args.command == "agent":
        if args.agent_cmd == "list":
            return cmd_agent_list(args)
        elif args.agent_cmd == "create":
            return cmd_agent_create(args)
        elif args.agent_cmd == "fund":
            return cmd_agent_fund(args)
        elif args.agent_cmd == "defund":
            return cmd_agent_defund(args)
        elif args.agent_cmd == "toggle":
            return cmd_agent_toggle(args)
        elif args.agent_cmd == "remove":
            return cmd_agent_remove(args)
        else:
            agent_parser.print_help()
            return 0

    elif args.command == "run":
        return cmd_run(args)

    elif args.command == "status":
        return cmd_status(args)

    elif args.command == "upcoming":
        return cmd_upcoming(args)

    elif args.command == "results":
        return cmd_results(args)

    elif args.command == "tui":
        return cmd_tui(args)

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
