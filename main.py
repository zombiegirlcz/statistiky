#!/usr/bin/env python3
"""
main.py — interaktivní TUI pro hru Lucky Six (Fortuna).

Řídí se oficiální nápovědou hry ("Lucky Six Nápověda.md"), doslovně:

  * 48 čísel, 8 barevných skupin po 6:
      Červená 1,9,17,25,33,41 · Zelená 2,10,18,26,34,42
      Modrá 3,11,19,27,35,43 · Fialová 4,12,20,28,36,44
      Hnědá 5,13,21,29,37,45 · Žlutá 6,14,22,30,38,46
      Oranžová 7,15,23,31,39,47 · Černá 8,16,24,32,40,48
  * V kole se vygeneruje 35 z 48 čísel (v pořadí).
  * Vyhraješ, když je všech tvých 6 čísel mezi 35 → výhra = vklad ×
    koeficient posledního (6.) trefeného čísla.

Sázkové trhy (dle nápovědy):
  - hlavní sázka na 6 čísel
  - systémová sázka 6/7, 6/8, 6/9, 6/10
  - Šest čísel jedné barvy
  - Sudá/Lichá – Předčíslí (většina sudých/lichých v prvních 5)
  - První číslo Sudé/Liché
  - Součet předčíslí (-122.5+)
  - První číslo (-24.5+)
  - Barva první koule (lze zvolit více barev)
  - Předčíslí – Vybrané číslo

Informace o hře: min vklad 3, max vklad 300, měna EUR,
RTP 85,87 % – 99,63 % (bonusové kolo + konfigurace).

Spuštění:
  cd /root/statistiky
  python3 main.py
"""
import os
import random
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator

import loterie_simulator as lot

C = "\033[36m"; G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"
D = "\033[90m"; Z = "\033[0m"; B = "\033[1m"

TOTAL = lot.TOTAL          # 48
PICK = lot.PICK            # 6
DRAWN = lot.DRAWN          # 35
MULT = lot.MULT

MENA = "Kč"
VKLAD_MIN = 3
VKLAD_MAX = 300
VKLAD_DEFAULT = 10

# 8 barevných skupin po 6 číslech (přesně dle nápovědy)
BARVY = {
    "Červená":  [1, 9, 17, 25, 33, 41],
    "Zelená":   [2, 10, 18, 26, 34, 42],
    "Modrá":    [3, 11, 19, 27, 35, 43],
    "Fialová":  [4, 12, 20, 28, 36, 44],
    "Hnědá":    [5, 13, 21, 29, 37, 45],
    "Žlutá":    [6, 14, 22, 30, 38, 46],
    "Oranžová": [7, 15, 23, 31, 39, 47],
    "Černá":    [8, 16, 24, 32, 40, 48],
}

# System Multiplier (z nápovědy) = 1 / počet kombinací
# 6/6→1, 6/7→0.1429, 6/8→0.0357, 6/9→0.0119, 6/10→0.0048
SYSTEM_MULT = {6: 1.0, 7: 0.1429, 8: 0.0357, 9: 0.0119, 10: 0.0048}


def _cisla_na_barvu(cislo):
    for nazev, skupina in BARVY.items():
        if cislo in skupina:
            return nazev
    return "?"


def _kc(x):
    """České formátování: mezera pro tisíce, čárka pro desetinná místa."""
    return f"{x:,.2f} {MENA}".replace(",", "\u00a0").replace(".", ",").replace("\u00a0", " ")


def header():
    print()
    print(f"  {B}{C}══════════════════════════════════════════════════════════════{Z}")
    print(f"  {B}{C}  LUCKY SIX — interaktivní hra (Fortuna)  {D}[simulace, žádné reálné peníze]{Z}")
    print(f"  {B}{C}══════════════════════════════════════════════════════════════{Z}")
    print(f"  {D}48 čísel · vygeneruje se 35 · vyhraješ všech 6 svých čísel{Z}")
    print()


