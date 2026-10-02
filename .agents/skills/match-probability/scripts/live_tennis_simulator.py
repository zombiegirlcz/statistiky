#!/usr/bin/env python3
"""
Živý TENISOVÝ in-play simulátor - sleduje průběh KAŽDÉHO právě běžícího
zápasu a staví na ně FIKTIVNÍ tikety (žádné skutečné peníze, rozpočet je
1000 vymyšlených "mincí").

Je to výhradně tenisový nástroj. Fotbalová obdoba (na historických datech)
je `ticket_builder.py`, ta s tímhle nijak nesouvisí.

ZDROJE DAT (všechno skutečná data, nic simulovaného):
  - Live Tennis API (livetennisapi.com, klíč LIVE_TENNIS_API_KEY v ~/.env) -
    právě probíhající zápasy včetně skóre na úrovni GEMŮ i BODŮ a informace,
    kdo podává.
  - The Odds API (the-odds-api.com, klíč ODDS_API_KEY v ~/.env) - skutečné
    živé sázkové kurzy (pokrytí je menší než u Live Tennis API, hlavně
    ATP/WTA tour, ne Challenger/ITF).
  - Vlastní historická data (tenis/prubeh/, Match Charting Project) přes
    game_flow.py - hold/break rate hráčů.

REŽIMY:
  1. `watch`   - hlavní režim. Stáhne VŠECHNY živé zápasy, u každého zapíše
                 snímek stavu do live_progress_log.jsonl, porovná ho
                 s minulým snímkem a vypíše, CO SE MEZITÍM STALO (brejk,
                 uzavřený set, tiebreak, setbol/mečbol, výrazný posun
                 pravděpodobnosti, změna favorita). Kde zároveň vidí
                 SILNÉHO FAVORITA (viz níže) a má volný rozpočet, založí
                 fiktivní tiket.
  2. `scan`    - jen alias na `watch` (zpětná kompatibilita).
  3. `status`  - rychlý přehled banky a tiketů, BEZ volání API.

Vyhodnocování sázek a připisování do banky dělá SAMOSTATNÝ skript
`bet_evaluator.py` (spouštěj ho zvlášť, viz AGENT_NAVOD.md).

CÍL A STRATEGIE (DŮLEŽITÁ ZMĚNA oproti dřívější verzi): cílem NENÍ porazit
trh (viz `references/metodika.md` - poctivý backtest ukázal, že tenhle model
žádnou prokázanou výhodu nad trhem nemá a mít nebude). Cílem je, aby banka
**mezi jednotlivými tikety spíš rostla, než klesala** - tedy vysoký podíl
vyhraných tiketů, i za cenu nižšího zisku na vyhraném tiketu. Proto se sází
výhradně na SILNÉ FAVORITY (viz FAV_MODEL_MIN/FAV_MARKET_MIN/FAV_MAX_ODDS
níže) - ti v historických datech vyhrávají nejčastěji (naměřeno: u kurzů do
1,2 vychází úspěšnost v řádu 90 % a ROI je nejméně záporné ze všech
kurzových pásem, viz metodika.md). I tak: sázková marže znamená, že se
OČEKÁVANÁ hodnota každého tiketu nikdy nedostane nad nulu - "spíš roste než
klesá" je o tom, že většina JEDNOTLIVÝCH tiketů vyhraje, ne o tom, že se tím
porazí matematika sázení. Řekni tohle uživateli na rovinu, nikdy to
nezamlčuj ani neslibuj zaručený růst.

ROZPOČET: 1000 fiktivních mincí. Vklad je STAKE_PCT z aktuální banky
(minimálně MIN_STAKE), a zároveň platí strop na souběžnou expozici
(MAX_EXPOSURE_PCT) - když je v nevyřízených tiketech už moc peněz, nové
se nezakládají. Banka se nikdy nepočítá odhadem, vždy se dopočítá z logu.

DŮLEŽITÁ OMEZENÍ (poctivé nálezy z dřívějšího ladění):
  - Mince jsou FIKTIVNÍ. Skript neovládá žádný sázkový účet a nikdy
    nevsadí skutečné peníze.
  - Model pracuje na úrovni gemů (hold/break rate), ne bod po bodu -
    nevidí aktuální zranění, únavu ani počasí. Proto má pravděpodobnost
    podlahu a strop (MIN_PROB/MAX_PROB), aby nikdy netvrdil "100 % jisté".
  - MIN_HOLD_N chrání proti nesmyslným odhadům u málo zaznamenaných hráčů.
  - FAV_MARKET_MIN vyžaduje, aby i SKUTEČNÝ trh (nezávislý zdroj) viděl
    stejného hráče jako jasného favorita - to je ochrana proti tomu, aby
    chyba nebo zastaralost v našem čtení živého skóre (přesně tohle se
    stalo u zápasu Bublik-Mensik 1. 10. 2026, viz references/metodika.md)
    vyrobila sázku na špatnou stranu. Model a trh se tu NEPOROVNÁVAJÍ kvůli
    hledání edge, ale kvůli vzájemnému ověření.
  - NIKDY nesmí vzniknout "trh" jako zpožděná kopie vlastního modelu - to je
    tautologie, která vyrobí zisk i při nulové předvídací schopnosti (viz
    metodika.md). Tenhle skript proto porovnává výhradně se skutečnými kurzy.

Použití:
    python3 live_tennis_simulator.py watch
    python3 live_tennis_simulator.py status
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
import game_flow as gf  # noqa: E402
import odds_compare as oc  # noqa: E402
import bookmaker as bm  # noqa: E402 - jednotná vrstva kurzů/sázení (SX.bet)

LIVE_API_BASE = "https://api.livetennisapi.com/api/public/v1"
_DATA_DIR = os.path.join(_SCRIPT_DIR, "..")
LOG_PATH = os.path.join(_DATA_DIR, "live_bets_log.jsonl")
PROGRESS_PATH = os.path.join(_DATA_DIR, "live_progress_log.jsonl")

MIN_HOLD_N = 20          # min. počet dřívějších podávacích gemů KAŽDÉHO hráče
MIN_PROB = 0.02          # nikdy netvrdit míň než 2 % - skutečná míra skreče/walkoveru
MAX_PROB = 0.98          # je v našich datech 3,59 % všech zápasů (30 885 zápasů)

# Strategie "silný favorit" (cíl: ať banka mezi tikety spíš roste než klesá,
# ne porazit trh - viz docstring výš). Sází se jen když SE SHODNOU oba
# nezávislé zdroje - náš model i skutečný trh:
FAV_MODEL_MIN = 0.75     # náš model musí hráče vidět aspoň na 75 % šanci
FAV_MARKET_MIN = 0.65    # a skutečný trh ho taky musí vidět jako jasného favorita
FAV_MAX_ODDS = 1.60      # kurz nad tohle už není "bezpečný" favorit, nesázet

# SET-level strategie (vítěz AKTUÁLNÍHO setu, SX.bet trhy 202/203/204).
SET_FAV_MODEL_MIN = 0.62
SET_FAV_MARKET_MIN = 0.55
SET_FAV_MAX_ODDS = 2.00

STARTING_BANK = 1000.0   # rozpočet ve fiktivních mincích
STAKE_PCT = 0.02         # vklad = 2 % aktuální banky
MIN_STAKE = 10.0         # pod tohle se nesází (odpovídá minimálnímu vkladu u sázkovek)
MAX_EXPOSURE_PCT = 0.25  # max. podíl banky vázaný v nevyřízených tiketech zároveň

# STUPŇOVANÉ SÁZENÍ podle JISTOTY (uživatel: "tutovka klidně all-in").
# Standardní favorit = malý vklad (nízký kurz = malý zisk, nemá smysl riskovat
# moc). Ale když se model I trh shodnou na TÉMĚŘ JISTOTĚ, vklad roste - až
# all-in. Logika: u 1.03 je výhra z 20 mincí skoro nic, kdežto riziko je malé.
CONF_STRONG_MODEL_MIN = 0.85   # silný favorit: model i trh vysoko
CONF_STRONG_MARKET_MIN = 0.80
CONF_STRONG_STAKE_PCT = 0.10   # 10 % banky
CONF_LOCK_MODEL_MIN = 0.90     # TUTOVKA: model i trh téměř jistí
CONF_LOCK_MARKET_MIN = 0.90
CONF_LOCK_MAX_ODDS = 1.10      # a kurz velmi nízký (near-lock)
CONF_LOCK_STAKE_PCT = 1.00     # ALL-IN na tutovku

BIG_PROB_SHIFT = 0.10    # od jakého posunu pravděpodobnosti to hlásit jako událost


# ---------------------------------------------------------------------------
# Systémová notifikace (NetHunter AI Operator `nh` CLI, pokud je dostupné)
# ---------------------------------------------------------------------------
def notify(title, content):
    """Pošle systémovou notifikaci přes `nh system notification`. Tohle
    prostředí běží v NetHunter AI Operator PRoot - `nh` je jeho sjednocený
    CLI bridge na Android notifikace (viz ~/nethunter_docs.md). Sdílí ji i
    `bet_evaluator.py` a `live_game_bet.py` (import live_tennis_simulator
    jako base/sim). NIKDY nesmí shodit volající skript - když `nh` chybí
    nebo selže (jiné prostředí, appka vypnutá...), jen se to potichu
    přeskočí, notifikace je bonus, ne kritická funkce."""
    try:
        # Absolutní cesta: v cronu je PATH jen /usr/bin:/bin a holé `nh`
        # (leží v /usr/local/bin) by se nenašlo - notifikace by se tiše ztratila.
        nh_bin = "/usr/local/bin/nh"
        if not os.path.exists(nh_bin):
            nh_bin = "nh"  # fallback pro prostředí, kde je nh v PATH
        subprocess.run(
            [nh_bin, "system", "notification", "-t", title, "-c", content],
            capture_output=True, timeout=10, check=False,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Live Tennis API
# ---------------------------------------------------------------------------
# ROTACE API KLÍČŮ: `LIVE_TENNIS_API_KEYS` = čárkou oddělené klíče (fallback
# jednotlivý `LIVE_TENNIS_API_KEY`). Když aktivní klíč narazí na kvótu (429)
# nebo je neplatný/odebraný (401/403), automaticky se přepne na další klíč
# v seznamu a zkusí to znovu. Fungující index se pamatuje v malém stavovém
# souboru, aby rotace přežila mezi jednotlivými spuštěními (skripty jsou
# bezstavové, běží z cronu). Vyčerpané klíče se „uzdraví" samy - stav drží
# jen PREFEROVANÝ index, ne trvalý seznam mrtvých klíčů, takže po resetu
# denní kvóty (UTC půlnoc) se příště prostě zkusí znovu.
_KEY_STATE_PATH = os.path.join(_DATA_DIR, ".live_api_key_state.json")
_QUOTA_CODES = {401, 403, 429}  # neplatný / vyčerpaný klíč -> zkus další


def _api_keys():
    raw = (os.environ.get("LIVE_TENNIS_API_KEYS")
           or os.environ.get("LIVE_TENNIS_API_KEY") or "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def _load_key_idx(n):
    try:
        with open(_KEY_STATE_PATH) as f:
            s = json.load(f)
        return int(s.get("idx", 0)) % max(n, 1)
    except Exception:
        return 0


def _save_key_idx(idx):
    try:
        with open(_KEY_STATE_PATH, "w") as f:
            json.dump({"idx": idx}, f)
    except Exception:
        pass


def _live_api_request(path, params=None):
    keys = _api_keys()
    if not keys:
        print("CHYBA: chybí LIVE_TENNIS_API_KEYS / LIVE_TENNIS_API_KEY (viz ~/.env).")
        sys.exit(1)
    import urllib.parse
    q = urllib.parse.urlencode(params or {})
    url = f"{LIVE_API_BASE}{path}" + (f"?{q}" if q else "")
    start = _load_key_idx(len(keys))
    last_err = None
    for attempt in range(len(keys)):
        idx = (start + attempt) % len(keys)
        api_key = keys[idx]
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if idx != start:
                    _save_key_idx(idx)  # zapamatuj si fungující klíč
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_err = f"HTTP {e.code}: {body}"
            if e.code in _QUOTA_CODES and attempt < len(keys) - 1:
                print(f"  [rotace klíčů] klíč #{idx + 1} selhal ({e.code}) -> zkouším další")
                continue
            print(f"CHYBA Live Tennis API ({e.code}): {body}")
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f"CHYBA síťového připojení (Live Tennis API): {e}")
            sys.exit(1)
    print(f"CHYBA: všechny API klíče selhaly. Poslední: {last_err}")
    sys.exit(1)


def fetch_live_matches():
    data = _live_api_request("/matches", {"status": "live", "limit": 100})
    return data.get("data", [])


def fetch_upcoming_matches():
    """Nadchazejici zapasy (jeste nezacaly) - pro PRE-MATCH sazeni."""
    data = _live_api_request("/matches", {"status": "upcoming", "limit": 100})
    return data.get("data", [])


def fetch_match(match_id):
    return _live_api_request(f"/matches/{match_id}")


# ---------------------------------------------------------------------------
# Čtení skóre z API (pozor na strukturu, snadno se přečte špatně)
# ---------------------------------------------------------------------------
def parse_score(sc, best_of_5=False):
    """Vytáhne ze 'score' aktuální stav.

    DŮLEŽITÉ 1: pole "games" je [gemy_hráče_1_po_setech, gemy_hráče_2_po_setech],
    tedy indexované NEJDŘÍV HRÁČEM, PAK SETEM - není to [skóre_1._setu,
    skóre_2._setu]. Ověřeno na dokončeném zápase id 196994 (games=[[2,3],[6,6]],
    sets=[0,2] -> 1. set 2:6, 2. set 3:6, sedí).

    DŮLEŽITÉ 2: poslední záznam v těch seznamech NEMUSÍ být rozehraný set.
    Mezi sety (a po skončení zápasu) je to skóre setu, který už je dohraný a
    už je započítaný v "sets". Kdyby se bral jako rozehraný, model by ten set
    přiřkl někomu DRUHÝ RAZ (např. stav sety 1:1 + gemy 6:4 by spočítal jako
    2:1). Rozpoznává se to podle počtu záznamů: je-li jich víc než dohraných
    setů, poslední je rozehraný; jinak se žádný set zrovna nehraje a gemy jsou
    0:0."""
    sets_a, sets_b = sc["sets"][0], sc["sets"][1]
    games = sc.get("games") or [[], []]
    per_set_a = list(games[0]) if len(games) > 0 else []
    per_set_b = list(games[1]) if len(games) > 1 else []
    completed = sets_a + sets_b
    n = min(len(per_set_a), len(per_set_b))
    if n > completed:
        ga, gb = per_set_a[n - 1], per_set_b[n - 1]
        between_sets = False
    else:
        ga, gb = 0, 0
        between_sets = True
    return {
        "sets": [sets_a, sets_b],
        "games": [ga, gb],
        "set_scores": [per_set_a, per_set_b],
        "between_sets": between_sets,
        "points": list(sc.get("points") or ["0", "0"]),
        "server": sc.get("server"),
        "is_tiebreak": bool(sc.get("is_tiebreak")),
        "sets_to_win": 3 if best_of_5 else 2,
    }


_POINT_RANK = {"0": 0, "15": 1, "30": 2, "40": 3, "AD": 4, "A": 4}


def _point_rank(p):
    if p in _POINT_RANK:
        return _POINT_RANK[p]
    try:
        return int(p)  # tiebreak se počítá normálními čísly
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Model: match_win_prob s PODLAHOU/STROPEM
# ---------------------------------------------------------------------------
def _match_win_prob_raw(hold_a, hold_b, sa, sb, ga, gb, a_serves, sets_to_win=2):
    memo = {}

    def rec(sa, sb, ga, gb, a_serves):
        if sa == sets_to_win:
            return 1.0
        if sb == sets_to_win:
            return 0.0
        key = (sa, sb, ga, gb, a_serves)
        if key in memo:
            return memo[key]
        if ga >= 6 and ga - gb >= 2:
            res = rec(sa + 1, sb, 0, 0, a_serves)
        elif gb >= 6 and gb - ga >= 2:
            res = rec(sa, sb + 1, 0, 0, a_serves)
        elif ga == 7:
            res = rec(sa + 1, sb, 0, 0, a_serves)
        elif gb == 7:
            res = rec(sa, sb + 1, 0, 0, a_serves)
        elif ga == 6 and gb == 6:
            p_tb_a = min(0.95, max(0.05, 0.5 + 0.5 * (hold_a - hold_b)))
            res = p_tb_a * rec(sa + 1, sb, 0, 0, not a_serves) + \
                  (1 - p_tb_a) * rec(sa, sb + 1, 0, 0, not a_serves)
        else:
            p_server = hold_a if a_serves else hold_b
            if a_serves:
                res = p_server * rec(sa, sb, ga + 1, gb, not a_serves) + \
                      (1 - p_server) * rec(sa, sb, ga, gb + 1, not a_serves)
            else:
                res = p_server * rec(sa, sb, ga, gb + 1, not a_serves) + \
                      (1 - p_server) * rec(sa, sb, ga + 1, gb, not a_serves)
        memo[key] = res
        return res

    return rec(sa, sb, ga, gb, a_serves)


def match_win_prob(hold_a, hold_b, sa, sb, ga, gb, a_serves, sets_to_win=2):
    """Jako _match_win_prob_raw, ale s podlahou a stropem.

    Důvod: samotná kombinatorika považuje stav typu 6:0 6:5 za jistotu
    (pravděpodobnost prakticky 0 nebo 1), jenže ve skutečném zápase se MŮŽE
    STÁT cokoliv - zranění, nevolnost, odstoupení, diskvalifikace. V našich
    datech (tenis/atp_matches_202*.csv + wta_matches_202*.csv, 30 885 zápasů)
    končí 3,59 % všech zápasů skrečí, walkoverem nebo diskvalifikací, a potkat
    to může i vedoucího hráče. Jako podlahu/strop proto bereme zhruba polovinu
    toho čísla (2 %) - hrubý, ale daty podložený odhad, ne číslo z hlavy."""
    raw = _match_win_prob_raw(hold_a, hold_b, sa, sb, ga, gb, a_serves, sets_to_win)
    return min(MAX_PROB, max(MIN_PROB, raw))


def _set_win_prob_raw(hold_a, hold_b, ga, gb, a_serves):
    """P(A vyhraje set) ze stavu gamu ga:gb v TOMTO setu, A podava (a_serves)."""
    memo = {}

    def rec(ga, gb, a_serves):
        if ga >= 6 and ga - gb >= 2:
            return 1.0
        if gb >= 6 and gb - ga >= 2:
            return 0.0
        if ga == 7:
            return 1.0
        if gb == 7:
            return 0.0
        key = (ga, gb, a_serves)
        if key in memo:
            return memo[key]
        if ga == 6 and gb == 6:
            p_tb_a = min(0.95, max(0.05, 0.5 + 0.5 * (hold_a - hold_b)))
            res = p_tb_a * rec(ga + 1, gb, not a_serves) + \
                  (1 - p_tb_a) * rec(ga, gb + 1, not a_serves)
        else:
            p_server = hold_a if a_serves else hold_b
            if a_serves:
                res = p_server * rec(ga + 1, gb, not a_serves) + \
                      (1 - p_server) * rec(ga, gb + 1, not a_serves)
            else:
                res = p_server * rec(ga, gb + 1, not a_serves) + \
                      (1 - p_server) * rec(ga + 1, gb, not a_serves)
        memo[key] = res
        return res

    return rec(ga, gb, a_serves)


def set_win_prob(hold_a, hold_b, ga, gb, a_serves):
    """Jako _set_win_prob_raw, ale s podlahou/stropem (skreč, odstoupení)."""
    raw = _set_win_prob_raw(hold_a, hold_b, ga, gb, a_serves)
    return min(MAX_PROB, max(MIN_PROB, raw))


# ---------------------------------------------------------------------------
# Hold/break rate hráčů (z game_flow.py / Match Charting Project)
# ---------------------------------------------------------------------------
_CACHE = {}


def get_hold_rate(player_name, gender_code):
    """gender_code: 'men' nebo 'women' (jak to vrací Live Tennis API). Načtená
    data se cachují v rámci jednoho běhu - během jednoho `watch` se ptáme na
    desítky hráčů ze stejných souborů."""
    g = "m" if gender_code == "men" else "w"
    if g not in _CACHE:
        _CACHE[g] = (gf.load_matches(g), gf.load_games(g))
    matches, games = _CACHE[g]
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    hold, _break, n_hold, _n_break = gf.hold_break_rate(player_name, g, matches, games, today)
    return hold, n_hold


# ---------------------------------------------------------------------------
# Živé tržní kurzy (The Odds API) - volitelné, zápas nemusí být v nabídce
# ---------------------------------------------------------------------------
_ODDS_CACHE = None


def _all_tennis_events():
    """Stáhne události ze všech právě běžících tenisových turnajů jednou za běh
    (šetří kredity Odds API - dřív se stahovalo zvlášť pro každý zápas)."""
    global _ODDS_CACHE
    if _ODDS_CACHE is not None:
        return _ODDS_CACHE
    _ODDS_CACHE = []
    if not os.environ.get("ODDS_API_KEY"):
        return _ODDS_CACHE
    try:
        sports = oc.tennis_candidates()
    except SystemExit:
        return _ODDS_CACHE
    for s in sports:
        try:
            data, _ = oc.fetch_odds(s["key"])
        except SystemExit:
            continue
        _ODDS_CACHE.extend(data)
    return _ODDS_CACHE


def get_market_probs(name1, name2):
    """Vrátí (probs_dict, best_odds_dict), nebo (None, None), pokud zápas není
    v nabídce žádného právě běžícího tenisového turnaje na Odds API."""
    ev = oc.find_event(_all_tennis_events(), name1, name2)
    if not ev:
        return None, None
    probs = oc.devigged_probs(ev, "tenis")
    if not probs:
        return None, None
    best = {}
    for bm in ev.get("bookmakers", []):
        for mk in bm.get("markets", []):
            if mk["key"] == "h2h" and len(mk["outcomes"]) == 2:
                for o in mk["outcomes"]:
                    best[o["name"]] = max(best.get(o["name"], 0), o["price"])
    return probs, best


# ---------------------------------------------------------------------------
# Logy (JSONL - jeden řádek = jeden záznam)
# ---------------------------------------------------------------------------
def _load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # poškozený řádek radši přeskočit než spadnout
    return out


def _append_jsonl(path, entry):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_log():
    return _load_jsonl(LOG_PATH)


def append_log(entry):
    _append_jsonl(LOG_PATH, entry)


def rewrite_log(entries):
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def last_snapshots():
    """Poslední zaznamenaný snímek pro každý zápas (podle match_id)."""
    snaps = {}
    for row in _load_jsonl(PROGRESS_PATH):
        snaps[row["match_id"]] = row
    return snaps


# ---------------------------------------------------------------------------
# Rozpočet
# ---------------------------------------------------------------------------
def current_bank(log):
    """Banka se VŽDY dopočítá z logu - nikde se neukládá žádné 'aktuální' číslo,
    jediný zdroj pravdy je live_bets_log.jsonl."""
    bank = STARTING_BANK
    for e in log:
        if e["status"] == "won":
            bank += e["stake"] * (e["odds"] - 1)
        elif e["status"] == "lost":
            bank -= e["stake"]
    return bank


def pending_exposure(log):
    """Kolik mincí je zrovna vázáno v nevyřízených tiketech."""
    return sum(e["stake"] for e in log if e["status"] == "pending")


def stake_tier(model_p, market_p, odds):
    """Podle jistoty vrátí (podil_banky, nazev_urovne).

    Tutovka (model i trh >= CONF_LOCK_*, kurz <= CONF_LOCK_MAX_ODDS) = all-in.
    Silný favorit (model i trh vysoko) = vetsi vklad. Jinak standardni STAKE_PCT.
    """
    if (model_p is not None and market_p is not None and odds is not None
            and model_p >= CONF_LOCK_MODEL_MIN and market_p >= CONF_LOCK_MARKET_MIN
            and odds <= CONF_LOCK_MAX_ODDS):
        return CONF_LOCK_STAKE_PCT, "TUTOVKA (all-in)"
    if (model_p is not None and market_p is not None
            and model_p >= CONF_STRONG_MODEL_MIN and market_p >= CONF_STRONG_MARKET_MIN):
        return CONF_STRONG_STAKE_PCT, "silny favorit"
    return STAKE_PCT, "standard"


def next_stake(log, model_p=None, market_p=None, odds=None):
    """Vrátí (vklad, důvod_zamítnutí). Vklad je None, když se sázet nemá.

    Vklad se stupňuje podle jistoty (viz stake_tier) - tutovka jde all-in
    i pres normalni strop soubezne expozice (maximalni vyuziti volne banky).
    """
    bank = current_bank(log)
    if bank < MIN_STAKE:
        return None, f"rozpočet vyčerpán (banka {bank:.0f} mincí)"
    exposure = pending_exposure(log)
    pct, tier = stake_tier(model_p, market_p, odds)
    if pct >= 1.0:
        # TUTOVKA = all-in: vsad celou volnou banku (bez ohledu na strop expozice)
        free = bank - exposure
        if free < MIN_STAKE:
            return None, f"tutovka, ale volná banka je jen {free:.0f} mincí (vázáno {exposure:.0f})"
        return round(free), None
    if exposure >= bank * MAX_EXPOSURE_PCT:
        return None, (f"strop souběžné expozice ({exposure:.0f} z max "
                      f"{bank * MAX_EXPOSURE_PCT:.0f} mincí už je v nevyřízených tiketech)")
    stake = max(MIN_STAKE, round(bank * pct))
    free = min(bank - exposure, bank * MAX_EXPOSURE_PCT - exposure)
    if stake > free:
        return None, f"na tiket by zbylo jen {free:.0f} mincí (potřeba {stake:.0f})"
    return stake, None


# ---------------------------------------------------------------------------
# Detekce událostí ("co se stalo od minule")
# ---------------------------------------------------------------------------
def detect_events(prev, cur, name1, name2):
    """Porovná minulý a současný snímek a vrátí seznam slovně popsaných
    událostí. prev může být None (zápas vidíme poprvé)."""
    names = (name1, name2)
    if prev is None:
        return [f"poprvé viděn (sety {cur['sets'][0]}:{cur['sets'][1]}, "
                f"gemy {cur['games'][0]}:{cur['games'][1]})"]

    ev = []
    ps, cs = prev["sets"], cur["sets"]
    pg, cg = prev["games"], cur["games"]

    # uzavřený set - skóre se bere z dohraného setu v AKTUÁLNÍM snímku
    # (minulý snímek ukazoval stav před posledním gemem, tedy např. 5:4)
    for i in (0, 1):
        if cs[i] > ps[i]:
            set_no = cs[0] + cs[1]
            ev.append(f"{names[i]} získal {set_no}. set "
                      f"({_completed_set_score(cur, set_no)}) - "
                      f"stav na sety {cs[0]}:{cs[1]}")

    # odehrané gemy v rozehraném setu (jen když se set nezměnil a oba snímky
    # jsou z rozehraného setu - mezi sety by se "gemy 0:0 -> 1:0" chybně
    # vyhodnotilo jako brejk podle serveru, který už patří novému setu)
    if cs == ps and not prev.get("between_sets") and not cur.get("between_sets"):
        for i in (0, 1):
            if cg[i] > pg[i]:
                prev_server = prev.get("server")
                won_by_slot = i + 1
                if prev_server in (1, 2) and prev_server != won_by_slot:
                    ev.append(f"BREJK pro {names[i]} ({cg[0]}:{cg[1]})")
        if cg == [6, 6] and pg != [6, 6]:
            ev.append("tiebreak")

    # setbol / mečbol v právě hraném gemu
    sb = _break_point_label(cur, names)
    if sb:
        ev.append(sb)

    # výrazný posun pravděpodobnosti
    pp, cp = prev.get("model_p1"), cur.get("model_p1")
    if pp is not None and cp is not None:
        if abs(cp - pp) >= BIG_PROB_SHIFT:
            ev.append(f"posun šance {name1}: {pp:.0%} -> {cp:.0%}")
        if (pp - 0.5) * (cp - 0.5) < 0:
            ev.append(f"změna favorita na {name1 if cp > 0.5 else name2}")

    return ev


def _completed_set_score(cur, set_no):
    a, b = cur.get("set_scores", [[], []])
    i = set_no - 1
    if i < len(a) and i < len(b):
        return f"{a[i]}:{b[i]}"
    return "?"


def _break_point_label(cur, names):
    """Vrátí 'mečbol pro X' / 'setbol pro X', pokud právě nastal, jinak None.
    Je to odhad ze stavu bodů - u tiebreaku se nepočítá přesně, proto se tam
    hlásí jen obecně."""
    pts = cur.get("points") or []
    if len(pts) != 2:
        return None
    r0, r1 = _point_rank(pts[0]), _point_rank(pts[1])
    if r0 is None or r1 is None or r0 == r1:
        return None
    lead = 0 if r0 > r1 else 1
    other = 1 - lead
    if cur.get("is_tiebreak") or cur["games"] == [6, 6]:
        # v tiebreaku stačí 7 bodů s odstupem 2
        if max(r0, r1) >= 6 and abs(r0 - r1) >= 1:
            return f"setbol/mečbol pro {names[lead]} v tiebreaku ({pts[0]}:{pts[1]})"
        return None
    if max(r0, r1) < 3:  # ani jeden nemá 40 ani výhodu
        return None
    g_lead, g_other = cur["games"][lead], cur["games"][other]
    wins_set = (g_lead + 1 >= 6 and g_lead + 1 - g_other >= 2)
    if not wins_set:
        return None
    if cur["sets"][lead] == cur["sets_to_win"] - 1:
        return f"MEČBOL pro {names[lead]} ({pts[0]}:{pts[1]}, gemy {g_lead}:{g_other})"
    return f"setbol pro {names[lead]} ({pts[0]}:{pts[1]}, gemy {g_lead}:{g_other})"


# ---------------------------------------------------------------------------
# Hlavní režim: watch
# ---------------------------------------------------------------------------
def cmd_watch():
    log = load_log()
    already_logged_ids = {e["match_id"] for e in log}
    prev_snaps = last_snapshots()
    matches = fetch_live_matches()
    singles = [m for m in matches
               if not m.get("is_doubles") and m.get("draw") == "singles"]
    print(f"Živých zápasů: {len(matches)} (z toho dvouhry: {len(singles)})")

    bank = current_bank(log)
    exposure = pending_exposure(log)
    print(f"Banka: {bank:.0f} mincí (start {STARTING_BANK:.0f}), "
          f"vázáno v nevyřízených tiketech: {exposure:.0f}\n")

    n_tracked = n_nodata = n_nomkt = n_bets = 0
    ts = datetime.now(timezone.utc).isoformat()

    for m in singles:
        sc = m.get("score") or {}
        if not sc.get("sets"):
            continue
        p1, p2 = m["players"]["p1"], m["players"]["p2"]
        name1, name2 = p1["name"], p2["name"]
        gender = m.get("gender", "men")
        cur = parse_score(sc, best_of_5=(m.get("format") == "BO5"))

        # model (když máme dost dat na OBA hráče)
        hold1, n1 = get_hold_rate(name1, gender)
        hold2, n2 = get_hold_rate(name2, gender)
        have_model = (hold1 is not None and hold2 is not None
                      and n1 >= MIN_HOLD_N and n2 >= MIN_HOLD_N)
        if have_model:
            cur["model_p1"] = match_win_prob(
                hold1, hold2, cur["sets"][0], cur["sets"][1],
                cur["games"][0], cur["games"][1],
                cur["server"] == 1, cur["sets_to_win"])
        else:
            cur["model_p1"] = None
            n_nodata += 1

        prev = prev_snaps.get(m["id"])
        events = detect_events(prev, cur, name1, name2)
        n_tracked += 1

        # SLEDOVÁNÍ PRŮBĚHU: zapisuje se u každého zápasu, i bez modelu a kurzů
        snapshot = {
            "match_id": m["id"], "ts": ts, "tournament": m.get("tournament"),
            "player1": name1, "player2": name2, "gender": gender,
            "sets": cur["sets"], "games": cur["games"], "points": cur["points"],
            "server": cur["server"], "is_tiebreak": cur["is_tiebreak"],
            "sets_to_win": cur["sets_to_win"],
            "model_p1": round(cur["model_p1"], 4) if cur["model_p1"] is not None else None,
            "events": events,
            "stale": bool(sc.get("stale")),
        }
        _append_jsonl(PROGRESS_PATH, snapshot)

        head = (f"{name1} vs {name2} [{m.get('tournament', '?')}] "
                f"sety {cur['sets'][0]}:{cur['sets'][1]}, "
                f"gemy {cur['games'][0]}:{cur['games'][1]}, "
                f"body {cur['points'][0]}:{cur['points'][1]}")
        if cur["model_p1"] is not None:
            head += f" | model: {cur['model_p1']:.0%} / {1 - cur['model_p1']:.0%}"
        else:
            head += " | model: málo historických dat"
        print(head)
        for e in events:
            print(f"      - {e}")

        # --- sázková část (jen pokud máme model i skutečné kurzy) ---
        if not have_model or m["id"] in already_logged_ids or sc.get("stale"):
            continue
        probs, best_odds, sx_market, src = bm.get_market_info(name1, name2)
        if not probs or probs.get(name1) is None or probs.get(name2) is None:
            n_nomkt += 1
            continue

        p1_model = cur["model_p1"]
        # Strategie "silný favorit": sází se jen když se SHODNOU model i
        # skutečný trh, že je některý hráč jasný favorit (ne na edge mezi
        # nimi - viz docstring, cíl je vysoký podíl vyhraných tiketů, ne
        # hledání hodnoty proti trhu). Jen jedna strana může podmínku
        # splnit zároveň, protože pravděpodobnosti dávají dohromady 1.
        candidates = ((name1, p1_model), (name2, 1 - p1_model))
        pick = None
        for name, p_model in candidates:
            p_mkt = probs.get(name)
            odds = best_odds.get(name)
            if p_mkt is None or odds is None:
                continue
            if p_model >= FAV_MODEL_MIN and p_mkt >= FAV_MARKET_MIN and odds <= FAV_MAX_ODDS:
                pick = (name, odds, p_model, p_mkt)
                break
        if not pick:
            continue

        stake, reason = next_stake(log, model_p=pick[2], market_p=pick[3], odds=pick[1])
        if stake is None:
            print(f"      ! favorit {pick[0]} @ {pick[1]} (model {pick[2]:.0%}/trh {pick[3]:.0%}), "
                  f"ale tiket se nezakládá: {reason}")
            continue

        name, odds, model_p, market_p = pick
        entry = {
            "match_id": m["id"], "logged_at": ts, "tournament": m.get("tournament"),
            "player1": name1, "player2": name2, "pick": name, "odds": odds,
            "model_p": round(model_p, 4), "market_p": round(market_p, 4),
            "score_at_bet": (f"sety {cur['sets'][0]}:{cur['sets'][1]}, "
                             f"gemy {cur['games'][0]}:{cur['games'][1]}"),
            "stake": stake, "status": "pending",
            # odkud kurz je + identifikátory pro pozdější reálné sázení
            "odds_source": src,
            "bookmaker_mode": bm.mode(),
        }
        if sx_market:
            entry["market_hash"] = sx_market.get("marketHash")
            # strana, na kterou sázíme (1 = outcomeOne, 2 = outcomeTwo)
            entry["outcome_side"] = bm.outcome_side_for(name, sx_market)

        # v režimu 'sxbet_real' pošle skutečnou sázku (jinak jen papírová)
        if bm.is_real():
            try:
                res = bm.place_bet(
                    name1, name2, pick=name, odds=odds, stake=stake,
                    market=sx_market, outcome_side=entry.get("outcome_side"),
                )
                entry["real_bet"] = res
                print(f"      => REÁLNÁ SÁZKA odeslána: {res}")
            except Exception as ex:
                print(f"      ! reálná sázka selhala: {ex}")
                continue

        append_log(entry)
        log.append(entry)
        n_bets += 1
        print(f"      => TIKET na favorita {name} @ {odds} "
              f"(model {model_p:.0%}, trh {market_p:.0%}), vklad {stake:.0f} mincí")

    print(f"\nSledováno zápasů: {n_tracked}")
    print(f"  bez modelu (málo historických dat na hráče): {n_nodata}")
    print(f"  bez živých kurzů v nabídce: {n_nomkt}")
    print(f"Nových fiktivních tiketů: {n_bets}")
    log = load_log()
    print(f"Banka: {current_bank(log):.0f} mincí, "
          f"nevyřízeno {sum(1 for e in log if e['status'] == 'pending')} tiketů "
          f"({pending_exposure(log):.0f} mincí vázáno)")
    print("\nVyhodnocení dohraných zápasů spusť zvlášť: python3 bet_evaluator.py vyhodnot")


def cmd_set_watch():
    """Sází na vítěze AKTUÁLNÍHO setu (SX.bet trhy 202/203/204)."""
    log = load_log()
    logged = {(e["match_id"], e.get("set_no")) for e in log}
    matches = fetch_live_matches()
    singles = [m for m in matches
               if not m.get("is_doubles") and m.get("draw") == "singles"]
    print(f"Živých zápasů: {len(matches)} (z toho dvouhry: {len(singles)}) [SET-level]")
    print(f"Banka: {current_bank(log):.0f} mincí (start {STARTING_BANK:.0f}), "
          f"vázáno {pending_exposure(log):.0f}\n")
    ts = datetime.now(timezone.utc).isoformat()
    n_bets = n_nomkt = 0
    for m in singles:
        sc = m.get("score") or {}
        if not sc.get("sets") or sc.get("stale"):
            continue
        cur = parse_score(sc, best_of_5=(m.get("format") == "BO5"))
        if cur["between_sets"]:
            continue
        p1, p2 = m["players"]["p1"], m["players"]["p2"]
        name1, name2 = p1["name"], p2["name"]
        gender = m.get("gender", "men")
        set_no = cur["sets"][0] + cur["sets"][1] + 1
        if set_no > 3 or (m["id"], set_no) in logged:
            continue
        hold1, n1 = get_hold_rate(name1, gender)
        hold2, n2 = get_hold_rate(name2, gender)
        if hold1 is None or hold2 is None or n1 < MIN_HOLD_N or n2 < MIN_HOLD_N:
            continue
        p1_set = set_win_prob(hold1, hold2, cur["games"][0], cur["games"][1],
                              cur["server"] == 1)
        probs, best, sx_market, src = bm.get_set_market_info(name1, name2, set_no)
        if not probs or probs.get(name1) is None or probs.get(name2) is None:
            n_nomkt += 1
            continue
        pick = None
        for name, p_model in ((name1, p1_set), (name2, 1 - p1_set)):
            p_mkt = probs.get(name)
            odds = best.get(name)
            if p_mkt is None or odds is None:
                continue
            if p_model >= SET_FAV_MODEL_MIN and p_mkt >= SET_FAV_MARKET_MIN \
                    and odds <= SET_FAV_MAX_ODDS:
                pick = (name, odds, p_model, p_mkt)
                break
        if not pick:
            continue
        stake, reason = next_stake(log, model_p=pick[2], market_p=pick[3], odds=pick[1])
        if stake is None:
            print(f"      ! set {set_no} favorit {pick[0]} @ {pick[1]}, ale tiket se nezakládá: {reason}")
            continue
        name, odds, model_p, market_p = pick
        entry = {
            "match_id": m["id"], "set_no": set_no, "market_kind": "set",
            "logged_at": ts, "tournament": m.get("tournament"),
            "player1": name1, "player2": name2, "pick": name, "odds": odds,
            "model_p": round(model_p, 4), "market_p": round(market_p, 4),
            "score_at_bet": (f"sety {cur['sets'][0]}:{cur['sets'][1]}, "
                             f"gemy {cur['games'][0]}:{cur['games'][1]}"),
            "stake": stake, "status": "pending",
            "odds_source": src, "bookmaker_mode": bm.mode(),
        }
        if sx_market:
            entry["market_hash"] = sx_market.get("marketHash")
            entry["outcome_side"] = bm.outcome_side_for(name, sx_market)
        if bm.is_real():
            try:
                res = bm.place_bet(name1, name2, pick=name, odds=odds, stake=stake,
                                   market=sx_market, outcome_side=entry.get("outcome_side"))
                entry["real_bet"] = res
                print(f"      => REÁLNÁ SET SÁZKA odeslána: {res}")
            except Exception as ex:
                print(f"      ! reálná set sázka selhala: {ex}")
                continue
        append_log(entry)
        log.append(entry)
        logged.add((m["id"], set_no))
        n_bets += 1
        print(f"      => SET {set_no} TIKET na {name} @ {odds} "
              f"(model {model_p:.0%}, trh {market_p:.0%}), vklad {stake:.0f} [{name1} vs {name2}]")
    print(f"\nNových set tiketů: {n_bets} (bez set kurzu: {n_nomkt})")
    log = load_log()
    print(f"Banka: {current_bank(log):.0f} mincí, "
          f"nevyřízeno {sum(1 for e in log if e['status'] == 'pending')} tiketů")


def cmd_prematch_watch():
    """PRE-MATCH sazeni: nadchazejici zapasy, kde SX.bet ma trh na viteze
    zapasu (typ 52). Model pocita pravdepodobnost z hold/break rate obou
    hracu na stavu 0:0 (los o podani je 50:50, proto prumeruji obe varianty)."""
    log = load_log()
    logged = {e["match_id"] for e in log}
    matches = fetch_upcoming_matches()
    singles = [m for m in matches
               if not m.get("is_doubles") and m.get("draw") == "singles"]
    print(f"Nadchazejicich zapasu: {len(matches)} (z toho dvouhry: {len(singles)}) [PRE-MATCH]")
    print(f"Banka: {current_bank(log):.0f} minci (start {STARTING_BANK:.0f}), "
          f"vazano {pending_exposure(log):.0f}\n")
    ts = datetime.now(timezone.utc).isoformat()
    n_bets = n_nodata = n_nomkt = 0
    for m in singles:
        if m["id"] in logged:
            continue
        name1, name2 = m["players"]["p1"]["name"], m["players"]["p2"]["name"]
        gender = m.get("gender", "men")
        hold1, k1 = get_hold_rate(name1, gender)
        hold2, k2 = get_hold_rate(name2, gender)
        if hold1 is None or hold2 is None or k1 < MIN_HOLD_N or k2 < MIN_HOLD_N:
            n_nodata += 1
            continue
        # los o podani = 50:50 -> prumer obou variant
        p_a_serves = match_win_prob(hold1, hold2, 0, 0, 0, 0, True)
        p_b_serves = match_win_prob(hold1, hold2, 0, 0, 0, 0, False)
        p1_model = (p_a_serves + p_b_serves) / 2.0
        probs, best, sx_market, src = bm.get_market_info(name1, name2)
        if not probs or probs.get(name1) is None or probs.get(name2) is None:
            n_nomkt += 1
            continue
        pick = None
        for name, p_model in ((name1, p1_model), (name2, 1 - p1_model)):
            p_mkt = probs.get(name)
            odds = best.get(name)
            if p_mkt is None or odds is None:
                continue
            if p_model >= FAV_MODEL_MIN and p_mkt >= FAV_MARKET_MIN and odds <= FAV_MAX_ODDS:
                pick = (name, odds, p_model, p_mkt)
                break
        if not pick:
            continue
        stake, reason = next_stake(log, model_p=pick[2], market_p=pick[3], odds=pick[1])
        if stake is None:
            print(f"      ! pre-match favorit {pick[0]} @ {pick[1]}, ale tiket se nezaklada: {reason}")
            continue
        name, odds, model_p, market_p = pick
        entry = {
            "match_id": m["id"], "market_kind": "match_prematch",
            "logged_at": ts, "tournament": m.get("tournament"),
            "scheduled_time": m.get("scheduled_time"),
            "player1": name1, "player2": name2, "pick": name, "odds": odds,
            "model_p": round(model_p, 4), "market_p": round(market_p, 4),
            "score_at_bet": "pred zapasem (0:0)",
            "stake": stake, "status": "pending",
            "odds_source": src, "bookmaker_mode": bm.mode(),
        }
        if sx_market:
            entry["market_hash"] = sx_market.get("marketHash")
            entry["outcome_side"] = bm.outcome_side_for(name, sx_market)
        if bm.is_real():
            try:
                res = bm.place_bet(name1, name2, pick=name, odds=odds, stake=stake,
                                   market=sx_market, outcome_side=entry.get("outcome_side"))
                entry["real_bet"] = res
                print(f"      => REALNA PRE-MATCH SAZKA odeslana: {res}")
            except Exception as ex:
                print(f"      ! realna sazka selhala: {ex}")
                continue
        append_log(entry)
        log.append(entry)
        logged.add(m["id"])
        n_bets += 1
        print(f"      => PRE-MATCH TIKET na {name} @ {odds} "
              f"(model {model_p:.0%}, trh {market_p:.0%}), vklad {stake:.0f} "
              f"[{name1} vs {name2}, {m.get('scheduled_time')}]")
    print(f"\nNovych pre-match tiketu: {n_bets} "
          f"(bez dat: {n_nodata}, bez SX.bet trhu: {n_nomkt})")
    log = load_log()
    print(f"Banka: {current_bank(log):.0f} minci, "
          f"nevyrizeno {sum(1 for e in log if e['status'] == 'pending')} tiketu")


def cmd_status():
    log = load_log()
    if not log:
        print("Zatím žádné tikety (spusť nejdřív 'watch').")
    else:
        won = sum(1 for e in log if e["status"] == "won")
        lost = sum(1 for e in log if e["status"] == "lost")
        pend = sum(1 for e in log if e["status"] == "pending")
        print(f"Tiketů celkem: {len(log)} (výhra {won}, prohra {lost}, nevyřízeno {pend})")
        print(f"Banka: {current_bank(log):.0f} mincí (start {STARTING_BANK:.0f}), "
              f"vázáno {pending_exposure(log):.0f}")
        print("\nPosledních 5 tiketů:")
        for e in log[-5:]:
            info = (f"edge {e['edge']:+.0%}" if "edge" in e
                    else f"model {e.get('model_p', 0):.0%}/trh {e.get('market_p', 0):.0%}")
            print(f"  [{e['status']:<8}] {e['player1']} vs {e['player2']} - na {e['pick']} "
                  f"@ {e['odds']} ({info}) při {e.get('score_at_bet', '?')}")
    snaps = last_snapshots()
    if snaps:
        print(f"\nSledovaných zápasů v průběhovém logu: {len(snaps)} "
              f"({len(_load_jsonl(PROGRESS_PATH))} snímků celkem)")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode in ("watch", "scan"):
        cmd_watch()
    elif mode == "set-watch":
        cmd_set_watch()
    elif mode == "prematch-watch":
        cmd_prematch_watch()
    elif mode == "status":
        cmd_status()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
