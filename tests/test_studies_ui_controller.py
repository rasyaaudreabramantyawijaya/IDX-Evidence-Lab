import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_late_response_cancel_and_mismatched_widget_do_not_replace_result():
    code=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
vm.runInThisContext(fs.readFileSync('docs/prototypes/studies-ui.js','utf8'));
let config={target_kind:'issuer',targets:['BBCA'],window:'20'},pending=[];
const c=StudiesUI.createController({config:()=>config,changed:()=>{},transport:request=>new Promise(resolve=>pending.push({request,resolve}))});
const reply=(id,value)=>({widget_id:id,status:'READY',request_fingerprint:'x',metrics:[{value}],series:[],tables:[]});
(async()=>{
 const a=c.run({id:'p',type:'price_risk'});
 config={...config,targets:['BBRI']};c.invalidate();
 const b=c.run({id:'p',type:'price_risk'});
 pending[1].resolve(reply('price_risk',2));await b;
 pending[0].resolve(reply('price_risk',1));await a;
 assert.equal(c.states.p.result.metrics[0].value,2);
 const d=c.run({id:'p',type:'price_risk'});c.cancel('p');pending[2].resolve(reply('price_risk',3));await d;
 assert.equal(c.states.p.status,'CANCELLED');
 const e=c.run({id:'p',type:'price_risk'});pending[3].resolve(reply('other',4));await e;
 assert.equal(c.states.p.status,'ERROR');
 assert(!StudiesUI.renderResult({status:'READY',metrics:[{id:'<script>x</script>',value:1,unit:'IDR'}],series:[],tables:[],warnings:[]}).includes('<script>'));
 const queue=[];
 const batch=StudiesUI.createController({config:()=>config,changed:()=>{},transport:r=>new Promise(resolve=>queue.push({r,resolve}))});
 const all=batch.runAll([{id:'a',type:'price_risk'},{id:'b',type:'price_risk'}]);
 batch.invalidate();queue[0].resolve(reply('price_risk',1));
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(queue.length,1,'Invalidated batch must not start subsequent panels');
 await all;
})().catch(e=>{console.error(e);process.exit(1)});
"""
    result=subprocess.run(['node','-e',code],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
