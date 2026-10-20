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
  if (games.length < 4 || new Set(games.map(g => g.game_id)).size !== games.length)
    return {enabled:false,reason:"Need four independent games"};
  if (games.some(g => !g.lineups?.length || g.lineups.some(l => !Number.isFinite(l.actual))))
    return {enabled:false,reason:"Missing actual scores"};
  const base = games.map(g => select(g.lineups, WEIGHTS.baseline).actual);
  const candidates = Object.entries(WEIGHTS).filter(([k]) => k !== "baseline").map(([name,w]) => {
    const heldOut = games.map((g,i) => {
      const training = games.filter((_,j) => i !== j);
      const trainLift = training.reduce((s,t) => s + select(t.lineups,w).actual - select(t.lineups,WEIGHTS.baseline).actual,0);
      return {game:g.game_id,trainLift,actual:select(g.lineups,w).actual,baseline:base[i]};
    });
    const lift = heldOut.reduce((s,x)=>s+x.actual-x.baseline,0)/heldOut.length;
    return {name,meanLift:lift,worstLift:Math.min(...heldOut.map(x=>x.actual-x.baseline)),heldOut};
  }).sort((a,b)=>b.meanLift-a.meanLift);
  const best = candidates[0];
  // Four games is exploratory: do not auto-enable unless all independent held-out games improve.
  const approved = best.meanLift > 0 && best.worstLift >= 0 && best.heldOut.every(x=>x.trainLift>0);
  return {enabled:approved,selected:approved?best.name:"baseline",baselineMean:base.reduce((a,b)=>a+b,0)/base.length,candidates,reason:approved?"All folds improved; still small-sample":"No consistently superior held-out ranker"};
}
module.exports = {WEIGHTS, features, score, select, calibrate};
