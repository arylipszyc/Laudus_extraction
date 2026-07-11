# Story 12.2: Importador multi-libro — entidad como parámetro, índice (entidad, código), assert de empresa

Status: done

## Story

As operador de la importación (Ary o dev),
I want que el importador Laudus exija el libro/entidad como parámetro explícito y rutee por (entidad, código),
so that sea estructuralmente imposible que asientos del Fondo Común se posteen a cuentas de EAG en silencio.

## Acceptance Criteria

1. **Given** una corrida de import sin libro/entidad, companyVATId o subdirectorio destino explícitos,
   **When** se ejecuta,
   **Then** falla con error claro ANTES de leer o escribir nada (FR50). Los entry points de prod (cron `cron-importer-entry.sh`, `/sync/trigger`) pasan el libro EAG EXPLÍCITO — siguen funcionando sin cambio de comportamiento.

2. **Given** los códigos en colisión entre libros (31 solapan, 18 son cuenta distinta bajo el mismo código — intake §4),
   **When** se importa un asiento de RUT2 con uno de esos códigos,
   **Then** rutea a la cuenta de RUT2 vía índice con noción de entidad `{(entidad, código)→cuenta}`, nunca a la homónima de EAG (FR51),
   **And** un código de RUT2 sin cuenta pre-creada cae en cuarentena bajo la entidad del LIBRO, no bajo `Assets:EAG:PendingReview` (hoy hardcodeado).

3. **Given** que Laudus devuelve datos de otro libro sin fallar ante un companyVATId equivocado,
   **When** el importador arranca una corrida,
   **Then** verifica que la identidad de la empresa devuelta por la API coincide con la esperada para el libro y aborta SIN ESCRIBIR si no coincide (FR52),
   **And** la verificación NO valida dígito verificador (RUT placeholder `12.345.678-2` con DV inválido por diseño).

4. **Given** el libro EAG con el importador refactorizado,
   **When** corre el import habitual de EAG,
   **Then** el resultado es idéntico al comportamiento previo (0 regresiones; suite backend completa verde; los archivos generados por una corrida EAG de prueba son byte-idénticos).

5. **Given** el índice de cuentas bancarias (`bank_account_index`),
   **When** resuelve la entidad de una cuenta RUT2 (cierra el defer del code-review 12.1),
   **Then** las cuentas FFCC/JAB NO caen en el fallback `entity="EAG"` — la resolución usa el segmento de entidad del PATH de la cuenta (autoridad per 11.x) y las categoria1 de RUT2 (`"PASIVO"`, `"INGRESOS"` — que hoy mapean EXPLÍCITO a EAG en `_ENTITY_PREFIXES`) dejan de ser ambiguas.

## Tasks / Subtasks

- [x] Task 1: Configuración por libro — romper el singleton import-time (AC: 1)
  - [x] `pipeline/config/laudus_config.py:20-24`: `payload` es un dict de MÓDULO evaluado en import-time (lee `LAUDUS_USERNAME/PASSWORD/COMPANYVATID` de env) y `laudus_service.py:7,32` cachea `_token` a nivel de módulo → estructuralmente mono-libro por proceso. Refactor: objeto/config de libro (`book_id`, `companyVATId`, identidad esperada, subdir destino, set de entidades) que se pasa explícito; token por-libro (no global de módulo).
  - [x] `run_import` (`pipeline/importers/laudus_run.py`) exige el parámetro libro SIN default → sin libro = error claro antes de tocar nada (AC1).
  - [x] Actualizar los 3 entry points para pasar EAG explícito: `backend/cron-importer-entry.sh:33` (`python -m pipeline.importers.laudus_run`, bloque `__main__` en `laudus_run.py:486-490` — env `IMPORTER_BOOK` explícita en el sh), `backend/app/api/v1/sync/service.py:147-153` (`_run_laudus_import` → `run_import(...)`), y la CLI.

