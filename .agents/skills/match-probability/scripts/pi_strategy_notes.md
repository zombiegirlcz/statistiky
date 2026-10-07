# Deník pi-mozku (strategie)

Sem pi zapisuje každý běh: co zkoušel, výsledek backtestu (čísla),
co změnil (nebo proč nic), co zkusit příště. Append, nepřepisovat.

<!-- první běh zapíše níže -->

## 2026-10-05 — Nalezena lepší strategie: trh-only favorit na ANTuce

**Co jsem zkoumal:** přečetl jsem staré sondy `_probe_fav_segments.py`,
`_probe_fav_oos.py` a napsal nové:
- `scripts/_probe_fav_maxodds.py` — jak přesně dopadá ŽIVÁ strategie
  (model≥0.75 & trh≥0.65 & kurz≤1.60) na historických datech + citlivost
  na max kurz a povrch.
- `scripts/_probe_market_fav.py` — srovnání 7 kandidátních strategií
  „favorit" s hlavní metrikou projektu = P(banka po 50 tiketech > start),
  na celku i na dvou polovinách let (OOS).

**Výsledky backtestu (WTA 2021–2025, reálné kurzy, 7290 zápasů):**

| Strategie | n | úspěšnost | ROI | P(růst) |
|---|---|---|---|---|
| A) ŽIVÁ: model&trh, o≤1.60 | 177 | 72.9 % | **−13.0 %** | **3.6 %** |
| B) trh-only favorit, o≤1.20 | 1133 | 85.9 % | −2.4 % | 36.2 % |
| C) trh-only favorit, o≤1.15 | 660 | 89.7 % | −0.8 % | 42.5 % |
| **D) trh-only favorit, o≤1.20, ANTUKA** | **244** | **88.9 %** | **+0.9 %** | **58.0 %** |
| E) trh-only favorit, o≤1.30, antuka | 460 | 83.7 % | −0.3 % | 49.6 % |
| F) ŽIVÁ + antuka | 37 | 78.4 % | −4.4 % | 27.1 % |

**Klíčové zjištění: náš model v této hře ŠKODÍ.** Živá podmínka (model i
trh se musí shodnout) má na datech nejhorší výsledek ze všech — ROI −13 %
a P(růst) 3.6 %. Náš model totiž sází do pásma kurz 1.20–1.60, kde je ROI
nejhorší (−4 až −5 %), a navíc vybírá jiné zápasy než trh. Prostý tržní
favorit s kurzem ≤1.20 na antuce má jediné KLADNÉ ROI, a to na OBOU
polovinách let zvlášť (+0.6 % / +1.0 % → není to overfitting).

**Co jsem změnil:**
- `live_tennis_simulator.py`: nová funkce `cmd_market_clay_watch()`
  (trh-only favorit na antuce, kurz≤1.20, sází PŘED zápasem, bez modelu) +
  `_is_clay()` a konstanty `MARKET_FAV_MAX_ODDS`, `CLAY_NAME_HINTS`.
- `agents.py`: nová strategie `market_clay_fav` (defaulty + popisky pro TUI).
- `executor.py`: runner `_run_market_clay_fav` v `_RUNNERY`.
- Založen agent `trh-only-antuka-favorit` (1000 mincí z hlavní banky)
  přes `agents.py` — `agents.json` jsem needitoval ručně.
- End-to-end ověřeno: `executor.py --only trh-only-antuka-favorit` proběhne
  bez chyby. Dnes našel 5 antukových zápasů, ale ani jeden neměl SX.bet trh
  → 0 tiketů (běžné, sbírá se postupně).

**Stávající agenty jsem nechal být** (nezastavoval, needitoval) — nová
strategie běží vedle nich jako experiment.

**Co zkusit příště:**
1. Až se nasbírá ~50+ tiketů, porovnat `trh-only-antuka-favorit.jsonl`
   proti ostatním agentům (P(růst) na živých datech vs. backtest).
2. Zvážit rozšíření na **2. kolo** turnajů (v OOS sondě mělo taky kladné
   ROI) — možná kombinace antuka NEBO 2. kolo.
3. Zvážit, jestli má smysl zkusit kurz≤1.15 (vyšší P(růst)=42 %, ale bez
   antuky; na antuce bylo ≤1.20 lepší).
