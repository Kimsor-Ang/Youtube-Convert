import os
import re
import sys
import glob
import time
import uuid
import shutil
import tempfile
import threading
import webbrowser
import jinja2
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response
import yt_dlp

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent

# Support index.html in both templates/ and root directory to prevent 500 errors
app.jinja_loader = jinja2.ChoiceLoader([
    jinja2.FileSystemLoader(str(BASE_DIR / "templates")),
    jinja2.FileSystemLoader(str(BASE_DIR)),
])

# Find FFmpeg binary
def find_ffmpeg():
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_pattern = os.path.join(
            local_app_data, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", "ffmpeg.exe"
        )
        matches = glob.glob(winget_pattern, recursive=True)
        if matches:
            return matches[0]
    for pf in [r"C:\Program Files\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe"]:
        if os.path.exists(pf):
            return pf
    return None

FFMPEG_PATH = find_ffmpeg()
FFMPEG_DIR = os.path.dirname(FFMPEG_PATH) if FFMPEG_PATH else None
if FFMPEG_DIR and FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

# Task store: task_id -> {status, percent, speed, eta, file_path, filename, error, tmp_dir}
tasks = {}
tasks_lock = threading.Lock()

def clean_youtube_url(url):
    if not url:
        return url
    url = url.strip()
    v_match = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", url)
    if v_match:
        return f"https://www.youtube.com/watch?v={v_match.group(1)}"
    short_match = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
    if short_match:
        return f"https://www.youtube.com/watch?v={short_match.group(1)}"
    shorts_match = re.search(r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})", url)
    if shorts_match:
        return f"https://www.youtube.com/watch?v={shorts_match.group(1)}"
    return url

def get_base_ydl_opts():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 10,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_args": {
            "youtube": {"player_client": ["android", "web"]}
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
    }
    if FFMPEG_DIR:
        opts["ffmpeg_location"] = FFMPEG_DIR
    cookies_file = BASE_DIR / "cookies.txt"
    if cookies_file.exists():
        opts["cookiefile"] = str(cookies_file)
    return opts

def format_bytes(size):
    if not size or size <= 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def format_duration(seconds):
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

def clean_error(err_str):
    el = err_str.lower()
    if "video unavailable" in el or "this video is unavailable" in el:
        return "This video is unavailable, deleted, or private on YouTube. Try another link."
    if "sign in to confirm" in el or "not a bot" in el or "429" in el:
        return "YouTube is blocking this request. Try a different video or try again in a moment."
    if "requested format is not available" in el:
        return "That resolution is not available. Try 720p or 480p."
    if "timed out" in el:
        return "Request timed out. Check your internet and try again."
    if "ERROR:" in err_str:
        return err_str.split("ERROR:")[-1].strip()
    return err_str

@app.route("/")
def index():
    return render_template("index.html", ffmpeg_available=bool(FFMPEG_PATH))

@app.route("/favicon.ico")
def favicon():
    return Response(status=204)

