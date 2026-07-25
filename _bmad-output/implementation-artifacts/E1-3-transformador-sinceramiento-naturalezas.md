# Story E1.3: Transformador de sinceramiento (naturalezas 0/A–H) + gate de destino

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **contadora**,
I want **la regla determinística que reclasifica cada pata de ingreso según su naturaleza (tabla-madre 0/A–H) y verifica que aterrizó en el destino correcto**,
so that **el P&L queda sincerado (los ~46B salen del ingreso) y sé que cada peso fue al lugar que corresponde, no solo que no se perdió**.

## Contexto (qué construye E1.3 y qué NO)

Cuarta story de Epic E1 — **el transformador de mayor riesgo contable del epic** (epics.md, nota de estructura (d): doble cobertura + ACs de destino). E1.2 dejó el colapso (`collapse()` → `OdooMoveRecord`/`OdooLineRecord` con código origen estampado) y el verificador reusable (`run_tier_a`). **E1.3 agrega el segundo transformador de la cadena: el sinceramiento por naturaleza** — Python puro, Tier A, SIN Odoo:

1. **Clasificador de naturaleza** — cada pata de ingreso matchea **exactamente una** naturaleza de la tabla-madre 0/A–H (inventario de Valentina, población CERRADA) por (código, glosa).
2. **Ruteo por naturaleza a nivel PATA** — B retiros → activo de ORIGEN provisional (FR4a); H-Jhonny → por-cobrar; G MIXTO → regla por-glosa con alias + normalización; A/F quedan; ambiguo/sin-match → queda en Income marcado (nunca descarte silencioso).
3. **Exclusión de washes (naturaleza 0)** — pares iguales-y-opuestos por criterio SEMÁNTICO, con log auditable **por identidad** (cierra el defer de E1.2: exclusiones por `je_id`, no por conteo).
4. **Gate de destino FR12c** — el ingreso bajó EXACTAMENTE la cifra que produce el inventario (no el redondeo "~46B"), los activos de origen subieron ese monto por vehículo, Molco recibió su gasto.

**Punto de partida clave (verificado contra la tabla versionada y el código de E1.2):** el colapso YA rutea a nivel CUENTA las naturalezas C y E — la columna `odoo` de la tabla manda Sade 310011 FFCC → `Assets:FFCC:InversionesSade` y Molco 310005 FFCC / 710005 JAB → `Expenses:MolcoFinanciamiento`. **E1.3 NO re-rutea C/E** (ya están; solo las verifica en el gate y les estampa naturaleza). Lo que E1.3 sí re-rutea es lo que exige decisión a nivel pata: B (los retiros siguen mapeados a `Income:Retiros *` en la tabla), H, y G por glosa.

> **Arquitectura aprobada** (resumen ejecutivo §0 re-aprobado por Ary 2026-07-24). Detalle técnico auto-aprobado según `project-context.md`. **Precondición de datos CERRADA:** inventario de naturalezas (`valentina-inventario-naturalezas-2026-07-23.md`).

## Acceptance Criteria

Copiadas del epic (`epics.md` → Story E1.3), formato Given/When/Then:

**AC1 — Cada pata de ingreso matchea exactamente UNA naturaleza y se rutea**
**Given** la tabla-madre de naturalezas (0/A–H, cerrada en el inventario),
**When** corre el sinceramiento,
**Then** cada pata de ingreso matchea **exactamente una** naturaleza por (código, glosa) y se rutea a su destino (queda-ingreso / activo-origen / activo-aporte Sade / disposición / gasto-Molco / contra-gasto / mixto-por-glosa / H devolución-préstamo).

**AC2 — Washes excluidos por criterio semántico + log auditable por identidad**
**Given** los washes de apertura/cierre,
**When** se excluyen,
**Then** se identifican por criterio **semántico** (cuenta+fecha de corte, no solo monto-opuesto), con **log auditable** de cada par excluido y conteo esperado; si excluye más de lo esperado → falla con alarma. (Caso de test: Latinoamericana ±423,6M que netea a 0.)

**AC3 — Gate de destino FR12c: cifras EXACTAS del inventario**
**Given** el gate de destino (FR12c),
**When** termina el sinceramiento,
**Then** el ingreso total bajó **exactamente la cifra esperada del inventario de naturalezas** (el monto exacto, NO el redondeo "~46B" — el test assertea el número que produce el inventario, no una aproximación), los activos de origen subieron **exactamente ese monto por vehículo**, y Molco recibió su financiamiento como gasto — cada aserción contra la expectativa del inventario.

**AC4 — Paridad-origen invariante: 0 diffs tras el sinceramiento**
**Given** la paridad-origen,
**When** corre el verificador Tier A tras el sinceramiento,
**Then** sigue en **0 diffs** (invariante: el código origen se preserva aunque cambie la cuenta destino).

**AC5 — Sin-match y ambiguos quedan marcados, nunca descartados**
**Given** una pata sin match, o el +32M "dividendo" dudoso de Nuevo Ciclo,
**When** no matchea con confianza,
**Then** queda en Income + marcada "sin clasificar" / "revisar con contadoras" (nunca descartada) y aparece en el reporte de cobertura.

## Alcance — qué SÍ y qué NO hace E1.3