4. Prověřit, zda antukový filtr (`_is_clay`) správně chytá i turnaje bez
   slova „clay" v názvu (používá i `surface` z API).

## 2026-10-07 — 2. KOLO je silnější filtr než antuka (a proč to zatím NEJDE nasadit)

**Co jsem zkoumal.** Navázal jsem na nález z 2026-10-06 (2. kolo vypadalo
lépe než antuka). Napsal jsem dvě nové sondy:
- `scripts/_probe_round2_oos.py` — robustnost 2. kola: rok po roku, OOS split,
  citlivost na kurzový cap, 2nd x povrch, koncentrace podle turnaje.
- `scripts/_probe_round2_signif.py` — je to statisticky reálné, nebo jen
  nejlepší z mnoha testovaných řezů? (bootstrap CI, permutační p-hodnota,
  kontrola mnohonásobného srovnání.)

**Výsledky (WTA 2021–2025, reálné kurzy, trh-only favorit):**

| řez | n | úspěšnost | ROI | P(růst50) |
|---|---|---|---|---|
| 2nd round, cap≤1.20 | 619 | 89.3 % | +1.3 % | 61 % |
| **2nd round, cap≤1.15** | **370** | **93.8 %** | **+3.6 %** | **80 %** |
| 1st round, cap≤1.20 | 870 | 87.5 % | −1.1 % | 43 % |
| 3rd/4th, cap≤1.20 | 229 | 80.8 % | −8.4 % | 8 % |
| celek (pool cap≤1.20) | 1908 | — | −1.56 % | — |

2. kolo drží: rok po roku +2.9/−0.1/+2.7/−2.6/+2.8 % (4 z 5 kladné),
OOS prvni +1.6 % / druha +1.1 %, a na OBOU površích (clay +2.2 %,
ne-clay +1.0 %, hard +0.0 %, grass +6.2 %). → **řidič je KOLO, ne antuka.**

**Statistická významnost (cap≤1.15):** ROI +3.56 %, bootstrap 95% CI
**[+0.68 %, +6.13 %]** (celé nad nulou), permutační p = **0.003**.
Kontrola mnohonásobného srovnání: jen 3.3 % náhodných řezů stejné velikosti
má ROI ≥ pozorované. → Není to artefakt mnoha testů.

**Co jsem změnil: NIC (záměrně).** Přestože strategie v backtestu poráží
baseline, **NEŠLA by nasadit živě**: historický zdroj (tennis-data.co.uk) má
sekvenční kola („2nd Round"), ale živé Live Tennis API vrací **zlomek pavouka**
(`round_code` = R16 / R32 / R64…), ne pořadí kola. „R16" je 2. kolo pro
32-pavouk, ale 4. kolo pro 128-pavouk (Slam). Abych to namapoval, potřebuju
velikost pavouka — tu API neposkytuje (`/tournaments/{id}` vrací tier, ale
žádný draw size; 22/100 zápasů má navíc `tier=None`). Zaregistrovat strategii
s odhadnutým/špatným mapováním by znamenalo sázet na špatné zápasy a zkazit
papírové výsledky — proto jsem agents.json needitoval.

**Co zkusit příště (priorita 1).** Sestavit tabulku `tier → velikost pavouka`
(grand_slam=128, wta_1000≈56, wta_500≈32–56, wta_250=32, wta_125=32) a
z `round_code` dopočítat pořadí kola (pořadí = log2(pavouk) − log2(round_code)).
Pak namapovat na „2nd round" a **ověřit na živých datech**, že výběr sedí,
než strategii zaregistruju. Alternativa: odvodit velikost pavouka z množiny
`round_code` viditelných v turnaji.

**Co zkusit příště (priorita 2).** Prověřit mechanismus: je 2. kolo bezpečnější
proto, že tam vstupují nasazené hráčky s bye (čerstvé + silnější)? Pokud ano,
dalo by se to aproximovat živě i bez přesného kola (např. favorit s bye).

**Co zkusit příště (priorita 3).** Zvážit, zda stávající `market_clay_fav`
(ROI +0.9 %, slabé OOS) nenahradit touto strategií — ale až po vyřešení
mapování kola.