# ---------------------------------------------------------------------------
# Výběr čísel
# ---------------------------------------------------------------------------
def vyber_cisel_rucne(pocet):
    while True:
        raw = inquirer.text(
            message=f"Zadej {pocet} různých čísel z 1–{TOTAL} (odděl čárkou/mezerou):",
            default="").execute()
        if raw is None:
            return None
        casti = raw.replace(",", " ").split()
        try:
            cisla = [int(x) for x in casti]
        except ValueError:
            print(f"  {R}✘ Neplatný vstup — zadávej celá čísla.{Z}")
            continue
        if any(not (1 <= c <= TOTAL) for c in cisla):
            print(f"  {R}✘ Čísla musí být v rozsahu 1–{TOTAL}.{Z}")
            continue
        if len(set(cisla)) != len(cisla):
            print(f"  {R}✘ Čísla se nesmí opakovat.{Z}")
            continue
        if len(cisla) != pocet:
            print(f"  {R}✘ Musíš zadat přesně {pocet} čísel (zadal jsi {len(cisla)}).{Z}")
            continue
        return sorted(cisla)


def vyber_cisel_nahodne(pocet):
    return sorted(random.sample(range(1, TOTAL + 1), pocet))


def vyber_cisel(pocet, popis="Svá čísla"):
    zpusob = inquirer.select(
        message=f"{popis} ({pocet} čísel):",
        choices=[
            Choice("manual", "✍  Zadat ručně"),
            Choice("random", "🎲  Náhodný výběr"),
            Separator(),
            Choice("zpet", "←  Zpět"),
        ], qmark="🔢").execute()
    if zpusob == "zpet":
        return None
    if zpusob == "random":
        return vyber_cisel_nahodne(pocet)
    return vyber_cisel_rucne(pocet)


# ---------------------------------------------------------------------------
# Losování a vyhodnocení
# ---------------------------------------------------------------------------
def losuj():
    return random.sample(range(1, TOTAL + 1), DRAWN)


def vyhodnot(moje, draw):
    """Vrací (pos6 nebo None, pocet_trefenych)."""
    muj_set = set(moje)
    seen = 0
    for i, d in enumerate(draw, start=1):
        if d in muj_set:
            seen += 1
            if seen == PICK:
                return i, seen
    return None, seen


def zobraz_losovani(moje, draw, animace=True):
    muj_set = set(moje)
    print(f"  {B}Tvoje čísla:{Z} " + " ".join(f"{G}{c:>2}{Z}" for c in moje))
    print(f"  {D}Generování ({DRAWN} z {TOTAL})…{Z}\n")
    seen = 0
    pos6 = None
    radek = []
    for i, d in enumerate(draw, start=1):
        if d in muj_set:
            seen += 1
            radek.append(f"{G}{d:>2}{Z}")
            if seen == PICK and pos6 is None:
                pos6 = i
        else:
            radek.append(f"{D}{d:>2}{Z}")
        if animace and i % 10 == 0:
            print("   " + " ".join(radek))
            radek = []
            time.sleep(0.05)
    if radek:
        print("   " + " ".join(radek))
    print()
    return pos6, seen


# ---------------------------------------------------------------------------
# 1) SÓLO SÁZKA (6 čísel)
# ---------------------------------------------------------------------------
def menu_solo():
    header()
    print(f"  {B}HLAVNÍ SÁZKA — 6 čísel{Z}\n")
    moje = vyber_cisel(PICK, "Tvoje čísla")
    if not moje:
        return

    vklad = _vklad("Vklad na kolo")
    if not vklad:
        return

    header()
    print(f"  {B}HLAVNÍ SÁZKA{Z}   vklad {G}{_kc(vklad)}{Z}\n")
    draw = losuj()
    pos6, seen = zobraz_losovani(moje, draw, animace=True)

    print(f"  {B}─── VÝSLEDEK ───{Z}")
    print(f"  Trefená čísla z tvých {PICK}: {B}{seen}{Z}")
    if pos6 is None:
        print(f"  {R}✘ NEVYHRÁVÁŠ{Z} — všech {PICK} čísel se mezi {DRAWN} vygenerovaných nenašlo.")
        print(f"  {D}(trefeno {seen} z {PICK}){Z}")
        print(f"  {D}Ztráta: {_kc(vklad)}{Z}\n")
    else:
        mult = MULT[pos6]
        vyhra = vklad * mult
        zisk = vyhra - vklad
        print(f"  {G}✔ VYHRÁVÁŠ!{Z} Poslední (6.) trefené číslo padlo jako "
              f"{B}{pos6}.{Z} v pořadí → koeficient {B}{mult}×{Z}")
        print(f"  Vklad {_kc(vklad)} × {mult} = {G}{B}{_kc(vyhra)}{Z}  "
              f"({zisk:+,.2f} {MENA})\n")
    inquirer.text(message="Enter pro pokračování", default="").execute()


