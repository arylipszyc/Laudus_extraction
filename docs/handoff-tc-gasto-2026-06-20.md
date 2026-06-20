# Handoff — Tarjetas de crédito como gasto (espejo fiel de Laudus) + re-import completo

**Fecha:** 2026-06-20 · **Owner:** Ary · **Estado:** EN PRODUCCIÓN
**PRs:** [#18](https://github.com/arylipszyc/Laudus_extraction/pull/18) (fix "Otros"), [#19](https://github.com/arylipszyc/Laudus_extraction/pull/19) (TC gasto + re-import + formato)
**Commits clave:** `aaa5118` (Otros), `cf5e0a6` (TC + re-import), `c6f1419` (formato Fava)

---

## 1. Qué cambió (resumen)

1. **Las 9 tarjetas de crédito pasan a GASTO** (`Expenses:EAG:TC:*`), tal cual están en Laudus.
   Antes estaban forzadas a `Liabilities` por un override viejo → el balance las mostraba en
   Pasivos, contradiciendo a Laudus.
2. **Ledger re-importado completo** desde Laudus (5982 asientos, 2021→hoy). De paso quedó probado
   que el pipeline de import funciona de punta a punta (0 cuentas pendientes, bean-check limpio).
3. **Fix "Otros" del balance** (PR #18): el `response_model` del backend descartaba el campo
   `account`, por eso las cuentas de las hijas caían en "Otros". Resuelto.
4. **Formato de números chileno** en Fava: miles con punto, CLP sin decimales. **Solo display** —
   ver §5.

## 2. El problema de fondo (por qué las TC estaban mal)

En **Laudus** las tarjetas son **gasto** (código `4xxx`, categoría "GASTOS - EGRESOS"). Un override
del bootstrap (`bootstrap/account_mapping.py` → `MAP_BANK_TYPE_TO_ROOT_GROUP`:
`tarjeta_credito → Liabilities`, decisión "Q7" de `architecture-c4.md §2.5`) las reclasificaba a
**Pasivo** en Beancount. Resultado: clasificación **inconsistente** —

- El **reporte de gastos** (agrupa por la metadata `categoria`, que es "GASTOS-EGRESOS") las contaba
  como gasto → coincidía con Laudus. ✅
- El **balance-sheet** (agrupa por la raíz de la cuenta, `Liabilities`) las mostraba en Pasivos →
  **NO** coincidía con Laudus. ❌

Misma cuenta, dos respuestas. Esa era la inconsistencia.

## 3. Qué se hizo (la corrección)

- En `ledger/accounts.beancount`: las 9 cuentas TC (`430005`-`430019`) cambian de
  `Liabilities:EAG:TC:*` → `Expenses:EAG:TC:*`. **La metadata queda intacta** (code, categoria,
  bank_account_*).
- **Re-backfill completo** desde Laudus (`run_import(mode="backfill")`) → regenera
  `ledger/imports/laudus/*` con los paths nuevos + la data fresca.
- **NO se tocó código de producción.** La clasificación sale de `accounts.beancount` (dato), no del
  código.

## 4. Decisiones de diseño (para no re-litigar)

- **Se DESCARTÓ una reestructura grande** del plan de cuentas a "paths nativos de Beancount" (clonar
  todo el árbol de Laudus en el nombre de la cuenta, 256 cuentas, jerarquía profunda, jubilar la
  metadata `laudus_categoria*`). Ary lo consultó con Valentina y eligió el camino conservador.
- **La corrección plena de las TC** (itemizar las compras de la cartola como gasto real, el pago como
  movimiento entre cuentas, la deuda real como `Liabilities:EAG:TC:Real`) se hace **solo con asientos
  contables** al importar la cartola — **diseño de Valentina**, ver
  `_bmad-output/planning-artifacts/valentina-correccion-tc-cartolas-2026-06-20.md`. **Está diferida**
  hasta que se arme el flujo de cartolas. Lo de hoy (TC = gasto) es la **base correcta** sobre la que
  eso se construye.
- **Regla de oro (Ary):** NUNCA modificar los **valores** del ledger — puede causar desbalanceos. El
  ledger es espejo fiel de Laudus; las correcciones se hacen con asientos, no editando montos. El
  formato de números se hizo a nivel de **display**, no tocando datos.

## 5. Formato de números (display, NO valores)

`ledger/main.beancount`:
```beancount
option "display_precision" "CLP:1"      ; CLP sin decimales (el peso no tiene centavos)
option "display_precision" "USD:0.01"   ; USD mantiene 2 decimales
2020-01-01 custom "fava-option" "locale" "es_CL"   ; miles con punto
```
`display_precision` y `locale` afectan **cómo se muestran** los números en Fava, nunca cómo se
almacenan ni cómo se valida el balance. `bean-check` confirma que los valores quedan idénticos.

## 6. Verificación

- **Balance Beancount == Laudus**: 186/186 cuentas al peso, 0 diferencias (al 2026-05-31).
  Fuente de verdad = `accounting/balanceSheet/totals` de Laudus. Evidencia en `_handoff/`.
- Las 9 TC salen del balance-sheet (ya no en Pasivos), quedan como gasto.
- Reporte de gastos: **sin cambios** (la metadata `categoria` no se tocó).
- `bean-check ledger/main.beancount`: limpio.
- Backend: **628 tests passed** (1 deselected = `test_run_backfill` pre-existente
  date-dependiente; 1 xfailed).

## 7. Deploy

- Merge de #19 a `main`. **Ojo:** el auto-deploy de Render solo observa cambios en `backend/`
  (código). Un commit que toca solo `ledger/` (datos) **no** dispara auto-deploy. Como el backend
  clona el ledger al arrancar, hubo que **gatillar un redeploy a mano** vía la Render API
  (`POST /v1/services/srv-d7dk4hv41pts73a35aqg/deploys`). Deploy `dep-d8rdts...` quedó **live**.
- El **cron semanal** del importer seguirá consistente: lee `accounts.beancount` (TC como gasto), no
  reintroduce el Pasivo.

## 8. Follow-ups / pendientes

- **`account_mapping.py` (disaster-recovery):** el override `tarjeta_credito → Liabilities` sigue en
  el código (deprecado, depende de Supabase). Quedó marcado como superado por comentario; un
  re-bootstrap desde cero lo reintroduciría — la SoT es `accounts.beancount`, no regenerar a ciegas.
- **Smoke visual de los dashboards:** handoff a Ary (el login Google bloquea la automatización).
- **Corrección plena de TC con cartolas:** diferida (diseño de Valentina, ver §4).
