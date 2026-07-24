# Plan de reorganización del tree — 2026-07-23

**Autor:** Winston (Arquitecto) · Para revisión/aprobación de Ary.
**Estado:** PROPUESTA. Nada se ejecuta hasta que Ary apruebe la lista de "archivar" (§3).
**Método:** `git mv` (renames limpios, reversibles) para trackeados; `mv` para untracked. Link-check hecho (§4).

---

## 1. Raíz del repo — sacar los screenshots sueltos

**Hallazgo:** ~24 PNGs sueltos en la raíz (screenshots efímeros del spike Odoo), **cero referencias** en docs/código.
22 sin trackear (ni en `.gitignore` → ensucian `git status`), 2 trackeados. Ninguno se referencia.

**Movida:** todos → `docs/screenshots/` (trackeados, quedan como documentación del spike) + `trial-balance.md` → `docs/`.
**Anti-recaída:** agregar `/*.png` a `.gitignore` (solo raíz) para que un screenshot suelto futuro no vuelva a acumularse.

| Archivo (raíz) | Destino |
|---|---|
| `analitica.png`, `apps-list.png`, `asientos-eag.png`, `asientos-lista.png`, `barra-final.png`, `categorizacion-febrero.png`*, `menu-contabilidad.png`, `navbar-final2.png`, `navbar-limpio.png`, `navbar-visual.png`, `panel-*.png` (×6), `plan-de-cuentas.png`, `report-view.png`, `tc-smoke-importada-ok.png`*, `trial-balance-eag.png` | `docs/screenshots/` |
| `trial-balance.md` | `docs/` |

*(\* = los 2 trackeados; el resto untracked.)*

**Se quedan en la raíz** (deploy/runtime legítimo): `render.yaml` (obligatorio en raíz), `Dockerfile.fava`,
`entrypoint-fava.sh`, `nginx-fava.conf`, `run-backend.sh`, `README.md`, `CLAUDE.md`. `sync.log` ya está gitignored.

---

## 2. planning-artifacts — de 53 archivos planos a carpetas por tema

### 2a. → `planning-artifacts/odoo-migracion/` (el track VIVO — lo que se usa hoy)

```
valentina-product-brief-migracion-odoo-2026-07-23.md
valentina-spec-estructura-odoo-2026-07-23.md
valentina-mapa-normalizacion-odoo-2026-07-23.md
valentina-tabla-mapeo-odoo-2026-07-23.csv
valentina-tabla-mapeo-resumen-2026-07-23.md
valentina-tabla-mapeo-generador-2026-07-23.py
valentina-tabla-alias-2026-07-23.yaml
valentina-inventario-naturalezas-2026-07-23.md
valentina-lista-partners-2026-07-23.md
valentina-analitica-familia-mecanismo-2026-07-23.md
valentina-metodo-multimoneda-ias21-2026-07-18.md        (feeds Fase 3; citado por el SPEC)
valentina-minidiseno-julius-baer-2026-07-18.md          (Fase 3)
winston-arquitectura-e1-odoo-2026-07-23.md
epics.md
spike-odoo-accounting-runbook-2026-07-22.md
```

> **Ojo (cross-ref):** `epics.md`, el SPEC y el brief se citan entre sí por nombre. Al moverlos JUNTOS a la
> misma carpeta, las referencias relativas se preservan. Los que citan por ruta absoluta (`_bmad-output/...`)
> hay que actualizarlos — el link-check §4 lista cuáles.

### 2b. → `planning-artifacts/_forense/` (scripts de investigación one-off)

```
_forense_inversiones.py   _forense_recon_vehiculo.py   _forense_retiros_rut2.py
_forense_sonda_primeros_asientos_rut2.py   _forense_verify_rut2_plan.py
```

### 2c. Se quedan en `planning-artifacts/` (raíz) — anclas vivas cross-cutting

```
architecture-c4.md      ← referenciado por ledger/main.beancount + bootstrap/*.py + README (CÓDIGO VIVO). NO mover.
adr-001-plan-de-cuentas-beancount-source-of-truth.md   ← ADR fundacional, sigue vigente (Beancount = fuente).
cartola-tc-controles-referencia-para-v2-2026-07-21.md  ← explícitamente "para v2" (reference futura).
research/               ← subcarpeta ya existente.
```

---

## 3. → `_archive-pre-reset-2026-07-22/planning-artifacts/` (superados por el reset — REQUIERE TU OK)

Espeja el archivo de `implementation-artifacts/` que ya existe. **Estos son los que necesitan tu criterio**
(algunos son borderline: los marco 🟡). El resto 🟢 es archivable con confianza.

