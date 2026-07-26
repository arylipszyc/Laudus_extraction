# Story E1.6: Verificación lado-Odoo (gate de release)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contadora**,
I want **el verificador que corre contra Odoo post-carga (paridad origen + destino + clasificación + muestreo dirigido), como gate de release**,
so that **antes de dar E1 por cerrado tengo la prueba al peso Y la prueba de que la clasificación no está podrida por debajo**.

## Contexto (qué construye E1.6 y qué NO)

Séptima y ÚLTIMA story de Epic E1. La cadena está completa y cargable: transformadores verdes
(`collapse → sincerar → dimensionar`, suite 439/14) y loader idempotente probado contra Odoo real
(E1.5: Tier B 7/7, golden slice). E1.6 construye **el otro lado del espejo**: el verificador que lee
lo que quedó EN Odoo y lo compara contra el mirror — el gate de aceptación de todo el epic
(winston §6: "0 diffs en los 569 códigos × moneda, ambas compañías, toda la historia").

**Lección CENTRAL del review E1.5 (P1) — el porqué de esta story tal como está:** la paridad por
`x_laudus_account_code` es **necesaria pero NO suficiente**. El crítico del review lo demostró
empíricamente: el loader ruteaba 182 líneas a la cuenta EQUIVOCADA (ignoraba el sinceramiento) y la
paridad por código daba 0 diffs igual, porque el código viaja correcto aunque la cuenta esté mal.
Por eso E1.6 verifica **tres planos**: (1) paridad ORIGEN por código × moneda × compañía (FR8, al
peso), (2) paridad DESTINO por cuenta Odoo REAL (`account_id`) contra lo que la cadena dice que
debe haber en cada cuenta (FR12 — pesca ruteo podrido), y (3) conteos + invariantes estructurales
(FR12b: N asientos/líneas, posted, sin duplicados por `x_laudus_je_id`, líneas 211005 == payload).

Dos capas, patrón de la casa (NFR3): el lado ESPERADO se deriva del mirror/cadena en Python puro
(Tier A, testeable sin Docker); el lado ODOO se lee vía XML-RPC y el diff corre como **gate de
release Tier B** (`-m odoo`). El muestreo dirigido (FR12d) genera un reporte para firma humana.

> **El full load real al VPS NO es de esta story** (gates: D-1 Valentina + VPS Hetzner + medir 1 año,
> winston §9). E1.6 deja el verificador CONSTRUIDO y probado sobre el golden en el compose; la corrida
> operativa full-history usa este mismo CLI cuando esos gates se levanten.

## Acceptance Criteria

Copiadas del epic (`epics.md` → Story E1.6), formato Given/When/Then:

**AC1 — Paridad origen al peso (FR8)**
**Given** la carga completa en Odoo,
**When** corre el verificador **Tier B** (query a `account.move.line`),
**Then** `Σ por x_laudus_account_code, por moneda == saldo Laudus` con **0 diffs** en los 569 códigos, ambas compañías, toda la historia.

**AC2 — Gate de destino (FR12)**
**Given** el gate de destino,
**When** corre,
**Then** valida Σ por cuenta destino, conteo de líneas/asientos, y el resultado del sinceramiento (ingreso −46B, activos de origen +ese monto).

**AC3 — Muestreo dirigido (FR12d)**
**Given** el muestreo dirigido,
**When** se seleccionan los **20 asientos de mayor monto + 20 aleatorios con seed fijo** (N pineado por determinismo, NFR1; misma selección en cada corrida),
**Then** se revisan a mano contra Laudus (cuenta + partner + dimensión) y se firma el resultado.

**AC4 — Tiers en su lugar**
**Given** los dos tiers de verificación,
**When** se define dónde vive el gate,
**Then** Tier A (Python puro) corre **por-push en CI**; Tier B (Odoo, lento) corre como **gate de release en el contenedor**, no por-commit (lección `tsc --noEmit`: el gate tiene que ser el comando real, no un no-op).

## Alcance — qué SÍ y qué NO hace E1.6

**SÍ (deliverables):**
- `pipeline/odoo_migration/verify_odoo.py` — el verificador: lado esperado PURO (funciones que
  derivan del mirror/cadena los saldos por código × moneda × compañía, los saldos por cuenta
  destino, y los conteos esperados) + lector Odoo vía XML-RPC (`read_group`, reusa `OdooClient`
  de `loader_rpc.py` — NO reinventar el cliente) + el diff con reporte programático + CLI
  `python -m pipeline.odoo_migration.verify_odoo`.
- Muestreo dirigido: selección determinística 20 mayores + 20 aleatorios (seed fijo pinneado) →
  reporte markdown por asiento (cuenta Odoo real + partner + dims + montos vs mirror) para firma
  de Ary/Valentina. La FIRMA es humana; esta story entrega el reporte.
- Reporte de cobertura de glosa (winston §6·B): el CLI adjunta los reportes que la cadena YA emite
  (sin-clasificar/revisar de E1.3, sin-match de E1.4) — no recalcula nada.
