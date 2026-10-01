# Návod pro agenta: živý TENISOVÝ simulátor sázek

Tenhle soubor je psaný pro **AI agenta, který o tomhle projektu nic neví** a má
nástroj obsluhovat sám. Čti ho celý, než něco spustíš. Nepotřebuješ žádnou
předchozí konverzaci ani kontext - všechno podstatné je tady.

**Je to výhradně tenisový nástroj.** Nic jiného než tenis neřeš.

---

## 1. Co to je jednou větou

Dva skripty: první průběžně **sleduje průběh každého právě běžícího tenisového
zápasu** a kde vidí **silného, oběma nezávislými zdroji (model + skutečný trh)
potvrzeného favorita**, založí **fiktivní tiket** z rozpočtu 1000 vymyšlených
mincí. Druhý skript tikety **vyhodnocuje a připisuje do banky**.

**Cíl strategie:** ne porazit trh, ale aby **mezi jednotlivými tikety
převažoval růst banky nad poklesem** - tedy vysoký podíl vyhraných tiketů.
Proto se sází jen na jasné favority, ne na "hodnotové" sázky proti trhu
(viz sekce 4.1 pro přesné vysvětlení rozdílu a jeho limity).

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
cd /root/statistiky/.agents/skills/match-probability/scripts && source ~/.env

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

### 4.1 Cíl: ať banka mezi tikety spíš roste - ne porazit trh

**Toto je důležité rozlišení.** Existuje poctivý, rigorózní backtest
(`scripts/tennis_value_backtest.py`, 11 730 skutečných historických kurzů
WTA 2021-2025), který ukázal, že tenhle model **nemá žádnou prokázanou
výhodu nad trhem** - trh tipuje vítěze přesněji, "hodnotové" sázky (kde
model vidí vyšší pravděpodobnost než trh) jsou v dlouhém běhu ztrátové
(ROI -7,7 % až -10,1 %). To platí a nic na tom tenhle nástroj nemění.

Proto `watch` NEHLEDÁ "hodnotu" (rozdíl model vs. trh, ve starší verzi
`EDGE_MIN`/`EDGE_MAX`) - hledá **silné favority**, na kterých se model i
skutečný trh NEZÁVISLE shodnou (`FAV_MODEL_MIN`, `FAV_MARKET_MIN`,
`FAV_MAX_ODDS` v kódu). Favorité v historických datech vyhrávají velmi
často (u kurzů do 1,2 to je řádově 90%+ úspěšnost) - to znamená, že
**většina jednotlivých tiketů vyhraje**, tedy banka se mezi tikety
mnohem častěji zvedá než propadá.

**Ale pozor na past v uvažování:** vysoký podíl výher NENÍ totéž co kladné
ROI ani zaručený dlouhodobý růst banky. Sázková marže zůstává zaceněná
i v kurzu na favorita - i při 90% úspěšnosti může jedna neočekávaná prohra
smazat zisk z mnoha malých výher, a v součtu přes stovky tiketů může ROI
vyjít mírně záporné. "Mince mají spíš stoupat než klesat" je o **frekvenci
jednotlivých pohybů nahoru/dolů**, ne o matematické záruce zisku - tu
nemůže dát žádná sázková strategie. Řekni tohle uživateli přesně takhle,
když se zeptá na výsledky - je to jiné tvrzení než "model vydělává".

**Když banka i přes vysoký podíl výher dlouhodobě klesá, je to platný
výsledek, ne chyba, kterou máš opravit.** Neupravuj parametry dodatečně tak,
aby výsledek vyšel hezky - to je přefitování a výsledek pak nic neznamená.
Když chceš parametry měnit, změň je PŘED dalším sběrem dat a nový vzorek
počítej zvlášť.

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

**Past č. 2 - velký NESOULAD mezi modelem a trhem obvykle znamená zastaralá
data, ne nalezenou příležitost.** Když model řekne 97 % a trh 40 %, skoro
jistě nevidíš příležitost, ale máš staré nebo špatně přečtené skóre. Proto
`watch` vyžaduje, aby se model i trh na favoritovi SHODLY (`FAV_MODEL_MIN`
i `FAV_MARKET_MIN` musí být splněné zároveň) - žádný tiket nevznikne jen
z toho, že model tvrdí něco, co trh nepotvrzuje. Nesnižuj `FAV_MARKET_MIN`
pod rozumnou hranici (0,65) a nezvyšuj `FAV_MAX_ODDS` nad bezpečné favority.

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