**SÍ (deliverables):**
- `pipeline/odoo_migration/sincerar.py` — clasificador de naturaleza + ruteo a nivel pata + exclusión de washes + reporte de cobertura. Función pura: `sincerar(moves, mapping) -> SinceramientoResult` (moves sincerados + exclusiones por identidad + líneas marcadas + reporte).
- Upgrade de `parity.py`: **exclusiones por IDENTIDAD** (`excluded_je_ids: set` en `verify_counts`/`run_tier_a` — verifica que esos y SOLO esos faltan, y que cada par excluido netea a 0 por código; cierra el defer de E1.2).
- Carga de la tabla de alias (`valentina-tabla-alias-2026-07-23.yaml`) + normalización de glosa (minúsculas, sin tildes, espacios colapsados) para la regla G.
- Gate FR12c Tier A: sobre el golden slice (al peso) + **test full-mirror** con las cifras exactas del inventario pinneadas.
- Tests de mutación (el gate DEBE poder fallar) + tests por naturaleza sobre los casos canónicos del fixture.
- README del paquete: sección E1.3 (posición en la cadena collapse→sincerar, contrato de regresión actualizado).

**NO (es de otra story / decisión):**
- Dimensiones analíticas / partners / tag `beneficiario:Raquel` / socio-uso → **E1.4**. La tabla de alias se carga acá SOLO para la regla G (naturaleza por glosa); el tagging de personas es E1.4.
- Carga hacia Odoo / creación real de cuentas → **E1.5** (nota: E1.5 deberá crear TAMBIÉN los activos de origen que E1.3 introduce — el plan operativo ya no es solo la tabla).
- Verificación lado-Odoo + muestreo dirigido → **E1.6**. El reporte de cobertura completo con histograma MIXTO por corrida es de E1.6 (winston §6·B.4); E1.3 emite la versión transformador (sin-match + conteos por naturaleza).
- Valuación de orígenes / IAS 21 / patrimonio (yate/avión/casas) → Fase 3 / **E1B**. Los saldos de origen quedan negativos/provisionales — **esperado y correcto** (SPEC §3.3).
- Molco como 3ª entidad, re-ruteo fino de D (ver P-2 abajo), refinamiento F (netear contra gasto) → después.

## Tasks / Subtasks

- [x] **Task 1 — Clasificador de naturaleza (AC1)**
  - [x] `sincerar.py`: tabla `NATURALEZA` versionada en código, keyed **`(entity, code)`** (misma key de E1.2 — los códigos se repiten entre entidades), construida desde la tabla-madre 0/A–H del inventario. Naturalezas: `WASH(0)`, `REAL(A)`, `RETIRO(B)`, `APORTE(C)`, `DISPOSICION(D)`, `GASTO_MOLCO(E)`, `REEMBOLSO(F)`, `MIXTO(G)`, `PRESTAMO(H)`.
  - [x] **Cross-check contra la columna `sinc` del CSV** (fail-loud, patrón E1.2 de la columna `company`): las 83 filas de la tabla con `sinc` no-vacío deben ser consistentes con `NATURALEZA`; divergencia → `ValueError` con contexto. Los mapeos: `RETIRO→activo origen`→B, `REAL(se queda)`/`REAL(allowlist-dividendo)`→A, `REEMBOLSO(se queda)`→F, `DISPOSICIÓN→baja activo`→D, `MIXTO→regla por-glosa`→G, `→GASTO(Molco financiamiento)`→E, `APORTE→Assets:InversionesSade`→C, `REAL?(revisar)`→ver Dev Notes (Latinoamericana→H; resto→A con flag `revisar`).
  - [x] Toda pata cuyo `odoo_account` de colapso empieza con `Income:` DEBE resolver a exactamente una naturaleza; cuenta de ingreso sin naturaleza → fail-loud (población cerrada; un código de ingreso nuevo no pasa en silencio).
- [x] **Task 2 — Washes por identidad (AC2) + upgrade del verificador**
  - [x] Detección **semántica** de pares: (0a) glosa normalizada contiene "comprobante de apertura"/"comprobante de cierre" y existe el par igual-y-opuesto en el mismo ejercicio; (0b) Latinoamericana (`(EAG,310010)`/`(FFCC,310009)`, H-excluir): pares reverso iguales-y-opuestos. Exclusión SIEMPRE de **pares completos de moves** (nunca una pata suelta — el par netea a 0 por TODOS sus códigos; una pata sola descuadra, testeado en E1.2).
  - [x] Log auditable: lista de pares excluidos con `je_id`s, fechas, montos por código; el resultado expone `excluded_je_ids: set`.
  - [x] `parity.py`: `verify_counts`/`run_tier_a` aceptan `excluded_je_ids: set[tuple[company, je_id]]` en lugar de conteos ciegos — verifican que (a) exactamente esos moves faltan del output, (b) ninguno más, (c) cada par excluido netea a 0 por `(company, code, currency)`. Excluir de más / de menos / no-declarado → `ParityError` con detalle ("falla con alarma", AC2). Actualizar los 2 tests de exclusión de E1.2 a la API nueva (romperlos es esperado; NO mantener la API por-conteo).
