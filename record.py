import requests
import subprocess
import time
import datetime
import signal
import sys
import os
import json
from internetarchive import upload  # library untuk upload ke archive.org

# Zona waktu WITA (UTC+8)
WITA_OFFSET = datetime.timedelta(hours=8)

# Ambil email dan password dari environment variable (GitHub Secrets)
EMAIL = os.environ.get("MY_ACC")
PASSWORD = os.environ.get("MY_PASS")

if not EMAIL or not PASSWORD:
    print("[ERROR] GitHub secrets MY_ACC atau MY_PASS belum diset!")
    sys.exit(1)

RECORDINGS_JSON = "recording.json"

def now_wita():
    return datetime.datetime.utcnow() + WITA_OFFSET

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
    import subprocess
    import sys
    import os
    import time
    import requests
    import signal

    date_str = now_wita().strftime("%d-%m-%y")
    os.makedirs("recordings", exist_ok=True)

    # Deteksi codec audio stream
    probe_cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name",
        "-of", "default=nokey=1:noprint_wrappers=1", url
    ]
    codec = subprocess.check_output(probe_cmd).decode().strip()

    ext_map = {"aac": "aac", "mp3": "mp3", "opus": "opus", "vorbis": "ogg"}
    ext = ext_map.get(codec, "bin")  # default bin jika codec tidak dikenali

    # Tambahkan suffix (contoh: -0, -1, dst)
    filename = f"recordings/VOT-Denpasar_{date_str}{suffix}.{ext}"

    cmd = [
        "ffmpeg",
        "-y",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "10",
        "-i", url,
        "-t", "7200",
        "-c", "copy",
        filename
    ]
    print(f"[ RUN ] Mulai rekaman ke {filename}")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # tampilkan log ffmpeg dengan overwrite (tanpa numpuk)
    def log_ffmpeg(proc):
        for line in proc.stderr:
            msg = "[FFMPEG] " + line.strip()
            sys.stdout.write("\r" + msg + " " * 10)
            sys.stdout.flush()
        print()  # newline setelah selesai

    import threading
    threading.Thread(target=log_ffmpeg, args=(process,), daemon=True).start()

    start_time = time.time()
    last_check = 0
    fail_count = 0

    while True:
        now = now_wita()

        # setiap 5 menit cek stream dengan HEAD
        if time.time() - last_check >= 300:
            last_check = time.time()
            try:
                resp = requests.head(url, timeout=10)
                if resp.status_code == 200:
                    fail_count = 0
                else:
                    fail_count += 1
                    print(f"\n[ ! ] Ping gagal (status {resp.status_code}), fail={fail_count}/15")
            except Exception as e:
                fail_count += 1
                print(f"\n[ ! ] Ping error: {e}, fail={fail_count}/15")

            if fail_count >= 3:
                print("\n[ CUT-OFF ] 3x gagal ping, hentikan rekaman...")
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                break

        # cut-off manual waktu tertentu
        if now.hour == 18 and now.minute >= 30:
            print("\n[ CUT-OFF ] Sudah 18.30 WITA, hentikan ffmpeg...")
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
        update_recording_json(date_str, archive_url)

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

def update_recording_json(date_str, url):
    data = []
    # baca file json lama jika ada
    if os.path.exists(RECORDINGS_JSON):
        try:
            with open(RECORDINGS_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[WARN] Gagal membaca {RECORDINGS_JSON}: {e}")

    # tambahkan entry baru DI ATAS (prepend)
    data.insert(0, {
        "title": "VOT-Denpasar",
        "tanggal": date_str,
        "url": url
    })

    # simpan kembali
    try:
        with open(RECORDINGS_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"[ JSON ] recording.json diperbarui, total {len(data)} entry.")
    except Exception as e:
        print(f"[ERROR] Gagal menulis {RECORDINGS_JSON}: {e}")

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
