const {chromium}=require('playwright');const fs=require('fs');const path=require('path');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});const context=await browser.newContext({viewport:{width:1440,height:1050}});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8773',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'Laadi näidistellimused',exact:true}).click();
  await page.getByRole('button',{name:'Vaata tõendeid →'}).first().click();
  await page.getByRole('button',{name:'Koosta uurimisplaan'}).click();
  const plan=page.getByTestId('investigation-plan');await plan.waitFor();await plan.getByText('Veel teadmata',{exact:true}).waitFor();
  if(!(await plan.locator('details summary').allTextContents()).some(x=>x.startsWith('Tõend:')))throw Error('Evidence citation missing');
  if(errors.length)throw Error(errors.join('\n'));
  const dir=path.join(__dirname,'../data/investigation-ui');fs.mkdirSync(dir,{recursive:true});await plan.screenshot({path:path.join(dir,'plan.png')});
  const report={passed:true,checks:['demo import','select finding','investigation plan','cited steps','unknowns','snapshot'],page_errors:errors,scope:'isolated localhost synthetic demo; no real model'};
  fs.writeFileSync(path.join(__dirname,'../investigation-ui-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await context.close();await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
