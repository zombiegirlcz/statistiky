# Návod pro agenta: živý TENISOVÝ simulátor sázek

Tenhle soubor je psaný pro **AI agenta, který o tomhle projektu nic neví** a má
nástroj obsluhovat sám. Čti ho celý, než něco spustíš. Nepotřebuješ žádnou
předchozí konverzaci ani kontext - všechno podstatné je tady.

**Je to výhradně tenisový nástroj.** Nic jiného než tenis neřeš.

---

## 1. Co to je jednou větou

Dva skripty: první průběžně **sleduje průběh každého právě běžícího tenisového
zápasu** a kde vidí hodnotu proti skutečným kurzům, založí **fiktivní tiket**
z rozpočtu 1000 vymyšlených mincí. Druhý skript tikety **vyhodnocuje a připisuje
do banky**.

**Nikdy se nevsázejí skutečné peníze. Žádný sázkový účet neexistuje a skripty
žádný neovládají.** Je to měřicí nástroj, ne sázecí bot.

---

## 2. Dva skripty, dvě role

| Skript | Co dělá | Jak často spouštět |
|---|---|---|
| `live_tennis_simulator.py watch` | sleduje průběh všech živých zápasů, hlásí události, zakládá tikety | **každých 15-30 minut**, dokud běží zápasy |
| `bet_evaluator.py vyhodnot` | zjistí výsledky dohraných zápasů, připíše výhry/prohry do banky, vypíše přehled | **jednou za 1-3 hodiny**, nebo kdykoli po skončení zápasů |

Přesné příkazy (vždy z kořene repozitáře, vždy s `source ~/.env`):

```bash
cd /root/statistiky/.claude/skills/match-probability/scripts && source ~/.env

python3 live_tennis_simulator.py watch      # sledování průběhu + zakládání tiketů
python3 live_tennis_simulator.py status     # rychlý přehled, NESTOJÍ žádnou kvótu
python3 bet_evaluator.py vyhodnot           # vyhodnocení sázek + připsání do banky
python3 bet_evaluator.py report             # jen přehled, NESTOJÍ žádnou kvótu
```

### Kolik to stojí API kvóty

- `watch` = **1 volání** Live Tennis API + několik kreditů Odds API (jeden za
  každý právě běžící tenisový turnaj, typicky 2-6).
- `vyhodnot` = **1 volání** Live Tennis API za každý nevyřízený tiket.
- `status` a `report` = **0 volání**, spouštěj kolikrát chceš.

Denní limit Live Tennis API (free tier) je **100 volání, 30 za minutu**.
Při rytmu výš se do toho pohodlně vejdeš. Spouštět `watch` častěji než jednou
za ~10 minut nemá smysl - na každý zápas se stejně sází jen jednou.

Zbývající kvótu zjistíš takhle (samo to kvótu nečerpá):

```bash
source ~/.env; curl -s -H "Authorization: Bearer $LIVE_TENNIS_API_KEY" \
  "https://api.livetennisapi.com/api/public/v1/usage" | python3 -m json.tool
```

Hledej `today.remaining_day`.

---

## 3. Rozpočet: 1000 fiktivních mincí

| Pravidlo | Hodnota | Proč |
|---|---|---|
| startovní rozpočet | 1000 mincí | zadání |
| vklad na tiket | 2 % aktuální banky, minimálně 10 mincí | sází se úměrně tomu, co zbývá - při klesající bance se vklady samy zmenšují |
| strop souběžné expozice | 25 % banky | aby nebylo naráz vázáno všechno v nevyřízených tiketech |
| jeden zápas | max. jeden tiket | na stejný zápas se nikdy nesází dvakrát |

Když je rozpočet vyčerpaný nebo narazí na strop expozice, `watch` to **vypíše
a tiket nezaloží** - ale průběh zápasů sleduje dál.

**Banka se nikde neukládá jako číslo.** Vždy se dopočítá z logu sázek
(start 1000, výhra `+vklad*(kurz-1)`, prohra `-vklad`). Jediný zdroj pravdy je
soubor `live_bets_log.jsonl`.

---

## 4. Co MUSÍŠ vědět, než to spustíš

### 4.1 Cíl není "vydělat mince"

Cíl je **změřit, jestli model má nebo nemá reálnou výhodu nad trhem**. Pravdivá
odpověď může klidně být "nemá". Ve fotbalové části tohohle projektu
(`ticket_builder.py`) vyšla po poctivém měření ztráta ve VŠECH testovaných
variantách (viz `references/metodika.md`). Tady může vyjít totéž.

