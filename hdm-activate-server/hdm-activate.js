/**
 * HDM online activation service — HAMI SMART SYSTEMS
 * ───────────────────────────────────────────────────
 * One serial = one computer. Re-activating on the SAME computer always works
 * (also after reinstalling Windows). Activating on a different computer is
 * refused until an admin releases the license.
 *
 * Zero dependencies — plain Node http + crypto.
 *
 * Use A) inside the hamidesigns.shop Express site (Finland):
 *        const activate = require('./routes/hdm-activate');
 *        app.use('/api/hdm', activate.router);
 *
 * Use B) standalone (Iran server or anywhere):
 *        node hdm-activate.js          # listens on 0.0.0.0:17432
 *        PORT=17432 node hdm-activate.js
 *
 * Endpoints:
 *   GET  /api/hdm/ping
 *   POST /api/hdm/activate  {name, key, machine, parts}
 *   POST /api/hdm/check     {name, key, machine, parts}
 *   GET  /api/hdm/admin/list?token=…
 *   POST /api/hdm/admin/release  {token, key}
 *   POST /api/hdm/admin/plan     {token, key, plan}   (change 06/12/99)
 */
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const SECRET = process.env.HDM_SECRET || 'HDM-2026-LICENSE-SECRET-HAMI-SMART-SYSTEMS';
const ADMIN_TOKEN = process.env.HDM_ADMIN_TOKEN || 'hami-admin-change-me';
const DB_FILE = process.env.HDM_DB || path.join(__dirname, 'hdm-activations.json');
const OFFLINE_GRACE_DAYS = 14;
/* Two servers (Finland = primary, Iran = mirror).
   The primary pushes every activation to the mirror so both answer the same. */
const PEER_URL = process.env.HDM_PEER_URL || '';     // e.g. https://smarthami63.shop/hdm-api
const PEER_TOKEN = process.env.HDM_PEER_TOKEN || '';
const MIRROR = String(process.env.HDM_MIRROR || '').toLowerCase() === 'true';
/* optional: serve uploaded files (used by the upload panel on this server) */
const FILES_DIR = process.env.HDM_FILES_DIR || '';

function serveFile(res, urlPath) {
  if (!FILES_DIR) return false;
  const rel = String(urlPath || '').replace(/^\/files\//, '').replace(/\.\./g, '');
  if (!rel) return false;
  const file = path.join(FILES_DIR, rel);
  if (!file.startsWith(path.resolve(FILES_DIR))) return false;
  try {
    const st = fs.statSync(file);
    if (!st.isFile()) return false;
  } catch (e) { return false; }
  const ext = path.extname(file).toLowerCase();
  const types = { '.exe': 'application/octet-stream', '.zip': 'application/zip',
                  '.apk': 'application/vnd.android.package-archive', '.png': 'image/png',
                  '.jpg': 'image/jpeg', '.webp': 'image/webp', '.txt': 'text/plain',
                  '.msi': 'application/octet-stream', '.gz': 'application/gzip' };
  res.setHeader('Content-Type', types[ext] || 'application/octet-stream');
  res.setHeader('Content-Length', st0(file));
  try { fs.createReadStream(file).pipe(res); } catch (e) { return false; }
  return true;
}
function st0(f) { try { return fs.statSync(f).size; } catch (e) { return 0; } }

const PLANS = {
  '06': { days: 180, label: '6 Months' },
  '12': { days: 365, label: '1 Year' },
  '99': { days: 0, label: 'Lifetime' },
};

/* ── storage ─────────────────────────────────────────────────────────── */
let db = { licenses: {}, log: [] };

function load() {
  try {
    const d = JSON.parse(fs.readFileSync(DB_FILE, 'utf8'));
    if (d && typeof d === 'object') db = Object.assign({ licenses: {}, log: [] }, d);
  } catch (e) { /* first run */ }
}
function save() {
  try {
    fs.mkdirSync(path.dirname(DB_FILE), { recursive: true });
    const tmp = DB_FILE + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(db, null, 2));
    fs.renameSync(tmp, DB_FILE);
  } catch (e) { console.error('save failed', e.message); }
}
function log(entry) {
  db.log.unshift(Object.assign({ at: new Date().toISOString() }, entry));
  db.log = db.log.slice(0, 500);
}
load();

