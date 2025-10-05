#!/bin/bash

# URL stream
url="https://i.klikhost.com:8502"

# Tanggal sekarang untuk nama file dan metadata
date_str=$(date +%Y-%m-%d)
filename="recording_${date_str}.mp3"

# Looping infinite supaya auto-reconnect saat FFmpeg exit
while true; do
    /workspaces/VOT-Denpasar/bin/ffmpeg -y \
        -reconnect 1 \
        -reconnect_at_eof 1 \
        -reconnect_streamed 1 \
        -reconnect_delay_max 10 \
        -reconnect_on_network_error 1 \
        -reconnect_on_http_error 401,403,404,500,502,503 \
        -timeout 5000000 \
        -i "$url" \
        -c copy \
        -metadata "title=VOT Denpasar $date_str" \
        -metadata "artist=VOT Radio Denpasar" \
        -metadata "date=$date_str" \
        "$filename"

    echo "⚠️ FFmpeg stopped, retrying in 1 seconds..."
    sleep 1
done
