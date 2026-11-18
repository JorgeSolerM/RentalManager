const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync('backend/static/js/property-geolocation.js', 'utf8');

function setup(hidden = false) {
  let handler, edits = [], focused = false, removed = false;
  const button = {dataset: {geoEdit:'9', geoCsrf:'synthetic-csrf'}};
  const form = {action:'', token:null, querySelector(){return this.token;}, append(n){this.token=n;}};
  const nodes = {
    'property-modal':{classList:{contains:()=>hidden}},
    'property-form':form,
    'property-delete-button':{classList:{add:()=>{removed=true;}}},
    street:{focus:()=>{focused=true;}},
  };
  vm.runInNewContext(script, {
    editProperty:async id=>{edits.push(id);},
    document:{querySelector:()=>({addEventListener:(_,fn)=>{handler=fn;}}),
      getElementById:id=>nodes[id],createElement:()=>({})}
  });
  return {button,form,edits,run:()=>handler.call(button),focused:()=>focused,removed:()=>removed};
}

test('reuses property editor, redirects only its form and focuses street', async()=>{
  const s=setup();await s.run();
  assert.deepEqual(s.edits,['9']);assert.equal(s.form.action,'/properties/9/geolocation/address');
  assert.equal(s.form.token.value,'synthetic-csrf');assert.equal(s.form.token.type,'hidden');
  assert.ok(s.focused() && s.removed());
});
test('repeated opens reuse one CSRF field',async()=>{
  const s=setup();await s.run();const token=s.form.token;await s.run();assert.equal(token,s.form.token);
});
test('failed property load does not redirect form or insert token',async()=>{
  const s=setup(true);await s.run();assert.equal(s.form.action,'');assert.equal(s.form.token,null);
});
