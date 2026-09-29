#!/usr/bin/env bash
# گزارش سریعِ سلامت کانفیگ‌ها — اجرا روی سرور فنلاند
cat /opt/hami-watchdog/status.json 2>/dev/null | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: print('گزارشی موجود نیست'); raise SystemExit(1)
print('زمان بررسی :', d.get('checked_at'))
print('وضعیت      :', '✅ سالم' if d.get('ok') else '❌ مشکل دارد')
i=d.get('info',{})
print('اینباندها  :', i.get('inbounds'), '| x-ui:', i.get('xui'), '| پورت ۴۴۳:', i.get('port443'), '| سایت:', i.get('site'))
print('shareAddr  :', i.get('shareAddr1'))
print('نمونهٔ ساب :', i.get('subSample'))
for f in d.get('fixes',[]): print('  🛠', f)
for p in d.get('problems',[]): print('  ❌', p)
"
echo "--- ۵ خط آخر لاگ ---"; tail -5 /opt/hami-watchdog/watch.log 2>/dev/null
