#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HDM — HAMI Download Manager v1.0.1 — desktop application window (PyQt6)."""
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt6.QtCore import Qt, QTimer, QSettings, QTime, QSize
from PyQt6.QtGui import QAction, QIcon, QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QProgressBar, QLabel,
    QMessageBox, QMenu, QFileDialog, QGroupBox, QFormLayout, QDialog,
    QDialogButtonBox, QCheckBox, QHeaderView, QAbstractItemView, QSystemTrayIcon,
    QSpinBox, QTimeEdit, QVBoxLayout as QV, QTextBrowser,
)

import hdm_license as lic
import hdm_activation as act
from hdm_engine import Engine
import hdm_server

VERSION = "1.0.3"
ORG = "HAMI SMART SYSTEMS"
APP = "HAMI Download Manager (HDM)"
STATE_DIR = Path(os.environ.get("HDM_HOME") or Path.home() / ".hami-download-manager")
STATE_DIR.mkdir(parents=True, exist_ok=True)
JOBS_FILE = STATE_DIR / "jobs.json"
CRASH_LOG = STATE_DIR / "crash.log"

T = {
    "en": {
        "dir": Qt.LayoutDirection.LeftToRight,
        "file": "&File", "open_folder": "Open Downloads Folder", "change_folder": "Choose Downloads Folder…",
        "startup": "Start with Windows", "exit": "Exit",
        "settings": "&Settings", "options": "Options…", "language": "Language", "help": "&Help",
        "website": "Website", "about": "About HDM", "activate_menu": "Activate license…",
        "url_ph": "Paste or copy a link — click here to read the clipboard", "add": "Add Download",
        "cols": ["File", "Size", "Parts", "Progress", "Speed", "Status"],
        "pause": "Pause", "resume": "Resume", "remove": "Remove", "clear": "Clear Finished",
        "up": "Up", "down": "Down",
        "queue": "Download queue", "queue_pause": "Pause Queue", "queue_resume": "Resume Queue",
        "start_now": "Start Now", "queue_state": "Queue: %d running (max %d)",
        "q_running": "Queue: running", "q_paused": "Queue: paused",
        "q_waiting": "Queue: waiting for scheduled time (%s – %s)",
        "no_sel": "Select a download first.",
        "trial_badge": "TRIAL — %d day(s) left, full speed",
        "trial_today": "TRIAL — last day",
        "expired_badge": "TRIAL ENDED — speed limited to 150 KB/s",
        "act_badge": "ACTIVATED — %s",
        "act_badge_days": "ACTIVATED — %s · %d days left",
        "activate_btn": "Activate…",
        "opt_title": "HDM Options", "opt_concurrent": "Simultaneous downloads (1–5)",
        "opt_categorize": "Sort files into folders (Programs, Video, Compressed, Photo, …)",
        "opt_schedule": "Download only between", "opt_folder": "Downloads folder",
        "opt_browse": "Browse…", "opt_queue": "Queue",
        "opt_resume_all": "Continue all unfinished downloads",
        "opt_auto_resume": "Continue unfinished downloads when HDM starts",
        "clip_auto": "Start download automatically when a link is copied",
        "clip_hint": "Copied link detected — press Add to start",
        "clip_added": "Added from clipboard: %s",
        "about_title": "About HDM",
        "about_text": "<h3>HAMI Download Manager (HDM) v%s</h3>"
                      "<p>Fast download manager — every file is split into parts, "
                      "downloaded in parallel and joined into one file.</p>"
                      "<p>%s</p>",
        "about_state": "License: <b>%s</b>",
        "about_owner": "Licensed to: %s",
        "about_expires": "Expires: %s",
        "about_left": "Time remaining: <b>%s</b>",
        "about_machine": "Machine ID: %s",
        "about_copy": "Copy ID",
        "st_active": "ACTIVE",
        "st_lifetime": "ACTIVE — Lifetime",
        "st_plan": "ACTIVE — %s",
        "st_trial": "TRIAL (%d days left)",
        "st_trial_end": "TRIAL ENDED",
        "st_other_pc": "NOT VALID ON THIS COMPUTER",
        "btn_activate": "Activate…",
        "btn_deactivate": "Remove license",
        "warn7_title": "License expiring",
        "warn7": "Your HDM license expires in %d day(s) (%s).\n\nRenew it now so downloading continues at full speed.",
        "warn1_title": "License expires tomorrow",
        "warn1": "Your HDM license expires on %s — tomorrow.\n\nAfter that the speed is limited until you renew.",
        "warn_end": "Your license has expired. Speed is limited to 150 KB/s. Please renew.",
        "act_title": "Activate HDM",
        "act_name": "Name on the license (exactly as issued)",
        "act_key": "License key  HG-XXXX-XXXX-XXXX-XXXX-XXXX",
        "act_ok": "License activated — %s. Thank you.",
        "act_note": "This license is locked to this computer. After reinstalling Windows "
                    "you can activate it again on the same machine with the same name and key.",
        "exit_title": "Quit HDM", "exit_text": "Close HDM and stop all downloads?",
        "tray_show": "Show HDM", "tray_quit": "Quit", "tray_msg": "HDM is running in the system tray.",
        "crash_title": "Unexpected error",
        "crash_text": "An unexpected error occurred. Details were written to:\n%s",
    },
    "fa": {
        "dir": Qt.LayoutDirection.RightToLeft,
        "file": "پرونده", "open_folder": "باز کردن پوشهٔ دانلودها", "change_folder": "انتخاب پوشهٔ دانلودها…",
        "startup": "اجرا با بالا آمدن ویندوز", "exit": "خروج",
        "settings": "تنظیمات", "options": "گزینه‌ها…", "language": "زبان", "help": "راهنما",
        "website": "وب‌سایت", "about": "درباره HDM", "activate_menu": "فعال‌سازی لایسنس…",
        "url_ph": "لینک را کپی کنید و اینجا کلیک کنید تا خوانده شود", "add": "افزودن دانلود",
        "cols": ["فایل", "حجم", "تکه‌ها", "پیشرفت", "سرعت", "وضعیت"],
        "pause": "توقف", "resume": "ادامه", "remove": "حذف", "clear": "پاک کردن کامل‌شده‌ها",
        "up": "بالا", "down": "پایین",
        "queue": "صف دانلود", "queue_pause": "توقف صف", "queue_resume": "ادامهٔ صف",
        "start_now": "شروع همین حالا", "queue_state": "صف: %d در حال دانلود (حداکثر %d)",
        "q_running": "صف: در حال دانلود", "q_paused": "صف: متوقف",
        "q_waiting": "صف: منتظر زمان برنامه‌ریزی‌شده (%s تا %s)",
        "no_sel": "ابتدا یک دانلود را انتخاب کنید.",
        "trial_badge": "نسخهٔ آزمایشی — %d روز باقی‌مانده (سرعت کامل)",
        "trial_today": "نسخهٔ آزمایشی — آخرین روز",
        "expired_badge": "پایان دورهٔ آزمایشی — سرعت محدود به ۱۵۰ کیلوبایت/ثانیه",
        "act_badge": "فعال‌شده — %s",
        "act_badge_days": "فعال‌شده — %s · %d روز باقی‌مانده",
        "activate_btn": "فعال‌سازی…",
        "opt_title": "تنظیمات HDM", "opt_concurrent": "تعداد دانلود همزمان (۱ تا ۵)",
        "opt_categorize": "دسته‌بندی فایل‌ها در پوشه‌ها (برنامه‌ها، ویدیو، فشرده، تصویر و …)",
        "opt_schedule": "دانلود فقط بین", "opt_folder": "پوشهٔ دانلودها", "opt_browse": "انتخاب…",
        "opt_queue": "صف",
        "opt_resume_all": "ادامهٔ همهٔ دانلودهای ناتمام",
        "opt_auto_resume": "با اجرای برنامه، دانلودهای ناتمام ادامه یابند",
        "clip_auto": "با کپی شدن لینک، دانلود خودکار شروع شود",
        "clip_hint": "لینک کپی‌شده پیدا شد — افزودن را بزنید",
        "clip_added": "از کلیپ‌بورد افزوده شد: %s",
        "about_title": "درباره HDM",
        "about_text": "<h3>HAMI Download Manager (HDM) v%s</h3>"
                      "<p>مدیریت دانلود سریع — هر فایل به چند تکه تقسیم شده، همزمان دریافت "
                      "و در پایان به یک فایل کامل تبدیل می‌شود.</p><p>%s</p>",
        "about_state": "وضعیت لایسنس: <b>%s</b>",
        "about_owner": "فعال‌شده برای: %s",
        "about_expires": "تاریخ پایان: %s",
        "about_left": "زمان باقی‌مانده: <b>%s</b>",
        "about_machine": "شناسهٔ دستگاه: %s",
        "about_copy": "کپی شناسه",
        "st_active": "فعال",
        "st_lifetime": "فعال — مادام‌العمر",
        "st_plan": "فعال — %s",
        "st_trial": "آزمایشی (%d روز باقی‌مانده)",
        "st_trial_end": "پایان دورهٔ آزمایشی",
        "st_other_pc": "روی این دستگاه معتبر نیست",
        "btn_activate": "فعال‌سازی…",
        "btn_deactivate": "حذف لایسنس",
        "warn7_title": "نزدیک شدن پایان لایسنس",
        "warn7": "لایسنس HDM شما %d روز دیگر تمام می‌شود (%s).\n\nبرای ادامهٔ سرعت کامل، آن را تمدید کنید.",
        "warn1_title": "پایان لایسنس، فردا",
        "warn1": "لایسنس شما فردا (%s) تمام می‌شود.\n\nبعد از آن سرعت محدود می‌شود تا تمدید کنید.",
        "warn_end": "لایسنس شما به پایان رسید. سرعت محدود به ۱۵۰ کیلوبایت/ثانیه است؛ لطفاً تمدید کنید.",
        "act_title": "فعال‌سازی HDM",
        "act_name": "نام درج‌شده روی لایسنس (دقیقاً همان‌طور که صادر شده)",
        "act_key": "کلید لایسنس  HG-XXXX-XXXX-XXXX-XXXX-XXXX",
        "act_ok": "لایسنس فعال شد — %s. سپاسگزاریم.",
        "act_note": "این لایسنس به همین دستگاه قفل می‌شود. بعد از نصب دوبارهٔ ویندوز، "
                    "روی همین سیستم با همان نام و کلید دوباره فعال می‌شود.",
        "exit_title": "خروج از HDM", "exit_text": "HDM بسته شود و دانلودها متوقف گردند؟",
        "tray_show": "نمایش HDM", "tray_quit": "خروج", "tray_msg": "HDM در نوار سیستم در حال اجراست.",
        "crash_title": "خطای پیش‌بینی‌نشده",
        "crash_text": "خطای پیش‌بینی‌نشده‌ای رخ داد. جزئیات در این فایل ثبت شد:\n%s",
    },
}