/* ── key maths (mirrors hdm_license.py) ──────────────────────────────── */
const hmac = (s) => crypto.createHmac('sha256', SECRET).update(s).digest('hex');
const norm = (n) => String(n || '').trim().replace(/\s+/g, ' ').toLowerCase();
const clean = (k) => String(k || '').toUpperCase().replace(/[^0-9A-Z]/g, '');

function parseKey(key) {
  const k = clean(key);
  if (!k.startsWith('HG') || k.length !== 22) return null;
  return { body: k.slice(2, 14), plan: k.slice(14, 16), sig: k.slice(16, 22) };
}

function verifyKey(name, key) {
  const p = parseKey(key);
  if (!p || !PLANS[p.plan]) return { ok: false, error: 'The key format is not valid.' };
  const n = norm(name);
  const body = crypto.createHash('sha1').update(n).digest('hex').slice(0, 12).toUpperCase();
  if (body !== p.body) return { ok: false, error: 'This key does not belong to that name.' };
  const sig = hmac(n + '|' + p.plan).slice(0, 6).toUpperCase();
  if (sig !== p.sig) return { ok: false, error: 'This key is not valid.' };
  return { ok: true, plan: p.plan, key: clean(key) };
}

/* ── machine matching (tolerant: survives a Windows reinstall) ───────── */
function machineScore(stored, current) {
  if (!stored || !current) return 0;
  const keys = ['board', 'cpu', 'bios', 'guid'].filter(
    (k) => stored[k] && current[k]);
  if (!keys.length) return 0;
  return keys.filter((k) => String(stored[k]).toUpperCase() === String(current[k]).toUpperCase()).length;
}

const STRONG = ['board', 'cpu', 'bios'];   // hardware: survives a Windows reinstall
const WEAK = ['guid'];                     // Windows install id: may change

function sameMachine(stored, current) {
  if (!stored || !current) return false;
  const eq = (k) => stored[k] && current[k] &&
    String(stored[k]).toUpperCase() === String(current[k]).toUpperCase();
  const strongBoth = STRONG.filter((k) => stored[k] && current[k]);
  const strongHits = strongBoth.filter(eq).length;
  if (strongHits >= 1) return true;                  // same mainboard / CPU / BIOS
  if (!strongBoth.length) return WEAK.some(eq);      // only a Windows id available
  return false;                                      // completely different computer
}

function signResponse(obj) {
  const payload = [obj.key, obj.machine || '', String(obj.exp || 0), obj.plan].join('|');
  return crypto.createHmac('sha256', SECRET).update('resp|' + payload).digest('hex').slice(0, 32);
}

/* ── core ────────────────────────────────────────────────────────────── */
function activate(body) {
  const name = String(body.name || '').trim();
  const key = clean(body.key);
  const parts = body.parts || {};
  const machine = String(body.machine || '');

  const v = verifyKey(name, key);
  if (!v.ok) return { status: 400, ok: false, error: v.error };
  if (!machine && !Object.keys(parts).length) {
    return { status: 400, ok: false, error: 'No machine information received.' };
  }

  const now = Date.now();
  let rec = db.licenses[key];

  if (!rec && MIRROR) {
    // the mirror may never invent a license — only the primary may
    return {
      status: 503, ok: false,
      error: 'This license is not known yet. Try again in a moment or contact support.',
    };
  }

  if (!rec) {
    rec = {
      key, name, plan: v.plan,
      parts, machine,
      first: now, last: now, checks: 1,
      last_ip: body.ip || '',
    };
    db.licenses[key] = rec;
    log({ act: 'activate', key, name, machine });
    save();
    syncPush(rec);
  } else {
    if (!sameMachine(rec.parts, parts)) {
      log({ act: 'reject-other-pc', key, name, machine });
      save();
      return {
        status: 409, ok: false,
        error: 'This license is already active on another computer.',
        active_since: new Date(rec.first).toISOString().slice(0, 10),
        hint: 'Ask support to release it, or buy an additional license.',
      };
    }
    rec.parts = parts;              // keep it up to date (e.g. new Windows GUID)
    rec.machine = machine;
    rec.last = now;
    rec.checks = (rec.checks || 0) + 1;
    rec.name = name;
    log({ act: 'recheck', key, name, machine });
    save();
    syncPush(rec);
  }

  const plan = PLANS[rec.plan];
  const expMs = plan.days ? rec.first + plan.days * 86400000 : 0;
  const res = {
    ok: true,
    key: rec.key,
    name: rec.name,
    plan: rec.plan,
    plan_label: plan.label,
    issued: Math.floor(rec.first / 1000),     // seconds
    exp: expMs ? Math.floor(expMs / 1000) : 0, // seconds (0 = lifetime)
    exp_date: expMs ? new Date(expMs).toISOString().slice(0, 10) : null,
    machine,
    grace_days: OFFLINE_GRACE_DAYS,
    server_time: now,
  };
  res.sig = signResponse(res);
  return { status: 200, ok: true, response: res };
}

