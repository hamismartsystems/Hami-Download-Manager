#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# فعال‌ساز مستقل HDM - به هیچ فایل قدیمی وابسته نیست
# فقط همین یک فایل را روی ویندوز اجرا کن: python activate-standalone.py
import base64, hashlib, hmac, json, os, platform, re, subprocess, sys, time
from pathlib import Path

SECRET = b"HDM-2026-LICENSE-SECRET-HAMI-SMART-SYSTEMS"
SALT = b"HDM-SIGNED-BLOB-V2"
APP_DIR = Path(os.environ.get("HDM_HOME") or Path.home() / ".hami-download-manager")
LICENSE_FILE = APP_DIR / "license.dat"
TRIAL_FILE = APP_DIR / "trial.dat"

PLANS = {
    "06": {"days": 180, "label": "6 Months"},
    "12": {"days": 365, "label": "1 Year"},
    "99": {"days": None, "label": "Lifetime"},
}

NAME = "Hamid"
KEY = "HG-E5C4-F933-A178-9919-765E"

def _mac(payload: str) -> str:
    return hmac.new(SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:6].upper()

def _norm(name: str) -> str:
    return " ".join((name or "").strip().split()).lower()

def parse(key: str):
    k = re.sub(r"[^0-9A-Z]", "", (key or "").upper())
    if not k.startswith("HG") or len(k) != 22:
        return False, "", "", ""
    body, tail, end = k[2:14], k[14:18], k[18:22]
    return True, tail[:2], tail[2:4] + end, body

def verify(key: str, name: str):
    ok, plan, sig, body = parse(key)
    if not ok or plan not in PLANS:
        return None, f"فرمت کلید اشتباه است. stripped={re.sub(r'[^0-9A-Z]','',(key or '').upper())} len={len(re.sub(r'[^0-9A-Z]','',(key or '').upper()))} plan={plan}"
    n = _norm(name)
    if hashlib.sha1(n.encode("utf-8")).hexdigest()[:12].upper() != body:
        return None, "این کلید برای این نام نیست"
    if _mac(n + "|" + plan) != sig:
        return None, "کلید معتبر نیست"
    return plan, "ok"

def _sign(payload: str) -> str:
    return hmac.new(SECRET, SALT + payload.encode("utf-8"), hashlib.sha256).hexdigest()

def _write_signed(path: Path, obj):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    payload = base64.b64encode(json.dumps(obj, sort_keys=True).encode("utf-8")).decode()
    blob = payload + "." + _sign(payload)
    path.write_text(blob, encoding="utf-8")

def _read_signed(path: Path):
    try:
        payload, sig = path.read_text(encoding="utf-8").strip().rsplit(".", 1)
    except Exception:
        return None
    if not hmac.compare_digest(_sign(payload), sig):
        return None
    try:
        return json.loads(base64.b64decode(payload).decode("utf-8"))
    except Exception:
        return None

def machine_parts():
    parts = {}
    # Windows full fingerprint like HDM does
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                parts["guid"] = winreg.QueryValueEx(k, "MachineGuid")[0]
        except Exception:
            pass
        ps = (
            "$b=Get-CimInstance Win32_BaseBoard;"
            "$c=Get-CimInstance Win32_Processor;"
            "$s=Get-CimInstance Win32_BIOS;"
            "$o=@{board=$b.SerialNumber;cpu=$c.ProcessorId;bios=$s.SerialNumber};"
            "$o | ConvertTo-Json -Compress"
        )
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=25,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout.strip()
            if out.startswith("{"):
                d = json.loads(out)
                for k in ("board", "cpu", "bios"):
                    v = str(d.get(k) or "").strip()
                    v = re.sub(r"\s+", "", v)
                    if v and v.lower() not in ("none", "null", "default string", "to be filled by o.e.m."):
                        parts[k] = v.upper()
        except Exception:
            pass
    # fallback for any OS
    if not parts:
        try:
            if os.path.exists("/etc/machine-id"):
                parts["guid"] = open("/etc/machine-id").read().strip()
        except Exception:
            pass
        parts.setdefault("guid", platform.node())
        parts.setdefault("cpu", platform.processor() or "cpu")
    return {k:v for k,v in parts.items() if v}

def machine_fingerprint():
    p = machine_parts()
    raw = "|".join(f"{k}={p[k]}" for k in sorted(p))
    return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()

print(f"NAME={NAME}")
print(f"KEY={KEY}")
print(f"APP_DIR={APP_DIR}")
# clean old binding
for fn in ["license.dat", "activation.dat"]:
    try:
        (APP_DIR / fn).unlink()
        print(f"Deleted old {fn}")
    except Exception:
        pass

ok, plan, sig, body = parse(KEY)
print(f"PARSE ok={ok} plan={plan} sig={sig} body={body}")
vplan, vmsg = verify(KEY, NAME)
print(f"VERIFY plan={vplan} msg={vmsg}")
if not vplan:
    print("❌ VERIFY FAILED")
    sys.exit(1)

now = int(time.time())
p = PLANS[vplan]
exp = 0 if p["days"] is None else now + p["days"]*86400
hw = machine_parts()
fp = machine_fingerprint()
print(f"Current Machine parts: {hw}")
print(f"Current Machine ID (باید با HDM یکی باشد): {fp}")
rec = {
    "v": 2,
    "name": NAME,
    "key": re.sub(r"[^0-9A-Z]", "", KEY.upper()),
    "plan": vplan,
    "exp": exp,
    "issued": now,
    "hw": hw,
    "fp": fp,
    "last_seen": now,
}
_write_signed(LICENSE_FILE, rec)
print(f"✅ Written {LICENSE_FILE}")
print(f"fp={rec['fp']}")
# read back
d = _read_signed(LICENSE_FILE)
print(f"READBACK ok={bool(d)} name={d.get('name') if d else None} plan={d.get('plan') if d else None}")
print("حالا HDM را کامل ببند و دوباره باز کن - باید Lifetime فعال باشد.")
print("اگر هنوز NOT VALID می‌زند، اسکرین‌شات Machine ID را با fp بالا مقایسه کن - باید یکی باشند.")
