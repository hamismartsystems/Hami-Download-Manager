# HDM - Hami Download Manager FREE EDITION v2.1.0

![Banner](screenshots/hdm-banner.png)

<p align="center">
  <img src="https://img.shields.io/badge/version-2.1.0--FREE--Pro-blue?style=for-the-badge" />
  <img src="https://img.shields.io/badge/UI-Exact%20Replica-121418?style=for-the-badge" />
  <img src="https://img.shields.io/badge/license-GPL--3.0-green?style=for-the-badge" />
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?style=for-the-badge&logo=windows" />
</p>

<p align="center">
  <b>Professional download manager — an exact, pixel-faithful replica of the reference design</b><br/>
  Card-based layout, eight segmented progress bars, live speed-graph sidebar.
</p>

[فارسی](README.md)

---

### 🎯 Exactly like the reference screenshots

**Your reference images:**

| Main Target | Settings Target |
|---|---|
| ![Target Main](screenshots/reference-main-target.png) | ![Target Settings](screenshots/reference-settings-target.png) |

**The new v2.1.0 implementation:**

![New v2.1.0 Exact](screenshots/hdm-v210-pro-exact.png)

---

### ✨ v2.1.0 — what matches the design exactly

#### Main Window — like image 1
- **Title bar**: `HDM - Hami Download Manager FREE EDITION, free` + `v2.1.0` on the right
- **Menu**: File | Downloads | Tools | Help
- **Toolbar**:
  - `📄+ New+` | `▶ Start All` | `⏸ Pause All` | `🗑 Remove` | `⚙️ Settings` — icon on top, text below
  - Search box on the right with 🔍
- **Download Cards** (3 as in the image):
  - File-type icon on the left (💿 for ISO, 📀 for EXE, 📦 for RAR)
  - Title: `Ubuntu Desktop 24.04 LTS ISO' (4.8 GB)`
  - **Segmented bars**: 8 small bars — green = complete, blue = downloading, dark/grey = waiting
  - Speed / ETA and Size / Percent under the card
  - Right-side buttons: active blue `⏸ Pause`, `▶ Resume`, `■ Stop`
  - Blue border on the active card
- **Right sidebar** (280px):
  - `Currently Downloading` + a green speed graph (50 points, gradient fill)
  - `Connection Status ✅` + `8/8 threads active`
  - `Details`: Save To + Total Speed
- **Bottom status**: `Total Speed: 45.5 MB/s | Total Downloaded: 4.8 GB | Active: 3, Completed: 0`

#### Settings — like image 2
- **Title**: `Settings - DownloadMaster` + blue icon
- **Left sidebar** (180px): General, Downloads (selected), Connection, Scheduler, Interface, Advanced — with icons
- **Right content**:
  - `Download Settings` big heading
  - **Queue Management card**:
    - `Max Simultaneous Downloads: [3]` + slider 1-5 (1...3...5) + default note
    - Buttons: `▶ Start Now` | `⏸ Pause Queue` | `▶ Resume Queue`
  - **Scheduler card**:
    - `Download Schedule` + `Enable Scheduling` checkbox
    - `Download between: [01]:[00]` and `[07]:[00]`
  - **Application Settings card**:
    - `Language: [🇬🇧 English ▼]` dropdown English / فارسی / Español
  - **Scheduler Info card**: scheduling explanation
  - Bottom buttons: OK | Cancel | Apply

---

### 🚀 Features

- **Segmented**: 8 parallel parts, per-part resume — the engine tracks `parts_progress` with done/running/pending states
- **Queue**: 1-5 simultaneous, pause/resume the queue, start now
- **Cards**: exact replica, 88-96px height, hover border #3A3F4B, active border #4A90E2
- **Graph**: real-time 50-point speed history, green line #4CAF50 with gradient fill
- **Search**: filter cards by name
- **FREE EDITION**: `FREE_MODE=True`, no license needed

---

### 📦 Installation

```bash
git clone https://github.com/hamismartsystems/Hami-Download-Manager.git
cd Hami-Download-Manager
pip install PyQt6 requests
python hdm_gui.py
```

Build:
```bat
build_windows.bat    :: -> dist\HDM-2.1.0\HDM-2.1.0.exe
build_installer.bat  :: -> installer\HDM-2.1.0-Setup.exe
```

---

### 🎨 Design Tokens — Exact Match

```
Window: #121418
Card: #1E2025
Card Border: #2A2E35 / Active #4A90E2
Card Hover: #3A3F4B
Sidebar: #1A1D23 / #1E2025
Segment Done: #4CAF50 green
Segment Running: #2196F3 blue
Segment Pending: #1E2025 black + #2A2E35 border
Button Pause Active: #4A90E2 blue
Button Ghost: #2A2E35 bg + #3A3F4B border
Text Primary: #E6E6E6
Text Secondary: #8B8F99 / #A0A5B0
Graph Line: #4CAF50 + gradient fill 120→10 alpha
```

---

### 📸 Screenshots

| v2.1.0 Exact | v1.0.3 Pro | Old |
|---|---|---|
| ![v210](screenshots/hdm-v210-pro-exact.png) | ![v103](screenshots/hdm-pro-main-v103.png) | ![old](screenshots/hdm-main.png) |

---

### 📄 License GPL-3.0

© HAMI SMART SYSTEMS — https://hamidesigns.shop/hdm/

**https://github.com/hamismartsystems/Hami-Download-Manager**
