---
name: match-probability
description: Spočítá pravděpodobnost výsledku nadcházejícího fotbalového, tenisového nebo hokejového zápasu na základě kompletních historických dat uložených v /statistiky (5 sezón, stovky tisíc řádků - vzájemné zápasy, forma, rohy, esa, přesilovky atd.). Použij tento skill VŽDY, když se uživatel zeptá na šance, pravděpodobnost, tip, predikci nebo "kdo vyhraje" u konkrétního zápasu dvou týmů nebo hráčů ve fotbale, tenise či hokeji - stačí že zmíní dva soupeře proti sobě (např. "co myslíš, Sinner vs Alcaraz?", "jaké má šance City doma na Liverpool", "vyhraje Toronto nad Edmontonem?"), i když nepoužije slovo "pravděpodobnost". Nikdy neodhaduj výsledek jen z obecné znalosti nebo paměti - tento skill vynucuje, že se musí nejdřív sáhnout do reálných dat.
---

# Pravděpodobnost zápasu

## Proč tenhle skill existuje

Když se někdo zeptá "kdo vyhraje Arsenal - Chelsea", je lákavé odpovědět z obecné intuice ("Arsenal je silnější, dám jim 60 %"). To je ale jen hádání se škálou procent navrch - vypadá to přesvědčivě, ale není to podložené ničím skutečným. V `/statistiky` leží kompletní zápasová historie (5 sezón, desetitisíce zápasů se skóre, rohy, esy, přesilovkami...) přesně proto, aby se tohle hádání nemuselo dít. Úkol tady není "odhadni", ale "spočítej z dat, která máš k dispozici".

## Postup

### 1. Rozpoznej sport a dvojici

Z dotazu urči, jde-li o fotbal, tenis nebo hokej, a jména obou stran. Pokud je sport nejasný (např. jméno týmu existuje ve více sportech), zeptej se nebo to odvoď z kontextu (jméno hráče = skoro jistě tenis; dva kluby = fotbal nebo hokej podle názvu).

### 2. Spusť agregační skript - nespoléhej na ruční čtení

Soubory v `fotbal/` mají až tisíce řádků a `tenis/` desetitisíce - ruční prohledávání `grep`em je pomalé a náchylné k tomu, že něco přehlédneš (např. zápas ve staré sezóně, nebo zápas, kde je tým uvedený pod mírně jiným zápisem). Skript `scripts/aggregate_stats.py` projde VŠECHNY relevantní soubory pro daný sport, najde VŠECHNY zápasy obou stran i jejich vzájemné duely, a spočítá to spolehlivě:

```bash
python3 .claude/skills/match-probability/scripts/aggregate_stats.py fotbal "Arsenal" "Chelsea"
python3 .claude/skills/match-probability/scripts/aggregate_stats.py tenis "Sinner" "Alcaraz"
python3 .claude/skills/match-probability/scripts/aggregate_stats.py hokej "Toronto" "Edmonton"
```

Jména nemusí sedět na znak přesně (skript dělá fuzzy matching), ale musí být rozpoznatelná - u fotbalu/hokeje zkus nejdřív běžný název klubu (viz `references/nazvy_tymu.md` pro mapování na přesné názvy/zkratky v datech, hlavně u hokeje, kde se v CSV používají 3písmenné zkratky jako TOR, EDM).

Pokud víš, který tým hraje doma, přidej `--home A` nebo `--home B` (výchozí je, že doma hraje první zadaný tým - u fotbalu a hokeje to ovlivňuje výsledek, protože domácí výhoda je reálný a měřitelný efekt v datech).

**Pokud skript vypíše CHYBA** (nenašel tým/hráče jednoznačně), nehádej náhradní jméno sám - buď zkus jiný běžný tvar jména (zkratka, celé jméno klubu), nebo se zeptej uživatele, kterého přesně tým/hráče myslí.

### 3. Zkontroluj, že čísla dávají smysl

Skript na konci vypíše návrh procent, ale než je použiješ, projdi si i surová čísla nad ním - kolik zápasů bylo k dispozici (pokud jen pár, výsledek je méně spolehlivý), jak vypadá vzájemná bilance a nedávná forma. Pokud je najednou něco v nepoměru (např. tým s hroznou formou vychází silný favorit), zkontroluj, jestli skript nenašel špatný tým kvůli nejednoznačnému jménu.

