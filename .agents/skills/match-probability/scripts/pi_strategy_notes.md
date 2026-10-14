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

## 2026-10-12 — Registrován GS-2kolo agent + nezávislé ověření "2. kolo" efektu

**Co jsem zkoumal.** Přečetl jsem deník (poslední běhy: 2026-10-05 antuka,
2026-10-07 2. kolo). Zjistil jsem NEDOKONČENÝ kus práce: strategie
`gs_round2_fav` (GS 2. kolo = R64, trh-only favorit, kurz<=1.15) MÁ
hotový kód (`cmd_gs_round2_watch` v `live_tennis_simulator.py`, runner
`_run_gs_round2_fav` v `executor.py`, defaulty v `agents.py`), MÁ zelený
backtest (`_probe_gs_round2.py`: n=102, ROI +5.95 %, P(50)=95 %,
CI[+1.44,+9.76], p=0.010, OOS 1.pol +9.84 % / 2.pol +3.12 %), ale
**NEBYL ZAREGISTROVANÝ žádný agent** — tedy se nikdy nespouštěl.

Navíc jsem napsal dvě nové sondy, které ověřují starší nález "2. kolo" na
JINÉ datové základně (přímo z `tenis/kurzy/wta_kurzy.csv`, kde je sloupec
`Round` — bez Sackmann joinu a fuzzy matchingu jmen):

- `scripts/_probe_round_direct.py` — trh-only favorit z kurzy CSV podle
  poradi kola (1./2./3./4.) x cap (1.10/1.15/1.20).
- `scripts/_probe_round2_clay_oos.py` — OOS, rozpad podle turnaju,
  rank-gap kontrola, citlivost na cap, permutacni kontrola.

**Výsledky (WTA 2021–2025, kurzy CSV, 11729 zápasů, FLAT vklad 100):**

Replikace „2. kolo" (bez Sackmann joinu!):
| segment | n | úspěšnost | ROI | P50 | CI | p |
|---|---|---|---|---|---|---|
| cap<=1.15 ordinal==1 | 715 | 91.5 % | −0.27 % | 51.9 % | [−2.7,+2.0] | 0.678 |
| **cap<=1.15 ordinal==2** | **462** | **93.9 %** | **+2.69 %** | **80.7 %** | **[+0.1,+5.1]** | **0.033** |
| cap<=1.15 ordinal==3 | 129 | 88.4 % | −3.40 % | 27.1 % | [−9.9,+2.3] | 0.904 |
| cap<=1.15 ordinal==4 | 31 | 83.9 % | −9.87 % | 2.9 % | [−24.4,+3.7] | 0.964 |

→ Potvrzeno nezávisle: řidič je KOLO 2 (ne kolo 1/3/4). Silnější než
stará sonda (n=462 vs 370), ale slabší ROI než starý nález (+2.69 %
vs +3.6 %) — stará sonda použila Sackmann `draw_size` pro přesné
pořadí kola; CSV `Round` label je ekvivalentní, drobný rozdíl dělá
jiný pool zápasů (stará sonda vyžadovala join, vyřadila ~nespojené).

Rozpad podle povrchu (ordinal==2, cap<=1.15):
| povrch | n | úspěšnost | ROI | P50 | CI | p |
|---|---|---|---|---|---|---|
| **clay** | **125** | **96.8 %** | **+6.00 %** | **97.3 %** | **[+2.3,+9.1]** | **0.009** |
| hard | 280 | 92.5 % | +0.98 % | 63.1 % | [−2.5,+4.2] | 0.351 |
| grass | 57 | 94.7 % | +3.84 % | 87.4 % | [−3.3,+9.5] | 0.184 |

Antuka se 2. kolem vypadá silně (ROI +6 %, P50 97 %), ale **n=125 je
malé** a je to jeden z mnoha testovaných segmentů → nutná robustnost.

Robustnost segmentu {ordinal==2, clay, cap<=1.15}:
- OOS: 1.pol (<2023) n=40, +9.85 % CI[+8.62,+11.05]; 2.pol (>=2023)
  n=85, +4.19 % CI[−1.35,+8.52]. Obě kladné, ale druhá má CI přes nulu.
- Rok po roku: 2021 +10.8 %, 2022 +8.8 %, 2023 −6.3 %, 2024 +9.4 %,
  2025 +9.8 %. 4 z 5 let kladné, jeden propadák (2023).
