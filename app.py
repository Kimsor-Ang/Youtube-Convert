import os
import re
import sys
import glob
import time
import uuid
import shutil
import threading
import webbrowser
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, Response
import yt_dlp

app = Flask(__name__)

# Base directories
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_FILE = BASE_DIR / "cookies.txt"

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

    prog_files = [
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    ]
    for pf in prog_files:
        if os.path.exists(pf):
            return pf

    return None

FFMPEG_PATH = find_ffmpeg()
FFMPEG_DIR = os.path.dirname(FFMPEG_PATH) if FFMPEG_PATH else None
if FFMPEG_DIR and FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

# In-memory download task tracker
tasks = {}
tasks_lock = threading.Lock()

def clean_youtube_url(url):
    """
    Strips playlist, mix, radio, and tracking parameters (&list=, &index=, &pp=)
    so that yt-dlp only inspects the requested video in 2-3 seconds instead of 
    recursively traversing 50-100 playlist items.
    """
    if not url:
        return url
    url = url.strip()

    # Standard watch?v=...
    v_match = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", url)
    if v_match:
        return f"https://www.youtube.com/watch?v={v_match.group(1)}"

    # youtu.be/VIDEO_ID
    short_match = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
    if short_match:
        return f"https://www.youtube.com/watch?v={short_match.group(1)}"

    # youtube.com/shorts/VIDEO_ID
    shorts_match = re.search(r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})", url)
    if shorts_match:
        return f"https://www.youtube.com/watch?v={shorts_match.group(1)}"

    return url

def get_base_ydl_opts():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "socket_timeout": 10,
        "retries": 2,
        "fragment_retries": 2,
        # Bypass YouTube bot detection by prioritizing android client
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"]
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
    }
    if FFMPEG_DIR:
        opts["ffmpeg_location"] = FFMPEG_DIR
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)
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
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"

def clean_error_message(err_str):
    err_lower = err_str.lower()
    if "video unavailable" in err_lower or "this video is unavailable" in err_lower:
        return "This video is unavailable, deleted, or set to private on YouTube. Please check the link or try another video."
    if "sign in to confirm you" in err_lower or "not a bot" in err_lower or "429" in err_lower:
        return "YouTube is requesting sign-in/verification for this specific video. Try another video, or export a cookies.txt file."
    if "requested format is not available" in err_lower:
        return "The requested video resolution is not available for this stream. Try selecting 720p or 480p."
    if "timed out" in err_lower:
        return "The request to YouTube timed out. Please check your internet connection and try again."
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

    # Clean URL (strip playlist parameters like &list=RDTnmgaOcCJVg)
    url = clean_youtube_url(raw_url)

    ydl_opts = get_base_ydl_opts()
    ydl_opts["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if 'entries' in info:
                entries = [e for e in info['entries'] if e]
                if entries:
                    info = entries[0]
                else:
                    return jsonify({"success": False, "error": "No playable videos found in this link."}), 400

            title = info.get("title", "Unknown Title")
            duration = info.get("duration", 0)
            thumbnail = info.get("thumbnail") or (info.get("thumbnails")[-1]["url"] if info.get("thumbnails") else "")
            uploader = info.get("uploader") or info.get("channel") or "Unknown Creator"
            views = info.get("view_count", 0)
            views_formatted = f"{views:,}" if views else "N/A"

            # Detect available video resolutions
            available_heights = set()
            for f in info.get("formats", []):
                h = f.get("height")
                if h and isinstance(h, int):
                    available_heights.add(h)

            sorted_heights = sorted(list(available_heights), reverse=True)
            target_resolutions = [2160, 1440, 1080, 720, 480, 360]
            detected_qualities = []
            for res in target_resolutions:
                if any(h >= res for h in sorted_heights):
                    detected_qualities.append(f"{res}p")

            if not detected_qualities:
                detected_qualities = ["720p", "480p", "360p"]

            return jsonify({
                "success": True,
                "title": title,
                "uploader": uploader,
                "duration": format_duration(duration),
                "views": views_formatted,
                "thumbnail": thumbnail,
                "url": url,
                "qualities": detected_qualities,
                "ffmpeg_available": bool(FFMPEG_PATH)
            })
    except Exception as e:
        friendly_msg = clean_error_message(str(e))
        return jsonify({"success": False, "error": friendly_msg}), 400

def run_download_task(task_id, raw_url, format_type, quality):
    with tasks_lock:
        tasks[task_id]["status"] = "downloading"
        tasks[task_id]["percent"] = 0
        tasks[task_id]["speed"] = "Connecting..."
        tasks[task_id]["eta"] = "Calculating..."

    url = clean_youtube_url(raw_url)
    out_tmpl = str(DOWNLOADS_DIR / "%(title).150s [%(id)s].%(ext)s")

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

                percent = 0
                if total > 0:
                    percent = round((downloaded / total) * 100, 1)

                task["percent"] = percent
                task["downloaded_bytes"] = format_bytes(downloaded)
                task["total_bytes"] = format_bytes(total) if total > 0 else "Unknown"
                task["speed"] = f"{format_bytes(speed)}/s" if speed else "Calculating..."
                task["eta"] = f"{int(eta)}s" if eta else "Calculating..."
                task["status"] = "downloading"

            elif status == "finished":
                task["status"] = "processing"
                task["percent"] = 99
                task["speed"] = "Finalizing..."
                task["eta"] = "Almost done"

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
    else: # mp4
        height_val = quality.replace("p", "") if quality and quality.endswith("p") else None
        if FFMPEG_PATH:
            if height_val and height_val.isdigit():
                ydl_opts["format"] = f"bestvideo[height<={height_val}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height_val}]+bestaudio/best[height<={height_val}][ext=mp4]/best"
            else:
                ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
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
            matches = list(DOWNLOADS_DIR.glob(f"*{video_id}*.{expected_ext}"))
            
            if not matches:
                matches = list(DOWNLOADS_DIR.glob(f"*{video_id}*.*"))

            if matches:
                matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                final_file = matches[0]
                final_filename = final_file.name
                filesize = final_file.stat().st_size
            else:
                final_filename = f"{meta.get('title', 'download')}.{expected_ext}"
                filesize = 0

            with tasks_lock:
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["percent"] = 100
                tasks[task_id]["filename"] = final_filename
                tasks[task_id]["filesize"] = format_bytes(filesize)
                tasks[task_id]["download_url"] = f"/api/file/{task_id}"

    except Exception as e:
        with tasks_lock:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["error"] = clean_error_message(str(e))

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
            "id": task_id,
            "url": clean_youtube_url(url),
            "format_type": format_type,
            "quality": quality,
            "status": "starting",
            "percent": 0,
            "speed": "Initializing...",
            "eta": "...",
            "downloaded_bytes": "0 B",
            "total_bytes": "...",
            "filename": None,
            "error": None,
            "start_time": time.time()
        }

    thread = threading.Thread(target=run_download_task, args=(task_id, url, format_type, quality), daemon=True)
    thread.start()

    return jsonify({"success": True, "task_id": task_id})

