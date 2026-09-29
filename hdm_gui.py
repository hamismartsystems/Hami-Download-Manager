#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HDM v2.1.3 — Pro finesse, big icons, auto-paste, open folder/file, full Settings + About like reference"""
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
from PyQt6.QtGui import QAction, QIcon, QFont, QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QMessageBox, QMenu, QFileDialog, QDialog, QCheckBox,
    QSystemTrayIcon, QScrollArea, QFrame, QToolButton, QInputDialog, QSlider,
    QSpinBox, QComboBox, QStackedWidget, QGroupBox
)

import hdm_license as lic
import hdm_activation as act
from hdm_engine import Engine
import hdm_server

VERSION = "2.1.3"
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

# ── Pro Widgets ──

class SegmentedBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(16)
        self._segs = [{"state":"pending","pct":0}]*8

    def set_segments(self, segs):
        arr = list(segs[:8]) if segs else []
        if not arr:
            self._segs = [{"state":"pending","pct":0}]*8
        else:
            arr = (arr + [{"state":"pending","pct":0}]*8)[:8]
            self._segs = arr
        self.update()

    def set_from_pct(self, pct, status):
        pct = int(pct)
        filled = int(pct/100*8)
        segs=[]
        for i in range(8):
            if i < filled:
                segs.append({"state":"done","pct":100})
            elif i == filled and status in ("running","paused") and 0<pct<100:
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
        bar_w = max(8, (w - spacing*(count-1)) // count)
        for i, s in enumerate(self._segs):
            x = i*(bar_w+spacing)
            if x+bar_w > w:
                bar_w = w - x
                if bar_w <=0:
                    break
            state = s.get("state","pending")
            if state == "done":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor("#4CAF50")))
                p.drawRoundedRect(x, y, bar_w, h, 3, 3)
            elif state == "running":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor("#2196F3")))
                p.drawRoundedRect(x, y, bar_w, h, 3, 3)
            else:
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
        p.setPen(QPen(QColor("#252A35"), 1, Qt.PenStyle.DotLine))
        p.drawLine(0, h//3, w, h//3)
        p.drawLine(0, 2*h//3, w, 2*h//3)
        pts = []
        for i, v in enumerate(self.history):
            x = int(i/(len(self.history)-1)*w) if len(self.history)>1 else 0
            y = h - int((v/max_v)*(h-20)) - 10
            pts.append(QPointF(x, y))
        if len(pts) > 1:
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
            p.setPen(QPen(QColor("#4CAF50"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
            p.drawPath(path)

class ToolBtn(QFrame):
    clicked = pyqtSignal()
    def __init__(self, icon_char, label_text):
        super().__init__()
        self.setObjectName("toolBtn")
        self.setFixedSize(96, 78)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2,8,2,8)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl = QLabel(icon_char)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("background: transparent; border: 0; font-size: 28px;")
        self.text_lbl = QLabel(label_text)
        self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_lbl.setStyleSheet("background: transparent; border: 0; font-size: 12px; color: #A0A5B0; font-weight: 500;")
        lay.addWidget(self.icon_lbl)
        lay.addWidget(self.text_lbl)
        self.setStyleSheet("""
            QFrame#toolBtn{
                background: transparent;
                border: 0;
                border-radius: 12px;
            }
            QFrame#toolBtn:hover{
                background: #252A35;
            }
        """)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def enterEvent(self, e):
        self.text_lbl.setStyleSheet("background: transparent; border: 0; font-size: 12px; color: #E6E6E6; font-weight: 600;")

    def leaveEvent(self, e):
        self.text_lbl.setStyleSheet("background: transparent; border: 0; font-size: 12px; color: #A0A5B0; font-weight: 500;")

class CardBtn(QFrame):
    clicked = pyqtSignal()
    def __init__(self, icon_char, label_text, blue=False):
        super().__init__()
        self._blue = blue
        self._icon_char = icon_char
        self._label_text = label_text
        self.setFixedSize(72, 64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("cardBtn")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2,6,2,6)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl = QLabel(icon_char)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet(f"background: transparent; border: 0; font-size: 18px; color: {'white' if blue else '#9AA0B0'};")
        self.text_lbl = QLabel(label_text)
        self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_lbl.setStyleSheet(f"background: transparent; border: 0; font-size: 10px; font-weight: 600; color: {'white' if blue else '#9AA0B0'};")
        lay.addWidget(self.icon_lbl)
        lay.addWidget(self.text_lbl)
        self._apply_style()

    def _apply_style(self):
        if self._blue:
            self.setStyleSheet("""
                QFrame#cardBtn{
                    background: #4A90E2;
                    border: 0;
                    border-radius: 10px;
                }
                QFrame#cardBtn:hover{
                    background: #5AA0F2;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#cardBtn{
                    background: #2A2E35;
                    border: 1px solid #353B4A;
                    border-radius: 10px;
                }
                QFrame#cardBtn:hover{
                    background: #353B4A;
                    border: 1px solid #4A4F5E;
                }
            """)

    def set_blue(self, blue):
        self._blue = blue
        self.icon_lbl.setStyleSheet(f"background: transparent; border: 0; font-size: 18px; color: {'white' if blue else '#9AA0B0'};")
        self.text_lbl.setStyleSheet(f"background: transparent; border: 0; font-size: 10px; font-weight: 600; color: {'white' if blue else '#9AA0B0'};")
        self._apply_style()

    def set_enabled_style(self, enabled):
        if not enabled:
            self.setStyleSheet("""
                QFrame#cardBtn{
                    background: #1E2025;
                    border: 1px solid #2A2E35;
                    border-radius: 10px;
                }
            """)
            self.icon_lbl.setStyleSheet("background: transparent; border: 0; font-size: 18px; color: #4A4F5E;")
            self.text_lbl.setStyleSheet("background: transparent; border: 0; font-size: 10px; color: #4A4F5E;")
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._apply_style()
            self.icon_lbl.setStyleSheet(f"background: transparent; border: 0; font-size: 18px; color: {'white' if self._blue else '#9AA0B0'};")
            self.text_lbl.setStyleSheet(f"background: transparent; border: 0; font-size: 10px; font-weight: 600; color: {'white' if self._blue else '#9AA0B0'};")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.clicked.emit()

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.set_enabled_style(enabled)

class DownloadCard(QFrame):
    pauseSig = pyqtSignal(str)
    resumeSig = pyqtSignal(str)
    stopSig = pyqtSignal(str)
    openFolderSig = pyqtSignal(str)
    openFileSig = pyqtSignal(str)

    def __init__(self, job):
        super().__init__()
        self.job_id = job["id"]
        self.setObjectName("downloadCard")
        self.setMinimumHeight(94)
        self.setMaximumHeight(100)
        self.setStyleSheet("""
            QFrame#downloadCard{
                background: #1E2025;
                border: 1px solid #2A2E35;
                border-radius: 12px;
            }
            QFrame#downloadCard:hover{
                border: 1px solid #3A4050;
            }
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14,12,14,12)
        lay.setSpacing(14)

        self.ico = QLabel()
        self.ico.setFixedSize(48,48)
        self.ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ico.setStyleSheet("background: #2A2E35; border-radius: 10px; font-size: 24px; color: #E6E6E6;")
        lay.addWidget(self.ico)

        center = QVBoxLayout()
        center.setSpacing(5)
        self.title = QLabel(job["name"])
        self.title.setStyleSheet("color: #E6E6E6; font-size: 13px; font-weight: 600; background: transparent; border: 0;")
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

        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(8)
        self.b_pause = CardBtn("⏸", "Pause", blue=True)
        self.b_resume = CardBtn("▶", "Resume")
        self.b_stop = CardBtn("■", "Stop")
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
        if ext in (".zip",".rar",".7z",".tar",".gz"): return "📦"
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

        if size and pct<100:
            self.title.setText(f"{name} ({fmt(size)})")
        else:
            self.title.setText(name)
        self.ico.setText(self._icon(name))

        segs = job.get("parts_progress", [])
        if segs and len(segs)>=1:
            self.bar.set_segments(segs)
        else:
            self.bar.set_from_pct(pct, status)

        if status == "running":
            self.speed.setText(f"Speed: {fmt_speed(speed)} | ETA: {fmt_eta(done,size,speed)}")
        elif status == "done":
            self.speed.setText("Completed — click Open File")
        elif status in ("paused","error","waiting","queue paused","scheduled"):
            self.speed.setText(f"Paused — {fmt(done)} / {fmt(size)}" if size else "Paused")
        else:
            self.speed.setText("")

        self.size.setText(f"{fmt(done)} / {fmt(size)} | {pct}%" if size else f"{pct}%")

        # button logic with bigger icons
        if status == "running":
            self.setStyleSheet("QFrame#downloadCard{background: #1E242E; border: 1px solid #4A90E2; border-radius: 12px;}")
            self.b_pause.set_blue(True)
            self.b_pause.setEnabled(True)
            self.b_resume.set_blue(False)
            self.b_resume.setEnabled(False)
            self.b_stop.setEnabled(True)
            # restore labels
            self.b_pause.icon_lbl.setText("⏸")
            self.b_pause.text_lbl.setText("Pause")
            self.b_resume.icon_lbl.setText("▶")
            self.b_resume.text_lbl.setText("Resume")
            self.b_stop.icon_lbl.setText("■")
            self.b_stop.text_lbl.setText("Stop")
            # disconnect/reconnect to avoid duplicate
            try:
                self.b_pause.clicked.disconnect()
            except:
                pass
            try:
                self.b_resume.clicked.disconnect()
            except:
                pass
            self.b_pause.clicked.connect(lambda: self.pauseSig.emit(self.job_id))
            self.b_resume.clicked.connect(lambda: self.resumeSig.emit(self.job_id))
        elif status == "done":
            self.setStyleSheet("QFrame#downloadCard{background: #1E2025; border: 1px solid #2A2E35; border-radius: 12px;}")
            self.b_pause.set_blue(False)
            self.b_pause.setEnabled(True)
            self.b_resume.set_blue(True)
            self.b_resume.setEnabled(True)
            self.b_stop.setEnabled(True)
            self.b_pause.icon_lbl.setText("📁")
            self.b_pause.text_lbl.setText("Open Folder")
            self.b_resume.icon_lbl.setText("▶")
            self.b_resume.text_lbl.setText("Open File")
            self.b_stop.icon_lbl.setText("🗑")
            self.b_stop.text_lbl.setText("Remove")
            try:
                self.b_pause.clicked.disconnect()
            except:
                pass
            try:
                self.b_resume.clicked.disconnect()
            except:
                pass
            try:
                self.b_stop.clicked.disconnect()
            except:
                pass
            self.b_pause.clicked.connect(lambda: self.openFolderSig.emit(self.job_id))
            self.b_resume.clicked.connect(lambda: self.openFileSig.emit(self.job_id))
            self.b_stop.clicked.connect(lambda: self.stopSig.emit(self.job_id))
        else: # paused etc
            self.setStyleSheet("QFrame#downloadCard{background: #1E2025; border: 1px solid #2A2E35; border-radius: 12px;} QFrame#downloadCard:hover{border: 1px solid #3A4050;}")
            self.b_pause.set_blue(False)
            self.b_pause.setEnabled(False)
            self.b_resume.set_blue(True)
            self.b_resume.setEnabled(True)
            self.b_stop.setEnabled(True)
            self.b_pause.icon_lbl.setText("⏸")
            self.b_pause.text_lbl.setText("Pause")
            self.b_resume.icon_lbl.setText("▶")
            self.b_resume.text_lbl.setText("Resume")
            self.b_stop.icon_lbl.setText("■")
            self.b_stop.text_lbl.setText("Stop")
            try:
                self.b_pause.clicked.disconnect()
            except:
                pass
            try:
                self.b_resume.clicked.disconnect()
            except:
                pass
            try:
                self.b_stop.clicked.disconnect()
            except:
                pass
            self.b_pause.clicked.connect(lambda: self.pauseSig.emit(self.job_id))
            self.b_resume.clicked.connect(lambda: self.resumeSig.emit(self.job_id))
            self.b_stop.clicked.connect(lambda: self.stopSig.emit(self.job_id))

# ── Settings Dialog — Exact like reference image 3 ──

class SettingsDialog(QDialog):
    def __init__(self, engine, qsettings, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.qsettings = qsettings
        self.setWindowTitle("Settings - DownloadMaster")
        self.setMinimumSize(860, 560)
        self.resize(880, 600)
        self.setStyleSheet("""
            QDialog{
                background: #1E2025;
            }
            QLabel{
                background: transparent;
                border: 0;
                color: #E6E6E6;
            }
            QFrame{
                background: transparent;
            }
            QFrame#leftPanel{
                background: #15181E;
                border-right: 1px solid #2A2E35;
            }
            QFrame#contentPanel{
                background: #1E2025;
            }
            QFrame#cardBox{
                background: #2A2E35;
                border: 1px solid #3A4050;
                border-radius: 10px;
            }
            QFrame#innerCard{
                background: #1E2025;
                border: 1px solid #2A2E35;
                border-radius: 8px;
            }
            QSpinBox, QComboBox{
                background: #1E2025;
                border: 1px solid #3A4050;
                border-radius: 6px;
                padding: 6px 10px;
                color: #E6E6E6;
                min-height: 22px;
            }
            QSpinBox:focus, QComboBox:focus{
                border: 1px solid #4A90E2;
            }
            QSlider::groove:horizontal{
                height: 6px;
                background: #3A4050;
                border-radius: 3px;
            }
            QSlider::handle:horizontal{
                background: #4A90E2;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal{
                background: #4A90E2;
                border-radius: 3px;
            }
            QCheckBox{
                color: #E6E6E6;
                spacing: 8px;
            }
            QCheckBox::indicator{
                width: 18px;
                height: 18px;
                border: 1px solid #3A4050;
                border-radius: 4px;
                background: #1E2025;
            }
            QCheckBox::indicator:checked{
                background: #4A90E2;
                border: 1px solid #4A90E2;
            }
            QPushButton{
                background: #2A2E35;
                border: 1px solid #3A4050;
                border-radius: 8px;
                padding: 8px 16px;
                color: #E6E6E6;
                font-size: 12px;
            }
            QPushButton:hover{
                background: #353B4A;
                border: 1px solid #4A4F5E;
            }
            QPushButton#primaryBtn{
                background: #4A90E2;
                border: 0;
                color: white;
                font-weight: 600;
            }
            QPushButton#primaryBtn:hover{
                background: #5AA0F2;
            }
        """)

        main = QHBoxLayout(self)
        main.setContentsMargins(0,0,0,0)
        main.setSpacing(0)

        # left panel
        left = QFrame()
        left.setObjectName("leftPanel")
        left.setFixedWidth(200)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(8,12,8,12)
        left_lay.setSpacing(4)

        # top logo
        logo_row = QHBoxLayout()
        logo_icon = QLabel("⬇️")
        logo_icon.setStyleSheet("font-size: 22px; background: #2196F3; border-radius: 6px; padding: 4px;")
        logo_icon.setFixedSize(36,36)
        logo_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_title = QLabel("DownloadMaster\nv2.1")
        logo_title.setStyleSheet("font-size: 11px; color: #A0A5B0;")
        logo_row.addWidget(logo_icon)
        logo_row.addWidget(logo_title)
        logo_row.addStretch()
        left_lay.addLayout(logo_row)
        left_lay.addSpacing(16)

        self.nav_buttons = []
        nav_items = [
            ("General", "⚙️"),
            ("Downloads", "⬇️"),
            ("Connection", "🔗"),
            ("Scheduler", "🕒"),
            ("Interface", "🎨"),
            ("Advanced", "⚙️"),
        ]
        for idx, (name, icon) in enumerate(nav_items):
            btn = QPushButton(f"  {icon}  {name}")
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton{
                    text-align: left;
                    background: transparent;
                    border: 0;
                    border-radius: 8px;
                    padding: 10px 12px;
                    color: #A0A5B0;
                    font-size: 13px;
                }
                QPushButton:hover{
                    background: #252A35;
                    color: #E6E6E6;
                }
                QPushButton:checked{
                    background: #2A2E35;
                    color: #E6E6E6;
                    border-left: 3px solid #4A90E2;
                }
            """)
            btn.clicked.connect(lambda checked, i=idx: self._switch_page(i))
            left_lay.addWidget(btn)
            self.nav_buttons.append(btn)

        left_lay.addStretch()
        main.addWidget(left)

        # right content
        right = QFrame()
        right.setObjectName("contentPanel")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(20,16,20,16)
        right_lay.setSpacing(12)

        # header
        header = QHBoxLayout()
        title = QLabel("Download Settings")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #E6E6E6;")
        header.addWidget(title)
        header.addStretch()
        # window controls mimic
        header.addWidget(QLabel(""))
        right_lay.addLayout(header)

        self.stack = QStackedWidget()
        # pages
        self.stack.addWidget(self._build_general_page())
        self.stack.addWidget(self._build_downloads_page())
        self.stack.addWidget(self._build_connection_page())
        self.stack.addWidget(self._build_scheduler_page())
        self.stack.addWidget(self._build_interface_page())
        self.stack.addWidget(self._build_advanced_page())

        right_lay.addWidget(self.stack, 1)

        # bottom OK Cancel Apply
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("primaryBtn")
        self.btn_ok.setFixedWidth(80)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(80)
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setFixedWidth(80)
        self.btn_ok.clicked.connect(self._apply_and_close)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self._apply)
        bottom.addWidget(self.btn_ok)
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_apply)
        right_lay.addLayout(bottom)

        main.addWidget(right, 1)

        # default to Downloads page like screenshot
        self._switch_page(1)

    def _switch_page(self, idx):
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i==idx)
        self.stack.setCurrentIndex(idx)

    def _build_general_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("General Settings — Customize HDM behavior"))
        lay.addStretch()
        return w

    def _build_downloads_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        # top row: Queue + Scheduler
        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        # Queue Management
        qm = QFrame()
        qm.setObjectName("cardBox")
        qm_lay = QVBoxLayout(qm)
        qm_lay.setContentsMargins(14,12,14,12)
        qm_lay.setSpacing(10)
        qm_title = QLabel("Queue Management")
        qm_title.setStyleSheet("font-size: 14px; font-weight: 700;")
        qm_lay.addWidget(qm_title)

        inner = QFrame()
        inner.setObjectName("innerCard")
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(12,12,12,12)
        inner_lay.setSpacing(10)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Max Simultaneous Downloads:"))
        row1.addStretch()
        self.spin_max = QSpinBox()
        self.spin_max.setRange(1,5)
        self.spin_max.setValue(self.engine.max_concurrent)
        self.spin_max.setFixedWidth(70)
        row1.addWidget(self.spin_max)
        inner_lay.addLayout(row1)

        self.slider_max = QSlider(Qt.Orientation.Horizontal)
        self.slider_max.setRange(1,5)
        self.slider_max.setValue(self.engine.max_concurrent)
        self.slider_max.valueChanged.connect(self.spin_max.setValue)
        self.spin_max.valueChanged.connect(self.slider_max.setValue)
        inner_lay.addWidget(self.slider_max)

        labels = QHBoxLayout()
        labels.addWidget(QLabel("1"))
        labels.addStretch()
        labels.addWidget(QLabel("3"))
        labels.addStretch()
        labels.addWidget(QLabel("5"))
        inner_lay.addLayout(labels)

        inner_lay.addWidget(QLabel("(Default: 3 simultaneously; range 1-5)"))

        btns = QHBoxLayout()
        btns.setSpacing(8)
        b_start = QPushButton("▶  Start Now")
        b_pause = QPushButton("⏸  Pause Queue")
        b_resume = QPushButton("▶  Resume Queue")
        b_start.clicked.connect(lambda: (self.engine.resume_queue(), QMessageBox.information(self, "Queue", "Queue resumed")))
        b_pause.clicked.connect(lambda: (self.engine.pause_queue(), QMessageBox.information(self, "Queue", "Queue paused")))
        b_resume.clicked.connect(lambda: (self.engine.resume_queue(), QMessageBox.information(self, "Queue", "Queue resumed")))
        for b in (b_start, b_pause, b_resume):
            b.setStyleSheet("background: #1E2025; border: 1px solid #3A4050; border-radius: 8px; padding: 8px;")
        btns.addWidget(b_start)
        btns.addWidget(b_pause)
        btns.addWidget(b_resume)
        inner_lay.addLayout(btns)

        qm_lay.addWidget(inner)
        top_row.addWidget(qm, 3)

        # Scheduler top right
        sched = QFrame()
        sched.setObjectName("cardBox")
        sched_lay = QVBoxLayout(sched)
        sched_lay.setContentsMargins(14,12,14,12)
        sched_lay.setSpacing(10)
        sched_title = QLabel("Scheduler")
        sched_title.setStyleSheet("font-size: 14px; font-weight: 700;")
        sched_lay.addWidget(sched_title)

        sched_inner = QFrame()
        sched_inner.setObjectName("innerCard")
        sched_inner_lay = QVBoxLayout(sched_inner)
        sched_inner_lay.setContentsMargins(12,12,12,12)
        sched_inner_lay.setSpacing(10)

        sched_inner_lay.addWidget(QLabel("Download Schedule"))
        self.chk_sched = QCheckBox("Enable Scheduling")
        self.chk_sched.setChecked(self.engine.schedule["enabled"])
        sched_inner_lay.addWidget(self.chk_sched)

        # time rows
        time_row1 = QHBoxLayout()
        time_row1.addWidget(QLabel("Download between:"))
        time_row1.addStretch()
        self.spin_start_h = QSpinBox()
        self.spin_start_h.setRange(0,23)
        self.spin_start_h.setValue(int(self.engine.schedule["start"].split(":")[0]))
        self.spin_start_h.setPrefix("[ ")
        self.spin_start_h.setSuffix(" ]")
        self.spin_start_h.setFixedWidth(70)
        self.spin_start_m = QSpinBox()
        self.spin_start_m.setRange(0,59)
        self.spin_start_m.setValue(int(self.engine.schedule["start"].split(":")[1]) if ":" in self.engine.schedule["start"] else 0)
        self.spin_start_m.setPrefix("[ ")
        self.spin_start_m.setSuffix(" ]")
        self.spin_start_m.setFixedWidth(70)
        time_row1.addWidget(self.spin_start_h)
        time_row1.addWidget(QLabel(":"))
        time_row1.addWidget(self.spin_start_m)
        sched_inner_lay.addLayout(time_row1)

        time_row2 = QHBoxLayout()
        time_row2.addStretch()
        self.spin_stop_h = QSpinBox()
        self.spin_stop_h.setRange(0,23)
        self.spin_stop_h.setValue(int(self.engine.schedule["stop"].split(":")[0]))
        self.spin_stop_h.setPrefix("[ ")
        self.spin_stop_h.setSuffix(" ]")
        self.spin_stop_h.setFixedWidth(70)
        self.spin_stop_m = QSpinBox()
        self.spin_stop_m.setRange(0,59)
        self.spin_stop_m.setValue(int(self.engine.schedule["stop"].split(":")[1]) if ":" in self.engine.schedule["stop"] else 0)
        self.spin_stop_m.setPrefix("[ ")
        self.spin_stop_m.setSuffix(" ]")
        self.spin_stop_m.setFixedWidth(70)
        time_row2.addWidget(self.spin_stop_h)
        time_row2.addWidget(QLabel(":"))
        time_row2.addWidget(self.spin_stop_m)
        sched_inner_lay.addLayout(time_row2)

        sched_lay.addWidget(sched_inner)
        sched_lay.addStretch()
        top_row.addWidget(sched, 2)

        lay.addLayout(top_row)

        # bottom row: App Settings + Scheduler desc
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(14)

        app_set = QFrame()
        app_set.setObjectName("cardBox")
        app_lay = QVBoxLayout(app_set)
        app_lay.setContentsMargins(14,12,14,12)
        app_lay.setSpacing(10)
        app_lay.addWidget(QLabel("Application Settings"))

        app_inner = QFrame()
        app_inner.setObjectName("innerCard")
        app_inner_lay = QHBoxLayout(app_inner)
        app_inner_lay.setContentsMargins(12,12,12,12)
        app_inner_lay.addWidget(QLabel("Language:"))
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["🇬🇧 English", "🇮🇷 فارسی", "🇪🇸 Español"])
        # map to en/fa/es
        cur_lang = self.qsettings.value("lang","en")
        idx_map = {"en":0,"fa":1,"es":2}
        self.combo_lang.setCurrentIndex(idx_map.get(cur_lang,0))
        app_inner_lay.addWidget(self.combo_lang, 1)
        app_lay.addWidget(app_inner)
        app_lay.addStretch()
        bottom_row.addWidget(app_set, 3)

        sched_desc = QFrame()
        sched_desc.setObjectName("cardBox")
        sched_desc_lay = QVBoxLayout(sched_desc)
        sched_desc_lay.setContentsMargins(14,12,14,12)
        sched_desc_lay.addWidget(QLabel("Scheduler"))
        desc_inner = QFrame()
        desc_inner.setObjectName("innerCard")
        desc_inner_lay = QVBoxLayout(desc_inner)
        desc_inner_lay.addWidget(QLabel("Schedule downloads to start/stop within\nthese times daily."))
        sched_desc_lay.addWidget(desc_inner)
        sched_desc_lay.addStretch()
        bottom_row.addWidget(sched_desc, 2)

        lay.addLayout(bottom_row)
        lay.addStretch()
        return w

    def _build_connection_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Connection Settings — Threads, timeout, retry"))
        lay.addStretch()
        return w

    def _build_scheduler_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Scheduler — Set download windows"))
        lay.addStretch()
        return w

    def _build_interface_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Interface — Theme, language"))
        lay.addStretch()
        return w

    def _build_advanced_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Advanced — Categories, throttling"))
        lay.addStretch()
        return w

    def _apply(self):
        max_c = self.spin_max.value()
        self.engine.set_max_concurrent(max_c)
        self.qsettings.setValue("max_concurrent", max_c)

        enabled = self.chk_sched.isChecked()
        start = f"{self.spin_start_h.value():02d}:{self.spin_start_m.value():02d}"
        stop = f"{self.spin_stop_h.value():02d}:{self.spin_stop_m.value():02d}"
        self.engine.set_schedule(enabled, start, stop)
        self.qsettings.setValue("sched_enabled", enabled)
        self.qsettings.setValue("sched_start", start)
        self.qsettings.setValue("sched_stop", stop)

        lang_idx = self.combo_lang.currentIndex()
        lang_map = {0:"en",1:"fa",2:"es"}
        self.qsettings.setValue("lang", lang_map.get(lang_idx,"en"))

    def _apply_and_close(self):
        self._apply()
        self.accept()

