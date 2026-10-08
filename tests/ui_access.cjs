const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs');
(async()=>{
 const key=process.env.SHOPIFY_OPS_OPERATOR_KEY;
 if(!key)throw new Error('Test operator key is required');
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
 try{
 const context=await browser.newContext();const page=await context.newPage();
 const base=process.env.WORKFLOW_TEST_URL||'http://127.0.0.1:8773';
 if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw new Error('Local test URL only');
 await page.goto(base);await page.getByRole('heading',{name:'Operaatori ligipääs'}).waitFor();
 await page.getByLabel('Operaatori ligipääsuvõti').fill('wrong');await page.getByRole('button',{name:'Ühenda',exact:true}).click();
 await page.getByRole('alert').filter({hasText:'vale'}).waitFor();
 await page.getByLabel('Operaatori ligipääsuvõti').fill(key);await page.getByRole('button',{name:'Ühenda',exact:true}).click();
 await page.getByRole('button',{name:'Lõpeta ligipääs'}).waitFor();
 await page.getByRole('button',{name:'Laadi näidistellimused',exact:true}).click();
 await page.getByRole('button',{name:'Uuenda juhtumeid leidudest'}).click();
 await page.getByRole('button',{name:'Ava juhtum'}).first().click();
 await page.getByText('local-operator',{exact:true}).waitFor();
 await page.locator('textarea').fill('Synthetic evidence checked in protected browser test.');
 await page.getByRole('button',{name:'Salvesta otsus'}).click();
 await page.getByRole('status').filter({hasText:'Menetlustoiming'}).waitFor();
 await page.reload();await page.getByLabel('Operaatori ligipääsuvõti').waitFor();
 const r=await context.request.get(base+'/api/incidents');if(r.status()!==401)throw new Error('Reload retained access unexpectedly');
 const storage=await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length}));
 if(storage.local||storage.session)throw new Error('Browser storage should not persist credentials');
 console.log(JSON.stringify({wrong_key_rejected:true,login_and_audit_workflow:true,reload_requires_key:true,browser_storage_empty:true}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
