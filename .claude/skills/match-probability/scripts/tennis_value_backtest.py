#!/usr/bin/env python3
"""
POCTIVY TEST, JESTLI MA NAS TENISOVY MODEL SAZKOVOU VYHODU PROTI TRHU.

OTAZKA, NA KTEROU TOHLE ODPOVIDA
--------------------------------
backtest.py uz zmeril, ze model tipuje viteze tenisoveho zapasu s ~70%
uspesnosti (baseline nahoda = 50 %). To zni dobre, ale je to ODPOVED NA JINOU
OTAZKU, nez jakou potrebuje sazeni. Favorit v tenise vyhrava sam od sebe
asi v 70 % pripadu - takze 70% uspesnost tipovani muze znamenat, ze model
jen opisuje to, co uz vi kazdy, a sazet podle toho je ztratove, protoze kurz
na favorita je nizky.

Sazkova vyhoda znamena neco jineho: nas odhad pravdepodobnosti musi byt
PRESNEJSI nez cena, kterou dava trh. Presne tohle se u fotbalu otestovalo
(ticket_builder.py) a vysledek byl ztrata - trh byl ostrejsi nez model.
U tenisu to doted otestovat neslo, protoze tenis/*.csv zadne kurzy nemaji.

Tenhle skript to doplnuje: spoji nase zapasove statistiky (tenis/wta_*.csv,
Jeff Sackmann) s historickymi kurzy (tenis/kurzy/wta_kurzy.csv, viz
fetch_tennis_odds.py) a zmeri realne ROI nekolika sazkovych strategii.

JAK SE HLIDA UNIK INFORMACE (to je na celem testu nejdulezitejsi)
----------------------------------------------------------------
1. Model u KAZDEHO zapasu pocita jen z zapasu ODEHRANYCH DRIV (cutoff =
   datum zacatku turnaje). Zadna znalost budoucnosti.
2. Strany se neoznacuji podle viteze. Player_1/Player_2 bere ze zdroje
   kurzu, kde poradi nema nic spolecneho s vysledkem. (Na tuhle past
   jsme uz jednou narazili u tenisovych dvojchyb - viz metodika.md.)
3. Sazi se za KURZ, ktery byl k dispozici pred zapasem, ne za nejaky
   dopocitany "fair" kurz.
4. Vyzaduje se minimalni historie obou hracek (--min-hist, vychozi 15
   zapasu), aby se nesazelo na nahodna cisla z 2-3 zapasu - stejna
   pojistka jako MIN_TEAM_MATCHES u fotbalu.

STRATEGIE, KTERE SE MERI
------------------------
  hodnota      - sazi se tam, kde model vidi edge >= --min-edge proti
                 odvigovanemu trhu (na kteroukoli stranu, favorit i outsider)
  kelly        - stejny vyber sazek, ale vklad podle frakcniho Kelly kriteria
  favorit      - kontrolni baseline: vzdy sazet favorita trhu
  model        - kontrolni baseline: vzdy sazet, koho tipuje model

Pouziti:
    python3 tennis_value_backtest.py
    python3 tennis_value_backtest.py --min-edge 0.08 --min-hist 25
    python3 tennis_value_backtest.py --rok 2024          # jen jeden rok
    python3 tennis_value_backtest.py --diagnostika       # kalibrace + join detaily
"""
import argparse
import bisect
import csv
import glob
import os
import sys
import unicodedata
from collections import defaultdict

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
ODDS_PATH = os.path.join(BASE, "tenis", "kurzy", "wta_kurzy.csv")

# Jak daleko po zacatku turnaje muze zapas padnout. Sackmannova data maji jen
# datum ZACATKU turnaje, zdroj kurzu ma presne datum zapasu - grandslam trva
# dva tydny, takze okno musi byt dost siroke, ale ne tak, aby spojilo dva
# rozdilne turnaje tech stejnych dvou hracek.
WINDOW_BEFORE_DAYS = 3
WINDOW_AFTER_DAYS = 21

# Vylucuje artefakty z mala dat - edge nad 25 procentnich bodu je skoro jiste
# sum, ne skutecna trzni neefektivita (stejny prah jako ticket_builder.py).
EDGE_MAX = 0.25
ODDS_MIN, ODDS_MAX = 1.05, 15.0

KELLY_FRACTION = 0.25  # frakcni Kelly - plny Kelly je na realnych datech moc agresivni
FLAT_STAKE = 100.0


# ---------------------------------------------------------------- jmena

def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_token(s):
    s = strip_accents(s or "").lower()
    return "".join(c for c in s if c.isalpha())


