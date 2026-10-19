"""Publish schedule only. ESPN schedule is not an injury or DK salary source."""
import json,urllib.request,datetime,pathlib
now=datetime.datetime.now(datetime.timezone.utc)
url='https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates='+now.strftime('%Y%m%d')+'-'+(now+datetime.timedelta(days=8)).strftime('%Y%m%d')+'&limit=100'
req=urllib.request.Request(url,headers={'User-Agent':'GridironLab/8.2'})
with urllib.request.urlopen(req,timeout=35) as response: raw=json.load(response)
games=[]
for e in raw.get('events',[]):
 try:
  comp=e['competitions'][0]['competitors']; teams={x['homeAway']:x['team']['abbreviation'].upper() for x in comp}
  if len(teams)!=2: continue
  games.append({'id':str(e['id']),'away':teams['away'],'home':teams['home'],'kickoff_utc':e['date']})
 except (KeyError,IndexError,TypeError):continue
if not games: raise RuntimeError('No schedule events returned; refusing to replace existing data')
out=pathlib.Path(__file__).parent/'data'/'nfl_matchups.json';out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({'updated_utc':now.isoformat(),'games':games},indent=2))
print('Published',len(games),'games')
