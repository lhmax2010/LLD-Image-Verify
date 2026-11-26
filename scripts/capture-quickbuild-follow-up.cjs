const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const path = require('path');
const origin = 'https://quickbuild.tizen.org';
const workspace = path.resolve(process.argv[2] || 'results/quickbuild-1234794');
const out = path.join(workspace, 'qb');
fs.mkdirSync(out, {recursive:true});
const pages = {
  steps: '/build/1234794/step_status',
  children: '/children/1917',
  overview: '/build/1234794/overview',
};
function scrub(text) {
  return text.split('\n').map(s => /password|passwd|secret|credential|authorization|cookie|access[_-]?token|refresh[_-]?token/i.test(s) ? '[redacted]' :
    s.replace(/(https?:\/\/)[^\s/@]+:[^\s/@]+@/g, '$1[redacted]@')).join('\n');
}
async function main() {
  const ctx = await chromium.launchPersistentContext(path.join(workspace, 'qb-profile'), {
    executablePath:'/usr/bin/google-chrome', headless:false, args:['--ozone-platform=x11','--disable-extensions'],
  });
  try {
    await Promise.all(Object.entries(pages).map(async ([kind, suffix]) => {
      const p = await ctx.newPage();
      await p.goto(origin + suffix, {waitUntil:'domcontentloaded',timeout:30000});
      if(p.url().includes('/signin')) throw new Error('QB login required');
      await p.locator('table').first().waitFor({timeout:20000}).catch(() => {});
      const body = await p.locator('body').innerText();
      fs.writeFileSync(path.join(out,kind+'-follow-up.txt'),scrub(body));
      const links=await p.locator('a').evaluateAll(es=>es.map(e=>({text:e.innerText.trim(),title:e.title,url:e.href})).filter(e=>e.url && !/logout|signout|token=/i.test(e.url)));
      fs.writeFileSync(path.join(out,kind+'-follow-up-links.json'),scrub(JSON.stringify(links,null,2)));
      console.log(kind, body.length);
    }));
  } finally { await ctx.close(); }
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
