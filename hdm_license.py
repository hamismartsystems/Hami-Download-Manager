# -*- coding: utf-8 -*-
"""HDM licensing — 7-day trial + hardware-locked, signed licenses.

Design
------
* Key      : HG-xxxx-xxxx-xxxx-xxxx-xxxx  = hash(name) + HMAC(name|plan)
             Generated with gen_license.py (never ship that file).
* License  : stored as a signed blob (HMAC-SHA256) in the user profile, so
             editing it by hand invalidates it immediately.
* Machine  : the license is bound to this computer's hardware (mainboard +
             CPU + BIOS). A Windows re-install keeps those, so re-activation
             on the same machine after re-installing works.
             Copying the license file to another computer does NOT work.
* Clock    : if the system date is moved back, the license stops working.
"""
import base64
import hashlib
import hmac
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

SECRET = b"HDM-2026-LICENSE-SECRET-HAMI-SMART-SYSTEMS"
SALT = b"HDM-SIGNED-BLOB-V2"
TRIAL_DAYS = 7
THROTTLE_BPS = 150 * 1024
# FREE MODE — HDM is now free for everyone (2026-09-29)
FREE_MODE = True
FREE_NAME = "FREE EDITION"

APP_DIR = Path(os.environ.get("HDM_HOME") or Path.home() / ".hami-download-manager")
LICENSE_FILE = APP_DIR / "license.dat"
TRIAL_FILE = APP_DIR / "trial.dat"

PLANS = {
    "06": {"days": 180, "label": "6 Months", "label_fa": "شش‌ماهه"},
    "12": {"days": 365, "label": "1 Year", "label_fa": "یک‌ساله"},
    "99": {"days": None, "label": "Lifetime", "label_fa": "مادام‌العمر"},
}

# ── key generation (server side / gen_license.py) ──────────────────────────
def _mac(payload: str) -> str:
    return hmac.new(SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:6].upper()


def _norm(name: str) -> str:
    return " ".join((name or "").strip().split()).lower()


def mint(name: str, plan: str = "12") -> str:
    n = _norm(name)
    body = hashlib.sha1(n.encode("utf-8")).hexdigest()[:12].upper()
    sig = _mac(n + "|" + plan)
    return f"HG-{body[:4]}-{body[4:8]}-{body[8:12]}-{plan}{sig[:2]}-{sig[2:6]}"


def parse(key: str):
    k = re.sub(r"[^0-9A-Z]", "", (key or "").upper())
    if not k.startswith("HG") or len(k) != 22:
        return False, "", "", ""
    body, tail, end = k[2:14], k[14:18], k[18:22]
    return True, tail[:2], tail[2:4] + end, body


def verify(key: str, name: str):
    ok, plan, sig, body = parse(key)
    if not ok or plan not in PLANS:
        return None, "فرمت کلید اشتباه است. کلید باید HG-XXXX-XXXX-XXXX-XXXX-XXXX باشد."
    n = _norm(name)
    if hashlib.sha1(n.encode("utf-8")).hexdigest()[:12].upper() != body:
        return None, "این کلید برای این نام نیست. نام باید دقیقا همان باشد که صادر شده (Hamid)."
    if _mac(n + "|" + plan) != sig:
        return None, "کلید معتبر نیست."
    return plan, "ok"


# ── machine fingerprint ────────────────────────────────────────────────────
def _win_parts():
    parts = {}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography") as k:
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
                if v and v.lower() not in ("none", "null", "default string",
                                           "to be filled by o.e.m."):
                    parts[k] = v.upper()
    except Exception:
        pass
    return parts


_PARTS_CACHE = None
_PARTS_LOCK = threading.Lock()
_PARTS_READY = threading.Event()
_PARTS_STARTED = False


def _load_parts():
    """Read hardware once. Never call this from a button handler."""
    global _PARTS_CACHE
    parts = {}
    try:
        if sys.platform == "win32":
            parts = _win_parts() or {}
        if not parts:
            if os.path.exists("/etc/machine-id"):
                parts["guid"] = open("/etc/machine-id").read().strip()
            try:
                with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "Serial" in line or "model name" in line:
                            parts.setdefault("cpu", line.split(":", 1)[1].strip())
            except Exception:
                pass
            parts.setdefault("cpu", platform.processor() or "")
            parts.setdefault("guid", platform.node())
        parts = {k: v for k, v in parts.items() if v}
    except Exception:
        parts = {}
    with _PARTS_LOCK:
        if parts:
            _PARTS_CACHE = dict(parts)
    _PARTS_READY.set()


def _kick_parts():
    global _PARTS_STARTED
    with _PARTS_LOCK:
        if _PARTS_CACHE or _PARTS_STARTED:
            return
        _PARTS_STARTED = True
    threading.Thread(target=_load_parts, name="hdm-hw", daemon=True).start()


def machine_parts(wait=False):
    """Hardware identity. The window must never wait on PowerShell.

    wait=True is only for activation, which has to bind the license.
    """
    if _PARTS_CACHE:
        return dict(_PARTS_CACHE)
    _kick_parts()
    if wait:
        _PARTS_READY.wait(25)
    return dict(_PARTS_CACHE or {})


