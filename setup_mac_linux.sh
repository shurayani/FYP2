#!/usr/bin/env bash
# One-time setup + run for macOS / Linux.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-ocr.txt || echo "[WARNING] PaddleOCR install failed - IPECS still runs; use Gemini or manual entry."
[ -f .env ] || cp .env.example .env
python training/train_model.py
streamlit run app.py
