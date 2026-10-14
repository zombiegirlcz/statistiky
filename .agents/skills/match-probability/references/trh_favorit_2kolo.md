# Trh-only favorit: 2. kolo turnaje (nález 2026-10-07)

## Tvrzení
Mezi trh-only favority (kurz ≤ 1.20) na WTA 2021–2025 je **2. kolo turnaje**
statisticky významně lepší segment než 1. kolo i než pozdní kola.
Efekt je silnější než dřívější nález „antuka" a drží na obou površích.

## Čísla (FLAT 100, start 10 000, bootstrap P(50) seed 7)

| řez | n | úspěšnost | ROI | P(růst50) |
|---|---|---|---|---|
| 2nd round, cap ≤ 1.20 | 619 | 89.3 % | +1.3 % | 61 % |
| 2nd round, cap ≤ 1.15 | 370 | 93.8 % | +3.6 % | 80 % |
| 2nd round, cap ≤ 1.10 | 180 | 93.3 % | +0.5 % | 57 % |
| 1st round, cap ≤ 1.20 | 870 | 87.5 % | −1.1 % | 43 % |
| 3rd/4th, cap ≤ 1.20 | 229 | 80.8 % | −8.4 % | 8 % |
| QF, cap ≤ 1.20 | 112 | 83.0 % | −5.3 % | 20 % |
| pool cap ≤ 1.20 (celek) | 1908 | — | −1.56 % | — |

Robustnost: 4 z 5 let kladné; OOS prvni +1.6 % / druhá +1.1 %;
clay +2.2 %, ne-clay +1.0 %.

## Statistická významnost (cap ≤ 1.15)
- bootstrap 95% CI ROI: **[+0.68 %, +6.13 %]** (celé nad nulou)
- permutační p-hodnota: **0.003**
- kontrola mnohonásobného srovnání: 3.3 % náhodných řezů stejné velikosti
  má ROI ≥ pozorované (tj. není to artefakt mnoha testů)

## PROČ TO ZATÍM NENÍ NASAZENÉ (blokér)
Historický zdroj kurzů (`tenis/kurzy/wta_kurzy.csv`) má **sekvenční** kola
(„1st Round", „2nd Round"). Živé Live Tennis API ale vrací **zlomek pavouka**:
`round` = „1/8-finals", `round_code` = `R16`/`R32`/`R64`.

Mapování `round_code` → pořadí kola vyžaduje **velikost pavouka**:
- 32-pavouk: 2. kolo = R16
- 64-pavouk: 2. kolo = R32
- 128-pavouk (Slam): 2. kolo = R64

`/tournaments/{id}` vrací `tier`, ale **žádný draw size**; navíc `tier` je
u části zápasů `None`. Bez velikosti pavouka nelze „2. kolo" spolehlivě určit.

## Plán nasazení (příští běh)
1. Tabulka `tier → velikost pavouka` (grand_slam=128, wta_1000≈56,
   wta_500≈32–56, wta_250=32, wta_125=32).
2. pořadí kola = log2(draw) − log2(round_code).
3. Namapovat na „2. kolo" a **ověřit na živých datech**, že výběr sedí,
   teprve pak zaregistrovat novou strategii.
4. Alternativa: odvodit velikost pavouka z množiny `round_code` v turnaji.

## Mechanismus (hypotéza k ověření)
2. kolo může být bezpečnější proto, že tam vstupují nasazené hráčky s bye
(čerstvé + silnější). Pokud to platí, šlo by to aproximovat živě i bez
přesného kola.

## Zdroje
- `scripts/_probe_round2_oos.py` — robustnost a citlivost
- `scripts/_probe_round2_signif.py` — významnost a mnohonásobné srovnání
- `scripts/_probe_round_market.py` — první nález (kolo x povrch)