def sackmann_key(full_name):
    """'Iga Swiatek' -> ('swiatek', 'i'). Viceslovna prijmeni ('Beatriz Haddad
    Maia') daji ('haddadmaia', 'b') - zdroj kurzu je zapisuje stejne
    ('Haddad Maia B.'), takze to sedi."""
    parts = (full_name or "").split()
    if len(parts) < 2:
        return None
    first, surname = parts[0], "".join(parts[1:])
    fi = norm_token(first)
    sn = norm_token(surname)
    if not fi or not sn:
        return None
    return (sn, fi[0])


def odds_key(short_name):
    """'Swiatek I.' -> ('swiatek', 'i'); 'Sun T.T.' -> ('sun', 't')."""
    parts = (short_name or "").replace(".", ". ").split()
    if len(parts) < 2:
        return None
    initials, surname = parts[-1], "".join(parts[:-1])
    fi = norm_token(initials)
    sn = norm_token(surname)
    if not fi or not sn:
        return None
    return (sn, fi[0])


def date_to_int(d):
    """'2024-03-16' -> 20240316"""
    return int(d.replace("-", ""))


def shift_days(yyyymmdd, days):
    """Hrube posunuti data o dny bez datetime - staci na okno pro spojovani."""
    import datetime
    y, m, d = yyyymmdd // 10000, (yyyymmdd // 100) % 100, yyyymmdd % 100
    try:
        dt = datetime.date(y, m, d) + datetime.timedelta(days=days)
    except ValueError:
        return yyyymmdd
    return dt.year * 10000 + dt.month * 100 + dt.day


# ---------------------------------------------------------------- data

