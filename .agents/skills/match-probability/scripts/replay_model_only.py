import csv, sys
sys.path.insert(0, "/root/statistiky/.agents/skills/match-probability/scripts")
import tennis_value_backtest as tv
import live_tennis_simulator as sim

sack = tv.load_sackmann_wta()
odds = list(csv.DictReader(open(tv.ODDS_PATH, encoding="utf-8")))
joined = tv.join_matches(sack, odds)
joined.sort(key=lambda m: m["cutoff"])
hist = tv.History(sack)

def run(allow_dog, bank0=1000.0, dog_min=0.55):
    bank=bank0; peak=bank; n=w=0; st=ret=0.0
    n_fav=n_dog=0; busted=None
    for m in joined:
        p1,n1,n2 = tv.model_prob(hist,m["name1"],m["name2"],m["cutoff"])
        if p1 is None or n1<15 or n2<15: continue
        o1,o2=m["odd1"],m["odd2"]
        if not (tv.ODDS_MIN<=o1<=tv.ODDS_MAX and tv.ODDS_MIN<=o2<=tv.ODDS_MAX): continue
        pm1,pm2,_=tv.devig(o1,o2)
        # model si vybere stranu, ktere veri vic (bez trhu)
        if p1>=0.5: name,pmod,od,won,pmkt = m["name1"],p1,o1,m["p1_won"],pm1
        else: name,pmod,od,won,pmkt = m["name2"],1-p1,o2,not m["p1_won"],pm2
        is_dog = pmkt < 0.5
        if is_dog and not allow_dog: continue
        need = dog_min if is_dog else sim.MODEL_ONLY_MIN
        if pmod < need: continue
        if is_dog: n_dog+=1
        else: n_fav+=1
        # stupnovane sazeni: bez trhu -> jako 'market' pouzij model
        pct,tier = sim.stake_tier(pmod, pmod, od)
        stake=round(bank*pct)
        if stake<sim.MIN_STAKE or stake>bank: continue
        n+=1; st+=stake
        if won: w+=1; ret+=stake*od; bank+=stake*(od-1)
        else: bank-=stake
        peak=max(peak,bank)
        if bank<sim.MIN_STAKE: busted=m["date"]; break
    roi=(ret-st)/st*100 if st else 0
    print(f"dog={allow_dog:d}: {n:4d} sazek (fav {n_fav}, dog {n_dog}) | "
          f"uspesnost {100.0*w/n if n else 0:5.1f}% | ROI {roi:+6.1f}% | "
          f"banka {bank:6.0f} (vrchol {peak:.0f})" + (f" | BUST {busted}" if busted else ""))

print("=== MODEL-ONLY (presne jako cmd_model_watch, stroj casu) ===")
print("-- bez underdogu --")
run(False)
print("-- vcetne underdogu (dog_min=0.55) --")
run(True)
