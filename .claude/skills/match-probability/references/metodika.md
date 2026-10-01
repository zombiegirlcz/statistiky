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
