#!/usr/bin/env python3
"""
Jednoduchá historie sázkových tiketů (ručně vkládané, mimo NHL/tenis
simulátory) - uklada se do `tiket_historie.jsonl` vedle tohoto skriptu,
stejny bezstavovy vzor jako `live_bets_log.jsonl` u live_tennis_simulator.py.

Pouziti:
    python3 tiket_historie.py add --kurz 78.44 --vklad 200 --typ Maxikombi \
        --skupiny "A:Thompson Tage (Buffalo-Minnesota),B:Kaprizov Kirill (Buffalo-Minnesota),..." \
        --vysledek "4/7" --screenshot /root/share/Screenshot_....jpg --poznamka "..."
    python3 tiket_historie.py list
    python3 tiket_historie.py show <id>
"""
import argparse
import json
import os
import time
import uuid

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(_SCRIPT_DIR, "tiket_historie.jsonl")


def load_all():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append(entry):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def cmd_add(args):
    skupiny = {}
    if args.skupiny:
        for part in args.skupiny.split(","):
            k, _, v = part.partition(":")
            skupiny[k.strip()] = v.strip()

    entry = {
        "id": str(uuid.uuid4())[:8],
        "ts": time.time(),
        "datum": time.strftime("%Y-%m-%d %H:%M"),
        "typ": args.typ,
        "kurz": args.kurz,
        "vklad": args.vklad,
        "skupiny": skupiny,
        "vysledek": args.vysledek,
        "screenshot": args.screenshot,
        "poznamka": args.poznamka,
    }
    append(entry)
    print(f"Ulozeno (id={entry['id']}): {entry['typ']}, kurz {entry['kurz']}, vklad {entry['vklad']} Kc, "
          f"{len(skupiny)} skupin, vysledek {entry['vysledek']}")


def cmd_list(args):
    rows = load_all()
    if not rows:
        print("Historie je prazdna.")
        return
    for r in rows:
        print(f"[{r['id']}] {r['datum']}  {r['typ']:12s} kurz {r['kurz']:>8}  vklad {r['vklad']:>6} Kc  "
              f"{len(r.get('skupiny', {})):2d} skupin  vysledek {r.get('vysledek','?')}")


def cmd_show(args):
    rows = load_all()
    match = next((r for r in rows if r["id"] == args.id), None)
    if not match:
        print(f"Tiket s id {args.id} nenalezen.")
        return
    print(json.dumps(match, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("--typ", default="Maxikombi")
    p_add.add_argument("--kurz", type=float, required=True)
    p_add.add_argument("--vklad", type=float, required=True)
    p_add.add_argument("--skupiny", default="", help="A:popis,B:popis,...")
    p_add.add_argument("--vysledek", default="")
    p_add.add_argument("--screenshot", default="")
    p_add.add_argument("--poznamka", default="")

    sub.add_parser("list")

    p_show = sub.add_parser("show")
    p_show.add_argument("id")

    args = ap.parse_args()
    {"add": cmd_add, "list": cmd_list, "show": cmd_show}[args.cmd](args)


if __name__ == "__main__":
    main()
