# CLI Guide — Správa tenisového sázejícího agenta

Kompletní průvodce příkazovou řádkou pro řízení agentů a bank.

## Úvod

CLI nástroj (`cli.py`) poskytuje programový přístup k systému správy sázejících agentů. Oproti TUI (interaktivnímu barevnému menu v `main.py`) je CLI:

- **Non-interaktivní** — Vhodný pro shell skripty, cron joby, Modal deployment
- **Scriptovatelný** — Vrací standardní exit kódy, snadno se parsuje výstup
- **Rychlý** — Bez čekání na uživatelský vstup
- **Automatizovatelný** — Ideální pro `pi` a ostatní agenty

## Návod v krocích

### Iniciální nastavení

1. **Zobrazit aktuální stav:**
   ```bash
   python3 cli.py status
   ```
   Vrátí:
   - Hlavní banka (volné mince)
   - Alokace agentů (přidělené mince)
   - Celkový rozpočet
   - Seznam agentů a jejich stavu

2. **Vložit mince do hlavní banky** (pokud je nulová):
   ```bash
   python3 cli.py bank deposit 5000
   python3 cli.py bank status
   ```

3. **Vytvořit nového agenta:**
   ```bash
   python3 cli.py agent create "Můj Match Agent" match_fav 1000
   python3 cli.py agent create "Můj Gem Agent" gem 500
   python3 cli.py agent list
   ```
   
   Dostupné strategie:
   - `match_fav` — Sází na vítěze CELÉHO zápasu (strong favorites)
   - `gem` — Sází na vítěze jednotlivého gemu (vyšší frekvence)
   - `gem_aggr` — Agresivní gem (celá banka na jednom tiket, cíl 6×, risk okamžité ztráty)

### Běžný provoz

4. **Spustit sázkový cyklus:**
   ```bash
   # Spustit všechny aktivní agenty
   python3 cli.py run
   
   # Spustit jen konkrétního agenta
   python3 cli.py run --agent match-fav
   ```
   
   Tento příkaz:
   - Vyhodnotí dohraná sázky (bet_evaluator)
   - Spustí watch (live_tennis_simulator)
   - Zakládá nové sázky podle strategie

5. **Zobrazit výsledky:**
   ```bash
   python3 cli.py results --limit 20
   ```
   
   Vrátí:
   - Posledních N tiketů (status, kurz, vklad)
   - Statistika: počet výher/proher, win rate %, ROI

6. **Zkontrolovat banku:**
   ```bash
   python3 cli.py bank status
   python3 cli.py agent list
   ```

### Správa prostředků

7. **Přidat mince agentovi** (ze sousední banky, pokud chce více):
   ```bash
   python3 cli.py agent fund match-fav 500
   python3 cli.py agent list
   ```

8. **Vybrat mince od agenta** (když skončit, nebo pokud selhal):
   ```bash
   python3 cli.py agent defund gem 300
   python3 cli.py agent list
   ```

9. **Dočasně vypnout agenta** (bez smazání):
   ```bash
   python3 cli.py agent toggle match-fav
   python3 cli.py agent list
   # Vypnuto znamená, že `cli.py run` ho nespustí
   ```

10. **Permanentně smazat agenta:**
    ```bash
    python3 cli.py agent remove gem --force
    # Bez --force se zeptá na potvrzení; vrátí jeho banku do hlavní
    ```

## Exit kódy

| Kód | Znamená |
|-----|---------|
| 0   | Úspěch |
| 1   | Chyba (nedost peněz, agent neexistuje, špatná strategie, ...) |
| >1  | Chyba agenta (executor.run_all vrátil specifický exit code) |

## Typické automatizační scénáře

### Cron job (každých 15 minut)
```bash
#!/bin/bash
cd /root/statistiky/.agents/skills/match-probability/scripts
source /root/.env  # pro API klíče
python3 cli.py run >> /tmp/cli_cron.log 2>&1
exit_code=$?
if [ $exit_code -ne 0 ]; then
    echo "CHYBA: cli.py run skončil s kódem $exit_code" | mail admin@example.com
fi
exit $exit_code
```

### Modal deployment (via tick.sh)
```bash
#!/bin/bash
# tick.sh jde v Sandboxu, cli.py se používá pro status+summary

cd /root/statistiky/.agents/skills/match-probability/scripts

# Běh agenta
python3 cli.py run

# Zaplnout stav, aby viděl uživatel
python3 cli.py status

# Pushnout zmeny do gitu
cd /root/statistiky
git add .agents/skills/match-probability/live_*.jsonl
git commit -m "cron_tick: aktualizace tiketů"
git push origin HEAD:master
```

### Pi integrace (agent řídí ostatní agenty)
```bash
# Pi dostane výstup CLI a rozhoduje
pi -p "
Podívej se na výstup stavu:
$(python3 cli.py status)

A výsledky:
$(python3 cli.py results --limit 5)

Pokud má některý agent méně než 200 mincí v bance, přidej mu 200 z hlavní.
Pokud bank hlavní klesla pod 500, stahni od některého agenta (toho co má více).
" --tools bash
```

## Srovnání: CLI vs. TUI

| Vlastnost | CLI | TUI |
|-----------|-----|-----|
| Interaktivita | Ne (příkazy) | Ano (menu) |
| Scripovatelnost | Ano | Ne |
| Barevný výstup | Ano | Ano |
| Uživatelský vstup | Pevné argumenty | Dialogy |
| Chyba=? | Stiskne Ctrl+C | Exit kód |
| Vhodná pro | Automatizace | Manuální práce |

## Chybové zprávy a řešení

```
Chyba: V hlavní bance není dost
→ Buď vložit víc: cli.py bank deposit <amount>
→ Nebo vyměnit prioritu (vybrat od jiného agenta)

Chyba: Agent 'xyz' neexistuje
→ Zkontrolovat: cli.py agent list
→ Možná se agentovi změní ID (fuzzy slug). Např. "Můj agent" → "muj-agent"

Chyba: Neznámá strategie
→ Dostupné: match_fav, gem, gem_aggr
→ Kontrola: python3 cli.py agent create --help
```

## Poznámky k datům

- **Tikety se logují** do `live_bets_log.jsonl`, `live_game_bets_log.jsonl` atd.
- **Agenti se uchovávají** v `../agents.json` (JSON, lze editovat ručně)
- **Výsledky živých sázek** si vezmu z LIVE Tennis API (za API kvótu)
- **Kurzy** z Odds API (za API kvótu)
- **Oba klíče** jsou v `~/.env` — bez nich scripts vrátí chybu

Příkazy `cli.py status` a `cli.py results` NESPOTŘEBUJÍ API (jen čtou logové soubory).
Příkazy `cli.py run` API potrebují.

## Pokročilé

### Editace agents.json ručně
```bash
# Viz obsah
cat ../.agents/skills/match-probability/agents.json | python3 -m json.tool

# Editace (opatrně!)
vim ../.agents/skills/match-probability/agents.json

# Validace (zkontroluj syntaxi)
python3 -c "import json; json.load(open('../agents.json'))" && echo OK
```

### Vrácení agentů do výchozího stavu
```bash
# Resetuj registr na výchozí (3 agenti, 10000 v bance)
python3 -c "import agents; agents.save_registry(agents._vychozi_registry())"
python3 cli.py agent list
```
