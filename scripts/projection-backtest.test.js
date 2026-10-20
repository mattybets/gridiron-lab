const assert=require("node:assert/strict");
const r=require("./projection-backtest").evaluate();
assert.equal(r.games,4);
assert.equal(r.players,80);
assert.equal(r.folds.length,4);
assert.equal(r.approved,false,"Do not deploy calibration that fails held-out MAE");
assert.ok(r.mae_improvement<0,"Historical scale correction should fail out-of-sample");
assert.ok(r.folds.every(x=>x.training_games===3));
console.log("PASS projection backtest: failed calibration correctly blocked",JSON.stringify({baseline:r.baseline_mae,candidate:r.candidate_mae,improvement:r.mae_improvement}));
