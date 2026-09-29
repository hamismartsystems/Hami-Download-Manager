#!/usr/bin/env node
/**
 * HDM / Scorpion config watchdog — HAMI SMART SYSTEMS
 * Runs on the Finland server every 5 minutes.
 *
 * It checks the exact things that have broken configs in the past:
 *   1. the panel is reachable
 *   2. the x-ui service is running
 *   3. every inbound is enabled
 *   4. shareAddr is the Iran relay 79.175.149.239
 *      (the Finland IP is filtered inside Iran; clients must use the relay)
 *   5. the public subscription really returns a link to that address:443
 *   6. local xray answers, and the Finland→Iran relay tunnel is up
 *   7. the website answers
 *
 * Any problem — and every automatic repair — is logged and sent to the owner
 * on Telegram immediately.
 */
'use strict';

const fs = require('fs');
const net = require('net');
const { execFile } = require('child_process');

const HOME = '/opt/hami-watchdog';
const LOG = HOME + '/watch.log';
const STATUS = HOME + '/status.json';
const BACKUPS = HOME + '/backups';

/* ── config from watch.env ──────────────────────────────────────────── */
const ENV = {};
try {
  String(fs.readFileSync(HOME + '/watch.env', 'utf8')).split('\n').forEach((line) => {
    const i = line.indexOf('=');
    if (i > 0 && !line.trim().startsWith('#')) {
      ENV[line.slice(0, i).trim()] = line.slice(i + 1).trim().replace(/^["']|["']$/g, '');
    }
  });
} catch (e) { /* first run */ }

const BASE = ENV.XUI_BASE || 'https://panel.hamidesigns.shop/wqyekvv4pig5qsv/panel/api';
const TOKEN = ENV.XUI_TOKEN || '';
const WANT = ENV.WANT_ADDR || '79.175.149.239';
const SUB_BASE = ENV.SUB_BASE || '';
const TG_TOKEN = ENV.TG_TOKEN || '';
const TG_CHAT = ENV.TG_CHAT || '';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36';

const problems = [];
const fixes = [];
const info = {};

function log(line) {
  const s = new Date().toISOString().replace('T', ' ').slice(0, 19) + '  ' + line;
  try {
    fs.appendFileSync(LOG, s + '\n');
    if (fs.statSync(LOG).size > 1024 * 1024) {          // keep the log small
      const keep = fs.readFileSync(LOG, 'utf8').split('\n').slice(-300);
      fs.writeFileSync(LOG, keep.join('\n'));
    }
  } catch (e) {}
  console.log(s);
}

/* ── helpers ────────────────────────────────────────────────────────── */
async function api(p, method, body) {
  const r = await fetch(BASE + p, {
    method: method || 'GET',
    headers: { Authorization: 'Bearer ' + TOKEN, 'User-Agent': UA,
               'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const t = await r.text();
  try { return JSON.parse(t); } catch (e) { return { success: false, msg: t.slice(0, 120) }; }
}

function tcpOpen(host, port, ms) {
  return new Promise((resolve) => {
    const s = net.connect({ host, port });
    const done = (v) => { try { s.destroy(); } catch (e) {} resolve(v); };
    s.setTimeout(ms || 6000);
    s.on('connect', () => done(true));
    s.on('timeout', () => done(false));
    s.on('error', () => done(false));
  });
}

function sh(cmd, args) {
  return new Promise((resolve) => {
    execFile(cmd, args || [], { timeout: 20000 }, (err, stdout) => resolve(String(stdout || '').trim()));
  });
}

async function telegram(text) {
  if (!TG_TOKEN || !TG_CHAT) { log('telegram: not configured — alert only in the log'); return false; }
  try {
    const r = await fetch('https://api.telegram.org/bot' + TG_TOKEN + '/sendMessage', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: TG_CHAT, text: text, disable_web_page_preview: true }),
    });
    const ok = r.ok;
    log('telegram alert: ' + (ok ? 'sent' : 'failed ' + r.status));
    return ok;
  } catch (e) { log('telegram error: ' + e.message); return false; }
}

function settingsOf(o) {
  if (!o.settings) return {};
  if (typeof o.settings === 'object') return o.settings;
  try { return JSON.parse(o.settings); } catch (e) { return {}; }
}

/* ── the check ──────────────────────────────────────────────────────── */
async function run() {
  fs.mkdirSync(BACKUPS, { recursive: true });

  // 1) panel API
  const list = await api('/inbounds/list');
  if (!list || !list.success) {
    problems.push('پنل در دسترس نیست: ' + String((list && list.msg) || 'بدون پاسخ'));
  }
  const inbounds = (list && list.obj) || [];
  info.inbounds = inbounds.length;

  for (const o of inbounds) {
    const tag = '#' + o.id + ' ' + (o.remark || '') + ' (port ' + o.port + ')';

    // 2) enabled?
    if (!o.enable) {
      const body = Object.assign({}, o);
      delete body.clientStats;
      body.enable = true;
      const r = await api('/inbounds/update/' + o.id, 'POST', body);
      if (r && r.success) { fixes.push('اینباند دوباره فعال شد: ' + tag); }
      else { problems.push('اینباند غیرفعال است و نتوانستم فعالش کنم: ' + tag); }
    }

    // 3) shareAddr — the classic breakage
    const cur = o.shareAddr || '';
    const strat = o.shareAddrStrategy || '';
    info['shareAddr' + o.id] = cur || '(خالی)';
    if (cur !== WANT || strat !== 'custom') {
      try {
        fs.writeFileSync(BACKUPS + '/inbound-' + o.id + '-' + Date.now() + '.json',
          JSON.stringify(o, null, 2));
      } catch (e) {}

      const body = Object.assign({}, o);
      delete body.clientStats;
      body.shareAddrStrategy = 'custom';
      body.shareAddr = WANT;
      let r = await api('/inbounds/update/' + o.id, 'POST', body);
      if (!r || !r.success) {           // some builds need settings as a string
        const b2 = Object.assign({}, body, { settings: JSON.stringify(body.settings || {}) });
        r = await api('/inbounds/update/' + o.id, 'POST', b2);
      }
      const after = await api('/inbounds/list');
      const o2 = ((after && after.obj) || []).find((x) => String(x.id) === String(o.id));
      if (o2 && (o2.shareAddr || '') === WANT) {
        fixes.push('آدرسِ اشتراکِ ' + tag + ' اصلاح شد (' + (cur || 'خالی') + ' ⇒ ' + WANT + ')');
        info['shareAddr' + o.id] = WANT;
      } else {
        problems.push('آدرسِ اشتراکِ ' + tag + ' اشتباه است («' + (cur || 'خالی') +
          '») و اصلاحِ خودکار ناموفق بود — باید دستی درست شود');
      }
    }
  }

  // 4) x-ui service
  const xui = await sh('systemctl', ['is-active', 'x-ui']);
  info.xui = xui;
  if (xui !== 'active') problems.push('سرویس x-ui فعال نیست: ' + xui);

  // 5) xray + relay. Finland cannot open the Iran public IP, so do not
  //    probe WANT:443 from here — that timeout is a false alarm.
  const local = await tcpOpen('127.0.0.1', 443, 3000);
  info.port443 = local;
  if (!local) problems.push('xray روی ۱۲۷.۰.۰.۱:۴۴۳ پاسخ نمی‌دهد');
  const tunnel = await sh('systemctl', ['is-active', 'fi-ir-vpn-tunnel']);
  info.relay = tunnel;
  if (tunnel !== 'active') problems.push('تونل رلهٔ ایران قطع است: ' + tunnel);

  // 6) subscription content
  if (SUB_BASE) {
    try {
      const fresh = await api('/inbounds/list');
      const o1 = ((fresh && fresh.obj) || [])[0];
      const st = settingsOf(o1 || {});
      const clients = st.clients || [];
      const subId = (clients[0] || {}).subId || (o1 && o1.subId);
      if (subId) {
        const r = await fetch(SUB_BASE + subId, { headers: { 'User-Agent': UA } });
        const txt = (await r.text()).trim();
        let decoded = txt;
        try { decoded = Buffer.from(txt, 'base64').toString('utf8'); } catch (e) {}
        info.subStatus = r.status;
        info.subSample = (decoded.match(/vless:\/\/[^\s"']{0,60}/) || [''])[0].slice(0, 90);
        if (!decoded.includes('@' + WANT + ':' + (o1 ? o1.port : 443))) {
          problems.push('لینکِ اشتراک به آدرس درست اشاره نمی‌کند (نمونه: ' +
            (info.subSample || 'خالی').slice(0, 60) + ')');
        }
      }
    } catch (e) {
      problems.push('بررسی لینک اشتراک ناموفق: ' + e.message);
    }
  }

  // 7) website
  try {
    const r = await fetch('https://hamidesigns.shop/', { headers: { 'User-Agent': UA } });
    info.site = r.status;
    if (r.status !== 200) problems.push('سایت پاسخ نمی‌دهد: HTTP ' + r.status);
  } catch (e) { problems.push('سایت در دسترس نیست: ' + e.message); }

  /* ── report ───────────────────────────────────────────────────────── */
  const ok = problems.length === 0;
  const st = { ok, checked_at: new Date().toISOString(), problems, fixes, info };
  fs.writeFileSync(STATUS, JSON.stringify(st, null, 2));

  if (ok && fixes.length === 0) { log('OK  (inbounds=' + info.inbounds + ')'); return st; }

  let msg = (ok ? '🛠 تعمیر خودکار انجام شد' : '🚨 هشدار کانفیگ') + '\n';
  msg += 'زمان: ' + new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC\n\n';
  if (fixes.length) msg += '✅ اصلاح شده:\n' + fixes.map((f) => ' • ' + f).join('\n') + '\n\n';
  if (problems.length) msg += '❌ مانده:\n' + problems.map((f) => ' • ' + f).join('\n');
  log(msg.replace(/\n/g, ' | '));
  await telegram(msg);
  return st;
}

run().then((st) => { process.exit(st.ok ? 0 : 1); })
  .catch((e) => { log('CRASH: ' + e.message); process.exit(2); });
