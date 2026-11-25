// Run against isolated synthetic mobile_test_server instances only; see docs/MOBILE_ADMIN.md.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const sizes=[[640,360],[667,375],[844,390],[932,430],[360,800],[375,812],[390,844],[430,932],[768,1024],[1100,450],[1280,900],[1920,1080]];
test('compact admin header, landscape controls, rotation and desktop preservation', {skip:!process.env.RM_LAYOUT_TEST_URL,timeout:240000},async()=>{
 const out=process.env.RM_LAYOUT_EVIDENCE_DIR; if(out)fs.mkdirSync(out,{recursive:true});
 const results=[],b=await chromium.launch({channel:'msedge',headless:true});
 try{
 for(const [version,url] of [['before',process.env.RM_LAYOUT_REFERENCE_URL],['after',process.env.RM_LAYOUT_TEST_URL]]){
 if(!url)continue;
 assert.ok(['127.0.0.1','localhost'].includes(new URL(url).hostname),'synthetic localhost only');
 for(const remote of [false,true])for(const [width,height] of sizes){
 const mobile=width<=1100,c=await b.newContext({viewport:{width,height},hasTouch:mobile,isMobile:mobile,deviceScaleFactor:1});
 if(process.env.RM_LAYOUT_BOOTSTRAP_DIR)await c.route('https://cdn.jsdelivr.net/**',r=>r.fulfill({contentType:r.request().url().endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(process.env.RM_LAYOUT_BOOTSTRAP_DIR,r.request().url().endsWith('.js')?'bootstrap.bundle.min.js':'bootstrap.min.css'))}));
 if(remote)await c.route('https://admin.example.test/**',async route=>{const req=route.request(),u=new URL(req.url());assert.equal(req.method(),'GET');const res=await c.request.get(url+u.pathname+u.search,{headers:{...await req.allHeaders(),'x-rm-test-remote':'1'},maxRedirects:0});await route.fulfill({response:res});});
 const p=await c.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));const base=remote?'https://admin.example.test':url;
 await p.goto(base+'/gantt/');await p.waitForTimeout(100);
 const layout=await p.evaluate(()=>{
  const rect=s=>{const n=document.querySelector(s);if(!n)return null;const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};
  return {header:rect('.rm-header'),menu:rect('.rm-menu-button'),title:rect('.rm-mobile-page-title'),badge:rect('.rm-consultation'),controls:rect('.gantt-controls'),calendar:rect('#ganttRoot'),nav:rect('#rmNavigation'),offcanvas:document.querySelector('#rmNavigation').classList.contains('offcanvas'),overflow:document.documentElement.scrollWidth>innerWidth+1};
 });
 results.push({version,remote,width,height,...layout});
 if(out&&remote&&([640,667,844,932,390,1280,1920].includes(width)))await p.screenshot({path:path.join(out,`${version}-${width}x${height}.png`)});
 if(version==='after'){
  assert.equal(layout.overflow,false);assert.equal(layout.offcanvas,mobile);
  if(mobile){
   assert.ok(layout.header.height>=48&&layout.header.height<=56,JSON.stringify(layout));assert.equal(layout.menu.width,44);assert.equal(layout.menu.height,44);
   assert.ok(layout.title.x>=layout.menu.right);assert.ok(Math.abs(layout.menu.y+22-(layout.title.y+layout.title.height/2))<2);
   if(remote){assert.ok(layout.badge.height<30);assert.ok(layout.badge.x>=layout.title.right-1);assert.ok(layout.badge.right<=width);}
   if(height<=450){assert.ok(layout.controls.height<=45,`controls ${width}: ${layout.controls.height}`);assert.ok(layout.calendar.width>=width-12);}
   await p.locator('.rm-menu-button').click();await p.locator('#rmNavigation.show').waitFor();await p.locator('#rmNavigation [data-bs-dismiss=offcanvas]').click();await p.locator('#rmNavigation.show').waitFor({state:'hidden'});
  }else{const before=results.find(x=>x.version==='before'&&x.width===width&&x.remote===remote);if(before){assert.deepEqual(layout.header,before.header);assert.deepEqual(layout.calendar,before.calendar);}}
  await p.locator('#ganttZoom').selectOption('2');await p.locator('#ganttExpand').click();assert.ok(await p.locator('#ganttExpand').isVisible());
  if(mobile&&height<=450)assert.ok(await p.locator('.gantt-controls').evaluate(n=>n.getBoundingClientRect().height)<=45);
  await p.locator('#ganttExpand').click();await p.locator('#ganttZoom').selectOption('1');
 }
 if(version==='after'&&width===390){
  await p.locator('#ganttZoom').selectOption('4');await p.locator('#ganttRoot').evaluate(n=>{n.scrollLeft=600;n.scrollTop=100});await p.waitForTimeout(60);
  const a=await p.evaluate(()=>RMGantt.captureAnchor());await p.setViewportSize({width:932,height:430});await p.waitForTimeout(100);const z=await p.evaluate(()=>RMGantt.captureAnchor());assert.ok(Math.abs(z.date-a.date)<86400000);assert.ok(Math.abs(z.top-a.top)<2);assert.ok(await p.locator('#rmNavigation').evaluate(n=>n.classList.contains('offcanvas')));
  for(const route of ['/','/persons','/owners','/properties/','/rooms/1','/expenses','/settlements','/bookings/1/finance']){
   const response=await p.goto(base+route);assert.equal(response.status(),200);assert.equal(await p.locator('.rm-header').evaluate(n=>n.getBoundingClientRect().height),53);
   assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
   if(remote)assert.equal(await p.locator('form[method="post"]').count(),0);
  }
 }
 assert.deepEqual(errors,[]);await c.close();console.log(version,remote,width,height,'header',layout.header.height,'calendar',layout.calendar.height);
 }
 }
 }finally{await b.close();if(out)fs.writeFileSync(path.join(out,'measurements.json'),JSON.stringify(results,null,2));}
});
