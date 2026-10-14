# Metodika výpočtu pravděpodobnosti

Jde o jednoduchý, transparentní statistický odhad z historických dat - ne o profesionální predikční model (žádné kurzové trhy, žádný ELO rating v čase, žádné zohlednění aktuálních zranění). Je to dobrý orientační odhad podložený reálnými čísly, ne věštění z koule.

## Fotbal (3 výsledky: výhra domácích / remíza / výhra hostů)

Pro každý tým se spočítá "skóre":

```
skóre_domácí = 0.4 × forma (posledních 10 zápasů, výhry/zápasy)
             + 0.3 × historický win rate na domácí půdě
             + 0.3 × win rate ve vzájemných zápasech (pokud jich je aspoň pár; jinak celkový win rate)

skóre_hosté = stejně, ale s "venku" win rate místo "doma"

remíza = historická remízovost v příslušné soutěži (lize), kde oba týmy hrají
```

Všechny tři složky (skóre_domácí, skóre_hosté, remíza) se normalizují tak, aby součet dal 100 %.

**Proč tyhle váhy:** nedávná forma (40 %) váží nejvíc, protože zachycuje aktuální stav týmu (zranění, zápalu, sérii) lépe než sezónní průměr. Domácí/venkovní split (30 %) odráží reálně měřitelnou domácí výhodu. Vzájemná bilance (30 %) zachycuje styl, který jednomu týmu historicky sedí nebo nesedí proti druhému - ale jen pokud je k dispozici dost vzájemných zápasů, jinak by pár náhodných výsledků zbytečně zkreslovalo odhad.

## Tenis (2 výsledky: výhra hráče A / hráče B)

```
skóre_hráč = 0.5 × forma (posledních 15 zápasů)
           + 0.3 × win rate ve vzájemných duelech
           + 0.2 × celkový win rate za celé období
```

**Proč forma váží nejvíc (50 %):** v tenise se forma hráče mění rychleji než ve fotbale (jeden hráč může mít famózní měsíc kvůli naladěnému servisu, druhý se zrovna vrací ze zranění) a je silnějším signálem než zápasy staré 3-4 roky.

Model nebere v potaz povrch (tvrdý/antuka/tráva) ani konkrétní turnaj - pokud se uživatel zeptá na zápas na konkrétním povrchu a chce přesnější odhad, dá se to dopočítat ručně z `tenis/*.csv` (sloupec `surface`), skript aktuálně počítá přes všechny povrchy dohromady.

## Hokej (2 výsledky: výhra týmu A / týmu B)

```
skóre_tým = 0.45 × forma (posledních 15 zápasů)
          + 0.25 × historický win rate doma/venku (podle toho, kde hraje)
          + 0.30 × win rate ve vzájemných zápasech
```

NHL zápasy nikdy nekončí remízou (prodloužení + nájezdy), takže model má jen dva výsledky.

## Co model NEumí a kdy mu nevěřit naslepo

- Nezohledňuje aktuální zranění, výměny hráčů, nebo motivaci (např. zápas "o nic" na konci sezóny vs. finále).
- U málo odehraných zápasů (nový tým, nový hráč na túře) je odhad nespolehlivý - čím míň dat skript najde, tím opatrněji k číslu přistupuj.
- Je to popisná statistika z minulosti, ne kauzální model - neumí predikovat zlomové momenty (změna trenéra, obrat formy).

Pokud tyhle kontextové informace znáš (např. víš, že klíčový hráč je zraněný), je rozumné procenta z výstupu skriptu jemně posunout vlastním úsudkem a říct, že jde o ruční korekci - ne předstírat, že číslo pořád vychází čistě z dat.

## Doplňkové trhy (`backtest.py`): přesné skóre, rohy, karty, SOG, PIM, esa, dvojchyby

`aggregate_stats.py` (hlavní skill) dává jen procenta výhra/remíza/prohra. `backtest.py`
navíc umí predikovat přesné skóre (Poisson rozdělení ze střeleckého průměru) a
"kdo bude mít víc" u rohů/karet (fotbal), střel na branku/trestných minut (hokej)
a es/dvojchyb (tenis) - a hlavně umí tyhle predikce zpětně otestovat proti
skutečným výsledkům (viz `backtest.py --help` resp. hlavička souboru).

### Zjištění z testování (náhodný vzorek 50 zápasů/sport, 2022-2026, seed=42)

| Trh | Přesnost | Baseline (náhoda) |
|---|---|---|
| Fotbal - výsledek | 46 % | ~33 % |
| Fotbal - přesné skóre | 14 % | ~5-10 % |
| Fotbal - víc rohů | 52 % | ~40-45 % |
| Fotbal - víc karet | 40 % | ~40-45 % |
| Hokej - výsledek | 64 % | 50 % |
| Hokej - přesné skóre | 10 % | ~5-8 % |
| Hokej - víc střel na branku | 56 % | ~45-50 % |
| Hokej - víc trestných minut | 36 % | ~45 % |
| Tenis - vítěz | 70 % | 50 % |
| Tenis - přesný poměr setů | 52 % | ~35-50 % |
| Tenis - víc es | 58 % | ~45 % |
| Tenis - víc dvojchyb | 38 % | ~45 % |

### Vzájemné zápasy (h2h) nejen u karet, ale u celého zápasu

Výhra/remíza/prohra (`h2h_home_wr`/`h2h_away_wr`) počítala se vzájemnými zápasy
odjakživa. Zpočátku ale **přesné skóre, rohy a střely na branku** vzájemné
zápasy ignorovaly a počítaly jen z obecného průměru týmu - přitom styl dvou
konkrétních týmů/soupeřů proti sobě je měřitelně jiný než jejich průměr proti
komukoliv jinému:

| Ukazatel | Odchylka h2h průměru od celkového průměru (dvojice se 3-4+ vzájemnými zápasy) |
|---|---|
| Fotbal - góly | ~22 % (0.6 gólu z průměru 2.7) |
| Fotbal - rohy | ~12 % (1.2 rohu z průměru 9.8) |
| Fotbal - karty | ~22 % (0.9 karty z průměru 4.25) |
| Hokej - góly | ~9 % (0.59 gólu z průměru 6.23) |
| Hokej - střely na branku | ~4 % (2.6 střely z průměru 59.7) |
| Hokej - trestné minuty | ~21 % (3.8 minuty z průměru 18.2) |
| Tenis - esa | značný rozptyl, ale v testu neprokázán reálný přínos (viz níže) |