**Když banka klesá, je to platný výsledek, ne chyba, kterou máš opravit.**
Neupravuj parametry dodatečně tak, aby výsledek vyšel hezky - to je přefitování
a výsledek pak nic neznamená. Když chceš parametry měnit, změň je PŘED dalším
sběrem dat a nový vzorek počítej zvlášť.

### 4.2 Tři pasti, do kterých se tenhle projekt už chytil (neopakuj je)

**Past č. 1 - tautologie "trh = zpožděná kopie modelu".**
Dřívější verze si "trh" vyráběla tím, že vzala STEJNÝ vzorec jako model, jen
s o gem starším skóre. Výsledek: banka 1000 → 119 430 mincí, 76 % úspěšných
sázek. Vypadalo to jako objev. Byla to tautologie - model porovnával sám se
sebou a z definice vyhrával. Dokázalo se to kontrolním testem, kde oba hráči
dostali ÚPLNĚ STEJNÝ hold rate (tedy nulová skutečná předvídatelnost) - a banka
přesto vyrostla na 172 643.

→ **Pravidlo: "trh" musí vždy pocházet z nezávislého vnějšího zdroje
(skutečné kurzy sázkových kanceláří).** Nikdy neporovnávej model s jeho vlastní
starší verzí. Současné skripty to dělají správně. Když je budeš upravovat,
tohle neporušuj.

**Past č. 2 - "obrovský edge" obvykle znamená zastaralá data, ne nalezenou
hodnotu.** Když model řekne 97 % a trh 40 %, skoro jistě nevidíš příležitost,
ale máš staré nebo špatně přečtené skóre. Proto existuje `EDGE_MAX = 0.25` -
rozdíly nad 25 procentních bodů se **ignorují**. Nezvyšuj ten strop.

**Past č. 3 - málo historických dat = nesmyslný odhad.** Hráč s pěti
zaznamenanými podáváními má "hold rate" čistý šum. Proto `MIN_HOLD_N = 20`.
Nesnižuj to. Je normální, že u třetiny živých zápasů (hlavně ITF/Challenger)
model data nemá - jejich průběh se pořád sleduje, jen se na ně nesází.

### 4.3 Model nemůže nikdy tvrdit 100 %

Kombinatorický model sám o sobě považuje stav 6:0 6:5 40:0 za jistotu.
Skutečný svět ne. V datech tohohle projektu (`tenis/atp_matches_202*.csv` +
`wta_matches_202*.csv`, 30 885 zápasů) **končí 3,59 % všech zápasů skrečí,
walkoverem nebo diskvalifikací** - zranění, nevolnost, odstoupení. To může
potkat i vedoucího hráče.

Proto má každá pravděpodobnost podlahu 2 % a strop 98 % (`MIN_PROB`/`MAX_PROB`).
Je to hrubý, ale **daty podložený** odhad (zhruba polovina naměřené míry
skreče), ne číslo z hlavy. Když o výsledcích mluvíš s uživatelem, nikdy neříkej
"jistá výhra" - skripty to taky neříkají.

---

## 5. Co potřebuješ nastavené

Dva API klíče, oba v souboru `~/.env` (mimo git repozitář). **Nikdy je nevypisuj
do výstupu.** Když potřebuješ zkontrolovat, že tam jsou, použij příkaz, který
ukáže jen názvy, ne hodnoty:

```bash
grep -o '^export [A-Z_]*' ~/.env
```

| Proměnná | Zdroj | Limit zdarma | K čemu |
|---|---|---|---|
| `LIVE_TENNIS_API_KEY` | livetennisapi.com | 30 volání/min, 100/den | živé zápasy, skóre po gemech a bodech |
| `ODDS_API_KEY` | the-odds-api.com | ~500 kreditů/měsíc | skutečné živé kurzy |

Před spuštěním vždy `source ~/.env` ve stejném příkazu.

Z free tieru Live Tennis API používej jen: `/matches?status=live`,
`/matches?status=upcoming`, `/matches/{id}` a `/usage`. Výpis dokončených
zápasů (`status=completed`) je **placený** a vrátí chybu `upgrade_required` -
výsledek dohraného zápasu proto zjišťuj přes detail podle ID, což `vyhodnot`
dělá sám.

---

## 6. Jak číst výstup `watch`

Reálný výstup z ověřeného běhu (1. 10. 2026, zkráceno):

