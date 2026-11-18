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
  addEventListener(event,fn){this[event]=fn;}
  getBoundingClientRect(){return {top:100,bottom:150};}
}
const token='x'.repeat(43);
const data={start:'2026-11-01',end:'2026-11-05',last_day:'2026-11-04',properties:[{name:'Synthetic property',rooms:[{name:'Synthetic room',slug:'synthetic',listing_url:'/habitaciones/synthetic',available_from:'2026-11-04',occupied:[{start:'2026-11-02',end:'2026-11-04'}]}]}]};
async function setup(hash='#'+token,payload=data){
  const nodes=Object.fromEntries(['calendar-status','calendar-scroll','calendar-period','calendar-previous','calendar-next','calendar-navigation','calendar-month','calendar-header','calendar-mobile-weeks','calendar-sort-property','calendar-sort-availability'].map(id=>[id,new Element('div')]));
  const calls=[],listeners={},location={hash};let refresh;
  const state={ok:true};
  const viewport={scrollY:900,matchMedia:()=>({matches:true}),scrollTo:options=>{viewport.scrollY=options.top;},addEventListener:(event,fn)=>listeners[event]=fn};
  vm.runInNewContext(script,{document:{getElementById:id=>nodes[id],createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)},location,window:viewport,Intl,Date,
    fetch:async(url,options)=>{calls.push({url,options});return {ok:state.ok,json:async()=>payload};},setInterval:fn=>refresh=fn});
  await new Promise(resolve=>setImmediate(resolve));
  return {nodes,calls,state,refresh,listeners,location,viewport};
}
function all(node){return [node,...node.children.flatMap(all)];}
test('anonymous read-only request and no legacy token in links or rendered DOM',async()=>{
  const x=await setup();assert.equal(x.calls.length,1);
  assert.equal(x.calls[0].options.method,'GET');assert.equal(x.calls[0].options.headers,undefined);
  assert.equal(x.calls[0].options.credentials,'omit');
  assert.equal(x.calls[0].options.cache,'no-store');assert.equal(x.calls[0].options.referrerPolicy,'no-referrer');
  assert.ok(!JSON.stringify(x.nodes).includes(token));
  const link=all(x.nodes['calendar-scroll']).find(n=>n.tag==='a');
  assert.equal(link.href,'/habitaciones/synthetic');assert.equal(link.title,'Ver anuncio de esta habitación');assert.equal(link.rel,'noopener noreferrer');
  assert.equal(link.children[1].textContent,'synthetic');assert.equal(link.target,'_blank');
});
test('temporary gaps not offered, exclusive checkout and partial clipped week',async()=>{
  const x=await setup();
  const cells=all(x.nodes['calendar-scroll']).filter(n=>n.tag==='td');
  assert.match(cells[1].title,/1 de 3 días disponibles/);
  assert.match(cells[0].title,/semana limitada/);
});

test('Monday month grouping, full weeks and exact availability date',async()=>{
  const payload=structuredClone(data);payload.start='2026-10-26';payload.end='2026-11-16';payload.last_day='2026-11-15';
  const room=payload.properties[0].rooms[0];room.available_from='2026-11-04';room.thumbnail_url='/media/synthetic/320.webp';
  const x=await setup('',payload), nodes=all(x.nodes['calendar-scroll']);
  assert.deepEqual(nodes.filter(n=>n.tag==='svg').map(n=>n.children.map(r=>[r.class,r.width])),[[['day-unavailable','7']],[['day-unavailable','2'],['day-available','5']],[['day-available','7']]]);
  assert.ok(nodes.some(n=>n.title==='26/10/2026 – 1/11/2026'));
  assert.ok(nodes.some(n=>n.textContent==='Disponible desde 4/11/2026'));
  assert.equal(nodes.find(n=>n.tag==='img').src,room.thumbnail_url);
});

test('one day clipped week available counts only in-range day and no photo placeholder',async()=>{
  const payload=structuredClone(data);payload.end='2026-11-02';payload.last_day=payload.start;
  payload.properties[0].rooms[0].available_from=payload.start;payload.properties[0].rooms[0].occupied=[];
  const nodes=all((await setup('',payload)).nodes['calendar-scroll']);
  assert.match(nodes.find(n=>n.tag==='td').title,/1 de 1 días disponibles/);
  assert.equal(nodes.filter(n=>n.tag==='img').length,0);
  assert.ok(nodes.some(n=>n.className==='room-thumbnail'));
});
test('refresh preserves scroll and failed request clears stale data',async()=>{
  const x=await setup(),region=x.nodes['calendar-scroll'];region.scrollLeft=200;await x.refresh();assert.equal(region.scrollLeft,200);
  x.state.ok=false;await x.refresh();assert.equal(region.children.length,0);assert.equal(region.hidden,true);
});
test('bare URL works without fragment, token or session',async()=>{
  const x=await setup('');assert.equal(x.calls.length,1);
  assert.equal(x.nodes['calendar-scroll'].hidden,false);
});