Proto teď **přesné skóre (Poisson λ) a rohy u fotbalu, přesné skóre a střely
na branku u hokeje i esa u tenisu** používají stejnou kombinaci jako karty/PIM:
65 % (fotbal/tenis) resp. 65 % (hokej) vlastní tým/hráč + 35 % vzájemné zápasy,
pokud jich je aspoň 3. Efekt na přesnost: fotbalové přesné skóre 12 %→14 %,
hokejové přesné skóre 6 %→10 %, hokejové střely na branku 52 %→56 %. Rohy a
tenisová esa vyšly v tomhle konkrétním vzorku prakticky beze změny (52-54 %,
resp. 58 %) - u tenisu navíc jen 7 z 50 testovaných zápasů vůbec mělo aspoň 3
předchozí vzájemná utkání, takže tam se úprava uplatní jen zřídka (u hráčů,
kteří proti sobě hrají opakovaně na túře, bude mít větší váhu).

Vyzkoušel jsem i vzájemně specifický vzorec poměru setů v tenise místo
obecně nejčastějšího vzorce pro daný počet setů - v testu nedal žádné
zlepšení (vzájemných zápasů se stejným best_of je mezi dvěma konkrétními
hráči obvykle málo), takže zůstal obecný vzorec.

## Herní úroveň u tenisu (`game_flow.py`): kdo vyhraje konkrétní game

Hlavní tenisová data mají jen konečné skóre setu - z nich NEJDE spočítat,
kdo vyhrál game č. 3/4/5/6, protože se tam neukládá pořadí gamů, jen výsledek
setu. Pro tohle je potřeba úplně jiný typ zdroje - bod-po-bodu záznam
zápasu, ne jen souhrnné statistiky.

Takový zdroj existuje: [Jeff Sackmannův Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject),
dobrovolnický crowdsourced projekt. Pokrývá ale jen **cca 15-20 % profi
zápasů od roku 2020** a silně nerovnoměrně - u sledovaných hráčů (Sinner,
Alcaraz, Djokovič) stovky zápasů, u hráčů mimo top 100 žebříčku často nic,
protože dobrovolníci chartují hlavně zápasy, které sledují. Licence CC
BY-NC-SA 4.0 (jen nekomerční použití). Ze syrových bod-po-bodu dat (93 MB,
notace úderů nečitelná pro člověka) jsme si odvodili jen kompaktní tabulku
"kdo podával a kdo vyhrál který game" (`tenis/prubeh/games_{m,w}.csv`,
~10 MB) - víc jsme z toho nepotřebovali.

**Metodika**: z historických nachartovaných zápasů (před datem testovaného
zápasu) se spočítá `hold_rate` (jak často hráč udrží vlastní podání) a
`break_rate` (jak často prolomí soupeřovo). Pravděpodobnost, že podávající
vyhraje daný game: `(hold_rate podávajícího + (1 - break_rate přijímajícího)) / 2`.

**Poctivý nález z backtestu** (40 zápasů, 963 gamů, `game_flow.py --backtest`):
tahle predikce vyšla **přesně stejně** jako triviální "podávající vždy
vyhraje svůj game" - 79,3 % oboje. Rozsah predikovaných pravděpodobností
byl 59-94 %, nikdy pod 50 % - tedy model nikdy nedoporučil vsadit na
přijímajícího, protože v profi tenise je držení podání (typicky 65-85 %) tak
dominantní, že ani nadprůměrný brejkér soupeře obvykle nestačí na podprůměr
ve hře toho druhého. Tohle je reálné zjištění o tenise, ne o nedostatečnosti
vzorce - jednotlivý game je v profi tenise mnohem předvídatelnější (kdo
podává) než set nebo zápas jako celek.

Kdo podává v gamu 1 (a tím i ve všech lichých gamech) se losuje těsně před
zápasem - to z dat předem zjistit nejde, je to 50:50 nezávisle na všem
ostatním.

## Kdo vyhraje 1. a 2. set (ne jen celý zápas) - s/bez statistiky průběhu

Na rozdíl od "kdo vyhraje game N" (viz výš) jde "kdo vyhraje set 1/set 2"
spočítat i bez Charting dat - ze `hold_break_rate()` (game_flow.py) se dá
odvodit pravděpodobnost výhry CELÉHO setu standardním kombinatorickým
vzorcem (Markov řetězec přes skóre v setu 0-0 až 6-6+tiebreak, střídání
podání po gamech). U 1. setu je potřeba zprůměrovat přes obě možnosti, kdo
podává jako první (to se losuje těsně před zápasem, nejde to vědět dopředu).

**Poctivý test na 186 zápasech** (nachartované zápasy z posledních ~30 %
dat chronologicky, aby se zabránilo úniku informace do tréninkové části -
viz níže o "momentum deltě"):

| Predikce | Přesnost |
|---|---|
| Set 1 (kombinatorický model, podání 1. gamu neznámé) | 62,4 % |
| Set 2 BEZ statistiky průběhu (ignoruje výsledek 1. setu) | 65,6 % |
| Set 2 S statistikou průběhu (momentum delta dle 1. setu) | **74,7 %** |
| Set 2 - naivní baseline ("vyhraje stejný hráč jako 1. set") | 74,2 % |

**Statistika průběhu zápasu (= "momentum") je reálná a měřitelná**: hold
rate hráče ve 2. setu je **+5,7 procentního bodu vyšší**, pokud vyhrál
1. set (80,7 % vs. základních 75,0 %), a **-6,8 b. nižší**, pokud ho
prohrál (68,2 %) - spočítáno ze 101 367 gamů na tréninkové (starší)
části dat. Přidání týhle statistiky do modelu zvedlo přesnost predikce
2. setu z 65,6 % na 74,7 % - o 9 procentních bodů, to je skutečné a
použitelné zlepšení.

**Ale stejný poctivý zádrhel jako u gamů**: naivní pravidlo "kdo vyhrál
1. set, vyhraje i 2." (žádný model, jen jedno `if`) dosahuje 74,2 % -
prakticky identicky s plným kombinatorickým modelem (74,7 %, rozdíl
0,5 b. je v mezích šumu na 186 zápasech). Momentum efekt je skutečný, ale
TAK silný, že většinu jeho predikční síly zachytí i triviální pravidlo bez
jakéhokoli výpočtu - sofistikovaný model (hold/break rate + kombinatorika)
přidává jen malý zlomek navíc. Řekni tohle uživateli na rovinu, pokud se
zeptá "vyplatí se počítat set 2 složitě" - krátká odpověď je "skoro ne,
kdo vyhrál set 1, většinou vyhraje i druhý, a to samo o sobě už je skoro
tak dobrý tip jako celý model."