# ---------------------------------------------------------------------------
# 2) SYSTÉMOVÁ SÁZKA (6/7 – 6/10)
# ---------------------------------------------------------------------------
def kombinace(cisla, k=6):
    import itertools
    return list(itertools.combinations(sorted(cisla), k))


def menu_system():
    header()
    print(f"  {B}SYSTÉMOVÁ SÁZKA{Z} — 7–10 čísel, vznikne předdefinovaný systém\n")
    print(f"  {D}Systém   Počet čísel   Kombinací   System Multiplier{Z}")
    for n in (7, 8, 9, 10):
        print(f"  {D}6/{n:<5}   {n:<11}   {len(kombinace(range(1, n+1))):<10}   "
              f"{SYSTEM_MULT[n]}{Z}")
    print()

    pocet = inquirer.select(
        message="Kolik čísel chceš vybrat?",
        choices=[Choice(n, f"Systém 6/{n}  ({len(kombinace(range(1, n+1)))} kombinací)")
                 for n in (7, 8, 9, 10)] + [Separator(), Choice("zpet", "←  Zpět")],
        qmark="🎯").execute()
    if pocet == "zpet":
        return

    moje = vyber_cisel(pocet, f"Tvých {pocet} čísel")
    if not moje:
        return

    komba = kombinace(moje)
    # dle nápovědy: celkový vklad na tiketu / počet kombinací = vklad na kombinaci
    celkovy_vklad = _vklad("Celkový vklad na tiket")
    if not celkovy_vklad:
        return
    vklad_kombo = celkovy_vklad * SYSTEM_MULT[pocet]

    header()
    print(f"  {B}SYSTÉM 6/{pocet}{Z}   čísla: " + " ".join(f"{G}{c}{Z}" for c in moje))
    print(f"  Kombinací: {B}{len(komba)}{Z}   vklad/kombinace {_kc(vklad_kombo)}   "
          f"celkem {B}{_kc(celkovy_vklad)}{Z}\n")

    draw = losuj()
    print(f"  {D}Vygenerovaná čísla ({DRAWN}):{Z} " +
          " ".join(f"{G if d in set(moje) else D}{d:>2}{Z}" for d in draw))
    print()

    vyhry = 0.0
    vyhrane_komba = 0
    print(f"  {B}─── VYHODNOCENÍ KOMBINACÍ ───{Z}")
    for kombo in komba:
        pos6, _ = vyhodnot(kombo, draw)
        if pos6 is None:
            continue
        mult = MULT[pos6]
        vyhra = vklad_kombo * mult
        vyhry += vyhra
        vyhrane_komba += 1
        print(f"   {G}✔{Z} {kombo} → 6. trefa na {pos6}. místě → {mult}× = {_kc(vyhra)}")
    if vyhrane_komba == 0:
        print(f"   {R}✘ Žádná kombinace netrefila všech 6 čísel.{Z}")

    zisk = vyhry - celkovy_vklad
    print()
    print(f"  Vyhraných kombinací: {B}{vyhrane_komba}/{len(komba)}{Z}")
    print(f"  Vsazeno: {_kc(celkovy_vklad)}   Vráceno: {_kc(vyhry)}   "
          f"Zisk: {(G if zisk >= 0 else R)}{zisk:+,.2f} {MENA}{Z}\n")
    inquirer.text(message="Enter pro pokračování", default="").execute()


# ---------------------------------------------------------------------------
# 3) SPECIÁLNÍ TRHY
# ---------------------------------------------------------------------------
def _vklad(popis="Vklad"):
    v = inquirer.number(
        message=f"{popis} ({MENA}, {VKLAD_MIN}–{VKLAD_MAX}):",
        default=VKLAD_DEFAULT, min_allowed=VKLAD_MIN, max_allowed=VKLAD_MAX,
        float_allowed=True).execute()
    return float(v) if v else 0.0


