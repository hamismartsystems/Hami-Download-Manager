# -*- coding: utf-8 -*-
"""HDM online activation — one serial, one computer.

Flow
----
1. Activate  : the app asks the activation server. The server checks the key and
               binds it to this computer's hardware.
2. Re-activate: the same computer (also after reinstalling Windows) always works.
3. Other PC  : refused (HTTP 409) until support releases the license.
4. Offline   : if the server cannot be reached, the license is accepted locally
               for a grace period (14 days); after that an online check is needed.
5. Periodically (once a day) the app re-checks with the server.
"""
import hashlib
import hmac
import json
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import hdm_license as lic

APP_DIR = lic.APP_DIR
ACT_FILE = APP_DIR / "activation.dat"
ENDPOINTS_FILE = Path(__file__).resolve().parent / "endpoints.json"

DEFAULT_ENDPOINTS = [
    "https://hamidesigns.shop/api/hdm",
]
GRACE_DAYS = 14
TIMEOUT = 10


def endpoints():
    try:
        data = json.loads(ENDPOINTS_FILE.read_text(encoding="utf-8"))
        eps = [e for e in data.get("endpoints", []) if isinstance(e, str) and e.strip()]
        if eps:
            return eps
    except Exception:
        pass
    return list(DEFAULT_ENDPOINTS)


def _post(base, path, payload):
    url = base.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "HDM/1.0.1")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _online(action, name="", key="", parts=None):
    """Try every configured server. Returns (response_dict, error_text)."""
    payload = {"name": name, "key": key, "machine": lic.machine_fingerprint(),
               "parts": parts or lic.machine_parts()}
    last_err = ""
    for base in endpoints():
        try:
            out = _post(base, "/" + action, payload)
            if out.get("ok"):
                out["_server"] = base
                return out, ""
            last_err = out.get("error") or "The server refused this license."
            if out.get("status") in (400, 409):
                return None, last_err          # definite answer, do not try others
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
                last_err = body.get("error") or ("HTTP %s" % e.code)
                if e.code in (400, 409):
                    return None, last_err
            except Exception:
                last_err = "HTTP %s" % e.code
        except Exception as e:
            last_err = str(e) or "network error"
    return None, last_err


# ── receipt ────────────────────────────────────────────────────────────────
def _write_receipt(rec):
    lic._write_signed(ACT_FILE, rec)


def _read_receipt():
    d = lic._read_signed(ACT_FILE)
    return d if isinstance(d, dict) and d.get("v") == 3 else None


def _receipt_sig(rec):
    payload = "resp|%s|%s|%s|%s" % (rec.get("key", ""), rec.get("machine", ""),
                                    int(rec.get("exp") or 0), rec.get("plan", ""))
    return hmac.new(lic.SECRET, payload.encode("utf-8"),
                    hashlib.sha256).hexdigest()[:32].upper()


def clean_key(key):
    return re.sub(r"[^0-9A-Z]", "", (key or "").upper())


def receipt_valid(rec):
    """Receipt must be signed by the server, belong to this PC and not be expired."""
    if not rec:
        return False
    if not lic._hw_match(rec.get("parts", {})):
        return False
    exp = int(rec.get("exp") or 0)
    if exp and exp <= int(time.time()):
        return False
    return hmac.compare_digest(_receipt_sig(rec), (rec.get("sig") or "").upper())


def offline_days_left(rec):
    if not rec:
        return 0
    last = int(rec.get("last_check") or 0)
    return max(0, GRACE_DAYS - int((time.time() - last) / 86400))


# ── public API ─────────────────────────────────────────────────────────────
def activate(name, key):
    """Activate online; fall back to the offline licence if there is no internet."""
    name = " ".join((name or "").split())
    if not name:
        return False, "Enter the name the license was issued for.", "offline"
    if not lic.verify(key, name)[0]:
        return False, lic.verify(key, name)[1], "offline"

    res, err = _online("activate", name, key)
    if res:
        rec = {
            "v": 3, "name": res.get("name") or name,
            "key": clean_key(key),
            "plan": res.get("plan", ""),
            "exp": int(res.get("exp") or 0),
            "issued": int(res.get("issued") or time.time()),
            "machine": lic.machine_fingerprint(),
            "parts": lic.machine_parts(),
            "last_check": int(time.time()),
            "sig": res.get("sig", ""),
            "server": res.get("_server", ""),
        }
        _write_receipt(rec)
        lic.activate(key, name)          # keep the offline copy as a second layer
        return True, "License activated — %s." % res.get("plan_label", ""), "online"

    if err and "network" not in err.lower() and "timed out" not in err.lower():
        return False, err, "refused"

    ok, msg = lic.activate(key, name)
    rec = _read_receipt()
    if rec:
        rec["last_check"] = int(time.time())
        _write_receipt(rec)
    if ok:
        return True, (msg + "\n\nNo connection to the activation server: this license "
                      "was activated for this computer and will be verified online "
                      "within %d days." % GRACE_DAYS), "offline"
    return False, msg, "offline"


