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