def fmt(n):
    n = float(n or 0)
    for unit, div in (("GB", 1073741824), ("MB", 1048576), ("KB", 1024)):
        if n >= div:
            return "%.1f %s" % (n / div, unit)
    return "%d B" % n


def countdown(seconds):
    seconds = max(0, int(seconds))
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    if d:
        return "%d days  %02d:%02d:%02d" % (d, h, m, s)
    return "%02d:%02d:%02d" % (h, m, s)


# ── a URL box that reads the clipboard when clicked ────────────────────────
class UrlBox(QLineEdit):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def mousePressEvent(self, e):
        try:
            self.owner.check_clip_now()
        except Exception:
            pass
        super().mousePressEvent(e)

    def focusInEvent(self, e):
        try:
            self.owner.check_clip_now()
        except Exception:
            pass
        super().focusInEvent(e)


class ActivateDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        t = T[parent.lang]
        self.p = parent
        self.setWindowTitle(t["act_title"])
        self.setStyleSheet(parent.qss())
        self.setMinimumWidth(600)
        self.resize(620, 210)
        f = QFormLayout(self)
        # make the input fields expand to show the full key
        try:
            f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        except Exception:
            try:
                f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # older PyQt6
            except Exception:
                pass
        try:
            f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        except Exception:
            pass
        self.name = QLineEdit()
        self.name.setPlaceholderText(t["act_name"])
        self.name.setMinimumWidth(380)
        self.name.setClearButtonEnabled(True)
        self.key = QLineEdit()
        # short placeholder so the real key is fully visible
        self.key.setPlaceholderText("HG-XXXX-XXXX-XXXX-XXXX-XXXX")
        self.key.setMinimumWidth(380)
        self.key.setClearButtonEnabled(True)
        # monospace so the whole license is readable
        try:
            self.key.setStyleSheet(
                "font-family: Consolas, 'Courier New', monospace;"
                " letter-spacing:0.6px; font-size:13px;"
            )
        except Exception:
            pass
        note = QLabel(t["act_note"])
        note.setWordWrap(True)
        note.setStyleSheet("color:#8aa0b8;font-size:11px")
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.do_activate)
        btns.rejected.connect(self.reject)
        f.addRow(t["act_name"], self.name)
        f.addRow(t["act_key"], self.key)
        f.addRow(note)
        f.addRow(btns)

    def do_activate(self):
        t = T[self.p.lang]
        ok, msg, _mode = act.activate(self.key.text(), self.name.text())
        if ok:
            QMessageBox.information(self, APP, t["act_ok"] % act.status()["plan"])
            self.p.after_activation()
            self.accept()
        else:
            QMessageBox.warning(self, APP, msg)


class AboutDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.p = parent
        t = T[parent.lang]
        self.setWindowTitle(t["about_title"])
        self.setStyleSheet(parent.qss())
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(14)

        # Pro header with icon
        header = QWidget()
        header.setObjectName("badgeCard")
        hv = QVBoxLayout(header)
        hv.setContentsMargins(16, 16, 16, 16)
        hv.setSpacing(8)
        title_lbl = QLabel("HDM — HAMI Download Manager")
        title_lbl.setStyleSheet("font-size:18px; font-weight:800; color:#E6EDF3; letter-spacing:0.3px;")
        sub_lbl = QLabel("FREE EDITION v%s • Fast segmented downloader • HAMI SMART SYSTEMS" % VERSION)
        sub_lbl.setStyleSheet("font-size:12px; color:#8B949E;")
        sub_lbl.setWordWrap(True)
        hv.addWidget(title_lbl)
        hv.addWidget(sub_lbl)
        v.addWidget(header)

        self.title = QTextBrowser()
        self.title.setOpenExternalLinks(True)
        self.title.setHtml(t["about_text"] % (VERSION, ORG))
        self.title.setFixedHeight(110)
        self.title.setStyleSheet("background:#161B22; border:1px solid #21262D; border-radius:10px; padding:8px;")
        v.addWidget(self.title)

        self.state = QLabel()
        self.state.setStyleSheet(
            "font-size:14px;font-weight:700;color:#56D364; background:#1F3A2E; "
            "border:1px solid #2EA043; border-radius:8px; padding:8px 12px;"
        )
        v.addWidget(self.state)

        self.owner = QLabel()
        self.expires = QLabel()
        self.left = QLabel()
        for w in (self.owner, self.expires, self.left):
            w.setStyleSheet("font-size:13px;color:#C9D1D9; background:#161B22; border:1px solid #21262D; border-radius:8px; padding:8px 12px;")
            w.setWordWrap(True)
            v.addWidget(w)

        row = QHBoxLayout()
        self.actinfo = QLabel()
        self.actinfo.setStyleSheet("font-size:11px;color:#8aa0b8")
        v.addWidget(self.actinfo)
        self.machine = QLabel()
        self.machine.setStyleSheet("font-size:11px;color:#8aa0b8")
        self.copy = QPushButton(t["about_copy"])
        self.copy.clicked.connect(
            lambda: QApplication.clipboard().setText(act.machine_fingerprint()))
        row.addWidget(self.machine, 1)
        row.addWidget(self.copy)
        v.addLayout(row)

        brow = QHBoxLayout()
        self.act_btn = QPushButton(t["btn_activate"])
        self.act_btn.setObjectName("accent")
        self.act_btn.clicked.connect(self.open_activate)
        self.deact_btn = QPushButton(t["btn_deactivate"])
        self.deact_btn.clicked.connect(self.remove_license)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        brow.addWidget(self.act_btn)
        brow.addWidget(self.deact_btn)
        brow.addStretch(1)
        brow.addWidget(close)
        v.addLayout(brow)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def state_text(self):
        t = T[self.p.lang]
        s = act.status()
        if s["licensed"]:
            if s["lifetime"]:
                return t["st_lifetime"]
            return t["st_plan"] % (s["plan_fa"] if self.p.lang == "fa" else s["plan"])
        if s["reason"]:
            return t["st_other_pc"]
        if s["trial_active"]:
            return t["st_trial"] % max(1, -(-s["trial_left_sec"] // 86400))
        return t["st_trial_end"]

    def refresh(self):
        t = T[self.p.lang]
        s = act.status()
        self.state.setText(t["about_state"] % self.state_text())
        self.owner.setText(t["about_owner"] % s["name"] if s["name"] else "")
        if s["licensed"] and not s["lifetime"]:
            self.expires.setText(t["about_expires"] %
                                 datetime.fromtimestamp(s["expires_at"]).strftime("%Y-%m-%d"))
            self.left.setText(t["about_left"] % countdown(s["expires_at"] - time.time()))
        elif s["licensed"]:
            self.expires.setText("")
            self.left.setText(t["about_left"] % "∞")
        else:
            self.expires.setText("")
            self.left.setText(t["about_left"] % countdown(s["trial_left_sec"]))
        self.machine.setText(t["about_machine"] % act.machine_fingerprint())
        src = s.get("source", "offline")
        if src == "online":
            last = time.strftime("%Y-%m-%d %H:%M", time.localtime(s.get("last_check") or 0))
            self.actinfo.setText("Verified with the activation server · last check: %s" % last)
        elif s.get("licensed"):
            self.actinfo.setText("Verified on this computer (offline copy).")
        else:
            self.actinfo.setText("")
        self.act_btn.setVisible(not s["licensed"])
        self.deact_btn.setVisible(bool(s["licensed"]))

    def open_activate(self):
        dlg = ActivateDialog(self.p)
        dlg.exec()
        self.refresh()

    def remove_license(self):
        t = T[self.p.lang]
        box = QMessageBox(self)
        box.setWindowTitle(t["btn_deactivate"])
        box.setText("Remove this license from this computer?")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if box.exec() == QMessageBox.StandardButton.Yes:
            act.deactivate()
            self.p.after_activation()
            self.refresh()


class OptionsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.p = parent
        t = T[parent.lang]
        self.setWindowTitle(t["opt_title"])
        self.setStyleSheet(parent.qss())
        f = QFormLayout(self)

        self.spin = QSpinBox()
        self.spin.setRange(1, 5)
        self.spin.setValue(parent.engine.max_concurrent)
        f.addRow(t["opt_concurrent"], self.spin)

        self.cat = QCheckBox()
        self.cat.setChecked(parent.engine.categorize)
        f.addRow(t["opt_categorize"], self.cat)

        self.clip = QCheckBox()
        self.clip.setChecked(parent.clip_auto)
        f.addRow(t["clip_auto"], self.clip)

        row = QHBoxLayout()
        self.sched = QCheckBox()
        self.sched.setChecked(parent.engine.schedule.get("enabled", False))
        self.t1, self.t2 = QTimeEdit(), QTimeEdit()
        for w in (self.t1, self.t2):
            w.setDisplayFormat("HH:mm")
        self.t1.setTime(self._qtime(parent.engine.schedule.get("start", "00:00")))
        self.t2.setTime(self._qtime(parent.engine.schedule.get("stop", "06:00")))
        row.addWidget(self.sched)
        row.addWidget(self.t1)
        row.addWidget(QLabel("–"))
        row.addWidget(self.t2)
        row.addStretch(1)
        f.addRow(t["opt_schedule"], row)

        # queue controls — also available here
        qbox = QGroupBox(t["opt_queue"])
        qv = QVBoxLayout(qbox)
        qrow = QHBoxLayout()
        b_resume = QPushButton(t["queue_resume"])
        b_pause = QPushButton(t["queue_pause"])
        b_start = QPushButton(t["start_now"])
        b_start.setObjectName("accent")
        b_resume.clicked.connect(lambda: (parent.engine.resume_queue(), parent.refresh()))
        b_pause.clicked.connect(lambda: (parent.engine.pause_queue(), parent.refresh()))
        b_start.clicked.connect(lambda: (parent.engine.start_now(), parent.refresh()))
        for b in (b_resume, b_pause, b_start):
            qrow.addWidget(b)
        qv.addLayout(qrow)
        self.auto_resume = QCheckBox()
        self.auto_resume.setChecked(
            str(parent.settings.value("auto_resume", True)).lower() == "true")
        qv.addWidget(self.auto_resume)
        self.auto_resume.setText(t["opt_auto_resume"])
        self.resume_all = QCheckBox()
        self.resume_all.setChecked(True)
        qv.addWidget(self.resume_all)
        self.resume_all.setText(t["opt_resume_all"])
        f.addRow(qbox)

        frow = QHBoxLayout()
        self.folder = QLineEdit(str(parent.dl_dir))
        b = QPushButton(t["opt_browse"])
        b.clicked.connect(self.browse)
        frow.addWidget(self.folder, 1)
        frow.addWidget(b)
        f.addRow(t["opt_folder"], frow)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        f.addRow(btns)

    @staticmethod
    def _qtime(v):
        try:
            h, m = str(v).split(":")
            return QTime(int(h), int(m))
        except Exception:
            return QTime(0, 0)

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "", self.folder.text())
        if d:
            self.folder.setText(d)

    def accept(self):
        self.p.engine.set_max_concurrent(self.spin.value())
        self.p.engine.categorize = self.cat.isChecked()
        self.p.clip_auto = self.clip.isChecked()
        self.p.engine.set_schedule(self.sched.isChecked(),
                                   self.t1.time().toString("HH:mm"),
                                   self.t2.time().toString("HH:mm"))
        self.p.settings.setValue("auto_resume", self.auto_resume.isChecked())
        d = self.folder.text().strip()
        if d and d != str(self.p.dl_dir):
            self.p.dl_dir = Path(d)
            self.p.dl_dir.mkdir(parents=True, exist_ok=True)
            self.p.engine.dest_dir = self.p.dl_dir
            self.p.settings.setValue("dl_dir", d)
        if self.resume_all.isChecked():
            self.p.engine.start_now()
        self.p.save_prefs()
        self.p.refresh()
        super().accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG, "HDM")
        self.lang = self.settings.value("lang", "en")
        if self.lang not in T:
            self.lang = "en"
        dl = self.settings.value("dl_dir", "")
        self.dl_dir = Path(dl) if dl else Path.home() / "Downloads" / "HDM"
        self.dl_dir.mkdir(parents=True, exist_ok=True)

        cat = str(self.settings.value("categorize", True)).lower() not in ("false", "0")
        conc = int(self.settings.value("max_concurrent", 3) or 3)
        self.engine = Engine(self.dl_dir, throttle_fn=lambda: act.status()["throttle_bps"],
                             max_concurrent=conc, categorize=cat, state_path=str(JOBS_FILE))
        self.engine.set_schedule(
            str(self.settings.value("sched_enabled", False)).lower() == "true",
            str(self.settings.value("sched_start", "00:00")),
            str(self.settings.value("sched_stop", "06:00")))
        self.engine.load_state(JOBS_FILE)

        self.rows = {}
        self.tray_notified = False
        self.clip_auto = str(self.settings.value("clip_auto", False)).lower() == "true"
        self._last_clip = ""
        self._last_clip_filled = ""
        self._save_tick = 0

        self.setWindowTitle("%s v%s — FREE EDITION" % (APP, VERSION))
        self.setWindowIcon(self.app_icon())
        self.resize(1080, 720)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(self.qss())

        self._build_ui()
        self._build_menu()
        self._build_tray()

        hdm_server.start_server(self.engine, self.dl_dir, version=VERSION)

        self.clipboard = QApplication.clipboard()
        try:
            self.clipboard.dataChanged.connect(self.clip_changed)
        except Exception:
            pass
        QTimer.singleShot(600, lambda: self.clip_changed(startup=True))

        if str(self.settings.value("auto_resume", True)).lower() == "true" \
                and self.engine.unfinished():
            QTimer.singleShot(1500, self.engine.resume_queue)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        lic.machine_parts()          # identify the PC in the background, never on a click
        self.timer.start(1000)
        self.apply_lang(self.lang)
        self.refresh()
        self._start_background_recheck()

    def _start_background_recheck(self):
        """Once a day: confirm the license with the activation server."""
        def work():
            try:
                rec = act._read_receipt()
                if not rec:
                    return
                if time.time() - int(rec.get("last_check") or 0) < 86400:
                    return
                act.recheck()
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    # ── UI ────────────────────────────────────────────────────────────────
    def app_icon(self):
        base = Path(getattr(sys, "_MEIPASS", HERE))
        for name in ("hdm.ico", "hdm-bmp.ico"):
            p = base / name
            if p.exists():
                return QIcon(str(p))
        p = HERE / "web" / "logo.png"
        return QIcon(str(p)) if p.exists() else QIcon()

    @staticmethod
    def qss():
        return """
        /* ── HDM Pro Dark — GitHub-inspired + HAMI green ── */
        QMainWindow, QWidget { background:#0D1117; color:#E6EDF3; font-family:'Segoe UI', Inter, sans-serif; font-size:13px; }
        QToolTip { background:#161B22; color:#E6EDF3; border:1px solid #30363D; border-radius:8px; padding:6px 10px; }

        QLineEdit, QSpinBox, QTimeEdit {
            background:#161B22; border:1px solid #30363D; border-radius:10px;
            padding:10px 14px; color:#E6EDF3; selection-background-color:#00A86B;
        }
        QLineEdit:focus, QSpinBox:focus, QTimeEdit:focus {
            border:1px solid #00A86B; background:#1C2128;
        }
        QLineEdit::placeholder { color:#6E7681; }

        QPushButton {
            background:#21262D; color:#C9D1D9; border:1px solid #30363D;
            border-radius:10px; padding:9px 18px; font-weight:500;
        }
        QPushButton:hover { background:#30363D; border-color:#8B949E; color:#E6EDF3; }
        QPushButton:pressed { background:#21262D; }
        QPushButton:disabled { color:#484F58; border-color:#21262D; background:#161B22; }

        QPushButton#accent {
            background:#238636; color:white; border:0; font-weight:600; letter-spacing:0.2px;
        }
        QPushButton#accent:hover { background:#2EA043; }
        QPushButton#accent:pressed { background:#238636; }

        QPushButton#ghost {
            background:transparent; border:1px solid #30363D; color:#8B949E;
        }
        QPushButton#ghost:hover { background:#161B22; color:#E6EDF3; border-color:#484F58; }

        /* Table — modern card */
        QTableWidget {
            background:#0D1117; border:1px solid #21262D; border-radius:12px;
            gridline-color:#21262D; selection-background-color:#1F3A2E;
            alternate-background-color:#0D1117; outline:0;
        }
        QTableWidget::item { padding:12px 10px; border-bottom:1px solid #161B22; }
        QTableWidget::item:selected { background:#1F3A2E; color:#E6EDF3; }
        QTableWidget::item:hover { background:#161B22; }

        QHeaderView::section {
            background:#161B22; color:#8B949E; padding:12px 12px; border:0;
            border-bottom:1px solid #21262D; border-right:1px solid #21262D;
            font-weight:600; font-size:11px; letter-spacing:0.6px;
        }
        QHeaderView::section:last { border-right:0; }

        QProgressBar {
            background:#21262D; border:0; border-radius:6px; height:8px;
            text-align:center; color:#E6EDF3; font-size:11px; font-weight:500;
        }
        QProgressBar::chunk {
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #00A86B, stop:1 #00D084);
            border-radius:6px;
        }

        QGroupBox {
            border:1px solid #21262D; border-radius:12px; margin-top:18px;
            padding:16px; background:#161B22;
        }
        QGroupBox::title {
            subcontrol-origin: margin; left:16px; padding:0 10px;
            color:#8B949E; font-weight:600; font-size:12px; letter-spacing:0.4px;
        }

        QMenuBar {
            background:#0D1117; color:#C9D1D9; border-bottom:1px solid #21262D; padding:4px 8px;
        }
        QMenuBar::item { padding:6px 12px; border-radius:6px; background:transparent; }
        QMenuBar::item:selected { background:#21262D; color:#E6EDF3; }

        QMenu {
            background:#161B22; color:#E6EDF3; border:1px solid #30363D;
            border-radius:10px; padding:6px;
        }
        QMenu::item { padding:8px 16px; border-radius:6px; }
        QMenu::item:selected { background:#21262D; }
        QMenu::separator { height:1px; background:#21262D; margin:6px 8px; }

        QStatusBar {
            background:#0D1117; color:#7D8590; border-top:1px solid #21262D;
            font-size:11px; padding:2px 8px;
        }
        QStatusBar::item { border:0; }

        QTextBrowser { background:#0D1117; color:#C9D1D9; border:0; selection-background-color:#00A86B; }

        QScrollBar:vertical { background:#0D1117; width:10px; margin:0; border:0; }
        QScrollBar::handle:vertical { background:#30363D; border-radius:5px; min-height:40px; margin:2px; }
        QScrollBar::handle:vertical:hover { background:#484F58; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; border:0; background:transparent; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }

        QScrollBar:horizontal { background:#0D1117; height:10px; margin:0; border:0; }
        QScrollBar::handle:horizontal { background:#30363D; border-radius:5px; min-width:40px; margin:2px; }
        QScrollBar::handle:horizontal:hover { background:#484F58; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }

        QCheckBox { spacing:10px; color:#C9D1D9; }
        QCheckBox::indicator {
            width:18px; height:18px; border-radius:5px; border:1px solid #30363D; background:#161B22;
        }
        QCheckBox::indicator:checked { background:#00A86B; border-color:#00A86B; }
        QCheckBox::indicator:hover { border-color:#8B949E; }
        QCheckBox::indicator:checked:hover { background:#2EA043; }

        QDialog { background:#0D1117; border:1px solid #21262D; }

        /* Badge strip — pro card */
        QWidget#badgeCard {
            background:#161B22; border:1px solid #21262D; border-radius:10px; padding:2px;
        }
        QLabel#badgeFree {
            background:#1F3A2E; color:#56D364; border:1px solid #2EA043; border-radius:8px;
            padding:6px 12px; font-weight:700; font-size:11px; letter-spacing:0.5px;
        }
        """

    def _build_ui(self):
        c = QWidget()
        self.setCentralWidget(c)
        v = QVBoxLayout(c)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(14)

        # ── Pro badge card (FREE EDITION) ──
        badge_wrap = QWidget()
        badge_wrap.setObjectName("badgeCard")
        strip = QHBoxLayout(badge_wrap)
        strip.setContentsMargins(12, 10, 12, 10)
        strip.setSpacing(12)

        # logo + title
        title_lbl = QLabel("HDM")
        title_lbl.setStyleSheet("font-weight:800; font-size:13px; letter-spacing:0.8px; color:#E6EDF3;")
        ver_lbl = QLabel("v%s • FREE EDITION" % VERSION)
        ver_lbl.setStyleSheet("color:#56D364; font-weight:600; font-size:11px; background:#1F3A2E; border:1px solid #2EA043; border-radius:6px; padding:4px 8px;")
        ver_lbl.setObjectName("badgeFree")

        self.lic_badge = QLabel("…")
        f = QFont("Segoe UI")
        f.setPointSize(11)
        f.setBold(True)
        self.lic_badge.setFont(f)
        self.lic_badge.setStyleSheet("color:#8B949E; font-weight:500;")

        self.act_btn = QPushButton()
        self.act_btn.setObjectName("accent")
        self.act_btn.setMinimumHeight(32)
        self.act_btn.clicked.connect(self.open_activate)

        strip.addWidget(title_lbl)
        strip.addWidget(ver_lbl)
        strip.addSpacing(12)
        strip.addWidget(self.lic_badge, 1)
        strip.addWidget(self.act_btn)
        v.addWidget(badge_wrap)

        # ── URL input — pro ──
        top = QHBoxLayout()
        top.setSpacing(10)
        self.url = UrlBox(self)
        self.url.setPlaceholderText(T[self.lang]["url_ph"])
        self.url.setMinimumHeight(44)
        self.url.returnPressed.connect(self.add_url)
        self.add_btn = QPushButton()
        self.add_btn.setObjectName("accent")
        self.add_btn.setMinimumHeight(44)
        self.add_btn.setMinimumWidth(130)
        self.add_btn.clicked.connect(self.add_url)
        top.addWidget(self.url, 1)
        top.addWidget(self.add_btn)
        v.addLayout(top)

        # ── Table — pro card with bigger rows ──
        self.table = QTableWidget(0, 6)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        try:
            self.table.setCornerButtonEnabled(False)
        except Exception:
            pass
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in (1, 2, 3, 4, 5):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.setStyleSheet("QTableWidget { border-radius:12px; }")
        v.addWidget(self.table, 1)

        # ── Action bar — pro ──
        acts = QHBoxLayout()
        acts.setSpacing(8)
        self.up_btn = QPushButton()
        self.down_btn = QPushButton()
        self.pause_btn = QPushButton()
        self.resume_btn = QPushButton()
        self.remove_btn = QPushButton()
        self.clear_btn = QPushButton()
        self.folder_btn = QPushButton()
        for btn in (self.up_btn, self.down_btn, self.pause_btn, self.resume_btn,
                    self.remove_btn, self.clear_btn, self.folder_btn):
            btn.setMinimumHeight(36)
            btn.setObjectName("ghost")
        self.up_btn.clicked.connect(lambda: self.move_selected(-1))
        self.down_btn.clicked.connect(lambda: self.move_selected(1))
        self.pause_btn.clicked.connect(lambda: self.act("pause"))
        self.resume_btn.clicked.connect(lambda: self.act("resume"))
        self.remove_btn.clicked.connect(lambda: self.act("cancel"))
        self.clear_btn.clicked.connect(self.clear_finished)
        self.folder_btn.clicked.connect(self.open_folder)
        for b in (self.up_btn, self.down_btn, self.pause_btn, self.resume_btn,
                  self.remove_btn, self.clear_btn, self.folder_btn):
            acts.addWidget(b)
        acts.addStretch(1)
        v.addLayout(acts)

        # ── Queue box — pro card ──
        self.queue_box = QGroupBox()
        self.queue_box.setMinimumHeight(64)
        qv = QVBoxLayout(self.queue_box)
        qv.setContentsMargins(14, 18, 14, 14)
        qrow = QHBoxLayout()
        qrow.setSpacing(10)
        self.queue_label = QLabel()
        self.queue_label.setStyleSheet("color:#C9D1D9; font-weight:500;")
        self.q_pause_btn = QPushButton()
        self.q_resume_btn = QPushButton()
        self.q_start_btn = QPushButton()
        self.q_start_btn.setObjectName("accent")
        for b in (self.q_pause_btn, self.q_resume_btn, self.q_start_btn):
            b.setMinimumHeight(36)
        self.q_pause_btn.setObjectName("ghost")
        self.q_resume_btn.setObjectName("ghost")
        self.q_pause_btn.clicked.connect(lambda: (self.engine.pause_queue(), self.refresh()))
        self.q_resume_btn.clicked.connect(lambda: (self.engine.resume_queue(), self.refresh()))
        self.q_start_btn.clicked.connect(lambda: (self.engine.start_now(), self.refresh()))
        qrow.addWidget(self.queue_label)
        qrow.addStretch(1)
        qrow.addWidget(self.q_pause_btn)
        qrow.addWidget(self.q_resume_btn)
        qrow.addWidget(self.q_start_btn)
        qv.addLayout(qrow)
        v.addWidget(self.queue_box)

        self.status = self.statusBar()
        self.status.showMessage(str(self.dl_dir))

    def _build_menu(self):
        mb = self.menuBar()
        self.m_file = mb.addMenu("")
        self.a_folder = QAction(self)
        self.a_folder.triggered.connect(self.open_folder)
        self.a_change = QAction(self)
        self.a_change.triggered.connect(self.change_folder)
        self.a_startup = QAction(self, checkable=True)
        self.a_startup.triggered.connect(self.toggle_startup)
        self.a_startup.setChecked(hdm_server.startup_enabled())
        self.a_exit = QAction(self)
        self.a_exit.triggered.connect(self.quit_app)
        for a in (self.a_folder, self.a_change, self.a_startup, self.a_exit):
            self.m_file.addAction(a)

        self.m_settings = mb.addMenu("")
        self.a_options = QAction(self)
        self.a_options.triggered.connect(lambda: OptionsDialog(self).exec())
        self.m_settings.addAction(self.a_options)
        self.m_lang = self.m_settings.addMenu("")
        self.a_en = QAction("English", self, checkable=True)
        self.a_fa = QAction("فارسی", self, checkable=True)
        self.a_en.triggered.connect(lambda: self.apply_lang("en"))
        self.a_fa.triggered.connect(lambda: self.apply_lang("fa"))
        self.m_lang.addAction(self.a_en)
        self.m_lang.addAction(self.a_fa)

        self.m_help = mb.addMenu("")
        self.a_site = QAction(self)
        self.a_site.triggered.connect(lambda: webbrowser.open("https://hamidesigns.shop/hdm/"))
        self.a_activate = QAction(self)
        self.a_activate.triggered.connect(self.open_activate)
        self.a_about = QAction(self)
        self.a_about.triggered.connect(self.open_about)
        self.m_help.addAction(self.a_site)
        self.m_help.addAction(self.a_activate)
        self.m_help.addAction(self.a_about)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self.app_icon(), self)
        menu = QMenu()
        self.tray_show = QAction(self)
        self.tray_show.triggered.connect(self.show_normal)
        self.tray_exit = QAction(self)
        self.tray_exit.triggered.connect(self.quit_app)
        menu.addAction(self.tray_show)
        menu.addAction(self.tray_exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.show_normal() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    # ── license badge / warnings ───────────────────────────────────────────
    def update_badge(self):
        t = T[self.lang]
        s = act.status()
        is_free = "FREE" in str(s.get("plan","")).upper()
        if s["licensed"]:
            if s["lifetime"]:
                txt = t["act_badge"] % (s["plan_fa"] if self.lang == "fa" else s["plan"])
            else:
                txt = t["act_badge_days"] % (s["plan_fa"] if self.lang == "fa" else s["plan"],
                                             s["days_left"])
            if is_free:
                # pro green pill for FREE EDITION
                self.lic_badge.setStyleSheet(
                    "background:#1F3A2E; color:#56D364; border:1px solid #2EA043; "
                    "border-radius:8px; padding:6px 12px; font-weight:700; font-size:11px; letter-spacing:0.4px;"
                )
            else:
                self.lic_badge.setStyleSheet(
                    "background:#1A2332; color:#00D084; border:1px solid #00A86B; "
                    "border-radius:8px; padding:6px 12px; font-weight:600;"
                )
            self.act_btn.setVisible(False)
        elif s["reason"]:
            txt = s["reason"] if self.lang == "en" else "لایسنس روی این دستگاه معتبر نیست"
            self.lic_badge.setStyleSheet(
                "background:#2D1217; color:#FF7B72; border:1px solid #F85149; "
                "border-radius:8px; padding:6px 12px; font-weight:600;"
            )
            self.act_btn.setVisible(True)
        elif s["trial_active"]:
            days = max(1, -(-s["trial_left_sec"] // 86400))
            txt = t["trial_badge"] % days if days > 1 else t["trial_today"]
            self.lic_badge.setStyleSheet(
                "background:#2D1F0E; color:#E3B341; border:1px solid #D29922; "
                "border-radius:8px; padding:6px 12px; font-weight:600;"
            )
            self.act_btn.setVisible(True)
        else:
            txt = t["expired_badge"]
            self.lic_badge.setStyleSheet(
                "background:#2D1217; color:#FF7B72; border:1px solid #F85149; "
                "border-radius:8px; padding:6px 12px; font-weight:600;"
            )
            self.act_btn.setVisible(True)
        self.lic_badge.setText(txt)
        self.act_btn.setText(t["activate_btn"])

    def check_expiry_warnings(self, s):
        if not s["licensed"] or s["lifetime"]:
            return
        t = T[self.lang]
        days = s["days_left"]
        today = time.strftime("%Y-%m-%d")
        last = str(self.settings.value("last_warn", ""))
        if days <= 1 and last != "d1":
            self.notify(t["warn1_title"], t["warn1"] % time.strftime(
                "%Y-%m-%d", time.localtime(s["expires_at"])))
            self.settings.setValue("last_warn", "d1")
        elif days <= 7 and last not in ("d1", "d7"):
            self.notify(t["warn7_title"], t["warn7"] % (days, time.strftime(
                "%Y-%m-%d", time.localtime(s["expires_at"]))))
            self.settings.setValue("last_warn", "d7")

    def notify(self, title, text):
        try:
            self.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Warning, 8000)
        except Exception:
            pass
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def open_activate(self):
        ActivateDialog(self).exec()

    def open_about(self):
        AboutDialog(self).exec()

    def after_activation(self):
        self.settings.remove("last_warn")
        self.refresh()

    # ── clipboard ─────────────────────────────────────────────────────────
    @staticmethod
    def _clip_url(text):
        t = (text or "").strip().split("\n")[0].strip()
        if t.lower().startswith(("http://", "https://")) and " " not in t:
            return t
        return ""

    def clip_changed(self, startup=False):
        try:
            url = self._clip_url(self.clipboard.text())
        except Exception:
            return
        if not url or url == self._last_clip:
            return
        self._last_clip = url
        if self.clip_auto and not startup:
            try:
                self.engine.add(url)
                self.status.showMessage(T[self.lang]["clip_added"] % url, 4000)
                self.refresh()
                return
            except Exception:
                pass
        current = self.url.text().strip()
        if not current or current == self._last_clip_filled:
            self.url.setText(url)
            self._last_clip_filled = url
            self.status.showMessage(T[self.lang]["clip_hint"], 4000)

    def check_clip_now(self):
        try:
            url = self._clip_url(self.clipboard.text())
        except Exception:
            return
        if url and not self.url.text().strip():
            self._last_clip = url
            self._last_clip_filled = url
            self.url.setText(url)
            self.status.showMessage(T[self.lang]["clip_hint"], 3000)

    # ── actions ───────────────────────────────────────────────────────────
    def save_prefs(self):
        self.settings.setValue("max_concurrent", self.engine.max_concurrent)
        self.settings.setValue("categorize", self.engine.categorize)
        self.settings.setValue("sched_enabled", self.engine.schedule.get("enabled", False))
        self.settings.setValue("sched_start", self.engine.schedule.get("start", "00:00"))
        self.settings.setValue("sched_stop", self.engine.schedule.get("stop", "06:00"))
        self.settings.setValue("clip_auto", self.clip_auto)

    def apply_lang(self, lang):
        self.lang = lang if lang in T else "en"
        t = T[self.lang]
        self.settings.setValue("lang", self.lang)
        QApplication.instance().setLayoutDirection(t["dir"])
        self.a_en.setChecked(self.lang == "en")
        self.a_fa.setChecked(self.lang == "fa")

        self.m_file.setTitle(t["file"])
        self.m_settings.setTitle(t["settings"])
        self.m_lang.setTitle(t["language"])
        self.m_help.setTitle(t["help"])
        self.a_folder.setText(t["open_folder"])
        self.a_change.setText(t["change_folder"])
        self.a_startup.setText(t["startup"])
        self.a_exit.setText(t["exit"])
        self.a_options.setText(t["options"])
        self.a_site.setText(t["website"])
        self.a_activate.setText(t["activate_menu"])
        self.a_about.setText(t["about"])

        self.url.setPlaceholderText(t["url_ph"])
        # pro icons
        self.add_btn.setText("➕  " + t["add"])
        self.up_btn.setText("↑ " + t["up"])
        self.down_btn.setText("↓ " + t["down"])
        self.pause_btn.setText("⏸ " + t["pause"])
        self.resume_btn.setText("▶ " + t["resume"])
        self.remove_btn.setText("✕ " + t["remove"])
        self.clear_btn.setText("🧹 " + t["clear"])
        self.folder_btn.setText("📁 " + t["open_folder"])
        self.queue_box.setTitle("⚡ " + t["queue"])
        self.q_pause_btn.setText("⏸ " + t["queue_pause"])
        self.q_resume_btn.setText("▶ " + t["queue_resume"])
        self.q_start_btn.setText("🚀 " + t["start_now"])
        self.table.setHorizontalHeaderLabels(t["cols"])
        self.tray_show.setText(t["tray_show"])
        self.tray_exit.setText(t["tray_quit"])
        self.refresh()

    def current_id(self):
        r = self.table.currentRow()
        for jid, row in self.rows.items():
            if row == r:
                return jid
        return None

    def move_selected(self, delta):
        jid = self.current_id()
        if not jid:
            self.status.showMessage(T[self.lang]["no_sel"])
            return
        if not self.engine.move(jid, delta):
            return
        self.rebuild()
        self.refresh()
        row = self.rows.get(jid)
        if row is not None:
            self.table.selectRow(row)

    def add_url(self):
        url = self.url.text().strip()
        if not url:
            self.check_clip_now()
            url = self.url.text().strip()
        if not url:
            return
        try:
            self.engine.add(url)
        except Exception as e:
            QMessageBox.warning(self, APP, str(e))
            return
        self.url.clear()
        self.refresh()

    def act(self, op):
        jid = self.current_id()
        if not jid:
            QMessageBox.information(self, APP, T[self.lang]["no_sel"])
            return
        getattr(self.engine, {"pause": "pause", "resume": "resume", "cancel": "cancel"}[op])(jid)
        self.refresh()

    def clear_finished(self):
        for j in self.engine.list():
            if j["status"] == "done":
                self.engine.cancel(j["id"])
                self.rows.pop(j["id"], None)
        self.rebuild()

    def open_folder(self):
        path = str(self.dl_dir)
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            webbrowser.open("file://" + path)

    def change_folder(self):
        d = QFileDialog.getExistingDirectory(self, "", str(self.dl_dir))
        if d:
            self.dl_dir = Path(d)
            self.settings.setValue("dl_dir", d)
            self.engine.dest_dir = self.dl_dir
            self.status.showMessage(str(self.dl_dir))

    def toggle_startup(self, checked):
        ok, msg = hdm_server.startup_registry(checked)
        if not ok:
            self.a_startup.setChecked(hdm_server.startup_enabled())
            self.status.showMessage(msg)

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        t = T[self.lang]
        box = QMessageBox(self)
        box.setWindowTitle(t["exit_title"])
        box.setText(t["exit_text"])
        box.setIcon(QMessageBox.Icon.Question)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self.engine.save_state(JOBS_FILE)
        self.engine.shutdown()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        if not self.tray_notified:
            self.tray.showMessage(APP, T[self.lang]["tray_msg"],
                                  QSystemTrayIcon.MessageIcon.Information, 2500)
            self.tray_notified = True

    # ── refresh ───────────────────────────────────────────────────────────
    def rebuild(self):
        self.table.setRowCount(0)
        self.rows = {}

    def refresh(self):
        t = T[self.lang]
        s = act.status()
        self.update_badge()
        self.check_expiry_warnings(s)

        q = self.engine.queue_state()
        if q["state"] == "paused":
            self.queue_label.setText(t["q_paused"])
        elif q["state"] == "waiting":
            self.queue_label.setText(t["q_waiting"] % (q["schedule"]["start"], q["schedule"]["stop"]))
        else:
            self.queue_label.setText(t["queue_state"] % (q["running"], q["max"]))

        jobs = self.engine.list()
        live = {j["id"] for j in jobs}
        if any(k not in live for k in self.rows):
            self.rebuild()

        for j in jobs:
            if j["id"] not in self.rows:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.rows[j["id"]] = row
                for col in (0, 1, 2, 4, 5):
                    self.table.setItem(row, col, QTableWidgetItem(""))
                bar = QProgressBar()
                bar.setTextVisible(True)
                self.table.setCellWidget(row, 3, bar)
            row = self.rows[j["id"]]
            size = j["size"]
            pctv = int(j["done"] / size * 100) if size else (100 if j["status"] == "done" else 0)
            def _set(col, text):
                item = self.table.item(row, col)
                if item is not None and item.text() != text:
                    item.setText(text)
            _set(0, j["name"])
            _set(1, fmt(size) if size else "…")
            _set(2, str(j.get("parts", 1)))
            bar = self.table.cellWidget(row, 3)
            if bar is not None and bar.value() != pctv:
                bar.setValue(pctv)
            _set(4, (fmt(j["speed"]) + "/s") if j["status"] == "running" else "")
            status = j["status"] + ((" · " + j["error"]) if j.get("error") else "")
            _set(5, status)

        self._save_tick += 1
        if self._save_tick % 20 == 0:          # ~ every 10 s
            self.engine.save_state(JOBS_FILE)


# ── crash safety net ───────────────────────────────────────────────────────
def _excepthook(etype, value, tb):
    text = "".join(traceback.format_exception(etype, value, tb))
    try:
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write("\n%s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except Exception:
        pass
    sys.__excepthook__(etype, value, tb)
    try:
        QMessageBox.critical(None, T["en"]["crash_title"], T["en"]["crash_text"] % CRASH_LOG)
    except Exception:
        pass


def main():
    sys.excepthook = _excepthook
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setOrganizationName(ORG)
    app.setQuitOnLastWindowClosed(False)
    w = MainWindow()
    if "--silent" in sys.argv:
        w.tray.showMessage(APP, T[w.lang]["tray_msg"],
                           QSystemTrayIcon.MessageIcon.Information, 2000)
    else:
        w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
