const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {price} = require('../../backend/public/static/catalog-map.js');
test('Spanish monthly prices and missing prices', () => {
  assert.equal(price('395'),'395 €/mes');
  assert.equal(price('395.50'),'395,5 €/mes');
  for (const value of [null,undefined,'',0,'no']) assert.equal(price(value),'Consultar precio');
});
function harness(properties,failAssets=false) {
 class El {
  constructor(){this.children=[];this.listeners={};this.style={};}
  append(...elements){this.children.push(...elements);}
  addEventListener(name,fn){this.listeners[name]=fn;}
  setAttribute(name,value){this[name]=value;}
  focus(options){this.focused=options;}
 }
 const open=new El(),close=new El(),status=new El(),canvas=new El(),dialog=new El();
 dialog.dataset={mapPayload:JSON.stringify({properties,omitted:0,tiles:'https://tiles.example.invalid/{z}/{x}/{y}'})};
 dialog.querySelector=s=>({'[data-map-close]':close,'[data-map-status]':status,'[data-map-canvas]':canvas}[s]);
 dialog.showModal=()=>{dialog.open=true;};
 dialog.close=()=>{dialog.open=false;dialog.listeners.close();};
 const body=new El(); body.style.overflow='auto'; const assets=[];
 const document={body,head:{append(el){assets.push(el);queueMicrotask(()=>failAssets?el.onerror():el.onload());}},createElement:()=>new El(),querySelector:s=>s==='[data-catalog-map]'?dialog:open};
 const window={scrollY:500,scrollTo(x,y){this.scrollY=y;}};
 const markers=[], tiles={on(event,fn){this[event]=fn;return this;},addTo(){return this;}};
 const L={map:()=>({fitBounds(){},invalidateSize(){}}),tileLayer:()=>tiles,divIcon:x=>x,marker(point,options){const m={point,options,addTo(){return this;},bindPopup(content){this.popup=content;return this;}};markers.push(m);return m;}};
 vm.runInNewContext(fs.readFileSync('backend/public/static/catalog-map.js','utf8'),{document,window,L,Intl,Number,JSON,encodeURIComponent});
 return {open:()=>open.listeners.click(),close:()=>close.listeners.click(),dialog,assets,markers,status,body,window,tiles,button:open};
}
const property={name:'Finca Demo',latitude:38,longitude:-.7,rooms:[{title:'<script>texto</script>',slug:'demo',price:'395',image:'/media/demo'}]};
test('Open/close is lazy, preserves scroll and renders safe room links and prices', async()=>{
 const h=harness([property]); assert.equal(h.assets.length,0);
 await h.open(); assert.equal(h.assets.length,2); assert.equal(h.dialog.open,true);
 assert.equal(h.markers.length,1);
 const details=h.markers[0].popup.children[1].children[1];
 assert.equal(details.children[0].textContent,'<script>texto</script>');
 assert.equal(details.children[1].textContent,'395 €/mes');
 assert.equal(details.children[2].href,'/habitaciones/demo');
 h.window.scrollY=0;h.close();assert.equal(h.window.scrollY,500);assert.equal(h.body.style.overflow,'auto');
 assert.equal(h.button.focused.preventScroll,true);
 await h.open(); assert.equal(h.assets.length,2);assert.equal(h.markers.length,1);
});
test('Empty locations never load external maps',async()=>{
 const h=harness([]);await h.open();assert.equal(h.assets.length,0);assert.match(h.status.textContent,/No hay habitaciones/);
});
test('Asset failures and tile failures retain the catalog fallback',async()=>{
 const broken=harness([property],true);await broken.open();assert.match(broken.status.textContent,/No se ha podido cargar/);broken.close();
 const h=harness([property]);await h.open();h.tiles.tileerror();assert.match(h.status.textContent,/temporalmente/);h.close();
});
