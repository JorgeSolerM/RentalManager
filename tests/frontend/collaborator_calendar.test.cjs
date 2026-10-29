const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const script=fs.readFileSync('backend/public/static/collaborator-calendar.js','utf8');
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.scrollLeft=0;this.scrollTop=0;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(key,value){this[key]=value;}
}
const token='x'.repeat(43);
const data={start:'2026-11-01',end:'2026-11-05',last_day:'2026-11-04',properties:[{name:'Synthetic property',rooms:[{name:'Synthetic room',listing_url:'/habitaciones/synthetic',available_from:'2026-11-04',occupied:[{start:'2026-11-02',end:'2026-11-04'}]}]}]};
async function setup(hash='#'+token){
  const nodes=Object.fromEntries(['calendar-status','calendar-scroll','calendar-period'].map(id=>[id,new Element('div')]));
  const calls=[],listeners={},location={hash};let refresh;
  const state={ok:true};
  vm.runInNewContext(script,{document:{getElementById:id=>nodes[id],createElement:tag=>new Element(tag)},location,window:{addEventListener:(event,fn)=>listeners[event]=fn},Intl,Date,
    fetch:async(url,options)=>{calls.push({url,options});return {ok:state.ok,json:async()=>data};},setInterval:fn=>refresh=fn});
  await new Promise(resolve=>setImmediate(resolve));
  return {nodes,calls,state,refresh,listeners,location};
}
function all(node){return [node,...node.children.flatMap(all)];}
test('read-only authenticated request and no token in links or rendered DOM',async()=>{
  const x=await setup();assert.equal(x.calls.length,1);
  assert.equal(x.calls[0].options.method,'GET');assert.equal(x.calls[0].options.headers.Authorization,'Bearer '+token);
  assert.equal(x.calls[0].options.cache,'no-store');assert.equal(x.calls[0].options.referrerPolicy,'no-referrer');
  assert.ok(!JSON.stringify(x.nodes).includes(token));
  const link=all(x.nodes['calendar-scroll']).find(n=>n.tag==='a');
  assert.equal(link.href,'/habitaciones/synthetic');assert.equal(link.title,'Ver anuncio de esta habitación');assert.equal(link.rel,'noopener noreferrer');
});
test('temporary gap is neutral, checkout exclusive and only terminal availability green',async()=>{
  const x=await setup();assert.deepEqual(all(x.nodes['calendar-scroll']).filter(n=>n.tag==='td').map(n=>n.className),['gap day','occupied day','occupied day','available day']);
});
test('refresh preserves scroll and revocation clears previous data',async()=>{
  const x=await setup(),region=x.nodes['calendar-scroll'];region.scrollLeft=200;await x.refresh();assert.equal(region.scrollLeft,200);
  x.state.ok=false;await x.refresh();assert.equal(region.children.length,0);assert.equal(region.hidden,true);
});
test('invalid link never fetches; adding fragment enables access without reload',async()=>{
  const x=await setup('');assert.equal(x.calls.length,0);
  x.location.hash='#'+token;await x.listeners.hashchange();assert.equal(x.calls.length,1);assert.equal(x.nodes['calendar-scroll'].hidden,false);
});
