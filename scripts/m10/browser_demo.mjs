// Explicit live demo only. Credentials remain in the ignored operator file.
// No trace/HAR/video, TLS bypass, automatic mutation retry, or raw exception output.
import { chromium } from '../../frontend/node_modules/playwright/index.mjs';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
const action = process.argv[2];
const output = 'docs/evidence/m10/browser';
mkdirSync(output, { recursive: true });
if (['checkout', 'checkout-notebook', 'chat-create'].includes(action) && existsSync(`${output}/${action}.json`)) {
  console.log(JSON.stringify({action,status:'ALREADY_RECORDED_REVIEW_BEFORE_NEW_WRITE'}));
  process.exit(1);
}
let browser, step = 'start';
const result = { action, checked_at: new Date().toISOString(), tls_verification: 'browser_default', checks: [] };
try {
  browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  if (['checkout', 'checkout-notebook', 'inspect-checkout'].includes(action)) {
    step = 'add_product';
    await page.goto('http://shop-m10.urumi.test/shop/');
    step = 'click_add_product';
    const productName = action === 'checkout-notebook' ? 'M10 Browser Demo Notebook' : 'Urumi Demo Product';
    await page.getByRole('button', {name:`Add to cart: “${productName}”`, exact:true}).click();
    await page.waitForTimeout(1500);
    step = 'load_checkout';
    await page.goto('http://shop-m10.urumi.test/checkout/');
    if (action === 'inspect-checkout') {
      result.inputs = await page.locator('input,select,button').evaluateAll(es => es.map(e => ({tag:e.tagName,id:e.id,name:e.name,type:e.type})));
    } else {
      step = 'fill_checkout';
      await page.locator('#billing_first_name').fill('Demo');
      await page.locator('#billing_last_name').fill('Customer');
      await page.locator('#billing_country').selectOption('IN');
      await page.locator('#billing_address_1').fill('10 Test Street');
      await page.locator('#billing_city').fill('Bengaluru');
      await page.locator('#billing_state').selectOption('KA');
      await page.locator('#billing_postcode').fill('560001');
      await page.locator('#billing_phone').fill('9999999999');
      await page.locator('#billing_email').fill('demo.customer@example.test');
      await page.locator('#payment_method_cod').check();
      await page.waitForTimeout(2000);
      step = 'place_order_once';
      await page.locator('#place_order').click();
      await page.waitForURL(/order-received/, {timeout:45000});
      const match = new URL(page.url()).pathname.match(/order-received\/(\d+)/);
      if (!match) throw new Error('order_id');
      result.order_id = Number(match[1]);
      result.product_name = productName;
      result.checks.push('storefront_checkout_order_received');
      await page.screenshot({path:`${output}/${action}.png`,fullPage:true});
    }
  } else if (['chat-create', 'chat-orders', 'admin-order', 'admin-notebook'].includes(action)) {
    const access = JSON.parse(readFileSync('.tools/operator/m10/access.json','utf8').replace(/^\uFEFF/,''));
    if (action === 'admin-order' || action === 'admin-notebook') {
      step = 'store_admin_login';
      await page.goto('http://shop-m10.urumi.test/wp-login.php');
      await page.locator('#user_login').fill(access.store_username);
      await page.locator('#user_pass').fill(access.store_password);
      await page.locator('#wp-submit').click();
      await page.waitForURL(/wp-admin/);
      const checkout = JSON.parse(readFileSync(`${output}/${action === 'admin-notebook' ? 'checkout-notebook' : 'checkout'}.json`,'utf8'));
      await page.goto(`http://shop-m10.urumi.test/wp-admin/admin.php?page=wc-orders&action=edit&id=${checkout.order_id}`);
      result.checks.push('woocommerce_admin_order_visible');
      result.order_id = checkout.order_id;
      result.order_heading = await page.locator('h2').allTextContents();
      if (!result.order_heading.some(text => text.includes(`Order #${checkout.order_id}`))) throw new Error('order_heading');
      await page.screenshot({path:`${output}/${action}.png`,fullPage:true,mask:[page.locator('#wpadminbar')]});
    } else {
      step = 'dashboard_login';
      await page.goto('https://dashboard-m10.urumi.test/login');
      await page.getByLabel('Email',{exact:true}).fill(access.admin_email);
      await page.getByLabel('Password',{exact:true}).fill(access.admin_password);
      await page.getByRole('button',{name:'Log in',exact:true}).click();
      await page.getByRole('heading',{name:'Servers',exact:true}).waitFor();
      await page.getByRole('link',{name:'Chat',exact:true}).click();
      const message = action === 'chat-create'
        ? 'Create exactly one published simple WooCommerce product named M10 Browser Demo Notebook with regular price 129 INR and SKU M10-BROWSER-NOTEBOOK. This is an approved test purchase product. Call the product creation tool exactly once; do not retry any write. Tell me its product ID and price.'
        : "Use the WooCommerce tool to list today's orders in the store Asia/Kolkata timezone. Tell me the order IDs, status, totals and items. This is a real read-only lookup.";
      await page.getByLabel('Message',{exact:true}).fill(message);
      step = 'chat_send_once';
      const responsePromise = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/chat' && r.request().method()==='POST',{timeout:140000});
      await page.getByRole('button',{name:'Send message',exact:true}).click();
      const response = await responsePromise;
      result.http_status = response.status();
      if (response.status() !== 200) {result.status='LIVE_CHAT_FAILED'; result.failure_step=step;}
      else {
        const reply = await response.json();
        result.reply = {answer:reply.answer,state:reply.state,request_id:reply.request_id,tool_calls:reply.tool_calls?.map(c=>({tool_name:c.tool_name,outcome:c.outcome,audit_id:c.audit_id,error_code:c.error_code,result_summary:c.result_summary}))};
        await page.locator('article').waitFor();
        await page.screenshot({path:`${output}/${action}.png`,fullPage:true});
        result.checks.push('real_dashboard_chat_response');
      }
      if (action === 'chat-create' && result.http_status===200) {
        await page.goto('http://shop-m10.urumi.test/shop/');
        result.created_product_visible = await page.getByText('M10 Browser Demo Notebook',{exact:true}).isVisible();
        if (!result.created_product_visible) throw new Error('created_product_missing');
        await page.screenshot({path:`${output}/created-product.png`,fullPage:true});
      }
    }
  } else throw new Error('unknown_action');
  result.status ??= 'PASS';
} catch {
  result.status = 'FAILED_REVIEW_BEFORE_RETRY';
  result.failure_step = step;
} finally {await browser?.close();}
writeFileSync(`${output}/${action}.json`, JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({action,status:result.status,failure_step:result.failure_step,order_id:result.order_id}));
