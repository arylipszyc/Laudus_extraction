# Story E1.5: Loader idempotente (full history) hacia Odoo

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **family office**,
I want **cargar toda la historia a Odoo vía loader con external IDs, probadamente idempotente y sin doble-carga de apertura**,
so that **Odoo tiene la historia completa y re-correr el loader nunca duplica ni infla el historial**.

## Contexto (qué construye E1.5 y qué NO)

Sexta story de Epic E1 — **el loader: la ÚNICA pieza que toca Odoo** (winston §2.4 "nota de honestidad
arquitectónica"). La cadena de transformadores está completa y verde (`collapse → sincerar → dimensionar`,
Tier A, 412/7); E1.5 la convierte en registros REALES de Odoo 18 vía RPC, con external IDs determinísticos
(E1.0, congelados) para que re-correr haga **upsert, no duplicados** (FR11). El módulo receptor
`x_laudus_migration` (E1.1) ya deja listas las 2 compañías (EAG/RUT2) sin `l10n_cl`, los diarios LAU1/LAU2
y los 6 planes analíticos contenedores.

Dos capas a propósito (la lección NFR3 del proyecto: el 90% de la lógica se testea sin infra):

1. **Payload builder (Tier A, Python puro):** funciones puras que convierten el output de la cadena +
   la tabla de mapeo en payloads Odoo (chart colapsado, partners, cuentas analíticas, moves con
   debit/credit + `amount_currency` + `partner_id` + `analytic_distribution`) con su xmlid cada uno.
   Acá vive TODA la lógica: se testea por-commit sin Docker.
2. **Cliente + upsert (Tier B, opt-in `-m odoo`):** capa fina XML-RPC (stdlib `xmlrpc.client`, cero deps
   nuevas) que aplica los payloads con skip-si-existe por external ID y postea. Se prueba contra el
   compose propio (`migration_e1`, puerto 8070) **sobre el golden slice** — la idempotencia 2× y el caso
   borrar-mitad/re-correr son ACs, no promesas.

**E1.5 cierra 3 defers que las stories anteriores le asignaron explícitamente** (deferred-work.md):
`posting.price` no conservado en `OdooLineRecord` (E1.2 — sin él no hay `amount_currency`/contravalor CLP),
validación de `otype` con población cerrada (E1.2) y consistencia `(company, odoo_account) → otype` (E1.2,
reforzado por E1.4: un typo en `otype` apaga la regla beneficiario en silencio).

> **Arquitectura aprobada** (winston §2.3, §7 — resumen ejecutivo §0 aprobado por Ary 2026-07-24). Detalle
> técnico auto-aprobado según `project-context.md`. **D-1 (residual Latinoamericana) sigue pendiente de
> Valentina** — no bloquea ESTA story (las 10 patas netean a 0 y viajan marcadas `latam-sin-par`/revisar),
> pero el defer dice "resolver antes de E1.5" refiriéndose al **full load real al VPS**: queda como
> pregunta guardada 1, gate humano antes de la corrida productiva (el loader es re-corrible, converge).

## Acceptance Criteria

Copiadas del epic (`epics.md` → Story E1.5), formato Given/When/Then:

**AC1 — Carga con external IDs + posteo, ambas compañías**
**Given** el output de los transformadores,
**When** corre el loader (`odoo shell` / XML-RPC),
**Then** crea cuentas/asientos/líneas con **external IDs determinísticos** y postea los asientos, ambas compañías.

**AC2 — Idempotencia probada (FR11)**
**Given** la idempotencia (FR11),
**When** se corre el loader 2× sobre Odoo limpio,
**Then** el estado es **idéntico** (mismo N de asientos y saldos, 0 duplicados); y el caso de recuperación: correr / borrar la mitad / re-correr → **converge** al estado completo. (Probado sobre el golden slice, no sobre 5 años.)

**AC3 — Sin doble-conteo de apertura**
**Given** la apertura 2021,
**When** se carga,
**Then** **no hay doble-conteo de apertura** (AC explícito — ya causó ~727M fantasma una vez).

**AC4 — Multi-moneda USD**
**Given** multi-moneda,
**When** se cargan líneas USD,
**Then** llevan `currency_id`+`amount_currency` y el asiento CLP+USD del golden slice cuadra por moneda.

## Alcance — qué SÍ y qué NO hace E1.5

**SÍ (deliverables):**
- `pipeline/odoo_migration/load.py` — payload builder **puro** (Tier A): `build_chart`, `build_partners`,
  `build_analytic`, `build_moves` sobre (`DimensionadoResult`/moves, `MappingTable`) → payloads con xmlid.
  Incluye la validación de `otype` (población cerrada + consistencia por destino — cierra los 2 defers) y
  el mapeo `otype → account_type` de Odoo 18.
- `pipeline/odoo_migration/loader_rpc.py` — cliente XML-RPC fino + `load_all` (upsert por xmlid,
  create batcheado, `action_post`) + CLI `python -m pipeline.odoo_migration.loader_rpc` (url/db/password
  por args; NUNCA credenciales hardcodeadas fuera del default dev del compose).
- `transform.py`: campo `price` en `OdooLineRecord` (contravalor por unidad, `posting.price`) — quirúrgico,
  default `None`, cierra el defer E1.2.
- `external_ids.py`: helpers NUEVOS `partner_xmlid` / `analytic_xmlid` (slug determinístico fail-loud sobre
  población cerrada). **Los 3 congelados (`acc_/mv_/aml_`) NO se tocan.**
- Tests: `test_load_payloads.py` (Tier A — payloads, xmlids, signos, USD, balance por move, mutaciones) +
  `test_loader_idempotente.py` (Tier B `-m odoo` — AC1–AC4 sobre el golden en el compose `migration_e1`).
- README del paquete: sección E1.5.