def _vysledek(vyhral, popis_vyhry, vklad, kurz=None):
    if vyhral:
        if kurz:
            print(f"  {G}✔ VYHRÁVÁŠ{Z} → {_kc(vklad*kurz)}\n")
        else:
            print(f"  {G}✔ VYHRÁVÁŠ{Z} — {popis_vyhry}\n")
    else:
        print(f"  {R}✘ NEVYHRÁVÁŠ{Z}\n")
    inquirer.text(message="Enter pro pokračování", default="").execute()


def special_sest_barvy():
    barva = inquirer.select(
        message="Na kterou barvu sázíš, že padne všech 6 čísel stejné barvy?",
        choices=[Choice(b, b) for b in BARVY] + [Separator(), Choice("zpet", "←  Zpět")],
        qmark="🎨").execute()
    if barva == "zpet":
        return
    vklad = _vklad()
    if not vklad:
        return
    draw = losuj()
    draw_set = set(draw)
    skupina = set(BARVY[barva])
    vse = skupina.issubset(draw_set)
    header()
    print(f"  {B}ŠEST ČÍSEL JEDNÉ BARVY{Z}   barva {barva}, vklad {_kc(vklad)}\n")
    print(f"  Čísla barvy {barva}: {sorted(skupina)}")
    print(f"  Z toho vygenerováno: {len(skupina & draw_set)}/6\n")
    _vysledek(vse, f"všech 6 čísel barvy {barva} padlo", vklad)


def special_suda_licha_predcisli():
    tip = inquirer.select(
        message="Mezi prvními 5 čísly bude více:",
        choices=[Choice("sude", "Sudých"), Choice("liche", "Lichých"),
                 Separator(), Choice("zpet", "←  Zpět")], qmark="⚖").execute()
    if tip == "zpet":
        return
    vklad = _vklad()
    if not vklad:
        return
    draw = losuj()
    prvnich5 = draw[:5]
    sude = sum(1 for x in prvnich5 if x % 2 == 0)
    liche = 5 - sude
    skutecnost = "sude" if sude > liche else "liche"
    header()
    print(f"  {B}SUDÁ/LICHÁ – PŘEDČÍSLÍ{Z}   tip: více {tip}, vklad {_kc(vklad)}\n")
    print(f"  Prvních 5 čísel: {prvnich5}  → sudých {sude}, lichých {liche}\n")
    _vysledek(tip == skutecnost, f"více {skutecnost}ch", vklad, kurz=2.0)


def special_prvni_sude():
    tip = inquirer.select(message="První číslo bude:",
                          choices=[Choice("sude", "Sudé"), Choice("liche", "Liché"),
                                   Separator(), Choice("zpet", "←  Zpět")], qmark="⚖").execute()
    if tip == "zpet":
        return
    vklad = _vklad()
    if not vklad:
        return
    draw = losuj()
    prvni = draw[0]
    skutecnost = "sude" if prvni % 2 == 0 else "liche"
    header()
    print(f"  {B}PRVNÍ ČÍSLO SUDÉ/LICHÉ{Z}   tip {tip}, vklad {_kc(vklad)}\n")
    print(f"  První vygenerované číslo: {B}{prvni}{Z} → {skutecnost}\n")
    _vysledek(tip == skutecnost, f"první číslo {skutecnost}", vklad, kurz=2.0)


def special_soucet_predcisli():
    tip = inquirer.select(message="Součet prvních 5 čísel bude:",
                          choices=[Choice("mensi", "Menší (≤ 122,5)"),
                                   Choice("vetsi", "Větší (> 122,5)"),
                                   Separator(), Choice("zpet", "←  Zpět")], qmark="➕").execute()
    if tip == "zpet":
        return
    vklad = _vklad()
    if not vklad:
        return
    draw = losuj()
    prvnich5 = draw[:5]
    soucet = sum(prvnich5)
    skutecnost = "mensi" if soucet <= 122.5 else "vetsi"
    header()
    print(f"  {B}SOUČET PŘEDČÍSLÍ (−122.5+){Z}   tip {tip}, vklad {_kc(vklad)}\n")
    print(f"  Prvních 5 čísel: {prvnich5} → součet {B}{soucet}{Z} (hranice 122,5)\n")
    _vysledek(tip == skutecnost, f"součet {skutecnost}", vklad, kurz=2.0)


