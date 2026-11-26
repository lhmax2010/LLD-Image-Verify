const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const path = require('path');
const origin = 'https://quickbuild.tizen.org/build/1234794';
const workspace = path.resolve(process.argv[2] || 'results/quickbuild-1234794');
const out = path.join(workspace, 'qb');
fs.mkdirSync(out, {recursive:true});
function scrub(text) {
  let inKey = false;
  return text.split('\n').map(line => {
    if (/BEGIN .*PRIVATE KEY/.test(line)) { inKey = true; return '[redacted key]'; }
    if (inKey) { if (/END .*PRIVATE KEY/.test(line)) inKey = false; return '[redacted key]'; }
    if (/password|passwd|secret|credential|authorization|cookie|access[_-]?token|refresh[_-]?token/i.test(line)) return '[redacted credential-labelled line]';
    return line.replace(/(https?:\/\/)[^\s/@]+:[^\s/@]+@/g, '$1[redacted]@');
  }).join('\n');
}
async function run() {
  const ctx = await chromium.launchPersistentContext(path.join(workspace, 'qb-profile'), {
    executablePath: '/usr/bin/google-chrome', headless: false,
    args: ['--ozone-platform=x11','--disable-extensions','--disable-background-networking'],
    timeout: 15000,
  });
  try {
    const p = ctx.pages()[0] || await ctx.newPage();
    await p.goto(origin + '/gbs_reports', {waitUntil:'domcontentloaded', timeout:25000});
    console.log(p.url().includes('/signin') ? 'WAITING_FOR_LOGIN' : 'QB_OPEN');
    if (p.url().includes('/signin')) await p.waitForURL(u => u.hostname==='quickbuild.tizen.org' && u.pathname.startsWith('/build/1234794'), {timeout:240000});
    const tasks = [['overview',''],['gbs_reports','/gbs_reports'],['log','/log']];
    await Promise.all(tasks.map(async ([kind,suffix]) => {
      const t = await ctx.newPage();
      await t.goto(origin+suffix, {waitUntil:'domcontentloaded',timeout:30000});
      if (t.url().includes('/signin')) throw new Error('QB login required');
      fs.writeFileSync(out+'/'+kind+'.txt', scrub(await t.locator('body').innerText()));
      const links = await t.locator('a,iframe').evaluateAll(xs => xs.map(e=>({title:e.title||'',text:e.innerText||'',url:e.href||e.src||''})).filter(x=>x.url&&!/logout|signout|token=/i.test(x.url)));
      fs.writeFileSync(out+'/'+kind+'-links.json',scrub(JSON.stringify(links,null,2)));
      if(kind==='gbs_reports'){
        const link=links.find(x=>x.url.includes('/download/') && x.url.includes('index.html'));
        if(link){
          const paths=new Map();
          if (/standard-(armv7l|aarch64|x86_64)(?=[/%]|$)/.test(link.url) && !link.url.includes('armv7l:aarch64:x86_64')){
            for (const a of ['armv7l','aarch64','x86_64']) paths.set(a,link.url.replace(/standard-(armv7l|aarch64|x86_64)(?=[/%]|$)/,'standard-'+a));
          }else{paths.set('all',link.url);}
          await Promise.all([...paths].map(async ([arch,url])=>{
            const res=await ctx.request.get(url,{timeout:30000});
            if(res.ok()&&!res.url().includes('/signin'))
              fs.writeFileSync(out+'/report-'+arch+'.html', await res.text());
            console.log('Report',arch,res.status());
          }));
        }
      }
      if(kind==='log'){
        const l=t.getByTitle('Save full log as text file');
        if(await l.count()){
          const href=await l.first().getAttribute('href');
          const res=await ctx.request.get(new URL(href,t.url()).href,{timeout:60000});
          if(!res.ok()) throw new Error('Full log '+res.status());
          fs.writeFileSync(out+'/full-log.txt',scrub(await res.text()));
        }
      }
      console.log('Captured',kind);
      await t.close();
    }));
  } finally { await ctx.close(); }
}
run().then(()=>process.exit(),err=>{console.error(err.message);process.exit(1)});