- `ParityError` con diffs programáticos (cierra defer E1.2): `origin_diffs`/`destination_diffs`
  como atributos de la excepción, no solo 5 reprs truncados en el mensaje.
- Tests: Tier A (lado esperado + selección de muestreo pinneada + mutaciones) y Tier B `-m odoo`
  (golden en el compose `migration_e1`: cargar con el loader E1.5 → verificar 0 diffs → **mutar
  un dato EN Odoo → el gate acusa**; un gate que no puede fallar es `tsc --noEmit`).
- README sección E1.6 (los 3 planos, cómo correr el gate de release, el CLI, y el aviso full load).

**NO (es de otra story / operación):**
- El **full load real** al VPS y su verificación full-history → corrida operativa post-E1 (gates
  D-1 + VPS + medir 1 año, winston §9). El Tier B de esta story prueba el verificador sobre el
  GOLDEN; el CLI queda listo para el full.
- Resolver D-1 Latinoamericana / preguntas 5-6 (numeración y nombre de cuentas) → Valentina.
- Optimizaciones de escala del LOADER (defer W2 E1.5: `_xmlid_map` sin paginar) → medición
  winston §9. El verificador usa `read_group` (agrega server-side) y no arrastra ese problema.
- Patrimonio (yate/avión/casas) → Epic E1B; su verificación es manual aparte (winston §5.3).
- Delta repetible / drift fino → Fase 2, brief §5.

## Tasks / Subtasks

- [x] **Task 1 — Lado esperado puro (Tier A) (AC1, AC2)**
  - [x] `verify_odoo.py`: `expected_origin(entries)` — reusa `parity.laudus_balances` TAL CUAL
    (mismo agrupador (company, code, currency) que ya dio 0 diffs en el Tier B de E1.5); NO
    escribir otro agregador.
  - [x] `expected_destination(payloads)` — Σ(debit−credit) por `(company, account_xmlid)` desde los
    `MovePayload` de `build_moves` (la MISMA fuente que el loader escribe; el plano que pesca el
    ruteo podrido — lección P1). Incluye las cuentas `accs_*` de origen sincerado.
  - [x] `expected_counts(payloads)` — N moves, N líneas, set de `(company, je_id)`.
  - [x] `sinceramiento_check(payloads, table)` — la cifra pinneada es DIRECCIONAL:
    `pre − post == Decimal("-45576501123")` (la expresión EXACTA del gate FR12c,
    `test_sinceramiento_full_mirror.py:89` — un `post − pre` natural da +45.576B y falla). El lado
    destino se deriva de las LÍNEAS ruteadas por el sinceramiento (`line.odoo_account` ≠ colapso),
    NO de totales por cuenta (una cuenta destino de tabla también recibe líneas no-sinceradas).
    Ojo: Molco FFCC (+2.895.757.384) va a GASTO, no a activo (pin E1.3) — "activos de origen" del
    AC es shorthand del epic.
- [x] **Task 2 — Lector Odoo + diff (AC1, AC2)**
  - [x] `OdooReader` fino sobre `OdooClient` (import de `loader_rpc`, cero deps nuevas):
    `read_group` de `account.move.line` con `groupby=[x_laudus_account_code, currency_id, company_id]`
    y `sum(amount_currency)` (para líneas en moneda compañía Odoo pone `amount_currency == debit−credit`
    — verificado en E1.5 Tier B); ídem por `account_id` con `sum(balance)`; conteos por `read_group`
    de `account.move` (state, company). Context `allowed_company_ids` SIEMPRE (las 2 cías).
  - [x] Diff: comparar esperado vs Odoo en los 3 planos → `ParityError` con `origin_diffs` /
    `destination_diffs` / `count_diffs` programáticos (cierra defer E1.2) y mensaje con los primeros
    N + total. **Columna por plano, explícito:** origen agrega `amount_currency`; destino agrega
    `balance` — son columnas ALMACENADAS INDEPENDIENTES en Odoo 18 (junto a debit/credit), no
    derivadas al leer. Invariantes extra: todos los moves `posted`; 0 duplicados
    `(company, x_laudus_je_id)`; 0 líneas con `x_laudus_*` vacíos; y **las líneas 211005 en Odoo ==
    exactamente las que la cadena emitió** (derivado del payload, NUNCA pinnear 0: en el golden son
    0 porque el par wash se excluye, pero en el full history SOBREVIVEN 2 patas sin par con
    Σ = −751.912.981 — un "invariante 211005 vacía" daría falsa alarma en la carga real correcta).
  - [x] Resolver cuentas Odoo → xmlid vía `ir.model.data` del namespace `__laudus__` (una query;
    los alias N→1 del chart: una cuenta puede tener N nombres `acc_*` — usar el xmlid del
    REPRESENTANTE que emite `build_chart`/`build_origin_accounts` para el matching, o mapear por
    `res_id` y comparar contra el set de aliases del payload).