```
Živých zápasů: 30 (z toho dvouhry: 15)
Banka: 1005 mincí (start 1000), vázáno v nevyřízených tiketech: 0

Alexander Bublik vs Jakub Menšik [Beijing] sety 0:1, gemy 5:5, body 30:15 | model: 22% / 78%
      - poprvé viděn (sety 0:1, gemy 5:5)
Polona Hercog vs Naiktha Bains [W75 Quinta do Lago] sety 1:0, gemy 1:1, body 40:30 | model: málo historických dat
      - poprvé viděn (sety 1:0, gemy 1:1)

Sledováno zápasů: 15
  bez modelu (málo historických dat na hráče): 5
  bez živých kurzů v nabídce: 9
Nových fiktivních tiketů: 0
Banka: 1005 mincí, nevyřízeno 0 tiketů (0 mincí vázáno)
```

- **`model: 22% / 78%`** = naše pravděpodobnost vítězství v zápase pro prvního
  a druhého hráče, spočítaná z aktuálního skóre a historického hold/break rate.
- **Odrážky pod zápasem** = co se stalo od minulého spuštění (viz dál).
- **`bez modelu`** = jeden z hráčů nemá aspoň 20 zaznamenaných podávacích gemů.
  **Je to v pořádku a žádoucí** - raději nesázet než hádat. Průběh se sleduje dál.
- **`bez živých kurzů v nabídce`** = Odds API tenhle zápas nemá (pokrývá hlavně
  ATP/WTA tour, ne Challenger/ITF). **Taky v pořádku.**

**Když `watch` nenajde žádný tiket, není to chyba.** Je naprosto normální, že
z 15 dvouher nevznikne žádný tiket. Neopakuj spuštění hned znovu ve snaze
"něco najít" - jen bys spálil kvótu. Počkej na další interval.

### Jaké události `watch` hlásí

Porovnává aktuální stav s posledním uloženým snímkem téhož zápasu a hlásí:

| Událost | Co znamená |
|---|---|
| `poprvé viděn` | zápas vidíme poprvé, není s čím srovnávat |
| `BREJK pro X` | hráč vzal gem soupeři na jeho podání |
| `X získal N. set` | set je uzavřený, mění se stav na sety |
| `tiebreak` | stav 6:6 v gemech |
| `setbol pro X` / `MEČBOL pro X` | hráč může tímhle gemem získat set, resp. celý zápas |
| `posun šance X: 40% -> 55%` | pravděpodobnost se pohnula o 10 procentních bodů a víc |
| `změna favorita na X` | model přehodil, kdo je favorit |

Při prvním spuštění je u všech zápasů jen `poprvé viděn` - události mají smysl
od druhého spuštění dál.

---

## 7. Jak číst výstup `bet_evaluator.py`

```
==================================================================
PŘEHLED FIKTIVNÍCH TENISOVÝCH SÁZEK
==================================================================
Rozpočet na start:          1000 mincí
Banka teď:                  1005 mincí  (+5)
Vázáno v nevyřízených:         0 mincí (0 tiketů)

Tiketů celkem:                 1
  vyhodnocených:               1  (výhra 1, prohra 0)
  úspěšnost:             100.0%
  vsazeno / vráceno:          20 / 25 mincí
  ROI:                   +27.0%
```

Při pěti a více vyhodnocených tiketech přidá navíc graf vývoje banky a rozpad
podle kurzových a edge pásem.

**`ROI`** je jediné číslo, které o kvalitě modelu vypovídá - ne banka a ne
úspěšnost. Sázky na favority s kurzem 1,2 můžou mít 85 % úspěšnost a přitom
být ztrátové.

Skript sám na konci připomíná, kolik tiketů je potřeba (řádově 100+), aby se
dalo mluvit o něčem jiném než o šumu. **Ber to vážně a opakuj to uživateli.**

---

## 8. Soubory se stavem

Oba leží v `.claude/skills/match-probability/`:

| Soubor | Co v něm je |
|---|---|
| `live_bets_log.jsonl` | jeden řádek = jeden tiket. **Jediný zdroj pravdy o bance.** |
| `live_progress_log.jsonl` | jeden řádek = jeden snímek stavu jednoho zápasu. Historie průběhu. |

Skutečný řádek z logu sázek:

