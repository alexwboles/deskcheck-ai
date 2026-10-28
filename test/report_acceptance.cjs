'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    for(const width of [1280,390]) {
      const context = await browser.newContext({viewport:{width,height:844}});
      const external=[], errors=[];
      await context.route('**/*',route=>{
        if(/^https?:/.test(route.request().url())) {external.push(route.request().url());return route.abort();}
        return route.continue();
      });
      const page=await context.newPage();
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
      assert.match(await page.locator('.badge').innerText(),/PASS/);
      assert.equal(await page.locator('img').evaluateAll(items=>items.length>0 && items.every(i=>i.complete&&i.naturalWidth>0)),true);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      assert.deepEqual(external,[]);
      assert.deepEqual(errors,[]);
      console.log(JSON.stringify({width,status:'pass',imagesLoaded:true,externalRequests:0,pageErrors:0}));
      await context.close();
    }
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
