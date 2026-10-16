"""Free nflverse weekly player stats -> conservative historical DK PPG baselines.
No salary, ownership, injuries or forward-looking matchup adjustment is inferred.
"""
import csv, io, json, urllib.request, datetime, pathlib, statistics
URL_TEMPLATE='https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv'
OUT=pathlib.Path(__file__).parent/'data'/'nfl_baselines.json'


def _number(row, key, default=0.0):
    try:
        return float(row.get(key) or default)
    except (TypeError, ValueError):
        return default


def _distribution(games, name, team, position):
    games = sorted(games)
    values = [v for _, v in games]
    if not values:
        return None
    average = sum(values) / len(values)
    ordered = sorted(values)
    p90 = ordered[min(len(ordered)-1, int(.9*(len(ordered)-1)+.999999))]
    return {'name':name, 'team':team, 'position':position,
            'historical_ppr_avg':round(average,2),
            'recent_ppr_avg':round(sum(values[-3:])/len(values[-3:]),2),
            'ppr_p90':round(p90,2),
            'ppr_stddev':round(statistics.pstdev(values),2) if len(values)>1 else 0,
            'games':len(values), 'last_week':games[-1][0]}


def load_special_teams(season, maxweek):
    """Derived *estimated* DK K/DST scoring from nflverse play-by-play.

    DST points allowed use final opponent score; this is an approximation of DK's
    defensive points-allowed definition (e.g., opponent return TD exclusions).
    """
    import gzip
    urls = [f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz',
            f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv']
    last_error = None
    for url in urls:
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'GridironLab/5.5'})
            with urllib.request.urlopen(req,timeout=120) as resp:
                raw=resp.read()
            if raw[:2] == b'\x1f\x8b': raw=gzip.decompress(raw)
            reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
            required={'game_id','week','season_type','home_team','away_team','home_score','away_score',
                      'posteam','defteam','field_goal_result','extra_point_result',
                      'kicker_player_name','kick_distance','sack','interception','fumble_lost',
                      'def_td','safety'}
            if not required.issubset(set(reader.fieldnames or [])):
                raise RuntimeError('PBP schema missing: '+', '.join(sorted(required-set(reader.fieldnames or []))))
            rows=[r for r in reader if (r.get('season_type') or 'REG')=='REG' and
                  str(r.get('week','')).isdigit() and 1<=int(r['week'])<=maxweek]
            if not rows: raise RuntimeError('PBP file has no current regular-season games')
            break
        except Exception as exc:
            last_error=exc
    else:
        raise RuntimeError('Could not load current-year PBP for K/DST: '+str(last_error))

    games={}; kick={}; defenses={}
    for r in rows:
        gid=r['game_id']; week=int(r['week'])
        home=r.get('home_team',''); away=r.get('away_team','')
        if not home or not away: continue
        g=games.setdefault(gid,{'week':week,'home':home,'away':away,'hs':0,'as':0})
        # Final scores are the largest observed scoreboard values, not summed scores.
        g['hs']=max(g['hs'],_number(r,'home_score'))
        g['as']=max(g['as'],_number(r,'away_score'))
        for team in (home,away): defenses.setdefault((gid,team),0.0)
        kicking_team=r.get('posteam','')
        kicker=(r.get('kicker_player_name') or '').strip()
        if kicker and kicking_team:
            k=(gid,kicking_team,kicker)
            if r.get('field_goal_result')=='made':
                dist=_number(r,'kick_distance')
                if dist>0: kick[k]=kick.get(k,0)+(5 if dist>=50 else 4 if dist>=40 else 3)
            if r.get('extra_point_result')=='good':
                kick[k]=kick.get(k,0)+1
        defense=r.get('defteam','')
        if not defense or (gid,defense) not in defenses: continue
        # A sack and an interception are separate scoring events.
        defenses[(gid,defense)]+=_number(r,'sack')+2*_number(r,'interception')
        defenses[(gid,defense)]+=2*_number(r,'fumble_lost')
        defenses[(gid,defense)]+=6*_number(r,'def_td')+2*_number(r,'safety')
        # Blocked kicks and return TDs are included only when reliably flagged.
        if 'blocked_kick' in r: defenses[(gid,defense)]+=2*_number(r,'blocked_kick')
    kick_weeks={}; defense_weeks={}
    for (gid,team,name),points in kick.items():
        kick_weeks.setdefault((team,name),[]).append((games[gid]['week'],points))
    for (gid,team),points in defenses.items():
        g=games[gid]
        allowed=g['as'] if team==g['home'] else g['hs']
        # DK defense points-allowed tiers; uses final opponent score as a proxy.
        pa=10 if allowed==0 else 7 if allowed<=6 else 4 if allowed<=13 else 1 if allowed<=20 else 0 if allowed<=27 else -1 if allowed<=34 else -4
        defense_weeks.setdefault(team,[]).append((g['week'],points+pa))
    output=[]
    for (team,name),values in kick_weeks.items():
        if max(w for w,_ in values)<maxweek-5: continue
        d=_distribution(values,name,team,'K')
        if d: output.append(d)
    for team,values in defense_weeks.items():
        if max(w for w,_ in values)<maxweek-5: continue
        d=_distribution(values,team+' DST',team,'DST')
        if d: output.append(d)
    if not any(p['position']=='K' for p in output) or not any(p['position']=='DST' for p in output):
        raise RuntimeError('PBP lacks sufficient kicker or defense scoring records; not publishing incomplete K/DST data')
    return output,url

