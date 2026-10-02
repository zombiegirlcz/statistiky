#!/bin/bash
# tick.sh - jedno "kolo" bezicího agenta, spoustí ho modal_app.py uvnitr
# kratkodobeho Sandboxu (viz tam docstring pro cely architektonicky rozbor).
#
# Co dela, v poradi:
#   1. Synchronizuje repo statistiky na perzistentnim Modal Volume (clone
#      poprve, pak vzdy pull) - tohle je JEDINY zdroj pravdy pro stav banky
#      (live_bets_log.jsonl), sdileny i s telefonem pres git.
#   2. Spusti `pi` (pi-coding-agent) s jednorazovym ukolem: podivat se na
#      dosavadni vysledky (bet_evaluator.py report), rozhodnout, jestli
#      strategii upravit, a pak spustit bezny cyklus (watch + vyhodnot).
#   3. Zapise a pushne zpet do GitHubu, cokoliv se zmenilo (log tiketu,
#      pripadne upravy strategie, ktere `pi` udela).
#
# OVERENO (lokalni test, pi 0.87.1): `-p/--print` je skutecne neinteraktivni
# rezim presne jak se predpokladalo. Povoleni nastroju ale NENI `--allow-tool`
# (to pi nezna) - spravny flag je `--tools`/`-t` s carkou oddelenym seznamem
# (napr. `--tools bash`). Testovano i s realnym bash pristupem (spustil
# bet_evaluator.py report a spravne shrnul vystup), takze cely tenhle krok
# uz je funkcne overeny, ne jen odhad.
set -euo pipefail

REPO_DIR="/data/statistiky"
REPO_URL="https://github.com/zombiegilrcz/statistiky.git"

if [ -d "$REPO_DIR/.git" ]; then
    echo "[tick] repo existuje, pulluji..."
    git -C "$REPO_DIR" pull --rebase --autostash
else
    echo "[tick] prvni beh, klonuji repo na volume..."
    git clone --depth 50 "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR/.agents/skills/match-probability/scripts"

echo "[tick] spoustim pi agenta (strategie + rozhodnuti)..."
# Syntax overena lokalnim testem (viz docstring vyse): -p je neinteraktivni
# rezim, --tools je spravny flag pro povoleni nastroju (ne --allow-tool).
pi -p "Podivej se na vysledky dosavadnich fiktivnich sazek
(python3 bet_evaluator.py report, bez volani API) a na aktualni parametry
strategie v live_tennis_simulator.py (FAV_MODEL_MIN, FAV_MARKET_MIN,
FAV_MAX_ODDS, STAKE_PCT...). Pokud vzorek tiketu uz je dost velky na
smysluplny zaver (viz N_MEANINGFUL v bet_evaluator.py) a vidis poctivy duvod
parametry upravit, uprav je - jinak nech beh probehnout beze zmeny. Vzdy
BOOKMAKER=sxbet_sim (fiktivni mince), zadne realne sazeni bez vyslovneho
schvaleni uzivatele. Pak spust 'python3 live_tennis_simulator.py watch' a
'python3 bet_evaluator.py vyhodnot'." \
    --tools bash \
    2>&1 || echo "[tick] VAROVANI: beh pi agenta selhal, pokracuji primym behem skriptu"

echo "[tick] jistota: spust watch+vyhodnot i kdyby pi vys nic nespustil"
python3 live_tennis_simulator.py watch || true
python3 bet_evaluator.py vyhodnot || true

cd "$REPO_DIR"
if ! git diff --quiet || ! git diff --cached --quiet; then
    git add -A \
        .agents/skills/match-probability/live_bets_log.jsonl \
        .agents/skills/match-probability/live_progress_log.jsonl \
        .agents/skills/match-probability/scripts/live_tennis_simulator.py
    git commit -m "cron_tick (modal): aktualizace tiketu/logu $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    git push origin HEAD:master
    echo "[tick] zmeny pushnuty"
else
    echo "[tick] zadne zmeny k pushnuti"
fi
