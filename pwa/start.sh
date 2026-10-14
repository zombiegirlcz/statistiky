#!/usr/bin/env bash
# start.sh — PWA Loterie na serveru přístupném v síti (Wi-Fi / hotspot).
# Použití: ./start.sh [port]   (default 8765)
#
# Bind 0.0.0.0 = poslouchá na všech rozhraních → kdokoli na stejné síti
# ho uvidí na své IP. Do prohlížeče patří skutečná IP, nikdy 0.0.0.0.

PORT="${1:-8765}"
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1

# --- najdi síťové IPv4 (vynech loopback a mobilní rmnet) ---
LAN_IPS="$(ip -4 addr show 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 \
  | grep -v '^127\.' | grep -v '^10\.67\.' | grep -v '^10\.49\.')"
if [ -z "$LAN_IPS" ]; then
  LAN_IPS="$(hostname -I 2>/dev/null | tr ' ' '\n' \
    | grep -v '^127\.' | grep -v '^10\.67\.' | grep -v '^10\.49\.' | grep -v '^$')"
fi

pkill -f "http.server $PORT" 2>/dev/null
sleep 0.3

setsid nohup python3 -m http.server "$PORT" --bind 0.0.0.0 >"/tmp/pwa-$PORT.log" 2>&1 &
sleep 1

echo "═══════════════════════════════════════════════════"
echo "  PWA Loterie — server"
echo "═══════════════════════════════════════════════════"
echo "  složka: $DIR"
echo "  port:   $PORT"
echo
echo "  Na tomto zařízení:  http://localhost:$PORT"
echo
if curl -s -m 3 -o /dev/null "http://127.0.0.1:$PORT/"; then
  echo "  ✔ Server běží."
  echo
  if [ -n "$LAN_IPS" ]; then
    echo "  Ostatní na stejné síti otevřou:"
    for ip in $LAN_IPS; do echo "      http://$ip:$PORT"; done
  else
    echo "  ⚠ Žádná síťová IP — Wi-Fi/hotspot je vypnutý, nebo ho guest nevidí."
    echo "    Zapni Wi-Fi/hotspot a spusť znovu.  (ip -4 addr | grep inet)"
  fi
else
  echo "  ✘ Server se nespustil:"; cat "/tmp/pwa-$PORT.log" 2>/dev/null; exit 1
fi
echo
echo "  Zastavit: pkill -f 'http.server $PORT'   Log: /tmp/pwa-$PORT.log"
echo "  Pozor: běží bez hesla (HTTP), kdokoli na síti ho uvidí."
echo "═══════════════════════════════════════════════════"
