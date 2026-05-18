#!/usr/bin/env bash
# Arranca el backend FastAPI local con el venv y el .env del proyecto.
# Uso (Git Bash en Windows): ./run-backend.sh
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d venv ]; then
  echo "ERROR: falta venv/. Corré: python -m venv venv && source venv/Scripts/activate && pip install -r backend/requirements.txt"
  exit 1
fi

if [ ! -f .env ]; then
  echo "ERROR: falta .env en la raíz del proyecto"
  exit 1
fi

source venv/Scripts/activate
exec uvicorn backend.main:app --reload --port 8000 --env-file .env
