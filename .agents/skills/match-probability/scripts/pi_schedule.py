#!/usr/bin/env python3
"""pi_schedule.py - planovac behu podle toho, KDY se hraji zapasy.

PROC: pevny cron cas (napr. 15:45) nesedi - zapasy se hraji v ruznych
casovych pasmech a dnech. Tenhle skript z kalendare zapasu (Live Tennis
API, /matches?status=upcoming + status=live) spocita, jestli se ZROVU neco
deje nebo brzy zacne, a podle toho rozhodne, zda ma smysl se vubec
probouzet. Diky cache spotrebuje minimum API kvoty (100/den).

POUZITI (a exit kody):
  python3 pi_schedule.py active   # 0 = aktivni okno (bezi zapasy), 3 = klid
  python3 pi_schedule.py next     # lidsky citelny plan (kdy priste, proc)
  python3 pi_schedule.py refresh  # vynuti novy dotaz na API a prepise cache

Cache: pi_schedule.json (vedle skriptu). Obnovi se jen kdyz je starsi nez
STALE_SEC nebo kdyz vyprsela aktivni okno - jinak se cte z disku (0 API).
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(_SCRIPT_DIR, "pi_schedule.json")

API_BASE = "https://api.livetennisapi.com/api/public/v1"
STALE_SEC = 2 * 3600          # cache se povazuje za starou po 2 h
LOOKAHEAD_MIN = 30            # zapas do 30 min = aktivni okno
FAR_HORIZON_MIN = 6 * 3600 // 60  # jak daleko dopredu jeste resime cas


def _api_key():
    raw = (os.environ.get("LIVE_TENNIS_API_KEYS")
           or os.environ.get("LIVE_TENNIS_API_KEY") or "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def _get(path):
    keys = _api_key()
    if not keys:
        return None
    req = urllib.request.Request(API_BASE + path,
                                 headers={"Authorization": f"Bearer {keys[0]}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def refresh():
    """1-2 volani API: stahne zive + nejblizsi nadchazejici zapasy, zapise cache."""
    live = _get("/matches?status=live&limit=100")
    upcoming = _get("/matches?status=upcoming&limit=100")
    if live is None and upcoming is None:
        return None  # API nedostupne - cache nech byt
    live_n = len((live or {}).get("data", []))
    starts = []
    for m in (upcoming or {}).get("data", []):
        t = _parse_iso(m.get("scheduled_time"))
        if t is not None:
            starts.append(t.astimezone(timezone.utc).isoformat())
    starts.sort()
    cache = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "live_count": live_n,
        "upcoming_starts": starts,
    }
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return cache


def load_cache(force=False):
    if not force:
        try:
            with open(CACHE, encoding="utf-8") as f:
                c = json.load(f)
            age = time.time() - _parse_iso(c["refreshed_at"]).timestamp()
            if age < STALE_SEC:
                return c
        except Exception:
            pass
    return refresh()


def decide(cache):
    """Vrati (active: bool, reason: str, next_dt: datetime|None)."""
    now = datetime.now(timezone.utc)
    if cache is None:
        return False, "bez cache (API nedostupne)", None
    if cache.get("live_count", 0) > 0:
        return True, f"{cache['live_count']} zivych zapasu", now + timedelta(minutes=15)
    nxt = None
    for s in cache.get("upcoming_starts", []):
        t = _parse_iso(s)
        if t and t >= now - timedelta(minutes=5):
            nxt = t
            break
    if nxt is None:
        return False, "zadny dalsi zapas v kalendari", None
    mins = (nxt - now).total_seconds() / 60.0
    if mins <= LOOKAHEAD_MIN:
        return True, f"zapas zacina za {mins:.0f} min", now + timedelta(minutes=15)
    if mins <= FAR_HORIZON_MIN:
        return False, f"klid, dalsi zapas {nxt.isoformat()}", nxt - timedelta(minutes=10)
    return False, f"klid (dalsi zapas dal nez {FAR_HORIZON_MIN//60} h)", now + timedelta(hours=2)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "next"
    cache = load_cache(force=(mode == "refresh"))
    active, reason, nxt = decide(cache)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    if mode == "active":
        if active:
            print(f"[{ts}] ACTIVE - {reason}")
            sys.exit(0)
        print(f"[{ts}] QUIET - {reason}")
        sys.exit(3)
    print(f"[{ts}] {'ACTIVE' if active else 'QUIET'} - {reason}")
    print(f"  pristi beh: {nxt.isoformat() if nxt else '(nezname)'}")
    if cache:
        print(f"  zivych: {cache.get('live_count', 0)}, "
              f"nadchazejicich v cache: {len(cache.get('upcoming_starts', []))}")
    sys.exit(0)


if __name__ == "__main__":
    main()
