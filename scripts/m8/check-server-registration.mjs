// Live disabled alias exercises credential storage without calling an upstream.
import { chromium } from '../../frontend/node_modules/playwright/index.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const origin = 'https://dashboard-m10.urumi.test';
const output = 'docs/evidence/fixes/server-registration-20261025';
const access = JSON.parse(await readFile('.tools/operator/m10/access.json', 'utf8'));
const name = 'Registration regression check';
const slug = 'qa-reg-' + Date.now().toString(36);
const dummy = 'LOCAL-DUMMY-NOT-A-REAL-CREDENTIAL';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const result = { status: 'FAIL', slug, responses: [] };
let created;
page.setDefaultTimeout(20000);
const waitChange = (method) => page.waitForResponse(r => r.request().method() === method
  && new URL(r.url()).pathname.startsWith('/api/v1/servers'));
async function form(serverName) {
  await page.getByLabel('Name', { exact: true }).fill(serverName);
  await page.getByLabel('Slug', { exact: true }).fill(slug);
  await page.getByLabel('URL', { exact: true }).fill('https://learn.microsoft.com/api/mcp');
  await page.getByLabel('Enabled', { exact: true }).uncheck();
  await page.getByLabel('Authentication', { exact: true }).selectOption('bearer');
  await page.getByLabel('Credential value', { exact: true }).fill(dummy);
}
async function capture(response) {
  const text = response.status() === 204 ? '' : await response.text();
  assert(!text.includes(dummy));
  result.responses.push({ method: response.request().method(), status: response.status(),
    contentType: response.headers()['content-type'] });
  return text ? JSON.parse(text) : null;
}
try {
  await page.goto(origin + '/login');
  await page.getByLabel('Email', { exact: true }).fill(access.admin_email);
  await page.getByLabel('Password', { exact: true }).fill(access.admin_password);
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  await page.locator('.server-card').first().waitFor();
  const before = await page.locator('.server-card h2').allTextContents();
  assert.equal(before.length, 3);
  await page.getByRole('button', { name: 'Add server', exact: true }).click();
  await form(name);
  let response = waitChange('POST');
  await page.getByRole('button', { name: 'Save server', exact: true }).click();
  response = await response;
  const data = await capture(response);
  assert.equal(response.status(), 201);
  created = data.id;
  assert.equal(data.enabled, false);
  assert.equal(data.auth_type, 'bearer');
  const card = page.locator('.server-card').filter({ has: page.getByRole('heading', { name, exact: true }) });
  await card.waitFor();
  await page.screenshot({ path: `${output}/server-created.png`, fullPage: true });
  await card.getByRole('button', { name: 'Edit ' + name, exact: true }).click();
  await page.getByLabel('Name', { exact: true }).fill(name + ' edited');
  response = waitChange('PATCH');
  await page.getByRole('button', { name: 'Save server', exact: true }).click();
  response = await response;
  assert.equal(response.status(), 200);
  const changed = await capture(response);
  assert.equal(changed.auth_type, 'bearer');
  const edited = page.locator('.server-card').filter({ has: page.getByRole('heading', { name: name + ' edited', exact: true }) });
  await edited.waitFor();
  await edited.getByRole('button', { name: 'Remove', exact: true }).click();
  response = waitChange('DELETE');
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
  response = await response;
  await capture(response);
  assert.equal(response.status(), 204);
  await edited.waitFor({ state: 'detached' });
  await page.waitForFunction(() => document.querySelectorAll('.server-card').length === 3);
  assert.deepEqual((await page.locator('.server-card h2').allTextContents()).sort(), before.sort());
  result.disabled_bearer_create_edit_remove = true;

  let intercepted = 0;
  await page.route(origin + '/api/v1/servers', async route => {
    if (route.request().method() === 'POST') {
      intercepted++;
      return route.fulfill({ status: 503, contentType: 'text/plain', body: 'no available server\n' });
    }
    return route.continue();
  });
  await page.getByRole('button', { name: 'Add server', exact: true }).click();
  await form('Intercepted outage check');
  await page.getByRole('button', { name: 'Save server', exact: true }).click();
  await page.getByText('The gateway is temporarily unavailable. Please try again shortly.', { exact: true }).waitFor();
  await page.getByText(/The change may have happened/).waitFor();
  assert.equal(intercepted, 1);
  result.outage_message = 'Correct message and uncertain-write warning, one request, no automatic retry';
  await page.screenshot({ path: `${output}/outage-feedback.png`, fullPage: true });
  await page.unroute(origin + '/api/v1/servers');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  const refreshed = page.waitForResponse(r => r.request().method() === 'GET'
    && new URL(r.url()).pathname === '/api/v1/servers');
  await page.getByRole('button', { name: 'Refresh servers', exact: true }).click();
  await refreshed;
  await page.waitForFunction(() => document.querySelectorAll('.server-card').length === 3);
  result.final_servers = await page.locator('.server-card h2').allTextContents();
  assert.equal(result.final_servers.length, 3);
  result.status = 'PASS';
} catch (error) {
  result.error = error.message;
  result.possibly_created_server_id = created;
  throw error;
} finally {
  await writeFile(`${output}/browser.json`, JSON.stringify(result, null, 2) + '\n');
  await browser.close();
  console.log(JSON.stringify({ status: result.status, artifact: `${output}/browser.json` }));
}
