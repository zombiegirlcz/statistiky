#!/usr/bin/env python3
"""
Denni aktualizace sportovnich statistik v /statistiky.

Na rozdil od puvodniho jednorazoveho sberu (ktery stahl 5 kompletnich
historickych sezon) tenhle skript resi jen PRIRUSTEK: stahne/dopocita
jen to, co se zmenilo od posledniho spusteni - aktualni sezonu/rok u
kazdeho sportu - a historicke, uz uzavrene sezony vubec nesaha.

Pouziti:
    python3 update_stats.py            # aktualizuje vse (fotbal, tenis, hokej)
    python3 update_stats.py fotbal     # jen jeden sport
"""
import csv
import glob
import os
import subprocess
import sys
import time
from datetime import date, datetime

import requests

import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

BASE = os.environ.get("STATISTIKY_BASE") or (
    "/root/statistiky" if os.path.exists("/root/statistiky") else REPO_ROOT
)
UA = "Mozilla/5.0 (StatistikyBot update tool)"
S = requests.Session()
S.headers.update({"User-Agent": UA})
LOG_PATH = os.path.join(BASE, "_update_log.txt")
MARKITDOWN = shutil.which("markitdown") or "/root/markitdown/.venv/bin/markitdown"
MARKITDOWN_PY = sys.executable

_log_lines = []


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    _log_lines.append(line)


def get(url, **kw):
    for attempt in range(4):
        try:
            r = S.get(url, timeout=20, **kw)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            return r
        except requests.RequestException as e:
            log(f"  chyba site ({url}): {e}, zkouska {attempt+1}/4")
            time.sleep(1.5 * (attempt + 1))
    return None


def count_lines(path):
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as f:
        return sum(1 for _ in f)


# ---------------------------------------------------------------------------
# FOTBAL - aktualni sezona se jednoduse prepise cerstvym CSV ze zdroje
# ---------------------------------------------------------------------------
LEAGUES = {
    "E0": "Anglie - Premier League", "E1": "Anglie - Championship",
    "E2": "Anglie - League One", "E3": "Anglie - League Two",
    "EC": "Anglie - National League",
    "SC0": "Skotsko - Premiership", "SC1": "Skotsko - Championship",
    "SC2": "Skotsko - League One", "SC3": "Skotsko - League Two",
    "D1": "Nemecko - Bundesliga", "D2": "Nemecko - 2. Bundesliga",
    "I1": "Italie - Serie A", "I2": "Italie - Serie B",
    "SP1": "Spanelsko - La Liga", "SP2": "Spanelsko - Segunda Division",
    "F1": "Francie - Ligue 1", "F2": "Francie - Ligue 2",
    "N1": "Nizozemsko - Eredivisie", "B1": "Belgie - Jupiler Pro League",
    "P1": "Portugalsko - Primeira Liga", "T1": "Turecko - Super Lig",
    "G1": "Recko - Super League",
}


def current_football_season(today):
    # evropska sezona bezi cca srpen-kveten; do konce cervence pocitame
    # jeste predchozi sezonu jako "aktualni" (prestupove okno, zadne zapasy)
    start_year = today.year if today.month >= 7 else today.year - 1
    code = f"{str(start_year)[2:]}{str(start_year + 1)[2:]}"
    label = f"{start_year}-{str(start_year + 1)[2:]}"
    return code, label


def update_football():
    today = date.today()
    season_code, season_label = current_football_season(today)
    prev_start = (today.year - 1 if today.month >= 7 else today.year - 2)
    prev_code = f"{str(prev_start)[2:]}{str(prev_start + 1)[2:]}"
    prev_label = f"{prev_start}-{str(prev_start + 1)[2:]}"

    outdir = os.path.join(BASE, "fotbal")
    changed = []
    for code, name in LEAGUES.items():
        slug = name.replace(" ", "_").replace("/", "-")
        path = os.path.join(outdir, f"{season_label}_{code}_{slug}.csv")
        old_lines = count_lines(path)

        r = get(f"https://www.football-data.co.uk/mmz4281/{season_code}/{code}.csv")
        use_season, use_label = season_code, season_label
        if r is None or r.status_code != 200 or len(r.content) < 50:
            # nova sezona jeste nezacala - zkus minulou (porad "aktualni")
            path = os.path.join(outdir, f"{prev_label}_{code}_{slug}.csv")
            old_lines = count_lines(path)
            r = get(f"https://www.football-data.co.uk/mmz4281/{prev_code}/{code}.csv")
            use_season, use_label = prev_code, prev_label
        if r is None or r.status_code != 200 or len(r.content) < 50:
            log(f"  [fotbal] {code}: nepodarilo se stahnout ani aktualni, ani minulou sezonu")
            continue

        with open(path, "wb") as f:
            f.write(r.content)
        new_lines = count_lines(path)
        if new_lines != old_lines:
            changed.append(path)
            log(f"  [fotbal] {name} ({use_label}): {old_lines} -> {new_lines} radku (+{new_lines - old_lines})")
    if not changed:
        log("[fotbal] zadne nove zapasy, vse aktualni")
    return changed


