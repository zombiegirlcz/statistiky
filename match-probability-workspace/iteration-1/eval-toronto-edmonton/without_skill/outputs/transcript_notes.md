# Transcript notes — Toronto Maple Leafs vs Edmonton Oilers

What I did to arrive at the answer (no specialized skill used, just manual exploration of the repo):

1. Explored `/root/statistiky` directory structure — found `fotbal/`, `tenis/`, `hokej/` data folders plus a `README.md` describing the dataset (football/tennis/NHL box scores 2021-2026, sourced from football-data.co.uk, Sackman tennis archive, and the NHL API).
2. Read `/root/statistiky/README.md` for dataset scope/limitations — confirmed hockey coverage is NHL only, 5 seasons (2021-22 through 2025-26), one row per game with columns for shots on goal, faceoff %, power play, PIM, hits, blocked shots, giveaways/takeaways for home and away teams.
3. Listed `/root/statistiky/hokej/` — found `NHL_2021-2022.csv` through `NHL_2025-2026.csv` (and matching .md versions). No 2026-2027 season file exists.
4. Checked the tail of `NHL_2025-2026.csv` — season data runs through playoffs ending 2026-06-14, i.e. the entire 2025-26 season (including playoffs) is already complete in the dataset. Since "today" is given as 2026-10-01, this is the most recent complete season available; no current/new-season fixture data exists for a literal upcoming TOR-EDM game.
5. Grepped all 5 season CSVs for TOR vs EDM head-to-head games (`grep -E "TOR.*EDM|EDM.*TOR"`), found 10 meetings across 2021-22 to 2025-26 and manually tallied results from the `away_team,home_team,away_score,home_score` columns: Toronto won 7 of 10 (2021-22: 2-0 TOR; 2022-23: 1-1; 2023-24: 1-1; 2024-25: 2-0 TOR; 2025-26: 1-1, Edmonton won the first meeting 6-3, Toronto won the rematch 5-2).
6. Wrote a small Python script (using `csv.DictReader`) to compute each team's full regular-season 2025-26 record, goals for/against, and last-10-games record:
   - TOR: 32-50 (.390), GF 253 / GA 299, last 10 games 2-8, missed playoffs.
   - EDM: 41-41 (.500), GF 282 / GA 269, last 10 games 6-4, made playoffs but lost first round to Anaheim 1-4.
7. Extended the script to compute power-play / penalty-kill percentages for both teams over the 2025-26 regular season: EDM PP 30.6% / PK 77.8%; TOR PP 21.3% / PK 81.2%.
8. Combined team win% via the log5 method to produce a rough win-probability estimate (no home/away specified by the user, so gave neutral-site, EDM-home, and TOR-home scenarios): neutral ~60-62% EDM / 38-40% TOR; EDM home ~65-67% EDM; TOR home ~44-46% TOR.
9. Wrote the final Czech-language answer summarizing: data-recency caveat (no 2026-27 season data), 2025-26 season form comparison, head-to-head history, probability estimate, and a responsible-gambling caveat since no current roster/injury/goalie information is available in this dataset.

No external web lookups were performed — analysis is based entirely on the local CSV files in `/root/statistiky/hokej/`.
