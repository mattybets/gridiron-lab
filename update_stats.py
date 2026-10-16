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
    current_season=datetime.datetime.now(datetime.timezone.utc).year
    if season < current_season:
        print(f'WARNING: NFL player statistics source only has {season}; current calendar year is {current_season}. No current-season projections will be published.')
    filtered=[r for r in rows if int(r.get('season') or 0)==season and (r.get('season_type') or 'REG')=='REG' and (r.get('week') or '').isdigit()]
    maxweek=max(int(r['week']) for r in filtered)
    by={}
    # Points allowed by each opponent, by position, from the same player-game dataset.
    defense_games={}
    for r in filtered:
        pos=r.get('position') or ''
        opp=r.get('opponent_team') or ''
        week=r.get('week') or ''
        if pos not in ('QB','RB','WR','TE') or not opp or not week.isdigit(): continue
        if int(week)<maxweek-5: continue
        try: pts=float(r.get('fantasy_points_ppr') or 0)
        except ValueError: continue
        defense_games[(opp,pos,int(week))]=defense_games.get((opp,pos,int(week)),0)+pts
    def_avgs={}
    for (opp,pos,week),pts in defense_games.items():
        def_avgs.setdefault(pos,{}).setdefault(opp,[]).append(pts)
    def_avgs={pos:{team:round(sum(values)/len(values),2) for team,values in teams.items()} for pos,teams in def_avgs.items()}
    league_avgs={pos:sum(teams.values())/len(teams) for pos,teams in def_avgs.items() if teams}

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
        players.append({'name':name,'team':team,'position':pos,'historical_ppr_avg':avg,'games':len(pts),'last_week':games[-1][0], 'recent_ppr_avg':round(sum(pts[-3:])/len(pts[-3:]),2)})
    if not players: raise RuntimeError('No usable player records; preserving last published data')
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({'season':season,'through_week':maxweek,'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':URL,'metric':'Historical PPR player game points and defense positional points allowed; projections are estimates, not DraftKings scoring','players':players,'defense_allowed_by_position':def_avgs,'league_allowed_by_position':league_avgs,'current_season_available':season>=current_season},separators=(',',':')))
    print('Wrote',len(players),'players through week',maxweek)
    # NFL matchup feed from ESPN public scoreboard; does not include DFS salaries.
    start=datetime.datetime.now(datetime.timezone.utc)
    dates=''.join([])  # dates handled by scoreboard's current-week feed
    api='https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?limit=100'
    request=urllib.request.Request(api,headers={'User-Agent':'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(request,timeout=25) as resp:
            schedule=json.load(resp)
        games=[]
        for e in schedule.get('events',[]):
            competition=(e.get('competitions') or [{}])[0]
            competitors=competition.get('competitors') or []
            home=next((c.get('team',{}).get('abbreviation','') for c in competitors if c.get('homeAway')=='home'),'')
            away=next((c.get('team',{}).get('abbreviation','') for c in competitors if c.get('homeAway')=='away'),'')
            kickoff=e.get('date','')
            if home and away and kickoff and e.get('status',{}).get('type',{}).get('state')=='pre':
                games.append({'id':str(e.get('id')),'home':home,'away':away,'kickoff_utc':kickoff})
        target=OUT.parent/'nfl_matchups.json'
        target.write_text(json.dumps({'updated_utc':start.isoformat(),'source':api,'games':games},separators=(',',':')))
        print('Wrote',len(games),'scheduled matchups')
    except Exception as exc:
        print('Schedule refresh unavailable:',exc)

if __name__=='__main__': main()