# ---------------------------------------------------------------------------
# TENIS - aktualni rok se prepise cerstvym CSV z archivu
# ---------------------------------------------------------------------------
def update_tennis():
    today = date.today()
    outdir = os.path.join(BASE, "tenis")
    changed = []
    for year in (today.year - 1, today.year, today.year + 1):
        for tour in ("atp", "wta"):
            path = os.path.join(outdir, f"{tour}_matches_{year}.csv")
            old_lines = count_lines(path)
            url = f"https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/{tour}/{tour}_matches_{year}.csv"
            r = get(url)
            if r is None or r.status_code != 200 or len(r.content) < 50:
                continue  # rok jeste neexistuje (napr. budouci) nebo vypadl - v poradku, preskoc
            with open(path, "wb") as f:
                f.write(r.content)
            new_lines = count_lines(path)
            if new_lines != old_lines:
                changed.append(path)
                log(f"  [tenis] {tour.upper()} {year}: {old_lines} -> {new_lines} radku (+{new_lines - old_lines})")
    if not changed:
        log("[tenis] zadne nove zapasy, vse aktualni")
    return changed


# ---------------------------------------------------------------------------
# HOKEJ - NHL, pridava jen zapasy, ktere jeste v CSV nejsou (resume logika)
# ---------------------------------------------------------------------------
STAT_FIELDS = [
    "sog", "faceoffWinningPctg", "powerPlay", "powerPlayPctg",
    "pim", "hits", "blockedShots", "giveaways", "takeaways",
]
CSV_FIELDNAMES = (
    ["game_id", "date", "gameType", "away_team", "home_team", "away_score", "home_score"]
    + [f"away_{f}" for f in STAT_FIELDS] + [f"home_{f}" for f in STAT_FIELDS]
)


def current_nhl_season(today):
    # NHL sezona bezi cca rijen-cerven
    return today.year if today.month >= 8 else today.year - 1


def nhl_week(date_str):
    r = get(f"https://api-web.nhle.com/v1/schedule/{date_str}")
    if r is None or r.status_code != 200:
        return None
    return r.json()


def load_existing_game_ids(path):
    ids = set()
    if not os.path.exists(path):
        return ids
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ids.add(int(row["game_id"]))
    return ids


