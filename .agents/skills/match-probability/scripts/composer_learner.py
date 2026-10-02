#!/usr/bin/env python3
"""composer_learner.py - "nauč se skládat tikety".

Systematicky otestuje RUZNE SKLADBY tiketu na historickych datech (WTA
2021-2025) a seradi je podle ROI. Cil: empiricky zjistit, ktera struktura
tiketu je nejlepsi - ne hadat.

Testovane skladby:
  A) SOLO favorit trhu - po pasmech kurzu (1.0-1.2 / 1.2-1.5 / 1.5-2.0 / 2.0+)
  B) SOLO podle modelu (model-only, bez ohledu na trh)
  C) BUILDER 2 nohy na JEDNOM zapase (vitez zapasu + vitez 1.setu)
  D) AKO 2 zapasy (dva solidni favoriti ve stejny den)
  E) AKO 3 zapasy

Pro kazdou skladbu se meri: pocet sazek, uspesnost, prumerny kurz, ROI,
konecna banka. Vse flat vklad 2% banky, jako zivy simulátor.
"""
import csv, os, re, sys, itertools
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tennis_value_backtest as tv

ODDS_BANDS = [(1.0,1.2),(1.2,1.5),(1.5,2.0),(2.0,3.0),(3.0,100.0)]

def load():
    sack = tv.load_sackmann_wta()
    odds = list(csv.DictReader(open(tv.ODDS_PATH, encoding="utf-8")))
    joined = tv.join_matches(sack, odds)
    joined.sort(key=lambda m: m["cutoff"])
    hist = tv.History(sack)
    # score lookup
    sbk = {}
    for r in odds:
        try: k=(r["Date"],round(float(r["Odd_1"]),2),round(float(r["Odd_2"]),2))
        except (ValueError,KeyError): continue
        sbk.setdefault(k, r.get("Score",""))
    return joined, hist, sbk

def set1_winner(score, name1, name2, match_winner):
    m = re.match(r"\s*(\d+)-(\d+)", score or "")
    if not m: return None
    a,b = int(m.group(1)), int(m.group(2))
    if a==b: return None
    loser = name2 if match_winner==name1 else name1
    return match_winner if a>b else loser

def prep(joined, hist, sbk):
    """Predpocitej pro kazdy zapas: model p, favorita, vysledky, score."""
    out = []
    for m in joined:
        p1,n1,n2 = tv.model_prob(hist, m["name1"], m["name2"], m["cutoff"])
        if p1 is None or n1<15 or n2<15: continue
        o1,o2 = m["odd1"], m["odd2"]
        if not (tv.ODDS_MIN<=o1<=tv.ODDS_MAX and tv.ODDS_MIN<=o2<=tv.ODDS_MAX): continue
        pm1,pm2,_ = tv.devig(o1,o2)
        fav = m["name1"] if p1>=0.5 else m["name2"]
        fav_odd = o1 if fav==m["name1"] else o2
        fav_won = m["p1_won"] if fav==m["name1"] else (not m["p1_won"])
        mkt_p = pm1 if fav==m["name1"] else pm2
        score = sbk.get((m["date"],round(o1,2),round(o2,2)),"")
        mw = m["name1"] if m["p1_won"] else m["name2"]
        s1 = set1_winner(score, m["name1"], m["name2"], mw)
        fav_set1 = (s1==fav) if s1 else None
        out.append({"date":m["date"],"cutoff":m["cutoff"],"fav":fav,"fav_odd":fav_odd,
                    "fav_won":fav_won,"mkt_p":mkt_p,"model_p":max(p1,1-p1),
                    "fav_set1":fav_set1,"n1":n1,"n2":n2})
    return out

def bankroll(bets):
    """bets = [(odd, won)] -> ROI, konecna banka, uspesnost. Flat 2%."""
    bank=1000.0; n=w=0; st=ret=0.0; odd_sum=0.0
    for odd, won in bets:
        stake=round(bank*0.02)
        if stake<10: break
        n+=1; st+=stake; odd_sum+=odd
        if won: w+=1; ret+=stake*odd; bank+=stake*(odd-1)
        else: bank-=stake
        if bank<10: break
    roi=(ret-st)/st*100 if st else 0
    return n,w,roi,bank,(odd_sum/n if n else 0)

def row(label, bets):
    n,w,roi,bank,avg = bankroll(bets)
    if n==0:
        print(f"  {label:34s} | 0 sazek"); return
    print(f"  {label:34s} | {n:5d} | usp {100.0*w/n:5.1f}% | avg kurz {avg:5.2f} | ROI {roi:+6.1f}% | banka {bank:5.0f}")

def main():
    joined, hist, sbk = load()
    rows = prep(joined, hist, sbk)
    print(f"=== COMPOSER LEARNER (WTA 2021-2025) ===")
    print(f"zapasu s daty: {len(rows)}\n")

    print("A) SOLO favorit trhu, podle pasma kurzu:")
    for lo,hi in ODDS_BANDS:
        bets=[(r["fav_odd"],r["fav_won"]) for r in rows if lo<=r["fav_odd"]<hi]
        row(f"kurz {lo:.1f}-{hi:.1f}", bets)

    print("\nB) SOLO podle MODELU (model vybere stranu):")
    for thr in (0.5,0.65,0.75):
        bets=[(r["fav_odd"],r["fav_won"]) for r in rows if r["model_p"]>=thr]
        row(f"model_p>={thr:.2f}", bets)

    print("\nC) BUILDER 2 nohy na 1 zapase (zapas + 1.set):")
    b=[(r["fav_odd"]*1.5, r["fav_won"] and r["fav_set1"]) for r in rows if r["fav_set1"] is not None]
    row("builder (odhad set1 kurzu)", b)

    print("\nD) AKO 2 zapasy (dva favoriti stejny den, kurz<=1.5):")
    byday=defaultdict(list)
    for r in rows: byday[r["date"]].append(r)
    bets=[]
    for d, rs in byday.items():
        favs=[r for r in rs if r["fav_odd"]<=1.5]
        for a,b_ in itertools.combinations(favs[:6],2):
            bets.append((a["fav_odd"]*b_["fav_odd"], a["fav_won"] and b_["fav_won"]))
    row("AKO2 (favoriti <=1.5)", bets)

    print("\nE) AKO 3 zapasy (stejny den, kurz<=1.4):")
    bets=[]
    for d, rs in byday.items():
        favs=[r for r in rs if r["fav_odd"]<=1.4]
        for combo in itertools.combinations(favs[:5],3):
            odd=1.0; won=True
            for c in combo: odd*=c["fav_odd"]; won=won and c["fav_won"]
            bets.append((odd,won))
    row("AKO3 (favoriti <=1.4)", bets)

if __name__=="__main__":
    main()
