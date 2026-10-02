#!/bin/bash
# pi_strategy_loop.sh - "mozek": necha pi zhodnotit vysledky a VYLEPSIT nebo
# VYMYSLET sazejici strategii. Pousten z cronu 1-2x denne (ne kazdych 20 min).
#
# Rozdil proti cron_tick.sh:
#   cron_tick.sh     = HLIDAC - kazdych 20 min watch/vyhodnot/tick (sazi)
#   pi_strategy_loop = MOZEK  - 1-2x denne pi rozmysli a upravi strategii
#
# VZDY BOOKMAKER=sxbet_sim - tenhle skript nikdy nezapne realne sazeni.
set -uo pipefail

DIR=/root/statistiky/.agents/skills/match-probability/scripts
cd "$DIR" || exit 1
export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
source ~/.env 2>/dev/null || true

export BOOKMAKER=sxbet_sim

LOG="$DIR/pi_strategy_loop.log"
PROMPT_FILE="$DIR/pi_strategy_prompt.md"

echo "" >> "$LOG"
echo "########## PI MOZEK start $(date '+%F %T %Z') ##########" >> "$LOG"

if [ ! -f "$PROMPT_FILE" ]; then
    echo "[pi] CHYBA: chybi prompt $PROMPT_FILE" >> "$LOG"
    exit 1
fi

python3 bet_evaluator.py report >> "$LOG" 2>&1 || echo "[pi] report selhal" >> "$LOG"

pi -p "$(cat "$PROMPT_FILE")" \
   --tools bash,edit,write,read \
   >> "$LOG" 2>&1 || echo "[pi] beh pi selhal (viz log vyse)" >> "$LOG"

echo "########## PI MOZEK konec $(date '+%F %T %Z') ##########" >> "$LOG"
