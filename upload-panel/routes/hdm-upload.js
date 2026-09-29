/**
 * HDM file-upload panel (admin only)
 * Mount:  app.use('/hdm-panel', require('./routes/hdm-upload'));
 *
 * Uploads a file to the Finland server (this machine) or forwards it to the
 * Iran server over SSH. Destinations are a fixed whitelist — an uploaded file
 * can never leave those folders, and the file name is sanitised.
 */
'use strict';

const express = require('express');
const router = express.Router();
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const os = require('os');
const crypto = require('crypto');
const { execFile } = require('child_process');
const authMiddleware = require('../middleware/auth');

const SITE = 'https://hamidesigns.shop';
const IR_HOST = 'root@79.175.149.239';
const IR_KEY = '/root/.ssh/hamidesigns_ed25519_v2';   // Finland -> Iran
const MAX_MB = 400;

/* ── destination whitelist ─────────────────────────────────────────── */
const DESTS = [
  { id: 'hdm', label: 'HDM Downloads — hamidesigns.shop/hdm/files/ …',
    fi: '/opt/hamidesigns/public/store/hdm/files',
    ir: '/opt/hdm-uploads/hdm',
    url: SITE + '/hdm/files/' },
  { id: 'apps', label: 'Scorpion Apps — hamidesigns.shop/apps/files/ …',
    fi: '/opt/hamidesigns/public/store/apps/files',
    ir: '/opt/hdm-uploads/apps',
    url: SITE + '/apps/files/' },
  { id: 'uploads', label: 'Images / APK — hamidesigns.shop/uploads/ …',
    fi: '/opt/hamidesigns/uploads',
    ir: '/opt/hdm-uploads/uploads',
    url: SITE + '/uploads/' },
];
const IR_FILES_URL = 'https://hunter.smarthami63.shop/files/';

const destById = (id) => DESTS.find((d) => d.id === String(id || ''));

function safeName(n) {
  let s = path.basename(String(n || '').trim()).replace(/\\/g, '/');
  s = s.split('/').pop();
  s = s.replace(/[^\w.\-()+ ]/g, '_').replace(/\s+/g, ' ').trim();
  s = s.replace(/^\.+/, '');
  return s.slice(0, 140) || ('file-' + Date.now());
}

const upload = multer({
  dest: os.tmpdir(),
  limits: { fileSize: MAX_MB * 1024 * 1024, files: 1 },
});

/* ── optional fallback login (panel password) ──────────────────────── */
const loginAttempts = new Map();
router.post('/login', (req, res) => {
  const ip = req.ip || '?';
  const tries = loginAttempts.get(ip) || { n: 0, until: 0 };
  if (tries.until > Date.now() && tries.n >= 8) {
    return res.status(429).json({ error: 'تلاش زیاد؛ چند دقیقه دیگر دوباره امتحان کنید.' });
  }
  const pass = String((req.body && req.body.password) || '');
  const want = process.env.HDM_PANEL_PASS || '';
  const jwt = require('jsonwebtoken');
  if (want && pass.length && pass === want) {
    loginAttempts.delete(ip);
    const token = jwt.sign(
      { id: 0, username: 'hdm-panel', role: 'admin', name_fa: 'پنل آپلود HDM' },
      process.env.JWT_SECRET, { expiresIn: '2d' });
    return res.json({ token, admin: { username: 'hdm-panel', name_fa: 'پنل آپلود HDM' } });
  }
  tries.n += 1;
  if (tries.n >= 8) tries.until = Date.now() + 10 * 60 * 1000;
  loginAttempts.set(ip, tries);
  return res.status(401).json({ error: 'نام کاربری یا رمز اشتباه است.' });
});

