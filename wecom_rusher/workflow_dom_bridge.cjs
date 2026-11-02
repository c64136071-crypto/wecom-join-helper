'use strict';
// Trusted bridge entry: no listeners/descendants until the parent has assigned its Job.
const fs = require('node:fs');
const path = require('node:path');
const {createOwnedServer} = require('./owned_apps/server.cjs');
const {captureDiagnostic} = require('./workflow_dom_capture.cjs');
const {spawn} = require('node:child_process');
const root = path.resolve(process.argv[2]);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function event(row) {
  const fd = fs.openSync(path.join(root, 'node-events.jsonl'), 'a');
  try { fs.writeSync(fd, JSON.stringify(row) + '\n'); fs.fsyncSync(fd); }
  finally { fs.closeSync(fd); }
}
function save(name, data) {
  if (fs.existsSync(path.join(root, name))) throw new Error('owned_message_already_exists');
  replyFile(name, data);
}
function replyFile(name, data) {
  const temp = path.join(root, name + '.tmp');
  const fd = fs.openSync(temp, 'wx');
  try { fs.writeSync(fd, JSON.stringify(data)); fs.fsyncSync(fd); }
  finally { fs.closeSync(fd); }
  fs.renameSync(temp, path.join(root, name));
}
async function openOwnedBrowser(config, origin, appPath) {
  const profilePath = path.join(root, 'runtime-temp', 'browser-profile');
  fs.mkdirSync(profilePath);
  const out = fs.openSync(path.join(root, 'browser.stdout.txt'), 'wx');
  const err = fs.openSync(path.join(root, 'browser.stderr.txt'), 'wx');
  const args = ['--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
    `--user-data-dir=${profilePath}`, '--no-first-run', '--no-default-browser-check',
    '--disable-background-networking', '--disable-component-update', '--disable-sync',
    '--disable-extensions', '--disable-default-apps', '--metrics-recording-only', '--no-startup-window'];
  if (config.headless) args.push('--headless=new');
  const chrome = spawn(config.browserExe, args, {stdio: ['ignore', out, err]});
  fs.closeSync(out); fs.closeSync(err);
  event({event: 'browser_spawned', pid: chrome.pid, profilePath});
  save('browser-spawn.json', {browserPid: chrome.pid, profilePath});
  let spawnFailed = false;
  chrome.on('error', () => { spawnFailed = true; });
  const activePort = path.join(profilePath, 'DevToolsActivePort');
  const until = Date.now() + 12000;
  while (!fs.existsSync(activePort)) {
    if (spawnFailed || chrome.exitCode !== null || Date.now() >= until) throw new Error('browser_start_failed');
    await sleep(10);
  }
  const cdpPort = Number(fs.readFileSync(activePort, 'utf8').split('\n')[0]);
  if (!Number.isInteger(cdpPort) || [9222, 18080, 13306, 18883, 18884].includes(cdpPort)) throw new Error('owned_port_rejected');
  const browserInfo = {browserPid: chrome.pid, profilePath, cdpPort};
  save('browser-info.json', browserInfo);
  event({event: 'browser_cdp_listening', pid: chrome.pid, port: cdpPort});
  const {chromium} = require(config.playwrightPath);
  // This endpoint belongs to the Chrome Popen above, never an existing user browser.
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${cdpPort}`, {timeout: 10000});
  const context = await browser.newContext({viewport: {width: 900, height: 700}, acceptDownloads: true, serviceWorkers: 'block'});
  let page;
  let refusedContext = false;
  const allowedPaths = new Set([appPath, '/app.js', '/api/save', '/api/export', '/api/redirect']);
  await context.route('**/*', async route => {
    try {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== origin || url.protocol !== 'http:') {
        refusedContext = true;
        event({event: 'external_request_blocked'});
        return await route.abort();
      }
      if (!allowedPaths.has(url.pathname) || request.isNavigationRequest() &&
          (url.href !== origin + appPath || request.frame() !== page.mainFrame())) {
        refusedContext = true;
        event({event: 'navigation_or_path_blocked'});
        return await route.abort();
      }
      // Fetch exactly once without following redirects, including same-origin 3xx.
      const response = await route.fetch({maxRedirects: 0, maxRetries: 0, timeout: 5000});
      try {
        if (response.status() >= 300 && response.status() < 400) {
          refusedContext = true;
          event({event: 'redirect_blocked'});
          return await route.abort();
        }
        const body = await response.body();
        if (body.length > 65536) throw new Error('owned_response_too_large');
        await route.fulfill({response, body});
      } finally { await response.dispose(); }
    } catch (_error) {
      refusedContext = true;
      event({event: 'owned_request_failed'});
      await route.abort().catch(() => {});
    }
  });
  context.on('page', created => {
    if (page && created !== page) {
      refusedContext = true;
      event({event: 'popup_blocked'});
      created.close().catch(() => {});
    }
  });
  page = await context.newPage();
  await page.goto(origin + appPath, {timeout: 10000, waitUntil: 'load'});
  await page.screenshot({path: path.join(config.artifacts, 'initial.png'), timeout: 5000});
  const targets = config.appId === 'owned-dom-form'
    ? {name: '[data-target="name"]', quantity: '[data-target="quantity"]', save: '[data-target="save"]', receipt: '[data-target="receipt"]'}
    : {period: '[data-target="period"]', total: '[data-target="total"]', export: '[data-target="export"]', receipt: '[data-target="receipt"]'};
  async function guard(target) {
    if (refusedContext || page.url() !== origin + appPath || await page.locator('body').getAttribute('data-app-id') !== config.appId ||
        await page.locator('body').getAttribute('data-instance-id') !== config.instanceId || page.frames().length !== 1)
      throw new Error('target_identity_changed');
    if (!Object.hasOwn(targets, target)) throw new Error('target_rejected');
    const locator = page.locator(targets[target]);
    if (await locator.count() !== 1 || !await locator.isVisible()) throw new Error('target_not_unique');
    return locator;
  }
  async function execute(command) {
    if (command.action === 'wait') {
      if (command.target !== null || !Number.isInteger(command.value) || command.value < 0 || command.value > 10000)
        throw new Error('target_rejected');
      await guard('receipt');
      await sleep(command.value);
      await guard('receipt');
      return null;
    }
    const locator = await guard(command.target);
    if (command.action === 'click' && command.target === 'export') {
      if (command.value !== null) throw new Error('target_rejected');
      const [download] = await Promise.all([page.waitForEvent('download', {timeout: 5000}), locator.click({timeout: 5000})]);
      if (!download.url().startsWith('blob:' + origin + '/')) throw new Error('target_rejected');
      const file = path.join(config.artifacts, 'export.csv');
      await download.saveAs(file);
      if (fs.statSync(file).size > 65536 || await download.failure()) throw new Error('target_rejected');
      await guard(command.target);
      await captureDiagnostic(page, path.join(config.artifacts, 'final.png'), () => guard(command.target), event);
      return null;
    }
    if (command.action === 'click' && command.target === 'save') {
      if (command.value !== null) throw new Error('target_rejected');
      const before = Number(await page.locator('[data-target="receipt"]').textContent());
      await locator.click({timeout: 5000});
      await page.waitForFunction(n => Number(document.querySelector('[data-target="receipt"]').textContent) === n, before + 1, {timeout: 5000});
      await guard(command.target);
      await captureDiagnostic(page, path.join(config.artifacts, 'final.png'), () => guard(command.target), event);
      return null;
    }
    if (command.action === 'input') {
      const valid = command.target === 'name' && typeof command.value === 'string' && command.value.length >= 1 && command.value.length <= 128 ||
        command.target === 'quantity' && Number.isInteger(command.value) && command.value >= 1 && command.value <= 10000 ||
        command.target === 'period' && ['2026-10', '2026-09'].includes(command.value);
      if (!valid) throw new Error('target_rejected');
      if (command.target === 'period') await locator.selectOption(command.value, {timeout: 5000});
      else await locator.fill(String(command.value), {timeout: 5000});
      await guard(command.target);
      const inputEvents = Number(await page.locator('body').getAttribute('data-input-events'));
      fs.appendFileSync(path.join(config.artifacts, 'dom-observations.jsonl'), JSON.stringify({action: 'input', target: command.target, inputEvents}) + '\n');
      await captureDiagnostic(page, path.join(config.artifacts, 'final.png'), () => guard(command.target), event);
      return null;
    }
    if (command.action === 'locate') return true;
    if (command.action === 'read' || command.action === 'assert') {
      if (command.target === 'receipt') return Number((await locator.textContent()).trim());
      if (command.target === 'name' || command.target === 'period') return locator.inputValue();
      if (command.target === 'total') return Number((await locator.textContent()).trim());
      if (command.target === 'quantity') return Number(await locator.inputValue());
    }
    throw new Error('action_not_implemented');
  }
  return {browserInfo, execute, close: async () => {
    await Promise.race([context.close().catch(() => {}), sleep(1000)]);
    await Promise.race([browser.close().catch(() => {}), sleep(1000)]);
    if (chrome.exitCode === null) chrome.kill();
  }};
}
async function main() {
  event({event: 'node_waiting_for_parent_job', pid: process.pid});
  while (!fs.existsSync(path.join(root, 'start.json'))) await sleep(10);
  const config = JSON.parse(fs.readFileSync(path.join(root, 'start.json'), 'utf8'));
  if (fs.existsSync(path.join(root, 'stop'))) {
    event({event: 'startup_cancelled_before_resources', pid: process.pid});
    return;
  }
  const appPath = config.appId === 'owned-dom-form' ? '/owned-form' : '/owned-report';
  const server = createOwnedServer(root, config, appPath);
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const httpPort = server.address().port;
  if ([9222, 18080, 13306, 18883, 18884].includes(httpPort)) throw new Error('forbidden_allocated_port');
  const info = {appId: config.appId, instanceId: config.instanceId, nodePid: process.pid, httpPort};
  save('server-info.json', info);
  event({event: 'server_listening', pid: process.pid, host: '127.0.0.1', port: httpPort});
  const controller = config.serverOnly ? null : await openOwnedBrowser(config, `http://127.0.0.1:${httpPort}`, appPath);
  save('ready.json', {...info, ...(controller ? controller.browserInfo : {})});
  let stopping = false;
  const timer = setInterval(async () => {
    if (fs.existsSync(path.join(root, 'stop'))) {
      stopping = true;
      clearInterval(timer);
      if (controller) await controller.close();
      server.close(() => process.exit(0));
      server.closeAllConnections();
    }
  }, 20);
  let sequence = 1;
  while (!stopping) {
    const name = String(sequence).padStart(6, '0') + '.json';
    const request = path.join(root, 'requests', name);
    if (!fs.existsSync(request)) { await sleep(10); continue; }
    let response;
    try {
      if (fs.statSync(request).size > 65536 || !controller) throw new Error('target_rejected');
      const command = JSON.parse(fs.readFileSync(request, 'utf8'));
      response = {ok: true, value: await controller.execute(command)};
    } catch (error) {
      const allowed = new Set(['target_identity_changed', 'target_rejected', 'target_not_unique', 'action_not_implemented']);
      response = {ok: false, reason: allowed.has(error.message) ? error.message : 'dom_action_failed'};
    }
    replyFile(path.join('responses', name), response);
    sequence++;
  }
}
main().catch(error => {
  // Only a fixed diagnostic; user/application data and exception text are not logs.
  event({event: 'bridge_failed', pid: process.pid, reason: 'owned_dom_start_failed'});
  save('failure.json', {reason: 'owned_dom_start_failed'});
  process.exitCode = 2;
});