**NO (es de otra story / decisión):**
- Verificación lado-Odoo full-history (Tier B a escala, paridad 569 códigos × moneda, muestreo dirigido)
  → **E1.6**. El Tier B de E1.5 verifica el GOLDEN (paridad por código sobre ~7 asientos), no los 5 años.
- El **full load real** al VPS Hetzner (requiere VPS provisto + D-1 resuelto con Valentina + medir 1 año
  antes del full, winston §9) → corrida operativa post-E1.6, no un test de esta story.
- Resolver D-1 Latinoamericana (grupo 4-vs-1) → pendiente Valentina (deferred-work E1.3).
- Delta repetible fino (asientos Laudus editados/borrados tarde, watermark) → Fase 2 / decisión §5 del brief.
- Activos de patrimonio (yate/avión/casas) → Epic E1B, fuera de E1 (no cargar nada sin código Laudus).

## Tasks / Subtasks

- [x] **Task 1 — Contrato transformador → payload (Tier A) (AC1, AC4)**
  - [x] `transform.py`: `OdooLineRecord.price: Decimal | None = None` poblado desde `posting.price.number`
    en `collapse` (defer E1.2). Regla dura en el builder: línea con `currency != "CLP"` SIN `price` →
    fail-loud (sin contravalor no hay debit/credit); línea CLP ignora `price`.
  - [x] `load.py`: validación `otype` al construir el chart — población cerrada
    {asset, bank, receivable, liability, equity, income, expense} (los 7 valores reales del CSV) → mapeo
    fijo a `account_type` Odoo 18 (`asset_current`, `asset_cash`, `asset_receivable`, `liability_current`,
    `equity`, `income`, `expense`); `otype` desconocido/vacío o dos códigos que colapsan al mismo
    `(company, odoo_account)` con `otype` distinto → `ValueError` con contexto (cierra defers E1.2×2).
  - [x] `build_chart(mapping)`: una cuenta Odoo por `(company, odoo_account)` colapsado; `name` = el path
    `odoo` de la tabla; `code` = **el menor código Laudus origen** que colapsa a ella (determinístico,
    numérico, estable — las 1:1 conservan SU código; pregunta guardada 2 a Valentina); `x_laudus_group` =
    `cat2/cat3`; SIN `currency_id` (multi-moneda vive en la línea). **Los external IDs `acc_<company>_<code>`
    se emiten POR CÓDIGO LAUDUS: N alias xmlid → la MISMA cuenta colapsada** (ir.model.data permite N
    nombres al mismo res_id; así el formato congelado de E1.0 sobrevive al colapso).
  - [x] `build_partners(moves)` / `build_analytic(moves)`: poblaciones REALES del output (partners canónicos
    estampados por E1.4; valores de los 5 planes + plan `entidad` desde `line.entity`), xmlids nuevos
    `prt_<slug>` / `aa_<plan>_<slug>` (slug = `normalize()` + solo `[a-z0-9]`; colisión de slug entre dos
    canónicos distintos → fail-loud). Los 6 planes contenedores NO se crean (E1.1, se referencian por xmlid
    del módulo).
  - [x] `build_moves(moves)`: por move → vals de `account.move` (journal por compañía LAU1/LAU2, `date`,
    `ref` = narration, `x_laudus_je_id`) + líneas `(0,0,vals)`: CLP → `debit/credit` desde el monto FIRMADO
    (amount>0 → debit, amount<0 → credit); USD → `currency_id` USD + `amount_currency` = monto firmado USD +
    debit/credit al contravalor `amount × price`; los 3 campos `x_laudus_*`; `partner_id`/`analytic_distribution`
    por xmlid-ref desde la metadata E1.4 (dims presentes → `{analytic_account_id: 100.0}` cada una, NUNCA
    exigir que sumen 100% entre líneas — AC3 de E1.4). **Balance por move: Σ(debit−credit)==0 en CLP o
    fail-loud ANTES de tocar Odoo.**
  - [x] Tests Tier A (`test_load_payloads.py`): chart golden (aliases N→1, code representante, otype map),
    USD 100@800 → `amount_currency=100`/`debit=80000`, signos, balance, xmlids pinneados, partners/analytic
    desde metadata sintética estampada, **mutaciones** (otype corrupto acusa; USD sin price acusa; move
    desbalanceado acusa; colisión de slug acusa).
- [x] **Task 2 — Cliente XML-RPC + upsert idempotente (AC1, AC2)**
  - [x] `loader_rpc.py`: cliente stdlib (`xmlrpc.client`) con `execute_kw`; namespace fijo de xmlids
    (`ir.model.data.module = "__laudus__"`, constante). `upsert(model, xmlid, vals)`: si el xmlid existe →
    **skip** (el input es determinístico: mismo transformador → mismo payload); si no → `create` + registrar
    xmlid. Aliases del chart: N xmlids `acc_*` registrados al MISMO `res_id`.
  - [x] Orden de carga: cuentas → partners → analíticas → moves (batcheado, `create` en lotes) →
    `action_post` SOLO de los moves recién creados (los existentes ya están posteados; re-postear revienta).
  - [x] CLI: `--url` (default `http://localhost:8070`), `--db`, `--login/--password` (default admin/admin
    del compose dev), `--ledger` (default golden para dry-runs; el full usa `ledger/main.beancount`).
    Corre la cadena completa (collapse → sincerar → dimensionar) + builders + carga y reporta conteos.
