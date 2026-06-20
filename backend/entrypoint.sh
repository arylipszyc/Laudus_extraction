#!/bin/sh
# Ledger Beancount (Story 9.11 cutover): la imagen no trae ledger/, así que lo
# clonamos vía SSH (deploy key) para que el backend pueda LEER el ledger (endpoints
# beancount) y correr el importer on-demand. Solo si hay deploy key (flag activo).
# BEANCOUNT_DEPLOY_KEY guardada base64 (evita mangling de newlines), igual que el cron.
if [ -n "$BEANCOUNT_DEPLOY_KEY" ]; then
    mkdir -p /root/.ssh
    printf '%s' "$BEANCOUNT_DEPLOY_KEY" | base64 -d > /root/.ssh/id_ed25519
    chmod 600 /root/.ssh/id_ed25519
    ssh-keyscan -t ed25519 github.com >> /root/.ssh/known_hosts 2>/dev/null
    export GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519 -o IdentitiesOnly=yes"
    git config --global user.email "importer-laudus@familyoffice.eag"
    git config --global user.name  "laudus-backend (render)"
    git config --global --add safe.directory '*'
    rm -rf /app/ledger-repo
    git clone "$BEANCOUNT_REPO_URL" /app/ledger-repo
    export LEDGER_DIR=/app/ledger-repo/ledger
    export LEDGER_PATH=/app/ledger-repo/ledger/main.beancount
fi

exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
