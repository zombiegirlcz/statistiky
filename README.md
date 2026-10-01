# Sportovní statistiky (2021–2026)

Dvě vrstvy dat za posledních ~5 sezón ve třech sportech, vše převedeno do Markdownu nástrojem **markitdown** (`/root/markitdown/.venv`).

1. **Přehledové soubory** (`YYYY_in_*.md`) — vítězové hlavních turnajů, žebříčky a klíčové události daného roku, čerpáno z Wikipedie.
2. **Kompletní zápasová data** (`*.csv` + `*.md`) — statistiky na úrovni jednotlivého zápasu (rohy, střely, karty, esa, brejkboly, přesilovky atd.), čerpáno z datových zdrojů popsaných níže.

## Struktura

### `fotbal/`
- 5× přehled roku (2021–2025, Wikipedia)
- **110 CSV/MD souborů** = 22 evropských lig × 5 sezón (2021-22 až 2025-26). Každý řádek = 1 zápas se sloupci:
  `HS/AS` střely, `HST/AST` střely na branku, `HF/AF` fauly, **`HC/AC` rohové kopy**, `HY/AY/HR/AR` žluté/červené karty, kurzy sázkových kanceláří.
  Ligy: Anglie (Premier League, Championship, League One/Two, National League), Skotsko (4 ligy), Německo (Bundesliga, 2. Bundesliga), Itálie (Serie A/B), Španělsko (La Liga/Segunda), Francie (Ligue 1/2), Nizozemsko, Belgie, Portugalsko, Turecko, Řecko.
  Zdroj: [football-data.co.uk](https://www.football-data.co.uk)

### `tenis/`
- 5× přehled roku (2021–2025, Wikipedia)
- **12 CSV/MD souborů** = ATP + WTA, roky 2021–2026 (2026 částečně, sezóna probíhá). Každý řádek = 1 zápas z celosvětového túru (Grand Slamy, Masters/1000, ATP/WTA 250-500 atd.) se sloupci: esa (`w_ace`/`l_ace`), dvojchyby (`w_df`/`l_df`), vyhrané body na servisu, **brejkboly** (`bpSaved`/`bpFaced`), délka zápasu, žebříčkové pozice hráčů.
  Zdroj: archiv [Jeff Sackman ATP/WTA match data](https://github.com/Aneeshers/tennis-sackmann-archive)
- **`tenis/prubeh/`** — herní úroveň (kdo podával a kdo vyhrál KAŽDÝ jednotlivý game, ne jen konečné skóre setu). Zdroj: [Jeff Sackmann's Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject) (crowdsourced bod-po-bodu data). **Pokrytí jen ~15–20 % zápasů od 2020** (dobrovolnický projekt, silně zkreslený směrem k top hráčům - u Sinnera/Alcaraze/Djokoviče stovky zápasů, u hráčů mimo top 100 často nic) - proto se nekonvertovala syrová bod-po-bodu notace (93 MB, nečitelná pro člověka), ale jen odvozená tabulka "kdo podával/vyhrál který game" (`games_m.csv`/`games_w.csv`, ~10 MB dohromady) + metadata zápasů (`charting-{m,w}-matches.csv`). **Licence CC BY-NC-SA 4.0 — pouze nekomerční použití.**

### `hokej/`
- 5× přehled roku (2021–2025, Wikipedia)
- **5 CSV/MD souborů** = NHL sezóny 2021-22 až 2025-26 (základní část + play-off), ~1400 zápasů/sezóna, ~7000 zápasů celkem. Každý řádek = 1 zápas se sloupci: střely na branku (`sog`), vhazování (`faceoffWinningPctg`), přesilovky (`powerPlay`), **vyloučení v minutách (`pim`)**, hity, zblokované střely, ztráty/zisky puku, pro domácí i hostující tým.
  Zdroj: [NHL API](https://api-web.nhle.com) (oficiální veřejné rozhraní)

## Známá omezení rozsahu ("co nejširší pokus")

Doslova kompletní celosvětová data (všechny soutěže na všech kontinentech) nejsou zdarma dostupná v žádném strojově čitelném zdroji. Rozsah byl proto omezen na největší veřejně dostupné datasety s plným box score:

- **Fotbal**: pouze evropské domácí ligy (22 soutěží). Mezinárodní turnaje (MS, EURO, Liga mistrů) a mimoevropské ligy (Jižní Amerika, Asie, Afrika, MLS) nemají volně dostupná data s počtem rohů na úrovni zápasu — u nich zůstává jen přehled z Wikipedie.
- **Hokej**: pouze NHL. Mezinárodní zápasy (MS IIHF, olympijský hokej) a jiné ligy (KHL, SHL, švýcarská NL) nemají veřejné API se zápasovým box score — u nich zůstává jen přehled z Wikipedie.
- **Tenis**: pokrytí je nejširší ze všech tří sportů — zahrnuje prakticky všechny zápasy hlavní túry ATP i WTA celosvětově.

## Postup

1. Data stažena přímo (CSV/API), Wikipedia stránky staženy jako HTML přes `curl`.
2. Vše převedeno do Markdownu nástrojem `markitdown` (CLI, u souborů s diakritikou v Python API s explicitním `charset='utf-8'` kvůli chybné autodetekci kódování).
3. U Wikipedia přehledů odstraněn navigační a licenční balast (hlavička/patička).

## Skilly nad těmito daty

- **`match-probability`** — spočítá pravděpodobnost výsledku zápasu dvou týmů/hráčů z historických dat (viz `.claude/skills/match-probability`). Volitelně umí i `scripts/odds_compare.py` — porovnání s živými sázkovými kurzy přes [The Odds API](https://the-odds-api.com) (klíč v `~/.env` jako `ODDS_API_KEY`, zdarma 500 kreditů/měsíc).
- **`update-sport-stats`** — denně doplňuje aktuální sezónu/rok o nově odehrané zápasy, včetně automatického rozpoznání nové sezóny (viz `.claude/skills/update-sport-stats`). Běží samo každý den v 9:00 UTC přes lokální cron, log v `~/.local/state/update-sport-stats/cron.log`.