Když se favorit najde, `watch` vypíše navíc řádek jako:

```
      => TIKET na favorita Xinyu Gao @ 1.27 (model 95%, trh 87%), vklad 20 mincí
```

**Když `watch` nenajde žádný tiket, není to chyba.** Protože se teď vyžaduje
shoda modelu i trhu na jasném favoritovi (ne jen nejmenší rozdíl), je
naprosto normální, že z 15-20 dvouher nevznikne žádný tiket - většina živých
zápasů zrovna není v situaci "jasný favorit s kurzem pod 1,60 a dostupnými
kurzy". Neopakuj spuštění hned znovu ve snaze "něco najít" - jen bys spálil
kvótu. Počkej na další interval.

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
PŘEHLED FIKTIVNÍCH TENISOVÝCH SÁZEK (strategie: silný favorit)
==================================================================
Podíl rostoucích tiketů (výher):  100.0%  -> PŘEVAŽUJE RŮST
  (1 roste / 0 klesá z 1 vyhodnocených)

Rozpočet na start:          1000 mincí
Banka teď:                  1005 mincí  (+5)
Vázáno v nevyřízených:         0 mincí (0 tiketů)

Tiketů celkem:                 1
  vyhodnocených:               1  (výhra 1, prohra 0)
  vsazeno / vráceno:          20 / 25 mincí
  ROI:                   +27.0%  (poctivé měřítko peněz - i vysoký podíl výher může dát záporné ROI)
```

Při pěti a více vyhodnocených tiketech přidá navíc graf vývoje banky a rozpad
podle kurzových pásem.

**`Podíl rostoucích tiketů`** je hlavní metrika pro tenhle cíl (viz 4.1) -
jestli převažuje `V` (výhra/růst) nad `P` (prohra/pokles). **`ROI`** je
oddělené, poctivé peněžní měřítko - i strategie s 85 % úspěšností (vysoký
podíl růstu) může mít mírně záporné ROI, protože jedna velká prohra smaže
víc malých výher. Oba řádky říkej uživateli zvlášť, nepleť je dohromady.

Skript sám na konci připomíná, kolik tiketů je potřeba (řádově 100+), aby byl
podíl výher spolehlivý. **Ber to vážně a opakuj to uživateli** - u pár desítek
tiketů se i spolehlivý dlouhodobý favorit (90% šance) může sejít hůř.

---

## 8. Soubory se stavem

Oba leží v `.agents/skills/match-probability/`:

| Soubor | Co v něm je |
|---|---|
| `live_bets_log.jsonl` | jeden řádek = jeden tiket. **Jediný zdroj pravdy o bance.** |
| `live_progress_log.jsonl` | jeden řádek = jeden snímek stavu jednoho zápasu. Historie průběhu. |

Skutečný řádek z logu sázek:

```json
{"match_id": 196994, "logged_at": "2026-10-01T13:34:44+00:00", "tournament": "Beijing",
 "player1": "Panna Udvardy", "player2": "Xinyu Gao", "pick": "Xinyu Gao", "odds": 1.27,
 "model_p": 0.9483, "market_p": 0.8694, "score_at_bet": "sety 0:1, gemy 3:5",
 "stake": 20.0, "status": "won", "resolved_at": "2026-10-01T13:39:03+00:00",
 "actual_winner": "Xinyu Gao", "profit": 5.4}
