const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const script = fs.readFileSync('backend/static/js/properties.js', 'utf8');
function setup({changed=false, ok=true, token='synthetic-token'}={}) {
  const button={dataset:{propertyId:'7',address:JSON.stringify(['Ejemplo','10','Elche'])},disabled:false};
  const nodes={'property-location-button':button,street:{value:changed?'Otra':'Ejemplo'},street_number:{value:'10'},city:{value:'Elche'}};
  const requests=[], errors=[], forms=[];
  const ctx={document:{addEventListener(){},getElementById:id=>nodes[id],
    body:{append:f=>forms.push(f)},createElement:()=>({children:[],append(n){this.children.push(n)},submit(){this.submitted=true}})},
    RMNotification:{error:m=>errors.push(m)},
    fetch:async(...args)=>{requests.push(args);return {ok,text:async()=>''}},
    DOMParser:class {parseFromString(){return {querySelector:()=>token?{value:token}:null}}}};
  vm.createContext(ctx);vm.runInContext(script,ctx);
  return {button,nodes,requests,errors,forms,run:()=>ctx.updatePropertyLocation()};
}
test('uses saved address and protected POST; never places token in URL',async()=>{
 const s=setup();await s.run();assert.equal(s.requests[0][0],'/properties/7/geolocation');
 assert.equal(s.forms[0].action,'/properties/7/geolocation/retry');assert.equal(s.forms[0].method,'post');
 assert.equal(s.forms[0].children[0].value,'synthetic-token');assert.ok(s.forms[0].submitted);
 await s.run();assert.equal(s.requests.length,1);
});
test('unsaved physical address must be saved first',async()=>{
 const s=setup({changed:true});await s.run();assert.equal(s.requests.length,0);assert.equal(s.forms.length,0);assert.match(s.errors[0],/Guarda primero/);
});
test('failed review and missing CSRF cannot submit',async()=>{
 for(const options of [{ok:false},{token:null}]) {const s=setup(options);await s.run();assert.equal(s.forms.length,0);assert.equal(s.button.disabled,false);assert.equal(s.errors.length,1)}
});
