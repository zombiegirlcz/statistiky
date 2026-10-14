#!/usr/bin/env python3
"""
Backtest strategie: sázet na favorita POUZE když prohrává (tehdy je kurz nejvyšší).

Načte posledních 100 tiketů z logu a simuluje:
- Kdo byl favorit (vyšší model_p)
- Jestli v době sázky prohrával (nižší skóre)
- Jestli by sázka na favorita vedla k výhře
"""
import json
import re
from pathlib import Path
from collections import defaultdict

LOG_PATH = Path("live_bets_log.jsonl")

def parse_score(score_str):
    """Parsuje score_at_bet typu 'sety 1:2, gemy 3:5' nebo 'sety 0:1, gemy 6:2, body 30:15'."""
    if not score_str:
        return None, None
    
    sets_match = re.search(r'sety (\d+):(\d+)', score_str)
    games_match = re.search(r'gemy (\d+):(\d+)', score_str)
    
    sets = (int(sets_match.group(1)), int(sets_match.group(2))) if sets_match else None
    games = (int(games_match.group(1)), int(games_match.group(2))) if games_match else None
    
    return sets, games

def is_losing(sets, games, player_idx):
    """Zjistí, jestli hráč prohrává (má méně setů, nebo stejně setů ale méně gemů)."""
    if not sets or not games:
        return False
    
    sets_p1, sets_p2 = sets
    games_p1, games_p2 = games
    
    if player_idx == 0:  # p1
        if sets_p1 < sets_p2:
            return True
        if sets_p1 == sets_p2 and games_p1 < games_p2:
            return True
    else:  # p2
        if sets_p2 < sets_p1:
            return True
        if sets_p2 == sets_p1 and games_p2 < games_p1:
            return True
    
    return False

