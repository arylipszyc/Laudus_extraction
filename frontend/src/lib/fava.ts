// Deep-link al editor de Fava en el asiento de una fila del reporte (story deep-link asiento).
//
// Fava valida el `file_path` del editor contra `ledger.options["include"]`, que son paths
// ABSOLUTOS del clon de Fava (backend/venv/.../fava/core/file.py:131 `get_source`). El backend
// entrega `filename` REPO-RELATIVE (ej. `ledger/imports/laudus/2026-06.beancount`); acá lo
// convertimos al absoluto del clon de Fava prependiendo `FAVA_LEDGER_ROOT`.
//
// El origin de Fava viene de env (VITE_FAVA_URL) — Fava es servicio aparte, con basic-auth y su
// propio dominio, y cambia entre staging/prod. El slug y el root del clon son hechos del DEPLOY de
// Fava versionados en ESTE repo (ver comentarios); si cambian allá, actualizar acá.

// Slug del ledger en la URL de Fava = slugify(option "title"). En `ledger/main.beancount`:
//   option "title" "LAUDUS — EAG Family Office"  →  "laudus-eag-family-office"
const FAVA_SLUG = 'laudus-eag-family-office'

// Root del clon del repo dentro del contenedor de Fava. En `entrypoint-fava.sh`: LEDGER_DIR=/ledger
// (el repo se clona ahí; el ledger vive en el subdir `ledger/`). El `filename` repo-relative ya
// incluye ese `ledger/`, así que el absoluto de Fava = `/ledger` + `/` + filename.
const FAVA_LEDGER_ROOT = '/ledger'

/**
 * URL del editor de Fava apuntando a `filename:lineno`, o `null` si falta config/datos
 * (fail-safe: el caller no muestra el affordance). No abre nada — solo construye la URL.
 */
export function favaEditorUrl(
  filename?: string | null,
  lineno?: number | null,
): string | null {
  const base = import.meta.env.VITE_FAVA_URL as string | undefined
  if (!base || !filename || !lineno) return null
  const origin = base.replace(/\/+$/, '')
  const absPath = `${FAVA_LEDGER_ROOT}/${filename}`
  const qs = new URLSearchParams({ file_path: absPath, line: String(lineno) })
  return `${origin}/${FAVA_SLUG}/editor/?${qs.toString()}`
}