def load_sackmann_wta():
    rows = []
    for path in sorted(glob.glob(os.path.join(BASE, "tenis", "wta_matches_*.csv"))):
        with open(path, encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                w, l, d = r.get("winner_name"), r.get("loser_name"), r.get("tourney_date")
                if not (w and l and d):
                    continue
                try:
                    di = int(d)
                except ValueError:
                    continue
                rows.append({
                    "d": di, "w": w, "l": l,
                    "surface": r.get("surface", ""),
                    "tourney": r.get("tourney_name", ""),
                    "score": r.get("score", ""),
                    "best_of": r.get("best_of", "3"),
                })
    rows.sort(key=lambda r: r["d"])
    return rows


class History:
    """Rychly pristup k 'co hracka odehrala PRED datem X'.

    Naivni filtrovani vsech radku pro kazdy testovany zapas by znamenalo
    11 tisic x 14 tisic porovnani. Misto toho se predpocitaji pro kazdou
    hracku setridene seznamy dat + kumulativni soucty vyher, takze dotaz
    'forma pred datem' je jen binarni hledani.
    """

    def __init__(self, rows):
        self.dates = defaultdict(list)   # hracka -> [datum, ...] vzestupne
        self.wins = defaultdict(list)    # hracka -> [1/0, ...] stejne poradi
        self.cumwins = {}                # hracka -> prefixovy soucet vyher
        self.h2h_dates = defaultdict(list)
        self.h2h_wins = defaultdict(list)  # 1 = vyhrala prvni (abecedne) hracka
        self.h2h_cum = {}

        for r in rows:
            for player, won in ((r["w"], 1), (r["l"], 0)):
                self.dates[player].append(r["d"])
                self.wins[player].append(won)
            pair = tuple(sorted((r["w"], r["l"])))
            self.h2h_dates[pair].append(r["d"])
            self.h2h_wins[pair].append(1 if r["w"] == pair[0] else 0)

        for player, wins in self.wins.items():
            acc, out = 0, [0]
            for v in wins:
                acc += v
                out.append(acc)
            self.cumwins[player] = out
        for pair, wins in self.h2h_wins.items():
            acc, out = 0, [0]
            for v in wins:
                acc += v
                out.append(acc)
            self.h2h_cum[pair] = out

    def n_before(self, player, cutoff):
        return bisect.bisect_left(self.dates.get(player, []), cutoff)

    def overall(self, player, cutoff):
        n = self.n_before(player, cutoff)
        if n == 0:
            return None, 0
        return self.cumwins[player][n] / n, n

    def form(self, player, cutoff, window=15):
        n = self.n_before(player, cutoff)
        if n == 0:
            return None, 0
        lo = max(0, n - window)
        wins = self.cumwins[player][n] - self.cumwins[player][lo]
        return wins / (n - lo), n - lo

    def h2h(self, a, b, cutoff):
        pair = tuple(sorted((a, b)))
        dates = self.h2h_dates.get(pair, [])
        n = bisect.bisect_left(dates, cutoff)
        if n == 0:
            return None, None, 0
        wins_first = self.h2h_cum[pair][n]
        wr_first = wins_first / n
        if pair[0] == a:
            return wr_first, 1 - wr_first, n
        return 1 - wr_first, wr_first, n


def model_prob(hist, a, b, cutoff):
    """Pravdepodobnost, ze vyhraje hracka 'a'. Stejny vzorec jako
    predict_tennis_match() v backtest.py (0.5 forma + 0.3 h2h + 0.2 celkove),
    ale pocitany efektivne a vzdy jen z dat pred 'cutoff'."""
    form_a, _ = hist.form(a, cutoff)
    form_b, _ = hist.form(b, cutoff)
    ov_a, na = hist.overall(a, cutoff)
    ov_b, nb = hist.overall(b, cutoff)
    if ov_a is None or ov_b is None:
        return None, na, nb
    h2h_a, h2h_b, _ = hist.h2h(a, b, cutoff)
    if h2h_a is None:
        h2h_a, h2h_b = ov_a, ov_b
    score_a = 0.5 * (form_a if form_a is not None else 0.5) + 0.3 * h2h_a + 0.2 * ov_a
    score_b = 0.5 * (form_b if form_b is not None else 0.5) + 0.3 * h2h_b + 0.2 * ov_b
    total = score_a + score_b
    if total <= 0:
        return None, na, nb
    return score_a / total, na, nb


# ---------------------------------------------------------------- Elo

# Elo je standardni zpusob, jak merit silu hrace v tenise (pouziva ho i Jeff
# Sackmann, autor nasich dat). Oproti nasemu vzorci "forma + h2h + win rate"
# ma dve zasadni vyhody:
#   1. Zohlednuje, JAK SILNY byl souper. Vyhra nad svetovou dvojkou se v nasem
#      win rate pocita stejne jako vyhra nad hrackou z 300. mista - v Elu ne.
#   2. Je to jedno cislo, ktere se prubezne updatuje, takze automaticky
#      "zapomina" stara data bez rucniho okna poslednich 15 zapasu.
#
# K-faktor podle Sackmanna: K = 250 / (pocet_zapasu + 5)^0.4 - zacatecnice
# se hybou rychle (malo informaci), zkusene hracky pomalu.

ELO_START = 1500.0
SURFACE_WEIGHT = 0.5  # vaha povrchove specifickeho Ela proti celkovemu


def _k_factor(n):
    return 250.0 / ((n + 5) ** 0.4)


class EloHistory:
    """Prubezne pocita Elo pres vsechny zapasy chronologicky a pamatuje si
    casovou osu, aby se dalo zpetne zjistit 'jake mela hracka Elo PRED
    datem X'. Elo je sekvencni, takze unik informace z budoucnosti je
    vylouceny uz principem - rating po zapase zavisi jen na zapasech, ktere
    mu predchazely."""

    def __init__(self, rows):
        self.timeline = defaultdict(list)       # hracka -> [(datum, rating_po)]
        self.surf_timeline = defaultdict(list)  # (hracka, povrch) -> [(datum, rating_po)]
        ratings = defaultdict(lambda: ELO_START)
        counts = defaultdict(int)
        surf_ratings = defaultdict(lambda: ELO_START)
        surf_counts = defaultdict(int)

        for r in rows:
            w, l, d, surf = r["w"], r["l"], r["d"], r["surface"] or "?"
            rw, rl = ratings[w], ratings[l]
            exp_w = 1.0 / (1.0 + 10 ** ((rl - rw) / 400.0))
            kw, kl = _k_factor(counts[w]), _k_factor(counts[l])
            ratings[w] = rw + kw * (1.0 - exp_w)
            ratings[l] = rl - kl * (1.0 - exp_w)
            counts[w] += 1
            counts[l] += 1
            self.timeline[w].append((d, ratings[w]))
            self.timeline[l].append((d, ratings[l]))

            kws, kls = (w, surf), (l, surf)
            sw, sl = surf_ratings[kws], surf_ratings[kls]
            exp_sw = 1.0 / (1.0 + 10 ** ((sl - sw) / 400.0))
            ksw, ksl = _k_factor(surf_counts[kws]), _k_factor(surf_counts[kls])
            surf_ratings[kws] = sw + ksw * (1.0 - exp_sw)
            surf_ratings[kls] = sl - ksl * (1.0 - exp_sw)
            surf_counts[kws] += 1
            surf_counts[kls] += 1
            self.surf_timeline[kws].append((d, surf_ratings[kws]))
            self.surf_timeline[kls].append((d, surf_ratings[kls]))

    @staticmethod
    def _at(tl, cutoff):
        """Rating po poslednim zapase PRED cutoff. Zadny takovy zapas =>
        startovni hodnota."""
        if not tl:
            return ELO_START, 0
        dates = [t[0] for t in tl]
        i = bisect.bisect_left(dates, cutoff)
        if i == 0:
            return ELO_START, 0
        return tl[i - 1][1], i

    def prob(self, a, b, cutoff, surface=None):
        ra, na = self._at(self.timeline.get(a, []), cutoff)
        rb, nb = self._at(self.timeline.get(b, []), cutoff)
        if surface:
            sa, nsa = self._at(self.surf_timeline.get((a, surface), []), cutoff)
            sb, nsb = self._at(self.surf_timeline.get((b, surface), []), cutoff)
            # povrchove Elo se pouzije jen tam, kde ho je na cem postavit
            if nsa >= 5 and nsb >= 5:
                ra = (1 - SURFACE_WEIGHT) * ra + SURFACE_WEIGHT * sa
                rb = (1 - SURFACE_WEIGHT) * rb + SURFACE_WEIGHT * sb
        return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0)), na, nb