# ── About Dialog — Exact like reference image 4 ──

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About HDM Download Manager")
        self.setFixedSize(480, 440)
        self.setStyleSheet("""
            QDialog{
                background: #0F1115;
            }
            QLabel{
                background: transparent;
                border: 0;
            }
            QFrame#card{
                background: #1E242E;
                border: 1px solid #2A2E35;
                border-radius: 16px;
            }
            QPushButton{
                background: #4A90E2;
                border: 0;
                border-radius: 8px;
                color: white;
                font-weight: 600;
                padding: 8px 16px;
            }
            QPushButton:hover{
                background: #5AA0F2;
            }
            QLabel#link{
                color: #4A90E2;
                text-decoration: underline;
            }
            QLabel#link:hover{
                color: #5AA0F2;
            }
        """)

        main = QVBoxLayout(self)
        main.setContentsMargins(20,20,20,20)
        main.setSpacing(0)

        # header with X
        header = QHBoxLayout()
        header.addWidget(QLabel("About HDM Download Manager"))
        header.addStretch()
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28,28)
        btn_close.setStyleSheet("background: #2A2E35; border-radius: 14px; color: #A0A5B0;")
        btn_close.clicked.connect(self.reject)
        header.addWidget(btn_close)
        main.addLayout(header)
        main.addSpacing(12)

        card = QFrame()
        card.setObjectName("card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(24,24,24,24)
        card_lay.setSpacing(12)
        card_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # logo
        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # try load logo.png
        logo_path = HERE / "web" / "logo.png"
        if logo_path.exists():
            pix = QPixmap(str(logo_path))
            if not pix.isNull():
                logo.setPixmap(pix.scaled(120, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText("🌐 HDM")
            logo.setStyleSheet("font-size: 36px; font-weight: 800; color: #4A90E2;")
        card_lay.addWidget(logo)

        title = QLabel("HDM Download Manager")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #E6E6E6;")
        card_lay.addWidget(title)

        # badge + version row
        badge_row = QHBoxLayout()
        badge_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge = QLabel("FREE EDITION Lifetime")
        badge.setStyleSheet("background: #4CAF50; color: white; border-radius: 12px; padding: 4px 12px; font-size: 12px; font-weight: 700;")
        ver = QLabel(f"Version {VERSION}")
        ver.setStyleSheet("color: #8B90A0; font-size: 12px; margin-left: 10px;")
        badge_row.addWidget(badge)
        badge_row.addWidget(ver)
        card_lay.addLayout(badge_row)

        card_lay.addSpacing(12)

        dev = QLabel("Developed by:  HAMI SMART SYSTEMS")
        dev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev.setStyleSheet("color: #E6E6E6; font-size: 13px;")
        card_lay.addWidget(dev)

        copyr = QLabel("© 2023 HAMI SMART SYSTEMS. All Rights Reserved.")
        copyr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyr.setStyleSheet("color: #8B90A0; font-size: 11px;")
        card_lay.addWidget(copyr)

        card_lay.addSpacing(12)

        links = QHBoxLayout()
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links.setSpacing(16)
        for txt, url in [("Visit Website","https://hamidesigns.shop"), ("Check for Updates","https://github.com/hamismartsystems/Hami-Download-Manager/releases"), ("Licensing Terms","https://github.com/hamismartsystems/Hami-Download-Manager/blob/main/LICENSE")]:
            lbl = QLabel(f"<a href='{url}' style='color:#4A90E2; text-decoration: underline;'>{txt}</a>")
            lbl.setOpenExternalLinks(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            links.addWidget(lbl)
        card_lay.addLayout(links)

        main.addWidget(card, 1)

        main.addSpacing(16)
        ok_row = QHBoxLayout()
        ok_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedSize(90, 36)
        ok_btn.clicked.connect(self.accept)
        ok_row.addWidget(ok_btn)
        main.addLayout(ok_row)

# ── New Download Dialog with auto-paste ──

class NewDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Download")
        self.setFixedSize(520, 160)
        self.setStyleSheet("""
            QDialog{background: #1E2025;}
            QLabel{color: #E6E6E6; background: transparent; border: 0;}
            QLineEdit{background: #2A2E35; border: 1px solid #3A4050; border-radius: 8px; padding: 10px; color: #E6E6E6;}
            QLineEdit:focus{border: 1px solid #4A90E2;}
            QPushButton{background: #2A2E35; border: 1px solid #3A4050; border-radius: 8px; padding: 8px 16px; color: #E6E6E6;}
            QPushButton:hover{background: #353B4A;}
            QPushButton#primary{background: #4A90E2; border: 0; color: white; font-weight: 600;}
            QPushButton#primary:hover{background: #5AA0F2;}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16,16,16,16)
        lay.setSpacing(12)
        lay.addWidget(QLabel("Enter URL:"))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("https://...")
        # auto-paste from clipboard
        try:
            clip = QApplication.clipboard().text()
            if clip and clip.strip().lower().startswith(("http://","https://")):
                self.edit.setText(clip.strip())
                self.edit.selectAll()
        except:
            pass
        lay.addWidget(self.edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        ok = QPushButton("Download")
        ok.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)

        self.edit.setFocus()

    def get_url(self):
        return self.edit.text().strip()

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
        self.resize(1220, 740)
        self.setMinimumSize(1040, 640)
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

        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar.setFixedHeight(84)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12,8,12,8)
        tb.setSpacing(6)

        self.t_new = ToolBtn("📄", "New+")
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
        sep.setFixedHeight(44)
        tb.addWidget(sep)
        tb.addWidget(self.t_settings)
        tb.addStretch()

        search_wrap = QFrame()
        search_wrap.setObjectName("searchWrap")
        search_wrap.setFixedSize(240, 40)
        search_wrap.setStyleSheet("QFrame#searchWrap{background: #2A2E35; border: 1px solid #3A4050; border-radius: 10px;}")
        s_lay = QHBoxLayout(search_wrap)
        s_lay.setContentsMargins(12,0,10,0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search")
        self.search.setStyleSheet("background: transparent; border: 0; color: #E6E6E6; font-size: 13px;")
        self.search_icon = QLabel("🔍")
        self.search_icon.setStyleSheet("background: transparent; border: 0; color: #6B7280; font-size: 16px;")
        s_lay.addWidget(self.search,1)
        s_lay.addWidget(self.search_icon)
        tb.addWidget(search_wrap)

        v.addWidget(toolbar)

        content = QHBoxLayout()
        content.setContentsMargins(0,0,0,0)
        content.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_wrap = QWidget()
        self.list_wrap.setObjectName("scrollContent")
        self.list_lay = QVBoxLayout(self.list_wrap)
        self.list_lay.setContentsMargins(14,14,14,14)
        self.list_lay.setSpacing(12)
        self.list_lay.addStretch()
        self.scroll.setWidget(self.list_wrap)
        content.addWidget(self.scroll, 1)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(310)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16,16,16,16)
        side.setSpacing(16)

        lbl_cur = QLabel("Currently Downloading")
        lbl_cur.setStyleSheet("color: #E6E6E6; font-size: 13px; font-weight: 600; background: transparent; border: 0;")
        side.addWidget(lbl_cur)

        self.graph = SpeedGraph()
        side.addWidget(self.graph)

        conn = QFrame()
        conn.setObjectName("connBox")
        cl = QVBoxLayout(conn)
        cl.setContentsMargins(14,12,14,12)
        cl.setSpacing(8)
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

        det = QFrame()
        det.setObjectName("detailsBox")
        dl = QVBoxLayout(det)
        dl.setContentsMargins(14,12,14,12)
        dl.setSpacing(8)
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
        a_about.triggered.connect(self._open_about)
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

    def _open_folder(self, path=None):
        p = str(path or self.dl_dir)
        try:
            if sys.platform == "win32":
                os.startfile(p)
            else:
                subprocess.Popen(["xdg-open", p])
        except Exception:
            webbrowser.open(f"file://{p}")

    def _open_file(self, path):
        p = str(path)
        try:
            if sys.platform == "win32":
                os.startfile(p)
            else:
                subprocess.Popen(["xdg-open", p])
        except Exception:
            webbrowser.open(f"file://{p}")

    def _add_dialog(self):
        dlg = NewDownloadDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            url = dlg.get_url()
            if url:
                try:
                    self.engine.add(url)
                    self.refresh()
                except Exception as e:
                    QMessageBox.warning(self, "HDM", str(e))

    def _remove_completed(self):
        for j in self.engine.list():
            if j["status"] == "done":
                self.engine.cancel(j["id"])
        self.refresh()

    def _open_settings(self):
        dlg = SettingsDialog(self.engine, self.settings, self)
        dlg.exec()
        self.refresh()

    def _open_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

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
                card.openFolderSig.connect(lambda jid: self._handle_open_folder(jid))
                card.openFileSig.connect(lambda jid: self._handle_open_file(jid))
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

    def _handle_open_folder(self, jid):
        job = self.engine.get(jid)
        if job and job.get("folder"):
            self._open_folder(job["folder"])
        else:
            self._open_folder()

    def _handle_open_file(self, jid):
        job = self.engine.get(jid)
        if job and job.get("path"):
            self._open_file(job["path"])
        else:
            QMessageBox.information(self, "HDM", "File not found")

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