```

(Starší záznamy z dřívější "hodnotové" strategie mají navíc pole `"edge"` -
oba skripty to zpětně zvládají, nic se s tím dělat nemusí.)

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

## 9a. Systémové notifikace při změně banky

Tohle prostředí běží v **NetHunter AI Operator PRoot** (viz `~/nethunter_docs.md`
pro kompletní dokumentaci jeho nástrojů). `bet_evaluator.py` i `live_game_bet.py`
automaticky pošlou systémovou notifikaci **při každém vyhodnocení tiketu**
(výhra/prohra - ne při založení tiketu a ne při zrušení/`void`, protože ani
jedno z toho banku nemění) přes `nh system notification -t <titulek> -c <text>`.
Nemusíš to nijak spouštět navíc - děje se to samo uvnitř `vyhodnot`/`tick`.
Je to defenzivně obalené (nikdy nespadne skript, i kdyby `nh` chybělo).

---

## 10. Jak o výsledcích mluvit s uživatelem

- Mluv o **"fiktivních mincích"**, nikdy o korunách ani o zisku.
- Cíl je "podíl rostoucích tiketů převažuje nad klesajícími" - to je jiné
  tvrzení než "model vydělává" nebo "porazí trh". Nepleť ta dvě tvrzení
  dohromady, ani když to vyzní hůř.
- Při malém počtu tiketů (pod ~100) **je podíl výher nespolehlivý odhad**.
  Deset výher v řadě u skutečného 90% favorita nedokazuje, že strategie bude
  takhle úspěšná napořád. Řekni to na rovinu, i když banka roste.
- Když banka i přes vysoký podíl výher klesá, **neomlouvej to a neslibuj
  nápravu** - je to legitimní výsledek (sázková marže), ne chyba.
- Nikdy netvrď, že nějaká strategie zaručí, že banka neklesne pod startovní
  hodnotu. To matematicky nejde - u každé sázky je nenulová šance prohry.
- Když si nejsi jistý, jestli výsledek o něčem svědčí, řekni že nesvědčí.

---

## 11. Kde je co (orientace v repozitáři)

```
/root/statistiky/
├── .agents/skills/match-probability/
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

---

## 12. Druhý, rychlejší trh: vítěz AKTUÁLNÍHO GEMU (`live_game_bet.py`)

Oddělený skript, **vlastní banka** (`live_game_bets_log.jsonl`, taky start
1000 mincí - NENÍ sdílená s `live_bets_log.jsonl` od `watch`). Sází na to,
kdo vyhraje PRÁVĚ ROZEHRANÝ gem, ne celý zápas - mnohem vyšší frekvence
(gem trvá pár minut, zápas jich má desítky).

```bash
cd /root/statistiky/.agents/skills/match-probability/scripts && source ~/.env
python3 live_game_bet.py tick     # jedno kolo: vyhodnotí dřívější tikety + hledá nové
python3 live_game_bet.py status   # přehled, NESTOJÍ API kvótu
```

**Zásadní rozdíl oproti `watch`:** pro "kdo vyhraje tenhle gem" neexistuje
nezávislý skutečný trh kurzů, proti kterému by šlo model ověřit (Odds API
nabízí nanejvýš vítěze zápasu/setu). Sází se čistě na historický hold rate
hráče přepočítaný na pravděpodobnost z AKTUÁLNÍHO bodového skóre (matematický
přepočet téhož čísla, ne nová informace - podrobnosti v hlavičce skriptu
a v `references/metodika.md`). Práh je proto přísnější (`GAME_FAV_MIN = 0,70`)
a tiebreaky se úplně přeskakují (jiné skórování).

**Vyhodnocení je OKAMŽITÉ, v rámci stejného `tick`** - žádný samostatný
`resolve` skript. Při každém kole se nejdřív ze stejného stažení dat
vyhodnotí tikety z MINULÉHO kola (porovná se zaznamenaný stav gemu s
aktuálním), a teprve pak se hledají nové příležitosti. Pokud mezi dvěma
koly proběhlo víc než jeden gem (= `tick` se nevolal dost často), tiket se
označí jako `void` (zrušen, banka se nemění) - radši nehádat vítěze, než
tvrdit něco nepodloženého.

**Kvóta: tenhle skript potřebuje MNOHEM kratší interval než `watch`** - gem
skončí za pár minut, takže dává smysl spouštět `tick` řádově **každých
1-3 minuty**, ne každých 15-30 jako `watch`. To spotřebuje kvótu rychle
(100 volání/den při 1 volání/tick vydrží jen ~2-5 hodin provozu podle
intervalu). **Před spuštěním smyčky vždy zkontroluj `/usage` a `crontab -l`**
- `watch` může běžet souběžně (jiný cron, viz `cron_tick.sh`) a sdílí stejný
klíč a denní limit. Naplánuj interval tak, aby oběma zbyla rezerva, nebo
pusť `live_game_bet.py` jen na omezenou dobu (např. jednu hodinu, pak
zastav), ne natrvalo.