def machine_fingerprint(wait=False):
    p = machine_parts(wait=wait)
    if not p:
        return ""
    raw = "|".join(f"{k}={p[k]}" for k in sorted(p))
    return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()


def _hw_match(stored):
    if FREE_MODE:
        return True
    """Does the current computer match the one the license was made on?

    Mainboard / CPU / BIOS survive a Windows reinstall — matching any of them is
    enough. The Windows install id is only used when nothing else is available.
    """
    if not _PARTS_READY.is_set():
        _kick_parts()
        return True
    cur = dict(_PARTS_CACHE or {})
    if not stored or not cur:
        return False
    eq = lambda k: bool(stored.get(k)) and bool(cur.get(k)) and \
        str(stored[k]).upper() == str(cur[k]).upper()
    strong_both = [k for k in ("board", "cpu", "bios") if stored.get(k) and cur.get(k)]
    if any(eq(k) for k in strong_both):
        return True
    if not strong_both:
        return eq("guid")
    return False


# ── signed storage ─────────────────────────────────────────────────────────
def _sign(payload: str) -> str:
    return hmac.new(SECRET, SALT + payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _write_signed(path: Path, obj):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    payload = base64.b64encode(json.dumps(obj, sort_keys=True).encode("utf-8")).decode()
    blob = payload + "." + _sign(payload)
    try:
        path.write_text(blob, encoding="utf-8")
    except Exception:
        pass


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


# ── trial ──────────────────────────────────────────────────────────────────
def _trial():
    d = _read_signed(TRIAL_FILE)
    now = int(time.time())
    if not d or not isinstance(d.get("first_run"), int):
        d = {"first_run": now}
        _write_signed(TRIAL_FILE, d)
    return d


# ── activation / status ────────────────────────────────────────────────────
def activate(key: str, name: str) -> tuple:
    name = " ".join((name or "").split())
    if not name:
        return False, "نام را وارد کنید. باید دقیقا همان باشد که صادر شده."
    plan, msg = verify(key, name)
    if not plan:
        return False, msg

    now = int(time.time())
    p = PLANS[plan]
    exp = 0 if p["days"] is None else now + p["days"] * 86400
    rec = {
        "v": 2,
        "name": name,
        "key": re.sub(r"[^0-9A-Z]", "", (key or "").upper()),
        "plan": plan,
        "exp": exp,
        "issued": now,
        "hw": machine_parts(wait=True),
        "fp": machine_fingerprint(wait=True),
        "last_seen": now,
    }
    _write_signed(LICENSE_FILE, rec)
    return True, f"License activated — {p['label']}."


def deactivate():
    """Free this installation (e.g. before moving the license elsewhere)."""
    try:
        LICENSE_FILE.unlink()
        return True
    except Exception:
        return False


def status():
    now = int(time.time())
    if FREE_MODE:
        return {
            "licensed": True,
            "name": FREE_NAME,
            "plan": "Lifetime",
            "plan_fa": "رایگان — Free Edition",
            "expires_at": 0,
            "days_left": 9999,
            "hours_left": 9999*24,
            "lifetime": True,
            "trial_active": False,
            "trial_left_sec": 0,
            "limited": False,
            "throttle_bps": 0,
            "trial_days": TRIAL_DAYS,
            "key_set": True,
            "reason": "",
            "machine": machine_fingerprint(wait=False),
        }
    out = {
        "licensed": False, "name": "", "plan": "", "plan_fa": "",
        "expires_at": 0, "days_left": 0, "hours_left": 0, "lifetime": False,
        "trial_active": False, "trial_left_sec": 0, "limited": False,
        "throttle_bps": 0, "trial_days": TRIAL_DAYS, "key_set": False,
        "reason": "", "machine": machine_fingerprint(wait=False),
    }

    rec = _read_signed(LICENSE_FILE)
    if rec:
        if not _hw_match(rec.get("hw", {})):
            out["reason"] = "This license belongs to another computer."
        elif int(rec.get("last_seen") or 0) - now > 2 * 86400:
            out["reason"] = "The system date was moved back. Correct your date and time."
        else:
            exp = int(rec.get("exp") or 0)
            alive = (exp == 0) or (exp > now)
            if not alive:
                out["reason"] = "The license period has ended."
            else:
                plan = rec.get("plan", "")
                out.update({
                    "licensed": True,
                    "name": rec.get("name", ""),
                    "plan": PLANS.get(plan, {}).get("label", ""),
                    "plan_fa": PLANS.get(plan, {}).get("label_fa", ""),
                    "lifetime": exp == 0,
                    "expires_at": exp,
                    "days_left": max(0, (exp - now) // 86400) if exp else 0,
                    "hours_left": max(0, (exp - now) // 3600) if exp else 0,
                    "key_set": True,
                })
                if now - int(rec.get("last_seen") or 0) > 3600:
                    rec["last_seen"] = now
                    _write_signed(LICENSE_FILE, rec)

    if not out["licensed"]:
        t = _trial()
        trial_end = int(t.get("first_run") or now) + TRIAL_DAYS * 86400
        left = max(0, trial_end - now)
        out.update({"trial_active": left > 0, "trial_left_sec": left,
                    "limited": left <= 0,
                    "throttle_bps": THROTTLE_BPS if left <= 0 else 0})
    return out
