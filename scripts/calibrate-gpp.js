/** GPP lineup ranking calibration. No changes to projection model. */
const WEIGHTS = Object.freeze({
  baseline: [0.45, 0.25, 0.20, 0.10],
  mean: [0, 0, 1, 0],
  p90: [1, 0, 0, 0],
  ceiling: [0, 0, 0, 1],
  balanced: [0.25, 0.25, 0.25, 0.25],
  conservative: [0.2, 0.4, 0.3, 0.1],
  upside: [0.3, 0.1, 0.1, 0.5]
});
function features(l) {
  return [l.modeled_p90, l.modeled_mean ?? l.projected, l.projected, l.modeled_ceiling ?? l.ceiling];
}
function score(l, w) {
  const f = features(l);
  if (f.some(x => !Number.isFinite(x))) throw new Error("Missing ranking feature");
  return f.reduce((s, x, i) => s + x * w[i], 0);
}
function select(lines, w) {
  if (!lines.length) throw new Error("No GPP candidates");
  return [...lines].sort((a,b) => score(b,w)-score(a,w) || a.index-b.index)[0];
}
function calibrate(games) {
  if (games.length < 4 || new Set(games.map(g=>g.game_id)).size !== games.length)
    return {enabled:false,reason:"Need four independent games"};
  if (games.some(g=>!g.lineups?.length || g.lineups.some(l=>!Number.isFinite(l.actual) || !Number.isFinite(l.modeled_p90) || !Number.isFinite(l.projected) || !Number.isFinite(l.modeled_ceiling ?? l.ceiling))))
    return {enabled:false,reason:"Missing actual scores"};
  const names=Object.keys(WEIGHTS).filter(n=>n!=="baseline");
  const baseline=games.map(g=>select(g.lineups,WEIGHTS.baseline).actual);
  const heldOut=games.map((game,i)=>{
    const train=games.filter((_,j)=>j!==i);
    const ranked=names.map(name=>({
      name,trainLift:train.reduce((sum,g)=>sum+select(g.lineups,WEIGHTS[name]).actual-select(g.lineups,WEIGHTS.baseline).actual,0)
    })).sort((a,b)=>b.trainLift-a.trainLift||a.name.localeCompare(b.name));
    const choice=ranked[0].trainLift>0?ranked[0].name:"baseline";
    const actual=select(game.lineups,WEIGHTS[choice]).actual;
    return {game:game.game_id,selected:choice,trainLift:ranked[0].trainLift,actual,baseline:baseline[i],lift:actual-baseline[i]};
  });
  const meanLift=heldOut.reduce((sum,x)=>sum+x.lift,0)/heldOut.length;
  const noLoss=heldOut.every(x=>x.lift>=0);
  const positiveFolds=heldOut.filter(x=>x.lift>0).length;
  const sameCandidate=heldOut.every(x=>x.selected===heldOut[0].selected && x.selected!=="baseline");
  // No deployment based on one lucky slate or a candidate chosen with held-out information.
  const enabled=meanLift>0 && noLoss && positiveFolds>=2 && sameCandidate;
  return {enabled,selected:enabled?heldOut[0].selected:"baseline",
    baselineMean:baseline.reduce((a,b)=>a+b,0)/baseline.length,
    meanLift,heldOut,reason:enabled?"Independent held-out gains verified":"Insufficient consistent out-of-sample improvement"};
}
module.exports = {WEIGHTS, features, score, select, calibrate};
