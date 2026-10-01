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

## Živý in-play simulátor na skutečných zápasech (`live_tennis_simulator.py`)

Navazuje na sekci "Živé kurzy 'mezi gemy/sety'" výš, ale s **jedním zásadním
rozdílem: žádný simulovaný trh**. Po té, co se ukázalo, že "trh = zpožděná
kopie modelu" je tautologie (viz tamtéž), byl nástroj postavený znovu na
skutečných datech z obou stran:

| Složka | Zdroj | Granularita |
|---|---|---|
| Průběh zápasu | Live Tennis API (livetennisapi.com) | sety + **gemy + body**, kdo podává |
| Kurzy | The Odds API (`h2h`, odvigované) | skutečné živé kurzy bookmakerů |
| Schopnosti hráčů | `tenis/prubeh/` (Match Charting) přes `game_flow.py` | hold/break rate |

**Proč Live Tennis API a ne The Odds API `/scores`:** `/scores` vrací u tenisu
jen skóre **po setech**, ne průběh uvnitř setu. Model, který má ohodnocovat
situaci "mezi gemy", tak od něj dostával stav zastaralý až o celý set, což
vyrábělo falešné "obrovské edge". Live Tennis API má ve free tieru (30 volání/
min, 100/den) skóre na úrovni gemu i bodu.

### Formát dat Live Tennis API (pozor, snadno se přečte špatně)

Pole `games` je `[gemy_hráče_1_po_setech, gemy_hráče_2_po_setech]` - tedy
indexované **nejdřív hráčem, pak setem**. Není to `[skóre_1._setu,
skóre_2._setu]`. Aktuální rozehraný set je `(games[0][-1], games[1][-1])`.

Ověřeno na dokončeném zápase Udvardy–Gao (id 196994): `games=[[2,3],[6,6]]`,
`sets=[0,2]` → 1. set 2:6, 2. set 3:6, Gao 2:0 na sety. Souhlasí.

První implementace tohle četla jako `games[-1][0], games[-1][1]`, což jednak
padalo na `IndexError` u zápasů s jediným odehraným setem, jednak u ostatních
tiše vracelo nesmyslné skóre - a na jeho základě vznikla **chybná analýza
zápasu Bublik–Mensik (1. 10. 2026)**, kde `games=[[4,1],[6,0]]` bylo přečteno
jako "Mensik vede 6:0 ve 2. setu, skoro mečbol", zatímco správné čtení je
"Mensik vyhrál 1. set 6:4, Bublik vede ve 2. setu 1:0". Zapsáno jako varování:
u každého nového API vždy ověř strukturu pole proti zápasu se **známým**
výsledkem, ne proti dojmu, že čísla vypadají rozumně.

Vítěz dokončeného zápasu je v **top-level** poli `winner` (číslo `1` nebo `2`),
`outcome` je řetězec `"completed"`, ne objekt. (Výpis dokončených zápasů
`status=completed` je placený, detail konkrétního zápasu podle ID je zdarma.)

### Podlaha a strop pravděpodobnosti (`MIN_PROB` / `MAX_PROB`)

Čistě kombinatorický model považuje stav typu 6:0 6:5 za jistotu (p → 1).
Skutečný zápas ale může kdykoli skončit skrečí, zraněním nebo diskvalifikací -
a to i u vedoucího hráče. Naměřeno v `tenis/atp_matches_202*.csv` +
`wta_matches_202*.csv`: ze **30 885 zápasů končí 3,59 % zkratkou**
(`RET` / `W/O` / `DEF` ve sloupci `score`).

Model proto každou výslednou pravděpodobnost ořezává do intervalu
**⟨0,02; 0,98⟩** - zhruba polovina naměřené míry skreče jako rezerva na "může
se stát cokoliv". Je to hrubý odhad, ale podložený daty, ne zvolený od oka.
Praktický dopad: skript nikdy nepostaví tiket s argumentem "je to jisté" a
kurz nad ~50 se nikdy netváří jako hodnota.

