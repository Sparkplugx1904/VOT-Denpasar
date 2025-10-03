import requests
import subprocess
import time
import datetime
import signal
import sys
import os
import argparse
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
    last_error = None
    while True:
        try:
            resp = requests.head(url, timeout=10)
            if resp.status_code == 200:
                print(f"[ OK ] Stream tersedia {url}")
                return
            else:
                msg = f"Status {resp.status_code}"
                if msg != last_error:
                    print(f"[ ! ] {msg}, coba lagi 0.1 detik...")
                    last_error = msg
        except Exception as e:
            msg = str(e)
            if msg != last_error:
                print(f"[ ! ] Error: {msg}, coba lagi 0.1 detik...")
                last_error = msg
        time.sleep(0.1)

def run_ffmpeg(url, suffix="", position=0):
    date_str = now_wita().strftime("%d-%m-%y")
    os.makedirs("recordings", exist_ok=True)

    # Deteksi codec audio stream
    probe_cmd = [
        "./ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name",
        "-of", "default=nokey=1:noprint_wrappers=1", url
    ]
    try:
        codec = subprocess.check_output(probe_cmd).decode().strip()
    except subprocess.CalledProcessError:
        codec = "bin"

    ext_map = {"aac": "aac", "mp3": "mp3", "opus": "opus", "vorbis": "ogg"}
    ext = ext_map.get(codec, "bin")

    if suffix:
        filename = f"recordings/VOT-Denpasar_{date_str}-{suffix}.{ext}"
    else:
        filename = f"recordings/VOT-Denpasar_{date_str}.{ext}"

    def start_ffmpeg():
        cmd = [
            "./ffmpeg",
            "-y",
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "0",             # reconnect segera tanpa delay
            "-reconnect_on_network_error", "1",      # retry jika jaringan putus
            "-reconnect_on_http_error", "4xx,5xx",   # retry jika error HTTP
            "-timeout", "5000000",                   # timeout koneksi cepat
            "-i", url,
            "-c", "copy",
            "-metadata", f"title=VOT Denpasar {date_str}",
            "-metadata", "artist=VOT Radio Denpasar",
            "-metadata", f"date={date_str}",
            filename
        ]
        print(f"[ RUN ] Mulai rekaman ke {filename}")
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

    process = start_ffmpeg()
    last_sound_time = now_wita()

    def log_ffmpeg(proc):
        nonlocal last_sound_time
        for line in proc.stderr:
            msg = "[FFMPEG] " + line.strip()
            sys.stdout.write("\r" + msg + " " * 10)
            sys.stdout.flush()

            if "silence_end" in line:
                last_sound_time = now_wita()
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

        # kalau ffmpeg mati total → tunggu max 10 menit (biar tau bener-bener gagal reconnect)
        if process.poll() is not None:
            print("\n[ LOST ] ffmpeg berhenti, menunggu auto-reconnect max 10 menit...")
            wait_start = time.time()
            while time.time() - wait_start < 600:  # 10 menit
                if process.poll() is None:
                    print("[ OK ] ffmpeg berhasil reconnect sendiri.")
                    break
                time.sleep(0.1)

            if process.poll() is not None:
                print("[ FAIL ] ffmpeg tidak bisa reconnect selama 10 menit, stop rekaman.")
                break

        time.sleep(0.1)

    print(f"\n[ DONE ] Rekaman selesai: {filename}")
    if position > 0:
        delay = position * 10
        print(f"[ DELAY ] Menunggu {delay} detik sebelum upload...")
        time.sleep(delay)
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

def main_recording():
    """Main recording function that can be restarted"""
    parser = argparse.ArgumentParser(description="Record stream and upload with suffix and delay")
    parser.add_argument("-s", "--suffix", type=str, default="", help="Suffix to add at the end of filename")
    parser.add_argument("-p", "--position", type=int, default=0, help="Position to determine delay before upload (delay = position * 10 seconds)")
    args = parser.parse_args()

    stream_url = "http://i.klikhost.com:8502/stream"
    wait_for_stream(stream_url)
    run_ffmpeg(stream_url, args.suffix, args.position)
    print("\n[ DONE ] Semua tugas selesai.")
    return True

if __name__ == "__main__":
    print("[ START ] Memulai program recording dengan restart otomatis...")

    while True:
        now = now_wita()

        # Jika sudah jam 18:30 WITA atau lebih, hentikan program
        if (now.hour > 18) or (now.hour == 18 and now.minute >= 30):
            print(f"\n[ STOP ] Sudah jam {now.strftime('%H:%M')} WITA (>= 18:30), menghentikan program.")
            break

        # Jalankan recording
        print(f"\n[ RUN ] Memulai recording pada jam {now.strftime('%H:%M')} WITA")
        try:
            main_recording()
        except Exception as e:
            print(f"[ ERROR ] Terjadi error: {e}")

        # Cek waktu lagi setelah recording selesai
        now = now_wita()
        if (now.hour > 18) or (now.hour == 18 and now.minute >= 30):
            print(f"\n[ STOP ] Setelah recording selesai, sudah jam {now.strftime('%H:%M')} WITA (>= 18:30), menghentikan program.")
            break
        else:
            print(f"\n[ RESTART ] Recording selesai sebelum 18:30 WITA, akan restart program...")
            print("[ INFO ] Menunggu 0 detik sebelum restart...")
            continue

    print("\n[ END ] Program selesai.")