## Živé kurzy "mezi gemy/sety" na vítěze zápasu - funguje mechanismus, NE "vydělávání mincí"

Zkusili jsme rozšířit stavový model o kombinatorický výpočet (Markov řetězec
přes skóre v setu i v zápase, z `hold_break_rate()`), který po KAŽDÉM gemu
přepočítá pravděpodobnost/kurz na vítěze CELÉHO zápasu - a nechali model
"sledovat celý průběh" historického zápasu se simulovanou bankou mincí,
která roste/klesá podle toho, jestli model proti "trhu" najde hodnotu.

**Výsledek: mechanismus (přepočet kurzu po každém gemu) funguje správně a
dává smysluplná čísla** - příklad, reálný zápas Casper Ruud - Jannik
Sinner (17. 5. 2026, Sinner hold rate 87,2 %, Ruud 84,2 %):

```
set  skóre gemů  podává    P(Ruud vyhraje zápas)  kurz Ruud  kurz Sinner
1    0-0         Ruud      41,1 %                 2,43       1,70
1    2-0         Ruud      58,4 %                 1,71       2,40   <- Ruud brejkl, dočasně favorit
1    4-5         Sinner    22,4 %                 4,47       1,29   <- Sinner srovnal a přebral vedení
2    0-2         Ruud       6,1 %                16,39       1,06
2    3-5         Ruud       2,2 %                44,55       1,02
```
(skutečný vítěz: Sinner - odpovídá trajektorii čísel)

**Ale "kolik mincí by model vydělal proti trhu" se nedá poctivě změřit,
protože žádná reálná live kurzová data pro tenis v `/statistiky` nejsou**
(na rozdíl od fotbalu, kde máme skutečné historické kurzy v CSV). Vyzkoušeli
jsme dvě náhrady za "trh" a obě byly zavádějící:

1. **Obecný/neinformovaný trh** (oba hráči = průměrný hold rate) - "edge"
   vznikl už při stavu 0-0/0-0 (před prvním gemem) jen z toho, že model zná
   konkrétní hráče a trh ne. To testuje předzápasovou znalost, ne živý
   průběh - skoro všechny sázky padaly hned na začátku.
2. **Trh = stejný model se zpožděním** (o celý set, pak zkráceno na 1 gem) -
   tohle je TAUTOLOGIE: trh je jen zastaralá kopie modelu se stejným
   vzorcem, takže model má téměř jistou výhru "z definice" (má vždy
   čerstvější verzi identické formule). Banka v testu rostla exponenciálně
   (1000 → 119 430 mincí za 150 zápasů, win rate 70 %) - to není skutečný
   nález o tenise, je to artefakt porovnávání modelu se sebou samým.

**Závěr**: nástroj na zobrazení živých kurzů v průběhu zápasu (`match_win_prob`
v `scripts/` - dá se použít k ukázání, jak se šance mění po každém gemu) je
plně funkční a použitelný jako informační přehled. Ale "kolik by se dalo
vydělat" se bez reálných live kurzů změřit nedá - kdyby se uživatel zeptal
na skutečnou ziskovost živého sázení v tenise, je čestná odpověď "na to
nemáme data, jen na fotbal u predzápasových kurzů" (viz sekce o
`ticket_builder.py` výš).

## Pravděpodobnost výhry podle aktuálního stavu zápasu ("živý" zvrat)

Zvrat se neděje na úrovni "kdo vyhrál první set" (to je jen výsledek) - děje
se v konkrétních herních situacích uprostřed setu, přesně jak to popsal
uživatel na příkladu: hráč prohrává 0:2 v druhém setu po ztraceném prvním
(to je nejhorší bod zápasu, nejvyšší kurz/nejnižší šance), pak se srovná na
5:1 nebo 6:1 (šance zpátky k 50:50), pak znovu klesne na 1:4 v rozhodujícím
setu (téměř nulová šance), a přesto zápas otočí.

`game_flow.py --zvrat` spočítá z `tenis/prubeh/games_{m,w}.csv` (Match
Charting Project) empirickou pravděpodobnost výhry CELÉHO zápasu pro KAŽDOU
kombinaci (rozdíl setů, rozdíl gamů v aktuálním setu) - tím, že projde
všechny nachartované zápasy, a pro každý odehraný game zaznamená stav před
ním z pohledu obou hráčů + jestli nakonec vyhráli. Žádná predikce dopředu -
čistě "kolikrát se to v historii stalo a jak to dopadlo".

Ověřené na datech (ATP, tisíce až desítky tisíc případů na řádek):

| Stav (sety, gamy v aktuálním setu) | P(výhra zápasu) | n |
|---|---|---|
| Prohrál 1. set, prohrává 0:2 ve 2. setu | 5 % | 4 038 |
| Prohrál 1. set, začátek 2. setu (0:0) | 21 % | 12 329 |
| Vyrovnáno, začátek setu | 50 % | 31 484 |
| Prohrává 0:4/1:4 v aktuálním setu | 11 % | 968 |
| Prohrál 1. set, ale vede 5:1 ve 2. setu | 48 % | 54 |
| Vede 1:0 na sety, vede 2:0 v gamech | 95 % | 4 038 |

Přesně to, co uživatel popsal: pád na ~5 %, návrat k ~50 % po srovnání na
5:1, a extrémy (95%+ favorit / pod 5% outsider) odpovídají intuici
sázkových kurzů, i když tohle NEJSOU skutečné kurzy - je to empirická
historická četnost, ne live tržní cena. `game_flow.py --state <sety_moje>
<sety_soupere> <gamy_moje> <gamy_soupere> [m|w]` dá odpověď pro libovolný
konkrétní stav.

**Omezení**: stejné pokrytí jako zbytek `tenis/prubeh/` (~15-20 % zápasů,
zkreslené k top hráčům) - tabulka je ale agregovaná přes VŠECHNY
nachartované zápasy (ne jen konkrétní dvojici hráčů), takže funguje i když
samotný dotazovaný zápas nachartovaný není - je to obecná "fyzika" tenisu
(jak těžké je otočit z daného stavu), ne vlastnost konkrétních dvou hráčů.
Rozdíl setů je omezen na ±2 a gamů na ±6 kvůli řídkým datům na okrajích
(víc než ±6 gamů v jednom setu skoro nenastane). U extrémně řídkých buněk
(`n < 20`) se automaticky použije širší odhad jen podle rozdílu setů.

**Karty, trestné minuty a dvojchyby jsou dlouhodobě nejslabší disciplíny** - prostý
průměr týmu/hráče na ně nestačí, protože je mnohem víc ovlivňují okolnosti
konkrétního zápasu (rozhodčí, rivalita, aktuální forma podání) než historický
průměr. Proto model u těchto tří trhů používá navíc:

