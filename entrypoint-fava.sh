#!/usr/bin/env bash
# Story 9.3 — entrypoint del servicio laudus-fava.
#   1. clona/pullea el ledger a /ledger (persistent disk)
#   2. genera htpasswd desde FAVA_BASIC_AUTH_USER/PASSWORD (AC2/AC6)
#   3. loop de git pull cada 60s (AC3/AC4 — Fava recarga vía watchfiles)
#   4. arranca Fava en 127.0.0.1:$FAVA_PORT y nginx (basic auth) en $PORT
set -euo pipefail

LEDGER_DIR="${LEDGER_DIR:-/ledger}"
FAVA_PORT="${FAVA_PORT:-5000}"
MAIN="${LEDGER_DIR}/main.beancount"
: "${PORT:?PORT no seteado (lo inyecta Render)}"
: "${FAVA_BASIC_AUTH_USER:?FAVA_BASIC_AUTH_USER requerido}"
: "${FAVA_BASIC_AUTH_PASSWORD:?FAVA_BASIC_AUTH_PASSWORD requerido}"
: "${BEANCOUNT_REPO_URL:?BEANCOUNT_REPO_URL requerido}"

# ── 1. ledger (clone o pull) ────────────────────────────────────────────────
if [ ! -d "${LEDGER_DIR}/.git" ]; then
  echo "[fava] clonando ledger en ${LEDGER_DIR}"
  git clone --depth 1 "${BEANCOUNT_REPO_URL}" "${LEDGER_DIR}"
else
  echo "[fava] ledger ya presente, pull inicial"
  git -C "${LEDGER_DIR}" pull --quiet || true
fi

# ── 2. basic auth (htpasswd) ────────────────────────────────────────────────
htpasswd -bc /tmp/htpasswd "${FAVA_BASIC_AUTH_USER}" "${FAVA_BASIC_AUTH_PASSWORD}"

# ── 3. git pull loop (refresh ≤ 60s) ────────────────────────────────────────
( while true; do sleep 60; git -C "${LEDGER_DIR}" pull --quiet || true; done ) &

# ── 4. Fava (localhost) + nginx (público con auth) ──────────────────────────
# EDIT_HOOK_ENABLED gobierna el editor: 9.0 (wrapper bean-check) está done, así que el
# default es habilitado. Con "false" se sirve read-only (sin botón de editar).
FAVA_ARGS=""
if [ "${EDIT_HOOK_ENABLED:-true}" != "true" ]; then
  FAVA_ARGS="--read-only"
fi

echo "[fava] iniciando Fava en 127.0.0.1:${FAVA_PORT} (edit_hook=${EDIT_HOOK_ENABLED:-true})"
# shellcheck disable=SC2086
fava --host 127.0.0.1 --port "${FAVA_PORT}" ${FAVA_ARGS} "${MAIN}" &

export PORT FAVA_PORT
envsubst '${PORT} ${FAVA_PORT}' < /app/nginx-fava.conf > /tmp/nginx.conf
echo "[fava] iniciando nginx (basic auth) en :${PORT}"
exec nginx -c /tmp/nginx.conf
