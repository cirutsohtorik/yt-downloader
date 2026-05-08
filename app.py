from flask import Flask, render_template, request, jsonify
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


FFMPEG_PATH = resource_path("ffmpeg.exe")


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
    name = re.sub(r'[^a-zA-Z0-9_ğüşıöçĞÜŞİÖÇ]', '', name)
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

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": temp_input,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            temp_downloaded = None

            for file in os.listdir(TEMP_DIR):
                if file.startswith(temp_id):
                    temp_downloaded = os.path.join(TEMP_DIR, file)
                    break

            if not temp_downloaded:
                return jsonify({
                    "success": False,
                    "error": "Ses dosyası indirilemedi."
                })

            convert_audio(
                temp_downloaded,
                save_path,
                start_time,
                end_time,
                quality
            )

        else:
            max_height = video["max_height"]

            if quality != "best":
                selected_quality = int(quality)

                if max_height and selected_quality > max_height:
                    return jsonify({
                        "success": False,
                        "error": f"Bu video en fazla {max_height}p destekliyor."
                    })

            temp_input = os.path.join(
                TEMP_DIR,
                f"{temp_id}.%(ext)s"
            )

            quality_map = {
                "360": "bestvideo[height<=360]+bestaudio/best[height<=360]",
                "480": "bestvideo[height<=480]+bestaudio/best[height<=480]",
                "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
                "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
                "best": "bestvideo+bestaudio/best",
            }

            ydl_opts = {
                "format": quality_map.get(
                    quality,
                    "bestvideo+bestaudio/best"
                ),
                "outtmpl": temp_input,
                "merge_output_format": "mp4",
                "ffmpeg_location": FFMPEG_PATH,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            temp_downloaded = None

            for file in os.listdir(TEMP_DIR):
                if file.startswith(temp_id) and file.endswith(".mp4"):
                    temp_downloaded = os.path.join(TEMP_DIR, file)
                    break

            if not temp_downloaded:
                return jsonify({
                    "success": False,
                    "error": "Video dosyası indirilemedi."
                })

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