- [x] Task 2: Índice con noción de entidad (AC: 2) — el core
  - [x] `pipeline/writers/beancount_writer.py:68-77` (`load_account_index`): hoy clave = `code` DESNUDO; `:128-133` lookup `account_index.get(code)`. Re-clavear con noción de entidad. Recomendación (dev decide y documenta): índice SCOPED por libro — construirlo solo sobre las cuentas cuyo 2º segmento de path ∈ entidades del libro (EAG: {EAG, Jocelyn, Jeannette, Johanna, Jael} + namespaces legacy sin entidad; RUT2: {FFCC, JAB}); dentro de un libro los codes son únicos (verificado: EAG hoy, RUT2 0 duplicados). Nota: derivar la entidad del CODE solo funciona en RUT2 (dígito de raíz) — en EAG el code no distingue EAG de hijas → por eso el scoping por path es lo mecánico.
  - [x] Cuarentena por libro: `beancount_writer.py:80-82` `_pending_account` hardcodea `Assets:EAG:PendingReview:Cuenta-{code}` → parametrizar por entidad del libro (RUT2: derivar FFCC/JAB del dígito de raíz del code; default recomendado `Assets:FFCC:PendingReview:...` si el dígito no mapea).
  - [x] Subdir destino por libro: `laudus_run.py:368` hardcodea `imports/laudus/`; también `:459` (`git add "ledger/imports/laudus/"`) y el include del ledger (`include "imports/laudus/*.beancount"`). EAG conserva `imports/laudus/` intacto; RUT2 → `imports/laudus-rut2/` (el include nuevo en main.beancount se AGREGA RECIÉN en 12.4 cuando exista el primer archivo — no en esta story, para no romper bean-check con glob vacío; documentarlo).
  - [x] `_incremental_start` (`laudus_run.py:299-311`) deriva `from_date` de los JEs en el subdir → con subdir por libro queda aislado gratis; test que lo cubra.

- [x] Task 3: Assert de identidad de empresa (AC: 3)
  - [x] HOY NO EXISTE ningún chequeo (verificado: `pipeline/services/laudus_service.py` — `login()` :23-41 solo extrae token; sin lectura de nombre de empresa en ningún módulo). Laudus NO falla ante companyVATId equivocado (intake §4).
  - [x] Investigar qué expone la API barata para identidad: (a) campos extra en la respuesta del `login` — inspeccionar; (b) endpoint de empresa/usuario actual; (c) FALLBACK ROBUSTO recomendado si (a)/(b) no dan nombre: fingerprint del plan de cuentas — GET del plan y assert del nombre de la cuenta raíz 1 (`"ACTIVO EAG"` para EAG / `"ACTIVO FFCC"` para RUT2, ambos verificados en datos reales). Cualquiera de las vías corre ANTES del primer write y aborta con error claro.
  - [x] La identidad esperada vive en la config del libro (Task 1). SIN validación de DV.

- [x] Task 4: Cerrar el defer `bank_account_index` (AC: 5)
  - [x] `backend/app/integrations/bank_account_index.py:111`: `entity = _resolve_entity(categoria1) or "EAG"` — fallback silencioso; `_ENTITY_PREFIXES` (:28-34) mapea `"PASIVO"`/`"INGRESOS"` EXPLÍCITO a EAG (colisiona con las categoria1 de RUT2 raíces 2/3). Fix recomendado: resolver por el 2º segmento del PATH de la cuenta (el índice se construye desde los `open` de accounts.beancount — tiene el nombre completo) con categoria1 como fallback legacy; entidades conocidas = VALID_ENTITIES.
  - [x] Test: cuenta `Assets:FFCC:...` con `laudus_categoria1: "ACTIVO FFCC"` → entity FFCC; cuenta con categoria1 `"PASIVO"` bajo path FFCC → FFCC (no EAG); cuentas EAG existentes → sin cambio (0 regresiones sobre el índice actual).
  - [x] Marcar el defer como cerrado en `deferred-work.md` (sección code review 12.1).

- [x] Task 5: Tests y anti-regresión EAG (AC: 4)
  - [x] `backend/tests/test_laudus_run.py` (fixture `_ledger_root` + `fetch_fn` fake :34-58), `test_sync.py`, `test_laudus_service.py`: adaptar a libro explícito + tests nuevos: AC1 (sin libro → error temprano), AC2 (colisión de código rutea por libro; cuarentena por entidad), AC3 (identidad no coincide → aborta sin escribir), incremental aislado por subdir.
  - [x] Suite completa backend: 0 regresiones (baseline 784 passed/1 xfailed; rojos PRE-EXISTENTES conocidos: test_fava_edit_validator ×2 históricos ya resueltos — verificar en HEAD limpio antes de atribuir).
  - [x] Gotcha Windows: `PYTHONUTF8=1` obligatorio para la suite.
  - [x] Commitear al cerrar (acuerdo retro).