def main():
    if not LOG_PATH.exists():
        print("❌ Log neexistuje:", LOG_PATH)
        return
    
    entries = [json.loads(line) for line in LOG_PATH.read_text().splitlines() if line.strip()]
    
    if not entries:
        print("❌ Log je prázdný")
        return
    
    # Posledních 100 tiketů
    entries = entries[-100:]
    print(f"Analyzuji posledních {len(entries)} tiketů\n")
    
    # Statistiky
    stats = {
        'total': len(entries),
        'fav_wins': 0,
        'fav_losses': 0,
        'fav_losing_at_bet': 0,
        'fav_losing_at_bet_wins': 0,
        'fav_losing_at_bet_losses': 0,
        'fav_winning_at_bet': 0,
        'fav_winning_at_bet_wins': 0,
        'fav_winning_at_bet_losses': 0,
    }
    
    examples_losing_wins = []
    examples_losing_losses = []
    
    for entry in entries:
        p1 = entry.get('player1', '')
        p2 = entry.get('player2', '')
        pick = entry.get('pick', '')
        model_p = entry.get('model_p', 0.5)
        actual_winner = entry.get('actual_winner', '')
        score_at_bet = entry.get('score_at_bet', '')
        odds = entry.get('odds', 1.0)
        stake = entry.get('stake', 0)
        status = entry.get('status', '')
        
        # Kdo byl favorit?
        if model_p >= 0.5:
            fav_name = p1
            fav_idx = 0
            fav_model_p = model_p
        else:
            fav_name = p2
            fav_idx = 1
            fav_model_p = 1 - model_p
        
        # Vyhrál favorit?
        fav_won = (actual_winner == fav_name)
        if fav_won:
            stats['fav_wins'] += 1
        else:
            stats['fav_losses'] += 1
        
        # Prohrával favorit v době sázky?
        sets, games = parse_score(score_at_bet)
        fav_losing = is_losing(sets, games, fav_idx)
        
        if fav_losing:
            stats['fav_losing_at_bet'] += 1
            if fav_won:
                stats['fav_losing_at_bet_wins'] += 1
                examples_losing_wins.append({
                    'match': f"{p1} vs {p2}",
                    'fav': fav_name,
                    'score': score_at_bet,
                    'odds': odds,
                    'result': 'VÝHRA'
                })
            else:
                stats['fav_losing_at_bet_losses'] += 1
                examples_losing_losses.append({
                    'match': f"{p1} vs {p2}",
                    'fav': fav_name,
                    'score': score_at_bet,
                    'odds': odds,
                    'result': 'PROHRA'
                })
        else:
            stats['fav_winning_at_bet'] += 1
            if fav_won:
                stats['fav_winning_at_bet_wins'] += 1
            else:
                stats['fav_winning_at_bet_losses'] += 1
    
    # Výsledky
    print("=" * 70)
    print("VÝSLEDKY BACKTESTU: 'Sázet na favorita JEN když prohrává'")
    print("=" * 70)
    
    print(f"\nCelkem tiketů: {stats['total']}")
    print(f"Favorit vyhrál zápas: {stats['fav_wins']}× ({stats['fav_wins']/stats['total']*100:.1f}%)")
    print(f"Favorit prohrál zápas: {stats['fav_losses']}× ({stats['fav_losses']/stats['total']*100:.1f}%)")
    
    print(f"\n--- Rozdělení podle stavu v době sázky ---")
    print(f"Favorit PROHRÁVAL v době sázky: {stats['fav_losing_at_bet']}×")
    if stats['fav_losing_at_bet'] > 0:
        win_rate = stats['fav_losing_at_bet_wins'] / stats['fav_losing_at_bet'] * 100
        print(f"  z toho vyhrál zápas: {stats['fav_losing_at_bet_wins']}× ({win_rate:.1f}%)")
        print(f"  z toho prohrál zápas: {stats['fav_losing_at_bet_losses']}×")
    
    print(f"\nFavorit VEDL v době sázky: {stats['fav_winning_at_bet']}×")
    if stats['fav_winning_at_bet'] > 0:
        win_rate = stats['fav_winning_at_bet_wins'] / stats['fav_winning_at_bet'] * 100
        print(f"  z toho vyhrál zápas: {stats['fav_winning_at_bet_wins']}× ({win_rate:.1f}%)")
        print(f"  z toho prohrál zápas: {stats['fav_winning_at_bet_losses']}×")
    
    # Simulace nové strategie
    print(f"\n{'='*70}")
    print("SIMULACE NOVÉ STRATEGIE")
    print("=" * 70)
    print("Pravidlo: sázet na favorita POUZE když prohrává (kurz je nejvyšší)")
    
    if stats['fav_losing_at_bet'] > 0:
        bets_placed = stats['fav_losing_at_bet']
        bets_won = stats['fav_losing_at_bet_wins']
        bets_lost = stats['fav_losing_at_bet_losses']
        win_rate = bets_won / bets_placed * 100
        
        # Předpokládáme průměrný kurz 2.0 (když favorit prohrává, kurz je vyšší)
        avg_odds = 2.0
        avg_stake = 20  # průměrný vklad
        
        profit = (bets_won * avg_stake * (avg_odds - 1)) - (bets_lost * avg_stake)
        
        print(f"\nVsazeno tiketů: {bets_placed}")
        print(f"Vyhráno: {bets_won} ({win_rate:.1f}%)")
        print(f"Prohráno: {bets_lost}")
        print(f"\nPři průměrném kurzu {avg_odds:.2f} a vkladu {avg_stake} mincí:")
        print(f"  Zisk/ztráta: {profit:+.0f} mincí")
        print(f"  ROI: {profit/(bets_placed*avg_stake)*100:+.1f}%")
    
    # Příklady
    if examples_losing_wins:
        print(f"\n{'='*70}")
        print(f"PŘÍKLADY: Favorit prohrával → vyhrál zápas ({len(examples_losing_wins)}×)")
        print("=" * 70)
        for ex in examples_losing_wins[:5]:
            print(f"  {ex['match']}")
            print(f"    Favorit: {ex['fav']}, skóre: {ex['score']}, kurz: {ex['odds']:.2f} → {ex['result']}")
    
    if examples_losing_losses:
        print(f"\n{'='*70}")
        print(f"PŘÍKLADY: Favorit prohrával → prohrál zápas ({len(examples_losing_losses)}×)")
        print("=" * 70)
        for ex in examples_losing_losses[:5]:
            print(f"  {ex['match']}")
            print(f"    Favorit: {ex['fav']}, skóre: {ex['score']}, kurz: {ex['odds']:.2f} → {ex['result']}")
    
    print(f"\n{'='*70}")
    print("ZÁVĚR")
    print("=" * 70)
    if stats['fav_losing_at_bet'] > 0:
        win_rate = stats['fav_losing_at_bet_wins'] / stats['fav_losing_at_bet'] * 100
        if win_rate >= 60:
            print(f"✅ Strategie vypadá slibně: {win_rate:.0f}% výher když favorit prohrává")
            print("   (kurz je v tu chvíli nejvyšší, protože trh favorita podceňuje)")
        elif win_rate >= 50:
            print(f"⚠️  Strategie je neutrální: {win_rate:.0f}% výher")
            print("   (potřeba vyšší kurz, aby se vyplatila)")
        else:
            print(f"❌ Strategie nefunguje: jen {win_rate:.0f}% výher")
            print("   (favorit často prohrává z dobrého důvodu)")
    else:
        print("⚠️  Žádné tikety kde favorit prohrával v době sázky")

if __name__ == "__main__":
    main()