- **Fotbalové karty**: kombinace vlastního průměru týmu (65 %) + průměru ve
  vzájemných zápasech konkrétně proti tomuto soupeři (35 %, pokud existují
  aspoň 3 vzájemné zápasy - derby mají prokazatelně jiný počet karet než
  průměr, odchylka cca 0.9 karty/zápas od ligového průměru). Pokud je u zápasu
  známý rozhodčí (jen anglické a skotské ligy mají `Referee` sloupec), přidá
  se jeho osobní tendence (80/20 směs) - mezi rozhodčími je směrodatná
  odchylka v počtu karet 0.5/zápas, není to šum. Defaultní hodnoty pro
  málo-datové případy navíc nejsou ploché "2.0 pro oba", ale empiricky změřený
  rozdíl domácí/hosté (1.98 vs 2.27 - hosté dostávají dlouhodobě víc karet,
  pravděpodobně vliv diváckého tlaku na rozhodčí).
- **Hokejové trestné minuty**: stejný princip jako karty, ale bez rozhodčího
  (NHL data ho neobsahují) - 60 % vlastní průměr týmu, 40 % průměr ve
  vzájemných zápasech (u PIM je tenhle efekt ještě silnější než u fotbalových
  karet - odchylka cca 20 % od ligového průměru u dvojic s aspoň 4 vzájemnými
  zápasy).
- **Tenisové dvojchyby**: dvojchyby jsou překvapivě stabilní osobní vlastnost
  hráče (vysoká korelace mezi náhodnými polovinami historie jednoho hráče),
  ale liší se podle povrchu (tráva ~7/zápas, antuka ~5.7/zápas) - model proto
  počítá průměr z zápasů na stejném povrchu jako testovaný zápas (s fallbackem
  na celkový průměr, pokud hráč nemá na daném povrchu aspoň 8 zápasů), a práh
  pro "vyrovnáno" je nižší (0.1 místo 0.5 u es) - testy ukázaly, že vyšší práh
  zbytečně často hlásil remízu tam, kde reálně vyhrál jeden hráč jasně.

**Metodologická past, na kterou jsme přišli při ladění:** v prvních verzích
testu byl v tenisovém testu hráč "p1" vždy definovaný jako skutečný vítěz
zápasu. To nenápadně protáhlo do testu informaci o výsledku - vítězové mají
v daném zápase prokazatelně míň dvojchyb než poražení (48 % zápasů vs. 32 %,
zbytek remíza), protože ten den podávali líp. Reálná předpověď dopředu ale
neví, kdo vyhraje - proto `run_tennis_backtest()` teď p1/p2 přiřazuje náhodně
(seedované podle jmen a data zápasu), aby test měřil to samé, co bude model
dělat v praxi u budoucího zápasu.

## Stavba sázkových tiketů (`ticket_builder.py`): hodnotové sázky proti reálným kurzům

Fotbalová data (`fotbal/*.csv`) obsahují i skutečné historické kurzy několika
sázkových kanceláří (sloupce `Avg*` - průměr z více kanceláří, NE přímo
Fortuna, přesné historické kurzy Fortuny k dispozici nejsou) pro tři trhy:
výsledek (1X2), přes/pod 2.5 gólu, asijský hendikep. `ticket_builder.py`
z nich pro každý zápas spočítá odvigovanou tržní pravděpodobnost a porovná
ji s vlastním modelem (stejná h2h-blended Poissonova logika jako výš) - kde
model vychází výš o aspoň 4 procentní body (a ne o víc než 25 b., to už je
spíš šum z mála dat než skutečná hodnota, viz níže), je to "hodnotová sázka"
(value bet), ať už jde o favorita, outsidera, hendikep na poraženého, nebo
"pod" góly - edge se hledá na OBOU stranách každého trhu, ne jen u vítěze.

**Kalibrační kontrola** (600 náhodných zápasů 2022-2026, bucket podle
predikované `p_home`): model NENÍ systematicky přehnaně sebevědomý - v
pásmu 20-60 % (kde je dost dat, n=84-167 na bucket) je skutečná výhernost
blízko predikce, spíš mírně podhodnocená (model řekne 35 %, realita 41 %;
model řekne 45 %, realita 51 %). To ale neznamená, že JEDNOTLIVÉ zápasy s
extrémním edge (viděli jsme "EV +180 %" u nedávno postoupených týmů typu
Almere City/St Johnstone s minimem odehraných zápasů v datech) jsou
důvěryhodné - to je šum z malého vzorku dat pro konkrétní tým, ne skutečná
tržní neefektivita. Proto skript vyžaduje aspoň 15 dřívějších zápasů KAŽDÉHO
týmu (`MIN_TEAM_MATCHES`) a odmítá kurzy mimo rozumné pásmo 1.25-6.0
(`ODDS_RANGE`) i edge nad 25 procentních bodů (`EDGE_MAX`) - vše skoro jistě
artefakty, ne hodnota.

### Honest nález z backtestu (40 náhodných dní 2022-2023, denní rozpočet 1000 Kč, riskuje se 35 % denně)

| Typ tiketu | Tiketů | Výher | ROI |
|---|---|---|---|
| SÓLO (1 noha) | 40 | 15 (38 %) | **-14,8 %** |
| AKO (3 nohy z různých zápasů) | 40 | **0 (0 %)** | **-100,0 %** |
| Celkem | 80 | 15 | -40,4 % |

**AKO kombinace v tomhle testu prohrály úplně všech 40 tiketů.** Důvod není
"smůla" ani chyba výpočtu - i když každá jednotlivá noha kombinace projde
kontrolou "má edge", při kombinaci 3 nezávislých nejistot se SOUČIN jejich
pravděpodobností zmenšuje mnohem rychleji, než roste kurz (typický kurz
kombinace v testu byl 30-170), takže šance na trefení celého tiketu je v
praxi výrazně nižší, než naznačuje prostý součet dílčích edge. To je obecná
vlastnost kombinovaných sázek, ne specifikum tohohle modelu - je to přesně
důvod, proč jsou AKO sázky pro sázkové kanceláře tak výhodné. Skript proto
dává AKO jen 30 % rizikového rozpočtu dne (SÓLO 70 %) - i to je spíš "los
do loterie" než hlavní strategie.

