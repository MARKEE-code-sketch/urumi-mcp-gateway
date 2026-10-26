// Read-only visual proof of registered Context7 discovery; never reads its token.
import { chromium } from '../../frontend/node_modules/playwright/index.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const origin = 'https://dashboard-m10.urumi.test';
const output = 'docs/evidence/fixes/context7-discovery-20261025';
const access = JSON.parse(await readFile('.tools/operator/m10/access.json', 'utf8'));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const evidence = { status: 'FAIL', tls_bypass: false };
try {
  await page.goto(origin + '/login');
  await page.getByLabel('Email', { exact: true }).fill(access.admin_email);
  await page.getByLabel('Password', { exact: true }).fill(access.admin_password);
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  const card = page.locator('.server-card').filter({ has: page.getByRole('heading', { name: 'Context7', exact: true }) });
  await card.waitFor();
  await card.getByRole('button', { name: 'View tools', exact: true }).click();
  await page.locator('.server-tools-panel .tool-card h3').first().waitFor({ timeout: 20000 });
  evidence.tools = await page.locator('.server-tools-panel .tool-card h3').allTextContents();
  assert.deepEqual(evidence.tools.sort(), ['context7__query-docs', 'context7__resolve-library-id']);
  const response = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname === '/api/v1/servers');
  await page.getByRole('button', { name: 'Refresh servers', exact: true }).click();
  await response;
  await card.locator('.status-connected').waitFor();
  evidence.recorded_status = await card.locator('.status-badge').innerText();
  await card.getByRole('button', { name: 'View tools', exact: true }).click();
  await page.locator('.server-tools-panel .tool-card h3').first().waitFor();
  await page.screenshot({ path: `${output}/connected-tools.png`, fullPage: true });
  evidence.status = 'PASS';
} catch (error) {
  evidence.error = error.message;
  throw error;
} finally {
  await writeFile(`${output}/browser.json`, JSON.stringify(evidence, null, 2) + '\n');
  await browser.close();
  console.log(JSON.stringify(evidence));
}
