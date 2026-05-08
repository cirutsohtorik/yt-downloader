from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import uuid
import subprocess
import re

app = Flask(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


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
        "skip_download": True,
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
        "audio_qualities": sorted(
            list(set(audio_bitrates))
        )
    }


def cut_mp4(input_file, output_file, start_time, end_time):

    command = [
        "ffmpeg",
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

    subprocess.run(command, check=True)


def cut_mp3(input_file, output_file, start_time, end_time):

    command = [
        "ffmpeg",
        "-y",
        "-ss", start_time,
        "-i", input_file,
        "-to", end_time,
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", "192k",
        output_file
    ]

    subprocess.run(command, check=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/info", methods=["POST"])
def api_info():

    data = request.get_json()

    url = data.get("url")

    if not url:
        return jsonify({
            "success": False
        })

    try:

        video = get_video_info(url)

        return jsonify({
            "success": True,
            "video": video
        })

    except:
        return jsonify({
            "success": False
        })


@app.route("/download", methods=["POST"])
def download():

    url = request.form.get("url")
    file_type = request.form.get("file_type")
    quality = request.form.get("quality")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")

    if not url:
        return "URL boş.", 400

    try:

        video = get_video_info(url)

        duration_seconds = video["duration"]

        start_seconds = hhmmss_to_seconds(start_time)
        end_seconds = hhmmss_to_seconds(end_time)

        if end_seconds > duration_seconds:

            return render_template(
                "index.html",
                server_error="Bitiş süresi video süresini geçiyor."
            )

        if start_seconds >= end_seconds:

            return render_template(
                "index.html",
                server_error="Başlangıç süresi bitiş süresinden büyük olamaz."
            )

        safe_title = sanitize_filename(
            video["title"]
        )

        if file_type == "mp3":

            final_name = f"{safe_title}_sound.mp3"

            downloaded_file = os.path.join(
                DOWNLOAD_DIR,
                f"{uuid.uuid4()}.mp3"
            )

            cut_output = os.path.join(
                DOWNLOAD_DIR,
                final_name
            )

            ydl_opts = {

                "format": "bestaudio/best",

                "outtmpl":
                downloaded_file.replace(
                    ".mp3",
                    ".%(ext)s"
                ),

                "postprocessors": [
                    {
                        "key":
                        "FFmpegExtractAudio",

                        "preferredcodec":
                        "mp3",

                        "preferredquality":
                        quality,
                    }
                ],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            cut_mp3(
                downloaded_file,
                cut_output,
                start_time,
                end_time
            )

            return send_file(
                cut_output,
                as_attachment=True,
                download_name=final_name
            )

        else:

            final_name = f"{safe_title}_video.mp4"

            downloaded_file = os.path.join(
                DOWNLOAD_DIR,
                f"{uuid.uuid4()}.mp4"
            )

            cut_output = os.path.join(
                DOWNLOAD_DIR,
                final_name
            )

            quality_map = {

                "360":
                "bestvideo[height<=360]+bestaudio/best",

                "480":
                "bestvideo[height<=480]+bestaudio/best",

                "720":
                "bestvideo[height<=720]+bestaudio/best",

                "1080":
                "bestvideo[height<=1080]+bestaudio/best",

                "best":
                "bestvideo+bestaudio/best",
            }

            ydl_opts = {

                "format":
                quality_map.get(
                    quality,
                    "bestvideo+bestaudio/best"
                ),

                "outtmpl":
                downloaded_file.replace(
                    ".mp4",
                    ".%(ext)s"
                ),

                "merge_output_format":
                "mp4",
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            cut_mp4(
                downloaded_file,
                cut_output,
                start_time,
                end_time
            )

            return send_file(
                cut_output,
                as_attachment=True,
                download_name=final_name
            )

    except Exception as e:

        return f"Hata oluştu: {str(e)}", 500


if __name__ == "__main__":
    app.run(debug=True)