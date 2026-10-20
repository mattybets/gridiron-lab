/** Leave-one-game-out player projection audit; excludes unverified zero outcomes. */
const fs=require("node:fs"),path=require("node:path");
const data=JSON.parse(fs.readFileSync(path.join(__dirname,"../data/backtests/positive-scorer-projection-fixture.json"),"utf8"));
const games=data.games;
if(games.length<4||new Set(games.map(g=>g.id)).size!==games.length)throw Error("Need four independent games");
const factors=[0.7,0.8,0.9,1,1.1,1.2,1.3];
const mae=(rows,k)=>rows.reduce((s,[,p,a])=>s+Math.abs(p*k-a),0)/rows.length;
const folds=games.map((g,i)=>{
 const train=games.filter((_,j)=>j!==i).flatMap(x=>x.rows);
 const selected=[...factors].sort((a,b)=>mae(train,a)-mae(train,b)||Math.abs(a-1)-Math.abs(b-1))[0];
 return {game:g.id,training_games:games.length-1,n:g.rows.length,selected_factor:selected,baseline_mae:mae(g.rows,1),candidate_mae:mae(g.rows,selected)};
});
const baseline=folds.reduce((s,x)=>s+x.baseline_mae,0)/folds.length;
const candidate=folds.reduce((s,x)=>s+x.candidate_mae,0)/folds.length;
const passed=candidate<baseline&&folds.every(x=>x.candidate_mae<=x.baseline_mae);
const result={games:games.length,players:games.reduce((s,g)=>s+g.rows.length,0),baseline_mae:baseline,candidate_mae:candidate,mae_improvement:baseline-candidate,approved:passed,folds,scope:"Positive-scoring matched players only. Does not evaluate participation, zero scores, lineup ROI or profitability."};
if(require.main===module)console.log(JSON.stringify(result,null,2));
module.exports={evaluate:()=>result};
