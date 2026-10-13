const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../backend/static/js/booking_early_termination.js'), 'utf8');
function setup(value='') {
  const fields = {};
  for (const id of ['effectiveDeparture','economicLastDay','earlyTerminationForm','earlyTerminationConfirmation','earlyTerminationStaleNotice','acceptProration']) {
    fields[id] = {value:'',hidden:false,listeners:{},addEventListener(event,fn){this.listeners[event]=fn;}};
  }
  fields.economicLastDay.value=value;
  fields.earlyTerminationStaleNotice.hidden=true;
  vm.runInNewContext(source,{document:{getElementById:id=>fields[id]}});
  return fields;
}
test('departure proposes the same inclusive economic date',()=>{
  const f=setup();f.effectiveDeparture.value='2027-03-15';f.effectiveDeparture.listeners.change();assert.equal(f.economicLastDay.value,'2027-03-15');
});
test('explicit economic date is preserved when departure changes',()=>{
  const f=setup();f.economicLastDay.value='2027-03-31';f.economicLastDay.listeners.input();f.effectiveDeparture.value='2027-03-16';f.effectiveDeparture.listeners.change();assert.equal(f.economicLastDay.value,'2027-03-31');
});
test('restored preview dates are not overwritten',()=>{
  const f=setup('2027-03-31');f.effectiveDeparture.value='2027-03-17';f.effectiveDeparture.listeners.change();assert.equal(f.economicLastDay.value,'2027-03-31');
});
test('clearing economic date permits a new proposal',()=>{
  const f=setup('2027-03-31');f.economicLastDay.value='';f.economicLastDay.listeners.input();f.effectiveDeparture.value='2027-03-18';f.effectiveDeparture.listeners.change();assert.equal(f.economicLastDay.value,'2027-03-18');
});
test('editing a reviewed form invalidates its confirmation',()=>{
  const f=setup();f.earlyTerminationForm.listeners.input();assert.equal(f.earlyTerminationConfirmation.hidden,true);assert.equal(f.earlyTerminationStaleNotice.hidden,false);
});
test('history without form safely loads',()=>{vm.runInNewContext(source,{document:{getElementById:()=>null}});});
test('changing the external proration checkbox invalidates confirmation',()=>{
  const f=setup();f.acceptProration.listeners.change();assert.equal(f.earlyTerminationConfirmation.hidden,true);assert.equal(f.earlyTerminationStaleNotice.hidden,false);
});
