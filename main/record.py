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

# --- Setup dasar ---
os.system("chmod +x ffmpeg ffprobe")

# Zona waktu WITA (UTC+8)
WITA_OFFSET = datetime.timedelta(hours=8)
WITA_TZ = datetime.timezone(WITA_OFFSET)

# Ambil MY_ACCESS_KEY dan MY_SECRET_KEY dari environment variable (GitHub Secrets)
MY_ACCESS_KEY = os.environ.get("MY_ACCESS_KEY")
MY_SECRET_KEY = os.environ.get("MY_SECRET_KEY")

def log(msg):
    """Tambahkan timestamp biru ke setiap log tanpa ubah isi pesan"""
    ts = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%H:%M:%S")
    print(f"\033[34m[{ts}]\033[0m {msg}", flush=True)

if not MY_ACCESS_KEY or not MY_SECRET_KEY:
    log("[ ERROR ] GitHub secrets MY_ACCESS_KEY atau MY_SECRET_KEY belum diset!")
    sys.exit(1)


def now_wita():
    """Waktu lokal WITA"""
    return datetime.datetime.now(datetime.UTC).astimezone(WITA_TZ)


def wait_for_stream(url):
    """Menunggu stream hingga online"""
    log(f"[ WAIT ] Menunggu stream {url}")
    while True:
        try:
            resp = requests.head(url, timeout=10)
            if resp.status_code == 200:
                log(f"[ OK ] Stream tersedia: {url}")
                return
            else:
                log(f"[ ! ] Status {resp.status_code}, coba lagi...")
        except Exception as e:
            log(f"[ ! ] Error: {e}")
        time.sleep(1)


def run_ffmpeg(url, suffix="", position=0):
    """Rekam stream audio dan upload"""
    date_str = now_wita().strftime("%d-%m-%y")
    os.makedirs("recordings", exist_ok=True)

    # Deteksi codec
    try:
        codec = subprocess.check_output([
            "./ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=nokey=1:noprint_wrappers=1", url
        ]).decode().strip()
    except subprocess.CalledProcessError:
        codec = "bin"

    ext_map = {"aac": "aac", "mp3": "mp3", "opus": "opus", "vorbis": "ogg"}
    ext = ext_map.get(codec, "bin")

    filename = f"recordings/VOT-Denpasar_{date_str}{('-' + suffix) if suffix else ''}.{ext}"

    # Jalankan ffmpeg
    cmd = [
        "./ffmpeg", "-y", "-hide_banner",
        "-reconnect", "1", "-reconnect_at_eof", "1",
        "-reconnect_streamed", "1", "-reconnect_delay_max", "0",
        "-reconnect_on_network_error", "1",
        "-reconnect_on_http_error", "4xx,5xx",
        "-timeout", "5000000",
        "-i", url, "-c", "copy",
        "-metadata", f"title=VOT Denpasar {date_str}",
        "-metadata", "artist=VOT Radio Denpasar",
        "-metadata", f"date={date_str}",
        filename
    ]

    log(f"[ RUN ] Mulai rekaman ke {filename}")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

    # Log thread untuk ffmpeg
    def log_ffmpeg(proc):
        for line in proc.stderr:
            now = datetime.datetime.now(WITA_TZ).strftime("%H:%M:%S")
            print(f"\r\033[34m[{now}]\033[0m [FFMPEG] {line.strip()}   ", end="", flush=True)
        print()

    threading.Thread(target=log_ffmpeg, args=(process,), daemon=True).start()

    # Tunggu hingga jam 18:30 WITA
    while True:
        now = now_wita()
        if now.hour == 18 and now.minute >= 30:
            log(f"[ CUT-OFF ] Sudah 18:30 WITA, hentikan ffmpeg...")
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            break

        if process.poll() is not None:
            log("[ FAIL ] ffmpeg berhenti tak terduga.")
            break

        time.sleep(1)

    log(f"[ DONE ] Rekaman selesai: {filename}")

    # Delay sebelum upload
    if position > 0:
        delay = position * 10
        log(f"[ DELAY ] Menunggu {delay} detik sebelum upload...")
        time.sleep(delay)

    # Upload ke archive.org
    archive_url, item_id = upload_to_archive(filename)

    if archive_url and item_id:
        log(f"[ ARCHIVE ] File tersedia di {archive_url}")
        write_env_variables(archive_url, item_id)
    else:
        write_env_variables("None", "None")