- [x] **Task 3 — Muestreo dirigido (AC3)**
  - [x] Selección determinística sobre los payloads: 20 moves de mayor Σ|debit| + 20 aleatorios con
    `random.Random(20260723)` (seed pinneada — NFR1: misma selección en cada corrida; si un move
    está en ambos grupos, el aleatorio toma el siguiente). Test Tier A pinnea la selección del
    golden (con 5 moves: los 5 salen, sin duplicar).
  - [x] Reporte markdown (`--out`, default `_bmad-output/implementation-artifacts/e1-6-muestreo.md`):
    por move → fecha, je_id, compañía, ref; por línea → cuenta Odoo REAL (leída de Odoo, no del
    payload), código Laudus, monto, partner, dims. Columnas "esperado vs Odoo" y sección de firma.
  - [x] Adjuntar cobertura de glosa (winston §6·B.3-4): (a) glosas sin-match — sale directo de los
    reportes de `sincerar`/`dimensionar` que ya existen; (b) **histograma por-glosa de las cuentas
    MIXTO** — no existe pre-armado, pero es una agregación trivial de data que ya viaja: agrupar
    `LineRef.desc` de los reportes por glosa normalizada y contar. No recalcular clasificación.
- [x] **Task 4 — Tier B: el gate puede fallar (AC1–AC4)**
  - [x] `test_verify_odoo_tier_b.py` (marker `odoo`, patrón compose E1.1/E1.5 verbatim, db fresca
    `test_e16`): instalar módulo → cargar golden con `load_all` (E1.5) → `verify` → **0 diffs en
    los 3 planos** (paridad origen, destino por cuenta real incl. las 5 `accs_*` de Tecnión,
    conteos 5/18).
  - [x] **Mutaciones contra Odoo real** (la razón de ser del Tier B) — cada mutación debe tocar LA
    COLUMNA QUE SU PLANO AGREGA (debit/credit/balance/amount_currency son 4 columnas almacenadas
    independientes; un `UPDATE … SET debit` no mueve `amount_currency` ni `balance` y NINGÚN plano
    lo vería): (a) `UPDATE account_move_line SET amount_currency = amount_currency + 1000 …` →
    paridad ORIGEN acusa ese código; (b) mover una línea de cuenta (`account_id`; el plano destino
    agrega `balance` reagrupado) → paridad DESTINO acusa y la de origen NO — el test documenta que
    el plano 2 existe por eso; (c) borrar un move (draft+unlink como E1.5) → conteos acusan. Cada
    mutación se revierte o re-carga antes del siguiente assert.
  - [x] El reporte de muestreo se genera sobre el golden y el test verifica que la selección es
    estable (2 corridas → mismo archivo).
- [x] **Task 5 — Regresión + README + cierre de epic (AC4)**
  - [x] Suite completa `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q`:
    baseline **439 passed / 14 skipped** + los nuevos Tier A, 0 regresiones; Tier B nuevos quedan
    skipped sin `-m odoo`. `bean-check` verde (picklecache borrado antes).
  - [x] deferred-work.md: marcar cerrado el defer `ParityError sin diffs programáticos` (E1.2);
    NO tocar los demás (W1/W2/W3 de E1.5 siguen; fixture session-scoped sigue).
  - [x] README sección E1.6: los 3 planos y POR QUÉ existen (P1), comando del gate de release,
    CLI del verificador, muestreo, y el recordatorio: E1 NO se cierra sin el sign-off AC5 de E1.4
    (partición) ni la firma del muestreo — gates humanos.

### Review Findings

Code review adversarial 2026-07-25 (Blind Hunter + Edge Case Hunter + Acceptance Auditor).
Veredicto del auditor: los 4 ACs cumplidos, decisiones pinneadas y gotchas 1–9 honrados.
Los hallazgos se concentran en el CLI y en el reporte de muestreo (el artefacto que se firma):