| Archivo | Conf. | Nota |
|---|---|---|
| `architecture.md` | 🟡 | Arquitectura full-stack de la era OAuth/Sheets (pre-reset). Referenciada por README → hay que actualizar el puntero del README al archivar. |
| `prd.md`, `prd-validation-report.md` | 🟢 | PRD viejo, pre-Odoo. |
| `adr-owner-comments-ancla-persistencia.md` | 🟢 | Epic 7 colaboración, cerrado. |
| `sprint-change-proposal-2026-06-10.md` | 🟢 | Histórico. |
| `research-beancount-pivot-2026-04-30.md` | 🟢 | Research histórico. |
| `review-estabilidad-performance-2026-07-06.md` | 🟢 | Fase 1 review, cerrado. |
| `design-note-balance-sheet-flip-2026-06-17.md` | 🟢 | Flip ya hecho. |
| `design-inversiones-lookthrough-2026-06-22.md` | 🟡 | Diseño de inversiones — puede alimentar Fase 3. ¿Archivar o a odoo-migracion? |
| `implementation-readiness-report-2026-07-10.md` | 🟢 | Reporte puntual. |
| `discovery-segundo-rut-intake-2026-06-30.md` | 🟢 | RUT2 ya integrado. |
| `reconciliacion-rut2-vs-laudus-2026-07-11.md` | 🟢 | Reconciliación cerrada. |
| `rut2-plan-cuentas-laudus-2026-07-10.json` | 🟢 | Snapshot. |
| `clasificacion-contable-rut2-firmada-2026-07-11.md` | 🟡 | "Firmada" — ¿referencia contable viva? |
| `guion-demo-contadores-2026-07-21.md` | 🟡 | Guion de demo reciente — ¿lo vas a reusar? |
| `valentina-auditoria-ingresos-inversiones-2026-06-20.md` | 🟡 | Alimenta la auditoría de inversiones diferida (Fase 3). |
| `valentina-clasificacion-rut2-fondo-comun-2026-06-30.md` | 🟢 | RUT2 cerrado. |
| `valentina-contexto-fondo-comun-jab-2026-07-11.md` | 🟢 | Contexto FFCC/JAB (ya en el diseño Odoo). |
| `valentina-correccion-tc-cartolas-2026-06-20.md` | 🟢 | Epic 6 TC, cerrado. |
| `valentina-cuentas-corriente-socios-ffcc-2026-07-12.md` | 🟡 | Cuentas corriente socios — insumo del partición socio-dueño en E1.4. |
| `valentina-diseno-cuadre-tc-cascada-conciliacion-2026-07-05.md` | 🟢 | Epic 6 TC. |
| `valentina-diseno-cuadre-tc-detalle-por-check-2026-07-05.md` | 🟢 | Epic 6 TC. |
| `valentina-fix-matcher-fx-consolidado-2026-06-29.md` | 🟢 | Fix cerrado. |
| `valentina-fix-wash-0858-pago-consolidado-2026-07-21.md` | 🟢 | Fix cerrado. |
| `valentina-preguntas-contadores-2026-07-21.md` | 🟡 | Preguntas abiertas a contadoras — ¿vivas? |
| `valentina-story-brief-fx-revolving-tc-usd-2026-07-06.md` | 🟢 | Story cerrada. |
| `valentina-tratamiento-saldos-usd-balance-2026-07-08.md` | 🟡 | Tratamiento USD — puede tocar Fase 3 (IAS 21). |
| `valentina-veredicto-desglose-tc-14cartolas-2026-06-29.md` | 🟢 | Veredicto TC, cerrado. |
| `valentina-brief-story-deeplink-asiento-fava-2026-07-21.md` | 🟢 | Deeplink Fava, hecho. |

**Los 🟡 (9) son los que quiero que revises**: archivar, o rescatar a `odoo-migracion/` si los ves vivos
para Fase 2/3. Los 🟢 (18) los archivo con tu OK general.

---

## 4. Cross-refs a respetar (del link-check)

- `architecture-c4.md` ← `ledger/main.beancount`, `bootstrap/account_mapping.py`, `bootstrap/init_ledger_dir.py`,
  `README.md` (+ 31 docs). **Se queda donde está** → no rompe nada.
- Si algún doc que muevo cita a otro por ruta absoluta `_bmad-output/planning-artifacts/<x>`, actualizo la ruta
  al mover (los del track Odoo se citan mayormente por nombre simple → se preservan al moverlos juntos).
- `render.yaml` / `Dockerfile.fava` referencian rutas de deploy → **no se tocan**.

---

## 5. Orden de ejecución (con tu OK)

1. **Raíz** (§1): mover PNGs + `trial-balance.md`, agregar regla `.gitignore`. Riesgo nulo.
2. **odoo-migracion/ + _forense/** (§2a/2b): `git mv`. Riesgo bajo (referencias por nombre se preservan).
3. **Archivar** (§3): solo tras tu aprobación de la lista, resueltos los 🟡. Actualizar puntero de README.
4. `git commit` en una rama (`chore/reorg-tree-2026-07-23`), no en `main` directo.