def special_prvni_cislo():
    tip = inquirer.select(message="První číslo bude:",
                          choices=[Choice("mensi", "Menší (< 24,5)"),
                                   Choice("vetsi", "Větší (> 24,5)"),
                                   Separator(), Choice("zpet", "←  Zpět")], qmark="🔢").execute()
    if tip == "zpet":
        return
    vklad = _vklad()
    if not vklad:
        return
    draw = losuj()
    prvni = draw[0]
    skutecnost = "mensi" if prvni < 24.5 else "vetsi"
    header()
    print(f"  {B}PRVNÍ ČÍSLO (−24.5+){Z}   tip {tip}, vklad {_kc(vklad)}\n")
    print(f"  První vygenerované číslo: {B}{prvni}{Z} (hranice 24,5)\n")
    _vysledek(tip == skutecnost, f"první číslo {skutecnost}", vklad, kurz=2.0)


def special_barva_prvni_koule():
    barvy = inquirer.checkbox(
        message="Na kterou/é barvu/y první koule sázíš? (mezerník = vybrat)",
        choices=[Choice(b, b) for b in BARVY],
        qmark="🎨").execute()
    if not barvy:
        return
    vklad = _vklad()
    if not vklad:
        return
    draw = losuj()
    prvni = draw[0]
    skutecna = _cisla_na_barvu(prvni)
    header()
    print(f"  {B}BARVA PRVNÍ KOULE{Z}   sázka na {', '.join(barvy)}, vklad {_kc(vklad)}\n")
    print(f"  První vygenerované číslo: {B}{prvni}{Z} → barva {B}{skutecna}{Z}\n")
    kurz = 8.0 / len(barvy)   # orientační férový kurz (8 barev)
    _vysledek(skutecna in barvy, f"první koule je {skutecna}", vklad, kurz=kurz)


def special_predcisli_vybrane():
    cislo = int(inquirer.number(message=f"Které číslo (1–{TOTAL}) tipuješ do předčíslí?",
                                default=13, min_allowed=1, max_allowed=TOTAL,
                                float_allowed=False).execute() or 0)
    if not cislo:
        return
    vklad = _vklad()
    if not vklad:
        return
    draw = losuj()
    prvnich5 = draw[:5]
    header()
    print(f"  {B}PŘEDČÍSLÍ — VYBRANÉ ČÍSLO{Z}   tip {cislo}, vklad {_kc(vklad)}\n")
    print(f"  Prvních 5 čísel: {prvnich5}\n")
    _vysledek(cislo in prvnich5, f"číslo {cislo} je mezi prvními 5", vklad)


def menu_specialni():
    while True:
        header()
        volba = inquirer.select(
            message="Speciální sázka:",
            choices=[
                Choice("sest", "🌈  Šest čísel jedné barvy"),
                Choice("suda_licha", "⚖  Sudá/Lichá – Předčíslí"),
                Choice("prvni_sude", "⚖  První číslo Sudé/Liché"),
                Choice("soucet", "➕  Součet předčíslí (−122.5+)"),
                Choice("prvni_cislo", "🔢  První číslo (−24.5+)"),
                Choice("barva1", "🎨  Barva první koule (více barev)"),
                Choice("predcisli", "🎯  Předčíslí – Vybrané číslo"),
                Separator(),
                Choice("zpet", "←  Zpět"),
            ], qmark="🎲").execute()
        if volba == "zpet":
            return
        {"sest": special_sest_barvy,
         "suda_licha": special_suda_licha_predcisli,
         "prvni_sude": special_prvni_sude,
         "soucet": special_soucet_predcisli,
         "prvni_cislo": special_prvni_cislo,
         "barva1": special_barva_prvni_koule,
         "predcisli": special_predcisli_vybrane}[volba]()