# ---------------------------------------------------------------- spojeni

def join_matches(sack_rows, odds_rows, verbose=False):
    """Prirad kazdemu radku s kurzy odpovidajici zapas ze Sackmannovych dat."""
    by_pair = defaultdict(list)
    for r in sack_rows:
        ka, kb = sackmann_key(r["w"]), sackmann_key(r["l"])
        if not ka or not kb:
            continue
        by_pair[tuple(sorted((ka, kb)))].append(r)

    joined = []
    stats = {"total": 0, "no_key": 0, "no_pair": 0, "no_window": 0,
             "winner_conflict": 0, "ambiguous": 0, "ok": 0}

    for o in odds_rows:
        stats["total"] += 1
        k1, k2 = odds_key(o["Player_1"]), odds_key(o["Player_2"])
        if not k1 or not k2 or k1 == k2:
            stats["no_key"] += 1
            continue
        cands = by_pair.get(tuple(sorted((k1, k2))))
        if not cands:
            stats["no_pair"] += 1
            continue
        md = date_to_int(o["Date"])
        lo = shift_days(md, -WINDOW_AFTER_DAYS)
        hi = shift_days(md, WINDOW_BEFORE_DAYS)
        inwin = [c for c in cands if lo <= c["d"] <= hi]
        if not inwin:
            stats["no_window"] += 1
            continue
        if len(inwin) > 1:
            # dve utkani tech stejnych hracek v okne - vyber to s blizsim datem
            inwin.sort(key=lambda c: abs(c["d"] - md))
            if abs(inwin[0]["d"] - md) == abs(inwin[1]["d"] - md):
                stats["ambiguous"] += 1
                continue
        s = inwin[0]

        # Kontrola konzistence: vitez podle kurzovych dat musi odpovidat
        # vitezi podle Sackmanna. Kdyz ne, je to spatne spojeny zapas nebo
        # chyba ve zdroji - radsi zahodit nez tim kontaminovat vysledek.
        wk = odds_key(o["Winner"])
        if wk == k1:
            odds_winner_is_p1 = True
        elif wk == k2:
            odds_winner_is_p1 = False
        else:
            stats["winner_conflict"] += 1
            continue
        sack_winner_key = sackmann_key(s["w"])
        if (sack_winner_key == k1) != odds_winner_is_p1:
            stats["winner_conflict"] += 1
            continue

        name1 = s["w"] if sack_winner_key == k1 else s["l"]
        name2 = s["l"] if sack_winner_key == k1 else s["w"]
        joined.append({
            "date": o["Date"], "cutoff": s["d"],
            "name1": name1, "name2": name2,
            "p1_won": odds_winner_is_p1,
            "odd1": float(o["Odd_1"]), "odd2": float(o["Odd_2"]),
            "surface": s["surface"], "tourney": s["tourney"],
            "round": o.get("Round", ""),
        })
        stats["ok"] += 1

    if verbose:
        print("Spojeni kurzu se zapasovymi statistikami:")
        for k, label in [("total", "radku s kurzy"), ("ok", "uspesne spojeno"),
                         ("no_pair", "dvojice nenalezena v Sackmannovi"),
                         ("no_window", "dvojice existuje, ale ne v casovem okne"),
                         ("no_key", "nerozpoznane jmeno"),
                         ("ambiguous", "nejednoznacne (dva zapasy stejne blizko)"),
                         ("winner_conflict", "nesouhlasil vitez - zahozeno")]:
            print("  %-45s %6d" % (label, stats[k]))
        print("  %-45s %5.1f %%" % ("uspesnost spojeni", 100.0 * stats["ok"] / max(1, stats["total"])))
        print()
    return joined


# ---------------------------------------------------------------- sazeni

def devig(odd1, odd2):
    q1, q2 = 1.0 / odd1, 1.0 / odd2
    tot = q1 + q2
    return q1 / tot, q2 / tot, tot - 1.0


