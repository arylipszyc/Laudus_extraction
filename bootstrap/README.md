# bootstrap/ — Generación inicial del ledger Beancount (Story 9.1)

Scripts que hidratan `ledger/` desde cero combinando Laudus API (datos
contables base) + Supabase one-time read (taxonomía + metadata bancaria).
Después de que Story 9.11 desactive Supabase, `accounts.beancount` queda
como single source of truth y estos scripts dejan de ser ejecutables tal
cual — para re-bootstrapear post-9.11 hay que extraer la taxonomía de
otra fuente (export Sheets, CSV manual, o re-implementarlo leyendo
metadata del propio `accounts.beancount`).

---

## Requisitos

- Python 3.12+
- `beancount` (incluye `bean-check` + `beanquery`).
- Variables de entorno (en `.env` raíz):
  - `LAUDUS_USERNAME`, `LAUDUS_PASSWORD`, `LAUDUS_COMPANYVATID`
  - `SUPABASE_URL`, `SUPABASE_KEY` *(temporal — desaparece post-9.11)*

---

## Orden de ejecución

```bash
# 1. Esqueleto del directorio ledger/ (idempotente, OK re-correr)
python -m bootstrap.init_ledger_dir

# 2. Plan de cuentas (genera ledger/accounts.beancount)
python -m bootstrap.generate_accounts

# 3. Saldos iniciales 2021-01-01 (genera ledger/opening-2021.beancount)
python -m bootstrap.generate_opening_balances

# 4. Histórico Laudus 2021 → hoy (DEFERRED — requiere Story 9.4 done)
# python -m bootstrap.import_laudus_history     # placeholder, no implementado

# 5. Validación end-to-end
bean-check ledger/main.beancount
python -m bootstrap.validate_cuadratura
```

Exit codes:

- `0` — OK
- `2` — mismatch / unmapped (intervención manual requerida)
- `3` — bootstrap inviable (precondiciones no cumplidas)

---

## Outputs por script

### `generate_accounts.py`

| Archivo | Contenido |
|---|---|
| `ledger/accounts.beancount` | 255 cuentas hoja con metadata Laudus + bank_account_* |
| `bootstrap/report-mismatch-accounts.csv` | Estructurales: cuentas presentes en Laudus pero no en Supabase (o viceversa). **Bloquean exit ≠ 0.** |
| `bootstrap/report-name-divergences.csv` | Info — Laudus y Supabase tienen `name` distinto para la misma cuenta. **Laudus manda en el render**, divergence se reporta para que Ary actualice Supabase si quiere sincronía. NO bloquea. |
| `bootstrap/report-hierarchy-nodes.csv` | Las 38 cuentas raíz/categoría (`accountNumber` len 1-3 en Laudus). NO se renderizan al ledger — Beancount infiere los grupos jerárquicos automáticamente al abrir hojas. |
| `bootstrap/report-unmapped-accounts.csv` | Cuentas hoja con `Categoria1` no mapeable o `bank_account_type` desconocido. **Bloquean exit ≠ 0.** Resolución: agregar entrada a `bootstrap/account_mapping.py` o reclasificar en Supabase. |

### `generate_opening_balances.py`

| Archivo | Contenido |
|---|---|
| `ledger/opening-2021.beancount` | `open Equity:EAG:OpeningBalances` + `pad`/`balance` por cada cuenta con saldo ≠ 0 al 2021-01-01 derivado del balance sheet Laudus. |

### `validate_cuadratura.py`

| Archivo | Contenido |
|---|---|
| `bootstrap/report-cuadratura-{YYYY-MM-DD}.csv` | Diferencias por cuenta: `laudus_clp`, `beancount_clp`, `diff`, `reason`. Vacío (excepto header) cuando cuadra exacto. |

---

## Convenciones implementadas

- **Account number padding:** Laudus devuelve longitudes variables ("1", "11",
  "111", "111005"). Supabase tiene todo padded a 6 dígitos. Normalizamos
  Laudus → padded a 6 con `account_mapping.normalize_account_number`. El
  `code:` metadata de cada `open` directive lleva el formato padded.
- **Solo cuentas hoja se abren** (`accountNumber` len 6 en Laudus). Las 38
  raíz/categoría no aportan en Beancount — se infieren al renderizar el
  tree view de Fava.
- **"Laudus manda" en `name`:** cuando Laudus y Supabase difieren en el
  account name, se renderiza con el de Laudus (es la fuente original).
  Supabase manda en taxonomía Cat1/2/3 + metadata bancaria.
