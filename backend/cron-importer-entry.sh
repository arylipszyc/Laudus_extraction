#!/usr/bin/env sh
# Render Cron Job entrypoint — importer Laudus → Beancount (Story 9.4).
#
# La imagen del cron no trae el ledger ni un working tree git. Como el ledger
# vive DENTRO de este mismo repo, clonamos el repo fresco via SSH en cada corrida
# (el clon aporta el ledger + un .git con origin SSH), corremos el importer contra
# el clon, y el `git push origin main` que el propio importer hace persiste el
# resultado. Sin disco persistente: el push ES la persistencia; el clon de la
# corrida siguiente levanta lo ultimo.
set -eu

# 1. Deploy key. Guardada base64 en BEANCOUNT_DEPLOY_KEY para evitar el mangling
#    de newlines al pasar por env vars / API.
mkdir -p /root/.ssh
printf '%s' "$BEANCOUNT_DEPLOY_KEY" | base64 -d > /root/.ssh/id_ed25519
chmod 600 /root/.ssh/id_ed25519
ssh-keyscan -t ed25519 github.com >> /root/.ssh/known_hosts 2>/dev/null
export GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519 -o IdentitiesOnly=yes"

# 2. Identidad git (para el commit del importer) + ownership relajado en el clon.
git config --global user.email "importer-laudus@familyoffice.eag"
git config --global user.name  "laudus-importer (render cron)"
git config --global --add safe.directory '*'

# 3. Clon fresco del repo. origin queda en SSH -> el push del importer usa la deploy key.
rm -rf /tmp/ledger-repo
git clone "$BEANCOUNT_REPO_URL" /tmp/ledger-repo

# 4. Importer contra el ledger clonado. Corre el codigo baked de la imagen (/app),
#    LEDGER_DIR apunta los reads/writes al clon. IMPORTER_BOOK explicito (FR50,
#    Story 12.2): este cron importa el libro EAG; sin libro el importer no corre.
export LEDGER_DIR=/tmp/ledger-repo/ledger
export IMPORTER_BOOK=EAG
cd /app
exec python -m pipeline.importers.laudus_run