function check(body) { return activate(body); }

/* ── replication between the two servers ──────────────────────────────── */
function syncPush(rec) {
  if (!PEER_URL || !PEER_TOKEN) return;
  const payload = JSON.stringify({
    token: PEER_TOKEN,
    record: {
      key: rec.key, name: rec.name, plan: rec.plan, parts: rec.parts,
      machine: rec.machine, first: rec.first, last: rec.last, checks: rec.checks || 1,
    },
  });
  try {
    const u = new URL(PEER_URL.replace(/\/+$/, '') + '/sync');
    const mod = u.protocol === 'https:' ? require('https') : require('http');
    const req = mod.request({
      hostname: u.hostname, port: u.port || (u.protocol === 'https:' ? 443 : 80),
      path: u.pathname, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
      timeout: 8000,
    }, (res) => { res.resume(); });
    req.on('error', () => {});
    req.on('timeout', () => req.destroy());
    req.end(payload);
  } catch (e) { /* never block the activation because of the mirror */ }
}

function syncReceive(body) {
  if (String(body.token || '') !== ADMIN_TOKEN) return { status: 401, ok: false, error: 'bad token' };
  const r = body.record || {};
  const key = clean(r.key);
  if (!key) return { status: 400, ok: false, error: 'no key' };
  const cur = db.licenses[key];
  db.licenses[key] = {
    key,
    name: r.name || (cur && cur.name) || '',
    plan: r.plan || (cur && cur.plan) || '12',
    parts: r.parts || (cur && cur.parts) || {},
    machine: r.machine || (cur && cur.machine) || '',
    first: r.first || (cur && cur.first) || Date.now(),
    last: Math.max(r.last || 0, (cur && cur.last) || 0),
    checks: Math.max(r.checks || 0, (cur && cur.checks) || 0),
  };
  save();
  return { status: 200, ok: true, synced: key };
}

function adminList(token) {
  if (token !== ADMIN_TOKEN) return { status: 401, ok: false, error: 'bad token' };
  const items = Object.values(db.licenses).map((r) => ({
    key: r.key, name: r.name, plan: PLANS[r.plan] ? PLANS[r.plan].label : r.plan,
    first: new Date(r.first).toISOString().slice(0, 16).replace('T', ' '),
    last: new Date(r.last).toISOString().slice(0, 16).replace('T', ' '),
    checks: r.checks, machine: r.machine,
  }));
  return { status: 200, ok: true, count: items.length, items };
}

function adminRelease(token, key) {
  if (token !== ADMIN_TOKEN) return { status: 401, ok: false, error: 'bad token' };
  const k = clean(key);
  if (!db.licenses[k]) return { status: 404, ok: false, error: 'not found' };
  delete db.licenses[k];
  log({ act: 'release', key: k });
  save();
  return { status: 200, ok: true, released: k };
}

function adminPlan(token, key, plan) {
  if (token !== ADMIN_TOKEN) return { status: 401, ok: false, error: 'bad token' };
  if (!PLANS[plan]) return { status: 400, ok: false, error: 'bad plan' };
  const k = clean(key);
  const rec = db.licenses[k];
  if (!rec) return { status: 404, ok: false, error: 'not found' };
  rec.plan = plan;
  rec.first = Date.now();     // the new period starts now
  log({ act: 'plan', key: k, plan });
  save();
  return { status: 200, ok: true, key: k, plan };
}