- [x] [Review][Patch] El Δ FR12c del sinceramiento es print-only en el CLI — nunca afecta el exit code; en el full load un Δ podrido saldría exit 0 con mensaje "[ledger parcial]" [pipeline/odoo_migration/verify_odoo.py:727-735]
- [x] [Review][Patch] `main()` nunca corre el gate Tier A del mirror (`run_tier_a` con `excluded_je_ids`) sobre el ledger vivo — una exclusión equivocada que netea a 0 por código es invisible a los 3 planos Odoo [pipeline/odoo_migration/verify_odoo.py:704-714]
- [x] [Review][Patch] Reporte de muestreo: pareo POSICIONAL payload↔Odoo (`odoo_rows[n]`) en vez de por identidad `aml_*` — una línea corrida cruza cuenta/partner/dims de TODAS las siguientes en el documento que se firma [pipeline/odoo_migration/verify_odoo.py:578-598]
- [x] [Review][Patch] Reporte de muestreo: debit/credit mostrados salen del PAYLOAD, no de Odoo (que `sample_lines` ya trae y se descarta) — el firmante cree validar lo que quedó en Odoo [pipeline/odoo_migration/verify_odoo.py:593-597]
- [x] [Review][Patch] Líneas EXTRA en Odoo: el reporte las cuenta pero no las vuelca (cuenta/montos ocultos al firmante) [pipeline/odoo_migration/verify_odoo.py:599-602]
- [x] [Review][Patch] Contrato de errores del CLI: `RuntimeError` con mensaje imposible ("el plano 3 debería haberlo acusado" — el plano 1 corre primero) + "OK" impreso antes de que el muestreo pueda reventar → traceback crudo tras un OK [pipeline/odoo_migration/verify_odoo.py:331-336,723-748]
- [x] [Review][Patch] `diff_origin` compara mirror SIN cuantizar vs Odoo cuantizado a 0.01 — monto no-CLP con >2 decimales daría diff fantasma en el full load [pipeline/odoo_migration/verify_odoo.py:180-191]
- [x] [Review][Patch] `sinceramiento_check` descarta en silencio patas sinceradas no-CLP ruteadas desde Income — subestima el Δ sin aviso ante data futura [pipeline/odoo_migration/verify_odoo.py:143-154]
- [x] [Review][Patch] `analytic_names()` sin `context=self._ctx` — contradice el "SIEMPRE" del docstring de `OdooReader`; una analítica acotada por compañía degradaría a `id=N` en silencio [pipeline/odoo_migration/verify_odoo.py:446-452]
- [x] [Review][Patch] `test_mutacion_c` sin try/finally: un assert fallido deja la db sin `mv_eag_4158` y el test de muestreo cae en cascada enmascarando la causa [pipeline/odoo_migration/tests/test_verify_odoo_tier_b.py:280-306]
- [x] [Review][Patch] `_line_id` (y las queries inline de mutación c) mueren en `int('')` sin nombrar el xmlid faltante [pipeline/odoo_migration/tests/test_verify_odoo_tier_b.py:121-126,282-285]
- [x] [Review][Patch] Prints del CLI con Δ/⚠️ revientan en consola cp1252 sin `PYTHONUTF8=1` — crash DESPUÉS del gate verde, antes de escribir el reporte [pipeline/odoo_migration/verify_odoo.py:723-748]
- [x] [Review][Patch] Celdas markdown del reporte sin escapar `|`/saltos de línea (glosas Laudus, partners) — columnas corridas en el documento firmado [pipeline/odoo_migration/verify_odoo.py:593-647]
- [x] [Review][Patch] `_fmt_dims` ordena ids analíticos como strings ("10" antes que "3") [pipeline/odoo_migration/verify_odoo.py:534]

Descartados (5): re-check `accs_*` redundante en Tier B (el pin de las 5 keys sí aporta; el
re-diff es inofensivo), pickle de `ParityError` pierde diffs (sin xdist/multiprocessing en este
repo), fixture `full_mirror_chain` "invisible" (existe en `conftest.py`, verificado), lista
`revisar` E1.3 solo como conteo (Task 3 es la descomposición autoritativa; el resumen la trae),
`sinceramiento_check(moves)` en vez de payloads (desviación documentada y legítima).

## Dev Notes

### Decisiones ya tomadas — NO re-litigar

