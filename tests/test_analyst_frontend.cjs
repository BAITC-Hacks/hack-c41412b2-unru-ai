// Pure renderer unit tests; no browser or network automation.
const {readFileSync}=require('node:fs');
const {runInNewContext}=require('node:vm');
const assert=require('node:assert/strict');
const source=readFileSync('web/app.js','utf8');
const renderer=source.slice(source.indexOf('function renderAnalystEvent('),source.indexOf('async function askAnalyst('));
const el=()=>({textContent:'',children:[],append(...nodes){this.children.push(...nodes)},replaceChildren(){this.children=[]}});
const elements={'ai-answer':el(),'ai-activity':el()};
const context={document:{createElement:el},$:id=>elements[id]};
runInNewContext(renderer,context);
assert.throws(()=>context.renderAnalystEvent({type:'result',answer:{why:'bad'}}));
assert.throws(()=>context.renderAnalystEvent({type:'error',message:'AI unavailable'}));
const text='<img src=x onerror=alert(1)>';
context.renderAnalystEvent({type:'result',answer:{conclusion:text,why:['A','B'],alternative:'distributor',evidence_against:'unknown',limitation:'limited',next_step:'request'},trace:[],model:'test',latency_seconds:1,notice:'test'});
assert.equal(elements['ai-answer'].children[0].children[1].textContent,text);
assert.equal(elements['ai-answer'].children[0].children[1].children.length,0);
console.log('3 frontend renderer checks passed (malformed/error/text-only output)');
