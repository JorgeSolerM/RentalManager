const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'../../backend/static/js/provider_settings.js'),'utf8');
function setup(initial, fetch, provider=false) {
 const muted={}; const feedback={}; const toasts=[];
 const input={checked:initial,disabled:false,dataset:{categoryName:'Ejemplo',url:'/providers/categories/1/active'},
  attrs:{'aria-checked':String(initial)},
  getAttribute(k){return this.attrs[k]},setAttribute(k,v){this.attrs[k]=v},
  addEventListener(e,fn){this.handler=fn},
  closest(){return {querySelector:s=>({classList:{toggle:(c,v)=>{muted[s]=v}}})}}
 };
 if(provider) input.dataset={providerName:'Empresa de ejemplo',url:'/providers/1/active'};
 vm.runInNewContext(script,{document:{querySelector:()=>feedback,querySelectorAll:()=>[input]},fetch,URLSearchParams,
  RMToast:{success:m=>toasts.push(['success',m]),error:m=>toasts.push(['error',m])}});
 return {input,muted,feedback,toasts,async toggle(value){input.checked=value;await input.handler({detail:{checked:value}})}};
}
test('provider switch shares persistence, muted state and accessible feedback',async()=>{
 const f=setup(true,async()=>({ok:true,json:async()=>({active:false})}),true);await f.toggle(false);
 assert.equal(f.input.attrs['aria-label'],'Activar proveedor Empresa de ejemplo');
 assert.equal(f.muted['[data-provider-name]'],true);
 assert.deepEqual(f.toasts,[['success','Proveedor desactivado.']]);
});
test('provider failure restores switch',async()=>{
 const f=setup(false,async()=>({ok:false}),true);await f.toggle(true);
 assert.equal(f.input.checked,false);assert.equal(f.input.attrs['aria-checked'],'false');
 assert.match(f.feedback.textContent,/No se pudo cambiar el proveedor/);
});
test('switch persists OFF and displays accessible state and toast',async()=>{
 const f=setup(true,async(url,options)=>{assert.equal(options.body.get('active'),'0');return {ok:true,json:async()=>({active:false})}});
 await f.toggle(false);assert.equal(f.input.checked,false);assert.equal(f.input.attrs['aria-checked'],'false');
 assert.equal(f.input.attrs['aria-label'],'Activar categoría Ejemplo');assert.equal(f.muted['[data-category-name]'],true);
 assert.deepEqual(f.toasts,[['success','Categoría desactivada.']]);assert.equal(f.input.disabled,false);
});
test('switch persists ON and removes muted state',async()=>{
 const f=setup(false,async()=>({ok:true,json:async()=>({active:true})}));await f.toggle(true);
 assert.equal(f.input.attrs['aria-checked'],'true');assert.equal(f.muted['[data-category-order]'],false);
 assert.deepEqual(f.toasts,[['success','Categoría activada.']]);
});
for(const [name,fetch] of [['http',async()=>({ok:false})],['network',async()=>{throw Error('offline')}],['invalid-json',async()=>({ok:true,json:async()=>({})})]]){
 test(name+' failure restores previous state and reports controlled error',async()=>{
  const f=setup(true,fetch);await f.toggle(false);assert.equal(f.input.checked,true);
  assert.equal(f.input.attrs['aria-checked'],'true');assert.equal(f.input.disabled,false);
  assert.equal(f.toasts[0][0],'error');assert.match(f.feedback.textContent,/No se pudo/);
 });
}