- [x] **Task 3 — Tier B: idempotencia probada sobre el golden (AC1–AC4)**
  - [x] `test_loader_idempotente.py` (marker `odoo`, module-scoped como E1.1): compose `migration_e1` up,
    db fresca `test_e15` (dropdb + `-i x_laudus_migration --without-demo all` — patrón E1.1 verbatim),
    cadena sobre el golden + `load_all` vía XML-RPC al 8070.
  - [x] AC1: cuentas/moves/líneas existen con sus xmlids en `__laudus__`; moves `state='posted'`; ambas
    compañías (el golden trae EAG y RUT2); campos `x_laudus_*` poblados en línea y cabecera.
  - [x] AC2: correr `load_all` 2× → mismo N de moves/líneas/cuentas y mismos saldos por código (query SQL);
    caso recuperación: borrar la MITAD de los moves (button_draft + unlink vía RPC) → re-correr → converge
    al estado completo (N y saldos idénticos a la primera corrida).
  - [x] AC3 + paridad golden: `Σ(debit−credit) por (x_laudus_account_code, currency, company)` en Odoo ==
    saldo del mirror golden por código (0 diffs — el mismo agrupador de E1.6 en miniatura). Cubre
    explícitamente que la apertura no se duplica (el par wash está excluido por E1.3: la cuenta 211005
    NO debe recibir líneas; assert explícito).
  - [x] AC4: la línea USD carga `currency_id=USD`, `amount_currency=100.00`, `debit=80000` CLP; el asiento
    9000003 cuadra por moneda (Σ CLP = 0 dentro del move; `amount_currency` preservado).
  - [x] Partner + dims end-to-end: estampar metadata E1.4 sintética (via `dataclasses.replace`) en ≥2 líneas
    del golden antes de cargar (1 partner partición + 1 dim analítica) → en Odoo la línea queda con
    `partner_id` y `analytic_distribution` correctos (el golden NO trae columnas de dims pobladas — lección
    E1.4: no buscar cobertura golden que no existe; lo sintético prueba el write-path).
- [x] **Task 4 — Regresión + README + cierre (invariantes)**
  - [x] Suite completa `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q`: baseline
    **412 passed / 7 skipped** + los nuevos Tier A, 0 regresiones (los Tier B quedan skipped por defecto).
  - [x] `bean-check` del mirror verde (E1.5 solo LEE el ledger; borrar picklecache antes).
  - [x] deferred-work.md: marcar cerrados los 3 defers (`posting.price`, `otype` población, `otype`
    consistencia) con referencia a esta story; NO tocar los demás.
  - [x] README sección E1.5 (dos capas, cómo correr el Tier B, el CLI, y el aviso: full load real = post-E1.6,
    gate D-1 + VPS).

### Review Findings

Code review adversarial 2026-07-25 (Blind Hunter + Edge Case Hunter + Acceptance Auditor; 33 hallazgos brutos → dedup + triage). El Acceptance Auditor no encontró violaciones de AC1–AC4 sobre el GOLDEN; el crítico P1 vive fuera de la cobertura del golden.

