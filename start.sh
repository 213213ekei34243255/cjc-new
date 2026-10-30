#!/bin/bash
# Gemini is the main model and needs nothing here. Qwen (llama-server) is only the backup, so it
# starts in the background: the web app is up immediately, and a Qwen problem can never stop it.
set -e

export LD_LIBRARY_PATH=/opt/llama:$LD_LIBRARY_PATH

MODEL_DIR="/var/data/models"
MODEL_FILE="$MODEL_DIR/qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"

start_qwen() {
    mkdir -p "$MODEL_DIR"
    if [ ! -f "$MODEL_FILE" ]; then
        echo "Downloading Qwen backup model (first boot only)..."
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