**SÓLO samotné vyšlo mírně ztrátově (-14,8 %), ne ziskově.** To je čestný a
očekávatelný výsledek: `Avg*` kurzy jsou průměr už tak dost ostrých
sázkových trhů, které v sobě mají zaceněné informace (zranění, čerstvé
přestupy, pohyb peněz od informovaných sázejících), jaké náš jednoduchý
historický průměr nevidí. Trvale porazit zavírací/průměrnou tržní cenu je
i pro profesionální sázkové analytiky vzácné - tenhle model na to není
stavěný a výsledek to potvrzuje. Neznamená to, že je model k ničemu (pořád
dobře odhaduje SMĚR - kdo je favorit, viz tabulka přesnosti výš), jen že
rozdíl mezi jeho čísly a tržními kurzy není spolehlivý zdroj skutečné
sázkové výhody.

**Na otázku "nesmí se dostat banka pod 1000 Kč":** v testu se to i přes
konzervativní řízení rizika (jen 35 % rozpočtu denně, žádné AKO navíc)
nepovedlo v 65 % dní (26 z 40). To není selhání skriptu - žádná sázková
strategie se zápornou dlouhodobou hodnotou (a tenhle test žádnou kladnou
hodnotu neprokázal) nemůže zaručit, že banka neklesne pod startovní částku.
Konzervativní staking omezuje, o KOLIK klesne (nejhorší den v testu: 650 Kč,
tedy ne celá tisícovka), ale garance "nikdy pod 1000" by vyžadovala
nesázet vůbec.

### Další varianty vyzkoušené na stejných datech (300-965 náhodných dní/zápasů)

| Varianta | ROI | Poznámka |
|---|---|---|
| Baseline (SÓLO+AKO 3 nohy, edge≥4 %) | -40,4 % | viz výš |
| Jen SÓLO (žádné AKO) | -14,8 % | AKO je hlavní problém |
| AKO jen 2 nohy (místo 3) | -32,1 % (AKO samo -72 %) | kratší kombinace škodí míň, pořád ztrátové |
| Přísnější edge_min 8 % (místo 4 %) | -38,8 % | téměř beze změny - síla edge nekoreluje s reálnou výherností |
| Nižší risk_fraction 15 % (místo 35 %) | -40,4 % (stejné, jen menší částky) | ROI se staking-frakcí nemění, jen absolutní ztráta |
| Větší vzorek n=100 dní, jiný seed n=40 | podobné řády ztráty | výsledek není náhoda jednoho vzorku |
| **Jen 1X2 "vyhraje/prohraje" (BEZ remízy), 300 náhodných zápasů** | **-1,4 %** | **zdaleka nejlepší výsledek ze všech variant** |
| Přesný CELKOVÝ počet gólů (Poisson mód), 287 zápasů, bez reálných kurzů | 23,3 % trefeno | **hůř než naivní baseline (31,0 % - vždy tipovat nejčastější celkový počet v lize)** |

**Vyřazení remízy z 1X2 (sázka jen na "vyhraje/prohraje") dalo zdaleka nejlepší
výsledek (-1,4 % ROI, prakticky na nule)** oproti plnému 1X2 s remízou
(-13 až -15 %). Důvod: 25,9 % takových tiketů prohrálo kvůli remíze, ne kvůli
špatnému tipu vítěze - remíza je notoricky nejhůř odhadnutelný výsledek
fotbalového zápasu (nejnižší informační obsah v datech, o kterém model ví
nejmíň), takže "edge" na remízu byl z velké části šum, který kontaminoval
i zbytek portfolia. Když se remíza úplně vynechá (sází se jen když model vidí
hodnotu na vítěze/poraženého), výsledek je o řád lepší - i když pořád ne
ziskový, je to nejblíž k "fér hře" ze všech testovaných variant.

**Přesný celkový počet gólů byl bez reálných tržních kurzů testován jen jako
čistá přesnost predikce** (ne jako sázka s Kč) - a prohrál s naivním
baseline. Model kvůli Poissonovu módu u nízkých λ tipoval "2 góly" v 71 %
případů (203/287), zatímco ve skutečnosti bylo v tomhle vzorku nejčastější
"3 góly" (31 %). To je stejný mechanismus jako u "1:1" u přesného skóre
(viz výš) - jen aplikovaný na součet místo na dvojici čísel. Pro tenhle
konkrétní trh (celkový počet gólů jako jedno číslo) je nejlíp spolehnout
se na ligový průměr, ne na zápas-specifické λ.

## Automatizované sázení na tenis pomocí AI - proč to nejde postavit na tomhle modelu

Byl proveden explicitní test, jestli lze tenisový model (`forma+h2h+win rate`
nebo Elo) postavit do automatického sázecího bota. Potřeba k tomu byly
**skutečné historické kurzy** - ty v `tenis/*.csv` (Jeff Sackmann) chybí,
proto byl doplněn `scripts/fetch_tennis_odds.py`, který stahuje WTA kurzy
2021-2025 (11 730 zápasů) z mirroru `tennis-data.co.uk` na Hugging Face
(primární zdroj je za Cloudflare, který blokuje datacentra). Výsledky testu
jsou ve `scripts/tennis_value_backtest.py`.

**Zdrojová data**: jen WTA (ženská túra) - ekvivalentní veřejně dostupný
mirror pro ATP (mužskou túru) se nenašel. Kdo chce ověřit i ATP, musí
soubory z tennis-data.co.uk stáhnout ručně z běžné (ne datacentrové) sítě a
uložit jako `tenis/kurzy/atp_kurzy.csv` se stejnými sloupci.

### Výsledek (7 290 zápasů 2021-2025, po vyřazení zápasů s málo historií)

| Test | Výsledek |
|---|---|
| Kdo lépe tipuje vítěze - model, nebo trh | model 60,6 % (Elo 63,8 %) vs. **trh 66,0 %** |
| "Hodnotové" sázky (edge ≥ 4 % proti trhu), flat staking | **ROI -7,7 %** |
| Totéž s frakčním Kelly stakingem | **ROI -10,1 %** |
| Baseline "vždy favorit trhu" | ROI -5,6 % (= zhruba marže sázkovky) |
| Baseline "vždy tip modelu" | ROI -6,2 % |
| Totéž s Elo modelem místo forma+h2h | ROI -10,0 % (Elo+povrch -8,9 %) |

**Nejpřísnější test (`--pridana-hodnota`)**: namíchá se predikce
`p = (1-w)×trh + w×model` a měří se, jestli JAKÁKOLI váha modelu (i malá,
w=0,05) zlepší přesnost (log loss/Brier) oproti čistému trhu. Výsledek:
**žádná váha modelu trh nezlepšila** - u všech tří variant modelu (forma,
Elo, Elo+povrch) vycházelo nejlépe `w = 0` (čistý trh). To znamená, že model
nedrží VŮBEC ŽÁDNOU informaci, kterou by trh už neměl zaceněnou - nejde jen
o to, že je slabší, ale že je čistě podmnožinou toho, co umí trh.