def update_hockey():
    today = date.today()
    start_year = current_nhl_season(today)
    season_label = f"{start_year}-{start_year + 1}"
    outdir = os.path.join(BASE, "hokej")
    out_path = os.path.join(outdir, f"NHL_{season_label}.csv")

    already = load_existing_game_ids(out_path)
    file_exists = os.path.exists(out_path)

    probe = nhl_week(today.strftime("%Y-%m-%d"))
    if not probe:
        log(f"[hokej] nelze ziskat rozpis sezony {season_label} (NHL API nedostupne nebo sezona jeste nezacala)")
        return []
    reg_start = probe.get("regularSeasonStartDate")
    reg_end = probe.get("regularSeasonEndDate")
    playoff_end = probe.get("playoffEndDate")
    if not reg_start or today.strftime("%Y-%m-%d") < reg_start:
        log(f"[hokej] sezona {season_label} jeste nezacala ({reg_start})")
        return []
    end_date = playoff_end or reg_end or today.strftime("%Y-%m-%d")
    # neprohledavej do budoucna za dnesek
    end_date = min(end_date, today.strftime("%Y-%m-%d"))

    game_ids = {}
    cur = reg_start
    seen_weeks = set()
    while cur and cur not in seen_weeks and cur <= end_date:
        seen_weeks.add(cur)
        wk = nhl_week(cur)
        if not wk:
            break
        for day in wk.get("gameWeek", []):
            for g in day.get("games", []):
                if g.get("gameState") in ("OFF", "FINAL") and g.get("gameType") in (2, 3):
                    game_ids[g["id"]] = {
                        "date": day.get("date"), "gameType": g.get("gameType"),
                        "away": g.get("awayTeam", {}).get("abbrev"),
                        "home": g.get("homeTeam", {}).get("abbrev"),
                        "awayScore": g.get("awayTeam", {}).get("score"),
                        "homeScore": g.get("homeTeam", {}).get("score"),
                    }
        nxt = wk.get("nextStartDate")
        if not nxt or nxt <= cur or nxt > end_date:
            break
        cur = nxt

    remaining = {gid: meta for gid, meta in game_ids.items() if gid not in already}
    if not remaining:
        log(f"[hokej] {season_label}: zadne nove zapasy (celkem {len(game_ids)}, uz mame {len(already)})")
        return []

    log(f"[hokej] {season_label}: {len(remaining)} novych zapasu k dostazeni (z {len(game_ids)} celkem)")
    with open(out_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        if not file_exists or os.path.getsize(out_path) == 0:
            w.writeheader()
        for gid, meta in sorted(remaining.items()):
            r = get(f"https://api-web.nhle.com/v1/gamecenter/{gid}/right-rail")
            stats = {}
            if r is not None and r.status_code == 200:
                for cat in r.json().get("teamGameStats", []) or []:
                    stats[cat["category"]] = cat
            row = {
                "game_id": gid, "date": meta["date"],
                "gameType": "regular" if meta["gameType"] == 2 else "playoffs",
                "away_team": meta["away"], "home_team": meta["home"],
                "away_score": meta["awayScore"], "home_score": meta["homeScore"],
            }
            for field in STAT_FIELDS:
                c = stats.get(field, {})
                row[f"away_{field}"] = c.get("awayValue", "")
                row[f"home_{field}"] = c.get("homeValue", "")
            w.writerow(row)
            f.flush()
    log(f"[hokej] {season_label}: pridano {len(remaining)} zapasu")
    return [out_path]


# ---------------------------------------------------------------------------
# MARKITDOWN - prevede jen soubory, ktere se skutecne zmenily
# ---------------------------------------------------------------------------
def reconvert(changed_csv_paths):
    for csv_path in changed_csv_paths:
        md_path = csv_path[:-4] + ".md"
        result = subprocess.run(
            [MARKITDOWN, csv_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if result.returncode == 0 and len(result.stdout) > 0:
            with open(md_path, "wb") as f:
                f.write(result.stdout)
        else:
            # fallback na Python API s explicitnim utf-8 (viz znama chyba
            # markitdown s automatickou detekci kodovani u souboru s diakritikou)
            code = (
                "from markitdown import MarkItDown, StreamInfo\n"
                "md = MarkItDown()\n"
                f"with open({csv_path!r}, 'rb') as f:\n"
                "    r = md.convert_stream(f, stream_info=StreamInfo(extension='.csv', charset='utf-8'))\n"
                f"open({md_path!r}, 'w', encoding='utf-8').write(r.text_content)\n"
            )
            subprocess.run([MARKITDOWN_PY, "-c", code], check=False)
        log(f"  [markitdown] prevedeno: {os.path.basename(md_path)}")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    log(f"=== DENNI AKTUALIZACE ({date.today().isoformat()}) ===")
    changed = []
    if only in ("all", "fotbal"):
        changed += update_football()
    if only in ("all", "tenis"):
        changed += update_tennis()
    if only in ("all", "hokej"):
        changed += update_hockey()

    if changed:
        log(f"Prevadim {len(changed)} zmenenych souboru do Markdownu...")
        reconvert(changed)
    log(f"=== HOTOVO: {len(changed)} souboru zmeneno ===")

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n--- {datetime.now().isoformat()} ---\n")
        f.write("\n".join(_log_lines) + "\n")


if __name__ == "__main__":
    main()