class Book:
    """Uctovani jedne strategie."""

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
    def roi(self):
        return (self.returned - self.staked) / self.staked * 100.0 if self.staked else 0.0

    def line(self):
        hr = 100.0 * self.wins / self.n if self.n else 0.0
        return "%-28s %6d %7d (%5.1f %%) %12.0f %12.0f %+8.1f %%" % (
            self.label, self.n, self.wins, hr, self.staked, self.returned, self.roi)


def run(min_edge, min_hist, year=None, diagnostika=False, model="forma"):
    if not os.path.exists(ODDS_PATH):
        print("CHYBA: chybi soubor s kurzy %s" % ODDS_PATH)
        print("Spust nejdriv: python3 fetch_tennis_odds.py")
        sys.exit(1)

    sack = load_sackmann_wta()
    with open(ODDS_PATH, encoding="utf-8") as f:
        odds_rows = list(csv.DictReader(f))
    if year:
        odds_rows = [r for r in odds_rows if r["Date"][:4] == str(year)]

    print("Sackmannovych zapasu WTA: %d | radku s kurzy: %d%s\n"
          % (len(sack), len(odds_rows), " (rok %s)" % year if year else ""))

    joined = join_matches(sack, odds_rows, verbose=True)
    if not joined:
        print("Nic se nespojilo - nejde pokracovat.")
        return

    hist = History(sack)
    elo = EloHistory(sack) if model in ("elo", "elo-povrch") else None
    use_surface = model == "elo-povrch"

    def probability(m):
        """Vrati (p_vyhra_name1, pocet_zapasu_name1, pocet_zapasu_name2)."""
        if elo is None:
            return model_prob(hist, m["name1"], m["name2"], m["cutoff"])
        p, _, _ = elo.prob(m["name1"], m["name2"], m["cutoff"],
                           m["surface"] if use_surface else None)
        n1 = hist.n_before(m["name1"], m["cutoff"])
        n2 = hist.n_before(m["name2"], m["cutoff"])
        return p, n1, n2

    print("Model: %s\n" % {
        "forma": "forma+h2h+win rate (stejny jako aggregate_stats.py)",
        "elo": "Elo (celkove)",
        "elo-povrch": "Elo (celkove %.0f %% + povrchove %.0f %%)" % (
            (1 - SURFACE_WEIGHT) * 100, SURFACE_WEIGHT * 100),
    }[model])

    books = {
        "hodnota": Book("hodnota (edge>=%.0f%%, flat)" % (min_edge * 100)),
        "kelly": Book("hodnota, Kelly %.2f" % KELLY_FRACTION),
        "favorit": Book("baseline: vzdy favorit trhu"),
        "model": Book("baseline: vzdy tip modelu"),
    }

    evaluated = 0
    skipped_hist = 0
    skipped_odds = 0
    model_correct = 0
    market_correct = 0
    edge_buckets = defaultdict(lambda: [0, 0, 0.0, 0.0])  # n, wins, sum p_model, sum p_mkt
    calib = defaultdict(lambda: [0, 0])
    overround_sum = 0.0

    for m in joined:
        p_model1, n1, n2 = probability(m)
        if p_model1 is None or n1 < min_hist or n2 < min_hist:
            skipped_hist += 1
            continue
        o1, o2 = m["odd1"], m["odd2"]
        if not (ODDS_MIN <= o1 <= ODDS_MAX and ODDS_MIN <= o2 <= ODDS_MAX):
            skipped_odds += 1
            continue
        p_mkt1, p_mkt2, over = devig(o1, o2)
        overround_sum += over
        evaluated += 1
        won1 = m["p1_won"]

        if (p_model1 >= 0.5) == won1:
            model_correct += 1
        if (p_mkt1 >= 0.5) == won1:
            market_correct += 1

        # kalibrace modelu
        calib[round(p_model1 * 10) / 10][0] += 1
        if won1:
            calib[round(p_model1 * 10) / 10][1] += 1

        # baseliny
        if o1 <= o2:
            books["favorit"].bet(FLAT_STAKE, o1, won1)
        else:
            books["favorit"].bet(FLAT_STAKE, o2, not won1)
        if p_model1 >= 0.5:
            books["model"].bet(FLAT_STAKE, o1, won1)
        else:
            books["model"].bet(FLAT_STAKE, o2, not won1)

        # hodnotove sazky - hleda se edge na OBOU stranach
        for p_model, p_mkt, odds, won in ((p_model1, p_mkt1, o1, won1),
                                          (1 - p_model1, p_mkt2, o2, not won1)):
            edge = p_model - p_mkt
            if not (min_edge <= edge <= EDGE_MAX):
                continue
            books["hodnota"].bet(FLAT_STAKE, odds, won)
            b = (p_model * odds - 1.0) / (odds - 1.0)  # Kellyho podil banky
            stake = max(0.0, b) * KELLY_FRACTION * 1000.0
            if stake > 0:
                books["kelly"].bet(stake, odds, won)
            bk = min(0.20, (int(edge * 100) // 4) * 0.04)
            eb = edge_buckets[bk]
            eb[0] += 1
            eb[1] += 1 if won else 0
            eb[2] += p_model
            eb[3] += p_mkt

    print("Vyhodnoceno zapasu: %d" % evaluated)
    print("  preskoceno pro malou historii (<%d zapasu): %d" % (min_hist, skipped_hist))
    print("  preskoceno pro kurz mimo pasmo %.2f-%.1f: %d" % (ODDS_MIN, ODDS_MAX, skipped_odds))
    if evaluated:
        print("  prumerna marze sazkovky (overround): %.1f %%" % (100.0 * overround_sum / evaluated))
    print()

    print("KDO LIP TIPUJE VITEZE (na stejnych %d zapasech)" % evaluated)
    if evaluated:
        print("  nas model:  %.1f %%" % (100.0 * model_correct / evaluated))
        print("  trh (kurz): %.1f %%" % (100.0 * market_correct / evaluated))
    print()

    print("VYSLEDKY SAZENI")
    print("%-28s %6s %7s %8s %12s %12s %10s" % ("strategie", "sazek", "vyher", "", "vsazeno", "vyplaceno", "ROI"))
    print("-" * 96)
    for key in ("hodnota", "kelly", "favorit", "model"):
        b = books[key]
        if b.n:
            print(b.line())
        else:
            print("%-28s %6d   (zadna sazka neprosla filtrem)" % (b.label, 0))
    print()

    if diagnostika:
        print("KALIBRACE MODELU (rika model pravdu o svych procentech?)")
        print("%-12s %8s %10s %10s" % ("model rika", "zapasu", "realne", "rozdil"))
        for bucket in sorted(calib):
            n, w = calib[bucket]
            if n < 20:
                continue
            real = 100.0 * w / n
            print("%-12s %8d %9.1f %% %+9.1f" % ("%.0f %%" % (bucket * 100), n, real, real - bucket * 100))
        print()

        if edge_buckets:
            print("JE EDGE SKUTECNY? (u hodnotovych sazek podle velikosti edge)")
            print("%-14s %7s %12s %12s %12s" % ("edge", "sazek", "model rika", "trh rika", "realne"))
            for bucket in sorted(edge_buckets):
                n, w, sm, sk = edge_buckets[bucket]
                if n < 15:
                    continue
                print("%-14s %7d %11.1f %% %11.1f %% %11.1f %%"
                      % ("%.0f-%.0f %%" % (bucket * 100, bucket * 100 + 4), n,
                         100.0 * sm / n, 100.0 * sk / n, 100.0 * w / n))
            print()
            print("Ctvrty sloupec ('realne') je ten rozhodujici: pokud je blizsi")
            print("tretimu ('trh rika') nez druhemu ('model rika'), model edge jen")
            print("predstira - trh mel pravdu a sazka je ztratova.")
            print()


# ---------------------------------------------- ma model vubec nejakou informaci?

def run_added_value(min_hist, year=None):
    """NEJOSTREJSI MOZNY TEST: pridava model k trhu nejakou informaci?

    Predchozi test merí, jestli se da podle modelu vydelat. Tenhle merí neco
    jemnejsiho a dulezitejsiho: jestli model VI NECO, co trh nevi - i kdyby
    toho bylo malo.

    Delá se to tak, ze se michaji predpovedi: p = (1-w) * trh + w * model.
    Kdyz i maly podil modelu (w = 0.05 az 0.2) ZLEPSI presnost predpovedi
    proti cistemu trhu, znamena to, ze model drzí nejakou informaci, kterou
    trh nema zacenenou - a pak ma smysl hledat, jak ji zpenezit. Kdyz kazde
    primichani modelu presnost ZHORSI, model nema nic navic a cela myslenka
    "predbehnu trh vlastnim modelem" je u tohoto typu zapasu mrtva.

    Meri se dvema standardnimi merami presnosti pravdepodobnostnich
    predpovedi (u obou plati: nizsi = lepsi):
      - log loss: trestá hlavne sebevedome omyly (rict 95 % a mylit se)
      - Brier:    prumerna kvadraticka chyba, citlivejsi na stred
    """
    sack = load_sackmann_wta()
    with open(ODDS_PATH, encoding="utf-8") as f:
        odds_rows = list(csv.DictReader(f))
    if year:
        odds_rows = [r for r in odds_rows if r["Date"][:4] == str(year)]

    joined = join_matches(sack, odds_rows, verbose=False)
    hist = History(sack)
    elo = EloHistory(sack)

    samples = []  # (p_trh, p_forma, p_elo, p_elo_povrch, vyhrala_1)
    for m in joined:
        p_form, n1, n2 = model_prob(hist, m["name1"], m["name2"], m["cutoff"])
        if p_form is None or n1 < min_hist or n2 < min_hist:
            continue
        o1, o2 = m["odd1"], m["odd2"]
        if not (ODDS_MIN <= o1 <= ODDS_MAX and ODDS_MIN <= o2 <= ODDS_MAX):
            continue
        p_mkt, _, _ = devig(o1, o2)
        p_elo, _, _ = elo.prob(m["name1"], m["name2"], m["cutoff"])
        p_elos, _, _ = elo.prob(m["name1"], m["name2"], m["cutoff"], m["surface"])
        samples.append((p_mkt, p_form, p_elo, p_elos, 1 if m["p1_won"] else 0))

    if not samples:
        print("Zadne pouzitelne zapasy.")
        return

    def scores(ps, ys):
        import math
        eps = 1e-12
        ll = -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))
                  for p, y in zip(ps, ys)) / len(ys)
        br = sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)
        return ll, br

    ys = [s[4] for s in samples]
    print("Zapasu v testu: %d\n" % len(samples))

    base_ll, base_br = scores([s[0] for s in samples], ys)
    print("SAMOSTATNE (nizsi = lepsi)")
    print("%-34s %10s %10s" % ("predpoved", "log loss", "Brier"))
    print("-" * 56)
    print("%-34s %10.4f %10.4f   <-- co musime porazit" % ("trh (odvigovany kurz)", base_ll, base_br))
    for idx, label in ((1, "forma+h2h+win rate"), (2, "Elo"), (3, "Elo + povrch")):
        ll, br = scores([s[idx] for s in samples], ys)
        print("%-34s %10.4f %10.4f" % (label, ll, br))
    print()

    print("SMES TRHU A MODELU: p = (1-w) * trh + w * model")
    print("Kdyby mel model informaci navic, nejaka vaha w > 0 by prekonala radek w = 0.")
    print()
    print("%-6s %14s %14s %14s" % ("w", "forma", "Elo", "Elo+povrch"))
    print("-" * 52)
    best = {}
    for w in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50):
        cells = []
        for idx, key in ((1, "forma"), (2, "elo"), (3, "elos")):
            ps = [(1 - w) * s[0] + w * s[idx] for s in samples]
            ll, _ = scores(ps, ys)
            cells.append(ll)
            if key not in best or ll < best[key][1]:
                best[key] = (w, ll)
        mark = "   <-- cisty trh" if w == 0.0 else ""
        print("%-6.2f %14.4f %14.4f %14.4f%s" % (w, cells[0], cells[1], cells[2], mark))
    print()
    print("ZAVER TOHOTO TESTU")
    for key, label in (("forma", "forma+h2h+win rate"), ("elo", "Elo"), ("elos", "Elo + povrch")):
        w, ll = best[key]
        if w == 0.0:
            print("  %-22s zadna vaha trh nezlepsila -> model nema informaci navic." % label)
        else:
            gain = base_ll - ll
            print("  %-22s nejlepsi w = %.2f, log loss %.4f (zlepseni %.4f) -> drobna informace navic."
                  % (label, w, ll, gain))


