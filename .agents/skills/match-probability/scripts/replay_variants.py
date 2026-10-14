import csv, os, sys
sys.path.insert(0, "/root/statistiky/.agents/skills/match-probability/scripts")
import tennis_value_backtest as tv
import live_tennis_simulator as sim

sack = tv.load_sackmann_wta()
odds = list(csv.DictReader(open(tv.ODDS_PATH, encoding="utf-8")))
joined = tv.join_matches(sack, odds)
joined.sort(key=lambda m: m["cutoff"])
hist = tv.History(sack)

def run(mode):
    bank=1000.0; start=bank; peak=bank; n=w=0; st=ret=0.0
    for m in joined:
        p1,n1,n2 = tv.model_prob(hist,m["name1"],m["name2"],m["cutoff"])
        if p1 is None or n1<15 or n2<15: continue
        o1,o2=m["odd1"],m["odd2"]
        if not (tv.ODDS_MIN<=o1<=tv.ODDS_MAX and tv.ODDS_MIN<=o2<=tv.ODDS_MAX): continue
        pm1,pm2,_=tv.devig(o1,o2)
        cands=[(m["name1"],p1,pm1,o1,m["p1_won"]),(m["name2"],1-p1,pm2,o2,not m["p1_won"])]
        pick=None
        for name,pmd,pmo,od,won in cands:
            if mode=="model+market": ok = pmd>=sim.FAV_MODEL_MIN and pmo>=sim.FAV_MARKET_MIN and od<=sim.FAV_MAX_ODDS
            elif mode=="market-only": ok = pmo>=sim.FAV_MARKET_MIN and od<=sim.FAV_MAX_ODDS
            elif mode=="model-only": ok = pmd>=sim.FAV_MODEL_MIN and od<=sim.FAV_MAX_ODDS
            if ok: pick=(name,pmd,pmo,od,won); break
        if not pick: continue
        name,pmd,pmo,od,won=pick
        pct,tier=sim.stake_tier(pmd,pmo,od)
        stake=round(bank*pct)
        if stake<sim.MIN_STAKE or stake>bank: continue
        n+=1; st+=stake
        if won: w+=1; ret+=stake*od; bank+=stake*(od-1)
        else: bank-=stake
        peak=max(peak,bank)
        if bank<sim.MIN_STAKE: break
    roi=(ret-st)/st*100 if st else 0
    print(f"{mode:14s}: {n:4d} sazek | uspesnost {100.0*w/n:5.1f}% | ROI {roi:+6.1f}% | banka {bank:6.0f} (start 1000)")

print("=== srovnani filtoru (stejny harness, banka 1000) ===")
run("model+market")
run("market-only")
run("model-only")
