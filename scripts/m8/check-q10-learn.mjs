// One exact Q10 prompt through actual dashboard chat; no write requests or retries.
import { chromium } from '../../frontend/node_modules/playwright/index.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const origin = 'https://dashboard-m10.urumi.test';
const output = 'docs/evidence/fixes/q10-learn-chat';
const access = JSON.parse(await readFile('.tools/operator/m10/access.json', 'utf8'));
const prompt = 'Use Microsoft Learn to find official documentation explaining Kubernetes Pods. Summarise the result and provide the source links.';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const evidence = { status: 'FAIL', prompt, tls_bypass: false };
try {
  await page.goto(origin + '/login');
  await page.getByLabel('Email', { exact: true }).fill(access.admin_email);
  await page.getByLabel('Password', { exact: true }).fill(access.admin_password);
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  await page.locator('.server-card').first().waitFor();
  await page.getByRole('link', { name: 'Chat', exact: true }).click();
  await page.getByLabel('Message', { exact: true }).fill(prompt);
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/chat'
    && r.request().method() === 'POST', { timeout: 130000 });
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const received = await response;
  evidence.http_status = received.status();
  evidence.reply = await received.json();
  await page.locator('.exchange').first().waitFor();
  await page.locator('.tool-activity > summary').click();
  evidence.rendered_links = await page.locator('.markdown-answer a').evaluateAll(
    nodes => nodes.map(node => ({ label: node.textContent, href: node.href })));
  await page.screenshot({ path: `${output}/live-chat.png`, fullPage: true });
  assert.equal(evidence.reply.state, 'completed');
  assert(evidence.reply.tool_calls.some(call => call.tool_name === 'learn__microsoft_docs_search' && call.outcome === 'success'));
  assert(evidence.rendered_links.some(link => link.href.startsWith('https://learn.microsoft.com/')));
  assert(!evidence.reply.answer.includes('Do not repeat the write'));
  assert(!evidence.reply.answer.includes('could not display the complete result'));
  evidence.status = 'PASS';
} catch (error) {
  evidence.error = error.message;
  throw error;
} finally {
  await writeFile(`${output}/live-chat.json`, JSON.stringify(evidence, null, 2) + '\n');
  await browser.close();
  console.log(JSON.stringify({ status: evidence.status, state: evidence.reply?.state,
    tools: evidence.reply?.tool_calls?.map(call => ({ name: call.tool_name, outcome: call.outcome })),
    source_links: evidence.rendered_links?.length, artifact: `${output}/live-chat.json` }));
}
