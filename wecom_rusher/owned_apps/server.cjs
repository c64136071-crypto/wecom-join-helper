'use strict';
// Fixed self-owned application fixture. No workflow-provided URL, path or code.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function writeJson(file, data) {
  const tmp = file + '.tmp';
  const fd = fs.openSync(tmp, 'wx');
  try { fs.writeSync(fd, JSON.stringify(data)); fs.fsyncSync(fd); }
  finally { fs.closeSync(fd); }
  fs.renameSync(tmp, file);
}
function fixtureControl(root) {
  const file = path.join(root, 'test-control.json');
  if (!fs.existsSync(file)) return {};
  if (fs.statSync(file).size > 2048) throw new Error('fixture_control_rejected');
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const allowed = new Set(['delayBeforeCommitMs', 'dropAck', 'identityChanged', 'identityAfterInput', 'duplicateName', 'compact', 'securityProbe']);
  if (!data || Array.isArray(data) || Object.keys(data).some(k => !allowed.has(k))) throw new Error('fixture_control_rejected');
  for (const [key, value] of Object.entries(data)) {
    if (key === 'delayBeforeCommitMs') {
      if (!Number.isInteger(value) || value < 0 || value > 3000) throw new Error('fixture_control_rejected');
    } else if (typeof value !== 'boolean') throw new Error('fixture_control_rejected');
  }
  return data;
}
async function body(req) {
  if (req.headers['content-type'] !== 'application/json') throw new Error('body_rejected');
  if (!/^\d+$/.test(req.headers['content-length'] || '') || Number(req.headers['content-length']) > 8192) throw new Error('body_rejected');
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 8192) throw new Error('body_rejected');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}
function createOwnedServer(root, config, appPath) {
  const records = [];
  const exports = [];
  const server = http.createServer(async (req, res) => {
    res.setHeader('Connection', 'close');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    try {
      const origin = `http://127.0.0.1:${server.address().port}`;
      if (req.headers.host !== `127.0.0.1:${server.address().port}` ||
          (req.headers.origin && req.headers.origin !== origin)) throw new Error('origin_rejected');
      const control = fixtureControl(root);
      const requestPath = new URL(req.url,origin).pathname;
      const knownPath = ['/health','/owned-form','/owned-report','/app.js','/api/save','/api/export','/api/redirect'].includes(requestPath) ? requestPath : 'unrecognized';
      fs.appendFileSync(path.join(config.artifacts,'app-requests.jsonl'),JSON.stringify({method:req.method,path:knownPath})+'\n');
      if (control.securityProbe && req.method === 'GET' && req.url === '/api/redirect') {
        res.writeHead(302,{Location:origin+'/health'}); return res.end();
      }
      if (req.method === 'GET' && req.url === '/health') {
        res.setHeader('Content-Type','application/json');
        return res.end(JSON.stringify({appId:config.appId,instanceId:config.instanceId}));
      }
      const appFile = config.appId === 'owned-dom-form' ? 'form' : 'report';
      if (req.method === 'GET' && req.url === '/app.js') {
        res.setHeader('Content-Type','text/javascript; charset=utf-8');
        return res.end(fs.readFileSync(path.join(__dirname,appFile+'.js')));
      }
      if (req.method === 'GET' && req.url === appPath) {
        let html = fs.readFileSync(path.join(__dirname,appFile+'.html'),'utf8').replaceAll('{{INSTANCE}}',config.instanceId);
        if (control.identityChanged) html = html.replace('data-app-id="owned-dom-form"','data-app-id="wrong-owned-app"');
        if (control.identityAfterInput) html = html.replace('<body ', '<body data-identity-after-input="true" ');
        if (control.securityProbe) html = html.replace('<body ', `<body data-security-probe="true" data-test-off-origin="http://localhost:${server.address().port}/health" `);
        if (control.duplicateName) html = html.replace('</form>','<input data-target="name" value="similar"></form>');
        if (control.compact) html = html.replace('max-width:680px','max-width:280px').replace('<form id="entry">','<form id="entry" style="display:flex;flex-direction:column-reverse">');
        res.setHeader('Content-Type','text/html; charset=utf-8');
        res.setHeader('Content-Security-Policy',`default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; connect-src 'self'${control.securityProbe ? ' http://localhost:'+server.address().port : ''}; form-action 'self'; frame-ancestors 'none'`);
        return res.end(html);
      }
      if (req.method === 'POST' && req.url === '/api/save' && config.appId === 'owned-dom-form') {
        const data = await body(req);
        if (!data || Object.keys(data).sort().join(',') !== 'inputEvents,instanceId,name,quantity' ||
            data.instanceId !== config.instanceId || typeof data.name !== 'string' || data.name.length < 1 || data.name.length > 128 ||
            !Number.isInteger(data.quantity) || data.quantity < 1 || data.quantity > 10000 ||
            !Number.isInteger(data.inputEvents) || data.inputEvents < 1 || data.inputEvents > 10000 || records.length >= 64) throw new Error('body_rejected');
        await sleep(control.delayBeforeCommitMs || 0);
        const record = {name:data.name,quantity:data.quantity,inputEvents:data.inputEvents,receipt:records.length+1,instanceId:config.instanceId};
        records.push(record);
        writeJson(path.join(config.artifacts,'app-records.json'),records);
        if (control.dropAck) return; // Test fixture only: real commit, no application acknowledgement.
        res.setHeader('Content-Type','application/json');
        return res.end(JSON.stringify({receipt:record.receipt,instanceId:config.instanceId}));
      }
      if (req.method === 'GET' && req.url.startsWith('/api/export?') && config.appId === 'owned-dom-report') {
        const params = new URL(req.url,origin).searchParams;
        const period = params.get('period');
        if (Array.from(params.keys()).sort().join(',') !== 'instanceId,period' ||
            params.get('instanceId') !== config.instanceId || !['2026-10','2026-09'].includes(period) || exports.length >= 64)
          throw new Error('export_rejected');
        const rows = [{period:'2026-10',amount:12},{period:'2026-10',amount:8},{period:'2026-09',amount:99}];
        const total = rows.filter(row=>row.period===period).reduce((n,row)=>n+row.amount,0);
        const bytes = Buffer.from(`period,total\n${period},${total}\n`,'utf8');
        const receipt = {period,total,receipt:exports.length+1,instanceId:config.instanceId,
          length:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex')};
        exports.push(receipt);
        writeJson(path.join(config.artifacts,'app-exports.json'),exports);
        fs.writeFileSync(path.join(config.artifacts,'app-export.csv'),bytes);
        res.setHeader('Content-Type','text/csv; charset=utf-8');
        res.setHeader('X-Owned-Instance',config.instanceId);
        res.setHeader('X-Owned-Receipt',String(receipt.receipt));
        return res.end(bytes);
      }
      res.writeHead(404); res.end();
    } catch (_error) {
      if (!res.headersSent) res.writeHead(400);
      res.end('owned_request_rejected');
    }
  });
  server.requestTimeout = 5000;
  server.headersTimeout = 5000;
  return server;
}
module.exports = {createOwnedServer, writeJson, fixtureControl};
