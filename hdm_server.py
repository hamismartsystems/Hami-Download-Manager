# -*- coding: utf-8 -*-
"""HDM local API server — used by the Chrome extension (and for remote control)."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORT = int(os.environ.get("HDM_PORT", "17321"))
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "HAMIDownloadManager"


def make_handler(engine, dl_dir, version="1.0.1"):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            import hdm_license as lic
            u = urlparse(self.path)
            if u.path == "/api/status":
                return self._json(200, {"ok": True, "license": lic.status(),
                                        "dir": str(dl_dir), "startup": startup_enabled(),
                                        "version": version,
                                        "queue": engine.queue_state()})
            if u.path == "/api/jobs":
                return self._json(200, {"jobs": engine.list()})
            self._json(404, {"error": "not found"})

        def do_POST(self):
            import hdm_license as lic
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                body = {}
            p = u.path
            if p in ("/api/add", "/add"):
                try:
                    headers = {}
                    if body.get("cookies"):
                        headers["Cookie"] = body["cookies"]
                    if body.get("referrer"):
                        headers["Referer"] = body["referrer"]
                    job = engine.add(body.get("url", ""), headers=headers,
                                     filename=body.get("filename"))
                    return self._json(200, {"ok": True, "job": job})
                except Exception as e:
                    return self._json(400, {"ok": False, "error": str(e)})
            if p == "/api/pause":
                engine.pause(body.get("id", ""))
                return self._json(200, {"ok": True})
            if p == "/api/resume":
                engine.resume(body.get("id", ""))
                return self._json(200, {"ok": True})
            if p == "/api/cancel":
                engine.cancel(body.get("id", ""))
                return self._json(200, {"ok": True})
            if p == "/api/queue/pause":
                engine.pause_queue()
                return self._json(200, {"ok": True, "queue": engine.queue_state()})
            if p == "/api/queue/resume":
                engine.resume_queue()
                return self._json(200, {"ok": True, "queue": engine.queue_state()})
            if p == "/api/queue/start":
                engine.start_now()
                return self._json(200, {"ok": True, "queue": engine.queue_state()})
            if p == "/api/settings":
                if "max_concurrent" in body:
                    engine.set_max_concurrent(int(body["max_concurrent"]))
                if "categorize" in body:
                    engine.categorize = bool(body["categorize"])
                if "schedule" in body:
                    s = body["schedule"]
                    engine.set_schedule(s.get("enabled"), s.get("start", "00:00"),
                                        s.get("stop", "06:00"))
                return self._json(200, {"ok": True, "queue": engine.queue_state()})
            if p == "/api/activate":
                ok, msg = lic.activate(body.get("key", ""), body.get("name", ""))
                return self._json(200 if ok else 400,
                                  {"ok": ok, "message": msg, "license": lic.status()})
            if p == "/api/startup":
                ok, msg = startup_registry(bool(body.get("enable")))
                return self._json(200 if ok else 400, {"ok": ok, "message": msg})
            if p == "/api/quit":
                self._json(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self._json(404, {"error": "not found"})

        def _json(self, code, obj):
            data = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def start_server(engine, dl_dir, port=PORT, version="1.0.1"):
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port),
                                    make_handler(engine, dl_dir, version))
    except OSError:
        return None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# ── Windows: run at startup ────────────────────────────────────────────────
def _startup_cmd():
    exe = os.path.abspath(sys.argv[0])
    if exe.lower().endswith(".exe"):
        return '"%s" --silent' % exe
    return '"%s" "%s" --silent' % (sys.executable.replace("python.exe", "pythonw.exe"), exe)


def startup_registry(enable: bool):
    if sys.platform != "win32":
        return False, "Only available on Windows."
    try:
        import winreg
    except Exception:
        return False, "winreg is not available."
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, _startup_cmd())
            else:
                try:
                    winreg.DeleteValue(key, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True, "Startup setting saved."
    except Exception as e:
        return False, str(e)


def startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
            return True
    except Exception:
        return False