def upload_to_archive(file_path, retries=5):
    """Upload file ke archive.org dan hasilkan URL langsung + item_id, retry jika gagal"""
    log(f"[ UPLOAD ] Mulai upload {file_path} ke archive.org...")
    item_identifier = f"vot-denpasar-{now_wita().strftime('%Y%m%d-%H%M%S')}"
    filename = os.path.basename(file_path)

    for attempt in range(1, retries + 1):
        try:
            upload(
                item_identifier,
                files=[file_path],
                metadata={
                    'mediatype': 'audio',
                    'title': filename,
                    'creator': 'VOT Radio Denpasar'
                },
                access_key=MY_ACCESS_KEY,
                secret_key=MY_SECRET_KEY,
                verbose=True
            )

            details_url = f"https://archive.org/details/{item_identifier}"
            download_url = f"https://archive.org/download/{item_identifier}/{filename}"

            log(f"[ DONE ] Upload berhasil: {details_url}")
            log(f"[ LINK ] URL langsung: {download_url}")
            log(f"[ ITEM ] ID: {item_identifier}")

            return download_url, item_identifier

        except Exception as e:
            log(f"[ WARN ] Upload gagal percobaan {attempt}: {e}")
            if attempt < retries:
                log("[ RETRY ] Menunggu 10 detik sebelum mencoba lagi...")
                time.sleep(10)
            else:
                log("[ ERROR ] Semua percobaan upload gagal.")
                return None, None


def write_env_variables(url, item_id):
    """Kirim ARCHIVE_URL dan ITEM_ID langsung ke environment GitHub"""
    try:
        if "GITHUB_ENV" in os.environ:
            with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env_file:
                env_file.write(f"ARCHIVE_URL={url}\n")
                env_file.write(f"ITEM_ID={item_id}\n")
                env_file.flush()
                log(f"[ ENV ] ARCHIVE_URL dan ITEM_ID dikirim ke environment GitHub.")
        else:
            log("[ WARN ] GITHUB_ENV tidak tersedia (mungkin bukan di workflow).")
    except Exception as e:
        log(f"[ ERROR ] Gagal menulis environment: {e}")


def main_recording():
    parser = argparse.ArgumentParser(description="Record stream and upload")
    parser.add_argument("-s", "--suffix", type=str, default="", help="Suffix di akhir nama file")
    parser.add_argument("-p", "--position", type=int, default=0, help="Posisi untuk delay upload (delay = position * 10 detik)")
    args = parser.parse_args()

    stream_url = "http://i.klikhost.com:8502/stream"
    wait_for_stream(stream_url)
    run_ffmpeg(stream_url, args.suffix, args.position)
    log("[ DONE ] Semua tugas selesai.")
    return True


if __name__ == "__main__":
    log("[ START ] Memulai program recording dengan restart otomatis...")

    while True:
        now = now_wita()

        if (now.hour > 18) or (now.hour == 18 and now.minute >= 30):
            log(f"[ STOP ] Sudah jam {now.strftime('%H:%M')} WITA, hentikan program.")
            break

        try:
            main_recording()
        except Exception as e:
            log(f"[ ERROR ] Terjadi error: {e}")

        now = now_wita()
        if (now.hour > 18) or (now.hour == 18 and now.minute >= 30):
            log(f"[ STOP ] Setelah recording selesai, sudah jam {now.strftime('%H:%M')} WITA, hentikan program.")
            break
        else:
            log("[ RESTART ] Restarting recording loop...")
            continue

    log("[ END ] Program selesai.")