### Ochrany proti falešné hodnotě

| Parametr | Hodnota | Proti čemu chrání |
|---|---|---|
| `MIN_HOLD_N` | 20 podávacích gemů na hráče | šum u málo zaznamenaných hráčů (stejný mechanismus jako "Almere City problém" u fotbalu) |
| `EDGE_MIN` | 0,06 | obchodování na šumu |
| `EDGE_MAX` | 0,25 | **rozdíl nad 25 p. b. je skoro vždy zastaralé/špatně přečtené skóre, ne nalezená hodnota** |
| `MIN_PROB`/`MAX_PROB` | 0,02 / 0,98 | tvrzení "100 % jisté" (viz výš) |

### Ověřený běh (1. 10. 2026)

Z 34 živých zápasů: 14 mělo dost historických dat pro oba hráče, 9 nebylo
v nabídce Odds API, 4 vypadla na `MIN_HOLD_N`. Vznikl **jeden** tiket
(Gao proti Udvardy @ 1,27 při stavu 0:1 na sety a 3:5 na gemy, edge +8 %),
který po dohrání zápasu vyhrál → fiktivní banka 1000 → 1005 mincí.

**Jeden tiket nedokazuje vůbec nic** - je to ověření, že celý cyklus
`scan → resolve` funguje na skutečných datech, ne výsledek měření. Smysluplný
závěr o tom, jestli model má nad trhem výhodu, vyžaduje řádově stovky tiketů
sbíraných v čase; log `live_bets_log.jsonl` je k tomu určený (je přírůstkový
a mezi spuštěními bezstavový). Očekávání na základě fotbalové části projektu
je spíš "žádná výhoda" - kurzy obsahují informace, které model nevidí.

### Sledování průběhu a oddělené vyhodnocování (`watch` + `bet_evaluator.py`)

Nástroj byl rozdělený na dvě role, protože jde o dvě různě časované činnosti:

- `live_tennis_simulator.py watch` - při každém spuštění zapíše snímek stavu
  **každého** živého zápasu (sety, gemy, body, kdo podává, naše pravděpodobnost)
  do `live_progress_log.jsonl` a porovná ho s minulým snímkem. Hlášené události:
  brejk, uzavřený set, tiebreak, setbol/mečbol, posun pravděpodobnosti o ≥10 p.b.
  a změna favorita. Průběh se sleduje i u zápasů, na které se nedá sázet (chybí
  historická data nebo kurzy) - sledování a sázení jsou záměrně oddělené.
- `bet_evaluator.py` - dotáhne výsledky dohraných zápasů, připíše výhry/prohry
  do banky a vypíše ROI, vývoj banky a rozpad podle kurzových a edge pásem.

**Řízení rozpočtu** (1000 fiktivních mincí): vklad je 2 % aktuální banky
(minimálně 10), strop souběžné expozice 25 % banky, max. jeden tiket na zápas.
Proporční vklad znamená, že při klesající bance se sázky samy zmenšují - banka
tak nemůže spadnout na nulu skokem, jen se asymptoticky zmenšuje. To není
ochrana proti ztrátě, jen proti rychlému bankrotu z jedné série proher.

**Čím se měří výsledek:** jediné vypovídající číslo je **ROI**, ne konečná banka
a ne úspěšnost. Sázky na favority s kurzem 1,2 mohou mít 85 % úspěšnost a přitom
být ztrátové. Vyhodnocovač proto u každého výpisu připomíná, že pod ~100
vyhodnocenými tikety je jakýkoli výsledek šum.

**Stav ověřeného běhu (1. 10. 2026):** ze 30 živých zápasů bylo 15 dvouher,
u 5 z nich chyběla historická data na aspoň jednoho hráče a 9 nebylo v nabídce
Odds API. Oba režimy i celý cyklus `watch → vyhodnot` běží na skutečných datech;
naměřený vzorek je zatím **1 tiket**, což neznamená nic než že mechanika funguje.