# ---------------------------------------------- bias podle vyse kurzu / povrchu / kola

def run_segments(min_hist, year=None):
    """Rozpada vysledek 'vzdy sazet favorita' podle segmentu - vyska kurzu,
    povrch, kolo turnaje. Odpovida na otazku: existuje aspon KOUSEK trhu, kde
    je marze mensi nebo kde nas model prekvapive vyhrava, i kdyz v celku
    prohrava?

    Tohle je DULEZITY navazujici test na run() - ten rekne "celkove proheles",
    tenhle rekne "a kdyby ses omezil jen na tohle, bylo by to jine?" (spoiler:
    ne, je to vsude podobne nebo hur - viz 'favourite-longshot bias' nize).
    """
    sack = load_sackmann_wta()
    with open(ODDS_PATH, encoding="utf-8") as f:
        odds_rows = list(csv.DictReader(f))
    if year:
        odds_rows = [r for r in odds_rows if r["Date"][:4] == str(year)]
    joined = join_matches(sack, odds_rows)
    hist = History(sack)

    def bucket_odd(o):
        for hi in (1.2, 1.4, 1.6, 2.0, 2.5, 3.5, 5.0, 8.0, 15.0):
            if o <= hi:
                return hi
        return 99.0

    by_odd, by_surface, by_round = defaultdict(lambda: [0, 0, 0.0, 0.0]), \
        defaultdict(lambda: [0, 0, 0.0, 0.0]), defaultdict(lambda: [0, 0, 0.0, 0.0])
    n_eval = 0

    for m in joined:
        p, n1, n2 = model_prob(hist, m["name1"], m["name2"], m["cutoff"])
        if p is None or n1 < min_hist or n2 < min_hist:
            continue
        o1, o2 = m["odd1"], m["odd2"]
        if not (ODDS_MIN <= o1 <= ODDS_MAX and ODDS_MIN <= o2 <= ODDS_MAX):
            continue
        n_eval += 1
        for odd, won in ((o1, m["p1_won"]), (o2, not m["p1_won"])):
            b = by_odd[bucket_odd(odd)]
            b[0] += 1
            b[1] += 1 if won else 0
            b[2] += FLAT_STAKE
            b[3] += FLAT_STAKE * odd if won else 0
        fav_odd, fav_won = (o1, m["p1_won"]) if o1 <= o2 else (o2, not m["p1_won"])
        for d, k in ((by_surface, m["surface"] or "?"), (by_round, m["round"] or "?")):
            b = d[k]
            b[0] += 1
            b[1] += 1 if fav_won else 0
            b[2] += FLAT_STAKE
            b[3] += FLAT_STAKE * fav_odd if fav_won else 0

    def roi(b):
        return (b[3] - b[2]) / b[2] * 100.0 if b[2] else 0.0

    print("Zapasu v testu: %d\n" % n_eval)
    print("A) SAZKA NA KAZDOU STRANU PODLE VYSE KURZU (hleda 'favourite-longshot bias' -")
    print("   znamy jev ze sazkove literatury, kdy sazkari systematicky preplaceji outsidery)")
    print("%-10s %8s %12s %10s" % ("kurz do", "sazek", "uspesnost", "ROI"))
    print("-" * 44)
    for k in sorted(by_odd):
        b = by_odd[k]
        if b[0] < 50:
            continue
        print("%-10.1f %8d %10.1f %% %+8.1f %%" % (k, b[0], 100.0 * b[1] / b[0], roi(b)))
    print()

    print("B) VZDY SAZET FAVORITA TRHU, PODLE POVRCHU")
    for k in sorted(by_surface, key=lambda x: -by_surface[x][0]):
        b = by_surface[k]
        if b[0] < 100:
            continue
        print("  %-10s n=%5d  uspesnost %5.1f %%  ROI %+6.1f %%" % (k, b[0], 100.0 * b[1] / b[0], roi(b)))
    print()

    print("C) VZDY SAZET FAVORITA TRHU, PODLE KOLA")
    for k in sorted(by_round, key=lambda x: -by_round[x][0]):
        b = by_round[k]
        if b[0] < 100:
            continue
        print("  %-16s n=%5d  uspesnost %5.1f %%  ROI %+6.1f %%" % (k, b[0], 100.0 * b[1] / b[0], roi(b)))
    print()
    print("ZAVER: pokud ROI vychazi zaporne VSUDE (vsechny kurzove pasma, vsechny")
    print("povrchy, vsechny kola), neni to smula na jednom segmentu, ale marze")
    print("sazkove kancelare rozprostrena rovnomerne pres cely trh - nelze ji")
    print("obejit tim, ze se vyberou jen 'ty spravne' zapasy.")