- [x] **Task 3 — Ruteo por naturaleza a nivel pata (AC1)**
  - [x] **B (retiro → activo de origen):** dict versionado `(entity, code) → cuenta activo origen` según SPEC §1.2/§2.2 (`Assets:EAG:InvTecnion`, `Assets:<hija>:InvTecnion`, `Assets:EAG:InmobiliariaEspana`, `Assets:EAG:InvNuevoCiclo`, `Assets:EAG:MBI`, `Assets:EAG:JuliusBaer`, …). **Test de completitud: toda fila con naturaleza B tiene destino de origen** (incluye las que el SPEC §2.2 no listó explícitamente: Cepech 310017, Resultado MBI 510011, FFCC Bank JB 310003 / MBI 310007, hijas Pléyades/JB/MBI — derivar el nombre con el mismo patrón y anotarlo). La línea re-ruteada conserva código origen/entidad/monto; solo cambia `odoo_account`.
  - [x] **H-Jhonny:** `(EAG,310045)` y `(EAG,310047)` → `Assets:EAG:PrestamoJhonnyGuerra` (mismo destino la cuenta madre y la hijo, inventario N-3).
  - [x] **C y E:** NO re-rutear (ya vienen del colapso). Solo estampar naturaleza + verificar en el gate que el destino es el esperado.
  - [x] **D (disposición):** en E1.3 queda en su cuenta Income de colapso + naturaleza D estampada + flag `revisar` — **NO se re-rutea** (P-2 abierta y el activo a dar de baja no existe en el libro — es patrimonio E1B). Asunción documentada; ver Dev Notes.
  - [x] **A/F:** quedan (allowlist por código; A-con-flag para los `REAL?(revisar)`).
  - [x] **Ambiguo (N-2, AC5):** pata en cuenta B con glosa de ingreso real ("dividendo"/"interés") → conflicto cuenta-vs-glosa → queda en Income + `revisar con contadoras` (fixture id 4158). **Pin del epic sobre el default del inventario** — ver Dev Notes.
  - [x] **Metadata de auditoría en cada línea tocada** (NFR1, SPEC §3.3): naturaleza, regla que decidió (código/glosa), destino original de colapso — reversible y listable ("qué se movió y por qué").
- [x] **Task 4 — G MIXTO: regla por-glosa + alias + normalización (AC1, AC5)**
  - [x] Normalización previa a todo match de glosa: minúsculas + sin tildes + espacios colapsados (winston §6·B.3). Cargar `valentina-tabla-alias-2026-07-23.yaml` respetando `excluir_homonimos` y word-boundary para tokens cortos (jb/mbi/fip — las notas del YAML lo exigen).
  - [x] Cascada §3.2 sobre la glosa de cada pata G (cuentas `sinc=MIXTO`: 310099 EAG/FFCC, 710099 JAB, `*70099` hijas — N-4): dividendo/interés/directorio/arriendo/sueldo → queda; reembolso/devol → queda (F); rescate/retiro/traspaso/"a cta" → activo de origen SI el vehículo resuelve por alias (p.ej. "Nuevo Ciclo: Devolución de préstamos" → `Assets:EAG:InvNuevoCiclo`); aporte + signo + → activo; venta → D (marcar, no re-rutear); "por cuenta de" → contra-gasto/por-cobrar según inventario §1.2.
  - [x] **Match conservador:** solo lo inequívoco se re-rutea; traspaso sin vehículo resoluble, o cualquier duda → **queda en Income + `sin clasificar`** (blast radius acotado: G total ≈ −1,8B; winston §6·B.1). NUNCA fuzzy como decisor.
  - [x] Reporte de cobertura del transformador (FR10 versión E1.3): líneas sin-match con glosa + cuenta + monto, y conteos por naturaleza. Salida estructurada (el dev decide el formato; debe ser asserteable en test y legible por Valentina).
- [x] **Task 5 — Gate de destino FR12c + regresión (AC3, AC4)**
  - [x] `run_tier_a` verde sobre el golden slice tras `collapse → sincerar`: 0 diffs de origen (AC4 — invariante), destino y conteos con `excluded_je_ids` declarados. **Ojo `verify_destination`:** su lado esperado rutea el mirror por la tabla; post-sinceramiento el ruteo esperado = tabla + reglas E1.3 → el ruteo debe vivir en UNA función compartida (transformador y verificador la comparten, mismo patrón del filtro de universo de E1.2; el cross-check independiente son las cifras pinneadas del inventario).
  - [x] Test golden slice al peso: retiro 1237 → las 5 patas income aterrizan en `Assets:<entidad>:InvTecnion` conservando código origen (310013 = −1.022.700.000 ahora bajo activo); Sade 3994 sigue en `Assets:FFCC:InversionesSade`; par wash 9000001/9000002 excluido por identidad; traspaso id 29 (G "Traspaso de Andres Turski G.") → según regla (sin vehículo → sin-clasificar); id 4158 → Income + revisar.
  - [x] **Test full-mirror Tier A (AC3):** cargar `ledger/main.beancount` (module-scoped, 1 sola carga), correr collapse+sincerar y assertear las cifras EXACTAS del inventario: Sade en activo == **+4.876.249.792** exacto; Molco FFCC en gasto == **+2.895.757.384** exacto; ingreso total baja exactamente Σ(patas re-ruteadas) y ese Σ se pinnea al peso por vehículo (derivar una vez con bean-query al implementar, pinnear el número real, documentar en Completion Notes — patrón snapshot de E1.2). Latinoamericana excluida netea 0 (±423,6M en patas, verificado por el check de pares).
  - [x] Tests de mutación: wash excluido a medias → falla; excluir un par NO declarado → falla; excluir el par equivocado que también netea → falla por identidad (el caso que el conteo ciego dejaba pasar — es EL motivo del upgrade); pata B ruteada al vehículo equivocado → gate de destino acusa; cifra pinneada alterada → falla.
