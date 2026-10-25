"""Evaluate recorded DraftKings outcomes; publish transparent, non-trained feedback.

Run: python evaluate_contests.py
Only validated pregame snapshots can support projection-error/backtest claims.
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'/'historical_contests.json'
OUT=ROOT/'data'/'model_feedback.json'
CONFIG=ROOT/'data'/'model_config.json'
DEFAULT_WEIGHTS={'p90':0.45,'mean':0.25,'projection':0.20,'ceiling':0.10}

def evaluate_snapshots():
    """Evaluate only when verified player-level actuals are saved for a slate.

    Actuals schema: {"matchup": "...", "players": [{"name":"...", "team":"...", "actual_points":12.5}]}
    Files belong in data/actuals/<snapshot filename>.json.
    """
    out=[]
    for path in sorted((ROOT/'data'/'pregame').glob('*.json')):
        snapshot=json.loads(path.read_text(encoding='utf-8'))
        actual_path=ROOT/'data'/'actuals'/path.name
        row={'snapshot':path.name,'matchup':snapshot.get('matchup'),'retrospective_only':bool(snapshot.get('retrospective_only')),
             'saved_at_utc':snapshot.get('saved_at_utc'),
             'player_count':len(snapshot.get('players',[])),
             'lineup_count':len(snapshot.get('lineups',[])),
             'status':'awaiting_verified_actuals'}
        if actual_path.exists():
            actual=json.loads(actual_path.read_text(encoding='utf-8'))
            if actual.get('matchup')!=snapshot.get('matchup'):
                row['status']='matchup_mismatch'
            else:
                lookup={(p['name'].strip().casefold(),p['team'].strip().upper()):float(p['actual_points'])
                        for p in actual.get('players',[]) if p.get('actual_points') is not None}
                matched=[(p,lookup[(p['name'].strip().casefold(),p['team'].strip().upper())])
                         for p in snapshot.get('players',[])
                         if (p['name'].strip().casefold(),p['team'].strip().upper()) in lookup]
                row['matched_player_count']=len(matched)
                row['matched_players']=[{'name':p['name'],'team':p['team'],
                    'position':p.get('position','UNKNOWN'),
                    'projection':float(p['projection']),'actual_points':score}
                    for p,score in matched]
                if matched:
                    errors=[p['projection']-score for p,score in matched]
                    row['mean_absolute_player_error']=round(sum(abs(x) for x in errors)/len(errors),3)
                    row['mean_signed_player_error']=round(sum(errors)/len(errors),3)
                player_inputs={(p['name'].strip().casefold(),p['team'].strip().upper()):p
                               for p in snapshot.get('players',[])}
                lineups=[]
                for l in snapshot.get('lineups',[]):
                    scores=[lookup.get((p['name'].strip().casefold(),p['team'].strip().upper()))
                            for p in l.get('players',[])]
                    expected=[player_inputs.get((p['name'].strip().casefold(),p['team'].strip().upper()))
                              for p in l.get('players',[])]
                    if len(scores)==6 and all(x is not None for x in scores):
                        total=sum(score*(1.5 if p['slot']=='CPT' else 1)
                                  for score,p in zip(scores,l['players']))
                        lineups.append({'strategy':l.get('strategy'),'index':l.get('index'),
                                        'projected':l.get('projected'),
                                        'modeled_p90':l.get('modeled_p90'),
                                        'modeled_mean':l.get('modeled_mean',sum(float(p['projection'])*(1.5 if v['slot']=='CPT' else 1) for p,v in zip(expected,l['players'])) if all(p is not None for p in expected) else None),
                                        'modeled_ceiling':l.get('modeled_ceiling',sum(float(p['ceiling'])*(1.5 if v['slot']=='CPT' else 1) for p,v in zip(expected,l['players'])) if all(p is not None and p.get('ceiling') is not None for p in expected) else None),
                                        'actual_points':round(total,2)})
                row['evaluated_lineups']=lineups
                row['gpp_candidate_count']=sum(l.get('strategy')=='gpp' for l in snapshot.get('lineups',[]))
                row['status']='evaluated' if lineups else 'partial_actuals'
        out.append(row)
    return out

def projection_diagnostics(snapshot_rows):
    """Historical, deduplicated player error audit; descriptive, never in-sample training."""
    by_matchup={}
    for row in snapshot_rows:
        if row.get('status')!='evaluated' or row.get('retrospective_only'): continue
        if not row.get('matched_players'): continue
        key=row.get('matchup')
        if key not in by_matchup or str(row.get('saved_at_utc',''))>str(by_matchup[key].get('saved_at_utc','')):
            by_matchup[key]=row
    positions=defaultdict(list)
    for row in by_matchup.values():
        for p in row['matched_players']:
            positions[p['position']].append(p['projection']-p['actual_points'])
    result={}
    for pos,errors in sorted(positions.items()):
        n=len(errors)
        result[pos]={'samples':n,'mean_signed_error':round(sum(errors)/n,3),
                     'mean_absolute_error':round(sum(abs(e) for e in errors)/n,3)}
    return {'independent_games':len(by_matchup),'by_position':result,
            'note':'Descriptive error audit; no correction automatically applied. Four games cannot establish reliable positional corrections.'}

def fit_position_adjustments(snapshot_rows):
    """Evaluate shrinkage corrections on untouched games; never fit and test on same slate."""
    by_game={}
    for row in snapshot_rows:
        if row.get('status')!='evaluated' or row.get('retrospective_only') or not row.get('matched_players'): continue
        key=row.get('matchup')
        if key not in by_game or str(row.get('saved_at_utc',''))>str(by_game[key].get('saved_at_utc','')):
            by_game[key]=row
    games=list(by_game.values())
    result={'enabled':False,'method':'leave-one-game-out positional bias shrinkage',
            'validated_games':len(games),'adjustments':{},
            'reason':'Insufficient independent games for safe position adjustments'}
    if len(games)<4:return result
    positions=sorted({p['position'] for g in games for p in g['matched_players'] if p.get('position') not in (None,'UNKNOWN')})
    def fit(rows,position):
        errors=[p['projection']-p['actual_points'] for g in rows for p in g['matched_players'] if p['position']==position]
        if len(errors)<8:return 0.0
        # Shrink by 20 virtual zero-bias observations, cap at 3 fantasy points.
        return max(-3.,min(3.,sum(errors)/(len(errors)+20)))
    outcomes={}
    for pos in positions:
        folds=[]
        for holdout in games:
            train=[g for g in games if g is not holdout]
            adjustment=fit(train,pos)
            for p in holdout['matched_players']:
                if p['position']!=pos:continue
                original=abs(p['projection']-p['actual_points'])
                revised=abs(p['projection']-adjustment-p['actual_points'])
                folds.append((original,revised))
        if not folds:continue
        improvement=sum(a-b for a,b in folds)/len(folds)
        # Each position must show out-of-sample benefit; no corrections to sparse groups.
        full=fit(games,pos)
        if improvement>=0.20 and abs(full)>=0.25:
            result['adjustments'][pos]=round(-full,3)
        outcomes[pos]={'samples':len(folds),'heldout_mae_improvement':round(improvement,3),
                       'proposed_delta':round(-full,3)}
    result['heldout_by_position']=outcomes
    result['enabled']=bool(result['adjustments'])
    result['reason']='Only individually validated positional adjustments enabled' if result['enabled'] else 'No positional correction demonstrated sufficient held-out benefit'
    return result

def fit_ranking(snapshot_rows):
    """Leave-one-game-out evaluation, not an in-sample claim of improvement.

    Candidate rankings use ONLY saved pregame lineup metrics. A game is eligible
    only if every GPP candidate has a verified final score. Multiple snapshots
    of the same matchup count as one game (latest snapshot wins).
    """
    by_matchup={}
    for row in snapshot_rows:
        if row.get('status')!='evaluated' or row.get('retrospective_only'): continue
        candidates=[l for l in row.get('evaluated_lineups',[]) if l.get('strategy')=='gpp']
        saved=row.get('gpp_candidate_count',0)
        if saved<2 or len(candidates)!=saved: continue
        if any(not all(isinstance(l.get(k),(int,float)) for k in
                       ('modeled_p90','modeled_mean','projected','modeled_ceiling','actual_points'))
               for l in candidates): continue
        name=row['matchup']
        if name not in by_matchup or row['saved_at_utc']>by_matchup[name]['saved_at_utc']:
            by_matchup[name]=row
    games=list(by_matchup.values())
    config={'schema_version':1,'enabled':False,'weights':DEFAULT_WEIGHTS,
            'validated_games':len(games),'method':'leave-one-game-out',
            'reason':'At least four independent games with complete candidate scores are required'}
    if len(games)<4:return config
    # Ranking weights must sum to 1. No tuning on a held-out game's actual scores.
    options=[DEFAULT_WEIGHTS,
        {'p90':0.60,'mean':0.20,'projection':0.15,'ceiling':0.05},
        {'p90':0.30,'mean':0.25,'projection':0.35,'ceiling':0.10},
        {'p90':0.25,'mean':0.15,'projection':0.25,'ceiling':0.35}]
    def score(l,w):
        return (w['p90']*l['modeled_p90']+w['mean']*l['modeled_mean']+
                w['projection']*l['projected']+w['ceiling']*l['modeled_ceiling'])
    def reward(game,w):
        selected=max((x for x in game['evaluated_lineups'] if x['strategy']=='gpp'),
                     key=lambda x:score(x,w))
        return selected['actual_points']
    # Nested LOOCV: select candidate weights on training games, compare to
    # baseline on the untouched held-out game. Penalize ties toward baseline.
    improvements=[]
    for i,holdout in enumerate(games):
        train=[g for j,g in enumerate(games) if j!=i]
        chosen=max(options,key=lambda w:(sum(reward(g,w) for g in train),-options.index(w)))
        improvements.append(reward(holdout,chosen)-reward(holdout,DEFAULT_WEIGHTS))
    config['heldout_mean_improvement']=round(sum(improvements)/len(improvements),3)
    config['heldout_wins']=sum(x>0.01 for x in improvements)
    config['heldout_losses']=sum(x< -0.01 for x in improvements)
    if config['heldout_mean_improvement']<=1.0 or config['heldout_wins']<3 or config['heldout_losses']>1:
        config['reason']='Held-out performance did not justify changing default weights'
        return config
    winner=max(options,key=lambda w:(sum(reward(g,w) for g in games),-options.index(w)))
    if winner==DEFAULT_WEIGHTS:
        config['reason']='Default weights remained best'
        return config
    config.update(enabled=True,weights=winner,reason='Held-out evidence supports tested alternative')
    return config

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
    snapshots=evaluate_snapshots()
    calibration=fit_ranking(snapshots)
    position_calibration=fit_position_adjustments(snapshots)
    calibration['position_calibration']=position_calibration
    return {'schema_version':1,'generated_utc':datetime.now(timezone.utc).isoformat(),
        'contest_count':len(contests),'known_winner_count':len(known),
        'mean_lineup_points':round(sum(c['lineup_points'] for c in contests)/len(contests),2),
        'mean_gap_to_winner':round(sum(gaps)/len(gaps),2) if gaps else None,
        'roi_complete_records':len(payout),'roi_percent_complete_records':roi,
        'pregame_snapshot_count':len({x['matchup'] for x in snapshots}),
        'saved_snapshot_file_count':len(snapshots),
        'full_field_count':sum(o['has_verified_full_field'] for o in observations),
        'records':observations,
        'snapshot_evaluations':snapshots,
        'projection_diagnostics':projection_diagnostics(snapshots),
        'position_calibration':position_calibration,
        'calibration':calibration,
        'training_status':'validated' if calibration['enabled'] else 'insufficient_evidence',
        'ranking_parameters_updated':calibration['enabled'],
        'limitations':['Historical outcomes are descriptive until matched with saved pre-kickoff projections and slate salaries.',
                       'Winning-score gaps do not identify the best alternative lineup or optimal ranking weights.',
                       'No model weights are changed from incomplete records.']}

def main():
    report=evaluate(json.loads(DATA.read_text(encoding='utf-8')))
    OUT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    CONFIG.write_text(json.dumps(report['calibration'],indent=2)+'\n',encoding='utf-8')
    print('Recorded contests:',report['contest_count'])
    print('Mean winner gap:',report['mean_gap_to_winner'])
    print('Saved snapshot files:',len(report['snapshot_evaluations']))
    print('Evaluated snapshots:',sum(x['status']=='evaluated' for x in report['snapshot_evaluations']))
    print('Model training:',report['training_status'])
    print('Wrote',OUT,'and',CONFIG)

if __name__=='__main__':main()