Metodika výpočtu (váhy, proč zrovna takhle) je v `references/metodika.md` - přečti si ji, pokud se tě uživatel zeptá, PROČ vyšlo zrovna takové číslo, nebo pokud chceš váhy u konkrétního zápasu jemně upravit (např. když jeden hráč/tým má čerstvé zranění nebo jde o finále s jinou motivací - takové kontextové věci skript neumí vidět v číslech, ale ty o nich můžeš vědět).

### 4. Odpověz stručně

Uživatel chce HOLÁ PROCENTA, ne esej. Formát odpovědi:

- **Fotbal**: `Tým A XX % / Remíza YY % / Tým B ZZ %`
- **Tenis**: `Hráč A XX % / Hráč B YY %`
- **Hokej**: `Tým A XX % / Tým B YY %` (v NHL je vždy vítěz, díky prodloužení/nájezdům)

Žádné dlouhé zdůvodňování navíc. Pokud se uživatel zeptá "proč" nebo "na základě čeho", teprve pak rozveď klíčová čísla (formu, vzájemnou bilanci) ze skriptového výstupu.

**Pokud uživatel chce i přesný výsledek** ("jaké bude skóre", "tipni přesný výsledek"), skript na konci výstupu už sám nabízí `Nejpravdepodobnejsi presne skore` (fotbal/hokej, Poissonův model) nebo `Nejpravdepodobnejsi pomer setu` (tenis) - stačí to zkopírovat do odpovědi, nepočítej to ručně. Vždy k tomu připoj i skriptem dodané varování o nízké spolehlivosti (přesné skóre se u fotbalu/hokeje trefí jen zhruba 1x z 8-10, ne že je to jistota) - jinak by to působilo mnohem jistěji, než jak to doopravdy je.

## Volitelně: herní úroveň u tenisu (kdo vyhraje konkrétní game)

Hlavní tenisová data (`tenis/*.csv`) mají jen konečné skóre setu (např. "7-6 6-4"), ne pořadí jednotlivých gamů. Pro to existuje doplňkový nástroj nad `tenis/prubeh/` (Match Charting Project):

```bash
python3 .claude/skills/match-probability/scripts/game_flow.py "Jannik Sinner" "Carlos Alcaraz"
```

Vrátí pravděpodobnost udržení podání pro oba hráče z jejich historie - ale **pokrytí je jen ~15-20 % zápasů od 2020, silně zkreslené k top hráčům** (viz `README.md`). Pokud skript řekne, že zápas není nachartovaný, neznamená to chybu - prostě ta úroveň detailu u tohohle zápasu/hráče není k dispozici, řekni to uživateli stejně přímo jako u chybějících dat jinde.

**Živý zvrat podle stavu zápasu**: `game_flow.py --zvrat` ukáže, jak se pravděpodobnost výhry mění podle aktuálního stavu (sety/gamy) - např. hráč prohrávající 0:2 ve 2. setu po ztraceném 1. setu má historicky jen ~5% šanci, ale po srovnání na 5:1 je to zpátky skoro 50:50. Pro konkrétní stav použij `game_flow.py --state <sety_moje> <sety_soupere> <gamy_moje> <gamy_soupere> [m|w]`. Tahle tabulka je agregovaná přes všechny nachartované zápasy, takže funguje i pro zápasy/hráče, co sami nachartovaní nejsou - je to obecná vlastnost tenisu, ne konkrétní dvojice. Použij to, když se uživatel zeptá na "živou" šanci uprostřed zápasu nebo na to, jak moc je daný stav zlomový.

**Důležitý poctivý nález z backtestu** (`game_flow.py --backtest`): predikce "kdo vyhraje game N" se u testovaných 40 zápasů (963 gamů) **shodovala 1:1 s triviálním pravidlem "podávající vždy vyhraje svůj game"** (79,3 % přesnost obou). V profi tenise je držení podání natolik dominantní (typicky 65-85 %), že jemnější zohlednění brejkové úspěšnosti soupeře prakticky nikdy nezmění tip. Řekni tohle uživateli na rovinu, pokud se zeptá "jak přesné to je" - je to poctivé zjištění o tenise samotném, ne o nedostatečném modelu. Kdo podává v gamu 1 (a tedy i ve všech lichých gamech) se losuje těsně před zápasem - to predikovat nejde, je to 50:50.

## Volitelně: profil konkrétního hráče