def recheck():
    """Daily online verification. Returns (ok, message)."""
    rec = _read_receipt()
    if not rec:
        return False, ""
    res, err = _online("check", rec.get("name", ""), rec.get("key", ""))
    if res:
        rec["last_check"] = int(time.time())
        rec["exp"] = int(res.get("exp") or 0)
        rec["plan"] = res.get("plan", rec.get("plan", ""))
        rec["sig"] = res.get("sig", rec.get("sig", ""))
        _write_receipt(rec)
        return True, ""
    if err and "refused" not in err.lower() and "another computer" in err.lower():
        ACT_FILE.unlink(missing_ok=True)
        lic.deactivate()
        return False, err
    return False, err


def deactivate():
    try:
        ACT_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    return lic.deactivate()


def machine_fingerprint():
    return lic.machine_fingerprint()


_STATUS_CACHE = {"at": 0.0, "value": None}
_RECHECK = {"at": 0.0, "busy": False, "ok": None, "msg": ""}


def _kick_recheck():
    """Confirm the licence in the background. Never block a button click."""
    if _RECHECK["busy"] or time.time() - _RECHECK["at"] < 60:
        return
    _RECHECK["busy"] = True

    def work():
        try:
            ok, msg = recheck()
            _RECHECK["ok"] = ok
            _RECHECK["msg"] = msg or ""
            _STATUS_CACHE["at"] = 0.0
        except Exception as e:
            _RECHECK["ok"] = False
            _RECHECK["msg"] = str(e)
        finally:
            _RECHECK["at"] = time.time()
            _RECHECK["busy"] = False

    threading.Thread(target=work, daemon=True).start()


def status():
    """Unified licence status: online receipt first, offline licence as fallback."""
    now_f = time.time()
    cached = _STATUS_CACHE["value"]
    if cached is not None and now_f - _STATUS_CACHE["at"] < 3:
        return dict(cached)

    st = lic.status()
    st.update({"source": "offline", "grace_days": 0, "last_check": 0, "server": ""})
    rec = _read_receipt()
    if not rec or not receipt_valid(rec):
        _STATUS_CACHE["at"] = now_f
        _STATUS_CACHE["value"] = dict(st)
        return st

    now = int(now_f)
    exp = int(rec.get("exp") or 0)
    days = max(0, (exp - now) // 86400) if exp else 0
    grace = offline_days_left(rec)

    if grace <= 0:      # offline for too long — confirm without freezing the window
        _kick_recheck()
        if _RECHECK["ok"] is False and not _RECHECK["busy"]:
            st.update({"licensed": False, "reason": _RECHECK["msg"] or "Online verification required."})
            _STATUS_CACHE["at"] = now_f
            _STATUS_CACHE["value"] = dict(st)
            return st
        rec = _read_receipt() or rec
        grace = offline_days_left(rec)

    st.update({
        "licensed": True,
        "name": rec.get("name", ""),
        "plan": lic.PLANS.get(rec.get("plan", ""), {}).get("label", ""),
        "plan_fa": lic.PLANS.get(rec.get("plan", ""), {}).get("label_fa", ""),
        "lifetime": exp == 0,
        "expires_at": exp,
        "days_left": days,
        "hours_left": max(0, (exp - now) // 3600) if exp else 0,
        "key_set": True,
        "source": "online",
        "grace_days": grace,
        "last_check": int(rec.get("last_check") or 0),
        "server": rec.get("server", ""),
        "reason": "",
    })
    _STATUS_CACHE["at"] = now_f
    _STATUS_CACHE["value"] = dict(st)
    return st
