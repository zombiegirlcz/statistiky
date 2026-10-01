# Transcript notes - Arsenal vs Chelsea

## Steps taken

1. Read the skill file: `.claude/skills/match-probability/SKILL.md` in full (it's short, no need to open references/ or scripts/ for inspection beyond running the script as instructed).
2. Identified sport = fotbal (football), teams = Arsenal, Chelsea. Query implies Arsenal plays at home ("doma proti Chelsea"), which matches the script's default (first team = home), so no `--home` flag was needed.
3. Ran the mandated aggregation script, no manual grep/reading of CSVs:

   ```bash
   python3 .claude/skills/match-probability/scripts/aggregate_stats.py fotbal "Arsenal" "Chelsea"
   ```

   Output (full):
   ```
   === FOTBAL: Arsenal vs Chelsea ===
   Domaci tym pro tento vypocet: Arsenal (predpoklad podle poradi zadani, lze zmenit --home)

   [Arsenal] celkem 190 zapasu v datech | W122-D35-L33 (win rate 64%)
     prumer branek: 2.00 vstrelenych / 0.95 obdrzenych | prumer rohu: 6.1
     doma win rate: 72%, venku win rate: 57%
     posledni forma (10 zapasu, nejnovejsi vpravo): WLWWWWDWWL (win rate 70%)

   [Chelsea] celkem 190 zapasu v datech | W84-D50-L56 (win rate 44%)
     prumer branek: 1.65 vstrelenych / 1.25 obdrzenych | prumer rohu: 5.9
     doma win rate: 47%, venku win rate: 41%
     posledni forma (10 zapasu, nejnovejsi vpravo): WLWLLLWDDW (win rate 40%)

   Vzajemne zapasy v datech: 10x | Arsenal vyhral 6x, remiza 3x, Chelsea vyhral 1x
     2023-24 23/04/2024: Arsenal 5:0 Chelsea
     2024-25 10/11/2024: Chelsea 1:1 Arsenal
     2024-25 16/03/2025: Arsenal 1:0 Chelsea
     2025-26 01/03/2026: Arsenal 2:1 Chelsea
     2025-26 30/11/2025: Chelsea 1:1 Arsenal
   Prumerna remizovost v relevantnich souteznich (zdroj pro draw %): 24%

   === ODHAD (navrh, Claude muze dle SKILL.md jemne doladit) ===
   Arsenal (domaci) 55% / Remiza 19% / Chelsea (hoste) 26%
   ```

4. Sanity-checked the numbers per SKILL.md step 3: sample size (190 matches each) is solid, Arsenal's edge is consistent across every signal shown (overall win rate, home win rate 72% vs Chelsea's away win rate 41%, recent form 70% vs 40%, and head-to-head 6-3-1 in Arsenal's favor over the last 10 meetings). No sign the script matched the wrong club (names unambiguous, no CHYBA printed). Did not see a need to adjust the script's suggested percentages or consult `references/metodika.md` since nothing looked out of proportion and the user didn't ask "proč".
5. Did not need `references/nazvy_tymu.md` (football club names, no ambiguity, script resolved both directly).
6. Wrote final answer in Czech, in the short format mandated by SKILL.md section 4 (bare percentages, no essay): `Arsenal 55 % / Remíza 19 % / Chelsea 26 %`, with one short line of justification since this is a natural "sance" question (not purely bare numbers, but kept minimal per skill's instruction to stay brief unless asked "proč").

## Files produced
- `answer.md` - final user-facing answer (Czech)
- `transcript_notes.md` - this file