- [x] [Review][Patch] **P1 CRÍTICO — El ruteo de cuenta ignora el destino sincerado de E1.3** [pipeline/odoo_migration/load.py:293] — `build_moves` rutea SOLO por `laudus_code` (alias `acc_*` → cuenta del colapso) y descarta `line.odoo_account`, que E1.3 reescribe. Medido sobre el mirror real: **182 líneas** (naturaleza B: 125, H: 57 — retiros a activos de origen, Jhonny, mixtos) quedarían posteadas en la cuenta PRE-sinceramiento, y **21 destinos sincerados** (JuliusBaer, MBI, InvTecnion, Pleyades, PrestamoJhonnyGuerra, …) ni existen en el chart de `build_chart` (que lee solo la tabla). Ni el golden (0 líneas B/H) ni la paridad AC3/E1.6 (agrupa por `x_laudus_account_code`, que sigue correcto) pueden detectarlo. Contradice el contrato de la story ("las patas sinceradas ya llevan su cuenta destino final"). Fix: resolver `account_xmlid` por `(company, line.odoo_account)` contra el chart indexado por destino + extender el chart con las cuentas de origen sincerado (helper xmlid nuevo aditivo, código sintético → aviso a Valentina) + assert de paridad por cuenta Odoo real en Tier B.
- [x] [Review][Patch] **P2 — Ventana create→register duplica partners/analíticas y TRABA cuentas en re-corrida** [pipeline/odoo_migration/loader_rpc.py:192-241] — crash entre el `create` y el `_register` (2 roundtrips por registro): partners/analíticas se duplican en silencio al re-correr (sin unique constraint); una cuenta re-creada choca el unique(code) de Odoo → la re-corrida NUNCA converge (contradice AC2). El defer documentado solo cubre la ventana del lote de moves. Fix: si el xmlid no está, buscar por clave natural (code+company / name / name+plan) antes de crear; actualizar el defer note.
- [x] [Review][Patch] **P3 — Moves creados+registrados pero nunca posteados quedan draft PARA SIEMPRE** [pipeline/odoo_migration/loader_rpc.py:290-309] — crash (o el RuntimeError de conteo de líneas, que dispara DESPUÉS de registrar `mv_*`) entre `_register` y `action_post`: la re-corrida los cuenta como `moves_skipped` y no los postea nunca; drafts silenciosos que los reportes excluyen. Fix: en cada corrida, buscar moves del namespace con `state != 'posted'` y postearlos (converge) o acusarlos fail-loud.
- [x] [Review][Patch] **P4 — Apareo `aml_*`↔líneas por orden de id sin verificación de contenido** [pipeline/odoo_migration/loader_rpc.py:288-305] — solo se chequea el CONTEO; si Odoo alguna vez reordena las `(0,0,…)`, cada `aml_*` (formato CONGELADO, trazabilidad E1.6) queda registrado contra la línea equivocada en silencio. Fix: antes de registrar, verificar `(x_laudus_account_code, debit, credit)` de cada línea contra el payload, fail-loud.
- [x] [Review][Patch] **P5 — Contravalor `amount × price` sin quantize a precisión CLP** [pipeline/odoo_migration/load.py:253-263,305] — un precio real no-redondo (p.ej. `761.90 USD @ 835.47`) da un Decimal con >0 decimales: (a) el balance check exacto revienta con LoadError espurio aunque Beancount balancee por tolerancia; (b) si suma 0 sin quantize, Odoo redondea cada línea por separado y el move puede llegar desbalanceado a `action_post` (tumba el lote entero). Hoy inalcanzable (mirror 100% CLP, golden usa 100@800 exacto) pero ES la feature de AC4. Fix: `quantize(Decimal("1"))` en `_contravalor` antes del check y del payload; corregir el comment falso de `_f` ("2 decimales exactos en float64").
- [x] [Review][Patch] **P6 — `_journals` solo guarda el caso ambos-faltantes** [pipeline/odoo_migration/loader_rpc.py:115-125] — LAU1 presente + LAU2 faltante (db a medio instalar) → `KeyError` pelado en el loop de lotes, DESPUÉS de haber escrito chart/partners/analíticas. Fix: assert por cada `(company, JOURNAL_CODE[company])` necesaria, con el patrón de mensaje de `_companies`.
- [x] [Review][Patch] **P7 — Código representante = `min` lexicográfico; la spec dice "numérico"** [pipeline/odoo_migration/load.py:139] — códigos reales con largos {2,4,6} + `GVAR`: hoy ningún grupo colapsado mezcla largos (verificado por el Auditor), pero nada lo garantiza y el pin del test usa el MISMO orden string (tautológico). Fix: key `(len, str)` (numérico-aware, determinístico con GVAR) + pin independiente en el test.
- [x] [Review][Patch] **P8 — Lógica de payload en la capa RPC: `"name": l.name or m.ref`** [pipeline/odoo_migration/loader_rpc.py:256] — transformación de datos en Tier B, sin cobertura Tier A; `LinePayload.name` deja de ser lo que aterriza en Odoo. Fix: mover el fallback a `build_moves`.
- [x] [Review][Patch] **P9 — `_ensure_analytic_group` y `_currency_id` mutan estado en silencio** [pipeline/odoo_migration/loader_rpc.py:146-175] — grant de grupo al usuario RPC en CADA corrida y activación de moneda inactiva vía `write`, sin log ni señal (doctrina fail-loud/no-arreglar). Son prerequisitos legítimos del propio loader: hacerlos condicionales (solo si falta), visibles (reportar en counts/stdout) y documentados en README.
- [x] [Review][Patch] **P10 — `build_moves` no valida unicidad del xmlid de move** [pipeline/odoo_migration/load.py:266] — dos moves con el mismo `(company, je_id)` pasan el filtro `pending` juntos: doble create y choque en `ir.model.data` DESPUÉS de escribir. Guard barato en el builder (capa designada de validación).
- [x] [Review][Patch] **P11 — `--url` con slash final → `ProtocolError` 404 confuso** [pipeline/odoo_migration/loader_rpc.py:63] — `http://host:8070/` arma `…//xmlrpc/2/common`. Fix: `url.rstrip("/")` en `OdooClient.__init__`.
- [x] [Review][Patch] **P12 — Higiene de tests (3 ítems)** [pipeline/odoo_migration/tests/] — regex de mutación debilitada (`match="NO\s+balancea|NO "` matchea cualquier "NO "); copy-dict identidad con comentario que describe un filtro inexistente (AC3 Tier B); comentario "(569+2 alias)" stale (son 568, la propia story lo dice bien). Arreglos triviales.
- [x] [Review][Defer] **Credenciales/TLS del CLI para la corrida VPS** [pipeline/odoo_migration/loader_rpc.py:346-348] — password default en argv (visible en process list/history), http plano sin historia TLS; hoy solo apunta al compose dev. Diferido al runbook del full load (post-E1.6, junto con el VPS): env-var para el password + https.
- [x] [Review][Defer] **Escala: `_xmlid_map` sin paginar + 1 `search` por move** [pipeline/odoo_migration/loader_rpc.py:81-88,293] — sobre el mirror real serían cientos de miles de `aml_*` en UNA respuesta XML-RPC + N roundtrips; el batcheo solo cubre `create`. Diferido al gate winston §9 (medir 1 año ANTES del full) — ahí se pagina/optimiza con datos.
- [x] [Review][Defer] **`compose exec odoo odoo -i` contra el server vivo** [pipeline/odoo_migration/tests/test_loader_idempotente.py:157-166] — segundo proceso odoo sobre la misma db = ventana de flake; patrón E1.1 verbatim, pre-existente. Endurecer junto con los smokes (defer E1.0/E1.1 ya registrado).

Descartados como ruido/inalcanzables: 5 (colisión de alias por código duplicado en tabla — el mapping loader ya falla fuerte; `KeyError` de xmlids de línea — inalcanzable hoy y subsumido en P1; `entity` vacío — transform falla fuerte upstream; mod de `mapping.py` "no declarada" — está en File List; `down -v` compartido entre módulos Tier B — corren secuenciales y cada uno resetea su db).