Příklad spuštění ve smyčce na omezenou dobu (30 kol po 90 s = cca 45 minut,
~30 volání API):

```bash
cd /root/statistiky/.agents/skills/match-probability/scripts && source ~/.env
for i in $(seq 1 30); do
  echo "=== tick $i $(date '+%H:%M:%S') ==="
  python3 live_game_bet.py tick
  sleep 90
done
python3 live_game_bet.py status
```

---

## 13. TŘETÍ, agresivní režim: rychlé znásobení s cílem a limitem (`agresivni-tick`)

Na výslovné přání uživatele existuje ještě třetí, oddělený režim (vlastní
banka `live_game_bet_aggressive_log.jsonl`) - cíl NENÍ postupný růst, ale
**co nejrychlejší znásobení**, s jasně danou metou a pojistkou:

```bash
python3 live_game_bet.py agresivni-tick     # jedno kolo (vyhodnotí + případně založí nový tiket)
python3 live_game_bet.py agresivni-status   # přehled, nestojí API kvótu
```

**Jak to funguje:**
1. **Růstová fáze** - sází se **CELÁ aktuální banka** na jeden tiket (jen
   jeden otevřený zároveň). Vybírá se zápas s NEJNIŽŠÍ pravděpodobností, co
   ještě splní bezpečnostní práh 70 % (`GAME_FAV_MIN`) - to dá nejvyšší
   dostupný kurz v rámci prahu, tedy nejrychlejší růst. Tohle je VÝSLOVNĚ
   POTVRZENÉ RIZIKO - jedna jediná prohra KDYKOLIV vynuluje banku bez
   možnosti zotavení. Uživatel na tohle upozornění reagoval "risk je zisk,
   proto to existuje" - je to jeho informované rozhodnutí, neopravuj to
   zpátky na opatrnější sázení bez vyžádání.
2. Jakmile banka dosáhne **6000 (6× start)**, přepne se do **ochranné
   fáze** - od tohohle bodu se už NEsází celá banka, ale nejvýš 1000 mincí
   na tiket (schválně, aby trailing stop níže mohl vůbec zafungovat - celá
   banka by jednou prohrou smazala vrchol napřímo, ne jen posledních 1000).
3. V ochranné fázi se sleduje VRCHOL banky - jakmile banka klesne na
   (vrchol − 1000) nebo níž, agent se **OKAMŽITĚ A NATRVALO ZASTAVÍ**
   (žádné další tikety, i kdyby zápasy dál běžely).
4. Pokud banka klesne pod minimální vklad PŘED dosažením cíle (= došly
   peníze po sérii proher), taky se natrvalo zastaví.

**Stav (vrchol, fáze, zastaveno/ne) se nikde zvlášť neukládá** - při
každém spuštění se přepočítá přehráním celého logu od začátku
(`_replay_aggressive`), stejný princip jako jinde v projektu.

**Jakmile `agresivni-status` nebo `agresivni-tick` hlásí "ZASTAVENO" (viz
`halt_reason`), NESPOUŠTĚJ to dál** - agent to sám odmítne (nezaloží nový
tiket), ale nemá smysl dál plýtvat API voláním na kontrolu něčeho, co se
už nehne.

**Jak o tomhle režimu mluvit s uživatelem:** tohle NENÍ "bezpečná" verze
nástroje jako `watch` nebo normální `tick` - je to vědomě vysoce rizikové
nastavení na uživatelovo přání. Nikdy netvrď, že "spíš poroste" stejným
tónem jako u opatrnějších režimů - tady je realistický výsledek buď rychlý
růst k cíli, nebo rychlá ztráta všeho, bez průběžného "spíš nahoru". Řekni
to takhle na rovinu, pokud se uživatel zeptá na pravděpodobnost úspěchu.