Pokud se uživatel zeptá na KONKRÉTNÍHO hráče (ne na zápas) - jeho věk, aktuální klub, přestupovou historii, sezónní statistiky (starty/góly/asistence/karty u fotbalu, góly/asistence/+-/trestné minuty u hokeje, nebo výhry/% zákroků u brankáře) - použij:

```bash
python3 .claude/skills/match-probability/scripts/player_profile.py fotbal "Erling Haaland"
python3 .claude/skills/match-probability/scripts/player_profile.py hokej "Connor McDavid"
```

**Pokrytí**: fotbal jen 11 z 22 lig (jen NEJVYŠŠÍ soutěž každé země - Premier League, Bundesliga, Serie A, La Liga, Ligue 1 atd., žádné druhé ligy ani nižší skotské soutěže) a data aktuální k 6. 7. 2026 (zdroj - Transfermarkt - má od poloviny července 2026 pozastavenou aktualizaci, takže úplně čerstvé přestupy/zápasy chybět mohou). Hokej pokrývá celou NHL průběžně. Pokud skript hráče nenajde, řekni to rovnou - je to buď mimo pokrytí, nebo nesedí jméno (zkus jinou variantu).

Tohle je DOPLNĚK k `aggregate_stats.py` (ten počítá pravděpodobnost výsledku ZÁPASU dvou týmů/hráčů) - použij `player_profile.py`, když jde o jednotlivce samotného, ne o souboj dvou stran.

## Volitelně: porovnání s živými sázkovými kurzy

Pokud je nastavená proměnná prostředí `ODDS_API_KEY` (klíč z the-odds-api.com, zdarma 500 kreditů/měsíc - viz hlavička `scripts/odds_compare.py`), můžeš navíc spustit:

```bash
python3 .claude/skills/match-probability/scripts/odds_compare.py fotbal "Arsenal" "Leeds"
```

Tohle vrátí implikovanou pravděpodobnost z průměru živých bookmakerských kurzů (bez marže) pro nadcházející zápas - je to dobrá kontrola, jestli náš odhad z historie nejede mimo realitu, protože trh v sobě má zaceněné i věci, co náš model neumí (zranění, čerstvá forma, motivace - viz `references/metodika.md`). Velký rozdíl (>15-20 procentních bodů) stojí za zmínku uživateli jako "náš odhad se dost liší od trhu, pravděpodobně kvůli něčemu, co data nezachycují."

**Nepoužívej to automaticky u každého dotazu** - stojí to API kredity (u fotbalu/hokeje 1 kredit, u tenisu pár kreditů podle počtu právě běžících turnajů) a funguje to jen pro NADCHÁZEJÍCÍ zápasy, ne historické. Použij to, když o to uživatel výslovně požádá ("porovnej to s kurzy", "co na to sázkové kanceláře") nebo když chceš u důležité predikce druhou kontrolu. Pokud proměnná `ODDS_API_KEY` není nastavená, skript to rovnou řekne i s návodem na založení účtu - neřeš to jako chybu, je to čistě volitelný doplněk.

## Volitelně: stavba sázkových tiketů (SÓLO i AKO kombinace)

Pokud uživatel chce rovnou TIKET (konkrétní sázku s vkladem, ne jen procenta) - "slož mi sázku", "jaký tiket na dnešek", "udělej kombinaci" - použij:

```bash
python3 .claude/skills/match-probability/scripts/ticket_builder.py den 2024-03-16   # historický den (má smysl jen na už odehraný den, kde známe i kurzy)
python3 .claude/skills/match-probability/scripts/ticket_builder.py backtest 40       # 40 náhodných dní, změří úspěšnost
```

Funguje jen pro **fotbal** (jediný sport, kde máme v `fotbal/*.csv` i skutečné historické kurzy - sloupce `Avg*`, průměr víc sázkových kanceláří, NE přímo Fortuna). Hledá "hodnotové sázky" (edge mezi modelem a odvigovaným trhem) na obou stranách každého trhu (1X2, přes/pod 2.5 gólu, hendikep) - takže klidně navrhne i sázku na outsidera nebo hendikep na poraženého, ne jen na favorita. Staví SÓLO i AKO (kombinované) tikety podle pravidel Fortuny (AKO = kurzy se násobí, kombinuje se vždy jen přes různé zápasy).

