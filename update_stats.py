"""Free nflverse weekly player stats -> conservative historical DK PPG baselines.
No salary, ownership, injuries or forward-looking matchup adjustment is inferred.
"""
import csv, io, json, urllib.request, datetime, pathlib, statistics
URL='https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv'
OUT=pathlib.Path(__file__).parent/'data'/'nfl_baselines.json'
def main():
    req=urllib.request.Request(URL,headers={'User-Agent':'GridironLab/3.0'})
    with urllib.request.urlopen(req,timeout=60) as r: content=r.read().decode('utf-8-sig')
    rows=list(csv.DictReader(io.StringIO(content)))
    if not rows: raise RuntimeError('NFL dataset is empty; preserving last published data')
    seasons=sorted({int(r['season']) for r in rows if (r.get('season') or '').isdigit()})
    season=seasons[-1]
    filtered=[r for r in rows if int(r.get('season') or 0)==season and (r.get('season_type') or 'REG')=='REG' and (r.get('week') or '').isdigit()]
    maxweek=max(int(r['week']) for r in filtered)
    by={}
    for r in filtered:
        if int(r['week'])<maxweek-5: continue
        name=r.get('player_name') or r.get('player_display_name') or ''
        team=r.get('recent_team') or ''
        pos=r.get('position') or ''
        if not name or not team or pos not in ('QB','RB','WR','TE'): continue
        try:
            pts=float(r.get('fantasy_points_ppr') or 0)
        except ValueError: continue
        key=(r.get('player_id') or name,team)
        by.setdefault(key,[]).append((int(r['week']),pts,name,pos))
    players=[]
    for (_,team),games in by.items():
        games.sort(); pts=[g[1] for g in games]; name=games[-1][2];pos=games[-1][3]
        if len(pts)<2: continue
        # historical baseline, not a forward prediction
        avg=round(sum(pts)/len(pts),2)
        players.append({'name':name,'team':team,'position':pos,'historical_ppr_avg':avg,'games':len(pts),'last_week':games[-1][0]})
    if not players: raise RuntimeError('No usable player records; preserving last published data')
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({'season':season,'through_week':maxweek,'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':URL,'metric':'Historical PPR points/game; not DraftKings scoring or a future projection','players':players},separators=(',',':')))
    print('Wrote',len(players),'players through week',maxweek)
if __name__=='__main__': main()
