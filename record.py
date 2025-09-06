import requests
import subprocess
import time
import datetime
import signal
import sys
import os
from internetarchive import upload
import threading
import re

# Add to path
os.system("chmod +x ffmpeg ffprobe")

# Zona waktu WITA (UTC+8)
WITA_OFFSET = datetime.timedelta(hours=8)
WITA_TZ = datetime.timezone(WITA_OFFSET)

# Ambil email dan password dari environment variable (GitHub Secrets)
EMAIL = os.environ.get("MY_ACC")
PASSWORD = os.environ.get("MY_PASS")

if not EMAIL or not PASSWORD:
    print("[ERROR] GitHub secrets MY_ACC atau MY_PASS belum diset!")
    sys.exit(1)

def now_wita():
    return datetime.datetime.now(datetime.UTC).astimezone(WITA_TZ)

def wait_for_stream(url):
    while True:
        try:
            resp = requests.head(url, timeout=10)
            if resp.status_code == 200:
                print(f"[ OK ] Stream tersedia {url}")
                return
            else:
                print(f"[ ! ] Status {resp.status_code}, coba lagi 30 detik...")
        except Exception as e:
            print(f"[ ! ] Error: {e}, coba lagi 30 detik...")
        time.sleep(5)

def run_ffmpeg(url, suffix=""):
    date_str = now_wita().strftime("%d-%m-%y")
    os.makedirs("recordings", exist_ok=True)

    # Deteksi codec audio stream
    probe_cmd = [
        "./ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name",
        "-of", "default=nokey=1:noprint_wrappers=1", url
    ]
    codec = subprocess.check_output(probe_cmd).decode().strip()

    ext_map = {"aac": "aac", "mp3": "mp3", "opus": "opus", "vorbis": "ogg"}
    ext = ext_map.get(codec, "bin")

    filename = f"recordings/VOT-Denpasar_{date_str}{suffix}.{ext}"

    cmd = [
        "./ffmpeg",
        "-y",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "10",
        "-i", url,
        "-c", "copy",
        "-metadata", f"title=VOT Denpasar {date_str}",
        "-metadata", "artist=VOT Radio Denpasar",
        "-metadata", f"date={date_str}",
        filename
    ]

    print(f"[ RUN ] Mulai rekaman ke {filename}")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    last_sound_time = now_wita()

    def log_ffmpeg(proc):
        nonlocal last_sound_time
        silence_re = re.compile(r"silence_(start|end)")

        for line in proc.stderr:
            msg = "[FFMPEG] " + line.strip()
            sys.stdout.write("\r" + msg + " " * 10)
            sys.stdout.flush()

            if "silence_end" in line:
                last_sound_time = now_wita()
            elif "silence_start" in line:
                # biarkan, karena ffmpeg log sudah nyebut kapan dimulai
                pass
        print()

    threading.Thread(target=log_ffmpeg, args=(process,), daemon=True).start()

    while True:
        now = now_wita()

        # cut-off otomatis jam 18:30 WITA
        if now.hour == 18 and now.minute >= 30:
            print("\n[ CUT-OFF ] Sudah 18.30 WITA, hentikan ffmpeg...")
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            break

        # cek silence terlalu lama (5 menit)
        if (now - last_sound_time).total_seconds() > 300:
            print("\n[ SILENCE ] Tidak ada suara selama lebih dari 5 menit, menghentikan ffmpeg...")
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            break

        if process.poll() is not None:
            print("\n[ DONE ] Rekaman selesai lebih cepat.")
            break

        time.sleep(1)

    print(f"\n[ DONE ] Rekaman selesai: {filename}")
    archive_url = upload_to_archive(filename)
    if archive_url:
        print(f"[ ARCHIVE ] File tersedia di {archive_url}")

def upload_to_archive(file_path):
    print(f"[ UPLOAD ] Mulai upload {file_path} ke archive.org...")
    try:
        item_identifier = f"vot-denpasar-{now_wita().strftime('%Y%m%d-%H%M%S')}"
        upload(item_identifier,
               files=[file_path],
               metadata={
                   'mediatype': 'audio',
                   'title': os.path.basename(file_path),
                   'creator': 'VOT Radio Denpasar'
               },
               access_key=EMAIL,
               secret_key=PASSWORD,
               verbose=True)
        archive_url = f"https://archive.org/details/{item_identifier}"
        print(f"[ DONE ] Upload berhasil: {archive_url}")
        return archive_url
    except Exception as e:
        print(f"[ ERROR ] Upload gagal: {e}")
        return None

if __name__ == "__main__":
    # ambil argumen (misal: -0, -1, dst)
    suffix = ""
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.startswith("-"):
            suffix = arg  # simpan langsung, misal "-0"

    stream_url = "http://i.klikhost.com:8502/stream"
    wait_for_stream(stream_url)
    run_ffmpeg(stream_url, suffix)
    print("\n[ DONE ] Semua tugas selesai.")