/* ── list files ────────────────────────────────────────────────────── */
router.get('/files', authMiddleware, (req, res) => {
  const d = destById(req.query.dest);
  const target = String(req.query.target || 'fi');
  if (!d) return res.status(400).json({ error: 'مقصد نامعتبر است.' });

  const listLocal = (dir, urlBase) => {
    try {
      if (!fs.existsSync(dir)) return [];
      return fs.readdirSync(dir)
        .filter((f) => fs.statSync(path.join(dir, f)).isFile())
        .map((f) => {
          const st = fs.statSync(path.join(dir, f));
          return { name: f, size: st.size, mtime: st.mtime.toISOString().slice(0, 16).replace('T', ' '),
                   url: urlBase + encodeURIComponent(f) };
        })
        .sort((a, b) => (b.mtime || '').localeCompare(a.mtime || ''));
    } catch (e) {
      return [];
    }
  };

  if (target === 'fi') return res.json({ ok: true, items: listLocal(d.fi, d.url) });

  execFile('ssh', ['-i', IR_KEY, '-o', 'StrictHostKeyChecking=accept-new',
    '-o', 'ConnectTimeout=25', '-p', '22', IR_HOST,
    `ls -1 --time-style=+%Y-%m-%dT%H:%M -l ${d.ir} 2>/dev/null | awk '{print $6"|"$7"|"$5}'`],
    { timeout: 40000 }, (err, stdout) => {
      if (err) return res.json({ ok: true, items: [], note: 'دسترسی به سرور ایران برقرار نشد.' });
      const items = String(stdout).trim().split('\n').filter(Boolean).map((line) => {
        const [mtime, name, size] = line.split('|');
        return { name, size: Number(size) || 0, mtime: (mtime || '').replace('T', ' '),
                 url: IR_FILES_URL + 'hdm/' + path.basename(d.ir) + '/' + encodeURIComponent(name || '') };
      }).filter((x) => x.name);
      res.json({ ok: true, items });
    });
});

/* ── upload ────────────────────────────────────────────────────────── */
router.post('/upload', authMiddleware, upload.single('file'), (req, res) => {
  const d = destById(req.body && req.body.dest);
  const target = String((req.body && req.body.target) || 'fi');
  if (!d) return res.status(400).json({ error: 'مقصد نامعتبر است.' });
  if (!req.file) return res.status(400).json({ error: 'فایلی انتخاب نشده است.' });

  const name = safeName((req.body && req.body.name) || req.file.originalname);
  const tmp = req.file.path;
  const sha = crypto.createHash('sha256').update(fs.readFileSync(tmp)).digest('hex');
  const size = req.file.size;

  const finish = (ok, extra) => {
    try { fs.unlinkSync(tmp); } catch (e) {}
    res.json(Object.assign({ ok, name, size, sha256: sha }, extra || {}));
  };

  if (target === 'fi') {
    try {
      fs.mkdirSync(d.fi, { recursive: true });
      fs.renameSync(tmp, path.join(d.fi, name));
      if (process.env.HDM_PEER_URL) { /* nothing to sync for files */ }
      return finish(true, { where: 'finland', url: d.url + encodeURIComponent(name),
                            path: path.join(d.fi, name) });
    } catch (e) {
      return finish(false, { error: 'خطا در ذخیره روی سرور فنلاند: ' + e.message });
    }
  }

  // Iran: copy over SSH (Finland -> Iran is the only open direction)
  const mkdir = ['-i', IR_KEY, '-o', 'StrictHostKeyChecking=accept-new',
    '-o', 'ConnectTimeout=25', '-p', '22', IR_HOST, `mkdir -p ${d.ir}`];
  execFile('ssh', mkdir, { timeout: 40000 }, (err) => {
    if (err) return finish(false, { error: 'ارتباط با سرور ایران برقرار نشد: ' + err.message });
    execFile('scp', ['-i', IR_KEY, '-o', 'StrictHostKeyChecking=accept-new',
      '-o', 'ConnectTimeout=25', '-P', '22', tmp, `${IR_HOST}:${d.ir}/${name}`],
      { timeout: 300000 }, (err2) => {
        if (err2) return finish(false, { error: 'خطا در انتقال به سرور ایران: ' + err2.message });
        finish(true, { where: 'iran', path: `${d.ir}/${name}`,
                       url: IR_FILES_URL + path.basename(d.ir) + '/' + encodeURIComponent(name) });
      });
  });
});

