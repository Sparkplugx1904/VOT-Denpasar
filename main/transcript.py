import whisper
from pathlib import Path
import requests
import sys
import torchaudio
import torch
from pydub import AudioSegment
import webrtcvad
import numpy as np
import tempfile

# -------------------------
# Pakai backend sox_io agar mp3 bisa langsung dibaca
# -------------------------
torchaudio.set_audio_backend("sox_io")

# -------------------------
# Fungsi convert mp3 ke wav
# -------------------------
def mp3_to_wav(mp3_path):
    wav_path = str(Path(mp3_path).with_suffix(".wav"))
    audio = AudioSegment.from_file(mp3_path)
    audio.export(wav_path, format="wav")
    return wav_path

# -------------------------
# Fungsi bantu VAD
# -------------------------
def vad_split(audio_path, aggressiveness=3, sample_rate=16000):
    """
    Memotong audio menjadi segmen yang hanya mengandung suara manusia.
    - aggressiveness: 0-3 (3 = paling agresif menghilangkan noise)
    """
    audio, sr = torchaudio.load(audio_path)
    if sr != sample_rate:
        audio = torchaudio.transforms.Resample(sr, sample_rate)(audio)
        sr = sample_rate

    # Mono audio
    if audio.shape[0] > 1:
        audio = torch.mean(audio, dim=0, keepdim=True)
    audio = audio.squeeze().numpy()

    # Konversi ke PCM16
    audio_pcm16 = (audio * 32768).astype(np.int16)

    vad = webrtcvad.Vad(aggressiveness)
    frame_duration = 30  # ms
    frame_size = int(sr * frame_duration / 1000)
    
    segments = []
    for i in range(0, len(audio_pcm16), frame_size):
        frame = audio_pcm16[i:i+frame_size].tobytes()
        if len(frame) < frame_size*2:  # PCM16 = 2 byte
            break
        if vad.is_speech(frame, sr):
            segments.append(audio_pcm16[i:i+frame_size])

    if len(segments) == 0:
        return audio_path  # fallback jika VAD gagal

    # Gabungkan kembali ke audio
    vad_audio = np.concatenate(segments).astype(np.int16)
    # Simpan sementara
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    torchaudio.save(tmp_file.name, torch.from_numpy(vad_audio).unsqueeze(0), sample_rate)
    return tmp_file.name

# -------------------------
# Main script
# -------------------------
if len(sys.argv) < 2:
    print("Usage: python transcript.py <audio_url> [model_name]")
    sys.exit(1)

url = sys.argv[1]
model_name = sys.argv[2] if len(sys.argv) >= 3 else "small"
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

# Convert ke WAV supaya VAD aman
wav_path = mp3_to_wav(audio_path)

# Proses VAD
print("Memproses VAD untuk memfilter suara manusia...")
vad_audio_path = vad_split(wav_path)

# Transkripsi
print("Mulai transkripsi lokal... (ini bisa butuh waktu beberapa menit)")
try:
    result = model.transcribe(
        str(vad_audio_path),
        language="id",
        condition_on_previous_text=False
    )
except Exception as e:
    print(f"[ ! ] Terjadi kesalahan saat transkripsi: {e}")
    sys.exit(1)

print("Transkripsi selesai!")

# Simpan hasil
output_txt = audio_path.with_suffix(".txt")
with open(output_txt, "w", encoding="utf-8") as f:
    f.write(result["text"])

print("Hasil transkripsi disimpan ke:", output_txt)

# Tampilkan hasil ke terminal
print("\n=== HASIL TRANSKRIPSI ===\n")
text = result["text"]
max_len = 1024
while len(text) > 0:
    if len(text) <= max_len:
        print(text)
        break
    split_index = text.rfind(" ", 0, max_len)
    if split_index == -1:
        split_index = max_len
    chunk = text[:split_index].strip()
    print(chunk)
    text = text[split_index:].strip()
