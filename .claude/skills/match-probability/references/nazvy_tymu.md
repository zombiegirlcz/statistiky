# Jak jsou týmy/hráči zapsaní v datech

## Fotbal (`fotbal/*.csv`)

Názvy klubů jsou v anglickém, zkráceném tvaru podle football-data.co.uk, ne vždy stejném jako běžný český název. Nejčastější úskalí (anglická Premier League):

| Běžný název | Zápis v datech |
|---|---|
| Manchester United | `Man United` |
| Manchester City | `Man City` |
| Tottenham Hotspur | `Tottenham` |
| Nottingham Forest | `Nott'm Forest` |
| Newcastle United | `Newcastle` |
| Wolverhampton | `Wolves` |
| Leicester City | `Leicester` |

Skript dělá fuzzy matching, takže drobné odchylky (diakritika, mezery) obvykle najde sám. U německých/španělských/italských týmů zkus nejdřív běžný anglický název klubu (např. "Bayern Munich", "Real Madrid", "Inter").

Pokrytí: Anglie (5 úrovní), Skotsko (4), Německo (2), Itálie (2), Španělsko (2), Francie (2), Nizozemsko, Belgie, Portugalsko, Turecko, Řecko - viz `/statistiky/README.md`.

## Tenis (`tenis/*.csv`)

Celá jména hráčů v latince, bez diakritiky vždy přesně podle ATP/WTA zápisu (např. `Novak Djokovic`, `Carlos Alcaraz`, `Iga Swiatek`). Skript prohledává ATP i WTA soubory najednou, takže není potřeba předem vědět, jestli jde o mužský nebo ženský túr.

## Hokej (`hokej/NHL_*.csv`)

Týmy jsou zapsané jako 3písmenné NHL zkratky (TOR, EDM, MTL...), ne celým názvem. Skript má zabudovaný seznam aliasů (město, maskot i zkratka), takže stačí zadat třeba "Toronto", "Maple Leafs" nebo rovnou "TOR" - všechno vede ke stejnému výsledku. Platí jen pro NHL - KHL, švýcarská liga ani mezinárodní zápasy (MS, olympiáda) v datech nejsou.

Aktuálních 32 týmů a jejich zkratky viz přímo v `scripts/aggregate_stats.py` (slovník `NHL_ALIASES`).