**Rozpad podle segmentu (`--segmenty`)**: ROI vychází záporné úplně všude -
v každém pásmu výše kurzu (1,2 až 15,0), na všech třech površích, ve všech
kolech turnaje. Navíc platí klasický **"favourite-longshot bias"** (známý
jev ze sázkové literatury): čím vyšší kurz (outsider), tím horší ROI -
od -2,4 % u favoritů (kurz do 1,2) až po -33,1 % u extrémních outsiderů
(kurz nad 15). Model v testu hledal "hodnotu" i mezi outsidery, a právě
tahle část trhu byla nejhůř placená ze všech.

### Proč to tak je (vysvětlení k běžnému životu)

Sázková kancelář je jako bazar s cedulkami cen, které denně upravuje podle
toho, kdo kolik na co sází. Tisíce lidí (včetně profesionálů s vlastními
statistickými modely) už do té ceny propsali vše, co šlo z veřejných dat
vyčíst - formu, vzájemné zápasy, žebříček. Amatérský model počítaný ze
stejných veřejných dat proto nemůže objevit nic, co by cena ještě
neobsahovala - je to, jako kdybyste se snažili prodat bazarníkovi zpátky
informaci, kterou mu sám do ceny už dávno zapracoval. Jediný způsob, jak reálně porazit cenu, je
mít informaci RYCHLEJI nebo PŘESNĚJI než trh (např. čerstvá zpráva o zranění
minuty před zápasem) - ne přepočítávat tatáž veřejná čísla jinak.

### Závěr pro "chci stavět bota na AI sázení na tenis"

Žádná verze tohoto modelu (jednoduchý vzorec ani Elo) neprokázala sázkovou
výhodu - naopak prokázala její opak, konzistentně napříč segmenty i
modely. Stavět automatického sázecího bota na tomhle datovém základu by
znamenalo stavět stroj na systematické prohrávání peněz, ne na vydělávání.
To není limitace implementace (zkusily se dvě různé metodiky), je to
základní vlastnost trhu: ceny u velkých, likvidních sázkových trhů (ATP/WTA
jsou jedny z nejlikvidnějších sportovních trhů vůbec) jsou extrémně efektivní.

Pokud se o automatizaci přesto chce uživatel pokusit, poctivé další kroky
(žádný z nich není zaručený, jen méně beznadějný než tohle):
1. **Jiný typ informace, ne přesnější výpočet ze stejných dat** - živé
   zpravodajství o zraněních/odstoupeních rychleji než trh, in-play data
   (viz `game_flow.py --zvrat` pro živé přeskupení šancí uprostřed zápasu -
   tam ale jde o sázení BĚHEM zápasu na burze, ne o předzápasové kurzy).
2. **Mnohem užší niche trh** s menší likviditou (nižší turnaje, challengery),
   kde je méně profesionálních peněz a model/zpravodajství může mít reálně
   náskok - ale tam zase chybí kurzová i zápasová data v tomhle rozsahu.
3. Realisticky: brát takový projekt jako technické cvičení (datový pipeline,
   backtesting, řízení rizika) s papírovým obchodováním, ne jako zdroj
   příjmu - a smířit se s tím, že matematicky očekávaná hodnota je záporná,
   dokud se nenajde opravdu nová informační výhoda.

## Živé sledování zápasů in-play (`live_tennis_simulator.py` + `bet_evaluator.py`)

Nezávisle na backtestu výš (předzápasové kurzy, historická WTA data) existuje
druhý nástroj pro **právě probíhající** zápasy - sleduje živý průběh (sety,
gemy, body, kdo podává) přes Live Tennis API a kde vidí rozdíl proti živým
kurzům z Odds API, založí fiktivní tiket. Po backtestu výš **neočekávej, že
tenhle nástroj najde skutečnou výhodu** - je to stejná rodina modelu
(hold/break rate ze stejných veřejných dat) jen uvnitř zápasu místo před ním,
a výše popsaný nález ("žádná váha modelu nezlepší čistý trh") pravděpodobně
platí i tady. Hodnota nástroje je v **mechanice sledování a měření**
(průběžný log, oddělené vyhodnocení, poctivé ROI), ne v očekávaném zisku.

- `live_tennis_simulator.py watch` - při každém spuštění zapíše snímek stavu
  **každého** živého zápasu do `live_progress_log.jsonl`, porovná ho
  s minulým snímkem a hlásí události (brejk, uzavřený set, tiebreak,
  setbol/mečbol, posun pravděpodobnosti ≥10 p.b., změna favorita). Sází jen
  tam, kde má dost historických dat na oba hráče **a** zápas je v nabídce
  živých kurzů (menšina zápasů).
- `bet_evaluator.py` - dotáhne výsledky dohraných zápasů, připíše výhry/prohry
  do banky (start 1000 fiktivních mincí, vklad 2 % banky, strop expozice
  25 %) a vypíše ROI, vývoj banky a rozpad podle kurzových/edge pásem.

**Ověřený běh (1. 10. 2026):** ze 30 živých zápasů bylo 15-18 dvouher, cca
třetina bez dost historických dat, cca dvě třetiny bez živých kurzů v nabídce.
Vznikl jeden tiket (Gao vs. Udvardy @ 1,27, edge +8 %), po dohrání vyhrál,
banka 1000 → 1005. **Jeden tiket nedokazuje vůbec nic** - je to ověření, že
cyklus `watch → vyhodnot` funguje na skutečných datech, ne výsledek měření.
Smysluplný závěr vyžaduje řádově stovky tiketů; log je k tomu určený
(přírůstkový, mezi spuštěními bezstavový).

**Chyba ve čtení pole "games" z Live Tennis API (opravena):** poslední záznam
v `games[hráč]` není vždy rozehraný set - mezi sety (dokud nezačal první gem
nového setu) je to pořád skóre PRÁVĚ DOHRANÉHO setu, už započítané v poli
"sets". Když se bral bezmyšlenkovitě jako rozehraný, vznikly dva reálně
pozorované efekty: (1) stav "sety 1:1, gemy 6:4" se počítal, jako by někdo
vedl 6:4 v rozehraném 3. setu, což vyrábělo falešné hlášky "BREJK" hned na
začátku nového setu, a (2) model dostával nesmyslný stav gemů. Oprava:
rozehraný set se pozná podle počtu záznamů v poli (`games[0]` má víc prvků
než je dohraných setů) - pokud ne, gemy jsou 0:0 a zápas je "mezi sety".
Ověřeno na reálném běhu: po opravě hlásí skript smysluplné "MEČBOL"/"setbol"
a žádné falešné brejky při přechodu mezi sety.

