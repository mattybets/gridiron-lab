const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const html=fs.readFileSync(require("node:path").join(__dirname,"..","index.html"),"utf8");
const start=html.indexOf("function selectDistinctGpp(");
const end=html.indexOf("\nfunction lineupKey(",start);
assert.ok(start>=0 && end>start,"GPP selector must exist");
const selector=html.slice(start,end);
const context={ $:id=>({value:id==="captainexposure"?"40":"100"}), lineupKey:l=>l.map(x=>x.slot+":"+x.p.name+"|"+x.p.team).sort().join(";") };
vm.createContext(context);
vm.runInContext(selector+";globalThis.selectDistinctGpp=selectDistinctGpp",context);
const names=["Purdy","Daniels","McCaffrey","Kittle","White","Burks","Okonkwo","Evans","Stevens","Cooks"];
const candidates=[];
for(let i=0;i<60;i++){
 const captain=i<30?"Purdy":names[1+i%8];
 const rest=names.filter(n=>n!==captain);
 const flex=[...rest.slice(i%4,i%4+5)];
 candidates.push({l:[{slot:"CPT",p:{name:captain,team:"A"}},...flex.map(name=>({slot:"FLEX",p:{name,team:"B"}}))]});
}
const selected=context.selectDistinctGpp(candidates,5,5,"showdown");
const counts={};
for(const x of selected){const captain=x.l.find(v=>v.slot==="CPT").p.name;counts[captain]=(counts[captain]||0)+1}
assert.equal(selected.length,5,"Should fill five lineups when diverse candidates exist");
assert.ok(Object.values(counts).every(n=>n<=2),"No captain can exceed 40% of five entries");
console.log("PASS: GPP captain hard exposure",JSON.stringify(counts));
