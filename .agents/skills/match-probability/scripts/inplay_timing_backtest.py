#!/usr/bin/env python3
"""
TEST: NAKOLIK POMUZE "POCKAT SI NA NEJVYSSI KURZ V PRUBEHU ZAPASU".

OTAZKA, NA KTEROU TOHLE ODPOVIDA
--------------------------------
Model (shodne s trhem - viz metodika.md, zadnou vlastni vyhodu nema) vybere
PRED zapasem favorita a chce na nej vsadit. Misto okamzite sazky PRED
zapasem ale ceka a sazi az VE PRUBEHU zapasu, v okamziku, kdy ma favorit
nejvyssi kurz (= trh ho v tu chvili povazuje za nejvic ohrozeneho).
Meri se, o kolik PROCENT se tim zvedne vynos oproti sazeni hned na
predzapasovy kurz - NE presna castka, presne podle zadani.

PROC JE TO "VYGENEROVANY" KURZ, NE REALNY
------------------------------------------
Nase data (tenis/kurzy/wta_kurzy.csv) maji jen JEDEN kurz na zapas - ten
predzapasovy. Zadny zdroj zivych in-play kurzu pro historicke zapasy k
dispozici neni. Prubeh kurzu behem zapasu je proto DOPOCITANY
(simulovany) z vysledku, ktery uz znamy - viz nize.

JAK SE TEN PRUBEH DOPOCITA
--------------------------
Vsechny zapasy ve WTA jsou na 2 vyherne sety. Z predzapasove
pravdepodobnosti favorita (p0, odvigovane z realnych kurzu) se spocita
pravdepodobnost VYHRY JEDNOHO SETU (p_set), ktera by pri konstantni
sance na kazdy set dala presne p0 na vyhru celeho zapasu (reseni rovnice
p0 = p_set^2 * (3 - 2*p_set)). Pak se podle SKUTECNEHO prubehu setu
(ze sloupce Score - realny vysledek, nic vymysleneho) dopocita
pravdepodobnost pred kazdym dalsim setem:
  - pred 1. setem:                      p0
  - pred 2. setem (po vysledku 1. setu): bud p_set + (1-p_set)*p_set
                                          (favorit vede 1:0), nebo p_set^2
                                          (favorit prohrava 0:1)
  - pred 3. setem (jen pokud je 1:1):    p_set

NEJVYSSI KURZ FAVORITA = NEJNIZSI z techto pravdepodobnosti (prevedeno na
kurz se stejnou marzi, jakou mel puvodni predzapasovy kurz).

DULEZITY, POCTIVY DUSLEDEK TOHOTO MODELU (overeno numericky nize ve
vystupu, ne jen tvrzeno):
  - Zapasy vyhrane na 2 sety NIKDY nedaji lepsi kurz nez predzapasovy -
    vedeni v setech pravdepodobnost jen zvysuje.
  - Zapasy, ktere se protahnou do 3. setu, VZDY nabidnou nizsi
    pravdepodobnost (= vyssi kurz) pred rozhodujicim setem, nez byla
    predzapasova - at vyhral 1. set kdokoliv (matematicky dusledek
    zesileni edge v format "na dva vyherne sety").
  - Zda favorit zapas skutecne DOHRAL VYHROU, rozhoduje o tom, jestli se
    ten lepsi kurz vubec promitne do penez - prohrana sazka prohrava
    stejnou castku bez ohledu na to, za jaky kurz byla uzavrena. Zisk ze
    "cekani na vrchol" tedy plyne VYHRADNE z trojsetovych zapasu, ktere
    favorit zvladl vyhrat (bez ohledu na poradi setu).

DALSI POCTIVE OMEZENI
----------------------
  - Tohle je "prodat na vrcholu" analyza SE ZPETNYM POHLEDEM - v realu
    nikdo nevi v okamziku sazky, ze kurz uz dal neporoste. Zivy, kauzalni
    algoritmus (ktery se musi rozhodnout BEZ znalosti budoucnosti) by
    realne dosahl MENSIHO zlepseni, nez tady vyjde. Cislo z tohoto testu
    je tedy HORNI ODHAD, ne slib dosazitelneho vynosu.
  - Model uvnitr setu (jednotlivé gemy, brejky, tie-breaky) se
    nesimuluje - pocita se jen na urovni CELYCH SETU. Realny in-play kurz
    kolisa i uvnitr setu (napr. pri brejku), takze realny rozptyl (a tedy
    i realne dosazitelne zlepseni) je pravdepodobne VETSI, nez co tenhle
    hruby odhad ukaze.
  - "Favorit" = strana s nizsim predzapasovym kurzem (shodne s trhem,
    protoze model zadnou vlastni vyhodu nad trhem nema - viz metodika.md).

Pouziti:
    python3 inplay_timing_backtest.py
    python3 inplay_timing_backtest.py --rok 2024
"""
import argparse
import csv
import os
import re
import statistics
import sys

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
ODDS_PATH = os.path.join(BASE, "tenis", "kurzy", "wta_kurzy.csv")

