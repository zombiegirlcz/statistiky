#!/usr/bin/env python3
"""
Stahne historicke SAZKOVE KURZY pro zenskou tenisovou turu (WTA) a ulozi je
do tenis/kurzy/wta_kurzy.csv.

PROC TOHLE EXISTUJE
-------------------
Fotbalova data v /statistiky (fotbal/*.csv) obsahuji i skutecne historicke
kurzy (sloupce Avg*), takze u fotbalu se dalo poctive otestovat, jestli nas
model dokaze porazit trh (vysledek: nedokaze, viz references/metodika.md).

Tenisova data od Jeffa Sackmanna (tenis/*.csv) ale ZADNE kurzy neobsahuji -
maji jen statistiky zapasu. Bez kurzu nelze zmerit, jestli ma model sazkovou
VYHODU (edge), jen jestli spravne tipuje viteze. To jsou dve naprosto jine
otazky: model s 70% uspesnosti tipovani muze byt silne ztratovy, pokud trh
oceni favority jeste presneji - presne to se stalo u fotbalu.

ZDROJ A JEHO PUVOD
------------------
Primarni zdroj kurzu je http://www.tennis-data.co.uk (volne dostupne historicke
kurzy ATP i WTA od roku 2000). Ten je ale za Cloudflare, ktery blokuje pristup
z datovych center - z tohoto kontejneru se stahnout neda. Pouzivame proto
mirror na Hugging Face, ktery data prebira (tennis-data.co.uk -> Kaggle
"WTA Tennis 2007-2023 Daily Update" -> HF):

    https://huggingface.co/datasets/Nevoreuven/tennis-betting-odds-model

Mirror realne pokryva 2007 az listopad 2025 (navzdory nazvu "2007-2023").

POZOR NA LICENCI: tennis-data.co.uk poskytuje data pro osobni, nekomercni
pouziti. Mirror na HF nema vlastni explicitni licenci. Pro osobni analyzu
a papirove testovani je to v poradu; pro komercni nasazeni je potreba si
licenci vyresit u primarniho zdroje.

ROZSAH: jen WTA. Pro ATP se stejny mirror nenasel - kdo chce otestovat i
muzskou turu, musi stahnout ATP soubory primo z tennis-data.co.uk ze site,
ktera neni blokovana (bezny domaci internet/telefon projde), a ulozit je
sem jako tenis/kurzy/atp_kurzy.csv se stejnymi sloupci.

CO SE UKLADA
------------
Jen roky 2021-2025, tedy presne prunik s tim, co mame v tenis/*.csv (puvodni
soubor ma 43 tisic radku od 2007, z nichz vetsina je k nicemu, protoze k nim
nemame zapasove statistiky). Sloupce:

    Date, Tournament, Surface, Round, Best of, Player_1, Player_2, Winner,
    Rank_1, Rank_2, Odd_1, Odd_2, Score

Odd_1/Odd_2 jsou predzapasove kurzy na Player_1/Player_2 (desetinny format,
tj. 1.50 = vklad 100 vrati 150). Winner je jmeno skutecneho viteze.

DULEZITE: Player_1 NENI vzdy favorit ani vitez - poradi je dane zdrojem, ne
vysledkem. To je dobre, protoze to znamena, ze v datech neni skryty unik
informace o vysledku (stejna past, na kterou jsme narazili u tenisovych
dvojchyb, viz metodika.md).

Pouziti:
    python3 fetch_tennis_odds.py            # stahne a ulozi
    python3 fetch_tennis_odds.py --info     # jen ukaze, co uz je ulozene
"""
import csv
import os
import sys
import urllib.request

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
OUT_DIR = os.path.join(BASE, "tenis", "kurzy")
OUT_PATH = os.path.join(OUT_DIR, "wta_kurzy.csv")

SRC_URL = (
    "https://huggingface.co/datasets/Nevoreuven/tennis-betting-odds-model/"
    "resolve/main/wta%20(1).csv"
)

YEAR_FROM, YEAR_TO = "2021", "2025"

COLUMNS = [
    "Date", "Tournament", "Surface", "Round", "Best of",
    "Player_1", "Player_2", "Winner", "Rank_1", "Rank_2",
    "Odd_1", "Odd_2", "Score",
]


def show_info():
    if not os.path.exists(OUT_PATH):
        print("Zadne kurzy jeste ulozene nejsou (%s chybi)." % OUT_PATH)
        print("Spust bez parametru: python3 fetch_tennis_odds.py")
        return
    with open(OUT_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    years = sorted({r["Date"][:4] for r in rows})
    print("Ulozeno: %s" % OUT_PATH)
    print("Zapasu s kurzy: %d" % len(rows))
    print("Roky: %s" % ", ".join("%s (%d)" % (y, sum(1 for r in rows if r["Date"][:4] == y)) for y in years))


def main():
    if "--info" in sys.argv:
        show_info()
        return

    print("Stahuji kurzy z mirroru na Hugging Face...")
    try:
        with urllib.request.urlopen(SRC_URL, timeout=300) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print("CHYBA: stazeni se nepovedlo: %s" % exc)
        print("\nPrimarni zdroj http://www.tennis-data.co.uk je za Cloudflare a z")
        print("datoveho centra ho stahnout nejde. Pokud je mirror nedostupny,")
        print("stahni soubory rucne z bezne site a uloz je jako")
        print("  %s" % OUT_PATH)
        print("se sloupci: %s" % ", ".join(COLUMNS))
        sys.exit(1)

    reader = csv.DictReader(raw.splitlines())
    kept = []
    skipped_no_odds = 0
    for row in reader:
        date = (row.get("Date") or "")[:10]
        if not (YEAR_FROM <= date[:4] <= YEAR_TO):
            continue
        if not row.get("Odd_1") or not row.get("Odd_2"):
            skipped_no_odds += 1
            continue
        try:
            if float(row["Odd_1"]) <= 1.0 or float(row["Odd_2"]) <= 1.0:
                skipped_no_odds += 1
                continue
        except ValueError:
            skipped_no_odds += 1
            continue
        kept.append({c: (date if c == "Date" else (row.get(c) or "")) for c in COLUMNS})

    kept.sort(key=lambda r: (r["Date"], r["Tournament"], r["Player_1"]))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(kept)

    print("Ulozeno %d zapasu s kurzy (%s-%s) do %s" % (len(kept), YEAR_FROM, YEAR_TO, OUT_PATH))
    if skipped_no_odds:
        print("Preskoceno %d zapasu bez pouzitelnych kurzu (skrecovane/chybejici)." % skipped_no_odds)
    show_info()


if __name__ == "__main__":
    main()