/* ── HTTP plumbing ───────────────────────────────────────────────────── */
function route(method, urlPath, body, query, ip) {
  const p = (urlPath || '').replace(/\/+$/, '');
  if (p.endsWith('/ping')) return { status: 200, ok: true, service: 'hdm-activate', time: Date.now() };

  if (method === 'GET' && p.endsWith('/admin/list')) return adminList(query.token);
  if (method === 'POST' && p.endsWith('/admin/release'))
    return adminRelease((body && body.token) || query.token, body && body.key);
  if (method === 'POST' && p.endsWith('/admin/plan'))
    return adminPlan((body && body.token) || query.token, body && body.key, body && body.plan);

  if (method === 'POST' && p.endsWith('/sync')) return syncReceive(body || {});

  if (method === 'POST' && (p.endsWith('/activate') || p.endsWith('/check'))) {
    const b = Object.assign({}, body, { ip });
    const r = activate(b);
    return r.status === 200 ? r.response : r;
  }
  return { status: 404, ok: false, error: 'not found' };
}

function jsonBody(req) {
  // when mounted inside an Express app, express.json() already parsed the body
  if (req.body && typeof req.body === 'object' && Object.keys(req.body).length) {
    return Promise.resolve(req.body);
  }
  return readJson(req);
}

function readJson(req) {
  return new Promise((resolve) => {
    let raw = '';
    req.on('data', (c) => { raw += c; if (raw.length > 1e6) req.destroy(); });
    req.on('end', () => {
      try { resolve(raw ? JSON.parse(raw) : {}); } catch (e) { resolve({}); }
    });
  });
}

function splitUrl(u) {
  const i = String(u || '/').indexOf('?');
  if (i < 0) return [String(u || '/'), {}];
  const q = {};
  new URLSearchParams(String(u).slice(i + 1)).forEach((v, k) => { q[k] = v; });
  return [String(u).slice(0, i), q];
}

/* Express router (use inside the hamidesigns site) */
let _router = null;

function makeRouter() {
  const express = require('express');          // only needed when mounted
  const r = express.Router();
  const handler = (req, res) => {
    const [p0, q] = splitUrl(req.originalUrl || req.url);
    const p = p0;
    if (req.method === 'GET' && p.indexOf('/files/') !== -1) {
      if (!serveFile(res, p)) { res.status(404).end('not found'); }
      return;
    }
    Promise.resolve(req.method === 'POST' ? jsonBody(req) : {})
      .then((body) => route(req.method, p, body, q, req.ip))
      .then((out) => {
        const code = out && out.status && out.status !== 200 ? out.status : 200;
        res.status(code);
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify(out));
      })
      .catch(() => { try { res.status(500).end('{"ok":false}'); } catch (e) {} });
  };
  r.all('*', handler);
  r.get('/', handler);
  return r;
}


/* Standalone server */
function standalone(port) {
  const http = require('http');
  http.createServer((req, res) => {
    const [p, q] = splitUrl(req.url);
    if (req.method === 'GET' && p.indexOf('/files/') !== -1) {
      if (!serveFile(res, p)) { res.status(404).end('not found'); }
      return;
    }
    Promise.resolve(req.method === 'POST' ? jsonBody(req) : {})
      .then((body) => route(req.method, p, body, q, req.socket.remoteAddress))
      .then((out) => {
        const code = out && out.status && out.status !== 200 ? out.status : 200;
        res.writeHead(code, { 'Content-Type': 'application/json',
                              'Access-Control-Allow-Origin': '*',
                              'Access-Control-Allow-Headers': 'Content-Type',
                              'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' });
        res.end(JSON.stringify(out));
      });
  }).listen(port || Number(process.env.PORT) || 17432, '0.0.0.0', () => {
    console.log('HDM activation service on port', port || process.env.PORT || 17432);
    console.log('database:', DB_FILE);
  });
}

module.exports = {
  activate, verifyKey, adminList, adminRelease, adminPlan, standalone,
};

/* `router` is created on first use, so the standalone mode needs no express */
Object.defineProperty(module.exports, 'router', {
  configurable: true,
  get() { if (!_router) _router = makeRouter(); return _router; },
});

if (require.main === module) standalone();
