"""Free nflverse weekly player stats -> conservative historical DK PPG baselines.
No salary, ownership, injuries or forward-looking matchup adjustment is inferred.
"""
import csv, io, json, urllib.request, datetime, pathlib, statistics, gzip, collections
URL_TEMPLATE='https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv'
OUT=pathlib.Path(__file__).parent/'data'/'nfl_baselines.json'
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
        if not r.get('player_name'):
            r['player_name']=r.get('player_display_name','')
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
        name=r.get('player_name') or r.get('player_display_name') or ''
        team=r.get('recent_team') or ''
        pos=r.get('position') or ''
        if not name or not team or pos not in ('QB','RB','WR','TE'): continue
        try:
            pts=float(r.get('fantasy_points_ppr') or 0)
        except ValueError: continue
        key=(r.get('player_id') or name,team)
        usage={}
        for col in ('targets','carries','rushing_first_downs','receiving_tds','rushing_tds'):
            raw=r.get(col)
            try: usage[col]=float(raw) if raw not in (None,'') else None
            except (ValueError,TypeError): usage[col]=None
        by.setdefault(key,[]).append((int(r['week']),pts,name,pos,usage))
    # Count designed rush attempts inside the opponent's 20 from nflverse PBP.
    # Match using the same GSIS player_id as the weekly stats, not fuzzy names.
    redzone_by_player=collections.Counter()
    pbp_available=False
    kicker_games=collections.defaultdict(float)
    kicker_names={}
    defense_games_pbp=collections.defaultdict(float)
    defense_final_scores={}
    defense_teams=collections.defaultdict(set)
    pbp_url=f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz'
    try:
        pbp_req=urllib.request.Request(pbp_url,headers={'User-Agent':'GridironLab/5.1'})
        with urllib.request.urlopen(pbp_req,timeout=120) as response:
            with gzip.GzipFile(fileobj=response) as zipped:
                reader=csv.DictReader(io.TextIOWrapper(zipped,encoding='utf-8-sig'))
                required={'rusher_player_id','rush_attempt','yardline_100','week','season_type','posteam','defteam','kicker_player_id','kicker_player_name','field_goal_result','extra_point_result','kick_distance','sack','interception','fumble_lost','home_team','away_team','total_home_score','total_away_score'}
                if not required.issubset(reader.fieldnames or []):
                    raise ValueError('PBP missing required red-zone fields')
                for play in reader:
                    if play.get('season_type')!='REG':
                        continue
                    try:
                        week=int(play['week'])
                    except (TypeError,ValueError):
                        continue
                    if not maxweek-5<=week<=maxweek:
                        continue
                    home,away=play.get('home_team',''),play.get('away_team','')
                    defense=play.get('defteam','')
                    if home and away:
                        defense_teams[week].update((home,away))
                        try:
                            hs=int(float(play['total_home_score']))
                            aws=int(float(play['total_away_score']))
                            defense_final_scores[(week,home,away)]=(hs,aws)
                        except (TypeError,ValueError):
                            pass
                    def flag(field):
                        try: return float(play.get(field) or 0)==1
                        except (TypeError,ValueError): return False
                    if defense:
                        key=(week,defense)
                        if flag('sack'): defense_games_pbp[key]+=1
                        if flag('interception'): defense_games_pbp[key]+=2
                        if flag('fumble_lost'): defense_games_pbp[key]+=2
                        # PBP defensive touchdowns and special teams returns need
                        # separate attribution; don't invent them here.
                    kicker_id=(play.get('kicker_player_id') or '').strip()
                    if kicker_id:
                        team=play.get('posteam','')
                        if team:
                            key=(kicker_id,team,week)
                            kicker_names[(kicker_id,team)]=play.get('kicker_player_name') or kicker_id
                            if play.get('field_goal_result')=='made':
                                try: distance=float(play.get('kick_distance') or 0)
                                except (TypeError,ValueError): distance=0
                                kicker_games[key]+=5 if distance>=50 else 4 if distance>=40 else 3
                            elif play.get('field_goal_result')=='missed':
                                kicker_games[key]-=1
                            if play.get('extra_point_result')=='good':
                                kicker_games[key]+=1
                    if play.get('rush_attempt')=='1':
                        try: yards=float(play['yardline_100'])
                        except (TypeError,ValueError): continue
                        if 0<yards<=20:
                            player_id=(play.get('rusher_player_id') or '').strip()
                            if player_id: redzone_by_player[player_id]+=1
        pbp_available=True
        print('Loaded red-zone rush attempts for',len(redzone_by_player),'players')
    except Exception as exc:
        # Missing or incompatible PBP must not fabricate zero red-zone attempts.
        print('Red-zone play-by-play unavailable; redzone remains null:',exc)
    players=[]
    for (player_id,team),games in by.items():
        games.sort(); pts=[g[1] for g in games]; name=games[-1][2];pos=games[-1][3]
        if len(pts)<2: continue
        # historical baseline, not a forward prediction
        avg=round(sum(pts)/len(pts),2)
        sorted_pts=sorted(pts)
        p90=sorted_pts[min(len(sorted_pts)-1, int(0.9*(len(sorted_pts)-1)+0.999999))]
        std=statistics.pstdev(pts) if len(pts)>1 else 0.0
        usage_fields=('targets','carries')
        usage_totals={}
        for col in usage_fields:
            values=[g[4].get(col) for g in games]
            usage_totals[col]=round(sum(values),2) if all(v is not None for v in values) else None
        usage_totals['games']=len(games)
        # Red-zone carries come from PBP; zero is valid only when the PBP loaded.
        usage_totals['redzone']=redzone_by_player.get(player_id,0) if pbp_available and player_id else None
        players.append({'usage':usage_totals,'ppr_p90':round(p90,2),'ppr_stddev':round(std,2),'name':name,'team':team,'position':pos,'historical_ppr_avg':avg,'games':len(pts),'last_week':games[-1][0], 'recent_ppr_avg':round(sum(pts[-3:])/len(pts[-3:]),2)})
    if pbp_available:
        # PBP kicker scores and DST scores are conservative estimates, not
        # complete official DK scoring (notably defensive/return TDs).
        kicker_group=collections.defaultdict(list)
        for (pid,team,week),points in kicker_games.items():
            kicker_group[(pid,team)].append((week,points))
        for (pid,team),games in kicker_group.items():
            games.sort()
            if len(games)<2: continue
            points=[v for _,v in games]
            avg=sum(points)/len(points)
            players.append({'name':kicker_names.get((pid,team),pid),'team':team,'position':'K','historical_ppr_avg':round(avg,2),'recent_ppr_avg':round(sum(points[-3:])/len(points[-3:]),2),'ppr_p90':round(sorted(points)[min(len(points)-1,int(.9*(len(points)-1)+.999999))],2),'ppr_stddev':round(statistics.pstdev(points),2),'games':len(points),'last_week':games[-1][0],'usage':{'games':len(points),'targets':None,'carries':None,'redzone':None}})
        dst_group=collections.defaultdict(list)
        for (week,home,away),(hs,aws) in defense_final_scores.items():
            for team,allowed in ((home,aws),(away,hs)):
                base=10 if allowed==0 else 7 if allowed<=6 else 4 if allowed<=13 else 1 if allowed<=20 else 0 if allowed<=27 else -1 if allowed<=34 else -4
                dst_group[team].append((week,base+defense_games_pbp[(week,team)]))
        for team,games in dst_group.items():
            games.sort()
            if len(games)<2: continue
            points=[v for _,v in games]
            players.append({'name':team+' DST','team':team,'position':'DST','historical_ppr_avg':round(sum(points)/len(points),2),'recent_ppr_avg':round(sum(points[-3:])/len(points[-3:]),2),'ppr_p90':round(sorted(points)[min(len(points)-1,int(.9*(len(points)-1)+.999999))],2),'ppr_stddev':round(statistics.pstdev(points),2),'games':len(points),'last_week':games[-1][0],'usage':{'games':len(points),'targets':None,'carries':None,'redzone':None}})
        print('PBP position coverage:',sum(p['position']=='K' for p in players),'kickers,',sum(p['position']=='DST' for p in players),'defenses')
    if not players: raise RuntimeError('No usable player records; preserving last published data')
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({'season':season,'through_week':maxweek,'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':url,'redzone_source':pbp_url if pbp_available else None,'redzone_available':pbp_available,'metric':'Historical PPR player game points and defense positional points allowed; projections are estimates, not DraftKings scoring','players':players,'defense_allowed_by_position':def_avgs,'league_allowed_by_position':league_avgs,'current_season_available':True},separators=(',',':')))
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
