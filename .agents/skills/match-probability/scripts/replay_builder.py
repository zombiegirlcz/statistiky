import csv, re, sys
sys.path.insert(0, "/root/statistiky/.agents/skills/match-probability/scripts")
import tennis_value_backtest as tv
K=0.7; MARG=0.05
sack=tv.load_sackmann_wta()
odds=list(csv.DictReader(open(tv.ODDS_PATH,encoding="utf-8")))
joined=tv.join_matches(sack,odds); joined.sort(key=lambda m:m["cutoff"])
hist=tv.History(sack)
sbk={}
for r in odds:
    try: k=(r["Date"],round(float(r["Odd_1"]),2),round(float(r["Odd_2"]),2))
    except: continue
    sbk.setdefault(k,r.get("Score",""))
def s1w(score,n1,n2,mw):
    m=re.match(r"\s*(\d+)-(\d+)",score or "")
    if not m: return None
    a,b=int(m.group(1)),int(m.group(2))
    if a==b: return None
    loser=n2 if mw==n1 else n1
    return mw if a>b else loser
def run(solo):
    bank=1000.0; peak=1000.0; n=w=0; st=ret=0.0
    for m in joined:
        p1,n1,n2=tv.model_prob(hist,m["name1"],m["name2"],m["cutoff"])
        if p1 is None or n1<15 or n2<15: continue
        o1,o2=m["odd1"],m["odd2"]
        if not(tv.ODDS_MIN<=o1<=tv.ODDS_MAX and tv.ODDS_MIN<=o2<=tv.ODDS_MAX): continue
        pm1,pm2,_=tv.devig(o1,o2)
        fav=m["name1"] if p1>=0.5 else m["name2"]
        pmf=pm1 if fav==m["name1"] else pm2
        om=o1 if fav==m["name1"] else o2
        mw=m["name1"] if m["p1_won"] else m["name2"]
        sw=s1w(sbk.get((m["date"],round(o1,2),round(o2,2)),""),m["name1"],m["name2"],mw)
        if sw is None: continue
        fwm=(mw==fav); fws=(sw==fav)
        if solo: won,odd=fwm,om
        else:
            won=fwm and fws
            ps=0.5+K*(pmf-0.5); odd=om*(1.0/(ps*(1+MARG)))
        stake=round(bank*0.02)
        if stake<10: continue
        n+=1; st+=stake
        if won: w+=1; ret+=stake*odd; bank+=stake*(odd-1)
        else: bank-=stake
        peak=max(peak,bank)
    roi=(ret-st)/st*100 if st else 0
    print(f"{'SOLO' if solo else 'BUILDER':8s}: {n:4d} sazek | usp {100.0*w/n if n else 0:5.1f}% | ROI {roi:+6.1f}% | banka {bank:.2f} vrchol {peak:.0f}")
print("=== overeni (bez break) ===")
run(True)
run(False)