def main():
    current_season=datetime.datetime.now(datetime.timezone.utc).year
    url=URL_TEMPLATE.format(season=current_season)
    req=urllib.request.Request(url,headers={'User-Agent':'GridironLab/5.1'})
    with urllib.request.urlopen(req,timeout=60) as r: content=r.read().decode('utf-8-sig')
    rows=list(csv.DictReader(io.StringIO(content)))
    if not rows: raise RuntimeError('NFL dataset is empty; preserving last published data')
    # Never silently publish a stale season as if it were current.
    season=current_season
    filtered=[r for r in rows if str(r.get('season',''))==str(season) and (r.get('season_type') or 'REG')=='REG' and str(r.get('week','')).isdigit()]
    if not filtered:
        raise RuntimeError(f'No current-season regular-season player data in {url}; existing file preserved')
    maxweek=max(int(r['week']) for r in filtered)
    if maxweek < 1 or maxweek > 18:
        raise RuntimeError('Invalid week value; existing file preserved')
    # The new stats_player release uses team instead of recent_team.
    for r in filtered:
        if not r.get('recent_team'):
            r['recent_team']=r.get('team','')
        if not r.get('player_display_name'):
            r['player_display_name']=r.get('player_name','')
        if not r.get('fantasy_points_ppr'):
            # Don't invent scoring when the expected column is absent.
            if 'fantasy_points_ppr' not in r:
                raise RuntimeError('Source schema lacks fantasy_points_ppr; existing file preserved')
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
        name=r.get('player_display_name') or r.get('player_name') or ''
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
        sorted_pts=sorted(pts)
        p90=sorted_pts[min(len(sorted_pts)-1, int(0.9*(len(sorted_pts)-1)+0.999999))]
        std=statistics.pstdev(pts) if len(pts)>1 else 0.0
        players.append({'ppr_p90':round(p90,2),'ppr_stddev':round(std,2),'name':name,'team':team,'position':pos,'historical_ppr_avg':avg,'games':len(pts),'last_week':games[-1][0], 'recent_ppr_avg':round(sum(pts[-3:])/len(pts[-3:]),2)})
    if not players: raise RuntimeError('No usable player records; preserving last published data')
    special, special_source=load_special_teams(season,maxweek)
    players.extend(special)
    print('Added',sum(p['position']=='K' for p in special),'kickers and',sum(p['position']=='DST' for p in special),'defenses')
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({'season':season,'through_week':maxweek,'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':url,'special_teams_source':special_source,'special_teams_scoring':'Estimated DK K/DST game scores from PBP; DST points allowed approximated from final opponent score','metric':'Historical PPR player game points and defense positional points allowed; projections are estimates, not DraftKings scoring','players':players,'defense_allowed_by_position':def_avgs,'league_allowed_by_position':league_avgs,'current_season_available':True},separators=(',',':')))
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