@app.route("/api/info", methods=["POST"])
def get_info():
    data = request.get_json(force=True) or {}
    raw_url = (data.get("url") or "").strip()
    if not raw_url:
        return jsonify({"success": False, "error": "Please provide a valid YouTube URL."}), 400

    url = clean_youtube_url(raw_url)
    ydl_opts = get_base_ydl_opts()
    ydl_opts["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                entries = [e for e in info['entries'] if e]
                if not entries:
                    return jsonify({"success": False, "error": "No playable videos found."}), 400
                info = entries[0]

            title = info.get("title", "Unknown Title")
            duration = info.get("duration", 0)
            thumbnail = info.get("thumbnail") or (info.get("thumbnails", [{}])[-1].get("url", "") if info.get("thumbnails") else "")
            uploader = info.get("uploader") or info.get("channel") or "Unknown"
            views = info.get("view_count", 0)

            available_heights = set()
            for f in info.get("formats", []):
                h = f.get("height")
                if h and isinstance(h, int):
                    available_heights.add(h)

            detected_qualities = []
            for res in [2160, 1440, 1080, 720, 480, 360]:
                if any(h >= res for h in available_heights):
                    detected_qualities.append(f"{res}p")
            if not detected_qualities:
                detected_qualities = ["720p", "480p", "360p"]

            return jsonify({
                "success": True,
                "title": title,
                "uploader": uploader,
                "duration": format_duration(duration),
                "views": f"{views:,}" if views else "N/A",
                "thumbnail": thumbnail,
                "url": url,
                "qualities": detected_qualities,
                "ffmpeg_available": bool(FFMPEG_PATH)
            })
    except Exception as e:
        return jsonify({"success": False, "error": clean_error(str(e))}), 400

def run_download_task(task_id, raw_url, format_type, quality):
    url = clean_youtube_url(raw_url)

    with tasks_lock:
        tasks[task_id]["status"] = "downloading"
        tasks[task_id]["percent"] = 0
        tasks[task_id]["speed"] = "Connecting..."
        tasks[task_id]["eta"] = "Calculating..."

    # Use a temporary directory — deleted after the file is served
    tmp_dir = tempfile.mkdtemp(prefix="streamvault_")
    out_tmpl = os.path.join(tmp_dir, "%(title).120s [%(id)s].%(ext)s")

    def progress_hook(d):
        with tasks_lock:
            task = tasks.get(task_id)
            if not task:
                return
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                speed = d.get("speed") or 0
                eta = d.get("eta") or 0
                percent = round((downloaded / total) * 100, 1) if total > 0 else 0
                task.update({
                    "percent": percent,
                    "downloaded_bytes": format_bytes(downloaded),
                    "total_bytes": format_bytes(total) if total > 0 else "Unknown",
                    "speed": f"{format_bytes(speed)}/s" if speed else "Calculating...",
                    "eta": f"{int(eta)}s" if eta else "Calculating...",
                    "status": "downloading"
                })
            elif status == "finished":
                task.update({"status": "processing", "percent": 99, "speed": "Finalizing...", "eta": "Almost done"})

    ydl_opts = get_base_ydl_opts()
    ydl_opts["outtmpl"] = out_tmpl
    ydl_opts["progress_hooks"] = [progress_hook]

    if format_type == "mp3":
        if FFMPEG_PATH:
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality if quality in ["128", "192", "256", "320"] else "192",
            }]
        else:
            ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
    else:
        height_val = quality.replace("p", "") if quality and quality.endswith("p") else None
        if FFMPEG_PATH:
            fmt = f"bestvideo[height<={height_val}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height_val}]+bestaudio/best" if height_val else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
            ydl_opts["format"] = fmt
            ydl_opts["merge_output_format"] = "mp4"
        else:
            ydl_opts["format"] = "best[ext=mp4]/best"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            meta = ydl.extract_info(url, download=True)
            if 'entries' in meta:
                meta = meta['entries'][0]

            expected_ext = "mp3" if format_type == "mp3" and FFMPEG_PATH else "mp4"
            video_id = meta.get("id", "")
            matches = list(Path(tmp_dir).glob(f"*{video_id}*.{expected_ext}"))
            if not matches:
                matches = list(Path(tmp_dir).glob(f"*{video_id}*.*"))
            if not matches:
                matches = list(Path(tmp_dir).glob("*.*"))

            if matches:
                matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                final_file = matches[0]
                with tasks_lock:
                    tasks[task_id].update({
                        "status": "completed",
                        "percent": 100,
                        "filename": final_file.name,
                        "file_path": str(final_file),
                        "tmp_dir": tmp_dir,
                        "download_url": f"/api/file/{task_id}"
                    })
            else:
                raise Exception("Could not locate the downloaded file.")
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        with tasks_lock:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["error"] = clean_error(str(e))

@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    format_type = data.get("format_type", "mp4").lower()
    quality = str(data.get("quality", "1080p")).lower()

    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400

    task_id = str(uuid.uuid4())
    with tasks_lock:
        tasks[task_id] = {
            "id": task_id, "url": clean_youtube_url(url),
            "format_type": format_type, "quality": quality,
            "status": "starting", "percent": 0,
            "speed": "Initializing...", "eta": "...",
            "downloaded_bytes": "0 B", "total_bytes": "...",
            "filename": None, "file_path": None, "tmp_dir": None,
            "error": None, "start_time": time.time()
        }

    threading.Thread(target=run_download_task, args=(task_id, url, format_type, quality), daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})

@app.route("/api/progress/<task_id>")
def get_progress(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "Task not found"}), 404
        # Return a safe copy without internal file paths
        safe = {k: v for k, v in task.items() if k not in ("file_path", "tmp_dir")}
        return jsonify({"success": True, "task": safe})

def cleanup_temp_dir(tmp_dir, task_id, delay=300):
    def _clean():
        time.sleep(delay)
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        with tasks_lock:
            tasks.pop(task_id, None)
    threading.Thread(target=_clean, daemon=True).start()

def purge_old_streamvault_temps():
    try:
        temp_base = tempfile.gettempdir()
        for p in glob.glob(os.path.join(temp_base, "streamvault_*")):
            try:
                shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass
    except Exception:
        pass

@app.route("/api/file/<task_id>")
def serve_file(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
        if not task or task.get("status") != "completed":
            return jsonify({"error": "File not ready"}), 404
        file_path = task.get("file_path")
        filename = task.get("filename")
        tmp_dir = task.get("tmp_dir")

    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    # Determine content-type
    ext = Path(filename).suffix.lower()
    content_type = "audio/mpeg" if ext == ".mp3" else "video/mp4"

    # Schedule automatic removal of temp folder after 5 minutes (enables retries, zero disk leaks)
    cleanup_temp_dir(tmp_dir, task_id, delay=300)

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype=content_type
    )

def open_browser(port):
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{port}")

if __name__ == "__main__":
    purge_old_streamvault_temps()
    port = int(os.environ.get("PORT", 5000))
    is_cloud = os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER") or os.environ.get("DYNO")
    print(f"=====================================================")
    print(f" StreamVault running on port {port}")
    print(f" FFmpeg: {'Found -> ' + FFMPEG_PATH if FFMPEG_PATH else 'Not found'}")
    print(f" Mode: {'Cloud' if is_cloud else 'Local'}")
    print(f"=====================================================")
    if not is_cloud:
        threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False)

