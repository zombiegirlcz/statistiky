#!/usr/bin/env python3
"""Sonda: jaká pole vrací živé Live Tennis API u nadcházejících zápasů?

CÍL (priorita 1 z deníku 2026-10-07): zjistit, zda z `round_code` + `tier`
dokážeme odvodit POŘADÍ KOLA (kvůli strategii "2. kolo favorit"), nebo zda
API dává i velikost pavouka (draw size) / počet hráčů.

Spuštění:
  cd scripts && source ~/.env
  python3 _probe_live_fields.py

Nic nezapisuje do agents.json. Jen čte API a vypisuje strukturu.
"""
import json
import sys
import urllib.parse
import urllib.request

BASE = "https://api.livetennisapi.com/api/public/v1"


def api_keys():
    import os
    raw = (os.environ.get("LIVE_TENNIS_API_KEYS")
           or os.environ.get("LIVE_TENNIS_API_KEY") or "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def get(path, params=None):
    keys = api_keys()
    if not keys:
        print("CHYBA: chybí LIVE_TENNIS_API_KEYS (source ~/.env)")
        sys.exit(1)
    q = urllib.parse.urlencode(params or {})
    url = f"{BASE}{path}" + (f"?{q}" if q else "")
    last = None
    for k in keys:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {k}"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
            continue
        except Exception as e:
            last = str(e)
            continue
    print("CHYBA všech klíčů:", last)
    sys.exit(1)


def dump_keys(label, obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                t = type(v).__name__
                n = len(v)
                print(f"    {prefix}{k}: {t}[{n}]")
                if isinstance(v, dict) and prefix.count(".") < 2:
                    dump_keys(label, v, prefix + k + ".")
            else:
                print(f"    {prefix}{k} = {v!r}")


def main():
    print("=" * 70)
    print("NADHÁZEJÍCÍ ZÁPASY (status=upcoming, limit=100)")
    print("=" * 70)
    data = get("/matches", {"status": "upcoming", "limit": 100})
    matches = data.get("data", [])
    print(f"počet zápasů: {len(matches)}")
    if not matches:
        print("žádné nadcházející zápasy - zkus později")
        return

    print("\n--- PRVNÍCH 5 ZÁPASŮ: VŠECHNA POLE (klíč = hodnota) ---")
    for i, m in enumerate(matches[:5]):
        print(f"\n[{i}] match id={m.get('id')}")
        dump_keys("m", m)

    print("\n" + "=" * 70)
    print("ANALÝZA: round_code + tier + hledání draw size")
    print("=" * 70)
    round_codes = {}
    tiers = {}
    draw_like = {}
    for m in matches:
        rc = m.get("round_code")
        t = m.get("tier")
        round_codes[rc] = round_codes.get(rc, 0) + 1
        tiers[t] = tiers.get(t, 0) + 1
        # hledej pole, která by mohla znamenat velikost pavouka
        for k, v in m.items():
            kl = k.lower()
            if any(s in kl for s in ("draw", "size", "players", "entr", "field", "bracket", "round")):
                draw_like.setdefault(k, set()).add(str(v))

    print("\nround_code -> počet:")
    for k, v in sorted(round_codes.items(), key=lambda x: -x[1]):
        print(f"  {k!r}: {v}")
    print("\ntier -> počet:")
    for k, v in sorted(tiers.items(), key=lambda x: -x[1]):
        print(f"  {k!r}: {v}")
    print("\npole s 'draw/size/players/round...' -> unikátní hodnoty:")
    for k, vals in sorted(draw_like.items()):
        shown = sorted(vals)[:15]
        print(f"  {k}: {shown}{' ...' if len(vals) > 15 else ''}")

    # Zkus detail turnaje - obsahuje draw size?
    tids = sorted({m.get("tournament_id") for m in matches if m.get("tournament_id")})
    print(f"\nunikátní tournament_id: {len(tids)}")
    for tid in tids[:3]:
        print(f"\n--- /tournaments/{tid} ---")
        try:
            td = get(f"/tournaments/{tid}")
            dump_keys("t", td)
        except SystemExit:
            pass

    # Zkus i zápas detail (může mít round/draw info)
    print(f"\n--- /matches/{matches[0].get('id')} (detail) ---")
    try:
        md = get(f"/matches/{matches[0].get('id')}")
        dump_keys("m", md)
    except SystemExit:
        pass


if __name__ == "__main__":
    main()