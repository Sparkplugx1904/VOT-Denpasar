import requests
import subprocess
import time
import datetime
import signal
import sys
import os

# Zona waktu WITA (UTC+8)
WITA_OFFSET = datetime.timedelta(hours=8)

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

    cmd = ["ffmpeg", "-y", "-i", url, "-c", "copy", "-t", "60", filename]
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

if __name__ == "__main__":
    stream_url = "https://i.klikhost.com:8074/stream"
    #wait_for_stream(stream_url)
    #wait_until_17_wita()
    run_ffmpeg(stream_url)
    print("[ DONE ] Semua tugas selesai.")
