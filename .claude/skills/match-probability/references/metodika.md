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