- [x] **Task 6 — Regresión y guardrails del proyecto**
  - [x] Suite completa `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q`: baseline **332 passed / 7 skipped** + los nuevos, 0 regresiones.
  - [x] `bean-check ledger/main.beancount` (picklecache borrado antes): exit 0 — E1.3 solo LEE el ledger.
  - [x] README sección E1.3 + actualización del contrato de regresión (`run_tier_a(..., excluded_je_ids=...)`).

### Review Findings

Code review 2026-07-25 (3 capas: Blind Hunter / Edge Case Hunter / Acceptance Auditor). Veredicto por AC: AC1 PASS, AC2 **PARTIAL** (D-1), AC3 PASS (nota P-10), AC4 PASS, AC5 PASS. El Auditor reprodujo la suite (366/7) y todas las cifras pinneadas.

- [x] [Review][Decision→Defer] **D-1: Latinoamericana FFCC-310009 ±423,6M NO se excluye en el mirror real** — el grupo real son 4 moves (RUT2 1194/1196/1316/1321) reversados por UNO (5387, +423.600.000): el emparejamiento por pares iguales-y-opuestos no puede 4-vs-1, así que las 10 patas quedan en Income + `latam-sin-par`/revisar (netean 0, nada pinneado se mueve). El inventario N-1 dice "Excluir" y solo el lado EAG-310010 se excluyó por pares. **Decisión Ary 2026-07-25: diferir a Valentina** — el código queda como está (residual conservador, flagueado y visible); el caso va a las preguntas para Valentina (§ abajo) y se resuelve en patch/story posterior según su veredicto (si confirma "excluir", implica exclusión por grupos-que-netean, no solo pares).
- [x] [Review][Patch] **P-1: wash sin par solo se marca en la rama G — una pata B de un comprobante huérfano se re-rutea al activo SIN flag** (A/F quedan sin flag). Flag `revisar` a nivel move para comprobantes no excluidos; cubre también el caso apertura 2-ene que `exercise_year` no cruza [pipeline/odoo_migration/sincerar.py:292-350]
- [x] [Review][Patch] **P-2: guards fail-loud en verify_counts + loader de alias** — identidades duplicadas/vacías del mirror colapsan en silencio en el dict; fallback `code "?"` en el neteo contradice la convención ValueError; sección `vehiculos` ausente en el YAML degrada todo G a sin-clasificar sin alarma [pipeline/odoo_migration/parity.py:220-263, sincerar.py:154-169]
- [x] [Review][Patch] **P-3: regex — `a\s+cta` sin boundary izquierdo ("transferencia cta" matchea), `_RE_PRESTAMO` sin boundaries ("desabono de prestamo" matchea), plurales faltantes arriendos/sueldos en `_RE_INGRESO_REAL`** (una pata B con glosa "arriendos" se rutea al activo en vez del conflicto N-2). Re-derivar pins si los conteos se mueven [pipeline/odoo_migration/sincerar.py:213-218]
- [x] [Review][Patch] **P-4: `VEHICULO_DESTINO` acuña cuentas cross-entity no validadas** — una glosa G de JAB con "mbi" → `Assets:JAB:MBI` (no existe en ningún plan); una glosa EAG con "sade" → `Assets:FFCC:InversionesSade` contaminaría el ancla pinneada de Sade. Validar el destino formateado contra allowlist conocida (ORIGEN_ASSETS ∪ Sade-FFCC); si no valida → sin-clasificar [pipeline/odoo_migration/sincerar.py:182-191, 383-387]
- [x] [Review][Patch] **P-5: log de washes sin "montos por código" (letra Task 2)** — `monto_abs` además duplica la magnitud (Σ|patas| = 2×wash) y mezcla monedas; las Completion Notes citan los valores doblados (±196M vs 98,2M del inventario). Agregar montos por (code, currency) a `ExcludedPair` [pipeline/odoo_migration/sincerar.py:393-455]
- [x] [Review][Patch] **P-6: "función pura" — las patas fuera del universo comparten el objeto (dataclass mutable) con el input**; mutar el resultado (E1.4 estamparía dims) corrompe el output de collapse. Copiar siempre [pipeline/odoo_migration/sincerar.py:540-541]
- [x] [Review][Patch] **P-7: docs stale** — docstring de módulo de parity.py y README §E1.2 aún citan `expected_excluded_*` (API eliminada); nota de que `verify_destination` standalone no valida exclusiones (lo hace `verify_counts` dentro de `run_tier_a`); docstring del cutoff full-mirror: es INCLUSIVO del 2026-07-23 — un posteo tardío ese mismo día también mueve pins (hoy solo advierte retro-posteos) [pipeline/odoo_migration/parity.py:15-18, README.md:69, tests/test_sinceramiento_full_mirror.py:39]
- [x] [Review][Patch] **P-8: tests — assert vacuo `cls.naturaleza in "0ABCDEFGH"`** ("" y "AB" pasan; usar set), `test_310013_al_peso` suma sin filtrar moneda, y el mensaje "exclusiones que NO existen en el mirror" (fantasma) no tiene test [pipeline/odoo_migration/tests/test_sinceramiento.py, test_parity_tier_a.py:159-168]
- [x] [Review][Patch] **P-9: la letra de Task 1 (tabla NATURALEZA independiente cross-checkeada vs `sinc`) no está** — hoy la columna CSV ES la autoridad para A/C/D/E/F/G; un flip en el CSV reclasifica sin ValueError. Cerrar al patrón snapshot E1.2: test que pinnea las 83 filas (entity,code)→naturaleza [pipeline/odoo_migration/sincerar.py:68-96]
- [x] [Review][Patch] **P-10: letra de Task 5 — los Σ por vehículo no son constantes pinneadas** (el test los re-deriva del mirror; los pins independientes son solo Sade/Molco/JAB/Jhonny/Δ). Derivar una vez, pinnear literales y documentar en Completion Notes [pipeline/odoo_migration/tests/test_sinceramiento_full_mirror.py]
- [x] [Review][Defer] **W-1: `_txn_identity` asume company homogénea por txn** (deriva de postings[0]; sin guard de homogeneidad) [pipeline/odoo_migration/parity.py:131-136] — deferred, inalcanzable hoy (cada JE Laudus vive en un solo RUT)
- [x] [Review][Defer] **W-2: cierre de población keyed por prefijo `Income:` del destino** — una futura fila de ingreso ya re-ruteada a nivel tabla con `sinc` vacío escaparía del sinceramiento sin fail-loud [pipeline/odoo_migration/sincerar.py:280-286] — deferred, población cerrada hoy (83 filas cross-checkeadas)
- [x] [Review][Defer] **W-3: el neteo de exclusiones es agregado sobre el set completo, no por par declarado** — dos moves reales no relacionados que neteen por (company,code,currency) pasarían; la API de set plano (pinneada por la story) no porta pares [pipeline/odoo_migration/parity.py:258-273] — deferred, sincerar solo produce sets derivados de pares; hardening para callers futuros