**Důležitý poctivý nález z backtestu** (viz `references/metodika.md` pro čísla): AKO kombinace v testu **prohrály úplně všechny** (0/40, ROI -100 %) - kombinování i hodnotných jednotlivých sázek nefunguje, protože nejistoty se násobí mnohem rychleji, než roste kurz. SÓLO vyšlo mírně ztrátově (-14,8 %), ne ziskově - náš jednoduchý historický model nemá prokázanou výhodu nad tržní cenou (ta v sobě má zaceněné informace, co náš model nevidí). Řekni tohle uživateli na rovinu, pokud se zeptá na reálnou výkonnost - skript je užitečný jako DEMONSTRACE stavby tiketu a jeho poctivého vyhodnocení, ne jako garance výhry. Žádná sázková strategie nemůže zaručit, že banka neklesne pod počáteční vklad - to je matematická vlastnost sázení (nenulová šance prohry u každé sázky), ne nedostatek skriptu.

## Volitelně: sázková výhoda u tenisu (automatizované sázení pomocí AI)

Pokud se uživatel zeptá, jestli lze postavit automatického sázecího bota na tenis (nebo obecně "má tenhle model sázkovou výhodu"), nejdřív stáhni historické kurzy (jen WTA, viz hlavička skriptu proč jen ta tura) a pak spusť test:

```bash
python3 .claude/skills/match-probability/scripts/fetch_tennis_odds.py           # jednorázově stáhne kurzy
python3 .claude/skills/match-probability/scripts/tennis_value_backtest.py --diagnostika
python3 .claude/skills/match-probability/scripts/tennis_value_backtest.py --pridana-hodnota   # nejpřísnější test
python3 .claude/skills/match-probability/scripts/tennis_value_backtest.py --segmenty          # rozpad podle kurzu/povrchu/kola
```

**Poctivý nález** (viz `references/metodika.md` pro plná čísla): model (ani jednoduchý `forma+h2h`, ani Elo) **nemá žádnou prokázanou sázkovou výhodu** - trh tipuje vítěze přesněji (66,0 % vs. 60,6-63,8 %), hodnotové sázky jsou ztrátové (ROI -7,7 % až -10,1 %) a nejpřísnější test (namíchání modelu do tržní ceny) ukázal, že **žádná váha modelu nezlepší predikci nad čistý trh** - model nedrží vůbec žádnou informaci navíc. Řekni tohle uživateli přímo, pokud se zeptá na stavbu automatizovaného sázecího bota - není to nedostatek implementace (zkusily se dvě různé metodiky), je to důsledek toho, že ATP/WTA kurzy jsou jeden z nejlikvidnějších a nejefektivnějších sportovních trhů - veřejná data, ze kterých model počítá, už má trh dávno zaceněná.

## Volitelně: živé sledování probíhajících tenisových zápasů (fiktivní tikety na favority)

Pokud uživatel chce sledovat **právě probíhající** tenisové zápasy a nechat model zakládat fiktivní tikety "za běhu" (mezi gemy/sety), použij dvojici skriptů. Potřebují dva klíče v `~/.env`: `LIVE_TENNIS_API_KEY` (livetennisapi.com - živé skóre po gemech a bodech) a `ODDS_API_KEY` (skutečné živé kurzy).

```bash
cd /root/statistiky/.claude/skills/match-probability/scripts && source ~/.env
python3 live_tennis_simulator.py watch   # sleduje průběh VŠECH živých zápasů, hlásí události, zakládá tikety
python3 live_tennis_simulator.py status  # rychlý přehled, nestojí API kvótu
python3 bet_evaluator.py vyhodnot        # zjistí výsledky dohraných zápasů a připíše je do banky
python3 bet_evaluator.py report          # jen přehled s podílem výher, ROI a vývojem banky, nestojí API kvótu
```

**Cíl tohohle nástroje NENÍ porazit trh** (viz nález výš - žádná prokázaná výhoda) - je to, aby banka **mezi jednotlivými tikety spíš rostla než klesala**. Proto nehledá "hodnotu" proti trhu, ale **silné favority, na kterých se nezávisle shodnou model i skutečný trh** (model aspoň 75 % šance, trh aspoň 65 %, kurz do 1,60) - ti v historických datech vyhrávají velmi často. Rozpočet je **1000 fiktivních mincí** (žádné skutečné peníze, žádný sázkový účet), stav žije v `live_bets_log.jsonl` a `live_progress_log.jsonl` - skripty jsou mezi spuštěními bezstavové, dají se spouštět opakovaně v čase (doporučeně `watch` každých 15-30 minut, limit free tieru je 100 volání/den). **Kompletní samostatný návod je v `AGENT_NAVOD.md`.**

