# 🎬 StreamVault - YouTube to MP4 & MP3 Downloader

A modern, fast, and 100% free web-based YouTube Downloader built with **Python 3.12**, **Flask**, **yt-dlp**, and **FFmpeg**.

---

## 🚀 Quick Start (One-Click)

### Option 1: Double-Click the Launcher
Simply double-click **`run.bat`** in this folder. It will:
1. Automatically detect your Python 3.12 installation.
2. Start the local Flask web server.
3. Automatically launch your default web browser to:
   👉 **`http://127.0.0.1:5000`**

### Option 2: Command Line
Open a terminal in this folder and run:
```bash
python app.py
```
*(If `python` is not in your PATH, run:)*
```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" app.py
```

---

## ✨ Features

- **🎥 Video Downloads (MP4)**:
  - Choose resolutions: **1080p Full HD**, **720p HD**, **480p**, or **360p Compact**.
  - Merges pristine video and audio tracks via high-performance **FFmpeg**.
- **🎵 Audio Downloads (MP3)**:
  - Extract studio-grade audio: **320 kbps (Ultra)**, **256 kbps**, **192 kbps**, or **128 kbps**.
- **⚡ Live Real-Time Progress**:
  - Live animated progress bar showing percentage, download speed (MB/s), downloaded size, and ETA.
- **💾 Automatic Browser Download & Local Storage**:
  - Automatically triggers browser file saving upon completion.
  - Keeps copies in the local [`downloads/`](file:///c:/Users/angki/OneDrive/Dokumen/New%20folder/downloads) directory.
- **📂 One-Click Folder Access**:
  - Click **"Downloads Folder"** anytime in the navigation bar to immediately open Windows File Explorer to your saved files.
- **📋 Clipboard Integration**:
  - One-click "Paste" button to quickly paste YouTube links.
- **📚 Built-in Library**:
  - View all downloaded videos and audio, re-save them to your browser, or delete them anytime.

---

## 🛠️ Installed Technologies

- **Python**: 3.12 (Installed via winget)
- **Engine**: [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) (Up to date)
- **Web Server**: [`Flask`](https://flask.palletsprojects.com/)
- **Transcoder**: [`FFmpeg 9.0.2`](https://ffmpeg.org/) (Full build with MP3 encoder)
- **Frontend**: Responsive modern UI with dark glassmorphism, animations, and zero heavy client frameworks.