/* ── delete ────────────────────────────────────────────────────────── */
router.post('/delete', authMiddleware, (req, res) => {
  const d = destById(req.body && req.body.dest);
  const target = String((req.body && req.body.target) || 'fi');
  const name = safeName(req.body && req.body.name);
  if (!d || !name) return res.status(400).json({ error: 'درخواست نامعتبر است.' });

  if (target === 'fi') {
    const p = path.join(d.fi, name);
    if (!p.startsWith(d.fi)) return res.status(400).json({ error: 'مسیر مجاز نیست.' });
    try { fs.unlinkSync(p); return res.json({ ok: true }); }
    catch (e) { return res.status(400).json({ error: String(e.message) }); }
  }
  execFile('ssh', ['-i', IR_KEY, '-o', 'StrictHostKeyChecking=accept-new',
    '-o', 'ConnectTimeout=25', '-p', '22', IR_HOST, `rm -f ${d.ir}/${name}`],
    { timeout: 40000 }, (err) => {
      if (err) return res.status(400).json({ error: String(err.message) });
      res.json({ ok: true });
    });
});

/* ── the page itself ───────────────────────────────────────────────── */
const PAGE = `<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>پنل آپلود فایل — HAMI SMART SYSTEMS</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 body{font-family:Tahoma,"Segoe UI",sans-serif;background:#0b1020;color:#eef2ff;
      padding:18px;line-height:1.9;min-height:100vh}
 .wrap{max-width:820px;margin:0 auto}
 header{text-align:center;margin:8px 0 22px}
 .brand{color:#00A86B;font-weight:800;font-size:20px}
 .sub{color:#9fb0d6;font-size:12.5px}
 .card{background:#141b33;border:1px solid #26304f;border-radius:16px;padding:18px;margin-bottom:16px}
 h2{font-size:16px;margin-bottom:10px}
 label{display:block;font-size:13px;color:#9fb0d6;margin:10px 0 4px}
 input,select{width:100%;background:#0f1730;color:#eef2ff;border:1px solid #2b3a63;
      border-radius:10px;padding:10px 12px;font-family:inherit;font-size:14px}
 .seg{display:flex;gap:8px;margin-top:6px}
 .seg label{flex:1;margin:0;text-align:center;background:#0f1730;border:1px solid #2b3a63;
      border-radius:10px;padding:10px;cursor:pointer;font-size:13.5px;color:#cfd9f5}
 .seg input{display:none}
 .seg input:checked + span{color:#00A86B;font-weight:700}
 .seg label:has(input:checked){border-color:#00A86B;box-shadow:0 0 0 1px #00A86B inset}
 .drop{border:2px dashed #2b3a63;border-radius:14px;padding:26px;text-align:center;
       color:#9fb0d6;margin-top:12px;cursor:pointer}
 .drop.hot{border-color:#00A86B;background:rgba(0,168,107,.08);color:#cfe0ff}
 button{width:100%;background:#00A86B;color:#04140c;border:0;border-radius:12px;padding:13px;
        font-weight:800;font-size:15px;cursor:pointer;font-family:inherit;margin-top:12px}
 button.ghost{background:#1e2942;color:#cfe0ff;border:1px solid #37466b;font-weight:600}
 button.sm{width:auto;padding:6px 12px;font-size:12.5px;margin:0}
 .bar{height:10px;background:#0f1730;border-radius:8px;overflow:hidden;margin-top:12px;display:none}
 .bar > i{display:block;height:100%;width:0;background:linear-gradient(90deg,#00A86B,#22D3EE)}
 .msg{margin-top:12px;font-size:13.5px;white-space:pre-wrap;word-break:break-all}
 .ok{color:#00A86B}.err{color:#ff6b6b}
 table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px}
 th,td{text-align:right;padding:7px 6px;border-bottom:1px solid #222c47;vertical-align:middle}
 th{color:#9fb0d6;font-weight:600}
 td a{color:#8fd7ff;text-decoration:none}
 .row{display:flex;gap:8px;align-items:center;justify-content:space-between}
 .hide{display:none}
 footer{text-align:center;color:#6d7fa8;font-size:11.5px;padding:18px 0}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">HAMI SMART SYSTEMS</div>
    <div class="sub">پنل آپلود فایل — ارسال به سرور فنلاند یا ایران</div>
  </header>

  <div class="card" id="loginCard">
    <h2>ورود</h2>
    <label>نام کاربری</label>
    <input id="user" autocomplete="username" placeholder="admin">
    <label>رمز عبور</label>
    <input id="pass" type="password" autocomplete="current-password">
    <button onclick="doLogin()">ورود</button>
    <div class="msg" id="loginMsg"></div>
  </div>

  <div class="card hide" id="mainCard">
    <div class="row">
      <h2>ارسال فایل</h2>
      <button class="sm ghost" onclick="logout()">خروج</button>
    </div>

    <label>سرور مقصد</label>
    <div class="seg">
      <label><input type="radio" name="target" value="fi" checked><span>🇫🇮 فنلاند (سایت اصلی)</span></label>
      <label><input type="radio" name="target" value="ir"><span>🇮🇷 ایران</span></label>
    </div>

    <label>پوشهٔ مقصد</label>
    <select id="dest">
      <option value="hdm">HDM Downloads — /hdm/files/</option>
      <option value="apps">Scorpion Apps — /apps/files/</option>
      <option value="uploads">تصاویر / APK — /uploads/</option>
    </select>

    <label>نام فایل روی سرور (اختیاری)</label>
    <input id="fname" placeholder="مثال: HDM-1.0.0-Setup.exe">

    <div class="drop" id="drop">اینجا کلیک کنید یا فایل را رها کنید<br><small>حداکثر ۴۰۰ مگابایت</small></div>
    <input type="file" id="picker" class="hide">
    <div class="bar" id="bar"><i></i></div>
    <div class="msg" id="msg"></div>
  </div>

  <div class="card hide" id="listCard">
    <div class="row"><h2>فایل‌های موجود در مقصد</h2>
      <button class="sm ghost" onclick="loadList()">بروزرسانی</button></div>
    <table id="tbl"><thead><tr><th>نام فایل</th><th>حجم</th><th>زمان</th><th></th></tr></thead>
      <tbody></tbody></table>
  </div>

  <footer>HAMI SMART SYSTEMS — فقط برای مدیر</footer>
</div>

<script>
var TOKEN = sessionStorage.getItem('hdm_token') || '';
var API = location.pathname.replace(/\\/+$/, '');
var BASES = ['/api/auth/login', '/hdm-panel/login'];

function $(id){ return document.getElementById(id); }
function target(){ return document.querySelector('input[name=target]:checked').value; }
function size(n){ n=+n||0; var u=['B','KB','MB','GB'],i=0; while(n>=1024&&i<3){n/=1024;i++;}
  return (i?n.toFixed(1):n)+' '+u[i]; }

function tryLogin(url, user, pass, cb){
  fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({username:user, password:pass})})
    .then(r => r.ok ? r.json() : Promise.reject(new Error('bad')))
    .then(d => cb(null, d))
    .catch(e => cb(e));
}

function doLogin(){
  var user = $('user').value.trim(), pass = $('pass').value;
  if(!pass){ $('loginMsg').className='msg err'; $('loginMsg').textContent='رمز عبور را وارد کنید.'; return; }
  $('loginMsg').className='msg'; $('loginMsg').textContent='در حال ورود…';
  tryLogin(BASES[0], user, pass, function(e1, d1){
    if(!e1 && d1 && d1.token){ success(d1.token); return; }
    tryLogin(BASES[1], user, pass, function(e2, d2){
      if(!e2 && d2 && d2.token){ success(d2.token); return; }
      $('loginMsg').className='msg err';
      $('loginMsg').textContent='ورود ناموفق — نام کاربری/رمز را بررسی کنید (همان رمز پنل مدیریت فروشگاه).';
    });
  });
}

function success(token){
  TOKEN = token; sessionStorage.setItem('hdm_token', token);
  $('loginCard').classList.add('hide');
  $('mainCard').classList.remove('hide');
  $('listCard').classList.remove('hide');
  loadList();
}

function logout(){ sessionStorage.removeItem('hdm_token'); location.reload(); }

function auth(){ return {'Authorization':'Bearer '+TOKEN}; }

$('drop').onclick = function(){ $('picker').click(); };
$('drop').ondragover = function(e){ e.preventDefault(); this.classList.add('hot'); };
$('drop').ondragleave = function(){ this.classList.remove('hot'); };
$('drop').ondrop = function(e){ e.preventDefault(); this.classList.remove('hot');
  if(e.dataTransfer.files[0]) send(e.dataTransfer.files[0]); };
$('picker').onchange = function(){ if(this.files[0]){ send(this.files[0]); } };
document.querySelectorAll('input[name=target]').forEach(function(r){
  r.onchange = loadList; });
$('dest').onchange = loadList;

function send(file){
  if(!$('fname').value) $('fname').value = file.name;
  var fd = new FormData();
  fd.append('file', file);
  fd.append('dest', $('dest').value);
  fd.append('target', target());
  fd.append('name', $('fname').value);
  $('bar').style.display='block'; $('bar').firstElementChild.style.width='0%';
  $('msg').className='msg'; $('msg').textContent='در حال ارسال…';
  var xhr = new XMLHttpRequest();
  xhr.open('POST', API + '/upload');
  xhr.setRequestHeader('Authorization', 'Bearer ' + TOKEN);
  xhr.upload.onprogress = function(e){
    if(e.lengthComputable){ $('bar').firstElementChild.style.width =
      Math.round(e.loaded/e.total*100)+'%'; } };
  xhr.onload = function(){
    var d; try{ d = JSON.parse(xhr.responseText); }catch(e){ d = {}; }
    if(xhr.status === 200 && d.ok){
      $('msg').className='msg ok';
      $('msg').innerHTML = '✅ ارسال شد (' + (d.where==='iran'?'سرور ایران':'سرور فنلاند') + ')\\n' +
        'لینک: ' + (d.url || '-') + '\\nSHA-256: ' + d.sha256;
      $('bar').firstElementChild.style.width='100%';
      loadList();
    } else {
      $('msg').className='msg err';
      $('msg').textContent = '❌ ' + (d.error || ('خطا ' + xhr.status));
    }
  };
  xhr.onerror = function(){ $('msg').className='msg err'; $('msg').textContent='❌ خطای شبکه'; };
  xhr.send(fd);
}

function loadList(){
  if(!TOKEN) return;
  fetch(API + '/files?dest=' + $('dest').value + '&target=' + target(), {headers: auth()})
    .then(function(r){ return r.status===401 ? Promise.reject(new Error('401')) : r.json(); })
    .catch(function(){ return {items:[]}; })
    .then(function(d){
      var tb = document.querySelector('#tbl tbody'); tb.innerHTML = '';
      (d.items||[]).forEach(function(f){
        var tr = document.createElement('tr');
        tr.innerHTML = '<td><a href="'+f.url+'" target="_blank">'+f.name+'</a></td>' +
          '<td>'+size(f.size)+'</td><td>'+(f.mtime||'')+'</td>' +
          '<td><button class="sm ghost" data-n="'+f.name+'">حذف</button></td>';
        tr.querySelector('button').onclick = function(){
          if(!confirm('حذف شود؟ '+f.name)) return;
          fetch(API + '/delete', {method:'POST', headers: Object.assign({'Content-Type':'application/json'}, auth()),
                body: JSON.stringify({dest:$('dest').value, target:target(), name:f.name})})
            .then(function(){ loadList(); });
        };
        tb.appendChild(tr);
      });
      if(!(d.items||[]).length){ tb.innerHTML = '<tr><td colspan="4">فایلی نیست' +
        (d.note ? ' — ' + d.note : '') + '</td></tr>'; }
    });
}

if(TOKEN){ success(TOKEN); }
</script>
</body>
</html>`;

router.get('/', (req, res) => {
  res.set('Cache-Control', 'no-store');
  res.type('html').send(PAGE);
});

module.exports = router;
