#!/usr/bin/env bash
# server.sh — spustí statistiky-server (server.py) na pozadí, bind 0.0.0.0.
# Použití: ./server.sh [port]   (default 8000)
#
# Bind 0.0.0.0 = poslouchá na všech rozhraních → kdokoli na stejné síti
# ho uvidí na své IP. Do prohlížeče/curl patří skutečná IP, nikdy 0.0.0.0.
#
# POZOR: server nemá autentizaci a umí spouštět pi agenta s bash přístupem.
# Používej jen v důvěryhodné síti (Wi-Fi/hotspot), nikdy ho nevystavuj
# do internetu bez reverzní proxy s autentizací.

PORT="${1:-8000}"
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1

# načti klíče (ODDS_API_KEY, LIVE_TENNIS_API_KEY, BOOKMAKER...) pokud existují
[ -f "$HOME/.env" ] && source "$HOME/.env"

# najdi síťové IPv4 (vynech loopback a mobilní rmnet)
LAN_IPS="$(ip -4 addr show 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 \
  | grep -v '^127\.' | grep -v '^10\.67\.' | grep -v '^10\.49\.')"
if [ -z "$LAN_IPS" ]; then
  LAN_IPS="$(hostname -I 2>/dev/null | tr ' ' '\n' \
    | grep -v '^127\.' | grep -v '^10\.67\.' | grep -v '^10\.49\.' | grep -v '^$')"
fi

pkill -f "server.py" 2>/dev/null
sleep 0.3

setsid nohup env SPORTS_PORT="$PORT" python3 server.py >"/tmp/statistiky-server-$PORT.log" 2>&1 &
sleep 1.5

echo "═══════════════════════════════════════════════════"
echo "  statistiky-server"
echo "═══════════════════════════════════════════════════"
echo "  složka: $DIR"
echo "  port:   $PORT"
echo
echo "  Na tomto zařízení:  http://localhost:$PORT/health"
echo
if curl -s -m 3 -o /dev/null "http://127.0.0.1:$PORT/health"; then
  echo "  ✔ Server běží."
  echo
  if [ -n "$LAN_IPS" ]; then
    echo "  Ostatní na stejné síti otevřou:"
    for ip in $LAN_IPS; do echo "      http://$ip:$PORT/health"; done
  else
    echo "  ⚠ Žádná síťová IP — Wi-Fi/hotspot je vypnutý, nebo ho guest nevidí."
  fi
else
  echo "  ✘ Server se nespustil:"; cat "/tmp/statistiky-server-$PORT.log" 2>/dev/null; exit 1
fi
echo
echo "  Zastavit: pkill -f 'server.py'   Log: /tmp/statistiky-server-$PORT.log"
echo "  POZOR: běží bez autentizace, kdokoli na síti ho uvidí."
echo "═══════════════════════════════════════════════════"