- **Modelo unificado de cuentas:** las 47 bank_accounts NO son registry
  separado — son subset del plan con metadata extra (`bank_account_id`,
  `bank_name`, `bank_account_type`, `bank_account_currency`) embebida en
  la directiva `open` correspondiente.
- **Q7 (corrección semántica):** `bank_account_type ∈ {tarjeta_credito,
  linea_credito}` fuerza Root = `Liabilities` aún si Categoria1 dice
  ACTIVO. La convención chilena tradicional las clasificaba mal.
- **Pre-2026 todo CLP** (Q4 cerrada 2026-05-05). La lógica multi-currency
  en cartolas USD aparece recién en 9.6.
- **Pad/Balance dating:** las cuentas se abren al **2020-12-31**, los
  `pad` también al 2020-12-31, y los `balance` al 2021-01-01. Beancount
  exige `pad-date < balance-date` para emparejarlos. Divergencia técnica
  obligatoria respecto al story file (que decía 2021-01-01 para todo).

---

## Troubleshooting

### `STILL DOWN` o `getaddrinfo failed` al leer Supabase

El proyecto Supabase free tier se auto-pausa tras ~7 días sin actividad.
Despertarlo desde el dashboard (botón "Resume project"). Tarda 1-3 min en
estar 100% caliente (DNS resuelve antes que PostgREST). Esperar y reintentar.

### `bean-check` falla con `Missing Commodity directive`

`init_ledger_dir.py` declara `commodity CLP` y `commodity USD` en
`main.beancount`. Si quitaste esas líneas, restáuralas re-corriendo el
script (sobreescribe `main.beancount` siempre).

### `bean-check` falla con `File glob ... does not match any files`

Ocurre cuando un directorio incluido por glob (e.g. `imports/laudus/`)
está completamente vacío. `init_ledger_dir.py` deja un `_init.beancount`
placeholder en cada directorio para evitar esto. Si lo borraste, re-corré
el script.

### Cross-check Laudus↔Supabase reporta muchos `laudus-only` o `supabase-only`

Indica que Story 4.0 cargó Supabase con un snapshot Laudus desactualizado,
o que el contador creó/eliminó cuentas en Laudus después. Revisar
`report-mismatch-accounts.csv` y reclasificar cada caso manualmente
(actualizar Supabase, o agregar la cuenta vía Fava editor en
`accounts.beancount`).

### Cuentas con `Categoria1` desconocido — `report-unmapped-accounts.csv`

Cuando Laudus expone una cuenta cuya `Categoria1` no está en la tabla
`MAP_CATEGORIA1_TO_ROOT_ENTITY` de `bootstrap/account_mapping.py`. Resolver:
1. Decidir el mapeo correcto (Root + Entity).
2. Agregar la entrada a la tabla.
3. Re-correr `generate_accounts.py`.

### Cuentas pendientes de revisión — `_new-accounts-pending.beancount`

⚠️ **Riesgo operativo activo:** si Eduardo (operador Laudus) crea una
cuenta nueva en Laudus que NO está en Supabase, el importer Story 9.4 la
detecta y la appendea a `imports/_new-accounts-pending.beancount` con tag
`#pending-account`. Las JEs contra esa cuenta entran al ledger pero
**quedan invisibles en reportes filtrados por categoría hasta que Ary la
promueva manualmente al `accounts.beancount` con su Cat1/2/3 + bank
metadata.** Revisar este archivo periódicamente (mensual al menos).

---

## Status post-bootstrap (2026-05-05)

| AC | Estado | Detalle |
|---|---|---|
| AC1 | ✅ | Estructura `ledger/` generada idempotente |
| AC2 | ✅ | 255 hojas + Q7 aplicado |
| AC3 | ✅ | 0 mismatches estructurales; 17 name-divergences info-only |
| AC4 | ✅ | 0 unmapped (4 entradas agregadas a la tabla §2.3 confirmadas por Ary) |
| AC5 | ✅ | 12 saldos iniciales con `pad`+`balance`, source_je="140" |
| AC6 | ⏸ | DEFERRED — requiere Story 9.4 done para importar histórico mensual |
| AC7 | ⏸ | DEFERRED — depende del importer 9.4 |
| AC8 | ✅ | `bean-check ledger/main.beancount` exit 0 con accounts + opening |
| AC9 | ⏸ | Parcial — solo cutoff 2021-01-01 (cuadra exacto). Cierres anuales y 2026-04-30 requieren AC6 done. |
| AC10 | ⏸ | Re-bootstrap idempotente — verificable cuando AC6 esté done |
