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
        time.sleep(30)

def wait_until_17_wita():
    while True:
        now = now_wita()
        if now.hour >= 17:
            print("[ OK ] Sudah lewat jam 17.00 WITA, lanjut...")
            return
        else:
            sisa = ((17 - now.hour) * 3600) - (now.minute * 60 + now.second)
            print(f"[ ... ] Tunggu hingga 17.00 WITA ({sisa//60} menit lagi)")
            time.sleep(60)

def run_ffmpeg(url):
    date_str = now_wita().strftime("%d-%m-%y")
    filename = f"recordings/VOT-Denpasar_{date_str}.mp3"
    os.makedirs("recordings", exist_ok=True)

    cmd = ["ffmpeg", "-y", "-i", url, "-c", "copy", "-t", "10", filename]
    print(f"[ RUN ] Mulai rekaman ke {filename}")
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    start_time = time.time()
    while True:
        now = now_wita()
        elapsed = int(time.time() - start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        sys.stdout.write(f"\r[ TIMER ] {h:02}:{m:02}:{s:02}")
        sys.stdout.flush()

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
            with open(RECORDINGS_JSON, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[WARN] Gagal membaca {RECORDINGS_JSON}: {e}")

    # tambahkan entry baru
    data.append({
        "tanggal": date_str,
        "url": url
    })

    # simpan kembali
    try:
        with open(RECORDINGS_JSON, "w") as f:
            json.dump(data, f, indent=4)
        print(f"[ JSON ] recording.json diperbarui, total {len(data)} entry.")
    except Exception as e:
        print(f"[ERROR] Gagal menulis {RECORDINGS_JSON}: {e}")

if __name__ == "__main__":
    stream_url = "https://i.klikhost.com:8074/stream"
    # wait_for_stream(stream_url)
    # wait_until_17_wita()
    run_ffmpeg(stream_url)
    print("[ DONE ] Semua tugas selesai.")