def main():
    ap = argparse.ArgumentParser(description="Test sazkove vyhody tenisoveho modelu proti realnym kurzum (WTA 2021-2025).")
    ap.add_argument("--min-edge", type=float, default=0.04,
                    help="minimalni edge proti trhu, aby se sazelo (vychozi 0.04 = 4 procentni body)")
    ap.add_argument("--min-hist", type=int, default=15,
                    help="minimalni pocet drive odehranych zapasu u OBOU hracek (vychozi 15)")
    ap.add_argument("--rok", type=int, default=None, help="omezit na jeden rok")
    ap.add_argument("--model", choices=["forma", "elo", "elo-povrch"], default="forma",
                    help="ktery model testovat: forma (vychozi, stejny jako aggregate_stats.py), "
                         "elo, nebo elo-povrch (Elo s povrchovou slozkou)")
    ap.add_argument("--segmenty", action="store_true",
                    help="rozpad vysledku podle vyse kurzu/povrchu/kola (hleda favourite-longshot bias)")
    ap.add_argument("--pridana-hodnota", action="store_true",
                    help="zmeri, jestli model pridava k trhu jakoukoli informaci (log loss / Brier)")
    ap.add_argument("--diagnostika", action="store_true",
                    help="navic kalibrace modelu a rozpad podle velikosti edge")
    a = ap.parse_args()
    if a.segmenty:
        run_segments(a.min_hist, a.rok)
    elif a.pridana_hodnota:
        run_added_value(a.min_hist, a.rok)
    else:
        run(a.min_edge, a.min_hist, a.rok, a.diagnostika, a.model)


if __name__ == "__main__":
    main()
