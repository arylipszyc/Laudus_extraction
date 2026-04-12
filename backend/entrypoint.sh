#!/bin/sh
# Write Google Service Account credentials from env var to file at startup.
# This avoids committing the key file to the repo.
if [ -n "$GOOGLE_SERVICE_ACCOUNT_JSON" ]; then
    mkdir -p config
    printf '%s' "$GOOGLE_SERVICE_ACCOUNT_JSON" > config/serviceAccountKey.json
    export GOOGLE_APPLICATION_CREDENTIALS=config/serviceAccountKey.json
fi

exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
