from flask import Flask, render_template, request, jsonify
import sys
import yt_dlp
import os
import uuid
import subprocess
import re
import sys

app = Flask(__name__)

TEMP_DIR = os.path.join(
    os.path.expanduser("~"),
    "AppData",
    "Local",
    "YT_Downloader_Temp"
)

os.makedirs(TEMP_DIR, exist_ok=True)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


if getattr(sys, 'frozen', False):
    FFMPEG_PATH = os.path.join(sys._MEIPASS, "ffmpeg.exe")
else:
    FFMPEG_PATH = "ffmpeg.exe"


def run_command_silent(command):
    startupinfo = None
    creationflags = 0

    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW

    subprocess.run(
        command,
        check=True,
        startupinfo=startupinfo,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def sanitize_filename(name):
    name = name.replace(" ", "_")

    name = re.sub(
        r'[^a-zA-Z0-9_ğüşıöçĞÜŞİÖÇ]',
        '',
        name
    )

    return name


def seconds_to_hhmmss(seconds):
    if seconds is None:
        return "00:00:00"

    seconds = int(seconds)

    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    return f"{h:02d}:{m:02d}:{s:02d}"


def hhmmss_to_seconds(time_str):
    h, m, s = map(int, time_str.split(":"))
    return h * 3600 + m * 60 + s


def get_video_info(url):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    heights = []
    audio_bitrates = []

    for fmt in info.get("formats", []):
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        abr = fmt.get("abr")

        if height and vcodec != "none":
            heights.append(height)

        if abr:
            audio_bitrates.append(int(abr))

    duration = info.get("duration")

    return {
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": duration,
        "duration_text": seconds_to_hhmmss(duration),
        "max_height": max(heights) if heights else None,
        "audio_qualities": sorted(list(set(audio_bitrates))) or [128, 192, 256, 320]
    }


def convert_audio(input_file, output_file, start_time, end_time, quality):
    command = [
        FFMPEG_PATH,
        "-y",
        "-ss", start_time,
        "-i", input_file,
        "-to", end_time,
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", f"{quality}k",
        output_file
    ]

    run_command_silent(command)


def convert_video(input_file, output_file, start_time, end_time):
    command = [
        FFMPEG_PATH,
        "-y",
        "-ss", start_time,
        "-i", input_file,
        "-to", end_time,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_file
    ]

    run_command_silent(command)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/info", methods=["POST"])
def api_info():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({
            "success": False,
            "error": "URL boş."
        })

    try:
        video = get_video_info(url)

        safe_title = sanitize_filename(video["title"])

        return jsonify({
            "success": True,
            "video": video,
            "safe_title": safe_title
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json()

    url = data.get("url")
    file_type = data.get("file_type")
    quality = data.get("quality")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    save_path = data.get("save_path")

    if not url:
        return jsonify({
            "success": False,
            "error": "URL boş."
        })

    if not save_path:
        return jsonify({
            "success": False,
            "error": "Kayıt yeri seçilmedi."
        })

    try:
        video = get_video_info(url)

        duration_seconds = video["duration"]

        start_seconds = hhmmss_to_seconds(start_time)
        end_seconds = hhmmss_to_seconds(end_time)

        if end_seconds > duration_seconds:
            return jsonify({
                "success": False,
                "error": "Bitiş süresi video süresini geçiyor."
            })

        if start_seconds >= end_seconds:
            return jsonify({
                "success": False,
                "error": "Başlangıç süresi bitiş süresinden büyük olamaz."
            })

        temp_id = str(uuid.uuid4())

        if file_type == "mp3":
            temp_input = os.path.join(
                TEMP_DIR,
                f"{temp_id}.%(ext)s"
            )

            temp_downloaded = os.path.join(
                TEMP_DIR,
                f"{temp_id}.m4a"
            )

            ydl_opts = {
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": temp_input,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if not os.path.exists(temp_downloaded):
                for file in os.listdir(TEMP_DIR):
                    if file.startswith(temp_id):
                        temp_downloaded = os.path.join(TEMP_DIR, file)
                        break

            convert_audio(
                temp_downloaded,
                save_path,
                start_time,
                end_time,
                quality
            )

        else:
            temp_input = os.path.join(
                TEMP_DIR,
                f"{temp_id}.%(ext)s"
            )

            temp_downloaded = os.path.join(
                TEMP_DIR,
                f"{temp_id}.mp4"
            )

            quality_map = {
                "360": "best[ext=mp4][height<=360]/best[height<=360]",
                "480": "best[ext=mp4][height<=480]/best[height<=480]",
                "720": "best[ext=mp4][height<=720]/best[height<=720]",
                "1080": "best[ext=mp4][height<=1080]/best[height<=1080]",
                "best": "best[ext=mp4]/best",
            }

            ydl_opts = {
                "format": quality_map.get(
                    quality,
                    "best[ext=mp4]/best"
                ),
                "outtmpl": temp_input,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if not os.path.exists(temp_downloaded):
                for file in os.listdir(TEMP_DIR):
                    if file.startswith(temp_id):
                        temp_downloaded = os.path.join(TEMP_DIR, file)
                        break

            convert_video(
                temp_downloaded,
                save_path,
                start_time,
                end_time
            )

        return jsonify({
            "success": True,
            "path": save_path
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


if __name__ == "__main__":
    app.run(debug=True)