### Změna cíle: "silný favorit" místo "hodnotová sázka" (1. 10. 2026)

Po poctivém backtestu výš (`tennis_value_backtest.py`) je jasné, že model
nemá žádnou výhodu nad trhem - "hodnotové" sázky (kde model vidí vyšší
pravděpodobnost než trh) jsou systematicky ztrátové. Uživatel upřesnil cíl:
nejde o to porazit trh, ale o to, **aby banka mezi jednotlivými tikety
spíš rostla než klesala** - tedy vysoký podíl vyhraných tiketů, ne edge.

To je jiná, dosažitelná metrika. Strategie `watch` se přepsala z
"edge mezi modelem a trhem" (`EDGE_MIN`/`EDGE_MAX`, odstraněno) na
"silný favorit potvrzený dvěma nezávislými zdroji":

| Parametr | Hodnota | Proč |
|---|---|---|
| `FAV_MODEL_MIN` | 0,75 | náš model musí hráče vidět jako jasného favorita |
| `FAV_MARKET_MIN` | 0,65 | a SKUTEČNÝ trh ho musí vidět jako favorita taky - nezávislé potvrzení, chrání proti chybě/zastaralosti v našem čtení živého skóre (viz oprava "games" výš) |
| `FAV_MAX_ODDS` | 1,60 | kurz nad tohle už není "bezpečný" favorit |

Důvod, proč tohle má šanci fungovat na úrovni "podíl výher", i když edge
nefunguje na úrovni "ROI": favorité v historických datech vyhrávají velmi
často (u kurzů do 1,2 to vychází na desítky procent nad 85% úspěšnost -
viz segmentový rozpad v `tennis_value_backtest.py --segmenty`). Vysoká
úspěšnost jednotlivých sázek je matematicky jiná vlastnost než kladné
očekávané ROI - **obojí spolu nesouvisí tak, jak by se mohlo zdát.**
Sázka s 90% šancí na výhru a kurzem 1,05 má v průměru i tak mírně zápornou
očekávanou hodnotu (bookmakerská marže je zaceněná i do kurzů na favority -
stejný segmentový rozpad ukázal ROI -2,4 % i v nejbezpečnějším pásmu).

**Co se tím získává:** vizuálně a prakticky banka "mezi tikety roste
častěji, než klesá" - to je to, co uživatel chtěl. **Co se tím NEzíská:**
žádná záruka, že banka v dlouhém běhu (stovky tiketů) skončí nad startovní
hodnotou - to zůstává matematicky nemožné zaručit u jakékoliv sázkové
strategie. `bet_evaluator.py` teď hlásí obojí zvlášť a výslovně odlišeně:
"podíl rostoucích tiketů" (hlavní sledovaná metrika) a ROI (poctivé peněžní
měřítko, které může být záporné i při vysokém podílu výher).

### Druhý trh: vítěz aktuálního gemu (`live_game_bet.py`, 1. 10. 2026)

