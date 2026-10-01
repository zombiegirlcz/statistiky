#!/bin/bash
# Aktivní agentní smyčka: sleduj živé tenisové zápasy, zakládej tikety a průběžně
# vyhodnocuj — dokud běží zápasy nebo dokud není půlnoc. Běží v popředí, píše na stdout.
DIR=/root/statistiky/.claude/skills/match-probability/scripts
cd "$DIR" || exit 1
source ~/.env

END=$(( $(date -d '23:59' +%s) ))
ITER=${1:-2}          # kolik cyklů v tomhle běhu
SLEEP=${2:-900}       # pauza mezi cykly (s)
last_eval=0

for i in $(seq 1 "$ITER"); do
  now=$(date +%s)
  if [ "$now" -ge "$END" ]; then echo "=== PŮLNOC, končím ==="; break; fi

  echo ""
  echo "################ CYKLUS $i  $(date '+%F %T %Z') ################"

  if [ $((now - last_eval)) -ge 5400 ]; then
    echo "--- vyhodnocení dohraných zápasů ---"
    python3 bet_evaluator.py vyhodnot 2>&1 | sed -n '1,25p'
    last_eval=$now
  fi

  echo "--- watch (sledování + tikety) ---"
  python3 live_tennis_simulator.py watch 2>&1 | sed -n '/Živých zápasů/,$p'

  if [ "$i" -lt "$ITER" ]; then
    # spočítej spánek tak, abychom nepřelezli půlnoc
    remain=$(( END - $(date +%s) ))
    s=$SLEEP; [ "$s" -gt "$remain" ] && s=$remain
    [ "$s" -gt 0 ] && { echo "--- spím ${s}s ---"; sleep "$s"; }
  fi
done
echo ""
echo "=== konec běhu $(date '+%F %T %Z') ==="
python3 bet_evaluator.py report 2>&1 | sed -n '1,30p'