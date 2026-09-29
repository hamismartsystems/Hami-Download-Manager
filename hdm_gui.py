#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HDM v2.1.2 — Exact replica, bulletproof finesse, fully working
Root fix for screenshot 1.png ugly vs reference:
- SegmentedBar now custom QPainter (no QFrame stylesheet) → always green #4CAF50 done, blue #2196F3 running, dark #15181E pending
- Global QSS no longer sets QWidget background → QLabel black rect bug fixed
- Sidebar pill border bug fixed via objectName styling
- DownloadCard labels all transparent, icon 44px, title 13px bold
"""
import os
import sys
import time
import json
import webbrowser
import subprocess
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt6.QtCore import Qt, QTimer, QSettings, QSize, QPointF, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QFont, QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QMessageBox, QMenu, QFileDialog, QDialog, QCheckBox,
    QSystemTrayIcon, QScrollArea, QFrame, QToolButton, QInputDialog
)

import hdm_license as lic
import hdm_activation as act
from hdm_engine import Engine
import hdm_server

VERSION = "2.1.2"
ORG = "HAMI SMART SYSTEMS"
APP = "HDM - Hami Download Manager"
STATE_DIR = Path(os.environ.get("HDM_HOME") or Path.home() / ".hami-download-manager")
STATE_DIR.mkdir(parents=True, exist_ok=True)
JOBS_FILE = STATE_DIR / "jobs.json"

def fmt(n):
    n = float(n or 0)
    for unit, div in (("GB", 1073741824), ("MB", 1048576), ("KB", 1024)):
        if n >= div:
            return f"{n/div:.1f} {unit}"
    return f"{int(n)} B"

def fmt_speed(bps):
    if bps <= 0:
        return "0 B/s"
    return fmt(bps) + "/s"

def fmt_eta(done, total, speed):
    if speed <= 0 or total <= 0:
        return "--:--"
    sec = int(max(0, total - done) / speed)
    if sec > 3600:
        return f"{sec//3600}h {sec%3600//60}m"
    if sec > 60:
        return f"{sec//60}m {sec%60}s"
    return f"{sec}s"

# ── Pro Widgets — bulletproof QPainter ──

class SegmentedBar(QWidget):
    """8 bars — paints directly, no child QFrames, so never invisible"""
    def __init__(self):
        super().__init__()
        self.setFixedHeight(16)
        self._segs = [{"state":"pending","pct":0}]*8

    def set_segments(self, segs):
        # normalize to 8
        arr = list(segs[:8]) if segs else []
        # if empty, arr stays empty
        if not arr:
            self._segs = [{"state":"pending","pct":0}]*8
        else:
            # pad
            arr = (arr + [{"state":"pending","pct":0}]*8)[:8]
            self._segs = arr
        self.update()

    def set_from_pct(self, pct, status):
        """fallback when engine gives no parts_progress"""
        pct = int(pct)
        filled = int(pct/100*8)
        segs=[]
        for i in range(8):
            if i < filled:
                segs.append({"state":"done","pct":100})
            elif i == filled and status=="running" and pct<100:
                segs.append({"state":"running","pct":50})
            elif i == filled and status=="paused" and pct>0 and pct<100:
                # paused in middle: show blue for current
                segs.append({"state":"running","pct":50})
            else:
                segs.append({"state":"pending","pct":0})
        self.set_segments(segs)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        h = 10
        y = (self.height()-h)//2
        count = 8
        spacing = 6
        # bar width
        bar_w = max(8, (w - spacing*(count-1)) // count)

        for i, s in enumerate(self._segs):
            x = i*(bar_w+spacing)
            if x+bar_w > w:
                bar_w = w - x
                if bar_w <=0:
                    break
            state = s.get("state","pending")
            # colors exact like reference
            if state == "done":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor("#4CAF50")))
                p.drawRoundedRect(x, y, bar_w, h, 3, 3)
            elif state == "running":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor("#2196F3")))
                p.drawRoundedRect(x, y, bar_w, h, 3, 3)
            else:
                # pending — dark with subtle border
                p.setPen(QPen(QColor("#252A35"), 1))
                p.setBrush(QBrush(QColor("#15181E")))
                p.drawRoundedRect(x, y, bar_w, h, 3, 3)

class SpeedGraph(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(112)
        self.setMinimumWidth(220)
        self.history = [0]*60

    def add(self, v):
        self.history.append(float(v or 0))
        if len(self.history) > 60:
            self.history.pop(0)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # bg
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#15181E")))
        p.drawRoundedRect(self.rect(), 8, 8)

        if not self.history or max(self.history) == 0:
            p.setPen(QPen(QColor("#252A35"), 1, Qt.PenStyle.DotLine))
            p.drawLine(0, self.height()//2, self.width(), self.height()//2)
            return
        max_v = max(self.history) or 1
        w = self.width()
        h = self.height()
        # grid
        p.setPen(QPen(QColor("#252A35"), 1, Qt.PenStyle.DotLine))
        p.drawLine(0, h//3, w, h//3)
        p.drawLine(0, 2*h//3, w, 2*h//3)

        pts = []
        for i, v in enumerate(self.history):
            x = int(i/(len(self.history)-1)*w) if len(self.history)>1 else 0
            y = h - int((v/max_v)*(h-20)) - 10
            pts.append(QPointF(x, y))

        if len(pts) > 1:
            # fill gradient
            p.setPen(Qt.PenStyle.NoPen)
            grad = QLinearGradient(0,0,0,h)
            grad.setColorAt(0, QColor(76,175,80,110))
            grad.setColorAt(1, QColor(76,175,80,12))
            p.setBrush(QBrush(grad))
            poly = QPainterPath()
            poly.moveTo(pts[0])
            for pt in pts[1:]:
                poly.lineTo(pt)
            poly.lineTo(QPointF(w, h))
            poly.lineTo(QPointF(0, h))
            poly.closeSubpath()
            p.drawPath(poly)

            # line
            p.setPen(QPen(QColor("#4CAF50"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
            p.drawPath(path)

class ToolBtn(QToolButton):
    def __init__(self, emoji, text):
        super().__init__()
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setText(f"{emoji}\n{text}")
        self.setFixedSize(78, 62)
        # no global background override
        self.setStyleSheet("""
            QToolButton{
                background: transparent;
                border: 0;
                border-radius: 8px;
                color: #A0A5B0;
                font-size: 11px;
                padding: 4px;
            }
            QToolButton:hover{
                background: #252A35;
                color: #E6E6E6;
            }
            QToolButton:pressed{
                background: #1E2025;
            }
        """)
        f = self.font()
        f.setPointSize(11)
        self.setFont(f)

class DownloadCard(QFrame):
    pauseSig = pyqtSignal(str)
    resumeSig = pyqtSignal(str)
    stopSig = pyqtSignal(str)

    def __init__(self, job):
        super().__init__()
        self.job_id = job["id"]
        self.setObjectName("downloadCard")
        self.setMinimumHeight(88)
        self.setMaximumHeight(96)
        # Only this object gets background, children transparent via global QLabel rule
        self.setStyleSheet("""
            QFrame#downloadCard{
                background: #1E2025;
                border: 1px solid #2A2E35;
                border-radius: 10px;
            }
            QFrame#downloadCard:hover{
                border: 1px solid #3A4050;
            }
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12,10,12,10)
        lay.setSpacing(12)

        # icon box
        self.ico = QLabel()
        self.ico.setFixedSize(44,44)
        self.ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ico.setStyleSheet("background: #2A2E35; border-radius: 8px; font-size: 22px; color: #E6E6E6;")
        lay.addWidget(self.ico)

        # center
        center = QVBoxLayout()
        center.setSpacing(4)
        self.title = QLabel(job["name"])
        self.title.setStyleSheet("color: #E6E6E6; font-size: 13px; font-weight: 600; background: transparent; border: 0;")
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        center.addWidget(self.title)

        self.bar = SegmentedBar()
        center.addWidget(self.bar)

        bot = QHBoxLayout()
        bot.setSpacing(10)
        self.speed = QLabel()
        self.speed.setStyleSheet("color: #8B90A0; font-size: 11px; background: transparent; border: 0;")
        self.size = QLabel()
        self.size.setStyleSheet("color: #8B90A0; font-size: 11px; background: transparent; border: 0;")
        bot.addWidget(self.speed)
        bot.addStretch()
        bot.addWidget(self.size)
        center.addLayout(bot)

        lay.addLayout(center, 1)

        # buttons
        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(6)
        self.b_pause = QPushButton("⏸\nPause")
        self.b_resume = QPushButton("▶\nResume")
        self.b_stop = QPushButton("■\nStop")
        for b in (self.b_pause, self.b_resume, self.b_stop):
            b.setFixedSize(58, 58)
            b.setStyleSheet("""
                QPushButton{
                    background: #2A2E35;
                    color: #9AA0B0;
                    border: 1px solid #353B4A;
                    border-radius: 8px;
                    font-size: 10px;
                    font-weight: 500;
                }
                QPushButton:hover{
                    background: #353B4A;
                    color: #E6E6E6;
                }
                QPushButton:disabled{
                    color: #4A4F5E;
                    background: #1E2025;
                    border: 1px solid #2A2E35;
                }
            """)
        self.b_pause.clicked.connect(lambda: self.pauseSig.emit(self.job_id))
        self.b_resume.clicked.connect(lambda: self.resumeSig.emit(self.job_id))
        self.b_stop.clicked.connect(lambda: self.stopSig.emit(self.job_id))
        btn_lay.addWidget(self.b_pause)
        btn_lay.addWidget(self.b_resume)
        btn_lay.addWidget(self.b_stop)
        lay.addLayout(btn_lay)

        self.update_job(job)

    def _icon(self, name):
        ext = Path(name).suffix.lower()
        if ext in (".iso",".img"): return "💿"
        if ext in (".exe",".msi"): return "💾"
        if ext in (".zip",".rar",".7z"): return "📦"
        if ext in (".mp4",".mkv"): return "🎬"
        if ext in (".mp3",): return "🎵"
        return "📄"

    def update_job(self, job):
        self.job_id = job["id"]
        name = job["name"]
        size = job["size"]
        done = job["done"]
        speed = job["speed"]
        status = job["status"]
        pct = int(done/size*100) if size else (100 if status=="done" else 0)

        # title: name + size in parens like reference
        if size and pct<100:
            self.title.setText(f"{name} ({fmt(size)})")
        else:
            self.title.setText(name)
        self.ico.setText(self._icon(name))

        segs = job.get("parts_progress", [])
        if segs and len(segs)>=8:
            # use engine segs directly
            self.bar.set_segments(segs)
        elif segs and len(segs)>0:
            # pad to 8 if less than 8
            self.bar.set_segments(segs)
        else:
            # fallback from pct — guarantees visible bars even if engine old
            self.bar.set_from_pct(pct, status)

        if status == "running":
            self.speed.setText(f"Speed: {fmt_speed(speed)} | ETA: {fmt_eta(done,size,speed)}")
        elif status == "done":
            self.speed.setText("Completed")
        elif status in ("paused","error","waiting","queue paused","scheduled"):
            self.speed.setText(f"Paused — {fmt(done)} / {fmt(size)}" if size else "Paused")
        else:
            self.speed.setText("")

        self.size.setText(f"{fmt(done)} / {fmt(size)} | {pct}%" if size else f"{pct}%")

        # border + button states — exact like reference
        if status == "running":
            self.setStyleSheet("QFrame#downloadCard{background: #1E242E; border: 1px solid #4A90E2; border-radius: 10px;}")
            self.b_pause.setEnabled(True)
            self.b_resume.setEnabled(False)
            self.b_pause.setStyleSheet("QPushButton{background: #2A2E35; color: #9AA0B0; border: 1px solid #353B4A; border-radius: 8px; font-size: 10px;} QPushButton:hover{background: #353B4A;}")
            self.b_resume.setStyleSheet("QPushButton{background: #1E2025; color: #4A4F5E; border: 1px solid #2A2E35; border-radius: 8px; font-size: 10px;}")
            # active running gets blue pause? Actually reference shows Pause blue when running
            self.b_pause.setStyleSheet("QPushButton{background: #4A90E2; color: white; border: 0; border-radius: 8px; font-size: 10px; font-weight: 700;} QPushButton:hover{background: #5AA0F2;}")
        elif status in ("paused","error","waiting","queue paused","scheduled"):
            self.setStyleSheet("QFrame#downloadCard{background: #1E2025; border: 1px solid #2A2E35; border-radius: 10px;} QFrame#downloadCard:hover{border: 1px solid #3A4050;}")
            self.b_pause.setEnabled(False)
            self.b_resume.setEnabled(True)
            self.b_pause.setStyleSheet("QPushButton{background: #1E2025; color: #4A4F5E; border: 1px solid #2A2E35; border-radius: 8px; font-size: 10px;}")
            self.b_resume.setStyleSheet("QPushButton{background: #4A90E2; color: white; border: 0; border-radius: 8px; font-size: 10px; font-weight: 700;} QPushButton:hover{background: #5AA0F2;}")
        else:
            self.setStyleSheet("QFrame#downloadCard{background: #1E2025; border: 1px solid #2A2E35; border-radius: 10px;}")
            self.b_pause.setEnabled(False)
            self.b_resume.setEnabled(False)