Na výslovné přání uživatele ("sledovat průběh zápasu a sázet na to, kdo
vyhraje aktuální gem") vznikl oddělený nástroj pro mnohem vyšší frekvenci
sázek - vítěz PRÁVĚ ROZEHRANÉHO gemu, ne celého zápasu. Vlastní banka
(`live_game_bets_log.jsonl`), neslučuje se s `live_bets_log.jsonl`.

**Model (odvozený, ne nový odhad):** hold rate hráče (pravděpodobnost výhry
celého gemu na podání od stavu 0:0) se binárním hledáním převede na
pravděpodobnost výhry JEDNOHO BODU na podání `p`, která při standardním
skórování (0/15/30/40, výhoda od 40:40) dá přesně tenhle hold rate zpátky.
Z `p` a aktuálního bodového skóre se klasickou rekurzí (shodný mechanismus
jako `match_win_prob`, jen na úrovni bodů místo gemů) spočítá pravděpodobnost
výhry rozehraného gemu. Ověřeno výpočtem: hold 0,55/0,65/0,75/0,85 →
invertované `p` → zpětně dosazené do vzorce dá přesně původní hold rate
(na 4 desetinná místa). Krajní stavy dávají očekávané hodnoty (hold 0,55 při
40:0 → 94,9 %, při 0:40 → 7,6 %; hold 0,60 na výhodu podávajícího → 80,7 %,
na výhodu přijímajícího → 31,4 %).

**Tohle NENÍ nová informace** - je to stejné historické číslo jako všude
jinde v projektu (hold rate z `game_flow.py`/Match Charting), jen vyjádřené
na jemnější časové škále. Proto skript ani netvrdí nic o "hodnotě" - cíl je
stejný jako u `watch` (ať banka mezi tikety spíš roste), ne objev edge.

**Chybí nezávislé ověření:** na rozdíl od `watch` (kde model musí souhlasit
se SKUTEČNÝM trhem) pro vítěze jednotlivého gemu žádný reálný trh kurzů
neexistuje (Odds API nabízí nanejvýš zápas/set) - nejde tedy stejným
způsobem chránit proti chybě ve čtení živého skóre. Jediná ochrana je vyšší
práh (`GAME_FAV_MIN = 0,70` vs. 0,65 u trhu v `watch`) a úplné vynechání
tiebreaků (jiné skórování, model na ně neplatí).

**Vyhodnocení bez extra volání API:** `tick` vyhodnotí tikety z PŘEDCHOZÍHO
kola ze stejných dat, která stahuje pro hledání nových příležitostí (žádný
samostatný `resolve`). Pokud mezi dvěma koly proběhl víc než jeden gem
(= `tick` se nevolal dost často), tiket se označí `void` (zrušen, banka se
nemění) - princip "radši nehádat, než tvrdit nepodložené", stejný jako jinde
v projektu.

**Kvótové omezení:** gem trvá řádově minuty, takže `tick` potřebuje interval
1-3 minuty (ne 15-30 jako `watch`) - to vyčerpá denní limit (100 volání)
za pár hodin provozu. Nástroj je proto určený ke spouštění v časově
omezených smyčkách, ne natrvalo, a sdílí API klíč/kvótu s `watch` (pokud
běží souběžně přes `cron_tick.sh`), takže je potřeba kontrolovat `/usage`
před spuštěním.

### Systémové notifikace při změně banky (1. 10. 2026)

Na přání uživatele posílá `notify()` (v `live_tennis_simulator.py`, sdílená
přes `bet_evaluator.py` i `live_game_bet.py`) systémovou notifikaci PŘI
KAŽDÉM vyhodnocení tiketu (won/lost - ne při `void` ani při pouhém založení
tiketu, protože ani jedno z toho banku nemění). Prostředí běží v
NetHunter AI Operator PRoot (viz `~/nethunter_docs.md`), notifikace jde
přes jeho sjednocené CLI: `nh system notification -t <titulek> -c <text>`.

Implementace je defenzivní - `notify()` je obalená v `try/except` a nikdy
nespadne, i kdyby `nh` chybělo nebo selhalo (notifikace je bonus, ne
kritická funkce; skript musí fungovat i mimo NetHunter prostředí).

### Agresivní režim: rychlé znásobení s cílem a limitem (`agresivni-tick`, 1. 10. 2026)

Uživatel explicitně odmítl pomalé proporční sázení ("agent dává malé sázky,
jedna špatná sázka způsobí ztrátu celkového [zisku]") a chtěl: sázet **celou
banku** na tiket, cíl 6× znásobení (1000 → 6000), a po jeho dosažení zastavit
se při poklesu o 1000 z vrcholu.

**Poctivé varování, které jsem dal PŘED implementací:** sázet doslova celou
banku na jeden tiket s pravděpodobností výhry 70-85 % dává **15-30% šanci,
že HNED PRVNÍ sázka smaže banku na nulu bez možnosti zotavení** - to je
nejvyšší možná šance na okamžitý krach, přesný opak toho, o co uživatel
žádal ("nejvyšší šance na jednoduché stoupání"). Navrhl jsem kompromis
(50 % banky na tiket - jedna prohra banku jen zmenší, nezničí).

**Uživatel reagoval:** "risk je zisk, proto to existuje" - a trval na celé
bance. To je informované rozhodnutí po jasném vysvětlení rizika, ne
přehlédnutý detail - implementováno přesně takhle (`AGGR_STAKE_FRACTION = 1.0`).

**Druhá chyba, kterou jsem našel a opravil SÁM při návrhu (ne po chybě v
provozu):** kdyby se "ochranný režim" po dosažení cíle dál sázel celou
bankou, trailing stop "pokles o 1000 od vrcholu" by byl matematicky
nedosažitelný - jedna prohra po dosažení cíle by vynulovala rovnou celý
vrchol (např. 6000), ne jen 1000, takže stop by nikdy nestihl zareagovat.
Oprava: v ochranném režimu se sází nejvýš `AGGR_TRAILING_STOP` (1000), ne
celá banka - tím je garantováno, že jedna sázka nikdy nestrhne víc než
rezervu, na kterou je trailing stop nastavený. Ověřeno numericky (viz
scénář v testech `_replay_aggressive`): banka 6275 po jedné prohře s
vkladem capnutým na 1000 klesne na 5275 a `halted=True` s přesným důvodem.

**Třetí problém, který se ukázal až při prvním živém běhu:** výběr "nejvyšší
pravděpodobnost" (bezpečnější) vybral zápas na 97 % s kurzem 1,03 - takový
tiket banku sotva pohne, přímo odporuje cíli "rychle znásob". Oprava: v
růstové fázi se vybírá **nejnižší** pravděpodobnost, co ještě splní
bezpečnostní práh (`GAME_FAV_MIN = 0,70`) - to dá nejvyšší dostupný kurz v
rámci prahu, tedy nejrychlejší očekávaný růst při stejné bezpečnostní
hranici.

**Jak o tom mluvit s uživatelem:** tohle NENÍ "spíš poroste" nástroj jako
`watch` nebo normální `tick` (proporční 2% sázky). Realistický výsledek je
buď rychlý růst k 6000, nebo rychlá ztráta celé startovní banky - žádné
plynulé mezistádium, protože při frakci 1.0 nejde o postupné kolísání, ale
o posloupnost "vše, nebo nic" sázek. Matematicky: pravděpodobnost dosažení
cíle BEZ jediné prohry po cestě je součin pravděpodobností jednotlivých
sázek (při p≈0,70-0,85 a potřebě cca 6-10 výher v řadě na dosažení 6×,
podle konkrétních kurzů, to vychází řádově v jednotkách až nízkých
desítkách procent) - zbytek případů končí vynulováním. To je legitimní,
uživatelem zvolený kompromis (vysoká odměna, vysoké riziko), ne chyba
implementace.

---

## Trh-only favorit na antuce (5. 10. 2026) — model v této hře ŠKODÍ

Sonda `scripts/_probe_market_fav.py` srovnala na datech WTA 2021–2025
(7290 zápasů s reálnými kurzy) kandidátní strategie "favorit" hlavní
metrikou projektu = P(banka po 50 tiketech > start):

| Strategie | n | úspěšnost | ROI | P(růst) |
|---|---|---|---|---|
| ŽIVÁ: model≥0.75 & trh≥0.65, o≤1.60 | 177 | 72.9 % | −13.0 % | 3.6 % |
| trh-only favorit, o≤1.20 | 1133 | 85.9 % | −2.4 % | 36.2 % |
| trh-only favorit, o≤1.15 | 660 | 89.7 % | −0.8 % | 42.5 % |
| **trh-only favorit, o≤1.20, ANTUKA** | **244** | **88.9 %** | **+0.9 %** | **58.0 %** |
| trh-only favorit, o≤1.30, antuka | 460 | 83.7 % | −0.3 % | 49.6 % |
| ŽIVÁ + antuka | 37 | 78.4 % | −4.4 % | 27.1 % |

**Závěr:** dosavadní živá strategie (shoda modelu i trhu) má na datech
NEJHORŠÍ výsledek — sází do pásma kurz 1.20–1.60, kde je ROI nejhorší
(−4 až −5 %), a vybírá jiné zápasy než trh. Jediná kombinace s KLADNÝM
ROI je prostý TRŽNÍ favorit s kurzem ≤1.20 na ANTuce, a to kladná v OBOU
polovinách let zvlášť (+0.6 % / +1.0 %) → není to overfitting.

**Zavedeno:** strategie `market_clay_fav` (`cmd_market_clay_watch()` v
`live_tennis_simulator.py`), runner v `executor.py`, agent
`trh-only-antuka-favorit`. Sází PŘED zápasem na tržního favorita
(kurz ≤ `MARKET_FAV_MAX_ODDS`=1.20) na antuce, BEZ našeho modelu.
Odpovídá zjištění z metodiky: "s tímhle modelem nelze porazit trh" —
proto se tu model vůbec nepoužívá. Nezavádět combo sázky (0/40, ROI −100 %).