**Důležité rozlišení, které je třeba uživateli říkat přesně:** vysoký podíl vyhraných tiketů (= banka mezi tikety spíš roste) NENÍ totéž co kladné ROI nebo zaručený dlouhodobý zisk. Sázková marže zůstává zaceněná i v kurzu na favorita - i při 90% úspěšnosti může jedna prohra smazat zisk z mnoha malých výher. `bet_evaluator.py report` proto hlásí obojí zvlášť: "podíl rostoucích tiketů" (hlavní cíl) a ROI (poctivé peněžní měřítko) - nepleť je dohromady, když referuješ výsledky.

### Rychlejší varianta: sázka na vítěze AKTUÁLNÍHO GEMU (`live_game_bet.py`)

Oddělený skript, oddělená banka (`live_game_bets_log.jsonl`) - sází na vítěze PRÁVĚ ROZEHRANÉHO GEMU, ne celého zápasu. Mnohem vyšší frekvence (gem trvá pár minut), ale **bez nezávislého trhu kurzů na ověření** (Odds API nemá kurzy na jednotlivé gemy) - sází čistě na historický hold rate přepočítaný na pravděpodobnost z aktuálního bodového skóre (matematický přepočet téhož čísla, ne nová informace).

```bash
python3 .claude/skills/match-probability/scripts/live_game_bet.py tick     # jedno kolo: vyhodnotí + hledá nové
python3 .claude/skills/match-probability/scripts/live_game_bet.py status   # přehled, nestojí API kvótu
```

Potřebuje spouštět **mnohem častěji** než `watch` (řádově co 1-3 minuty, ne co 15-30) - při free tieru (100 volání/den) to vydrží jen pár hodin provozu, takže ho spouštěj v časově omezené smyčce, ne natrvalo, a vždy zkontroluj `/usage` a `crontab -l`, jestli neběží souběžně i `watch` na stejný klíč. Kompletní návod včetně modelu a příkladu smyčky je v `AGENT_NAVOD.md`, sekce 12.

### Agresivní varianta: rychlé znásobení s cílem a limitem (`agresivni-tick`)

Třetí, oddělený režim ve stejném skriptu (vlastní banka `live_game_bet_aggressive_log.jsonl`) - na výslovné přání uživatele, který chtěl "rychle znásobit" a potvrdil, že chce i riziko okamžité ztráty všeho ("risk je zisk, proto to existuje"). **Sází se CELÁ aktuální banka na jeden tiket** (vybírá se zápas s nejnižší pravděpodobností, co ještě splní bezpečnostní práh 70 %, pro nejvyšší dostupný kurz). Po dosažení cíle 6000 (6× start) se přepne do ochranné fáze (sází se už jen nejvýš 1000 z banky) a sleduje vrchol - jakmile banka klesne o 1000 od vrcholu, agent se **natrvalo zastaví**.

```bash
python3 .claude/skills/match-probability/scripts/live_game_bet.py agresivni-tick     # jedno kolo
python3 .claude/skills/match-probability/scripts/live_game_bet.py agresivni-status   # přehled, nestojí API kvótu
```

**Tohle není "spíš poroste" nástroj jako ostatní dva** - je to vědomě vysoce rizikové nastavení. Realistický výsledek je buď rychlý růst k cíli, nebo rychlá ztráta všeho - žádné plynulé mezistádium. Mluv o tom s uživatelem takhle na rovinu. Jakmile hlásí "ZASTAVENO", dál to nespouštěj (agent sám odmítne nový tiket). Podrobnosti a zdůvodnění 50%→100% kompromisu v `AGENT_NAVOD.md`, sekce 13, a v `references/metodika.md`.

## Když data chybí

Skript hledá jen v tom, co je v `/statistiky` - u fotbalu je to 22 evropských lig, u hokeje jen NHL, u tenisu prakticky celá ATP/WTA túra (viz `/statistiky/README.md` pro přesný rozsah). Pokud se někdo zeptá na zápas mimo tento rozsah (např. mimoevropský klub, KHL, MS v hokeji), skript žádná data nenajde - v tom případě to uživateli řekni rovnou, místo abys dopočítal procenta z ničeho. Je v pořádku říct "na tenhle zápas nemám v datech dost podkladů."
