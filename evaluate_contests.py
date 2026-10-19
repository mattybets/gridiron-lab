"""Evaluate recorded DraftKings outcomes; publish transparent, non-trained feedback.

Run: python evaluate_contests.py
Only validated pregame snapshots can support projection-error/backtest claims.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'/'historical_contests.json'
OUT=ROOT/'data'/'model_feedback.json'

def evaluate(data):
    contests=data.get('contests',[])
    if not contests: raise ValueError('No contests available')
    known=[c for c in contests if isinstance(c.get('winner_points'),(int,float))]
    payout=[c for c in contests if isinstance(c.get('entry_fee_usd'),(int,float)) and isinstance(c.get('payout_usd'),(int,float))]
    gaps=[round(c['winner_points']-c['lineup_points'],2) for c in known]
    observations=[]
    for c in contests:
        item={'id':c['id'],'date':c.get('reported_date'),'lineup_points':c['lineup_points'],
              'finish_rank':c.get('finish_rank'),'winner_points':c.get('winner_points'),
              'gap_to_winner':round(c['winner_points']-c['lineup_points'],2) if c.get('winner_points') is not None else None,
              'has_player_scores':bool(c.get('players')),
              'has_pregame_snapshot':bool(c.get('pregame_snapshot')),
              'has_verified_full_field':bool(c.get('verified_full_field'))}
        observations.append(item)
    total_cost=sum(c['entry_fee_usd'] for c in payout)
    roi=round(100*(sum(c['payout_usd'] for c in payout)-total_cost)/total_cost,2) if total_cost>0 else None
    return {'schema_version':1,'generated_utc':datetime.now(timezone.utc).isoformat(),
        'contest_count':len(contests),'known_winner_count':len(known),
        'mean_lineup_points':round(sum(c['lineup_points'] for c in contests)/len(contests),2),
        'mean_gap_to_winner':round(sum(gaps)/len(gaps),2) if gaps else None,
        'roi_complete_records':len(payout),'roi_percent_complete_records':roi,
        'pregame_snapshot_count':sum(o['has_pregame_snapshot'] for o in observations),
        'full_field_count':sum(o['has_verified_full_field'] for o in observations),
        'records':observations,
        'training_status':'not_trained',
        'ranking_parameters_updated':False,
        'limitations':['Historical outcomes are descriptive until matched with saved pre-kickoff projections and slate salaries.',
                       'Winning-score gaps do not identify the best alternative lineup or optimal ranking weights.',
                       'No model weights are changed from incomplete records.']}

def main():
    report=evaluate(json.loads(DATA.read_text(encoding='utf-8')))
    OUT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Recorded contests:',report['contest_count'])
    print('Mean winner gap:',report['mean_gap_to_winner'])
    print('Pregame snapshots:',report['pregame_snapshot_count'])
    print('Model training:',report['training_status'])
    print('Wrote',OUT)

if __name__=='__main__':main()
