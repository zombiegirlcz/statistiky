# Transcript notes — Toronto Maple Leafs vs Edmonton Oilers (hokej)

1. Přečetl jsem `/root/statistiky/.claude/skills/match-probability/SKILL.md` (hlavní instrukce skillu).
2. Přečetl jsem `.claude/skills/match-probability/references/nazvy_tymu.md` (jak se týmy/hráči zapisují v datech) a zjistil obsah `scripts/` adresáře (`aggregate_stats.py`).
3. Rozpoznal sport (hokej, NHL) a dvojici (Toronto Maple Leafs → "Toronto", Edmonton Oilers → "Edmonton"); Toronto bylo v dotazu uvedeno první, takže ponecháno jako výchozí domácí tým (bez explicitní zmínky "doma" v dotazu jsem nepoužil `--home`, protože skript bere první zadaný tým jako domácí ve výchozím nastavení).
4. Spustil skript:
   ```
   python3 .claude/skills/match-probability/scripts/aggregate_stats.py hokej "Toronto" "Edmonton"
   ```
   Výstup (zkráceně):
   - TOR: 448 zápasů, win rate 56 %, doma 59 %, venku 53 %; forma posledních 15 zápasů: WLLLWWLWLLLLLLL (27 % win rate)
   - EDM: 491 zápasů, win rate 57 %, doma 61 %, venku 53 %; forma posledních 15 zápasů: WWWLLWLLWWLLLWL (47 % win rate)
   - Vzájemné zápasy: 10x, TOR vyhrál 7x, EDM 3x (poslední z nich 2026-02-03: TOR 5:2 EDM)
   - Návrh skriptu: TOR (domácí) 52 % / EDM (hosté) 48 %
5. Zkontroloval jsem čísla podle kroku 3 skillu (dostatek zápasů k dispozici — stovky zápasů i 10 vzájemných; žádné podezření na špatně dohledaný tým). Všiml jsem si rozporu mezi vzájemnou bilancí/domácí výhodou (favorizuje Toronto) a aktuální formou (favorizuje Edmonton) — ponechal jsem návrh skriptu beze změny (52/48), protože jde o mírný rozdíl a nešlo o chybu v datech, jen o smíšené signály; tento rozpor jsem zmínil v odpovědi jako stručné zdůvodnění.
6. Metodiku (`references/metodika.md`) jsem nečetl do hloubky, protože uživatel se neptal "proč" ani nežádal úpravu vah — jen jsem v odpovědi stručně zmínil klíčová čísla (formu, vzájemnou bilanci), jak skill doporučuje i bez explicitního dotazu "proč", pro kontext u vyrovnaného zápasu.
7. Odpověď formátována podle skillu: `Tým A XX % / Tým B YY %`, stručně, s jednou větou kontextu.