ODDS_MIN, ODDS_MAX = 1.01, 15.0
FLAT_STAKE = 100.0

_SET_RE = re.compile(r"(\d+)-(\d+)")


def devig(odd_fav, odd_opp):
    q1, q2 = 1.0 / odd_fav, 1.0 / odd_opp
    tot = q1 + q2
    return q1 / tot, tot - 1.0


def solve_p_set(p0):
    """p0 = p_set^2 * (3 - 2*p_set), reseno pro p_set bisekci (g je na [0.5,1]
    rostouci, viz g'(p)=6p(1-p)>=0)."""
    lo, hi = 0.5, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        val = mid * mid * (3.0 - 2.0 * mid)
        if val < p0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def prob_three_sets(p0):
    """Pravdepodobnost, ze zapas dojde do 3. (rozhodujiciho) setu, SPOCITANA
    JESTE PRED ZAPASEM z predzapasoveho kurzu. Zapas dojde do 3. setu
    presne tehdy, kdyz si sety "vymeni" - bud favorit prohraje 1. a vyhraje
    2. set, nebo naopak - tedy P = p_set*(1-p_set) + (1-p_set)*p_set =
    2*p_set*(1-p_set). Tohle je presne ten signal, ktery model potrebuje,
    aby vedel JESTE PRED ZAPASEM, jestli se vyplati cekat na kurz v
    prubehu (vysoke P = vyplati se cekat), nebo rovnou sazet na
    predzapasovy kurz (nizke P = cekani skoro nic nezmeni, viz
    _navyseni_kurzu() a tabulka v `run()`)."""
    p_set = solve_p_set(p0)
    return 2.0 * p_set * (1.0 - p_set)


def parse_sets(score_str):
    """'6-4 3-6 7-5' (i s tiebreakem '7-6(4)') -> [(6,4),(3,6),(7,5)], nebo
    None kdyz se neparsuje (poskozeny radek)."""
    tokens = (score_str or "").split()
    if not tokens:
        return None
    sets = []
    for t in tokens:
        m = _SET_RE.match(t)
        if not m:
            return None
        sets.append((int(m.group(1)), int(m.group(2))))
    return sets


def validate_best_of_3(sets, p1_won):
    """Vrati True, kdyz poradi setu odpovida skutecnemu zapasu na 2 vyherne
    sety (2 nebo 3 odehrane sety, jeden hrac ma presne 2 vyhrane, druhy < 2,
    a tenhle vitez souhlasi s tim, co rika sloupec Winner)."""
    if len(sets) not in (2, 3):
        return False
    w1 = sum(1 for g1, g2 in sets if g1 > g2)
    w2 = len(sets) - w1
    if not ((w1 == 2 and w2 < 2) or (w2 == 2 and w1 < 2)):
        return False
    winner_is_p1 = (w1 == 2)
    return winner_is_p1 == p1_won


