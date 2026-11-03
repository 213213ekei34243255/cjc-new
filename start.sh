#!/bin/bash
# Gemini is the main model and needs nothing here. Qwen (llama-server) is only the backup, so it
# starts in the background: the web app is up immediately, and a Qwen problem can never stop it.
set -e

export LD_LIBRARY_PATH=/opt/llama:$LD_LIBRARY_PATH

# Noah's database lives on your Render disk (the app finds it: noah/config.py, or set NOAH_DB_PATH).
# Work out which folder that is, so the Qwen model can sit next to it when there is plenty of room.
DATA_DIR="${NOAH_DATA_DIR:-}"
if [ -z "$DATA_DIR" ] && [ -n "${NOAH_DB_PATH:-}" ]; then
    DATA_DIR="$(dirname "$NOAH_DB_PATH")"
fi
if [ -z "$DATA_DIR" ]; then
    for d in /var/data/staff /var/data /data; do
        if [ -d "$d" ] && [ -w "$d" ]; then
            DATA_DIR="$d"
            break
        fi
    done
fi

# The model is about 1 GB. It only goes on the disk when more than 4 GB is free, so it can never fill the disk
# that holds the database. Otherwise it goes to /tmp and is downloaded again after a restart (the app keeps working meanwhile).
MODEL_DIR="${NOAH_MODEL_DIR:-}"
if [ -z "$MODEL_DIR" ]; then
    MODEL_DIR="/tmp/models"
    if [ -n "$DATA_DIR" ] && [ -d "$DATA_DIR" ]; then
        FREE_KB="$(df -Pk "$DATA_DIR" 2>/dev/null | awk 'NR==2 {print $4}')"
        if [ -n "$FREE_KB" ] && [ "$FREE_KB" -gt 4000000 ]; then
            MODEL_DIR="$DATA_DIR/models"
        fi
    fi
fi
MODEL_FILE="$MODEL_DIR/qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"

echo "Data folder: ${DATA_DIR:-none found}   Qwen model folder: $MODEL_DIR"

start_qwen() {
    mkdir -p "$MODEL_DIR"
    if [ ! -f "$MODEL_FILE" ]; then
        echo "Downloading Qwen backup model..."
        curl -L -C - "$MODEL_URL" -o "$MODEL_FILE" || { echo "Qwen download failed; backup model disabled."; return; }
    fi
    echo "Starting llama-server (Qwen backup)..."
    /opt/llama/llama-server -m "$MODEL_FILE" --host 127.0.0.1 --port 8080 || echo "llama-server exited; Gemini is unaffected."
}

if [ "${QWEN_ENABLED:-1}" != "0" ]; then
    ( start_qwen ) > /tmp/qwen.log 2>&1 &
fi

echo "Starting Gunicorn (Gemini primary: ${GEMINI_MODEL:-gemini-3.5-flash-lite})..."
# 8 threads: each open chat stream holds one thread while words are being sent.
exec gunicorn app:app \
    --bind 0.0.0.0:${PORT:-10000} \
    --workers 1 \
    --threads 8 \
    --worker-class gthread \
    --timeout 120 \
    --graceful-timeout 30
