const {chromium}=require('playwright');
const fs=require('fs');const path=require('path');
const base=process.env.SHOPIFY_UI_URL||'http://127.0.0.1:8770';
const target=new URL(base);if(!['127.0.0.1','localhost'].includes(target.hostname))throw Error('Run this mutating synthetic test only against a local demo');
const artifacts=path.join(__dirname,'../data/ui-check');fs.mkdirSync(artifacts,{recursive:true});
const note='Synthetic UI validation '+Date.now()+': reviewed source evidence; no merchant changes.';
(async()=>{
 for(let attempt=0;attempt<20;attempt++){try{const r=await fetch(base+'/api/health');if(r.ok)break}catch{}if(attempt===19)throw Error('Local service not ready');await new Promise(resolve=>setTimeout(resolve,500))}
 const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(base+'/',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'120 tellimusega tööpäev'}).click();
  await page.getByText('120 väljamõeldud tellimusega tööpäev laaditud. Uuenda juhtumeid leidudest.').waitFor();
  await page.getByRole('button',{name:'Uuenda juhtumeid leidudest'}).click();
  await page.getByRole('button',{name:'Ava juhtum'}).first().waitFor();
  await page.getByRole('button',{name:'Ava juhtum'}).first().click();
  await page.getByLabel('Vastutaja',{exact:true}).fill('synthetic-test-operator');
  await page.getByLabel('Kontrolli tulemus / otsuse põhjus').fill(note);
  await page.getByLabel('Uus olek',{exact:true}).selectOption('investigating');
  await page.getByRole('button',{name:'Salvesta otsus'}).click();
  await page.getByText('Menetlustoiming ja enne/pärast seis salvestatud.').waitFor();
  await page.locator('.incident-history').getByText(note).waitFor();
  await page.locator('.incident-detail').screenshot({path:path.join(artifacts,'incident-workflow.png')});
  await page.reload({waitUntil:'networkidle'});
  await page.getByRole('button',{name:'Ava juhtum'}).first().click();
  await page.locator('.incident-history').getByText(note).waitFor();
  if(errors.length)throw Error(errors.join('\n'));
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({scenario_orders:120,checks:['scenario import','incident sync','evidence view','owner assignment','operator note','revision update','audit persistence after reload'],page_errors:errors,passed:true},null,2));
  console.log('Verified UI triage flow and persistence after reload.');
 }finally{await context.close();await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