# ---------------------------------------------------------------------------
# 4) STATISTIKY & RTP
# ---------------------------------------------------------------------------
def menu_statistiky():
    header()
    print(f"  {B}STATISTIKY & RTP (analyticky + simulace){Z}\n")
    p = lot.analytic_hit_prob()
    print(f"  Pravděpodobnost trefy všech {PICK} čísel (generuje se {DRAWN} z {TOTAL}):")
    print(f"    {B}{p*100:.5f} %{Z}  = 1 z {1/p:,.1f} kola\n")
    dist = lot.analytic_pos_dist()
    print(f"  Výplatní tabulka (dle nápovědy) + pravděpodobnost pořadí 6. trefy:")
    print(f"    {'pořadí':>6} {'koef':>8} {'P(pořadí)':>12} {'podíl z tref':>13}")
    for pos in range(PICK, DRAWN + 1):
        print(f"    {pos:>6} {MULT[pos]:>8} {dist[pos]:>12.6%} {dist[pos]/p:>12.3%}")
    print()
    n = int(inquirer.number(
        message="Kolik kol nasimulovat pro RTP? (0 = přeskočit)",
        default=100000, min_allowed=0, max_allowed=20000000,
        float_allowed=False).execute() or 0)
    if n:
        print(f"\n  {D}Simuluji {n:,} kol…{Z}")
        res = lot.simulate(n, seed=None)
        hits = res["hits"]
        roi = (res["returned"] - res["staked"]) / res["staked"] * 100
        print(f"\n  Trefeno plný počet: {hits:,} ({100.0*hits/n:.4f} %)")
        print(f"  {B}RTP simulace (základní sázka, bez bonusu): {100+roi:.2f} %{Z}")
        print(f"  {D}Oficiální RTP v nápovědě je 85,87–99,63 % (bonusové kolo +")
        print(f"  nastavitelná konfigurace; v základní tabulce není).{Z}\n")
    inquirer.text(message="Enter pro pokračování", default="").execute()


# ---------------------------------------------------------------------------
# 5) RYCHLÁ SIMULACE CELÉHO DNE
# ---------------------------------------------------------------------------
KOLO_MIN = 2.5   # jedno kolo = 2:30 min