**Fixes aplicados (2026-07-25, mismo review):** los 12 patches arriba quedaron implementados y verificados.
- **P1:** `build_origin_accounts` (21 cuentas de origen E1.3 en el mirror, xmlid aditivo `accs_<company>_<slug>`, tipo por población cerrada `Assets:` → `asset_current`, grupo `ORIGEN-SINCERADO`, code = slug del path) + `build_moves(moves, chart)` rutea CADA línea por `(company, line.odoo_account)`. Verificado sobre el mirror completo: 16.623 payloads, 182 líneas a `accs_*`, unicidad `(company, code)` del chart combinado OK. Sorpresa del fix: **el golden SÍ trae 5 patas naturaleza-B reales** (retiros Tecnión del JE 1237 → `Assets:*:InvTecnion`) — el Dev Notes decía que no; el Tier B nuevo `test_ac1_ruteo_por_destino_sincerado` verifica ese ruteo REAL contra Odoo (las 5 patas aterrizan en `accs_*`, con tipo y grupo correctos vía `code_store` de Odoo 18). La numeración definitiva de las cuentas de origen queda como pregunta guardada 5 a Valentina.
- **P2/P3:** adopción por clave natural en los 4 payloads + barrido final que postea drafts (`moves_adopted`/`moves_reposted` en counts) — cierra también el defer "ventana create→registro" que la implementación había documentado (marcado CERRADO en deferred-work.md).
- **P4:** `_register_lines` verifica `(x_laudus_account_code, debit, credit)` payload↔línea antes de registrar `aml_*`.
- **P5:** `_contravalor` cuantiza a precisión CLP (half-up, lo mismo que Odoo); test `test_contravalor_usd_quantize_half_up`; comment de `_f` corregido.
- **P6–P12:** guard por-compañía en `_journals`; representante numérico `(len, código)` + pin independiente; fallback `desc→ref` movido al builder; `_ensure_analytic_group`/`_currency_id` condicionales y contados; guard de je_id duplicado; `rstrip("/")` en la URL; higiene de tests (regex, comment AC3, "(569→568+1)").
- Verificación post-fix: paquete migración 182 passed; **Tier B `-m odoo` contra Odoo real: 7/7 verde en 68s** (AC1–AC4 + ruteo sincerado real); suite completa verde (conteo final en Change Log); bean-check verde.

## Dev Notes

### Decisiones ya tomadas — NO re-litigar

- **Loader programático vía RPC, NO import CSV por UI** (winston §2.3 — frágil a escala). El spike
  (`_spike-odoo/import_to_odoo.py`) probó el camino con `odoo shell`; E1.5 lo endurece con XML-RPC desde el
  host (loader vive en el repo, testeable, sin inyectar código al contenedor). stdlib `xmlrpc.client` —
  **cero dependencias nuevas** (gate del workflow).
- **External IDs congelados** (E1.0): `acc_<company>_<code>` / `mv_<company>_<je_id>` /
  `aml_<company>_<je_id>_<n>` — componentes `[a-z0-9]`, company en minúsculas. NO cambiar formato; los
  helpers nuevos (partner/analytic) son ADICIONES con la misma disciplina fail-loud.
- **Odoo queda tonto**: cero lógica de negocio en Odoo; el loader NO clasifica ni corrige, solo escribe lo
  que la cadena emite (winston §2). Si algo falta/no cuadra → fail-loud ANTES de escribir, nunca "arreglar"
  en el loader.
- **Paridad por moneda, USD nominal** (winston §6): las líneas USD llevan `currency_id` + `amount_currency`
  (USD firmado) y debit/credit en CLP al precio registrado. IAS 21/revalúo = Fase 3, acá NADA de revalúo.
- **Convención de signo** (winston §6): monto firmado Beancount == `debit − credit` Odoo. Positivo → debit;
  negativo → credit. Es lo que hace que `Σ(debit−credit)` por código reproduzca `Σ(units.number)` exacto.
- **2 compañías, diarios LAU1/LAU2, sin `l10n_cl`** — YA existen (hook E1.1, idempotente). El loader los
  BUSCA (journal por code+company), no los crea. Los 6 planes analíticos contenedores idem (xmlids del
  módulo `x_laudus_migration`).
- **Tier A por-commit / Tier B opt-in `-m odoo`** — el conftest ya salta Tier B por defecto. El gate real
  por-commit es la suite completa del proyecto (comando de project-context.md, NO inventar otro).

### Data real verificada (2026-07-25, contra código y CSV — leer antes de codear)

1. **`otype` real del CSV (569 filas):** expense 358, income 80, asset 65, receivable 33, bank 20,
   liability 11, equity 2. Población cerrada de 7 — el mapeo a `account_type` de Odoo 18 va como tabla
   fija en `load.py` con fail-loud ante valor nuevo.
2. **Destinos colapsados:** 361 `(company, odoo_account)` distintos (≈336 del plan + activos de origen
   nuevos). El `odoo` de la tabla es un PATH (`Assets:FFCC:InversionesSade`, `Bancos:Banco BCI - 10160175`)
   → va a `name`; el `code` de la cuenta Odoo no existe en la tabla → **representante = menor código
   Laudus origen** (determinístico; la mayoría de las cuentas son 1:1 y conservan su código, coherente con
   spec §1.1 "no se renumera").
3. **El golden slice ya cubre AC1/AC3/AC4:** EAG + RUT2 (ambas compañías), el par wash 9000001/9000002
   (excluido por E1.3 → 211005 sin líneas = la prueba de no-doble-apertura en miniatura) y el asiento USD
   sintético 9000003 (`100.00 USD @ 800.00 CLP` contra −80.000 CLP). El mirror real NO tiene postings USD
   — el sintético es LA cobertura de AC4 (por diseño del fixture, E1.0).
4. **El golden NO trae partners/dims estampables** (E1.4 lo verificó: sin 115xxx, sin columnas pobladas).
   El write-path de `partner_id`/`analytic_distribution` se prueba con metadata sintética estampada por
   `dataclasses.replace` — NO inventar fixtures nuevos ni buscar cobertura que no existe.
5. **`price` en el mirror:** solo el asiento sintético USD tiene `@ 800.00 CLP`. `posting.price` es
   `Amount(number, currency)`; guardar `price = posting.price.number` cuando existe. TODA la historia real
   es CLP (contravalor == amount, price None).
6. **Posted moves no se editan:** `action_post` es terminal para el flujo del loader. El upsert es
   skip-si-existe (el input es determinístico); "borrar mitad" en el test AC2 requiere `button_draft` +
   `unlink` vía RPC antes de re-correr. Si un move existente difiere del payload (no debería: mismo
   transformador), NO pisarlo en silencio — está fuera del contrato, documentarlo en README.
