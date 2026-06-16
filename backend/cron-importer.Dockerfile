# Imagen del Cron Job del importer Laudus (Story 9.4) — separada del web service
# (backend/Dockerfile) porque necesita git + ssh-client y un entrypoint que clona
# el ledger en runtime. dockerContext = raiz del repo (igual que el web service).
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Mismas deps que el backend (incluye beancount/beanquery/requests/google-genai).
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY pipeline/ ./pipeline/

COPY backend/cron-importer-entry.sh ./cron-importer-entry.sh
RUN chmod +x ./cron-importer-entry.sh

ENTRYPOINT ["./cron-importer-entry.sh"]
