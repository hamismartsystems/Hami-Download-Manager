# -*- coding: utf-8 -*-
"""HDM engine — segmented (multi-part) downloading, queue, scheduler, categories.

Like Internet Download Manager, a file is split into several parts which are
downloaded in parallel (HTTP Range) and written into one single output file;
parts can resume individually after a pause or a disconnect.
"""
import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

UA = "HDM/1.0.1 (HAMI SMART SYSTEMS)"
PARTS = 8              # parallel connections per file
CHUNK = 64 * 1024
MIN_MULTI = 262144   # 256 KB and up: split into parts

CATEGORIES = {
    "Programs": [".exe", ".msi", ".msix", ".apk", ".aab", ".dmg", ".pkg", ".deb", ".rpm",
                 ".appimage", ".jar", ".bin", ".run"],
    "Compressed": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".z",
                   ".iso", ".cab", ".lz", ".lzma"],
    "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg",
              ".mpeg", ".3gp", ".ts", ".m2ts"],
    "Photo": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".heif",
              ".tif", ".tiff", ".ico", ".raw", ".psd", ".ai"],
    "Music": [".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".opus", ".wma"],
    "Documents": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt",
                  ".rtf", ".csv", ".epub", ".mobi", ".djvu", ".odt", ".ods"],
}
OTHER = "Others"


def category_for(name: str) -> str:
    ext = os.path.splitext((name or "").lower())[1]
    if not ext:
        return OTHER
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return OTHER


def _filename(url, cd=""):
    if cd and "filename=" in cd.lower():
        part = cd.split("filename=", 1)[-1].strip().strip("\"'")
        return os.path.basename(unquote(part))
    path = unquote(urlparse(url).path)
    name = os.path.basename(path) or "download.bin"
    return (name.split("?")[0] or "download.bin") or "download.bin"


class Job:
    def __init__(self, url, dest_dir, headers=None):
        self.id = uuid.uuid4().hex[:10]
        self.url = url
        self.dest_dir = Path(dest_dir)
        self.headers = headers or {}
        self.name = _filename(url)
        self.path = ""
        self.size = 0
        self.done = 0
        self.status = "waiting"   # waiting running paused done error canceled
        self.error = ""
        self.speed = 0
        self.created = time.time()
        self.auto_paused = False
        self.parts = 1
        self.prog = None      # per-part resume positions
        self.gen = 0          # guards stale worker threads
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._lock = threading.Lock()
        self._t0 = time.time()
        self._d0 = 0


