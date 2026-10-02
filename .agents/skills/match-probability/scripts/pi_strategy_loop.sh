#!/bin/bash
# pi_strategy_loop.sh - "mozek": necha pi zhodnotit vysledky a VYLEPSIT nebo
# VYMYSLET sazejici strategii. Pousten z cronu casto (napr. kazdych 20 min),
# ale SKUTECNE se rozbehne jen kdyz se hraji zapasy - o tom rozhoduje
# pi_schedule.py (kalendar Live Tennis API, cache, min API kvoty).
#
# Rozdil proti cron_tick.sh:
#   cron_tick.sh     = HLIDAC - kazdych 20 min watch/vyhodnot/tick (sazi)
#   pi_strategy_loop = MOZEK  - jen v aktivnim okne, max 1x za MIN_INTERVAL
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
STAMP="$DIR/.pi_brain_last_run"
MIN_INTERVAL=7200   # 2 h - mozek nema bezet casteji (kvota, smysl)

log() { echo "$@" >> "$LOG"; }

echo "" >> "$LOG"
echo "########## PI MOZEK pokus $(date '+%F %T %Z') ##########" >> "$LOG"

# 1) PLANOVANI: hraji se zapasy? (pi_schedule ma vlastni cache, ~0 API)
if ! python3 pi_schedule.py active >> "$LOG" 2>&1; then
    log "[pi] klid - zadne zapasy, koncim (spustim se, az se bude hrat)"
    log "########## PI MOZEK konec (klid) $(date '+%F %T %Z') ##########"
    exit 0
fi

# 2) THROTTLE: mozek max 1x za MIN_INTERVAL (i kdyz se hraje)
now=$(date +%s)
if [ -f "$STAMP" ]; then
    last=$(cat "$STAMP" 2>/dev/null || echo 0)
    if [ $((now - last)) -lt "$MIN_INTERVAL" ]; then
        log "[pi] mozek uz bezel pred $(( (now-last)/60 )) min - preskakuji (min interval $((MIN_INTERVAL/60)) min)"
        log "########## PI MOZEK konec (throttle) $(date '+%F %T %Z') ##########"
        exit 0
    fi
fi

if [ ! -f "$PROMPT_FILE" ]; then
    log "[pi] CHYBA: chybi prompt $PROMPT_FILE"
    exit 1
fi

# 3) REPORT + MOZEK
python3 bet_evaluator.py report >> "$LOG" 2>&1 || log "[pi] report selhal"

pi -p "$(cat "$PROMPT_FILE")" \
   --tools bash,edit,write,read \
   >> "$LOG" 2>&1 || log "[pi] beh pi selhal (viz log vyse)"

date +%s > "$STAMP"
log "########## PI MOZEK konec $(date '+%F %T %Z') ##########"
