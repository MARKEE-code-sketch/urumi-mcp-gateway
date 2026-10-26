import { chromium } from "../../frontend/node_modules/playwright/index.mjs";
import { readFile, writeFile } from "node:fs/promises";

const output = 'docs/evidence/ui-refresh/teal-dashboard';
const access = JSON.parse(await readFile('.tools/operator/m10/access.json','utf8'));
const origin = 'https://dashboard-m10.urumi.test';
const browser = await chromium.launch();
const results = [];
try {
  for (const role of ['admin','member']) {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    try {
      const page = await context.newPage();
      const violations = [], external = [];
      await page.addInitScript(() => {
        window.previewViolations = [];
        addEventListener('securitypolicyviolation', e => window.previewViolations.push({directive:e.effectiveDirective,uri:e.blockedURI}));
      });
      page.on('request', request => {
        const url = new URL(request.url());
        if (url.origin !== origin) external.push(url.origin);
      });
      await page.goto(origin+'/login');
      await page.getByLabel('Email',{exact:true}).fill(access[`${role}_email`]);
      await page.getByLabel('Password',{exact:true}).fill(access[`${role}_password`]);
      await page.getByRole('button',{name:'Log in',exact:true}).click();
      await page.getByRole('button',{name:'Logout',exact:true}).waitFor();
      await page.locator('.server-card').first().waitFor();
      const servers = [];
      const cards = page.locator('.server-card');
      for(let i=0; i<await cards.count(); i++) {
        const card=cards.nth(i);
        const name=await card.getByRole('heading').innerText();
        await card.getByRole('button',{name:'View tools',exact:true}).click();
        await page.locator('.server-tools-panel .tool-card h3').first().waitFor();
        const tools=await page.locator('.server-tools-panel .tool-card h3').allTextContents();
        if(!tools.length || tools.some(n=>!n.includes('__')))throw new Error('Canonical tool name missing');
        if(await page.locator('.server-tools-panel pre').count())throw new Error('Raw schema dump rendered');
        servers.push({name,tools});
      }
      await page.screenshot({path:`${output}/live-${role}-tools.png`,fullPage:true});
      if(role==='member' && await page.getByRole('link',{name:'Members',exact:true}).count())throw new Error('Member gained admin navigation');
      await page.getByRole('link',{name:'Chat',exact:true}).click();
      await page.getByLabel('Message',{exact:true}).waitFor();
      await page.evaluate(()=>document.fonts.ready);
      const appearance=await page.evaluate(()=>({
        primary:getComputedStyle(document.documentElement).getPropertyValue('--primary').trim(),
        font:getComputedStyle(document.body).fontFamily,
        iconsLoaded:[...document.images].every(image=>image.complete&&image.naturalWidth>0),
        favicon:document.querySelector('link[rel="icon"]')?.getAttribute('href')
      }));
      if(appearance.primary!=='#147d69'||!appearance.iconsLoaded)throw new Error('Teal assets did not load');
      await page.screenshot({path:`${output}/live-${role}-chat-start.png`,fullPage:true});
      let chat;
      if(role==='admin') {
        await page.getByLabel('Message',{exact:true}).fill('List our WooCommerce products with their IDs, SKUs and INR prices. Format the answer as a Markdown table. Read only; do not change any products.');
        await page.getByRole('button',{name:'Send message',exact:true}).click();
        await page.locator('.exchange').first().waitFor({timeout:120000});
        await page.getByRole('button',{name:'Send message',exact:true}).waitFor({state:'visible'});
        const table=page.locator('.markdown-answer table');
        chat={tables:await table.count(),columns:await table.first().getByRole('columnheader').allTextContents(),rows:await table.first().getByRole('row').count(),answerChars:(await page.locator('.markdown-answer').innerText()).length};
        if(chat.tables<1||chat.rows<2)throw new Error('Real chat did not render a product table');
        await page.locator('.tool-activity > summary').click();
        chat.tools=await page.locator('.tool-activity-body strong').allTextContents();
        await page.screenshot({path:`${output}/live-admin-chat-answer.png`,fullPage:true});
      }
      await page.setViewportSize({width:390,height:844});
      if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Mobile page overflow');
      await page.screenshot({path:`${output}/live-${role}-mobile.png`,fullPage:true});
      violations.push(...await page.evaluate(()=>window.previewViolations));
      if(violations.length||external.length)throw new Error('Unexpected CSP violation or external browser request');
      results.push({role,servers,appearance,chat,mobile_no_page_overflow:true,csp_violations:violations,external_browser_requests:external});
    } finally {await context.close();}
  }
} finally {await browser.close();}
await writeFile(`${output}/live-browser.json`,JSON.stringify({checked_at:new Date().toISOString(),tls_bypass:false,results},null,2)+'\n');
console.log(JSON.stringify({status:'PASS',roles:results.map(r=>r.role),artifact:`${output}/live-browser.json`}));
