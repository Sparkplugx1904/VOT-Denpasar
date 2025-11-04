import whisper
from pathlib import Path
import requests
import sys

# Pastikan ada minimal 1 argumen (URL)
if len(sys.argv) < 2:
    print("Usage: python transcript.py <audio_url> [model_name]")
    print("Example: python transcript.py 'https://example.com/audio.mp3' small")
    sys.exit(1)

# Ambil URL dan model dari argumen
url = sys.argv[1]
model_name = sys.argv[2] if len(sys.argv) >= 3 else "small"

# File audio akan disimpan berdasarkan nama dari URL
audio_path = Path(url.split("/")[-1])

print(f"Memuat model lokal: {model_name}")
model = whisper.load_model(model_name)

# Unduh file jika belum ada
if not audio_path.exists():
    print(f"Mengunduh audio dari: {url}")
    response = requests.get(url)
    if response.status_code == 200:
        audio_path.write_bytes(response.content)
        print("Selesai mengunduh:", audio_path)
    else:
        print(f"[ ! ] Gagal mengunduh audio, status code: {response.status_code}")
        sys.exit(1)
else:
    print("File sudah ada:", audio_path)

# Proses transkripsi
print("Mulai transkripsi lokal... (ini bisa butuh waktu beberapa menit)")
try:
    result = model.transcribe(str(audio_path), language="id")
except Exception as e:
    print(f"[ ! ] Terjadi kesalahan saat transkripsi: {e}")
    sys.exit(1)

print("Transkripsi selesai!")

# Simpan hasil ke file teks
output_txt = audio_path.with_suffix(".txt")
with open(output_txt, "w", encoding="utf-8") as f:
    f.write(result["text"])

print("Hasil transkripsi disimpan ke:", output_txt)

# Tampilkan hasil ke terminal
print("\n=== HASIL TRANSKRIPSI ===\n")

text = result["text"]
max_len = 1024

# Selama masih ada teks yang tersisa
while len(text) > 0:
    # Jika sisa teks masih pendek, cetak dan hentikan
    if len(text) <= max_len:
        print(text)
        break

    # Jika panjang lebih dari 1024, cari spasi terakhir sebelum batas
    split_index = text.rfind(" ", 0, max_len)

    # Jika tidak ada spasi, paksa potong di 1024
    if split_index == -1:
        split_index = max_len

    # Ambil bagian pertama dan cetak
    chunk = text[:split_index].strip()
    print(chunk)

    # Hapus bagian yang sudah dicetak dari teks
    text = text[split_index:].strip()