## Dev Notes

### Decisiones ya tomadas — NO re-litigar

- **Key `(entity, code)`** en todo (E1.2); códigos se repiten entre entidades. Company SIEMPRE derivada de la entity.
- **External IDs congelados** (E1.0): si algo emite xmlids, `external_ids.py`. Los washes excluidos NUNCA llegan a E1.5 → no consumen external ID.
- **La tabla CSV es la fuente del colapso; el generador de Valentina NO se toca.** E1.3 agrega reglas TRANSACCIONALES encima del colapso — la tabla-madre del inventario es la autoridad de naturaleza; la columna `sinc` del CSV es el seed que se cross-valida (mismo patrón que la columna `company` en E1.2).
- **NO fuzzy matching como decisor** (winston §6·B.3). Tabla de alias explícita + normalización; fuzzy a lo sumo como sugeridor en revisión humana (fuera de scope E1.3).
- **Universo `source: "laudus-erp"`** compartido por transformador y verificador (E1.2).

### Resoluciones de ambigüedad pinneadas para el dev (con fuente)

1. **N-2 (dividendo +32,16M Nuevo Ciclo, fixture id 4158):** el inventario decía "sigue el destino de la cuenta salvo que las contadoras la separen"; el AC5 del epic (posterior, mesa redonda) dice "queda en Income + marcada revisar". **Manda el epic**: queda en Income + flag. La regla general que lo implementa: pata en cuenta B cuya glosa matchea patrón de ingreso real → ambigua → Income + revisar.
2. **D (disposición, P-2 abierta):** SPEC §3.2.e dice "Sale de Income → baja del Activo [sujeto a P-2]" — pero P-2 sigue abierta Y el activo a dar de baja no existe en el libro (autos/lancha jamás activados; patrimonio = E1B). Resolución conservadora (NFR6): **naturaleza D estampada + flag, SIN re-ruteo en E1.3**. El gate FR12c entonces NO cuenta D en la baja del ingreso. Documentar en Completion Notes; si Ary/Valentina cierran P-2 distinto, es un cambio de 1 entrada en el ruteo (la clasificación ya está).
3. **`REAL?(revisar)` (12 filas):** Latinoamericana 310009/310010 → **H-excluir** (inventario N-1, netea 0, tratar como wash por pares); JhonnyGuerra 310045/310047 → **H-por-cobrar** (el inventario los saca de "revisar"); Fondos Mutuos BCI (310025, x70021) y `Resultado*` 5xxx → **A con flag `revisar`** (cuentas casi vacías / Fase 2, quedan en Income). Ojo: la tabla marca `Resultado MBI 510011` como RETIRO → seguir la tabla (B).
4. **RetirosFondoComn-310006:** SPEC §2.2 lo describe como "traspaso desde FFCC (cuenta corriente de socios)" sin cuenta destino clara. `sinc` dice RETIRO. Resolución: **B con destino `Assets:EAG:RetirosFondoComun` provisional + flag `revisar`** (consistente con conservador; el monto es −125M). Anotar en Completion Notes.
5. **El "~46B" NO se assertea:** la cifra del gate = la que producen los datos clasificados; los anchors independientes exactos son Sade +4.876.249.792 y Molco +2.895.757.384 (inventario §1.1, verificados con bean-query por Valentina). El resto se deriva una vez y se pinnea (patrón "pinnear lo que DÉ" del snapshot E1.2).

### Cómo encaja con E1.2 (leer antes de codear)

