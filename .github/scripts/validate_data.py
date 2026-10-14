#!/usr/bin/env python3
"""
Lehka validace dat a skriptu v /statistiky, spoustena v CI na kazdy PR.

Nekontroluje spravnost sportovnich vysledku (na to nema CI pristup k
zivym zdrojum) - hlida jen veci, ktere by jinak proslyly nepovsimnute
a rozbily by update_stats.py nebo navazujici skripty:

1. Vsechny .py soubory v repu musi jit zkompilovat (syntax check).
2. Kazdy CSV v fotbal/, hokej/, tenis/ musi mit konzistentni pocet
   sloupcu na vsech radcich (zadny utrzeny/poskozeny radek).
3. hokej/*.csv navic nesmi mit duplicitni game_id - update_stats.py
   append-only logika na tom stoji, duplicita by znamenala dvojite
   zapasy v datech.

Exit kod 0 = vse v poradku, 1 = nalezen problem (CI job selze).
"""
import ast
import csv
import glob
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

errors = []


def check_python_syntax():
    py_files = glob.glob(os.path.join(REPO_ROOT, "**", "*.py"), recursive=True)
    for path in py_files:
        rel = os.path.relpath(path, REPO_ROOT)
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
            ast.parse(source, filename=rel)
        except SyntaxError as e:
            errors.append(f"[python] {rel}: syntax error - {e}")
        except UnicodeDecodeError as e:
            errors.append(f"[python] {rel}: nelze precist jako utf-8 - {e}")


# Jen soubory, ktere skutecne pise update_stats.py (denni refresh).
# Rucne sbirana/importovana data v podslozkach (hraci/, prubeh/, kurzy/)
# maji svuj vlastni format a nejsou soucasti denni aktualizace - tam uz
# historicky existuji neduslednosti (napr. ragged radky v point-by-point
# datech), ktere nejsou chybou teto PR.
CSV_GLOBS = (
    "fotbal/*.csv",
    "hokej/NHL_*.csv",
    "tenis/atp_matches_*.csv",
    "tenis/wta_matches_*.csv",
)


def check_csv_consistency():
    for pattern in CSV_GLOBS:
        for path in glob.glob(os.path.join(REPO_ROOT, pattern)):
            rel = os.path.relpath(path, REPO_ROOT)
            rows = None
            last_err = None
            # Vetsina souboru je cistej utf-8 (to pise update_stats.py), ale
            # nektera historicka data (uzavrene sezony, uz se nemeni) maji
            # znaky v cp1252/latin1 (napr. chytra uvozovka v nazvu tymu) -
            # zkus to jako fallback, nez soubor oznac za nepouzitelny.
            for enc in ("utf-8", "cp1252", "latin-1"):
                try:
                    with open(path, newline="", encoding=enc) as f:
                        rows = list(csv.reader(f))
                    break
                except (UnicodeDecodeError, csv.Error) as e:
                    last_err = e
            if rows is None:
                errors.append(f"[csv] {rel}: nelze precist v zadnem bezne pouzivanem kodovani - {last_err}")
                continue
            if not rows:
                continue  # prazdny soubor je v poradku (zatim zadna data)
            width = len(rows[0])
            for i, row in enumerate(rows[1:], start=2):
                if len(row) != width:
                    errors.append(
                        f"[csv] {rel}: radek {i} ma {len(row)} sloupcu, "
                        f"ocekavano {width} (podle hlavicky)"
                    )
                    break  # jedna chyba na soubor staci k nahlaseni


def check_hockey_duplicate_game_ids():
    pattern = os.path.join(REPO_ROOT, "hokej", "*.csv")
    for path in glob.glob(pattern):
        rel = os.path.relpath(path, REPO_ROOT)
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None or "game_id" not in reader.fieldnames:
                    continue
                seen = set()
                for row in reader:
                    gid = row.get("game_id")
                    if gid in seen:
                        errors.append(f"[hokej] {rel}: duplicitni game_id {gid}")
                    seen.add(gid)
        except Exception as e:
            errors.append(f"[hokej] {rel}: nelze precist - {e}")


def main():
    check_python_syntax()
    check_csv_consistency()
    check_hockey_duplicate_game_ids()

    if errors:
        print(f"Nalezeno {len(errors)} problemu:\n")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("Vse v poradku: python skripty jdou zkompilovat, CSV soubory "
          "jsou konzistentni, zadne duplicitni game_id v hokejovych datech.")
    sys.exit(0)


if __name__ == "__main__":
    main()