- **Paridad por línea agrupando por código origen** (winston §6, decisión #5): invariante al colapso
  Y al sinceramiento; convención de signo `Σ(debit−credit) == Σ(units.number)`; por moneda (CLP vs
  CLP, USD vs USD, nominal — IAS 21 es Fase 3). El agrupador ya está probado (E1.5 Tier B, 0 diffs).
- **El verificador habla XML-RPC, no psql** (winston §6: "XML-RPC o Postgres directo" — se elige
  XML-RPC): el mismo canal del loader, funciona igual contra el compose local y el VPS remoto, y
  `read_group` agrega server-side (no arrastra 57k líneas por el socket). El Tier B puede
  cross-checkear con `_psql` puntualmente (patrón E1.5), pero el CLI es RPC puro.
- **Tres planos, no uno** (review E1.5 P1): origen (código) + destino (cuenta real) + conteos.
  La paridad origen SOLA demostró ser ciega al ruteo. No colapsar los planos "porque origen ya da 0".
- **Tier A por-push / Tier B opt-in `-m odoo`** — ya vigente (conftest). El gate por-commit es la
  suite completa del comando real de project-context.md; NO inventar otro comando (AC4).
- **N del muestreo pinneado**: 20 mayores + 20 aleatorios seed fijo (readiness report 2026-07-24,
  ítem 2). La seed se pinnea como literal en el código y en el test.
- **Reusar, no reinventar**: `laudus_balances`/`verify_*` (parity.py E1.2), `route_sincerado`
  (sincerar.py), `OdooClient` (loader_rpc.py E1.5), `build_chart/build_origin_accounts/build_moves`
  (load.py E1.5) y los helpers compose del Tier B (E1.1/E1.5). Todo el lado esperado SALE de esas
  piezas.

### Data real verificada (2026-07-25/26 — leer antes de codear)

1. **Números del golden (post-E1.5, pinneables):** 5 moves posteados (EAG 4 / RUT2 1), 18 líneas,
   366 cuentas (361 tabla + **5 de origen sincerado REALES** — las patas naturaleza-B del JE 1237
   van a `Assets:*:InvTecnion` vía `accs_*`), 6 analíticas entidad, paridad por (company, code,
   currency) == mirror con 0 diffs. El asiento USD 9000003: `amount_currency=100.00`, debit 80.000.
2. **Números del mirror completo (cadena en ~2 min local):** 16.623 move-payloads, 56.740 líneas,
   chart 382 (361 + 21 orígenes), 182 líneas rutean a `accs_*`. El verificador full-history debe
   digerir eso — con `read_group` el tamaño del resultado es ~570 códigos × moneda, trivial.
   **⚠️ NO pinnear estos conteos full-mirror como literales en tests de E1.6:** D-1 sigue abierta
   y su resolución "mueve conteos pinneados" (deferred-work E1.3 — excluiría ~5 moves). El esperado
   full se deriva de los payloads EN RUNTIME; los únicos pins literales son del golden.
3. **Gotcha Odoo 18 — `account.account.code` es company-dependent:** NO es columna SQL; vive en el
   jsonb `code_store` keyed por id de compañía (`a.code_store ->> co.id::text` en SQL crudo; por
   ORM/RPC leer `code` con context de UNA compañía). El Tier B de E1.5 ya pagó este peaje — copiar
   el patrón, no redescubrirlo.
4. **`amount_currency` en líneas CLP:** Odoo lo puebla == `debit − credit` (currency_id = moneda
   compañía). Por eso el agrupador único `sum(amount_currency)` por código × moneda sirve para las
   dos monedas a la vez (probado E1.5 Tier B, AC3).
5. **Los washes excluidos netean a 0 — pero 211005 NO queda vacía en el full:** el diff debe tratar
   "código ausente en Odoo con saldo mirror 0" como OK y "ausente con saldo ≠ 0" como diff (patrón
   del test AC3 de E1.5). OJO: en el golden 211005 queda sin líneas (su único uso era el par wash),
   pero en la historia completa **2 patas 211005 sin par sobreviven al sinceramiento
   (Σ = −751.912.981)** y quedan en su lugar (SPEC paso 4) — en el full, 211005 SÍ existe en Odoo
   con saldo ≠ 0 y la paridad origen cuadra igual (el mirror trae lo mismo). No convertir el caso
   golden en invariante.
6. **`read_group` multi-groupby vía XML-RPC — NO probado aún en este repo** (lo que E1.5 verificó
   fue la semántica `amount_currency == debit−credit`, vía SQL crudo, no `read_group` por RPC).
   Gotchas del camino nuevo: el agregado se pide como `'amount_currency:sum'` en `fields`;
   `lazy=False` para agrupar por los 3 campos de una vez (el resultado trae `__domain`/`__count`);
   los groupby m2o (`currency_id`, `company_id`, `account_id`) vuelven como `[id, display_name]`;
   los agregados llegan como **float** por XML-RPC → convertir `Decimal(str(v)).quantize(Decimal("0.01"))`
   ANTES de comparar contra 0 exacto (el ruido binario en centavos crearía diffs fantasma).
   `x_laudus_account_code` está indexado (E1.1) — es la query más caliente del sistema (winston §4).
   Conteo esperado de grupos: ~570 × ~2 monedas × 2 cías máximo.
7. **Duplicados `x_laudus_je_id`:** la adopción de huérfanos de E1.5 (review P2) ya previene el
   caso nuevo, pero el verificador chequea igual (belt-and-suspenders para dbs cargadas con
   versiones previas del loader o corridas manuales).
8. **"569 códigos" del AC = 568 con código + 1 fila sin code (Suspense, excluida):** verdad
   establecida en E1.2 (números reales ≠ resumen). El universo de la paridad son los 568 códigos
   reales; el diff no debe esperar un código 569 que no existe.
9. **El sinceramiento en cifras (para AC2):** Δ ingreso EXACTO −45.576.501.123 (gate FR12c de E1.3,
   corre por-commit sobre el mirror); Sade +4.876.249.792 y Molco FFCC +2.895.757.384 ya pinneados.
   El lado Odoo de esto = Σ por las cuentas destino del sinceramiento — derivar del MISMO payload,
   no inventar una tercera fuente.

### Cómo encaja con E1.0–E1.5 (el contrato)

- **El lado esperado es EXACTAMENTE lo que el loader escribió:** `chart = build_chart(table) +
  build_origin_accounts(moves, table)`; `payloads = build_moves(moves, chart)`. Si el verificador
  deriva el esperado de otra ruta (p.ej. re-clasificando por su cuenta), un bug compartido se
  auto-valida. La INDEPENDENCIA la da el plano origen (mirror crudo vía `laudus_balances`, sin
  pasar por la cadena) — mantener esa asimetría: origen = mirror puro, destino = cadena.
- **xmlids:** el namespace `__laudus__` tiene los 4 tipos (`acc_*`/`accs_*`/`mv_*`/`aml_*` +
  `prt_*`/`aa_*`). Para mapear `account_id → payload` usar `ir.model.data` (una query, filtrar
  `model = account.account`).
- **Learnings de reviews previos (aplicar de entrada):** (a) fail-loud con contexto; (b) el gate
  DEBE poder fallar — tests de mutación contra Odoo real, no solo asserts verdes; (c) pins con
  literales derivados una vez, nunca llamando al helper que se testea; (d) diffs programáticos en
  la excepción (el defer que esta story cierra); (e) no depender de internos de Odoo — `read_group`
  y `search_read` son API pública.
- **Defers que esta story CIERRA:** ParityError sin diffs programáticos (E1.2). **Defers que NO
  toca:** W1 credenciales/TLS (runbook VPS), W2 escala `_xmlid_map` del loader (medición §9),
  W3 `exec -i` (smokes), YAML duplicados, fixture session-scoped, D-1 (Valentina).

### Tier B — infra de test (patrón E1.1/E1.5 verbatim)

- Compose `migration_e1` puerto 8070, db fresca `test_e16` (dropdb + `-i x_laudus_migration
  --without-demo all`), helpers `_compose`/`_psql`/`_wait_*` duplicados con nota (defer E1.0/E1.1
  de endurecer skips sigue vigente — no resolverlo acá).
- El test CARGA con `load_all` de E1.5 (import directo, como `test_loader_idempotente.py`) y
  después verifica. Presupuesto: install ~40s + carga golden + 3 mutaciones — mantener el módulo
  bajo ~3 min.
- Las mutaciones SQL van por `_psql` (UPDATE directo — Odoo no permite editar posted vía ORM, y
  justamente queremos corromper por debajo para que el gate acuse).

### Project Structure Notes

- Código nuevo: `pipeline/odoo_migration/verify_odoo.py` (esperado puro + lector RPC + diff + CLI
  + muestreo). Hermano de parity/load/loader_rpc — mismo estilo docstring-contrato.
- Modificación quirúrgica: `parity.py` SOLO para los diffs programáticos de `ParityError`
  (atributos nuevos, mensaje intacto — hay tests que matchean el mensaje).
- Tests nuevos: `tests/test_verify_odoo.py` (Tier A) + `tests/test_verify_odoo_tier_b.py` (Tier B
  `-m odoo`).
- README del paquete: sección E1.6.

### Testing Requirements

- **Comando real (NO inventar otro):** `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q`
  (suite completa) / `… -m pytest pipeline/odoo_migration -q` (iterar Tier A) /
  `… -m pytest pipeline/odoo_migration/tests/test_verify_odoo_tier_b.py -m odoo -q` (Tier B, Docker).
  [Source: project-context.md]
- Baseline actual: **439 passed / 14 skipped** (post-review E1.5, commit 3bc29d2). 0 regresiones.
- `bean-check` del mirror (picklecache borrado antes) — E1.6 solo LEE el ledger.

### References

- [Source: _bmad-output/planning-artifacts/odoo-migracion/epics.md#Story-E1.6] — ACs.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/winston-arquitectura-e1-odoo-2026-07-23.md#6, #6·B, #5.3, #9] —
  mecanismo de paridad 3 pasos, cobertura de glosa, qué queda fuera del gate, gates del full load.
- [Source: _bmad-output/implementation-artifacts/E1-5-loader-idempotente-odoo.md] — loader + review
  P1 (el porqué del plano destino) + gotchas Odoo 18 + patrón Tier B.
- [Source: pipeline/odoo_migration/parity.py] — laudus_balances / verify_* / run_tier_a (E1.2).
- [Source: pipeline/odoo_migration/load.py + loader_rpc.py] — payloads y cliente a reusar.
- [Source: pipeline/odoo_migration/tests/test_loader_idempotente.py] — agrupador probado + compose.
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-07-24.md] — N muestreo pinneado.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — defer ParityError que E1.6 cierra.

### Preguntas guardadas para Ary / Valentina (no bloquean el dev)

1. **Firma del muestreo (AC3):** el reporte queda generado; la revisión a mano contra Laudus y la
   firma son de Ary/Valentina. Proponer sesión cuando el reporte exista (sobre el golden primero;
   el full cuando haya full load).
2. **Cierre de Epic E1:** con E1.6 done quedan pendientes los gates humanos — sign-off AC5 de E1.4
   (partición), firma del muestreo, D-1, preguntas 5-6 — y el cierre de epic requiere aprobación
   explícita de Ary (project-context: gate de cierre de épica).

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) — dev-story 2026-07-26