7. **Odoo 18 (imagen `odoo:18`, compose E1.1):** `account.account` usa `company_ids` m2m (patrón spike:
   `[(6,0,[cid])]` + `with_company`); `account.move` type `entry` + `journal_id` + `line_ids=[(0,0,…)]`;
   `analytic_distribution` = dict `{str(analytic_account_id): porcentaje}` — cada dim presente va con
   `100.0` (dispersas independientes, pueden convivir N planes en una línea).
8. **La db del Tier B se instala con `--without-demo all`** y el hook deja `admin` viendo ambas compañías.
   XML-RPC: `common.authenticate(db, 'admin', 'admin', {})` + `object.execute_kw`. El loader escribe en la
   compañía del move vía `context={'allowed_company_ids': [cid]}` o campo `company_id` explícito en vals
   (decisión dev; el spike usó `with_company`, en RPC es el context).

### Cómo encaja con E1.0–E1.4 (el contrato)

- **Input del loader = output de la cadena completa:** `collapse(cut, table) → sincerar(moves, table,
  alias_table=aliases) → dimensionar(result.moves, table, alias_table=aliases)` → `DimensionadoResult.moves`.
  Los moves excluidos (washes) YA no están; las patas sinceradas ya llevan su cuenta destino final; la
  metadata E1.4 (`partner`, `dim_*`) viaja en cada línea con defaults vacíos.
- `OdooLineRecord.laudus_code/entity` → `x_laudus_account_code`/`x_laudus_entity`; `OdooMoveRecord.je_id` →
  `x_laudus_je_id` (línea Y cabecera). `n` de la línea es el índice del xmlid `aml_*`.
- El plan `entidad` (6º plan analítico) se puebla desde `line.entity` — E1.4 lo dejó explícitamente para
  E1.5 ("Entidad = line.entity, ya viaja; E1.5 la convierte en analítica").
- **Learnings de reviews previos (aplicar de entrada):** (a) fail-loud con contexto, nunca degradar en
  silencio (patrón external_ids/mapping); (b) poblaciones cerradas validadas (otype, slugs, partners) —
  un valor nuevo revienta, no adivina; (c) tests de mutación obligatorios: un gate que no puede fallar es
  `tsc --noEmit`; (d) pins con literales derivados una vez (xmlids esperados del golden pinneados a mano,
  no re-derivados llamando al mismo helper); (e) del review E1.1: no depender de internos privados de Odoo
  — el loader usa solo modelos/métodos públicos (`create`, `write`, `action_post`, `ir.model.data`).
- **Defers que esta story CIERRA:** posting.price (E1.2), otype población cerrada (E1.2/E1.4), otype
  consistencia por destino (E1.2). **Defers que NO toca:** ParityError diffs programáticos (E1.6),
  neteo por-par (parity, sin caller nuevo), D-1 Latam (Valentina), duplicados YAML (tocar
  `load_alias_table` no está en scope), fixture session-scoped (higiene tests E1.3/E1.4).

### Tier B — infra de test (patrón E1.1 verbatim)

- Compose propio: `pipeline/odoo_migration/docker-compose.yml`, project `migration_e1`, puerto **8070**,
  monta `./addons` + `odoo.conf`. Helpers `_compose`/`_psql`/`_wait_for_db` de
  `test_x_laudus_migration_install.py` — extraerlos a un helper compartido o duplicarlos con nota
  (decisión dev; NO reescribirlos distinto).
- Db fresca SIEMPRE (dropdb + install): un run matado sin `down -v` deja la db vieja y el test validaría
  estado de código viejo (falso verde — comentario del fixture E1.1).
- El skip-si-no-hay-docker es el patrón vigente (deferred E1.0/E1.1: endurecer ambos smokes a la vez si
  se decide — NO lo hace esta story).
- Timeout: install ~40s + carga golden (~7 moves) — el módulo completo debe quedar bajo ~3 min como los
  smokes existentes.

### Project Structure Notes

- Código nuevo: `pipeline/odoo_migration/load.py` (builder puro) + `pipeline/odoo_migration/loader_rpc.py`
  (cliente + CLI). Hermanos de transform/sincerar/dimensionar/parity — mismo estilo docstring-contrato.
- Modificación quirúrgica: `transform.py` (campo `price`), `external_ids.py` (2 helpers nuevos AL FINAL,
  los congelados intactos).
- Tests nuevos: `tests/test_load_payloads.py` (Tier A) + `tests/test_loader_idempotente.py` (Tier B,
  marker `odoo`). El Tier A puede consumir el fixture golden existente (carga module-scoped propia, NO
  tocar `full_mirror_chain` — E1.5 no necesita el mirror completo).
- README del paquete: sección E1.5.

### Testing Requirements

- **Comando real (NO inventar otro):** `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q`
  (suite completa) / `… -m pytest pipeline/odoo_migration -q` (iterar Tier A) /
  `… -m pytest pipeline/odoo_migration/tests/test_loader_idempotente.py -m odoo -q` (Tier B, requiere
  Docker). [Source: project-context.md]
- Baseline actual: **412 passed / 7 skipped** (post-review E1.4, commit ccd367b). 0 regresiones.
- `bean-check` del mirror (picklecache borrado antes) — E1.5 solo LEE el ledger.
- Tier B es OPT-IN: la suite por-commit queda verde sin Docker (los nuevos `odoo` aparecen como skipped).

### References

