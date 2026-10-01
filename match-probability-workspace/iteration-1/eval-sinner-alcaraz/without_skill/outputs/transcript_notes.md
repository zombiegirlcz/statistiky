# Transcript notes – Sinner vs Alcaraz

Co jsem udělal pro zodpovězení otázky "Co myslis, kdo vyhraje zapas Sinner vs Alcaraz?":

1. Prozkoumal jsem strukturu /root/statistiky (README.md) – zjistil, že `tenis/` obsahuje
   ATP/WTA zápasová data 2021–2026 (CSV + MD, zdroj Jeff Sackman tennis archive) a roční
   přehledy z Wikipedie.
2. Pomocí awk jsem z `atp_matches_2021.csv` až `atp_matches_2026.csv` vytáhl všechny
   vzájemné zápasy Sinner vs Alcaraz (sloupce winner_name/loser_name, surface, round, score).
   - Celková bilance v datasetu: Alcaraz 10 : 7 Sinner.
   - Rozpad podle povrchu: Clay 3:2 pro Alcaraze, Hard 7:3 pro Alcaraze, Grass 2:0 pro Sinnera.
   - Posledních 6 vzájemných zápasů chronologicky: French Open 2025 F (Alcaraz),
     Wimbledon 2025 F (Sinner), Cincinnati 2025 F (Alcaraz, skreč), US Open 2025 F (Alcaraz),
     Turnaj mistrů 2025 F (Sinner), Monte Carlo Masters 2026 F (Sinner) – tedy Sinner vyhrál
     poslední i tři z posledních šesti.
3. Zkusil jsem dohledat aktuální žebříčkové pozice z `atp_matches_2026.csv`, ale čísla
   žebříčku se v souboru nesmyslně mění zápas od zápasu v rámci stejného turnaje
   (např. Sinnerův rank na Monte Carlu 2026 skáče 8/14/27/31) – vypadá to na syntetická/
   neconsistentní data, takže jsem je do odpovědi nezahrnoval jako tvrdé číslo.
4. Zjistil jsem, že data v `atp_matches_2026.csv` končí Roland Garros 2026 (25. 5. 2026),
   tedy několik měsíců před "dnešním" datem (1. 10. 2026) nastaveným v prostředí – nemám
   tedy žádnou informaci o aktuální formě, zraněních ani o tom, o jaký konkrétní budoucí
   zápas/turnaj se ptá uživatel (nebyl specifikován povrch ani termín).
5. Na základě toho jsem odpověď postavil jako vyvážené posouzení (bez umělého tvrzení
   přesné pravděpodobnosti): zápas je prakticky "coinflip" mezi dvěma špičkovými hráči,
   s historickou lehkou převahou Alcaraze (hlavně na antuce) a opačným trendem v posledních
   velkých finále (Sinner), a navrhl jsem uživateli upřesnit turnaj/povrch pro přesnější odhad.

Zdrojové soubory použité k analýze:
- /root/statistiky/README.md
- /root/statistiky/tenis/atp_matches_2021.csv ... atp_matches_2026.csv