- Rozpad podle turnajů: 20 různých antukových turnajů; **NENÍ to jen
  Roland Garros** (RG n=32 ROI +8.4 %, ale i Madrid +10.2 %, Charleston
  +11.0 %, Stuttgart +8.3 %, Palermo +9.5 % atd.). Dva turnaje záporné
  (Lausanne −16 %, Poland −20 %, malé n).
- Rank-gap kontrola (klíčové!): stejný filtr fav_rank<=20 & und_rank>=50
  na antuce, ale **MIMO 2. kolo**, dává ROI **−1.86 %** (n=90).
  → „2. kolo" NENÍ jen jinak zapsaný rank-gap; má vlastní informaci.
- Citlivost na cap: 1.05 +3.2 %, 1.10 +2.5 %, **1.15 +6.0 %**,
  1.20 +1.9 %, 1.25 +2.1 %, 1.30 +0.2 %. Všechny kladné (dobré), ale
  vrchol na 1.15 je nejspíš šum (malá n, široké CI).
- Permutační kontrola: z 5000 náhodných antukových segmentů velikosti
  n=125 jich 4.86 % dosáhne ROI >= +6 %. → Není to super-vzácné, ale
  ani banální (p ~ 0.05 v rámci antukového poolu).

**Co jsem změnil.**
1. **Zaregistroval agenta `gs-2kolo-favorit`** (strategie `gs_round2_fav`,
   1000 mincí z hlavní banky) přes `cli.py agent create`. Toto je jediná
   strategie s živě-OVĚŘENÝM zdrojem signálu (GS má vždy pavouk 128 →
   R64 = přesně 2. kolo, žádný odhad velikosti pavouka není potřeba).
   `agents.json` jsem needitoval ručně.
2. **NEZAREGISTROVAL jsem** strategii „2. kolo + antuka" (i když backtest
   vypadá ještě líp než GS 2. kolo), protože pořadí kola u NE-grandslamů
   nejde živě odvodit (Live API vrací jen round_code R16/R32…, ne
   velikost pavouka — potvrzeno starými sondami 2026-10-07). Sázet na
   špatně odhadnuté kolo = zkazit papírové výsledky. Zapsáno jako nález,
   ne nasazeno.
3. Ověřil end-to-end: `BOOKMAKER=sxbet_sim python3 executor.py --only
   gs-2kolo-favorit` proběhne bez chyby. Dnes 0 tiketů (žádný GS se
   nehraje, 81 zápasů mimo GS) — běžné, sbírá se postupně.

**Proč GS-2kolo a ne „2. kolo + antuka".** GS 2. kolo má:
- živě-OVĚŘITELNÝ zdroj (R64 + tier=grand_slam stačí),
- silnější statistiku (n=102, CI celé nad nulou, perm p=0.010),
- test OOS přes poloviny let.
„2. kolo + antuka" má sice hezčí ROI (+6 %), ale n=125, CI dolní mez
+2.3 % je blízko nuly, perm p v rámci antuky 0.049 (ne 0.01) a vrchol
na capu 1.15 vypadá jako náhoda. Radši nasadit konzervativnější.

**Co zkusit příště.**
1. Sledovat `gs-2kolo-favorit.jsonl` — příští grandslam (Australian Open,
   leden 2026) dá první živá data. Cíl: 30+ tiketů a porovnat s backtestem.
2. Prověřit, jestli se GS-2kolo efekt liší podle grandslamu (RG/WIM/USO/
   AO); backtestováno jen na WTA, ale strategie sází i muže.
3. Zvážit, jestli rozšířit `gs_round2_fav` o trh-only favorita na cap
   <=1.20 (více tiketů, ROI +3.5 %) nebo zůstat na <=1.15 (méně, ale
   lepší P50). Zatím default 1.15.
4. Mapování round_code na pořadí kola pro NE-grandslamy: zkusit odvodit
   velikost pavouka z MNOŽINY round_code viditelných v turnaji
   (stará priorita 1 z 2026-10-07 — dosud nevyřešeno).
5. Zkontrolovat, jestli nový agent `gs-2kolo-favorit` nekoliduje s
   `market_clay_fav` (oba trh-only) — mohou sázet na stejný zápas, ale
   každý má vlastní banku/log, takže to není problém pro měření.