- **Input de `sincerar` = output de `collapse`** (`OdooMoveRecord`/`OdooLineRecord`, [transform.py](../../pipeline/odoo_migration/transform.py)). `OdooLineRecord` ya trae `odoo_account`, `laudus_code`, `entity`, `currency`, `amount` (Decimal firmado), `desc` (la glosa por-pata — la regla G la lee de ahí). Agregar campos de metadata de sinceramiento al dataclass es decisión del dev (E1.2 dejó el naming libre).
- **`run_tier_a` es el contrato**: "todo transformador nuevo termina con esto en verde sobre el golden slice" (README del paquete). E1.3 lo llama con las exclusiones declaradas por identidad.
- **`verify_destination` computa el esperado ruteando el MIRROR por la tabla** ([parity.py](../../pipeline/odoo_migration/parity.py)). Tras E1.3 ese ruteo debe incluir el sinceramiento → extraer el ruteo a una función `route(entity, code, desc, amount) -> odoo_account` compartida por transformador y verificador. Limitación conocida (nota transversal del review E1.2): lo compartido se auto-cancela — por eso el cross-check independiente son las cifras pinneadas del inventario (AC3).
- **Guards nuevos de E1.2 que te afectan:** `collapse` fail-louds en `(company, je_id)` duplicado y move sin patas — `sincerar` NUNCA debe producir un move vacío (excluye moves completos, no patas); el loader de mapping cross-valida columnas (si tocás la tabla, esos guards avisan).
- **Learning del review E1.2 (aplicar de entrada):** exclusiones por conteo son un gate ciego — por eso AC2 exige identidad. Los tests de mutación no son opcionales: un verificador que no puede fallar es `tsc --noEmit`.

### El fixture golden YA trae los casos canónicos (E1.0 los curó a propósito — NO modificarlo)

| id | Caso | Naturaleza esperada |
|---|---|---|
| `1237` | Retiro Tecnión, 5 entidades (310013 + 4×`x70011`), −1.022.700.000 en 310013 | B → `Assets:<entidad>:InvTecnion` |
| `3994` | Aporte Sade signo + ("Inv. Sade Ltda - Aporte capital") | C — ya ruteado por la tabla; verificar |
| `29` | "Traspaso de Andres Turski G." en 310099 (G) | G → traspaso sin vehículo → sin-clasificar |
| `4158` | "Inversiones Nuevo Ciclo SPA - Dividendo" en 310016 (cuenta B) | Ambiguo N-2 → Income + revisar |
| `9000001`/`9000002` | Par Comprobante cierre/apertura sobre Latinoamericana 310009 ±423,6M | 0 → excluir el par por identidad |
| `9000003` | USD 100 @ 800 (multi-moneda) | La paridad por moneda no se toca |

El guardrail `test_fixture_golden.py` se pone rojo si el fixture cambia.

### Insumos que E1.3 reusa (NO reescribe)

- `pipeline/odoo_migration/transform.py` / `mapping.py` / `parity.py` (E1.2, ya code-reviewed) — extender, no duplicar. `MappingRow.sinc` ya viaja en la tabla cargada.
- `valentina-tabla-alias-2026-07-23.yaml` — cargarla tal cual (respetar `excluir_homonimos`, word-boundary en tokens cortos). Es data versionada; si falta un alias, se agrega AL YAML (loop de convergencia §6·B.3), no se hardcodea en el código.
- `valentina-inventario-naturalezas-2026-07-23.md` §2.2 (tabla-madre) — la autoridad de la clasificación. `valentina-spec-estructura-odoo-2026-07-23.md` §2.2 (destinos B por vehículo) + §3.2 (cascada).
- Patrón fail-loud `ValueError` contextual (external_ids.py/E1.2).
- PyYAML ya está disponible en el venv (lo usa el backend); no agregar dependencias.

### Deferred de E1.2 que esta story CIERRA / NO cierra

- **CIERRA:** exclusiones por identidad en `verify_counts`/`run_tier_a` (deferred-work.md, "[Parity] Exclusiones por CONTEO"). Al cerrar, marcar el ítem en `deferred-work.md`.
- **Opcional si se toca `ParityError`:** adjuntar los diffs como atributos programáticos (defer "[Parity] ParityError sin diffs programáticos") — hacerlo solo si sale gratis al modificar la excepción; si no, sigue diferido.
- **NO cierra:** `posting.price` (E1.5), validación `otype` (E1.5).

### Project Structure Notes

- Código nuevo: `pipeline/odoo_migration/sincerar.py` (hermano de transform/parity). Modificación quirúrgica de `parity.py` (API de exclusiones).
- Tests nuevos: `pipeline/odoo_migration/tests/test_sinceramiento.py` (+ el full-mirror puede ir en módulo propio `test_sinceramiento_full_mirror.py` para aislar el costo de carga). Todo Tier A — NADA `@pytest.mark.odoo`.
- El full-mirror test carga `ledger/main.beancount` una vez (fixture module-scoped). Si la carga supera ~30s y castiga la suite, plantearlo en Completion Notes (opciones: cache, marker) — NO inventar markers sin avisar.
- README del paquete: sección E1.3.

### Testing Requirements

- **Comando real (NO inventar otro):** `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q` (suite completa) / `… -m pytest pipeline/odoo_migration -q` (iterar). [Source: project-context.md]
- Baseline actual: **332 passed / 7 skipped** (post-review E1.2, commit 8858627). 0 regresiones.
- `bean-check` del mirror (picklecache borrado antes) — guardrail de solo-lectura.
- Tests de mutación obligatorios (Task 5) — disciplina anti-`tsc --noEmit`.