- [Source: _bmad-output/planning-artifacts/odoo-migracion/epics.md#Story-E1.5] — ACs.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/winston-arquitectura-e1-odoo-2026-07-23.md#2.3, #6, #7] —
  mecanismo de carga elegido, convención de signo/multi-moneda, idempotencia por external ID.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/valentina-spec-estructura-odoo-2026-07-23.md#1] —
  plan Laudus puro, mapeo raíz→tipo, cuentas de origen nuevas.
- [Source: pipeline/odoo_migration/external_ids.py] — convención congelada + disciplina de componentes.
- [Source: pipeline/odoo_migration/{transform,sincerar,dimensionar,parity,mapping}.py] — la cadena (commit ccd367b).
- [Source: pipeline/odoo_migration/tests/test_x_laudus_migration_install.py] — patrón Tier B (compose/db fresca/SQL).
- [Source: _spike-odoo/import_to_odoo.py] — el camino probado (shell): companies/cuentas/moves/post.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — los 3 defers que E1.5 cierra + D-1.
- [Source: _bmad-output/implementation-artifacts/E1-4-transformador-dimensiones-partners.md] — metadata que
  el loader consume + learnings de review.

### Preguntas guardadas para Ary / Valentina (no bloquean el dev)

1. **D-1 Latinoamericana (gate humano ANTES del full load real):** el residual ±423,6M (grupo 4-vs-1) sigue
   en Income marcado `latam-sin-par`. El deferred dice "resolver antes de E1.5" = antes de la corrida
   productiva al VPS. ¿Veredicto de Valentina sobre excluir el grupo?
2. **Código de cuenta para destinos colapsados:** cuando N códigos Laudus colapsan a una cuenta Odoo, el
   `code` de la cuenta será el MENOR código origen (las 1:1 conservan el suyo). ¿OK, o Valentina prefiere
   otra numeración para el plan colapsado? (Cambio barato: es un campo del builder.)
3. **Cuentas `receivable` (33 filas):** se crean como `asset_receivable`. El golden no las ejercita; si el
   full load acusa alguna restricción de Odoo sobre líneas receivable sin partner, se ajusta en E1.6
   (partner placeholder o tipo `asset_current` para las no-socio). Aviso, no decisión.
4. **Decisión §5 del brief (Laudus-ongoing vs Odoo-nativo):** sigue abierta; E1.5 no la necesita (la carga
   es idéntica en ambas), pero el CLI queda listo para re-corridas si eligen A.
5. **Código de las 21 cuentas de ORIGEN SINCERADO (review P1):** los destinos que E1.3 crea al re-rutear
   (JuliusBaer, MBI, InvTecnion, Pleyades, …) no tienen código Laudus; hoy llevan `code` = slug del path
   (p.ej. `assetseagjuliusbaer`) y grupo `ORIGEN-SINCERADO`, determinístico y único. ¿Valentina prefiere
   asignarles numeración del plan (rango 12xxxx/13xxxx)? Cambio barato: es un campo del builder.
6. **Nombre VISIBLE de las cuentas (tour Ary 2026-07-25):** hoy `name` = la columna `odoo` de la tabla
   tal cual (path técnico: `Assets:Jael:InvTecnion`, `Bancos:Banco BCI - 10160175`) — Ary lo encontró
   difícil de leer en el plan de cuentas. Opciones: nombre corto + dueño ("InvTecnion — Jael") o path
   con separador legible ("Assets › Jael › InvTecnion"). No afecta paridad ni external IDs (cambio
   barato del builder); Ary prefirió el veredicto de Valentina antes de tocar SU tabla.

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) — create-story + dev-story workflow, 2026-07-25.

### Implementation Plan

- `load.py` (Tier A puro): `OTYPE_TO_ACCOUNT_TYPE` (7 valores, fail-loud), `build_chart` (agrupa mapping
  por `(company, odoo_account)`, code = min código origen, aliases `acc_*` por código), `_slug` +
  `build_partners`/`build_analytic` (poblaciones desde la metadata estampada, xmlids `prt_`/`aa_`),
  `build_moves` (vals + líneas con debit/credit/amount_currency/x_laudus_*/partner/dims, balance CLP
  fail-loud). Sin I/O, sin Odoo.
- `loader_rpc.py`: `OdooClient` (authenticate + execute_kw + xmlid resolve/register en `__laudus__`),
  `load_all(client, chart, partners, analytic, moves)` con skip-si-existe y `action_post` de los creados,
  CLI con la cadena completa.
- `transform.py`: `price` en el dataclass + `posting.price.number` en collapse (1 línea + campo).
- `external_ids.py`: `partner_xmlid(name)` / `analytic_xmlid(plan, name)` con slug fail-loud (no tocar
  los congelados).
- Tests: Tier A sobre golden + sintéticos con mutaciones; Tier B patrón E1.1 (helpers propios del módulo,
  db `test_e15`).

### Debug Log References

- RED→GREEN 1 (Tier A): el asiento USD del golden desbalancea en `build_moves` si el contravalor no usa
  `price` — confirmó el defer E1.2 (sin `price`, Σ CLP del move 9000003 = −80.000 ≠ 0). GREEN al poblar
  `price` en `collapse` y usar `amount × price` como contravalor.
- RED→GREEN 2 (Tier B, Fault 4 real): el admin de una db fresca NO tiene el grupo Technical/Analytic
  Accounting → crear `account.analytic.account` vía RPC revienta. Fix: `_ensure_analytic_group` en
  `load_all` — el loader asegura su propio prerequisito (idempotente, `(4, id)` no duplica).
- RED→GREEN 3 (Tier B): `button_draft` devuelve `None` y el endpoint XML-RPC de Odoo no marshalea `None`
  (allow_none server-side off). Fix en el TEST (el loader nunca draftea): borrar-mitad usa
  `write({'state': 'draft'})` — lo que `button_draft` hace por dentro — y después `unlink`. De paso quedó
  verificado que el `unlink` ORM limpia los `ir.model.data` (los xmlids no quedan huérfanos → converge).
- Tier B corrido 2026-07-25 (Docker 29.6.2, imagen `odoo:18`): **6/6 passed en 69s** (install módulo +
  3 corridas del loader + borrar-mitad). Db `test_e15` fresca (dropdb + install), stack `down -v` al final.

### Completion Notes List

