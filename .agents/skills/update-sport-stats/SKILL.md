---
name: update-sport-stats
description: Aktualizuje sportovní statistiky v /statistiky (fotbal, tenis, hokej) o nově odehrané zápasy od posledního spuštění. Použij tento skill, když tě někdo požádá o aktualizaci, obnovení, doplnění nebo synchronizaci sportovních dat ("doplň nové zápasy", "aktualizuj statistiky", "stáhni poslední výsledky"), nebo když běžíš jako naplánovaná denní údržbová úloha pro tento projekt. Na rozdíl od prvotního jednorázového sběru dat tenhle skript stahuje jen přírůstek - historické uzavřené sezóny nechává být a sahá jen na aktuální sezónu/rok u každého sportu, včetně automatického rozpoznání přechodu na novou sezónu.
---

# Denní aktualizace sportovních statistik

## Co to dělá a proč

`/statistiky` obsahuje historická data (fotbal, tenis, hokej) i skript `match-probability`, který z nich počítá pravděpodobnosti zápasů. Aby ty predikce zůstaly užitečné, potřebují čerstvá data - jinak by model o týden od teď furt počítal s formou týmů starou týden. Tenhle skill řeší přesně tohle: jedním spuštěním doplní, co od posledně přibylo, a nic víc.

Je to návazný nástroj na prvotní historický sběr (ten stáhl 5 kompletních sezón najednou a trval desítky minut kvůli tisícům NHL zápasů) - tady jde o rychlou denní údržbu, řádově sekundy až pár minut.

## Jak na to

Před spuštěním skriptu i jakýmikoliv úpravami se ujisti, že pracuješ přímo na větvi `master` (`git checkout master`).

Spusť skript, nic jiného není potřeba řešit ručně:

```bash
python3 .agents/skills/update-sport-stats/scripts/update_stats.py
```

Skript sám:

1. **Fotbal** - přepíše CSV aktuální sezóny (2026-27 apod.) čerstvou verzí ze zdroje pro všech 22 lig. Staré sezóny nestahuje vůbec, protože se už nemění.
2. **Tenis** - přepíše CSV aktuálního roku (plus okolní roky pro jistotu) z archivu ATP/WTA dat.
3. **Hokej** - projde aktuální NHL sezónu a připojí JEN zápasy, které v CSV ještě nejsou (podle `game_id`) - nestahuje znovu nic, co už tam je.
4. Soubory, které se skutečně změnily, rovnou převede do Markdownu (`markitdown`) - nedotčené soubory nechává být, aby to zbytečně netrvalo.
5. Vše zaloguje do `/statistiky/_update_log.txt` (časové razítko, co se změnilo, kolik řádků přibylo).

Pokud chceš aktualizovat jen jeden sport, přidej argument: `python3 update_stats.py hokej` (nebo `fotbal` / `tenis`).

### Co dělat s výstupem

Po doběhnutí skriptu stručně shrň uživateli, co se změnilo (kolik nových zápasů/řádků v kterém sportu) - stejně jako to dělá log. Pokud skript nic nenašel (sezóna zrovna nehraje, data ještě nejsou na zdroji), řekni to rovnou, není to chyba.

**Pokud skript spadne na síťové chybě** (zdroj dat nedostupný), zkus to znovu o něco později - weby jako football-data.co.uk nebo NHL API občas na chvíli vypadnou, není potřeba hned hlásit poruchu.

## Automatizace (denní spouštění)

Tohle běží samo každý den v 9:00 UTC přes lokální `cron` (ne cloudový Claude routine - tahle složka není git repo a data musí zůstat na tomto stroji, kde je čte i skill `match-probability`):

- Wrapper: `/root/.local/bin/update-sport-stats-cron` (řeší PATH/HOME pro cron, logování, rotaci logu, notifikaci jen při skutečné změně)
- Crontab řádek: `0 9 * * * /root/.local/bin/update-sport-stats-cron`
- Log: `~/.local/state/update-sport-stats/cron.log`
- Notifikace: přes `nh system notification`, jen když přibyly nové zápasy nebo běh selhal (žádný denní spam)

Vypnutí: smaž příslušný řádek z `crontab -e` (je označený komentářem `# statistiky: denni doplneni novych zapasu`). Změna času: uprav cron výraz stejným způsobem.

### Přechod na novou sezónu

Skript si datum podle dneška sám spočítá, kterou sezónu/rok považovat za "aktuální", takže když v srpnu/říjnu začne nová sezóna, automaticky si pro ni vytvoří nový CSV soubor - není potřeba nic ručně měnit. Pokud by se přesto stalo, že se nějaký zdroj dat přejmenoval nebo změnil formát (málo pravděpodobné, ale weby se mění), skript to v logu nahlásí jako chybu stahování - v tom případě je potřeba se podívat, jestli URL adresa zdroje pořád sedí (viz `scripts/update_stats.py`, zdrojové URL jsou nahoře v konstantách).
