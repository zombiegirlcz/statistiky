#!/bin/bash
# Jeden tik živého tenisového simulátoru. Spouští ho cron každých 20 minut
# mezi 16:00 a 23:59. Sleduje zápasy a sází; po 23:40 se sám odstraní z cronu.
DIR=/root/statistiky/.agents/skills/match-probability/scripts
cd "$DIR" || exit 1
# Cron má minimální PATH (/usr/bin:/bin) - `nh` (notifikace) je v /usr/local/bin,
# bez tohohle řádku notify() tiše nic nepošle (viz live_tennis_simulator.notify).
export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
source ~/.env
LOG=$DIR/run_until_midnight.log

H=$(date +%H); M=$(date +%M)
echo "" >> "$LOG"
echo "########## $(date '+%F %T %Z') ##########" >> "$LOG"

# vyhodnocení dohraných zápasů v :00 (ne každých 20 min, šetří API kvótu)
if [ "$M" -lt 20 ]; then
  python3 bet_evaluator.py vyhodnot >> "$LOG" 2>&1
fi

# sledování živých zápasů + zakládání tiketů (match-level: vítěz celého zápasu)
python3 live_tennis_simulator.py watch >> "$LOG" 2>&1

# gem-level režimy (vítěz AKTUÁLNÍHO gemu) - normální i agresivní banka.
# Bez tohohle se gemové tikety vyhodnocují/zakládají jen při ručním spuštění.
echo "--- live_game_bet tick ---" >> "$LOG"
python3 live_game_bet.py tick >> "$LOG" 2>&1
echo "--- live_game_bet agresivni-tick ---" >> "$LOG"
python3 live_game_bet.py agresivni-tick >> "$LOG" 2>&1

# po 23:40 finální vyhodnocení a úklid cronu
if [ "$H" = "23" ] && [ "$M" -ge 40 ]; then
  echo "=== FINÁLE $(date '+%F %T %Z') ===" >> "$LOG"
  python3 bet_evaluator.py vyhodnot >> "$LOG" 2>&1
  python3 bet_evaluator.py report >> "$LOG" 2>&1
  python3 live_game_bet.py status >> "$LOG" 2>&1
  python3 live_game_bet.py agresivni-status >> "$LOG" 2>&1
  crontab -l 2>/dev/null | grep -v cron_tick.sh | crontab -
  echo "=== cron odstraněn, konec ===" >> "$LOG"
fi