def menu_rychla_simulace():
    header()
    print(f"  {B}RYCHLÁ SIMULACE — celý den{Z}\n")
    print(f"  {D}Jedno kolo = {KOLO_MIN:g} min  →  24 h = {int(24*60/KOLO_MIN)} kol{Z}\n")

    pocet = inquirer.select(
        message="Kolik čísel budeš sázet?",
        choices=[Choice(6, "Hlavní sázka (6 čísel)")] +
                [Choice(n, f"Systém 6/{n} ({n} čísel, {len(kombinace(range(1, n+1)))} kombinací)")
                 for n in (7, 8, 9, 10)] +
                [Separator(), Choice("zpet", "←  Zpět")],
        qmark="🎯").execute()
    if pocet == "zpet":
        return

    moje = vyber_cisel(pocet, f"Tvých {pocet} čísel")
    if not moje:
        return

    if pocet == 6:
        vklad = _vklad("Vklad na kolo")
        if not vklad:
            return
        vklad_kombo = vklad
        celkovy = vklad
    else:
        vklad = _vklad("Celkový vklad na tiket (kolo)")
        if not vklad:
            return
        vklad_kombo = vklad * SYSTEM_MULT[pocet]
        celkovy = vklad

    bank_start = inquirer.number(
        message=f"Počáteční bank (startovní kapitál, {MENA}):",
        default=max(VKLAD_MIN, 100), min_allowed=1, max_allowed=1000000,
        float_allowed=True).execute()
    bank_start = float(bank_start) if bank_start else 100.0

    hodiny = inquirer.number(message="Kolik hodin simulovat?", default=24,
                             min_allowed=1, max_allowed=72,
                             float_allowed=True).execute()
    hodiny = float(hodiny) if hodiny else 24.0
    kola = int(hodiny * 60 / KOLO_MIN)

    komba = kombinace(moje) if pocet > 6 else [tuple(sorted(moje))]

    header()
    print(f"  {B}SIMULACE {kola} kol ({hodiny:g} h){Z}   čísla: " +
          " ".join(f"{B}{c}{Z}" for c in moje) +
          f"   vklad/kolo {_kc(celkovy)}")
    if pocet > 6:
        print(f"  {D}vklad/kombinace {_kc(vklad_kombo)} · {len(komba)} kombinací{Z}")
    print(f"  {B}Počáteční bank: {_kc(bank_start)}{Z}")
    print(f"  {D}formát: číslo(pořadí) — zeleně trefeno, šedě netrefeno;")
    print(f"  pořadí 1 = první koule, {DRAWN} = poslední · [bank] = stav po kole{Z}\n")

    staked = 0.0
    returned = 0.0
    hits = 0
    bank = bank_start
    bank_min = bank_start
    bank_max = bank_start
    bank_min_k = 0
    bank_max_k = 0
    first_bust = None   # první kolo, kdy bank klesl pod vklad

    for k in range(1, kola + 1):
        # když banka nestačí na vklad, končíme (ruinace)
        if bank < celkovy:
            first_bust = k
            print(f"\n  {R}✘ BANKROT ve {k}. kole — bank {_kc(bank)} < vklad {_kc(celkovy)}.{Z}")
            print(f"  {D}Simulace ukončena, odehráno {k-1} kol.{Z}")
            break

        draw = losuj()
        pos_map = {c: i for i, c in enumerate(draw, start=1)}

        vyhra_kolo = 0.0
        for kombo in komba:
            pos6, _ = vyhodnot(kombo, draw)
            if pos6 is not None:
                vyhra_kolo += vklad_kombo * MULT[pos6]
        staked += celkovy
        returned += vyhra_kolo
        if vyhra_kolo > 0:
            hits += 1

        bank += vyhra_kolo - celkovy
        if bank < bank_min:
            bank_min = bank
            bank_min_k = k
        if bank > bank_max:
            bank_max = bank
            bank_max_k = k

        casti = []
        for c in moje:
            p = pos_map.get(c)
            if p is None:
                casti.append(f"{D}{c}(–){Z}")
            else:
                casti.append(f"{G}{c}({p}){Z}")
        radek = " ".join(casti)

        if vyhra_kolo > 0:
            vys = f"{G}✔{Z} {(vyhra_kolo - celkovy):+,.2f}"
        else:
            vys = f"{R}✘{Z} {-celkovy:+,.2f}"
        barva_bank = G if bank >= bank_start else R
        print(f"  {k:>3}.  {radek}   {vys}   {barva_bank}[{bank:,.2f}]{Z}")

    odehrano = k - 1 if first_bust else kola
    zisk = returned - staked
    print()
    print(f"  {B}─── SOUHRN ZA {odehrano} KOL ({odehrano*KOLO_MIN/60:.1f} h) ───{Z}")
    print(f"  Počáteční bank: {_kc(bank_start)}")
    print(f"  Konečný bank:   {(G if bank >= bank_start else R)}{_kc(bank)}{Z}  "
          f"({bank - bank_start:+,.2f})")
    print(f"  Vsazeno:        {_kc(staked)}")
    print(f"  Vráceno:        {_kc(returned)}")
    print(f"  Zisk:           {(G if zisk >= 0 else R)}{zisk:+,.2f} {MENA}{Z}")
    print(f"  RTP:            {100*returned/staked:.2f} %   (100 % = návrat vkladu)")
    print(f"  Výherních kol:  {hits}/{odehrano}  ({100*hits/odehrano:.2f} %)")
    print(f"  Nejnižší bank:  {_kc(bank_min)}  ({bank_min_k}. kolo)")
    print(f"  Nejvyšší bank:  {_kc(bank_max)}  ({bank_max_k}. kolo)")
    if first_bust:
        print(f"  {R}Bankrot:        {first_bust}. kolo{Z}")
    else:
        print(f"  {G}Přežil celou simulaci.{Z}")
    print()
    inquirer.text(message="Enter pro pokračování", default="").execute()


# ---------------------------------------------------------------------------
# HLAVNÍ MENU
# ---------------------------------------------------------------------------
def hlavni_menu():
    while True:
        header()
        volba = inquirer.select(
            message="Co chceš dělat?",
            choices=[
                Choice("solo", "🎟  Hlavní sázka (6 čísel)"),
                Choice("system", "🧩  Systémová sázka (6/7 – 6/10)"),
                Choice("special", "🌈  Speciální sázky"),
                Choice("rychla", "⚡  Rychlá simulace celého dne (24 h / 2:30)"),
                Choice("stats", "📊  Statistiky & RTP"),
                Separator(),
                Choice("konec", "👋  Konec"),
            ], qmark="🎲").execute()

        if volba == "solo":
            menu_solo()
        elif volba == "system":
            menu_system()
        elif volba == "special":
            menu_specialni()
        elif volba == "rychla":
            menu_rychla_simulace()
        elif volba == "stats":
            menu_statistiky()
        elif volba == "konec":
            print(f"\n  {C}Ahoj!{Z}\n")
            return


if __name__ == "__main__":
    try:
        hlavni_menu()
    except KeyboardInterrupt:
        print(f"\n  {C}Ukončeno.{Z}\n")
