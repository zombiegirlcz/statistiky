#!/usr/bin/env bash
# start.sh — spustí PWA Loterie na lokálním serveru.
# Použití:  ./start.sh [port]     (default 8765)
#
# DŮLEŽITÉ: 0.0.0.0 je jen "poslouchat na všech rozhraních" (bind adresa).
# V prohlížeči se otevře  http://localhost:PORT  nebo  http://127.0.0.1:PORT
# NIKDY ne http://0.0.0.0:PORT (to v prohlížeči nefunguje).

PORT="${1:-8765}"
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1

echo "PWA Loterie — server"
echo "  složka: $DIR"
echo "  port:   $PORT"
echo

pkill -f "http.server $PORT" 2>/dev/null
sleep 0.3

setsid nohup python3 -m http.server "$PORT" --bind 0.0.0.0 \
  >"/tmp/pwa-$PORT.log" 2>&1 &
sleep 1

if curl -s -m 3 -o /dev/null "http://127.0.0.1:$PORT/"; then
  echo "✔ Server běží."
  echo
  echo "Otevři v prohlížeči:"
  echo "    http://localhost:$PORT"
  echo "    http://127.0.0.1:$PORT"
  echo
  echo "Zastavit:   pkill -f 'http.server $PORT'"
  echo "Log:        /tmp/pwa-$PORT.log"
else
  echo "✘ Server se nespustil. Log:"
  cat "/tmp/pwa-$PORT.log" 2>/dev/null
  exit 1
fi