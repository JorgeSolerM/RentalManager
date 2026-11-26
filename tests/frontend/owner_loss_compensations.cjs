// Real browser submissions against a disposable fixture server only.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
 const [base, incident, loss, settlement, out] = process.argv.slice(2);
 assert.equal(new URL(base).hostname, '127.0.0.1');
 fs.mkdirSync(out, { recursive: true });
 const browser = await chromium.launch({channel:'msedge',headless:true});
 const page = await browser.newPage();
 const errors=[];page.on('pageerror', e=>errors.push(e.message));
 if(process.env.RM_TEST_BOOTSTRAP) await page.route('https://cdn.jsdelivr.net/**', route => {
  const name=new URL(route.request().url()).pathname.split('/').pop();
  const file=path.join(process.env.RM_TEST_BOOTSTRAP,name);
  return fs.existsSync(file) ? route.fulfill({path:file,contentType:name.endsWith('.css')?'text/css':'application/javascript'}) : route.abort();
 });
 const url=base+'/transfer-incidents/'+incident+'/compensations';
 const measurements=[];
 for(const [width,height] of [[360,800],[375,812],[390,844],[430,932],[768,1024],[1280,800],[1920,1080],[844,390]]) {
  await page.setViewportSize({width,height});await page.goto(url);await page.waitForLoadState('networkidle');
  const result=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,forms:[...document.querySelectorAll('form[method="post"]')].every(f=>!!f.querySelector('input[name="_rm_csrf"]')?.value)}));
  assert(result.scroll<=width+1,JSON.stringify(result));assert(result.forms);
  measurements.push({...result,height});
  await page.screenshot({path:path.join(out,'compensations-'+width+'x'+height+'.png'),fullPage:true,timeout:30000});
 }
 await page.setViewportSize({width:390,height:844});
 let form=page.locator('form').filter({has:page.locator('input[name="mode"][value="authorize"]')});
 await form.locator('[name="loss_id"]').selectOption(loss);
 await form.locator('[name="agreement_reference"]').fill('BROWSER-SYNTHETIC-AGREEMENT');
 await form.locator('[name="settlement_ids"][value="'+settlement+'"]').check();
 await form.locator('[name="amount"]').fill('100');
 await form.locator('[name="reason"]').fill('Autorización sintética de navegador');
 await form.locator('[name="evidence"]').fill('Acuerdo sintético expreso');
 await form.locator('[name="authorized"]').check();
 await Promise.all([page.waitForURL('**/preview'),form.locator('button').click()]);
 form=page.locator('form[action$="/confirm"]');
 await form.locator('[name="authorized"]').check();await form.locator('[name="confirmed"]').check();
 await Promise.all([page.waitForURL(url),form.locator('button').click()]);
 assert.equal(await page.locator('article').count(),1);
 form=page.locator('form').filter({has:page.locator('input[name="mode"][value="apply"]')});
 await form.locator('[name="amount"]').fill('40');
 await form.locator('[name="reason"]').fill('Aplicación sintética de navegador');
 await form.locator('[name="evidence"]').fill('Apartado de acuerdo sintético');
 await Promise.all([page.waitForURL('**/preview'),form.locator('button').click()]);
 form=page.locator('form[action$="/confirm"]');await form.locator('[name="confirmed"]').check();
 await Promise.all([page.waitForURL(url),form.locator('button').click()]);
 assert.match(await page.locator('article').innerText(),/Aplicado 40/);
 await page.screenshot({path:path.join(out,'applied-mobile.png'),fullPage:true});
 // Native navigation refresh must not create another application.
 await page.reload();assert.match(await page.locator('article').innerText(),/Aplicado 40/);
 await page.goto(base+'/settlements/'+settlement);
 assert.match(await page.locator('main').innerText(),/Compensado mediante acuerdo: 40/);
 assert.match(await page.locator('main').innerText(),/Resultado económico y fondos/);
 await page.screenshot({path:path.join(out,'settlement-local.png'),fullPage:true});
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({measurements,errors,authorization:true,application:true,refresh:true},null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