### References

- [Source: _bmad-output/planning-artifacts/odoo-migracion/epics.md#Story-E1.3] — ACs + nota (d) "mayor riesgo contable".
- [Source: _bmad-output/planning-artifacts/odoo-migracion/valentina-inventario-naturalezas-2026-07-23.md] — tabla-madre 0/A–H §2.2, gaps N-1..N-4, cifras exactas §1.1, afirmación de cierre §1.4.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/valentina-spec-estructura-odoo-2026-07-23.md#2-2 y #3-2] — destinos B por vehículo + cascada de la regla.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/winston-arquitectura-e1-odoo-2026-07-23.md#6] — invariancia de la paridad + caso washes; [#6·B] — alias/normalización/no-fuzzy/cobertura; [#8] — verify E1.3.
- [Source: _bmad-output/planning-artifacts/odoo-migracion/valentina-tabla-alias-2026-07-23.yaml] — alias + homónimos + word-boundary.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#Deferred-from-code-review-of-E1-2] — el defer de identidad que esta story cierra.
- [Source: pipeline/odoo_migration/{transform,parity,mapping}.py] — la cadena existente (post-review, commit 8858627).

### Preguntas guardadas para Ary / Valentina (no bloquean el dev)

1. **P-2 (Venta de Activos):** sigue abierta; E1.3 la esquiva (D marcada sin re-ruteo). Cuando las contadoras confirmen, el re-ruteo de D es una story chica o parte de E1B.
2. **N-2:** la pata "dividendo" +32,16M queda marcada `revisar con contadoras` (pin del epic). Si deciden separarla como ingreso real, es 1 entrada de allowlist.
3. **RetirosFondoComn-310006:** destino provisional propio (resolución 4). Validar con Valentina si prefiere rutearlo a cuenta corriente de socios en E1.4 (partners).
4. **N-1 residual (review 2026-07-25, D-1):** en el mirror real el grupo FFCC-310009 son 4 moves reversados por UNO (RUT2 1194/1196/1316/1321 vs 5387) — el algoritmo de pares no lo puede excluir, así que las ±423,6M quedan en Income + `revisar` (netean 0). El inventario N-1 dice "Excluir": ¿confirmás exclusión (→ extender a grupos-que-netean) o el residual flagueado te sirve hasta E1.5?

## Dev Agent Record

### Agent Model Used

claude-fable-5 (dev-story)

### Debug Log References

- Paquete: `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -q` → **109 passed, 5 skipped** (1.3s; los 5 skipped son Tier B opt-in).
- Suite completa: `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q` → **366 passed, 7 skipped** (2:06). Baseline 332+7 → **+34 tests nuevos, 0 regresiones**.
- bean-check del mirror (picklecache borrado antes): **exit 0** — E1.3 solo lee el ledger.
- Full-mirror exploratorio: carga 0.4s + collapse 0.1s + sincerar 0.4s + run_tier_a 0.2s sobre 16.633 asientos / 57.540 patas → el gate FR12c completo corre por-commit sin marker (~1.4s el archivo entero).

### Completion Notes List

- **Las DOS cifras del inventario dieron EXACTAS al primer full-mirror run:** Sade en activo == **+4.876.249.792** y Molco FFCC en gasto == **+2.895.757.384** (y JAB **−1.200.000.000**) — pinneadas al peso en `test_sinceramiento_full_mirror.py`. Anchors independientes del transformador (Valentina las derivó con bean-query).
- **La cifra exacta del "~46B" (FR12c):** ingreso CLP −84.825.124.241 (post-colapso) → −39.248.623.118 (post-sinceramiento) = **Δ −45.576.501.123** movidos fuera del ingreso por B/H/G-ruteado. Consistencia verificada con el SPEC §2: sumando el neto C/E que ya había salido en el colapso (+6.572M) se recupera el total de ingresos Laudus −78.253M del SPEC, al peso.
- **Cutoff por mirror vivo:** el mirror se sincroniza de Laudus → el test full-mirror corta las transacciones a la fecha del inventario (**2026-07-23**) para que la historia pinneada no se mueva con syncs futuros. Si se pone rojo sin tocar el transformador = un asiento retro-posteado cambió historia previa al corte (hallazgo, no flaky).
- **Washes excluidos por identidad (log pinneado):** 2 pares Comprobante cierre/apertura (RUT2 4529/4530 por 11.881M y 4724/4725 por 28.372M) + 3 pares reverso Latinoamericana (EAG 553/635, 555/636, 611/637 — ±98,2M/33M/10M por código, N-1; corregido en review: la cifra anterior citaba Σ|patas| = el doble). Los 4 comprobantes del mirror emparejaron todos (0 sin par). Emparejamiento por firma igual-y-opuesta `(code, currency, amount)` dentro del mismo ejercicio (el Comprobante de apertura del 1-ene cierra el ejercicio ANTERIOR). Desde el review P-5, `ExcludedPair.montos` trae la magnitud del wash por (código, moneda).
- **Hallazgo N-2 (data real):** el "dividendo dudoso" de Nuevo Ciclo resultó ser un **PAR espejado** — ids 4158 (−32,16M) y 4159 (+32,16M), mismo día, misma glosa — que **netea a 0**. Ambos quedan en Income + `revisar con contadoras` (regla cuenta-vs-glosa, pin del epic). No afecta ningún total. Son las ÚNICAS patas B que no aterrizan en su activo de origen (asserteado).
- **Exclusiones por identidad cierran el defer de E1.2:** `verify_counts`/`run_tier_a` ahora verifican (a) exactamente los declarados faltan, (b) ninguno más, (c) el conjunto excluido netea a 0 por código. El test de mutación clave: declarar el par equivocado (que también "cuadra" en número) **falla por identidad** — el caso que el conteo ciego dejaba pasar. Los 2 tests de E1.2 migrados a la API nueva (la API por conteo se eliminó, no convive).
- **Ruteo compartido transformador↔verificador:** `classify_line` es LA función de clasificación; `route_sincerado(mapping, aliases)` se la pasa a `verify_destination(route=...)` para computar el lado esperado desde el mirror. Limitación conocida (heredada del diseño E1.2): lo compartido se auto-cancela — el cross-check independiente son las cifras pinneadas del inventario.
- **Cobertura del transformador (FR10 versión E1.3), pinneada al corte:** por naturaleza A=318 B=127 C=31 D=41 E=115 F=422 G=342 H=67; **232 sin clasificar** (de las 342 G — visibles con glosa+monto en el reporte, nunca perdidas) y **64 a revisar** (D por P-2, A-revisar, N-2). La paridad es invariante a todo esto (winston §6·B.2: una glosa mal clasificada degrada la analítica, nunca el cuadre).
- **Resoluciones pinneadas aplicadas tal cual la story:** D marcada sin re-ruteo (P-2 abierta); RetirosFondoComn-310006 → `Assets:EAG:RetirosFondoComun` provisional + revisar; `REAL?(revisar)` repartidas (Latam→H-excluir, Jhonny→H por-cobrar −8,6M, resto→A+revisar); hijas `*70099` en G (N-4, la tabla ya las trae MIXTO).
- Alcance respetado: sin dimensiones/partners (E1.4), sin Odoo (E1.5/E1.6), fixture golden intacto, generador de Valentina intacto, tabla de alias consumida tal cual (data versionada).
- **Code review 2026-07-25 (3 capas): 10 patches aplicados, 0 pins movidos.** Los patches son hardening puro — la data real no tenía comprobantes huérfanos, falsos positivos de regex ni cuentas cross-entity acuñadas, así que TODAS las cifras pinneadas quedaron idénticas. Lo agregado: comprobante-sin-par visible en toda naturaleza (no solo G), guards fail-loud (identidades duplicadas/vacías en `verify_counts`, sección `vehiculos` del YAML, `code` sin meta), regex con word-boundary + plurales, allowlist de destinos G (`_DESTINOS_G_VALIDOS` + entidad fija para Sade/Inmobiliarias), `ExcludedPair.montos` por código, copia de patas fuera del universo (función pura de verdad), snapshot versionado de las 83 naturalezas (`NATURALEZA_SNAPSHOT`), y pins literales por activo de origen (`ACTIVOS_PINNEADOS`, 22 cuentas al peso). +7 tests → paquete 116/5, suite completa **373/7, 0 regresiones**. Queda 1 decisión diferida a Valentina (D-1, residual Latinoamericana 310009 — ver Review Findings y deferred-work.md) y 3 defers de hardening.

### File List

- `pipeline/odoo_migration/sincerar.py` (nuevo)
- `pipeline/odoo_migration/parity.py` (modificado — exclusiones por identidad + `route` en `verify_destination`/`run_tier_a`, helper `_txn_identity`)
- `pipeline/odoo_migration/transform.py` (modificado — 4 campos de metadata de sinceramiento en `OdooLineRecord`, defaults vacíos)
- `pipeline/odoo_migration/tests/test_sinceramiento.py` (nuevo — 23 tests)
- `pipeline/odoo_migration/tests/test_sinceramiento_full_mirror.py` (nuevo — 8 tests, gate FR12c)
- `pipeline/odoo_migration/tests/test_parity_tier_a.py` (modificado — 2 tests de exclusión migrados a identidad + 3 nuevos)
- `pipeline/odoo_migration/README.md` (modificado — sección E1.3 + contrato de regresión actualizado)
- `_bmad-output/implementation-artifacts/deferred-work.md` (modificado — defer de identidad marcado CERRADO)
- `_bmad-output/implementation-artifacts/E1-3-transformador-sinceramiento-naturalezas.md` (este registro)

## Change Log

- 2026-07-25 — E1.3 implementada: transformador de sinceramiento (`sincerar.py`: clasificador 0/A–H keyed `(entity,code)` con cross-check vs columna `sinc`, ruteo B→activos de origen / H→por-cobrar / G por-glosa con alias+normalización, washes excluidos por pares con identidad) + upgrade de `parity.py` a exclusiones por identidad (cierra defer E1.2) + ruteo esperado componible. Gate FR12c full-mirror con cifras exactas del inventario pinneadas (Sade +4.876.249.792 / Molco +2.895.757.384 / Δ ingreso −45.576.501.123), corte 2026-07-23. +34 tests (paquete 109/5; suite completa 366/7, 0 regresiones); bean-check verde. Hallazgo: N-2 es un par espejado 4158/4159 que netea a 0. Status → review.
