// Read-only admin UI checks: no products, orders, settings or user accounts saved.
import { chromium } from '../../frontend/node_modules/playwright/index.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const origin = 'https://shop-m10.urumi.test';
const out = 'docs/evidence/ui-refresh/shop-admin';
const access = JSON.parse(await readFile('.tools/operator/m10/access.json', 'utf8'));
const deployment = JSON.parse(await readFile(`${out}/deployment.json`, 'utf8'));
const result = { status: 'FAIL', checks: [], externalOrigins: [], pageErrors: [] };
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(20000);
page.on('request', request => {
  const url = new URL(request.url());
  if (url.protocol.startsWith('http') && url.origin !== origin) result.externalOrigins.push(url.origin);
});
page.on('pageerror', error => result.pageErrors.push(error.message));
async function go(path) { await page.goto(origin + path, { waitUntil: 'domcontentloaded' }); }
async function appearance(name, screenshot = true) {
  await page.evaluate(() => document.fonts.ready);
  const state = await page.evaluate(() => ({
    width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
    font: getComputedStyle(document.body).fontFamily,
    primary: getComputedStyle(document.body).getPropertyValue('--urumi-primary').trim(),
    cssLoaded: !!document.querySelector('link#urumi-shop-admin-css'),
  }));
  assert(state.scrollWidth <= state.width + 1, `${name}: page overflow ${state.scrollWidth}/${state.width}`);
  assert(state.cssLoaded && state.primary === '#147d69' && state.font.includes('Figtree'), `${name}: branding missing`);
  result.checks.push({ name, ...state });
  if (screenshot) await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
}
try {
  await go('/wp-login.php');
  await appearance('login-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await appearance('login-mobile');
  await page.locator('#user_login').fill(access.store_username);
  await page.locator('#user_pass').fill('invalid-password-for-ui-check');
  await page.locator('#wp-submit').click();
  await page.locator('#login_error').waitFor();
  // WordPress clears the password on load after a failed login.
  await page.waitForLoadState('load');
  await page.waitForFunction(() => document.activeElement?.id === 'user_pass');
  result.checks.push({ name: 'native invalid-login validation', passed: true });
  await page.locator('#user_login').fill(access.store_username);
  await page.locator('#user_pass').fill(access.store_password);
  await page.locator('#wp-submit').click();
  await page.waitForURL('**/wp-admin/**', { waitUntil: 'domcontentloaded' });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await go('/wp-admin/');
  await page.locator('.urumi-admin-overview').waitFor();
  assert.equal(await page.locator('#dashboard_primary').count(), 0);
  result.checks.push({ name: 'unrelated external news panel omitted', passed: true });
  const counts = await page.locator('.urumi-admin-metric strong').allTextContents();
  assert.deepEqual(counts.map(Number), [deployment.after.products.length, deployment.after.order_ids.length]);
  result.checks.push({ name: 'overview real product/order totals', counts: counts.map(Number), passed: true });
  await appearance('dashboard-desktop');
  await page.locator('.urumi-admin-actions').getByRole('link', { name: 'Manage products', exact: true }).click();
  await page.locator('#the-list #post-12').waitFor();
  await appearance('products-desktop');
  await page.locator('.search-box input[type=search]').fill('DEMO-001');
  await page.locator('.search-box input[type=submit]').click();
  await page.waitForURL(/s=DEMO-001/);
  await page.locator('#the-list #post-12').waitFor();
  result.checks.push({ name: 'product search', passed: true });
  await go('/wp-admin/post.php?post=12&action=edit');
  await page.locator('#title').waitFor();
  assert.equal(await page.locator('#title').inputValue(), 'Urumi Demo Product');
  assert.equal(Number(await page.locator('#_regular_price').inputValue()), 499);
  await page.locator('.inventory_options a').click();
  await page.locator('#inventory_product_data').waitFor({ state: 'visible' });
  assert.equal(await page.locator('#_sku').inputValue(), 'DEMO-001');
  await appearance('product-editor-desktop');
  result.checks.push({ name: 'native product price, inventory tab and SKU controls', passed: true, saved: false });

  await go('/wp-admin/');
  await page.locator('.urumi-admin-metric').filter({ hasText: 'Orders' }).click();
  await page.locator('.wp-list-table').waitFor();
  await appearance('orders-desktop');
  await page.locator('.search-box input[type=search]').fill('21');
  await page.locator('.search-box input[type=submit]').click();
  await page.waitForURL(/s=21/);
  await page.locator('.order_number').filter({ hasText: '#21' }).waitFor();
  result.checks.push({ name: 'order search', passed: true });
  await go('/wp-admin/admin.php?page=wc-orders&action=edit&id=21');
  await page.locator('#order_status').waitFor();
  assert.equal(await page.locator('#order_status').inputValue(), 'wc-processing');
  await page.getByRole('link', { name: 'Urumi Demo Product', exact: true }).waitFor();
  await appearance('order-detail-desktop');
  result.checks.push({ name: 'existing order and native status controls', passed: true, orderId: 21, saved: false });
  await go('/wp-admin/admin.php?page=wc-settings&tab=checkout&section=cod');
  const cod = page.getByRole('checkbox', { name: 'Enable cash on delivery payments', exact: true });
  await cod.waitFor();
  assert(await cod.isChecked());
  await appearance('settings-desktop');
  result.checks.push({ name: 'cash-on-delivery settings controls', passed: true, saved: false });

  await page.setViewportSize({ width: 390, height: 844 });
  for (const [name, path] of [
    ['dashboard-mobile', '/wp-admin/'],
    ['products-mobile', '/wp-admin/edit.php?post_type=product'],
    ['product-editor-mobile', '/wp-admin/post.php?post=12&action=edit'],
    ['orders-mobile', '/wp-admin/admin.php?page=wc-orders'],
    ['order-detail-mobile', '/wp-admin/admin.php?page=wc-orders&action=edit&id=21'],
    ['settings-mobile', '/wp-admin/admin.php?page=wc-settings&tab=checkout&section=cod'],
  ]) {
    await go(path);
    await appearance(name);
  }
  await go('/wp-admin/');
  await page.locator('#wp-admin-bar-menu-toggle a').click();
  await page.locator('#menu-posts-product > a').waitFor({ state: 'visible' });
  await page.locator('#menu-posts-product > a').click();
  await page.locator('#menu-posts-product .wp-submenu a[href="edit.php?post_type=product"]').click();
  await page.waitForURL(/post_type=product/, { waitUntil: 'domcontentloaded' });
  result.checks.push({ name: 'native mobile menu opens and navigates', passed: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator('#wp-admin-bar-my-account').hover();
  await page.locator('#wp-admin-bar-logout a').click();
  await page.locator('#user_login').waitFor();
  result.checks.push({ name: 'native admin logout', passed: true });
  await go('/');
  assert.equal(await page.locator('link#urumi-shop-admin-css').count(), 0);
  await page.getByRole('heading', { name: /Find your next/ }).waitFor();
  result.checks.push({ name: 'admin stylesheet isolated from storefront', passed: true });
  result.externalOrigins = [...new Set(result.externalOrigins)];
  result.status = 'PASS';
} catch (error) {
  result.error = error.message;
  await page.screenshot({ path: `${out}/failure.png`, fullPage: true });
  throw error;
} finally {
  await writeFile(`${out}/browser.json`, JSON.stringify(result, null, 2) + '\n');
  await browser.close();
  console.log(JSON.stringify({ status: result.status, checks: result.checks.length, artifact: `${out}/browser.json` }));
}
