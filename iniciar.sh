#!/usr/bin/env bash
# Primera vez: crea el entorno virtual e instala todo. Después solo abre la app.
set -e
cd "$(dirname "$0")"
if ! command -v ffmpeg >/dev/null; then
  echo "Instalando ffmpeg…"; sudo apt update && sudo apt install -y ffmpeg
fi
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
.venv/bin/python app.py
