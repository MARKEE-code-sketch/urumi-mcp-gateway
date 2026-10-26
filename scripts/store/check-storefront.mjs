// Real local-shop checks. No traces, HAR, passwords, cookies or order keys saved.
import { chromium } from '../../frontend/node_modules/playwright/index.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const origin = 'https://shop-m10.urumi.test';
const out = 'docs/evidence/ui-refresh/storefront';
const access = JSON.parse(await readFile('.tools/operator/m10/access.json', 'utf8'));
let existing;
try { existing = JSON.parse(await readFile(`${out}/browser.json`, 'utf8')); } catch {}
if (process.argv.includes('--reuse-order') && !existing?.orderId) {
  existing = JSON.parse(await readFile(`${out}/purchase-browser.json`, 'utf8'));
}
if (existing?.orderId && !process.argv.includes('--reuse-order')) {
  throw new Error('An order already exists. Use --reuse-order to verify without creating another purchase.');
}
const result = { status: 'FAIL', checks: [], externalOrigins: [], pageErrors: [], testTag: `storefront-${Date.now()}` };
if (existing?.orderId) result.orderId = existing.orderId;
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(20000);
page.on('request', request => {
  const url = new URL(request.url());
  if (!['data:', 'blob:'].includes(url.protocol) && url.hostname !== new URL(origin).hostname) result.externalOrigins.push(url.origin);
});
page.on('pageerror', error => result.pageErrors.push(error.message));
async function go(path) { await page.goto(origin + path, { waitUntil: 'domcontentloaded' }); }
async function shot(name) { await page.screenshot({ path: `${out}/${name}.png`, fullPage: true }); }
async function layout(name) {
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(async () => {
    for (const image of document.images) image.loading = 'eager';
    await Promise.all([...document.images].map(image => image.decode().catch(() => {})));
  });
  const state = await page.evaluate(() => ({
    width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
    brokenImages: [...document.images].filter(i => !i.complete || !i.naturalWidth).map(i => new URL(i.src).pathname),
    font: getComputedStyle(document.body).fontFamily,
  }));
  assert(state.scrollWidth <= state.width + 1, `${name} horizontal overflow`);
  assert.deepEqual(state.brokenImages, [], `${name} broken images`);
  result.checks.push({ name, ...state });
  await shot(name);
}
try {
  await go('/');
  await page.getByRole('heading', { name: /Find your next/ }).waitFor();
  await layout('home-desktop');
  await page.keyboard.press('Tab');
  assert.equal(await page.locator(':focus').innerText(), 'Skip to content');
  result.checks.push({ name: 'keyboard skip link', passed: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await layout('home-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator('.primary-nav').getByRole('link', { name: 'All products' }).click();
  await page.locator('ul.products li.product').first().waitFor();
  result.productCount = await page.locator('ul.products li.product').count();
  await layout('catalog-desktop');
  await page.locator('select.orderby').selectOption('price-desc');
  await page.waitForURL(/orderby=price-desc/);
  result.checks.push({ name: 'catalog sorting', passed: true });
  await page.getByRole('searchbox', { name: 'Search products' }).fill('Notebook');
  await page.locator('.site-search').getByRole('button', { name: 'Search' }).click();
  await page.getByRole('heading', { name: 'M10 Browser Demo Notebook', exact: true }).waitFor();
  result.checks.push({ name: 'product search', passed: true });
  await page.getByRole('searchbox', { name: 'Search products' }).fill('no-such-product-storefront-check');
  await page.locator('.site-search').getByRole('button', { name: 'Search' }).click();
  await page.getByText(/No products were found/).waitFor();
  result.checks.push({ name: 'empty search', passed: true });

  await go('/shop/');
  await page.locator('li.product').filter({ hasText: 'Urumi Demo Product' }).locator('a.woocommerce-LoopProduct-link').click();
  await page.locator('h1.product_title').waitFor();
  await layout('product-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await layout('product-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator('form.cart input.qty').fill('2');
  await page.locator('button.single_add_to_cart_button').click();
  await page.locator('.woocommerce-message').waitFor();
  assert.equal((await page.locator('.cart-count').innerText()).trim(), '2');
  await page.locator('.header-actions .cart-link').click();
  await page.locator('.woocommerce-cart-form').waitFor();
  await layout('cart-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await layout('cart-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator('.woocommerce-cart-form input.qty').fill('1');
  await page.getByRole('button', { name: 'Update cart' }).click();
  await page.waitForFunction(() => document.querySelector('.cart-count')?.textContent.trim() === '1');
  result.checks.push({ name: 'cart quantity and header count', passed: true });
  await page.locator('a.remove').click();
  await page.getByText('Your cart is currently empty.').waitFor();
  result.checks.push({ name: 'remove and empty cart', passed: true });

  // Prove asynchronous catalogue add-to-cart updates the shared navigation badge.
  await go('/shop/');
  await page.locator('li.product').filter({ hasText: 'Urumi Demo Product' }).locator('a.add_to_cart_button').click();
  await page.waitForFunction(() => document.querySelector('.cart-count')?.textContent.trim() === '1');
  result.checks.push({ name: 'AJAX catalogue cart count', passed: true });
  await go('/checkout/');
  await page.locator('#place_order').waitFor();
  await layout('checkout-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await layout('checkout-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator('#place_order').click();
  await page.locator('.woocommerce-error').waitFor();
  result.checks.push({ name: 'checkout required-field validation', passed: true });
  if (existing?.orderId) {
    result.orderId = existing.orderId;
    result.checks.push({ name: 'existing browser purchase retained', orderId: existing.orderId, source: 'purchase-browser.json', newOrderSubmitted: false });
  } else {
  const values = {
    billing_first_name: 'Storefront', billing_last_name: 'Test',
    billing_address_1: '1 Local Test Street', billing_city: 'New Delhi',
    billing_postcode: '110001', billing_phone: '9999999999',
    billing_email: `${result.testTag}@example.test`, order_comments: result.testTag,
  };
  for (const [id, value] of Object.entries(values)) await page.locator(`#${id}`).fill(value);
  if (await page.locator('#billing_state').count()) await page.locator('#billing_state').selectOption('DL');
  if (await page.locator('#terms').count()) await page.locator('#terms').check();
  await page.locator('#payment_method_cod').check();
  // Submit once. If this becomes uncertain, inspect stored orders before any retry.
  await page.locator('#place_order').click();
  await page.waitForURL(/order-received\/\d+/, { timeout: 60000 });
  result.orderId = Number(new URL(page.url()).pathname.match(/order-received\/(\d+)/)[1]);
  await page.getByText(/Thank you. Your order has been received/).waitFor();
  await shot('order-confirmation');
  result.checks.push({ name: 'cash on delivery order confirmation', passed: true, orderId: result.orderId });
  }

  await go('/my-account/');
  await page.locator('#username').fill(access.store_username);
  await page.locator('#password').fill(access.store_password);
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  await page.locator('.woocommerce-MyAccount-navigation').waitFor();
  await layout('account-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await layout('account-mobile');
  await page.locator('.woocommerce-MyAccount-navigation-link--orders a').click();
  await page.locator('.woocommerce-MyAccount-content').waitFor();
  await page.locator('.woocommerce-MyAccount-navigation-link--customer-logout a').click();
  await page.locator('#username').waitFor();
  result.checks.push({ name: 'account login, orders navigation and logout', passed: true });
  result.externalOrigins = [...new Set(result.externalOrigins)];
  assert.deepEqual(result.pageErrors, []);
  assert.deepEqual(result.externalOrigins, []);
  result.status = 'PASS';
} catch (error) {
  result.error = error.message;
  await shot('failure');
  throw error;
} finally {
  await writeFile(`${out}/browser.json`, JSON.stringify(result, null, 2) + '\n');
  await browser.close();
  console.log(JSON.stringify({ status: result.status, checks: result.checks.length, orderId: result.orderId, artifact: `${out}/browser.json` }));
}