## Dev Notes

### Contexto del riesgo (por qué existe esta story)

RUT2 = 2º libro del MISMO login de Laudus (`companyVATId` placeholder `12.345.678-2`, swap de companyVATId cambia de libro — sonda 2026-06-30). **31 códigos de RUT2 solapan con codes ya presentes en accounts.beancount y 18 son cuenta DISTINTA bajo el mismo código** (intake §4; las 31 son hojas que 12.3 va a crear). Con el índice actual por code desnudo, un asiento RUT2 con código solapado se postearía EN SILENCIO a la cuenta EAG homónima — ni siquiera pasaría por cuarentena. Este es el guardrail que la memoria del proyecto marca como crítico desde 2026-06-30.

### Hechos verificados del código (mapa 2026-07-11, no re-derivar)

- **Entry points** → todos convergen en `run_import`: cron `backend/cron-importer-entry.sh:33` (clon SSH fresco, `LEDGER_DIR=/tmp/ledger-repo/ledger` :31; env `IMPORTER_MODE`/`IMPORTER_FROM_DATE` leídas en `laudus_run.py:486-490`); backend POST `/sync/trigger` (`sync/router.py:36-53` → `service.py:89,147,153`); CLI `python -m pipeline.importers.laudus_run`.
- **Conexión**: `pipeline/config/laudus_config.py:20-24` — dict de módulo con `LAUDUS_USERNAME/PASSWORD/COMPANYVATID` (declaradas en `render.yaml:37-42`, sync:false). Token cacheado a nivel módulo (`laudus_service.py:7,32`).
- **Índice**: `beancount_writer.py:68-77` construye `dict[code→account]` desde los `open` con metadata `code`; lookup `:128-133`; `write_jes` (`:216-242`) no recibe noción de entidad.
- **Cuarentena**: `_pending_account` (`beancount_writer.py:80-82`) → `Assets:EAG:PendingReview:Cuenta-{code}`; archivo `imports/_new-accounts-pending.beancount` (`laudus_run.py:370`; writer `:198-210`); tag `#pending-account` (`:97-98`).
- **Assert de empresa: NO existe** — `login()` solo extrae token; ningún módulo lee nombre de empresa.
- **Incremental**: `_incremental_start` (`laudus_run.py:299-311`) lee los JEs de `imports/laudus/` → subdir compartido contaminaría el from_date de ambos libros.

### Decisiones técnicas con default (auto-aprobar per project-context, documentar en Dev Agent Record)

1. **Forma del "índice (entidad,code)"**: scoping por libro (path 2º segmento ∈ entidades del libro) recomendado sobre clave compuesta global — en EAG el code no distingue EAG de hijas, el path sí. Cumple la INTENCIÓN de FR51.
2. **Vía del assert de identidad**: la que resulte más barata/estable de la investigación (login-payload > endpoint empresa > fingerprint raíz del plan). El fingerprint es el fallback garantizado (datos reales verificados a ambos lados).
3. **Cuarentena RUT2**: entidad por dígito de raíz del code (1-4→FFCC, 6-8→JAB); dígito desconocido → FFCC.
4. **Include de `imports/laudus-rut2/`**: se difiere a 12.4 (primer archivo real); esta story solo deja el subdir parametrizado.

### Coordinación con 12.3 (corre EN PARALELO)

12.3 genera el árbol RUT2 en `ledger/accounts.beancount` + `bootstrap/generate_rut2_accounts.py`. **Esta story NO toca `ledger/accounts.beancount` ni `bootstrap/`** (los tests usan fixtures propias con cuentas FFCC/JAB mini, patrón `MINI_ACCOUNTS` de `test_laudus_run.py:34-42`). Archivos de esta story: `pipeline/` (config, services, writers, importers), `backend/cron-importer-entry.sh`, `backend/app/api/v1/sync/service.py`, `backend/app/integrations/bank_account_index.py`, tests. Cero solape esperado con 12.3.

### Qué NO hacer (scope guard)

- NO crear cuentas RUT2 en `accounts.beancount` — eso es 12.3 (paralela)
- NO importar datos reales de RUT2 ni agregar el include del subdir nuevo — eso es 12.4
- NO tocar el motor de reconciliación/cartolas más allá de `bank_account_index._resolve_entity`
- NO validar dígito verificador del RUT (placeholder por diseño)
- NO cambiar el comportamiento observable del libro EAG (AC4 es un gate duro)

