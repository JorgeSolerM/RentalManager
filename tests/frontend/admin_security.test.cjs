const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const script = fs.readFileSync('backend/static/js/admin_security.js', 'utf8');

test('Browser forms, fetch and XHR carry CSRF only to their own origin', async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    const page = await browser.newPage();
    const requests=[];
    await page.route('**/*', async route => {
      const r=route.request();
      if (r.url()==='https://admin.example.test/') return route.fulfill({contentType:'text/html',body:`<html><head><meta name="rm-admin-csrf" content="synthetic-token"><meta name="rm-admin-remote" content="1"><script>${script}</script></head><body><span role="status">Modo consulta</span><form method="post" action="/write"><input name="value" value="kept"><select name="method"><option>cash</option></select><input name="action" value="synthetic"><button>Enviar</button></form></body></html>`});
      requests.push({url:r.url(),method:r.method(),headers:await r.allHeaders(),data:r.postData()});
      await route.fulfill({contentType:'application/json',body:'{}',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'}});
    });
    await page.goto('https://admin.example.test/');
    assert.equal(await page.locator('[role=status]').count(),1);
    await page.evaluate(async()=>{
      await fetch('/search',{method:'POST',body:new URLSearchParams({q:'test'})});
      await fetch(new Request('/request',{method:'POST',body:'value'}));
      await new Promise(resolve=>{const x=new XMLHttpRequest();x.open('POST','/xhr');x.onload=resolve;x.send('value');});
      await fetch('https://outside.example.test/post',{method:'POST',body:'no-secret'});
    });
    for (const r of requests.filter(r=>r.url.startsWith('https://admin.example.test/'))) assert.equal(r.headers['x-rm-csrf'],'synthetic-token');
    for (const r of requests.filter(r=>r.url.startsWith('https://outside.example.test/'))) {
      assert.equal(r.headers['x-rm-csrf'],undefined);
      assert.ok(!JSON.stringify(r).includes('synthetic-token'));
    }
    await Promise.all([page.waitForRequest(r=>r.url()==='https://admin.example.test/write' && r.method()==='POST'),page.locator('button').click({force:true})]);
    assert.match(requests.find(r=>r.url.endsWith('/write')).data,/_rm_csrf=synthetic-token/);
    await page.goto('https://admin.example.test/');
    await Promise.all([page.waitForRequest(r=>r.url()==='https://admin.example.test/write' && r.method()==='POST'),page.evaluate(()=>document.querySelector('form').submit())]);
    assert.match(requests.filter(r=>r.url.endsWith('/write')).at(-1).data,/_rm_csrf=synthetic-token/);
  } finally { await browser.close(); }
});