### Implementation Plan

1. Patch quirúrgico `parity.py`: `ParityError.__init__` con `origin_diffs`/
   `destination_diffs`/`count_diffs` (defaults vacíos — construcción pelada de
   tests existentes sigue funcionando); `run_tier_a` los adjunta. Mensaje
   INTACTO (hay tests que lo matchean).
2. `verify_odoo.py` nuevo, tres secciones: (a) lado esperado PURO —
   `expected_origin = laudus_balances` (alias, no wrapper: el AC exige el
   agrupador de E1.2 tal cual), `expected_destination` desde `MovePayload`
   (Σ debit−credit por (company, account_xmlid)), `expected_counts`
   (identidades + líneas + 211005 DERIVADO), `sinceramiento_check` (Δ
   direccional pre−post desde las líneas ruteadas, no totales por cuenta);
   (b) diffs puros por plano (`diff_origin`/`diff_destination`/`diff_counts`)
   — testeables sin Odoo, con resolución de alias N→1 vía ir.model.data;
   (c) `OdooReader` sobre `OdooClient` (read_group lazy=False, agregados
   float→Decimal 2 dec, context allowed_company_ids siempre) + `verify()`
   orquestador + muestreo (`select_sample` seed 20260723, `build_muestreo_report`
   determinístico sin timestamps, `glosa_histogram`) + CLI.