def checkpoints(sets, p_set, p0, fav_is_p1):
    """Pravdepodobnost vyhry favorita PRED kazdym setem (vcetne 1.), podle
    skutecneho prubehu."""
    cps = [p0]
    n = len(sets)
    if n >= 2:
        g1, g2 = sets[0]
        fav_games, opp_games = (g1, g2) if fav_is_p1 else (g2, g1)
        fav_won_set1 = fav_games > opp_games
        cp2 = (p_set + (1 - p_set) * p_set) if fav_won_set1 else (p_set * p_set)
        cps.append(cp2)
    if n == 3:
        cps.append(p_set)  # tretí set nastava jen pri stavu 1:1 -> vzdy p_set
    return cps


def load_rows(year=None):
    with open(ODDS_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if year:
        rows = [r for r in rows if r["Date"][:4] == str(year)]
    return rows


class Book:
    def __init__(self, label):
        self.label = label
        self.n = 0
        self.wins = 0
        self.staked = 0.0
        self.returned = 0.0

    def bet(self, stake, odds, won):
        self.n += 1
        self.staked += stake
        if won:
            self.wins += 1
            self.returned += stake * odds

    @property
    def profit(self):
        return self.returned - self.staked

    @property
    def roi(self):
        return self.profit / self.staked if self.staked else 0.0


def _navyseni_kurzu(rises_all, rises_3set):
    """Vypise, o kolik prumerne (a medianove) stoupne kurz favorita mezi
    predzapasovou cenou a nejvyssim bodem v prubehu zapasu. Pocita se
    ABSOLUTNE (kolik kurzovych bodu) i RELATIVNE (o kolik % narostl kurz
    oproti predzapasovemu). U zapasu na 2 sety je rozdil per definitionem
    0, proto se pocita jen z 3setovych a ze vsech (kde je 3setovych rozdil
    zarednen nulami ze 2setovych - obe cisla se hodi na jinou otazku)."""
    def stats(pairs):
        abs_d = [peak - base for base, peak in pairs]
        pct_d = [(peak - base) / base * 100.0 for base, peak in pairs]
        return (statistics.mean(abs_d), statistics.median(abs_d),
                statistics.mean(pct_d), statistics.median(pct_d))

    print("=" * 72)
    print("PRUMERNE NAVYSENI KURZU FAVORITA (predzapasovy -> nejvyssi v prubehu)")
    print("=" * 72)

    a_mean, a_med, p_mean, p_med = stats(rises_all)
    print(f"Ze VSECH pouzitelnych zapasu (2setove pocitaji s navysenim 0):")
    print(f"  prumer:  {a_mean:+.3f} kurzoveho bodu  ({p_mean:+.1f} % relativne)")
    print(f"  median:  {a_med:+.3f} kurzoveho bodu  ({p_med:+.1f} % relativne)")

    if rises_3set:
        a_mean3, a_med3, p_mean3, p_med3 = stats(rises_3set)
        print(f"\nJen z zapasu, ktere se protahly do 3. setu (tam, kde se navyseni")
        print(f"vubec deje):")
        print(f"  prumer:  {a_mean3:+.3f} kurzoveho bodu  ({p_mean3:+.1f} % relativne)")
        print(f"  median:  {a_med3:+.3f} kurzoveho bodu  ({p_med3:+.1f} % relativne)")

        actually_risen = [(b, p) for b, p in rises_3set if p > b + 1e-9]
        if actually_risen:
            ar_mean, ar_med, arp_mean, arp_med = stats(actually_risen)
            print(f"\nJen z zapasu, kde kurz SKUTECNE stoupl nad predzapasovy "
                  f"({len(actually_risen)} z {len(rises_3set)} trojsetovych):")
            print(f"  prumer:  {ar_mean:+.3f} kurzoveho bodu  ({arp_mean:+.1f} % relativne)")
            print(f"  median:  {ar_med:+.3f} kurzoveho bodu  ({arp_med:+.1f} % relativne)")
    print()


def _kdy_cekat(match_rows, roi_base_all, roi_peak_all):
    """Odpovida na otazku 'kdy rict modelu, aby cekal na kurz v prubehu, a
    kdy at sazi rovnou pred zapasem'. Signal je prob_three_sets(p0) -
    spocitatelny JESTE PRED ZAPASEM jen z predzapasovych kurzu.

    Dve veci se tu overuji:
      1. KALIBRACE - sedi predikovane P(3. set) s tim, jak casto se 3. set
         ve skutecnosti odehral? (Kdyby ne, cely signal by byl k nicemu.)
      2. ROZHODOVACI PRAH - kolik z celkoveho zlepseni ROI se zachyta, kdyz
         se "ceka" jen u zapasu nad danym prahem P(3. set), a kolik zapasu
         to vubec vyzaduje sledovat (= naklad na zivy monitoring/API kvotu
         v live_tennis_simulator.py)."""
    print("=" * 72)
    print("KDY CEKAT NA KURZ V PRUBEHU, KDY SAZET HNED (signal: P(3. set)")
    print("spocitana PRED zapasem jen z predzapasovych kurzu)")
    print("=" * 72)

    # --- 1. kalibrace: predikce P(3. set) vs. skutecnost, podle pasma p0 ---
    edges = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.0]
    bins = {e: [] for e in edges}
    for m in match_rows:
        for e in edges:
            if m["p0"] < e:
                bins[e].append(m)
                break
        else:
            bins[edges[-1]].append(m)

    print(f"\n{'p0 favorita':<14}{'n':>6}{'P(3.set) predikce':>20}"
          f"{'skutecnost':>12}{'navyseni kurzu':>17}{'zlepseni ROI':>15}")
    lo = 0.50
    for e in edges:
        g = bins[e]
        if not g:
            lo = e
            continue
        pred = sum(m["p3_pred"] for m in g) / len(g)
        real = sum(1 for m in g if m["got_3set"]) / len(g)
        rise_pct = statistics.mean(
            (m["peak_odds_fav"] - m["odd_fav"]) / m["odd_fav"] * 100.0 for m in g)
        bb, pp = Book("b"), Book("p")
        for m in g:
            bb.bet(FLAT_STAKE, m["odd_fav"], m["fav_won"])
            pp.bet(FLAT_STAKE, m["peak_odds_fav"], m["fav_won"])
        zlepseni = (pp.roi - bb.roi) * 100
        print(f"{lo:.2f}-{e:.2f}      {len(g):>6}{pred:>19.1%}{real:>12.1%}"
              f"{rise_pct:>16.1f}%{zlepseni:>+14.1f} b.")
        lo = e
    print("\n(,,P(3.set) predikce'' a ,,skutecnost'' by si mely odpovidat - to je")
    print("kontrola, ze signal spocitany jen z predzapasovych kurzu neni fiktivni.)")

    # --- 2. rozhodovaci prah: kolik % zlepseni zachytime za jak velky
    #        monitorovaci naklad (podil zapasu, co se musi zive sledovat) ---
    print(f"\n{'prah P(3.set)':<16}{'% zapasu k cekani':>20}{'ROI hybridu':>14}"
          f"{'zachyceno z mozneho zlepseni':>30}")
    rozpeti = roi_peak_all - roi_base_all
    thresholds = [0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 1.01]
    best_t, best_waits = None, None
    for t in thresholds:
        hb = Book("hybrid")
        n_wait = 0
        for m in match_rows:
            if m["p3_pred"] >= t:
                n_wait += 1
                hb.bet(FLAT_STAKE, m["peak_odds_fav"], m["fav_won"])
            else:
                hb.bet(FLAT_STAKE, m["odd_fav"], m["fav_won"])
        zachyceno = ((hb.roi - roi_base_all) / rozpeti * 100.0) if rozpeti else float("nan")
        podil_wait = n_wait / len(match_rows) * 100.0
        print(f"P(3.set)>={t:<6.2f}{podil_wait:>19.1f}%{hb.roi:>+13.1%}"
              f"{zachyceno:>29.1f} %")
        if zachyceno >= 90.0:
            # chceme NEJVYSSI prah, co jeste zachyti >=90 % - tedy nejmensi
            # monitorovaci naklad za tuhle cenu (zachyceno s rostoucim prahem
            # monotonne klesa, takze posledni zapis pred porusenim podminky
            # je to spravne maximum)
            best_t, best_waits = t, podil_wait

    print()
    if best_t is not None:
        print(f"DOPORUCENI: prah P(3. set) >= {best_t:.2f} zachyti aspon 90 % "
              f"z celkoveho mozneho zlepseni,")
        print(f"ale zive sledovat (cekat na kurz behem zapasu) vyzaduje jen "
              f"{best_waits:.0f} % zapasu -")
        print("u ostatnich (jasni favorite, kde se temer jiste rozhodne na 2 sety)")
        print("se vyplati sazet rovnou na predzapasovy kurz, bez cekani.")
    print()


