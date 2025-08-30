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
        time.sleep(15)

def run_ffmpeg(url):
    date_str = now_wita().strftime("%d-%m-%y")
    filename = f"recordings/VOT-Denpasar_{date_str}.mp3"
    os.makedirs("recordings", exist_ok=True)

    cmd = ["ffmpeg", "-y", "-i", url, "-c", "copy", "-t", "7200", filename]
    print(f"[ RUN ] Mulai rekaman ke {filename}")
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    start_time = time.time()
    last_check = 0
    fail_count = 0

    while True:
        now = now_wita()
        elapsed = int(time.time() - start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        sys.stdout.write(f"\r[ TIMER ] {h:02}:{m:02}:{s:02}")
        sys.stdout.flush()

        # setiap 1 menit lakukan call HEAD ke stream URL
        if time.time() - last_check >= 60:
            last_check = time.time()
            try:
                resp = requests.head(url, timeout=10)
                if resp.status_code == 200:
                    print(f"\n[ OK ] Ping stream {url} → 200 OK")
                    fail_count = 0
                else:
                    fail_count += 1
                    print(f"\n[ ! ] Ping gagal (status {resp.status_code}), fail={fail_count}/15")
            except Exception as e:
                fail_count += 1
                print(f"\n[ ! ] Ping error: {e}, fail={fail_count}/15")

            # stop ffmpeg jika gagal 15 kali beruntun
            if fail_count >= 15:
                print("\n[ CUT-OFF ] 15x gagal ping, hentikan rekaman...")
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                break

        # cut-off normal di 18:30 WITA
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
    stream_url = "https://i.klikhost.com:8074/stream"
    wait_for_stream(stream_url)
    run_ffmpeg(stream_url)
    print("\n[ DONE ] Semua tugas selesai.")