3. Tier A (`test_verify_odoo.py`): pins del golden derivados una vez
   (destinos accs_*, identidades, delta −1.704.500.000), pin FR12c full-mirror
   por OTRA ruta (líneas ruteadas), mutaciones puras por plano, muestreo
   estable/sensible-a-seed, diffs programáticos, reporte determinístico.
4. Tier B (`test_verify_odoo_tier_b.py`, db `test_e16`): cargar golden con
   `load_all` E1.5 → 0 diffs 3 planos → mutaciones SQL contra la COLUMNA que
   cada plano agrega (amount_currency / account_id / unlink) con revert →
   muestreo 2 corridas == mismo archivo.
5. Regresión completa + bean-check + README E1.6 + cierre defer E1.2 en
   deferred-work.md.

### Debug Log References

- Pins del golden derivados UNA vez (2026-07-26, script one-shot): 16 destinos
  con movimiento, 5 `accs_*` Tecnión (EAG −1.022.700.000; Jael/Jeannette/
  Jocelyn/Johanna −170.450.000 c/u), identidades {EAG:29, EAG:1237, EAG:4158,
  EAG:9000003, RUT2:3994}, 211005 = (0, 0) derivado, Δ sinceramiento golden
  −1.704.500.000, selección muestreo estable.
- Tier B `-m odoo` (db `test_e16`): **5/5 en 82s** — gate verde 3 planos,
  mutación (a) amount_currency → origen acusa (diff −1000.00, código real
  leído de la db), mutación (b) account_id → destino acusa 2 diffs y origen
  NO (P1 documentado), mutación (c) unlink → conteos acusan + reconverge con
  `load_all`, muestreo 2 corridas == mismo string.
- CLI ejercitado end-to-end contra stack real: loader E1.5 → `verify_odoo
  --db test_e16` exit 0 (0 diffs, Δ impreso, muestreo escrito); mutación SQL
  → exit 1 con diff programático (111007) → revertida → verde de nuevo.
- Suite completa: **467 passed / 19 skipped** (= baseline 439/14 + 28 Tier A
  nuevos + 5 Tier B nuevos skipped) — 0 regresiones. `bean-check` verde
  (picklecache borrado antes).
- Ajuste sobre el plan de la story: `sinceramiento_check` recibe los MOVES
  dimensionados (no los payloads) — la story pedía derivar de las líneas
  ruteadas (`odoo_account ≠ colapso`) y esa metadata viaja en
  `OdooLineRecord`, no en `MovePayload`. El pin FR12c full-mirror se verifica
  por esta OTRA ruta y da el mismo número (−45.576.501.123, direccional).
- La mutación (c) no necesita limpiar `ir.model.data` a mano: el unlink vía
  ORM borra los xmlids (mismo camino que el test AC2 de E1.5).

### Completion Notes List

- ✅ **Task 1** — lado esperado puro: `expected_origin = laudus_balances`
  (alias, el MISMO objeto función — test lo pinnea con `is`),
  `expected_destination` desde `MovePayload` (Σ debit−credit por
  (company, account_xmlid), `accs_*` incluidas), `expected_counts`
  (identidades + líneas + 211005 DERIVADO del payload, nunca pinneado a 0),
  `sinceramiento_check` (Δ DIRECCIONAL pre−post desde las líneas ruteadas +
  Σ por destino; pin FR12c full-mirror verificado por otra ruta).
- ✅ **Task 2** — `OdooReader` sobre `OdooClient` (cero deps nuevas):
  `read_group` lazy=False multi-groupby, agregados float→`Decimal(str(v))
  .quantize(0.01)` antes de comparar contra 0 exacto, context
  `allowed_company_ids` siempre; diffs puros por plano (origen reusa
  `ParityDiff`; destino `OdooDestinationDiff` con resolución de alias N→1 vía
  `ir.model.data`, cuenta con saldo sin xmlid del namespace = diff etiquetado;
  conteos con duplicados/ausentes/extra/no-posteados/x_laudus_ vacíos/211005).
  `verify()` levanta `ParityError` con los 3 sets de diffs programáticos.
- ✅ **Task 3** — `select_sample` (20 mayores por Σ debit + 20 aleatorios
  `random.Random(20260723)` sobre el pool depurado — sin solape, estable,
  sensible a la seed), `build_muestreo_report` (markdown determinístico SIN
  timestamps, cuenta/partner/dims LEÍDOS de Odoo, líneas ausentes/extra
  acusadas, sección de firma Ary/Valentina) + anexo cobertura de glosa
  (resúmenes E1.3/E1.4 + histograma por-glosa normalizada de las patas MIXTO
  sin clasificar + listado sin-match AC5). Reporte real del golden generado en
  `_bmad-output/implementation-artifacts/e1-6-muestreo.md` (firma pendiente).
