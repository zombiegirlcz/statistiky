import sys
sys.path.insert(0, "/root/statistiky/.agents/skills/match-probability/scripts")
import bet_evaluator as ev
FAILS=[]
def chk(n,c,d=""):
    print(f"  [{'OK ' if c else 'FAIL'}] {n}"+(f"  {d}" if d else ""));
    if not c: FAILS.append(n)
def ent(pick): return {"match_id":1,"market_kind":"builder","player1":"A","player2":"B","pick":pick,"odds":2.5,"stake":20,"status":"pending"}
def mk(status,winner,g1,g2):
    return {"id":1,"status":status,"winner":winner,"players":{"p1":{"name":"A"},"p2":{"name":"B"}},"score":{"sets":[2,0],"games":[[g1,6],[g2,4]]}}

print("1) A vyhral zapas I 1.set -> won")
e=ent("A"); chk("True",ev._settle_builder_entry(e,mk("completed",1,6,4)) is True); chk("won",e["status"]=="won",e["status"])
print("2) A vyhral zapas, ale 1.set vyhral B -> lost")
e=ent("A"); ev._settle_builder_entry(e,mk("completed",1,4,6)); chk("lost",e["status"]=="lost",e["status"])
print("3) zapas neni dohrany -> False")
e=ent("A"); chk("False",ev._settle_builder_entry(e,mk("live",None,6,4)) is False); chk("pending",e["status"]=="pending")
print("4) B vyhral obe nohy -> won (pick B)")
e=ent("B"); ev._settle_builder_entry(e,mk("completed",2,4,6)); chk("won",e["status"]=="won",e["status"])
print()
print("VYSLEDEK:","vse OK" if not FAILS else f"{len(FAILS)} selhani {FAILS}")
sys.exit(1 if FAILS else 0)