### References

- [Source: _bmad-output/planning-artifacts/epics-segundo-rut.md#Story 12.2] — FR50/FR51/FR52
- [Source: _bmad-output/planning-artifacts/discovery-segundo-rut-intake-2026-06-30.md#Sección 4] — sonda: swap companyVATId, 31/18 colisiones, Laudus no valida RUT
- [Source: _bmad-output/planning-artifacts/clasificacion-contable-rut2-firmada-2026-07-11.md] — entidades FFCC/JAB por dígito de raíz; §8 advertencia bank_account_index
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#code review 12-1] — defer bank_account_index que esta story cierra
- [Source: pipeline/writers/beancount_writer.py:68-82,128-133] — índice por code + cuarentena hardcodeada (el core)
- [Source: pipeline/config/laudus_config.py:20-24; pipeline/services/laudus_service.py:7,23-41] — singleton mono-libro
- [Source: pipeline/importers/laudus_run.py:299-311,368,459,486-490] — incremental, subdir, git add, entry CLI

## Dev Agent Record

### Agent Model Used

claude-fable-5 (Amelia, dev-story BMAD) — 2026-07-11, en git worktree aislado (12.3 en paralelo).

### Debug Log References

- Verificación de entorno: fallo deliberado en `pipeline/importers/laudus_run.py` visible desde pytest → confirma que la suite ejecuta el código del WORKTREE, no del checkout principal (revertido). El venv del checkout principal resuelve `pipeline`/`backend` por cwd, sin install editable — no hizo falta PYTHONPATH para pytest (sí para scripts sueltos: `PYTHONPATH=<worktree>`).
- Branch del worktree fast-forwardeado a `main` local (013f0c8) antes de empezar: sin 11.2 el worktree no tenía los labels FFCC/JAB en `VALID_ENTITIES` ni el defer de 12.1 en `deferred-work.md`.
- Baseline pre-cambios verificado: `PYTHONUTF8=1 python -m pytest backend/tests pipeline -q` → **784 passed, 1 xfailed** (coincide con el story file; los 2 rojos históricos de test_fava_edit_validator no aparecen — ya resueltos en HEAD).
- Gate AC4 byte-identidad: corrida EAG de prueba (mini ledger + fetch fake, incluye código desconocido → cuarentena) ejecutada con el código PRE-cambio y POST-cambio; los 4 archivos generados (`2024-03/2024-04.beancount`, `_init`, `_new-accounts-pending.beancount`) son **byte-idénticos** (comparación binaria). Además hay un test permanente en suite (`test_write_jes_libro_eag_byte_identico_al_legacy`).
- CLI sin `IMPORTER_BOOK` verificada a mano: exit 1 con mensaje claro FR50, sin tocar nada.

### Completion Notes List

**Decisiones técnicas (defaults del story file, auto-aprobadas per project-context):**

1. **Forma del índice (entidad, code): scoping por libro** (default recomendado). `load_account_index(path, book)` solo indexa cuentas cuyo 2º segmento de path ∈ `book.entities`; EAG además incluye los namespaces legacy sin entidad (2º segmento que no es entidad de NINGÚN libro, ej. `Equity:Apertura:*`) vía `include_entityless`. La clave sigue siendo el code desnudo pero el universo es del libro → cumple la INTENCIÓN de FR51 (colisión 111005 EAG/FFCC testeada en ambos niveles: writer y run).
2. **Vía del assert de identidad: fingerprint del plan de cuentas** (fallback robusto del story file). No hay red/credenciales en este entorno para sondear el login-payload o un endpoint de empresa, así que se implementó la única vía VERIFICADA en datos reales: `POST /accounting/accounts/list` (fields `accountNumber,name`, mismo endpoint del bootstrap) y assert `nombre(cuenta raíz "1") == book.expected_root_name` (`"ACTIVO EAG"` / `"ACTIVO FFCC"`). Vive en `laudus_service.verify_book_identity` y corre al inicio de `default_fetch` (antes de pedir el ledger y de cualquier write); `BookIdentityError` → corrida failed sin escribir. SIN validación de DV. Si el login-payload resulta traer identidad más barata, es swap interno de esa función.
3. **Cuarentena RUT2 por dígito de raíz**: `BookConfig.pending_entity_by_root` = 1-4→FFCC, 6-8→JAB; dígito desconocido → FFCC (default de la story). EAG: siempre EAG (idéntico a hoy). Cada libro tiene su PROPIO pending file (`_new-accounts-pending-rut2.beancount` para RUT2) — necesario porque el archivo se REGENERA entero en cada corrida y un archivo compartido re-etiquetaría los codes del otro libro.
4. **Include de `imports/laudus-rut2/` y del pending RUT2 en main.beancount: DIFERIDO a 12.4** (primer archivo real; glob vacío rompe bean-check). Esta story solo parametriza el subdir; los tests espejan prod (MAIN sin el include nuevo).

**Decisiones adicionales (documentadas, no estaban en el story file):**

5. **`write_jes`/`load_account_index` aceptan `book` opcional (None = comportamiento pre-12.2)**: el guardrail duro (libro SIN default) vive en `run_import` (el entry point que la story manda blindar); el writer mantiene compat con callers legacy (bootstrap `generate_opening_balances` importa `load_account_index` y NO se puede editar en esta story) y con los ~25 call sites de tests existentes. `run_import` pasa `book` SIEMPRE.
6. **`companyVATId` por libro vía env**: EAG = `LAUDUS_COMPANYVATID` (existente), RUT2 = `LAUDUS_COMPANYVATID_RUT2` (nueva; NO está en render.yaml todavía — va con 12.4 cuando el import RUT2 se ejecute de verdad). La env se lee al hacer login (runtime), ya no en import-time; si falta para el libro pedido → RuntimeError ANTES de abrir sesión.
7. **Token por libro**: `laudus_service._tokens: dict[book_id → token]` (reemplaza el `_token` global); el 401 invalida solo el token del libro. `login(book=None)`/`get_info_API(book=None)` = EAG, para bootstrap y `balance_sheet_service` legacy.
8. **Import-log multi-libro**: el record de una corrida gana campos `book` y usa `importer = book.importer_name` — EAG sigue siendo `"laudus"` (el lector de `/sync/status` filtra por ese literal, cero cambio de comportamiento); RUT2 escribe `"laudus-rut2"` para NO avanzar el indicador "Datos de Laudus al:" de EAG (testeado). Los mensajes de commit de RUT2 salen `[importer-laudus-rut2]`.
9. **`fetch_fn=None` como default de `run_import`** (antes `default_fetch` directo): el fetch real ahora necesita el libro, así que None → `partial(default_fetch, book)`; los fakes de tests conservan la firma `(date_from, date_to)`.

**Resultado de la suite**: `PYTHONUTF8=1 python -m pytest backend/tests pipeline -q` → **828 passed, 1 xfailed** (baseline 784/1 → +44 tests nuevos, 0 regresiones).

**Cobertura AC→test (nuevos):**
- AC1: `test_run_import_sin_libro_falla_antes_de_tocar_nada`, `test_get_book_rechaza_libro_ausente_o_desconocido`, asserts `captured["book"]=="EAG"` en `test_sync.py` (entry point backend), CLI verificada a mano (exit 1, FR50).
- AC2: `test_rut2_codigo_en_colision_rutea_a_su_libro_nunca_a_eag`, `test_rut2_codigo_sin_cuenta_cae_en_cuarentena_de_su_entidad`, `test_load_account_index_scoped_por_libro`, `test_write_jes_rut2_cuarentena_por_entidad_del_libro`, `test_pending_entity_rut2_por_digito_de_raiz`.
- AC3: `test_verify_book_identity_*` (×4, incl. mismatch RUT2←datos EAG), `test_run_import_aborta_sin_escribir_si_identidad_no_coincide`, `test_default_fetch_verifica_identidad_antes_de_pedir_datos`, `test_login_cachea_token_por_libro`.
- AC4: `test_write_jes_libro_eag_byte_identico_al_legacy` + comparación binaria externa pre/post (Debug Log) + suite completa verde.
- AC5: `test_entity_from_path` (×7), `test_index_cuentas_rut2_no_caen_al_fallback_eag` (incluye el caso categoria1="PASIVO" bajo path FFCC y 0 regresiones EAG/hijas).
- Aislamiento incremental: `test_incremental_rut2_aislado_del_subdir_eag`; indicador: `test_import_log_de_rut2_no_avanza_el_indicador_eag`.

**Scope guard respetado**: no se tocó `ledger/accounts.beancount`, `bootstrap/`, `frontend/`, ni el motor de reconciliación (solo `bank_account_index`, permitido). No se importaron datos RUT2 ni se agregó include nuevo. Sin validación de DV.

### File List

- `pipeline/config/laudus_config.py` — BookConfig + BOOKS (EAG/RUT2) + get_book + login_payload + ACCOUNTS_LIST_URL + ALL_BOOK_ENTITIES; removido el dict `payload` de import-time.
- `pipeline/services/laudus_service.py` — token por libro (`_tokens`), `login(book)`, `get_info_API(..., book)`, `verify_book_identity` + `BookIdentityError`.
- `pipeline/services/ledger_service.py` — `fetch_ledger(..., book)` pass-through.
- `pipeline/writers/beancount_writer.py` — `load_account_index(..., book)` scoped, `_account_in_book`, `_pending_account(code, book)`, pending header/entidad por libro, `write_jes(..., book)`.
- `pipeline/importers/laudus_run.py` — `run_import(book, ...)` libro obligatorio, `default_fetch(book, ...)` con verify de identidad, `_min_account_number(book)`, subdir/pending/git-paths/mensajes/import-log por libro, `__main__` exige `IMPORTER_BOOK`.
- `backend/cron-importer-entry.sh` — `export IMPORTER_BOOK=EAG` explícito.
- `backend/app/api/v1/sync/service.py` — `run_import("EAG", ...)` explícito.
- `backend/app/integrations/bank_account_index.py` — `_entity_from_path` (autoridad path, `VALID_ENTITIES`) con `_resolve_entity(categoria1)` como fallback legacy.
- `backend/tests/test_book_config.py` — NUEVO (BookConfig/get_book/pending_entity/login_payload).
- `backend/tests/test_laudus_run.py` — libro explícito en run_import + fixture parametrizable + 7 tests 12.2.
- `backend/tests/test_laudus_service.py` — fixture `_tokens` por libro + 5 tests (login por libro, verify_book_identity ×4).
- `backend/tests/test_sync.py` — fakes de run_import con `book` + asserts EAG explícito.
- `backend/tests/test_beancount_writer.py` — 4 tests 12.2 (índice scoped, legacy sin libro, cuarentena RUT2, byte-identidad EAG).
- `backend/tests/test_bank_account_index.py` — `_entity_from_path` (×7) + fixture RUT2 (AC5).
- `_bmad-output/implementation-artifacts/deferred-work.md` — defer `bank_account_index` de 12.1 marcado CERRADO.
- `_bmad-output/implementation-artifacts/12-2-importador-multi-libro.md` — este story file (tasks, record, status).

### Review Findings

Code review adversarial 3 capas (Blind Hunter / Edge Case Hunter / Acceptance Auditor), 2026-07-11. **AC1–AC5: PASS** con verificación independiente (índice scoped seguido sobre el ledger real: 111005 → FFCC con book=RUT2 / EAG con book=EAG; verify antes de todo write en incremental/backfill; aislamiento de subdir/pending/incremental; cierre del defer 12.1 real). Gates: suite 836→842 passed / 1 xfailed, bean-check exit 0, 0-diffs EAG byte-idéntico vs 013f0c8. Triage: **1 decision-needed** / 3 patch / 5 defer / 6 dismiss.

**Decision-needed — RESUELTO por Ary 2026-07-11 ("dejalo como quedó" = ratificado como fix):**
- [x] **23 cuentas de las HIJAS cambian de entity en `bank_account_index` (EAG → Jocelyn×6/Jeannette×6/Johanna×5/Jael×6)**, además de las 6 RUT2 buscadas. Causa: el fallback viejo por categoria1 era case-sensitive (`_FAMILY_NAMES` title-case) y en prod las categorías están en MAYÚSCULA (`"DISPONIBLE JOCELYN AVAYU DEUTSCH"`) → NUNCA matcheó, todas las hijas resolvían EAG; la autoridad por path de AC5 ahora resuelve la hija correcta. La letra de Task 4 ("cuentas EAG existentes → sin cambio") no se sostiene sobre datos reales — el test AC5 pasa porque su fixture usa categoria1 title-case, que no modela prod. La DIRECCIÓN es corrección (una cuenta `Assets:Jocelyn:...` ES de Jocelyn) y AC5 mismo manda path-como-autoridad; único consumidor = `source.entity` del JSON canónico de cartolas (string libre, sin enum) → riesgo bajo. **Decisión requerida:** ratificar el cambio de las 23 como fix intencional (y de paso ajustar el fixture del test a categoria1 MAYÚSCULA real), o exigir preservación estricta del entity previo para las hijas. Verificado con script sobre el ledger real: 29 cuentas cambian (6 RUT2 intencionales + 23 hijas).

**Patches aplicados:**
- [x] **`verify_book_identity` maneja 401 invalidando SOLO el token del libro + retry único** (`laudus_service.py`) — era la única llamada de red sin el manejo de token expirado que `get_info_API` sí tiene, y ahora es la PRIMERA de toda corrida: en el backend long-lived (`/sync/trigger`) un token expirado quedaba en `_tokens` para siempre → todas las corridas siguientes fallaban hasta reiniciar el proceso. +2 tests (retry con login fresco; 401 persistente propaga sin loop).
- [x] **Test del wiring `fetch_fn=None → partial(default_fetch, book)`** (`test_laudus_run.py`) — el camino de prod real no tenía cobertura (todos los tests inyectan fetch_fn); un error en ese wiring pasaba la suite completa.
- [x] **Guard anti-drift `ALL_BOOK_ENTITIES == VALID_ENTITIES`** (`test_book_config.py`) — pipeline y backend mantienen dos registros de la misma noción de entidad; si divergen, `_account_in_book` y `_entity_from_path` clasificarían la misma cuenta distinto.

**Defer (anotados en deferred-work.md § 12-2):**
- [x] `bootstrap/generate_opening_balances` + `validate_cuadratura` con índice propio last-wins → resuelven las 31 colisiones a RUT2 desde 12.3 (scripts offline; scoping por libro en 12.4).
- [x] `book=None` permisivo en el writer (teórico, 0 callers de prod; incluye corrección documental: la decisión 5 citaba un import de bootstrap que no existe — bootstrap define su propia función).
- [x] Corrida RUT2 commitearía datos que bean-check no ve hasta el include de 12.4 (validar lo escrito antes de activar el include).
- [x] Re-login mid-run sin re-verificar identidad (teórico, mismo VAT).
- [x] Choque de rebase en `import-log.jsonl` entre clones EAG/RUT2 (failed+retry, dato a salvo; relevante recién con cron RUT2).

**Dismiss:** `export IMPORTER_BOOK=EAG` incondicional en el cron (Task 1 lo pide explícito; cron dedicado-EAG, determinista); `pending_entity` dígito 5/9/0 → FFCC (default firmado en la story); camino no-op commitea import-log sin verify (no escribe datos del libro; inalcanzable en incremental — `get_date_range` acota from_date ≤ hoy); campo aditivo `"book"` en el import-log EAG (el lector filtra por `importer`, sin efecto); `fetch_fn` inyectado salta el verify (documentado en docstrings; solo tests — los 3 entry points de prod usan el default); `target_dir.mkdir` antes del lock/verify (deja un dir vacío, cosmético).

## Change Log

- 2026-07-11 — Story 12.2 implementada completa (Tasks 1-5, AC1-AC5) por Amelia (claude-fable-5). Suite 828 passed / 1 xfailed (baseline 784/1, +44 nuevos, 0 regresiones); corrida EAG byte-idéntica pre/post verificada. Status → review.
- 2026-07-11 — Code review 3 capas: AC1–AC5 PASS; 3 patches aplicados (retry 401 en verify_book_identity + tests de wiring y anti-drift; suite 842/1 verde), 5 defers anotados. Queda 1 decision-needed (23 cuentas de hijas cambian entity en bank_account_index — ratificar como fix o revertir). Status se mantiene en review hasta la decisión de Ary.
- 2026-07-11 — Ary ratifica el decision-needed ("dejalo como quedó"): las 23 cuentas de hijas conservan su entity correcta por path. Se agrega `test_hijas_con_categoria1_mayuscula_de_prod_resuelven_por_path` (fixture con categoria1 MAYÚSCULA real de prod) que pinnea la decisión. Suite 843 passed / 1 xfailed. Status → done.
