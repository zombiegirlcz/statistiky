# Transcript notes – Arsenal vs Chelsea (without_skill)

Co jsem udělal pro zodpovězení dotazu "Jake ma Arsenal sance doma proti Chelsea?":

1. Prozkoumal jsem strukturu /root/statistiky (README.md) – zjistil jsem, že projekt obsahuje
   fotbalová zápasová data (football-data.co.uk) pro 22 evropských lig, sezóny 2021-22 až 2025-26,
   ve složce `fotbal/` jako CSV + MD (shodný obsah).
2. Ověřil jsem, že žádný soubor pro sezónu 2026-27 neexistuje (dataset končí sezónou 2025-26,
   která skončila 24.5.2026) – tedy žádná konkrétní nadcházející fixtura/los není v datech k
   dispozici; "dnešní datum" v prostředí je 2026-10-01, takže poslední kompletní sezóna už je
   uzavřená historie, ne "live" aktuální ročník.
3. Z pěti souborů `*_E0_Anglie_-_Premier_League.csv` (2021-22 až 2025-26) jsem skriptem (python3,
   csv.DictReader) vytáhl všechny vzájemné zápasy Arsenal–Chelsea (10 zápasů za 5 sezón) – skóre,
   poločas, střely, střely na branku, rohy, kurzy B365.
4. Spočítal jsem bilanci specificky pro zápasy na hřišti Arsenalu (domácí) – 4 výhry, 1 prohra
   z posledních 5 vzájemných domácích zápasů.
5. Z posledního kompletního ročníku (2025-26_E0) jsem spočítal celou tabulku Premier League
   (P/W/D/L/GF/GA/Pts) – Arsenal skončil 1. (85 b.), Chelsea 10. (52 b.).
6. Spočítal jsem domácí bilanci Arsenalu (19 zápasů: 15-2-2) a venkovní bilanci Chelsea
   (19 zápasů: 7-5-7) v sezóně 2025-26.
7. Podíval jsem se na kurzy sázkových kanceláří (B365H/D/A) u posledního vzájemného zápasu
   (1.3.2026, Arsenal 2:1 Chelsea doma) jako doplňkový tržní odhad šancí.
8. Sestavil jsem odpověď kombinující: H2H na Emirates, celkovou H2H bilanci, tabulkové
   umístění a domácí/venkovní formu, s jasnou výhradou, že jde o statistický odhad z historických
   dat (chybí sestavy, zranění, aktuální forma nové sezóny 2026-27, přesný termín zápasu).

Zdrojové soubory použité pro analýzu:
- /root/statistiky/README.md
- /root/statistiky/fotbal/2021-22_E0_Anglie_-_Premier_League.csv
- /root/statistiky/fotbal/2022-23_E0_Anglie_-_Premier_League.csv
- /root/statistiky/fotbal/2023-24_E0_Anglie_-_Premier_League.csv
- /root/statistiky/fotbal/2024-25_E0_Anglie_-_Premier_League.csv
- /root/statistiky/fotbal/2025-26_E0_Anglie_-_Premier_League.csv
