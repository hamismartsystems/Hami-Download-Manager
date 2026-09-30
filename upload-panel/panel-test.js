/* temporary: exercise the upload router on a scratch port, then delete */
require('dotenv').config({ path: '/opt/hamidesigns/.env' });
const express = require('express');
const fs = require('fs');
const path = require('path');
const app = express();
app.use(express.json());
app.use('/hdm-panel', require('./routes/hdm-upload'));

const PORT = Number(process.env.TESTPORT) || 3995;
const base = 'http://127.0.0.1:' + PORT + '/hdm-panel';

const srv = app.listen(PORT, '127.0.0.1', () => { run().then(() => srv.close()); });

async function run() {
  const ok = (label, cond, extra) => console.log((cond ? 'PASS ' : 'FAIL ') + label, extra || '');

  // 1) login with the panel password
  let r = await fetch(base + '/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: process.env.HDM_PANEL_PASS }) });
  let d = await r.json();
  ok('login(panel password)', r.status === 200 && !!d.token);
  const T = d.token || '';

  // 2) wrong password must fail
  r = await fetch(base + '/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: 'nope' }) });
  ok('login(wrong password rejected)', r.status === 401);

  // 3) API without a token must fail
  r = await fetch(base + '/files?dest=hdm&target=fi');
  ok('api without token -> 401', r.status === 401);

  const H = { Authorization: 'Bearer ' + T };

  // 4) upload to Finland
  const form = new FormData();
  form.append('file', new Blob([Buffer.from('hello-hdm-panel\n')], { type: 'text/plain' }), 'panel-test.txt');
  form.append('dest', 'hdm'); form.append('target', 'fi'); form.append('name', 'panel-test.txt');
  r = await fetch(base + '/upload', { method: 'POST', headers: H, body: form });
  d = await r.json();
  ok('upload -> finland', r.status === 200 && d.ok === true, d.url || d.error);
  const p = '/opt/hamidesigns/public/store/hdm/files/panel-test.txt';
  ok('file exists on disk', fs.existsSync(p));

  // 5) list
  r = await fetch(base + '/files?dest=hdm&target=fi', { headers: H });
  d = await r.json();
  ok('list shows the file', (d.items || []).some((x) => x.name === 'panel-test.txt'));

  // 6) upload to Iran
  const form2 = new FormData();
  form2.append('file', new Blob([Buffer.from('iran-test\n')], { type: 'text/plain' }), 'panel-test.txt');
  form2.append('dest', 'hdm'); form2.append('target', 'ir'); form2.append('name', 'panel-test.txt');
  r = await fetch(base + '/upload', { method: 'POST', headers: H, body: form2 });
  d = await r.json();
  ok('upload -> iran', r.status === 200 && d.ok === true, d.error || d.path);

  // 7) delete both
  r = await fetch(base + '/delete', { method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, H),
    body: JSON.stringify({ dest: 'hdm', target: 'fi', name: 'panel-test.txt' }) });
  ok('delete(finland)', r.status === 200 && !fs.existsSync(p));
  r = await fetch(base + '/delete', { method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, H),
    body: JSON.stringify({ dest: 'hdm', target: 'ir', name: 'panel-test.txt' }) });
  d = await r.json();
  ok('delete(iran)', r.status === 200, d.error || '');

  // 8) path traversal must be refused
  const form3 = new FormData();
  form3.append('file', new Blob(['x'], { type: 'text/plain' }), 'x.txt');
  form3.append('dest', 'hdm'); form3.append('target', 'fi');
  form3.append('name', '../../../../etc/passwd');
  r = await fetch(base + '/upload', { method: 'POST', headers: H, body: form3 });
  d = await r.json();
  ok('traversal sanitised', d.ok === true && !String(d.path || '').includes('..'), d.path);
  try { fs.unlinkSync('/opt/hamidesigns/public/store/hdm/files/' + d.name); } catch (e) {}

  process.stdout.write('done\n');
}