- **AC1 cumplido (probado contra Odoo real):** `load_all` sobre el golden crea el chart COMPLETO de la
  tabla (**361 cuentas colapsadas**, con los 568 alias `acc_*` — uno por fila con código — apuntando N→1
  vía `ir.model.data`), 1 partner (sintético), 7 cuentas analíticas (6 entidad + Vía Gris sintética) y
  **5 moves posteados** (7 del slice − 2 washes excluidos por E1.3), EAG 4 / RUT2 1. Los 18 `aml_*`
  registrados y los 3 campos `x_laudus_*` poblados en TODAS las líneas (verificado por SQL).
- **AC2 cumplido (FR11):** 2ª corrida → **0 creates** (todo skip por xmlid), snapshot (N moves/líneas +
  saldos por código × moneda × compañía) IDÉNTICO. Recuperación: 3 de 5 moves borrados (intercalados
  EAG/RUT2, draft+unlink vía ORM) → re-corrida crea exactamente los 3 → snapshot == 1ª corrida.
- **AC3 cumplido:** 211005 (Apertura) SIN líneas en Odoo (el par wash quedó excluido en E1.3 — assert
  explícito) y paridad golden por código × moneda × compañía: **0 diffs** contra el mirror (mismo
  agrupador que usará E1.6, sumando `amount_currency`: CLP == debit−credit, USD == nominal).
- **AC4 cumplido:** línea USD con `currency_id=USD`, `amount_currency=100.00`, `debit=80000`; el move
  9000003 cuadra en CLP (Σ=0) y preserva el nominal USD.
- **3 defers cerrados** (posting.price, otype población cerrada, otype consistencia por destino) —
  marcados en deferred-work.md. Verificado contra el CSV real: 0 conflictos de otype por destino
  colapsado hoy (el guard queda para drift futuro).
- **2 defers nuevos documentados** (deferred-work.md): ventana de crash entre create del lote y registro
  de xmlids (la pesca E1.6 por `x_laudus_je_id`); upsert sin detección de drift (disciplina de re-corrida
  documentada en docstring + README: cambiar reglas ⇒ db nueva, el delta fino es Fase 2 / brief §5).
- **Población real del chart:** 361 destinos colapsados, 79 con >1 código origen (máx: Donaciones RUT2,
  15 códigos → `acc_rut2_415055`); code representante = menor código origen, unicidad `(company, code)`
  validada fail-loud en `build_chart`.
- Suite completa: **430 passed / 13 skipped** (baseline 412/7 + 18 Tier A nuevos; +6 Tier B nuevos que
  quedan skipped sin `-m odoo`), 0 regresiones. `bean-check` verde (picklecache borrado antes).
- **Pregunta guardada 1 (D-1) sigue abierta** — gate humano antes del full load real al VPS. Las
  preguntas 2 (code representante) y 3 (receivables sin partner) tampoco bloquean: son avisos a Valentina.

### File List

- `pipeline/odoo_migration/load.py` (nuevo — payload builder Tier A + validación otype)
- `pipeline/odoo_migration/loader_rpc.py` (nuevo — cliente XML-RPC + load_all + CLI)
- `pipeline/odoo_migration/transform.py` (mod — campo `price` en OdooLineRecord + collapse)
- `pipeline/odoo_migration/mapping.py` (mod — campos `cat2`/`cat3` en MappingRow → `x_laudus_group`)
- `pipeline/odoo_migration/external_ids.py` (mod — helpers `slug`/`partner_xmlid`/`analytic_xmlid`; congelados intactos)
- `pipeline/odoo_migration/README.md` (mod — sección E1.5)
- `pipeline/odoo_migration/tests/test_load_payloads.py` (nuevo — Tier A: payloads + mutaciones)
- `pipeline/odoo_migration/tests/test_loader_idempotente.py` (nuevo — Tier B `-m odoo`: AC1–AC4)
- `_bmad-output/implementation-artifacts/deferred-work.md` (mod — 3 defers cerrados + 2 nuevos)

## Change Log

- 2026-07-25 — Story E1.5 creada (create-story: contexto epics + winston §2.3/§6/§7 + spec §1 + defers
  E1.2/E1.4 + data real verificada del CSV/golden). Status: ready-for-dev.
- 2026-07-25 — E1.5 implementada completa (Tasks 1–4): payload builder Tier A (`load.py`, chart colapsado
  361 cuentas con alias N→1, otype población cerrada, USD con contravalor) + loader XML-RPC idempotente
  (`loader_rpc.py`, upsert por xmlid en `__laudus__`, batches + action_post) + **Tier B corrido contra
  Odoo real en Docker: 6/6 verde (AC1–AC4 probados: 2× idéntico, borrar-mitad converge, apertura sin
  doble-conteo, paridad golden 0 diffs, USD amount_currency)**. 18 tests Tier A nuevos. Suite 430/13,
  0 regresiones; bean-check verde. 3 defers cerrados + 2 nuevos documentados. Status → review.
- 2026-07-25 — **Code review adversarial + 12 patches aplicados** (ver Review Findings). Crítico P1:
  el loader ruteaba por `laudus_code` ignorando el destino sincerado de E1.3 (182 líneas del mirror a
  cuenta equivocada, 21 cuentas de origen inexistentes) — arreglado con ruteo por destino +
  `build_origin_accounts` + cobertura Tier A/B nueva. Idempotencia endurecida (adopción por clave
  natural + re-post de drafts: cierra el defer "ventana create→registro"). Verificación final:
  suite completa **439 passed / 14 skipped** (+9 Tier A nuevos), bean-check verde, **Tier B re-corrido
  contra Odoo real: 7/7 en 68s** — incluye el ruteo sincerado REAL del golden (5 patas B del JE 1237 →
  `accs_*`; el golden sí traía naturaleza B, corrigiendo el Dev Notes) y el `code_store` company-dependent
  de Odoo 18. 3 defers nuevos del review en deferred-work.md; pregunta guardada 5 (numeración cuentas
  de origen) para Valentina. Status → done.