test('month arrows, limits and refresh preserve selection',async()=>{
  const x=await setup('');
  assert.equal(x.nodes['calendar-previous'].disabled,true);
  assert.match(x.nodes['calendar-month'].textContent,/octubre/);
  assert.equal(x.nodes['calendar-header'].hidden,false);
  assert.match(x.nodes['calendar-mobile-weeks'].children[0].title,/1\/11\/2026/);
  x.nodes['calendar-scroll'].scrollTop=900;
  x.nodes['calendar-next'].click();
  assert.match(x.nodes['calendar-month'].textContent,/noviembre/);
  assert.match(x.nodes['calendar-mobile-weeks'].children[0].title,/2\/11\/2026/);
  assert.equal(x.nodes['calendar-scroll'].scrollTop,900);
  assert.equal(x.viewport.scrollY,900);
  assert.equal(x.nodes['calendar-next'].disabled,true);
  await x.refresh();assert.match(x.nodes['calendar-month'].textContent,/noviembre/);
  const selected=all(x.nodes['calendar-scroll']).filter(n=>n.tag==='td'&&n.className.includes('selected-week'));
  assert.equal(selected.length,1);
  x.nodes['calendar-previous'].click();assert.match(x.nodes['calendar-month'].textContent,/octubre/);
});

test('chronological proportional segments merge equal days without seams',async()=>{
  const payload=structuredClone(data);payload.start='2026-11-02';payload.end='2026-11-09';payload.last_day='2026-11-08';
  const room=payload.properties[0].rooms[0];room.available_from=payload.start;
  room.occupied=[{start:'2026-11-02',end:'2026-11-04'},{start:'2026-11-06',end:'2026-11-07'}];
  const svg=all((await setup('',payload)).nodes['calendar-scroll']).find(n=>n.tag==='svg');
  assert.equal(svg.viewBox,'0 0 7 1');
  assert.deepEqual(svg.children.map(r=>[r.x,r.width,r.class]),[['0','2','day-unavailable'],['2','2','day-available'],['4','1','day-unavailable'],['5','2','day-available']]);
});

test('missing slug uses existing title without generating slug',async()=>{
  const payload=structuredClone(data);delete payload.properties[0].rooms[0].slug;
  const link=all((await setup('',payload)).nodes['calendar-scroll']).find(n=>n.tag==='a');
  assert.equal(link.children[1].textContent,'Synthetic room');assert.equal(link.href,'/habitaciones/synthetic');
});

test('availability order uses today, future date then slug; missing/out-of-range last; property restores exact order',async()=>{
  const make=(slug,date)=>({slug,name:slug,listing_url:'/habitaciones/'+slug,available_from:date,occupied:[]});
  const payload={...structuredClone(data),end:'2027-05-01',properties:[
    {name:'A',rooms:[make('z-future','2026-12-01'),make('z-now','2026-10-01'),make('missing',null)]},
    {name:'B',rooms:[make('a-future','2026-12-01'),make('a-now','2026-11-01'),make('later','2027-04-01'),make('outside','2027-06-01')]}
  ]};
  const x=await setup('',payload);
  const order=()=>all(x.nodes['calendar-scroll']).filter(n=>n.tag==='a').map(n=>n.children[1].textContent);
  const initial=order();
  x.nodes['calendar-sort-availability'].click();
  assert.deepEqual(order(),['a-now','z-now','a-future','z-future','later','missing','outside']);
  assert.equal(x.nodes['calendar-sort-availability']['aria-pressed'],'true');
  const selected=x.nodes['calendar-month'].textContent;
  x.nodes['calendar-sort-property'].click();assert.deepEqual(order(),initial);
  assert.equal(x.nodes['calendar-month'].textContent,selected);
  x.nodes['calendar-sort-availability'].click();const sorted=order();
  x.nodes['calendar-next'].click();assert.deepEqual(order(),sorted);
  await x.refresh();assert.deepEqual(order(),sorted);
  assert.equal(x.viewport.scrollY,900);
});

test('sort and month controls share the only mobile sticky header',()=>{
  const html=fs.readFileSync('backend/public/templates/collaborator_calendar.html','utf8');
  const css=fs.readFileSync('backend/public/static/collaborator-calendar.css','utf8');
  assert.match(html,/id="calendar-header"[\s\S]*id="calendar-sort-property"[\s\S]*id="calendar-navigation"[\s\S]*id="calendar-mobile-weeks"/);
  assert.match(css,/\.calendar-header \{ position:sticky; top:0;/);
  assert.match(css,/\.calendar-sort button:focus-visible/);
});

test('monthly price uses Spanish formatting below linked identity without changing link or availability',async()=>{
  for (const [price,label] of [['395.00','395 €/mes'],['350.50','350,5 €/mes'],[null,'Consultar precio'],['','Consultar precio'],[undefined,'Consultar precio']]) {
    const payload=structuredClone(data);payload.properties[0].rooms[0].price_monthly=price;
    const x=await setup('',payload);
    const identity=all(x.nodes['calendar-scroll']).find(n=>n.tag==='th' && n.children.some(c=>c.tag==='a'));
    assert.equal(identity.children[0].tag,'a');
    assert.equal(identity.children[0].href,'/habitaciones/synthetic');
    assert.equal(identity.children[1].className,'room-price');
    assert.equal(identity.children[1].textContent,label);
    assert.equal(identity.children[1].tag,'small');
    assert.match(identity.children[2].textContent,/Disponible desde/);
    x.nodes['calendar-sort-availability'].click();x.nodes['calendar-next'].click();
    assert.equal(all(x.nodes['calendar-scroll']).find(n=>n.className==='room-price').textContent,label);
  }
});