@app.route("/api/progress/<task_id>")
def get_progress(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "Task not found"}), 404
        return jsonify({"success": True, "task": task})

@app.route("/api/file/<task_id>")
def serve_file(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
        if not task or task.get("status") != "completed":
            return jsonify({"error": "File not ready or task not found"}), 404
        filename = task.get("filename")

    if not filename:
        return jsonify({"error": "No file associated with this task"}), 404

    target_path = DOWNLOADS_DIR / filename
    if not target_path.exists():
        return jsonify({"error": "File not found on server disk"}), 404

    return send_file(target_path, as_attachment=True, download_name=filename)

@app.route("/api/library", methods=["GET"])
def get_library():
    files = []
    for file in DOWNLOADS_DIR.iterdir():
        if file.is_file():
            stat = file.stat()
            ext = file.suffix.lower().replace(".", "")
            files.append({
                "name": file.name,
                "size": format_bytes(stat.st_size),
                "ext": ext,
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                "mtime": stat.st_mtime,
                "download_url": f"/downloads/{file.name}"
            })

    files.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify({"success": True, "files": files, "count": len(files)})

@app.route("/downloads/<path:filename>")
def download_library_file(filename):
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)

@app.route("/api/open-folder", methods=["POST"])
def open_folder():
    try:
        if sys.platform == "win32":
            os.startfile(DOWNLOADS_DIR)
        elif sys.platform == "darwin":
            os.system(f'open "{DOWNLOADS_DIR}"')
        else:
            os.system(f'xdg-open "{DOWNLOADS_DIR}"')
        return jsonify({"success": True, "path": str(DOWNLOADS_DIR)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/delete-file", methods=["POST"])
def delete_file():
    data = request.get_json(force=True) or {}
    filename = data.get("filename", "")
    if not filename:
        return jsonify({"success": False, "error": "No filename provided"}), 400

    target = DOWNLOADS_DIR / filename
    if not target.resolve().is_relative_to(DOWNLOADS_DIR.resolve()):
        return jsonify({"success": False, "error": "Forbidden path"}), 403

    if target.exists() and target.is_file():
        try:
            target.unlink()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": False, "error": "File does not exist"}), 404

def open_browser(port):
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{port}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    is_cloud = os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER") or os.environ.get("DYNO")
    print(f"=====================================================")
    print(f" YouTube Downloader running on port {port}")
    print(f" FFmpeg status: {'Available (' + FFMPEG_PATH + ')' if FFMPEG_PATH else 'Not detected (cloud mode)'}")
    print(f" Downloads folder: {DOWNLOADS_DIR}")
    print(f" Cloud mode: {'YES' if is_cloud else 'NO (local)'}")
    print(f"=====================================================")
    # Only auto-open browser when running locally
    if not is_cloud:
        threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False)
