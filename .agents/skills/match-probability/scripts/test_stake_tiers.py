import sys
sys.path.insert(0, "/root/statistiky/.agents/skills/match-probability/scripts")
import live_tennis_simulator as s

FAILS=[]
def chk(n,c,d=""):
    print(f"  [{'OK ' if c else 'FAIL'}] {n}"+(f"  {d}" if d else ""));  FAILS.append(n) if not c else None

print("1) tutovka (model .95, trh .95, kurz 1.03) -> all-in")
log=[{"status":"won","stake":1000,"odds":1.1}]  # banka ~1100
pct,tier = s.stake_tier(0.95,0.95,1.03)
chk("pct=1.0", pct==1.0, str(pct)); chk("tier TUTOVKA", "TUTOVKA" in tier, tier)
stake,reason = s.next_stake(log, 0.95,0.95,1.03)
chk("stake = cela banka", stake==s.current_bank(log), f"{stake} vs {s.current_bank(log)}")

print("2) silny favorit (model .88, trh .85, kurz 1.20) -> 10%")
pct,tier = s.stake_tier(0.88,0.85,1.20)
chk("pct=0.10", pct==0.10, str(pct))

print("3) standard (model .80, trh .70, kurz 1.50) -> 2%")
pct,tier = s.stake_tier(0.80,0.70,1.50)
chk("pct=0.02", pct==s.STAKE_PCT, str(pct))

print("4) skoro-tutovka ale vysoky kurz (model .95,trh .95,kurz 1.30) NENI all-in")
pct,tier = s.stake_tier(0.95,0.95,1.30)
chk("pct != 1.0", pct!=1.0, str(pct))

print("5) model vysoky, trh nizky -> ne all-in")
pct,tier = s.stake_tier(0.95,0.70,1.03)
chk("neni all-in", pct!=1.0, str(pct))

print()
print("VYSLEDEK:", "vse OK" if not FAILS else f"{len(FAILS)} selhani {FAILS}")
sys.exit(1 if FAILS else 0)
