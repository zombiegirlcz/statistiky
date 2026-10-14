#!/usr/bin/env python3
"""Izolovany test pro _settle_completed v live_game_bet.py.

Mockuje base.fetch_match, takze nepotrebuje LIVE_TENNIS_API_KEY ani sit.
Overuje tri scenare:
  1) dokonceny zapas, vitez == pick        -> won
  2) dokonceny zapas, vitez != pick        -> lost
  3) dokonceny zapas, chybi 'winner'       -> void
  4) nedokonceny zapas                     -> False, status zustava pending
  5) fetch_match vyhodi SystemExit (401)   -> False, status zustava pending
"""
import sys

sys.path.insert(0, "/root/statistiky/.agents/skills/match-probability/scripts")
import live_game_bet as lgb  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def make_entry(pick):
    return {
        "match_id": 999999,
        "player1": "Player One",
        "player2": "Player Two",
        "pick": pick,
        "odds": 1.30,
        "model_p": 0.80,
        "score_at_bet": "sety 0:0, gemy 0:0, body 0:0",
        "state_at_bet": {"sets": [0, 0], "games": [0, 0], "between_sets": False},
        "stake": 1411,
        "status": "pending",
    }


def mock_match(status, winner=None, p1="Player One", p2="Player Two"):
    m = {
        "id": 999999,
        "status": status,
        "players": {"p1": {"name": p1}, "p2": {"name": p2}},
        "score": {"sets": [1, 0], "games": [[6, 0], [4, 0]], "points": ["0", "0"],
                  "server": 1, "is_tiebreak": False},
        "format": "BO3",
    }
    if winner is not None:
        m["winner"] = winner
    return m


# ---------------------------------------------------------------------------
print("1) dokonceny zapas, vitez == pick -> won")
entry = make_entry("Player One")
lgb.base.fetch_match = lambda mid: mock_match("completed", winner=1)
res = lgb._settle_completed(entry)
check("vraci True", res is True)
check("status == won", entry["status"] == "won", entry["status"])
check("actual_winner", entry.get("actual_winner") == "Player One", str(entry.get("actual_winner")))
check("resolved_at vyplneno", bool(entry.get("resolved_at")))

print("2) dokonceny zapas, vitez != pick -> lost")
entry = make_entry("Player One")
lgb.base.fetch_match = lambda mid: mock_match("completed", winner=2)
res = lgb._settle_completed(entry)
check("vraci True", res is True)
check("status == lost", entry["status"] == "lost", entry["status"])
check("actual_winner == Player Two", entry.get("actual_winner") == "Player Two", str(entry.get("actual_winner")))

print("3) dokonceny zapas bez viteze -> void")
entry = make_entry("Player One")
lgb.base.fetch_match = lambda mid: mock_match("completed", winner=None)
res = lgb._settle_completed(entry)
check("vraci True", res is True)
check("status == void", entry["status"] == "void", entry["status"])
check("void_reason vyplneno", bool(entry.get("void_reason")), str(entry.get("void_reason")))

print("4) nedokonceny zapas -> False, zustava pending")
entry = make_entry("Player One")
lgb.base.fetch_match = lambda mid: mock_match("live", winner=None)
res = lgb._settle_completed(entry)
check("vraci False", res is False)
check("status zustava pending", entry["status"] == "pending", entry["status"])

print("5) fetch_match vyhodi SystemExit (401) -> False, zustava pending")
entry = make_entry("Player One")

def boom(mid):
    raise SystemExit(1)

lgb.base.fetch_match = boom
res = lgb._settle_completed(entry)
check("vraci False", res is False)
check("status zustava pending", entry["status"] == "pending", entry["status"])

print()
if FAILS:
    print(f"VYSLEDEK: {len(FAILS)} selhani: {FAILS}")
    sys.exit(1)
print("VYSLEDEK: vsechny testy prosly")