def run(year=None):
    if not os.path.exists(ODDS_PATH):
        print("CHYBA: chybi soubor s kurzy %s" % ODDS_PATH)
        print("Spust nejdriv: python3 fetch_tennis_odds.py")
        sys.exit(1)

    rows = load_rows(year)
    print("Nactenych radku s kurzy: %d%s\n" % (len(rows), " (rok %s)" % year if year else ""))

    n_total = n_bad_score = n_no_fav = n_bad_odds = n_ok = 0
    n_3set = n_2set = 0

    base = Book("predzapasovy kurz")
    peak = Book("nejvyssi kurz v prubehu")
    base_3set = Book("predzapasovy (jen 3 sety)")
    peak_3set = Book("vrchol (jen 3 sety)")
    base_2set = Book("predzapasovy (jen 2 sety)")
    peak_2set = Book("vrchol (jen 2 sety)")

    examples = []
    rises_all = []    # (odd_fav, peak_odds_fav) pro VSECHNY pouzitelne zapasy
    rises_3set = []   # totez, jen zapasy na 3 sety
    match_rows = []   # pro _kdy_cekat(): p0, predikce P(3. set), realita, ...

    for r in rows:
        n_total += 1
        try:
            odd1, odd2 = float(r["Odd_1"]), float(r["Odd_2"])
        except (ValueError, TypeError):
            n_bad_odds += 1
            continue
        if odd1 == odd2:
            n_no_fav += 1
            continue
        fav_is_p1 = odd1 < odd2
        odd_fav, odd_opp = (odd1, odd2) if fav_is_p1 else (odd2, odd1)
        if not (ODDS_MIN <= odd_fav <= ODDS_MAX):
            n_bad_odds += 1
            continue

        sets = parse_sets(r.get("Score", ""))
        if sets is None:
            n_bad_score += 1
            continue
        p1_won = (r["Winner"].strip() == r["Player_1"].strip())
        if not validate_best_of_3(sets, p1_won):
            n_bad_score += 1
            continue

        fav_won = (p1_won == fav_is_p1)

        p0, overround = devig(odd_fav, odd_opp)
        p_set = solve_p_set(p0)
        p3_pred = 2.0 * p_set * (1.0 - p_set)  # == prob_three_sets(p0), uz mame p_set
        cps = checkpoints(sets, p_set, p0, fav_is_p1)
        peak_prob = min(cps)
        peak_odds_fav = 1.0 / (peak_prob * (1.0 + overround))

        n_ok += 1
        base.bet(FLAT_STAKE, odd_fav, fav_won)
        peak.bet(FLAT_STAKE, peak_odds_fav, fav_won)
        rises_all.append((odd_fav, peak_odds_fav))
        match_rows.append({
            "p0": p0, "p3_pred": p3_pred, "got_3set": len(sets) == 3,
            "odd_fav": odd_fav, "peak_odds_fav": peak_odds_fav, "fav_won": fav_won,
        })

        if len(sets) == 3:
            n_3set += 1
            base_3set.bet(FLAT_STAKE, odd_fav, fav_won)
            peak_3set.bet(FLAT_STAKE, peak_odds_fav, fav_won)
            rises_3set.append((odd_fav, peak_odds_fav))
            if fav_won and peak_odds_fav > odd_fav * 1.05 and len(examples) < 6:
                examples.append((r["Player_1"], r["Player_2"], r["Score"],
                                  odd_fav, peak_odds_fav, fav_won))
        else:
            n_2set += 1
            base_2set.bet(FLAT_STAKE, odd_fav, fav_won)
            peak_2set.bet(FLAT_STAKE, peak_odds_fav, fav_won)

    print("Pouzitelnych zapasu: %d (vyrazeno: %d chybny/nerozpoznany Score, "
          "%d bez jasneho favorita, %d kurz mimo rozsah)"
          % (n_ok, n_bad_score, n_no_fav, n_bad_odds))
    print("  z toho na 2 sety: %d | na 3 sety: %d\n" % (n_2set, n_3set))

    _navyseni_kurzu(rises_all, rises_3set)

    def tabulka(nazev, b_base, b_peak):
        print("=" * 72)
        print(nazev)
        print("=" * 72)
        print(f"{'':28}{'vsazeno':>10}{'vraceno':>12}{'ROI':>10}{'uspesnost':>12}")
        for b in (b_base, b_peak):
            print(f"{b.label:28}{b.staked:>10.0f}{b.returned:>12.0f}"
                  f"{b.roi:>+9.1%} {b.wins / b.n if b.n else 0:>11.1%}")
        if b_base.roi != 0:
            rel = (b_peak.roi - b_base.roi) / abs(b_base.roi) * 100
        else:
            rel = float("nan")
        bodu = (b_peak.roi - b_base.roi) * 100
        zisk_rel = ((b_peak.profit - b_base.profit) / abs(b_base.profit) * 100
                    if b_base.profit != 0 else float("nan"))
        print(f"\nZlepseni ROI: {bodu:+.1f} procentniho bodu "
              f"(relativne {rel:+.0f} % vuci puvodnimu ROI)")
        print(f"Zisk/ztrata: {b_base.profit:+.0f} -> {b_peak.profit:+.0f} mincí "
              f"({zisk_rel:+.0f} % relativne)\n")

    tabulka("CELKEM (vsechny zapasy, vklad %.0f na zapas)" % FLAT_STAKE, base, peak)
    tabulka("JEN ZAPASY NA 2 SETY (kontrola: tady by zmena mela byt nulova)",
            base_2set, peak_2set)
    tabulka("JEN ZAPASY NA 3 SETY (tady se cely efekt odehrava)",
            base_3set, peak_3set)

    if examples:
        print("=" * 72)
        print("PRIKLADY (3setovy zapas, favorit vyhral, kurz v prubehu vyssi)")
        print("=" * 72)
        for p1, p2, score, o0, opeak, won in examples:
            print(f"  {p1} vs {p2}  [{score.strip()}]  "
                  f"predzapasovy kurz {o0:.2f} -> nejvyssi v prubehu {opeak:.2f}")
        print()

    _kdy_cekat(match_rows, base.roi, peak.roi)

    print("-" * 72)
    print("SHRNUTI: Cekani na nejvyssi kurz NIKDY nezmeni, jestli sazka vyhraje")
    print("nebo prohraje (to urcuje jen skutecny vysledek zapasu) - zmeni jen")
    print("VYPLATU u vyhranych sazek. Cele zlepseni tedy plyne z trojsetovych")
    print("zapasu, ktere favorit vyhral, protoze jen tam kurz behem zapasu")
    print("skutecne na chvili stoupne nad predzapasovou uroven. Je to HORNI")
    print("ODHAD se zpetnym pohledem (viz docstring) - realny, kauzalni")
    print("algoritmus by v praxi dosahl mene.")
    print("-" * 72)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rok", type=int, default=None, help="omezit jen na jeden rok")
    args = ap.parse_args()
    run(year=args.rok)


if __name__ == "__main__":
    main()