- ✅ **Task 4** — Tier B `test_verify_odoo_tier_b.py` (patrón compose E1.1/E1.5
  verbatim, db fresca `test_e16`, carga con `load_all` E1.5): 0 diffs en los
  3 planos + las 3 mutaciones contra la COLUMNA que cada plano agrega, con
  revert/reconvergencia, + muestreo estable. 5/5 en 82s (bajo el presupuesto
  de ~3 min).
- ✅ **Task 5** — suite completa 467/19 (0 regresiones sobre baseline 439/14),
  bean-check verde, README sección E1.6 (3 planos + P1 + comandos + aviso
  full load + gates humanos), deferred-work: defer `ParityError sin diffs
  programáticos` (E1.2) CERRADO; W1/W2/W3 de E1.5, YAML duplicados, fixture
  session-scoped y D-1 quedan intactos.
- ✅ Resolved review finding (defer E1.2): `ParityError` con
  `origin_diffs`/`destination_diffs`/`count_diffs` como atributos — mensaje
  intacto (los tests que lo matchean siguen verdes), construcción pelada
  sigue funcionando (defaults vacíos).

### File List

- `pipeline/odoo_migration/verify_odoo.py` — NUEVO: verificador 3 planos +
  muestreo + CLI.
- `pipeline/odoo_migration/parity.py` — MODIFICADO (quirúrgico): `ParityError`
  con diffs programáticos; `run_tier_a` los adjunta. Mensaje intacto.
- `pipeline/odoo_migration/tests/test_verify_odoo.py` — NUEVO: 28 tests Tier A.
- `pipeline/odoo_migration/tests/test_verify_odoo_tier_b.py` — NUEVO: 5 tests
  Tier B (`-m odoo`, db `test_e16`).
- `pipeline/odoo_migration/README.md` — MODIFICADO: sección E1.6.
- `_bmad-output/implementation-artifacts/deferred-work.md` — MODIFICADO:
  defer ParityError (E1.2) marcado cerrado.
- `_bmad-output/implementation-artifacts/e1-6-muestreo.md` — NUEVO (generado
  por el CLI sobre el golden): reporte de muestreo para firma.
- `_bmad-output/implementation-artifacts/E1-6-verificacion-lado-odoo.md` —
  MODIFICADO: tracking de la story.

## Change Log

- 2026-07-26 — Story E1.6 creada (create-story: epic + winston §6/§6·B + lección P1 del review
  E1.5 + data real del golden/mirror post-E1.5 + defers heredados). Validador de contexto fresco:
  2 críticos corregidos ANTES del dev — (1) "211005 vacía" era falso en full history (2 patas sin
  par sobreviven, Σ −751.912.981; el invariante ahora se deriva del payload) y (2) la mutación (a)
  del Tier B apuntaba a `debit`, columna que ningún plano agrega (ahora muta `amount_currency`);
  + 4 mejoras (dirección del Δ pinneado, Molco→gasto, gotchas read_group RPC, histograma §6·B) y
  3 optimizaciones (wording del epic, filename Tier B, guarda D-1 sobre conteos). Status: ready-for-dev.
- 2026-07-26 — Implementación completa (dev-story, Claude Fable 5): `verify_odoo.py` (3 planos +
  muestreo + CLI) + `ParityError` con diffs programáticos (cierra defer E1.2) + 28 tests Tier A +
  5 tests Tier B con mutaciones contra Odoo real (5/5 en 82s) + CLI ejercitado end-to-end (verde
  exit 0 / mutado exit 1). Suite 467/19 (baseline 439/14, 0 regresiones), bean-check verde. README
  sección E1.6, deferred-work actualizado, reporte de muestreo del golden generado (firma
  pendiente). Ajuste documentado: `sinceramiento_check` toma los moves dimensionados, no los
  payloads (la metadata de ruteo viaja en `OdooLineRecord`). Status: review.
- 2026-07-25 — Code review adversarial (3 capas: Blind Hunter + Edge Case Hunter + Acceptance
  Auditor). Los 4 ACs cumplidos; 14 patches aplicados, 5 hallazgos descartados, 0 defers. Los
  patches grandes: (1) `--full` convierte el pin FR12c en gate real del CLI; (2) el CLI ahora corre
  `run_tier_a` sobre el ledger VIVO (exclusiones por identidad — invisible a los 3 planos Odoo);
  (3) el reporte de muestreo parea por identidad `aml_*` (no por posición), muestra los montos
  LEÍDOS de Odoo junto a los esperados y vuelca las líneas extra; + robustez (quantize ambos lados,
  fail-loud no-CLP, contrato de errores del CLI, try/finally mutación c, escaping markdown, stdout
  ASCII). Verificado: suite 470/19 (0 regresiones), Tier B 5/5 en 87s, CLI end-to-end exit 0 y
  reporte de muestreo REGENERADO con el código final. Status: done.
