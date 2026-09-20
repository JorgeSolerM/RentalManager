// Run with node --test tests/frontend/expense_category_autofill.test.cjs.
// Execute the production form script; no browser framework or dependencies.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '../../backend/static/js/expense_form.js'), 'utf8');

function formState(initialCategory='', initialProvider='') {
  const fields = {};
  for (const name of ['category_id','provider_id','property_id','expense_date','owner_id','borne_by','imputation']) {
    fields[name] = {value:'',dataset:{},options:[],listeners:{},addEventListener(event,fn){this.listeners[event]=fn;},replaceChildren(){}};
  }
  fields.category_id.options = ['', 'cleaning', 'repair', 'other'].map(value=>({value}));
  fields.category_id.value = initialCategory;
  fields.provider_id.value = initialProvider;
  const defaults = {a:'cleaning',b:'repair',none:'',inactive:'archived'};
  Object.defineProperty(fields.provider_id,'selectedOptions',{get(){return [{dataset:{category:defaults[this.value]||''}}];}});
  const form = {elements:{namedItem:name=>fields[name]},querySelector:()=>({})};
  const document = {querySelector:selector=>selector==='[data-expense-form]'?form:{addEventListener(){}}};
  vm.runInNewContext(script,{document,Option:function(){}});
  return {
    provider(value){fields.provider_id.value=value; fields.provider_id.listeners.change();},
    manual(value){fields.category_id.value=value; fields.category_id.listeners.change();},
    get category(){return fields.category_id.value;}
  };
}

test('provider default fills an empty category',()=>{const f=formState();f.provider('a');assert.equal(f.category,'cleaning');});
test('changing provider replaces an untouched automatic proposal',()=>{const f=formState();f.provider('a');f.provider('b');assert.equal(f.category,'repair');});
test('manual override survives subsequent provider changes',()=>{const f=formState();f.provider('a');f.manual('other');f.provider('b');assert.equal(f.category,'other');});
test('manual choice before provider selection is protected',()=>{const f=formState();f.manual('repair');f.provider('a');assert.equal(f.category,'repair');});
test('removing provider retains category',()=>{const f=formState();f.provider('a');f.provider('');assert.equal(f.category,'cleaning');});
test('provider without default changes nothing',()=>{const f=formState();f.provider('none');assert.equal(f.category,'');f.provider('a');f.provider('none');assert.equal(f.category,'cleaning');});
test('inactive default is never offered',()=>{const f=formState();f.provider('inactive');assert.equal(f.category,'');});
test('restored category after validation remains protected',()=>{const f=formState('other','a');f.provider('b');assert.equal(f.category,'other');});
test('preselected provider fills empty category on load',()=>{assert.equal(formState('','a').category,'cleaning');});
test('explicitly empty category can receive a new proposal',()=>{const f=formState();f.manual('');f.provider('a');assert.equal(f.category,'cleaning');});
test('without provider category stays manually editable',()=>{const f=formState();f.manual('other');assert.equal(f.category,'other');});