class Engine:
    def __init__(self, dest_dir, throttle_fn, max_concurrent=3, categorize=True,
                 state_path=None):
        self.dest_dir = Path(dest_dir)
        self.state_path = state_path
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        self.jobs = {}
        self.order = []
        self.lock = threading.Lock()
        self.throttle_fn = throttle_fn
        self._window = []
        self.max_concurrent = max(1, min(5, int(max_concurrent)))
        self.categorize = bool(categorize)
        self.user_paused = False      # Queue Pause button
        self.hold = False             # scheduler holds the queue
        self.override = False         # "Start Now" ignores the schedule once
        self.schedule = {"enabled": False, "start": "00:00", "stop": "06:00"}
        threading.Thread(target=self._sched_loop, daemon=True).start()

    # ── folders ───────────────────────────────────────────────────────────
    def _save(self):
        if self.state_path:
            self.save_state(self.state_path)

    def folder_for(self, name):
        if not self.categorize:
            return self.dest_dir
        return self.dest_dir / category_for(name)

    # ── queue ─────────────────────────────────────────────────────────────
    def running_count(self):
        return sum(1 for j in self.jobs.values() if j.status == "running")

    def queue_state(self):
        return {
            "running": self.running_count(),
            "max": self.max_concurrent,
            "paused": self.user_paused,
            "hold": self.hold,
            "schedule": dict(self.schedule),
            "state": ("paused" if self.user_paused else
                      "waiting" if self.hold else
                      "running"),
        }

    def pump(self):
        """Start waiting jobs while there is room in the queue."""
        if self.user_paused or self.hold:
            return
        with self.lock:
            for jid in self.order:
                if self.running_count() >= self.max_concurrent:
                    break
                j = self.jobs.get(jid)
                if j and j.status == "waiting":
                    j._stop.clear()
                    j._pause.clear()
                    j.status = "queued"
                    threading.Thread(target=self._run, args=(j,), daemon=True).start()

    def set_max_concurrent(self, n):
        self.max_concurrent = max(1, min(5, int(n)))
        self.pump()

    def _pause_auto(self):
        """Scheduler closed the window: stop everything, remember it was automatic."""
        for j in self.jobs.values():
            if j.status == "running":
                j._pause.set()
                j.status = "paused"
                j.auto_paused = True
            elif j.status == "waiting":
                j.auto_paused = True

    def _release_auto(self):
        """Scheduler opened the window: continue what the scheduler had stopped."""
        for j in self.jobs.values():
            if j.auto_paused and j.status in ("paused", "waiting"):
                j.auto_paused = False
                j.status = "waiting"
        self.pump()

    def pause_queue(self, auto=False):
        if auto:
            self.hold = True
            self._pause_auto()
        else:
            self.user_paused = True
            for j in self.jobs.values():
                if j.status == "running":
                    j._pause.set()
                    j.status = "paused"

    def resume_queue(self):
        """Continue the queue — every unfinished download goes back to work."""
        self.user_paused = False
        self.hold = False
        for j in self.jobs.values():
            if j.status in ("paused", "error", "waiting", "queued"):
                j.auto_paused = False
                if j.status != "waiting":
                    j.status = "waiting"
        self.pump()

    def start_now(self):
        """User pressed 'Start now': continue everything, ignore the schedule."""
        self.override = True
        self.user_paused = False
        self.hold = False
        for j in self.jobs.values():
            if j.status in ("paused", "error", "waiting", "queued"):
                j.auto_paused = False
                j.status = "waiting"
        self.pump()

    def set_schedule(self, enabled, start="00:00", stop="06:00"):
        self.schedule = {"enabled": bool(enabled), "start": start or "00:00",
                         "stop": stop or "23:59"}
        self.override = False
        self._apply_schedule(force=True)

    def _in_window(self, now=None):
        s = self.schedule
        if not s["enabled"] or self.override:
            return True
        now = now or datetime.now()
        hm = now.hour * 60 + now.minute

        def mins(v):
            try:
                h, m = str(v).split(":")
                return int(h) * 60 + int(m)
            except Exception:
                return 0
        a, b = mins(s["start"]), mins(s["stop"])
        if a == b:
            return True
        return a <= hm < b if a < b else (hm >= a or hm < b)

    def _apply_schedule(self, force=False):
        inside = self._in_window()
        if not self.schedule["enabled"]:
            if self.hold:
                self.hold = False
                self._release_auto()
            return
        if inside:
            if self.hold or force:
                self.hold = False
                self._release_auto()
        elif not self.hold:
            self.hold = True
            self._pause_auto()

    def _sched_loop(self):
        while True:
            try:
                self._apply_schedule()
            except Exception:
                pass
            time.sleep(10)

    # ── jobs ──────────────────────────────────────────────────────────────
    def list(self):
        with self.lock:
            return [self._pub(self.jobs[i]) for i in self.order]

    def get(self, jid):
        with self.lock:
            j = self.jobs.get(jid)
            return self._pub(j) if j else None

    # ── persistence (so unfinished downloads survive a restart) ───────────
    def save_state(self, path):
        try:
            items = []
            with self.lock:
                ids = list(self.order)
            for jid in ids:
                j = self.jobs.get(jid)
                if not j or j.status in ("done", "canceled"):
                    continue
                items.append({"url": j.url, "name": j.name, "size": j.size,
                              "done": j.done, "prog": j.prog,
                              "folder": str(j.dest_dir), "status": j.status,
                              "id": j.id})
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            tmp = str(path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(items, f)
            os.replace(tmp, path)
        except Exception as _e:
            if os.environ.get("HDM_DEBUG"):
                import traceback; traceback.print_exc()

    def load_state(self, path):
        """Restore unfinished downloads as paused jobs."""
        try:
            items = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return 0
        n = 0
        for it in items:
            if not it.get("url"):
                continue
            j = Job(it["url"], Path(it.get("folder") or self.dest_dir))
            j.name = it.get("name") or j.name
            j.size = int(it.get("size") or 0)
            j.done = int(it.get("done") or 0)
            j.prog = it.get("prog")
            j.status = "paused"
            j.dest_dir = Path(it.get("folder") or self.dest_dir)
            j.path = str(j.dest_dir / j.name)
            with self.lock:
                self.jobs[j.id] = j
                self.order.append(j.id)
            n += 1
        return n

    def unfinished(self):
        return sum(1 for j in self.jobs.values()
                   if j.status in ("paused", "waiting", "queued", "error"))

    def add(self, url, headers=None, filename=None):
        url = (url or "").strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("Only http/https URLs")
        j = Job(url, self.dest_dir, headers)
        if filename:
            j.name = os.path.basename(filename)
        with self.lock:
            self.jobs[j.id] = j
            self.order.append(j.id)   # first added is first to start
        self.pump()
        self._save()
        return self._pub(j)

    def move(self, jid, delta):
        """Move a job earlier (delta -1) or later (delta +1) in the queue."""
        with self.lock:
            if jid not in self.order:
                return False
            i = self.order.index(jid)
            j = i + int(delta)
            if j < 0 or j >= len(self.order):
                return False
            self.order[i], self.order[j] = self.order[j], self.order[i]
        self._save()
        return True

    def pause(self, jid):
        j = self.jobs.get(jid)
        if j and j.status == "running":
            j._pause.set()
            j.status = "paused"

    def resume(self, jid):
        j = self.jobs.get(jid)
        if j and j.status in ("paused", "error", "waiting"):
            j._pause.clear()
            j._stop.clear()
            j.auto_paused = False
            j.status = "waiting"
            self.pump()

    def cancel(self, jid):
        j = self.jobs.get(jid)
        if not j:
            return
        j._stop.set()
        j._pause.clear()
        j.status = "canceled"
        self.pump()
        self._save()

    def shutdown(self):
        for j in list(self.jobs.values()):
            if j.status in ("running", "waiting", "queued"):
                j._stop.set()
                j._pause.clear()
                j.status = "paused"

    def _pub(self, j):
        st = j.status
        if st == "waiting" and self.hold and self.schedule["enabled"]:
            st = "scheduled"
        elif st == "waiting" and self.user_paused:
            st = "queue paused"
        return {
            "id": j.id, "url": j.url, "name": j.name, "path": j.path,
            "size": j.size, "done": j.done, "status": st,
            "error": j.error, "speed": int(j.speed), "parts": j.parts,
            "folder": str(j.dest_dir) if j.path else "",
        }

    # ── transfer ──────────────────────────────────────────────────────────
    def _headers(self, j, extra=None):
        h = {"User-Agent": UA}
        h.update(j.headers)
        if extra:
            h.update(extra)
        return h

    def _throttle(self, n):
        cap = int(self.throttle_fn() or 0)
        if cap <= 0:
            return
        now = time.time()
        self._window.append((now, n))
        cut = now - 1.0
        self._window = [(t, b) for t, b in self._window if t >= cut]
        used = sum(b for _, b in self._window)
        if used > cap:
            time.sleep(min(1.0, (used - cap) / float(cap)))

    def _run(self, j: Job):
        j.gen += 1
        gen = j.gen
        try:
            j.status = "running"
            req = Request(j.url, headers=self._headers(j))
            with urlopen(req, timeout=30) as r:
                length = int(r.headers.get("Content-Length") or 0)
                j.size = length
                cd = r.headers.get("Content-Disposition", "")
                if cd:
                    j.name = _filename(j.url, cd)
                accept_ranges = "bytes" in (r.headers.get("Accept-Ranges") or "").lower()

            folder = self.folder_for(j.name)
            folder.mkdir(parents=True, exist_ok=True)
            j.dest_dir = folder
            dest = folder / j.name
            n = 1
            while dest.exists() and j.done == 0:
                stem, ext = os.path.splitext(j.name)
                dest = folder / f"{stem} ({n}){ext}"
                n += 1
            j.path = str(dest)
            j.name = dest.name

            if length >= MIN_MULTI and accept_ranges:
                j.parts = PARTS
                self._multi(j, dest, length)
            else:
                j.parts = 1
                self._single(j, dest)

            if j.gen != gen:          # a newer worker took over
                return
            if j._pause.is_set() or j._stop.is_set():
                return
            if j.size and j.done >= j.size:
                j.status = "done"
                j.done = j.size
            elif not j.size:
                j.status = "done"
            else:
                j.status = "paused"
        except Exception as e:
            if j.gen == gen and j.status != "paused":
                j.status = "error"
                j.error = str(e)[:240]
        finally:
            self._save()
            if j.gen == gen and j.status in ("done", "error", "canceled"):
                self.pump()

    def _single(self, j, dest):
        # resume support: continue from what is already on disk
        if j.done and dest.exists():
            mode, rng = "ab", {"Range": f"bytes={j.done}-"}
        else:
            mode, rng = "wb", None
        req = Request(j.url, headers=self._headers(j, rng))
        with urlopen(req, timeout=60) as r, open(dest, mode) as f:
            while not j._stop.is_set():
                if j._pause.is_set():
                    j.status = "paused"
                    return
                data = r.read(CHUNK)
                if not data:
                    break
                f.write(data)
                self._note(j, len(data))
                self._throttle(len(data))

    def _multi(self, j, dest, length):
        """Split the file into PARTS ranges; each part resumes where it stopped."""
        step = length // PARTS
        spans = [(i * step, (length - 1) if i == PARTS - 1 else (i + 1) * step - 1)
                 for i in range(PARTS)]
        if not (j.prog and len(j.prog) == len(spans) and dest.exists()):
            # fresh start: create the final file at full size, all parts at zero
            with open(dest, "wb") as f:
                f.truncate(length)
            j.prog = [a for a, _ in spans]
        j.done = sum(pos - a for pos, (a, _) in zip(j.prog, spans))
        threads = [threading.Thread(target=self._part,
                                    args=(j, dest, j.prog[i], spans[i][1], i), daemon=True)
                   for i in range(len(spans))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def _part(self, j, dest, start, end, idx):
        pos = start
        retries = 0
        while pos <= end and not j._stop.is_set():
            if j._pause.is_set():
                return
            req = Request(j.url, headers=self._headers(j, {"Range": f"bytes={pos}-{end}"}))
            try:
                with urlopen(req, timeout=60) as r:
                    with open(dest, "r+b") as f:
                        f.seek(pos)
                        while pos <= end and not j._stop.is_set() and not j._pause.is_set():
                            data = r.read(CHUNK)
                            if not data:
                                break
                            take = min(len(data), end - pos + 1)
                            f.write(data[:take])
                            pos += take
                            j.prog[idx] = pos
                            self._note(j, take)
                            self._throttle(take)
            except Exception:
                retries += 1
                if retries > 25:
                    raise
                time.sleep(0.8)

    def _note(self, j, n):
        with j._lock:
            j.done += n
            now = time.time()
            dt = now - j._t0
            if dt >= 0.4:
                j.speed = (j.done - j._d0) / dt
                j._t0, j._d0 = now, j.done
