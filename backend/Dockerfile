FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application
COPY backend/ ./backend/

# Copy existing pipeline modules (SheetsRepository imports from these)
COPY services/ ./services/
COPY config/ ./config/
COPY utils/ ./utils/

EXPOSE 8000

COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
