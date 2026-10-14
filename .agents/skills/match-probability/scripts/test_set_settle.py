import sys
sys.path.insert(0, "/root/statistiky/.agents/skills/match-probability/scripts")
import bet_evaluator as ev

FAILS = []
def check(name, cond, detail=""):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)

def entry(pick, set_no=1):
    return {"match_id": 1, "market_kind": "set", "set_no": set_no,
            "player1": "A", "player2": "B", "pick": pick,
            "odds": 1.5, "stake": 10, "status": "pending"}

def match(sets, games, winner=None):
    m = {"id": 1, "status": "completed",
         "players": {"p1": {"name": "A"}, "p2": {"name": "B"}},
         "score": {"sets": sets, "games": games}}
    if winner is not None:
        m["winner"] = winner
    return m

print("1) set 1 dohrany, A vyhral 6:4 -> won")
e = entry("A", 1)
check("True", ev._settle_set_entry(e, match([1,0], [[6,0],[4,0]])) is True)
check("won", e["status"] == "won", e["status"])

print("2) set 1 dohrany, B vyhral 4:6 -> lost")
e = entry("A", 1)
ev._settle_set_entry(e, match([0,1], [[4],[6]]))
check("lost", e["status"] == "lost", e["status"])

print("3) set 2, A vyhral druhy set -> won")
e = entry("A", 2)
ev._settle_set_entry(e, match([1,1], [[6,6],[4,3]]))
check("won", e["status"] == "won", e["status"])

print("4) set 2 jeste neni dohrany (completed=1 < 2) -> False, zustava pending")
e = entry("A", 2)
check("False", ev._settle_set_entry(e, match([1,0], [[6],[4]])) is False)
check("pending", e["status"] == "pending", e["status"])

print("5) nerozhodny set (6:6 v datech) -> False")
e = entry("A", 1)
check("False", ev._settle_set_entry(e, match([0,0], [[6],[6]])) is False)

print()
if FAILS:
    print(f"VYSLEDEK: {len(FAILS)} selhani: {FAILS}"); sys.exit(1)
print("VYSLEDEK: vsechny testy prosly")