# ── Main Window ──
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG, "HDM")
        self.lang = self.settings.value("lang","en")
        dl = self.settings.value("dl_dir","")
        self.dl_dir = Path(dl) if dl else Path.home() / "Downloads" / "HDM"
        self.dl_dir.mkdir(parents=True, exist_ok=True)

        cat = str(self.settings.value("categorize", True)).lower() not in ("false","0")
        conc = int(self.settings.value("max_concurrent",3) or 3)
        self.engine = Engine(self.dl_dir, throttle_fn=lambda: act.status()["throttle_bps"], max_concurrent=conc, categorize=cat, state_path=str(JOBS_FILE))
        self.engine.set_schedule(
            str(self.settings.value("sched_enabled", False)).lower()=="true",
            str(self.settings.value("sched_start","01:00")),
            str(self.settings.value("sched_stop","07:00")))
        self.engine.load_state(JOBS_FILE)

        self.cards = {}
        self.tray_notified = False
        self._save_tick = 0

        self.setWindowTitle(f"HDM - Hami Download Manager FREE EDITION, free")
        self.setWindowIcon(self._app_icon())
        self.resize(1200, 720)
        self.setMinimumSize(1020, 620)
        self.setStyleSheet(self._qss())

        self._build_ui()
        self._build_menu()
        self._build_tray()

        try:
            hdm_server.start_server(self.engine, self.dl_dir, version=VERSION)
        except Exception as e:
            print(f"server start failed: {e}")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(800)
        self.refresh()

    def _app_icon(self):
        for name in ("hdm.ico","hdm-bmp.ico"):
            p = HERE / name
            if p.exists():
                return QIcon(str(p))
        p = HERE / "web" / "logo.png"
        return QIcon(str(p)) if p.exists() else QIcon()

    def _qss(self):
        # FIX: no QWidget{background} — that caused black rect behind labels in screenshot
        return """
        QMainWindow{
            background: #0F1115;
        }
        QLabel{
            background: transparent;
            border: 0;
        }
        QFrame{
            background: transparent;
        }
        QMenuBar{
            background: #1E2025;
            color: #A0A5B0;
            border-bottom: 1px solid #2A2E35;
            padding: 2px 6px;
        }
        QMenuBar::item{
            padding: 6px 12px;
            border-radius: 4px;
        }
        QMenuBar::item:selected{
            background: #2A2E35;
            color: #E6E6E6;
        }
        QMenu{
            background: #1E2025;
            color: #E6E6E6;
            border: 1px solid #2A2E35;
            border-radius: 8px;
            padding: 6px;
        }
        QMenu::item{
            padding: 8px 16px;
            border-radius: 6px;
        }
        QMenu::item:selected{
            background: #2A2E35;
        }
        QStatusBar{
            background: #1A1D23;
            color: #8B90A0;
            border-top: 1px solid #2A2E35;
            font-size: 11px;
            padding: 4px 10px;
        }
        QScrollArea{
            background: #0F1115;
            border: 0;
        }
        QWidget#scrollContent{
            background: #0F1115;
        }
        QScrollBar:vertical{
            background: #0F1115;
            width: 8px;
            margin: 0;
        }
        QScrollBar::handle:vertical{
            background: #2A2E35;
            border-radius: 4px;
            min-height: 40px;
            margin: 2px;
        }
        QScrollBar::handle:vertical:hover{
            background: #3A4050;
        }
        QLineEdit{
            background: #2A2E35;
            border: 1px solid #3A4050;
            border-radius: 8px;
            padding: 8px 12px;
            color: #E6E6E6;
        }
        QLineEdit:focus{
            border: 1px solid #4A90E2;
        }
        QFrame#sidebar{
            background: #15181E;
            border-left: 1px solid #2A2E35;
        }
        QFrame#toolbar{
            background: #1E2025;
            border-bottom: 1px solid #2A2E35;
        }
        QFrame#connBox, QFrame#detailsBox{
            background: #1E2025;
            border: 1px solid #2A2E35;
            border-radius: 8px;
        }
        """

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0,0,0,0)
        v.setSpacing(0)

        # toolbar
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar.setFixedHeight(72)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(10,6,10,6)
        tb.setSpacing(4)

        self.t_new = ToolBtn("📄+", "New+")
        self.t_start = ToolBtn("▶", "Start All")
        self.t_pause = ToolBtn("⏸", "Pause All")
        self.t_remove = ToolBtn("🗑", "Remove")
        self.t_settings = ToolBtn("⚙️", "Settings")

        for b in (self.t_new, self.t_start, self.t_pause, self.t_remove):
            tb.addWidget(b)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background: #2A2E35; border: 0;")
        sep.setFixedWidth(1)
        sep.setFixedHeight(40)
        tb.addWidget(sep)
        tb.addWidget(self.t_settings)
        tb.addStretch()

        # search — fixed design like reference, no pill inside
        search_wrap = QFrame()
        search_wrap.setObjectName("searchWrap")
        search_wrap.setFixedSize(220, 38)
        search_wrap.setStyleSheet("QFrame#searchWrap{background: #2A2E35; border: 1px solid #3A4050; border-radius: 8px;}")
        s_lay = QHBoxLayout(search_wrap)
        s_lay.setContentsMargins(10,0,8,0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search")
        self.search.setStyleSheet("background: transparent; border: 0; color: #E6E6E6; font-size: 13px;")
        self.search_icon = QLabel("🔍")
        self.search_icon.setStyleSheet("background: transparent; border: 0; color: #6B7280; font-size: 14px;")
        s_lay.addWidget(self.search,1)
        s_lay.addWidget(self.search_icon)
        tb.addWidget(search_wrap)

        v.addWidget(toolbar)

        # content
        content = QHBoxLayout()
        content.setContentsMargins(0,0,0,0)
        content.setSpacing(0)

        # left list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_wrap = QWidget()
        self.list_wrap.setObjectName("scrollContent")
        self.list_lay = QVBoxLayout(self.list_wrap)
        self.list_lay.setContentsMargins(12,12,12,12)
        self.list_lay.setSpacing(10)
        self.list_lay.addStretch()
        self.scroll.setWidget(self.list_wrap)
        content.addWidget(self.scroll, 1)

        # right sidebar — fixed pill bug
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(300)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14,14,14,14)
        side.setSpacing(14)

        lbl_cur = QLabel("Currently Downloading")
        lbl_cur.setStyleSheet("color: #E6E6E6; font-size: 13px; font-weight: 600; background: transparent; border: 0;")
        side.addWidget(lbl_cur)

        self.graph = SpeedGraph()
        side.addWidget(self.graph)

        # connection status — no inner pill
        conn = QFrame()
        conn.setObjectName("connBox")
        cl = QVBoxLayout(conn)
        cl.setContentsMargins(12,10,12,10)
        cl.setSpacing(6)
        row1 = QHBoxLayout()
        t1 = QLabel("Connection Status")
        t1.setStyleSheet("color: #E6E6E6; font-size: 12px; font-weight: 600; background: transparent; border: 0;")
        chk = QLabel("✅")
        chk.setStyleSheet("background: transparent; border: 0;")
        row1.addWidget(t1)
        row1.addStretch()
        row1.addWidget(chk)
        cl.addLayout(row1)
        self.lbl_threads = QLabel("8/8 threads active")
        self.lbl_threads.setStyleSheet("color: #8B90A0; font-size: 11px; background: transparent; border: 0;")
        cl.addWidget(self.lbl_threads)
        side.addWidget(conn)

        # details — no inner pill
        det = QFrame()
        det.setObjectName("detailsBox")
        dl = QVBoxLayout(det)
        dl.setContentsMargins(12,10,12,10)
        dl.setSpacing(6)
        t2 = QLabel("Details")
        t2.setStyleSheet("color: #E6E6E6; font-size: 12px; font-weight: 600; background: transparent; border: 0;")
        dl.addWidget(t2)
        self.lbl_save = QLabel(f"Save To: {self.dl_dir}")
        self.lbl_save.setWordWrap(True)
        self.lbl_save.setStyleSheet("color: #8B90A0; font-size: 11px; background: transparent; border: 0;")
        self.lbl_speed = QLabel("Total Speed: 0 B/s")
        self.lbl_speed.setStyleSheet("color: #8B90A0; font-size: 11px; background: transparent; border: 0;")
        dl.addWidget(self.lbl_save)
        dl.addWidget(self.lbl_speed)
        side.addWidget(det)

        side.addStretch()
        content.addWidget(sidebar)

        v.addLayout(content,1)

        self.status = self.statusBar()
        self.status.showMessage("Total Speed: 0 B/s | Total Downloaded: 0 B | Active: 0, Completed: 0")

        self.t_new.clicked.connect(self._add_dialog)
        self.t_start.clicked.connect(lambda: (self.engine.resume_queue(), self.refresh()))
        self.t_pause.clicked.connect(lambda: (self.engine.pause_queue(), self.refresh()))
        self.t_remove.clicked.connect(self._remove_completed)
        self.t_settings.clicked.connect(self._open_settings)
        self.search.textChanged.connect(self._filter)

    def _build_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu("File")
        a_open = QAction("Open Downloads Folder", self)
        a_open.triggered.connect(self._open_folder)
        m_file.addAction(a_open)
        a_exit = QAction("Exit", self)
        a_exit.triggered.connect(self._quit)
        m_file.addAction(a_exit)

        m_dl = mb.addMenu("Downloads")
        m_tools = mb.addMenu("Tools")
        a_set = QAction("Settings", self)
        a_set.triggered.connect(self._open_settings)
        m_tools.addAction(a_set)

        m_help = mb.addMenu("Help")
        a_about = QAction("About", self)
        a_about.triggered.connect(lambda: QMessageBox.information(self, "HDM", f"HDM v{VERSION} FREE EDITION\nHAMI SMART SYSTEMS"))
        m_help.addAction(a_about)

        ver = QLabel(f"v{VERSION}")
        ver.setStyleSheet("color: #6B7280; font-size: 11px; padding: 4px 12px; background: transparent; border: 0;")
        mb.setCornerWidget(ver, Qt.Corner.TopRightCorner)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self._app_icon(), self)
        menu = QMenu()
        a_show = QAction("Show HDM", self)
        a_show.triggered.connect(self.showNormal)
        a_quit = QAction("Quit", self)
        a_quit.triggered.connect(self._quit)
        menu.addAction(a_show)
        menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _open_folder(self):
        p = str(self.dl_dir)
        try:
            if sys.platform == "win32":
                os.startfile(p)
            else:
                subprocess.Popen(["xdg-open", p])
        except Exception:
            webbrowser.open(f"file://{p}")

    def _add_dialog(self):
        url, ok = QInputDialog.getText(self, "New Download", "Enter URL:")
        if ok and url.strip():
            try:
                self.engine.add(url.strip())
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "HDM", str(e))

    def _remove_completed(self):
        for j in self.engine.list():
            if j["status"] == "done":
                self.engine.cancel(j["id"])
        self.refresh()

    def _open_settings(self):
        n, ok = QInputDialog.getInt(self, "Settings", "Max simultaneous downloads (1-5):", self.engine.max_concurrent, 1, 5)
        if ok:
            self.engine.set_max_concurrent(n)
            self.settings.setValue("max_concurrent", n)
            self.refresh()

    def _filter(self, txt):
        txt = txt.lower()
        for card in self.cards.values():
            card.setVisible(txt in card.title.text().lower() if txt else True)

    def _quit(self):
        self.engine.save_state(JOBS_FILE)
        self.engine.shutdown()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        if not self.tray_notified:
            self.tray.showMessage("HDM", "HDM is running in tray.", QSystemTrayIcon.MessageIcon.Information, 2000)
            self.tray_notified = True

    def refresh(self):
        jobs = self.engine.list()
        cur_ids = set(self.cards.keys())
        new_ids = set(j["id"] for j in jobs)
        for jid in cur_ids - new_ids:
            c = self.cards.pop(jid)
            self.list_lay.removeWidget(c)
            c.deleteLater()
        for job in jobs:
            jid = job["id"]
            if jid in self.cards:
                self.cards[jid].update_job(job)
            else:
                card = DownloadCard(job)
                card.pauseSig.connect(lambda jid: (self.engine.pause(jid), self.refresh()))
                card.resumeSig.connect(lambda jid: (self.engine.resume(jid), self.refresh()))
                card.stopSig.connect(lambda jid: (self.engine.cancel(jid), self.refresh()))
                self.list_lay.insertWidget(self.list_lay.count()-1, card)
                self.cards[jid] = card

        total_speed = sum(j["speed"] for j in jobs if j["status"]=="running")
        active = sum(1 for j in jobs if j["status"]=="running")
        completed = sum(1 for j in jobs if j["status"]=="done")
        total_done = sum(j["done"] for j in jobs)

        self.graph.add(total_speed)
        self.lbl_threads.setText(f"{active*8 if active else 8}/8 threads active" if active else "8/8 threads active")
        self.lbl_speed.setText(f"Total Speed: {fmt_speed(total_speed)}")
        self.lbl_save.setText(f"Save To: {self.dl_dir}")
        self.status.showMessage(f"Total Speed: {fmt_speed(total_speed)} | Total Downloaded: {fmt(total_done)} | Active: {active}, Completed: {completed}")

        self._save_tick += 1
        if self._save_tick % 8 == 0:
            self.engine.save_state(JOBS_FILE)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setOrganizationName(ORG)
    app.setQuitOnLastWindowClosed(False)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
