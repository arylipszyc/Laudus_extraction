FROM python:3.12-slim

WORKDIR /app

# git + ssh: el backend clona el ledger Beancount al startup (deploy key) para
# poder leerlo y correr el importer on-demand (Story 9.11 cutover).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application
COPY backend/ ./backend/

# Copy pipeline package (sync, models, services, config, utils)
COPY pipeline/ ./pipeline/

EXPOSE 8000

COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