```json
{"match_id": 196994, "logged_at": "2026-10-01T13:34:44+00:00", "tournament": "Beijing",
 "player1": "Panna Udvardy", "player2": "Xinyu Gao", "pick": "Xinyu Gao", "odds": 1.27,
 "edge": 0.0789, "model_p": 0.9483, "market_p": 0.8694, "score_at_bet": "sety 0:1, gemy 3:5",
 "stake": 20.0, "status": "won", "resolved_at": "2026-10-01T13:39:03+00:00",
 "actual_winner": "Xinyu Gao", "profit": 5.4}
```

`status` jde `pending` → `won` / `lost`.

**Nikdy ty soubory needituj ručně a nemaž je.** Když smažeš log sázek, přijdeš
o celou měřenou historii a banka se vrátí na 1000 - tím znehodnotíš všechno
dosavadní měření. Průběhový log roste rychle (desítky řádků za spuštění); když
se rozroste přes únosnou velikost, je v pořádku ho **archivovat** (přejmenovat),
ale ne zahodit.

Skripty jsou mezi spuštěními **bezstavové** - celý stav žije v těch dvou
souborech. Klidně je spouštěj z jiného procesu, jiného modelu nebo jiný den,
nic se neztratí a nic se nezduplikuje.

---

## 9. Co dělat, když něco selže

| Co vidíš | Co to znamená | Co udělat |
|---|---|---|
| `CHYBA: chybí proměnná prostředí LIVE_TENNIS_API_KEY` | nenačetl jsi prostředí | `source ~/.env` ve stejném příkazu |
| `CHYBA Live Tennis API (429)` | překročen limit (30/min nebo 100/den) | počkej, zkontroluj `/usage` |
| `CHYBA Live Tennis API (401/403)` | neplatný klíč | řekni to uživateli, klíč neopravuj sám |
| `upgrade_required` v odpovědi | sáhl jsi na placený endpoint | drž se endpointů ze sekce 5 |
| `Žádné nevyřízené tikety.` | všechno je vyhodnocené | nic, je to normální |
| `[čeká] ... zápas je ve stavu 'live'` | zápas ještě neskončil | nic, zkus `vyhodnot` později |
| `Živých zápasů: 0` | zrovna se nehraje (noc v Evropě i Asii) | nic, zkus později |
| Žádný tiket při `watch` | prostě nebyla příležitost | nic, počkej na další interval |

---

## 10. Jak o výsledcích mluvit s uživatelem

- Mluv o **"fiktivních mincích"**, nikdy o korunách ani o zisku.
- Při malém počtu tiketů (pod ~100) **jakýkoli výsledek je šum**. Deset výher
  v řadě nedokazuje nic. Řekni to na rovinu, i když banka roste.
- Když banka klesá, **neomlouvej to a neslibuj nápravu** - je to legitimní
  zjištění, které stojí za víc než vymyšlený úspěch.
- Nikdy netvrď, že nějaká strategie zaručí, že banka neklesne pod startovní
  hodnotu. To matematicky nejde - u každé sázky je nenulová šance prohry.
- Když si nejsi jistý, jestli výsledek o něčem svědčí, řekni že nesvědčí.

---

## 11. Kde je co (orientace v repozitáři)

```
/root/statistiky/
├── .claude/skills/match-probability/
│   ├── AGENT_NAVOD.md              ← tenhle soubor
│   ├── SKILL.md                    ← popis celého skillu (predikce zápasů)
│   ├── live_bets_log.jsonl         ← stav fiktivních tiketů (NEMAZAT)
│   ├── live_progress_log.jsonl     ← historie průběhu sledovaných zápasů
│   ├── references/metodika.md      ← VŠECHNY naměřené výsledky a poctivé nálezy
│   └── scripts/
│       ├── live_tennis_simulator.py  ← sledování živých zápasů + tikety
│       ├── bet_evaluator.py          ← vyhodnocení sázek + banka
│       ├── game_flow.py              ← hold/break rate z Match Charting dat
│       ├── odds_compare.py           ← stahování živých kurzů (Odds API)
│       ├── ticket_builder.py         ← fotbalová obdoba (historická data)
│       └── aggregate_stats.py        ← základní predikce zápasu
├── tenis/      ← historická tenisová data (ATP/WTA + Match Charting)
└── fotbal/     ← historická fotbalová data včetně skutečných kurzů
```

**Než budeš cokoli měnit, přečti si `references/metodika.md`.** Jsou tam
naměřená čísla ke všemu, co se v tomhle projektu zkoušelo, včetně věcí, co
nefungovaly - ušetří ti to opakování slepých uliček.
