# Memory

_Conocimiento curado de largo plazo. Vacío al nacer — crece a través de las sesiones._

_Este archivo es para insights destilados, no notas crudas. Captura la esencia: decisiones tomadas, ideas que valen la pena, patrones detectados, lecciones aprendidas._

_Mantén bajo 200 líneas. Las notas crudas van en `sessions/YYYY-MM-DD.md` (no aquí). Destila insights de los session logs en este archivo. Poda lo obsoleto. Cada token aquí se carga en cada sesión — que cada uno cuente._

## Contexto del Proyecto

**family-office-eag** = family office de EAG. La contabilidad ahora vive en **Beancount** (antes se
exportaba de Laudus a Google Sheets; ese flujo se reemplazó). El importer Laudus→Beancount deja
Beancount = espejo fiel de Laudus. Ledger en `ledger/` (main.beancount + imports/laudus/ +
imports/cartolas/). Pipeline de import en `pipeline/importers/` (Stories 9.x).

## Modelo de Datos — Estado Actual

**Problema conocido — Tarjetas de crédito (diagnóstico verificado, corrige el entendimiento previo):**
NO es que "las compras estén como gasto". Lo real:
- Las compras individuales **no se registran**. Solo se registra el **pago mensual** (Banco → TC).
- Las cuentas `Liabilities:EAG:TC:*` son pasivo en el árbol Beancount, PERO su metadata dice
  `laudus_categoria1: "GASTOS - EGRESOS"`, así que el **reporte lee el pago como el gasto** (lumpeado).
- Verificado en histórico 2021-2022: 566 pagos vs 2 compras. Saldo TC absurdamente positivo.

**Estado:** Se corrige al importar cartolas de cada tarjeta (solo 2026 en adelante; proceso continuo).
**Acción requerida:** Reportes de gasto total / balance deben advertir la limitación mientras la
tarjeta no tenga cartola importada.

**Fuentes de datos:**
- Laudus → Beancount: activo (espejo fiel).
- Cartolas de tarjetas: import en construcción (Stories 9.5/9.6a/9.6b). Fuente de verdad de las compras.
- Cartolas bancarias (cta corriente): fuente de verdad planificada de movimientos de banco.

## Hallazgo — Ingresos de inversión mal contabilizados (2026-06-20, EAG)

Auditoría a pedido de Ary (sospechaba que cargaban mal los ingresos sin actualizar activos —
CONFIRMADO). Detalle en `_bmad-output/planning-artifacts/valentina-auditoria-ingresos-inversiones-2026-06-20.md`.

- Los retiros/rescates **no separan capital de ganancia**. Dos errores opuestos conviven:
  - **Error A:** retiro 100% a cuenta de ingreso, no baja el activo → infla P&L y balance.
    Tecnion 12.204M, Nuevo Ciclo 5.963M, MBI 4.767M, JB 3.259M = **≈26.193M CLP** mal cargados.
  - **Error B:** retiro 100% contra el activo sin reconocer ganancia → activo NEGATIVO (imposible).
    InvTecnionLimitada −3.353M, FmBciClass0 −202M, FmBciAp0 −26M.
- Cuentas de resultado de inversión `Income:EAG:Resultado*` (510xxx) = **0 asientos**. Nunca se usaron.
- Laudus NO hace revalorización a valor cuota (0 asientos de ajuste). La ganancia de fondos se fuga.
- Indumotora (≈25.269M a ingreso) = **dividendos, CORRECTO**, no es error (Ary lo clasificó).
- Clasificación de Ary: Tecnion/Nuevo Ciclo/MBI = inversiones; JB = cta inversión; BCI = fondos mutuos.
- **Clave:** la paridad contra el contador NO detecta esto — Beancount es espejo fiel de Laudus y el
  error está dentro de Laudus. Solo se pesca reconciliando vs posición real del custodio (cartolas).
- **No corregir sin saldos del custodio confirmados.** Fix futuro = estilo TC (solo asientos estándar).
- Hijas (Jocelyn/Jeannette/Johanna/Jael) FUERA de alcance: no se sabe si retiran de fondos propios.
- Herramientas: `_forense_inversiones.py`, `_forense_recon_vehiculo.py` (planning-artifacts).

## ✅ Revisado — Story 6.2 (desglose TC): 3 pendientes cerrados (2026-06-22)

Revisé los 3 pendientes contables con Ary antes de cablear el orquestador. Detalle en el
planning-artifact (§9 y §12.1 reescritos) y session log `sessions/2026-06-22.md`.

1. **Cruce cross-período (`MONTO CANCELADO`) — lo más delicado, OK con corrección.** El asiento (b) se
   maneja por el modelo **MONTO CANCELADO** (la línea interna del estado, que salda el período
   ANTERIOR y matchea un pago Laudus del MISMO mes), NO por la liquidación que salda el estado actual.
   Un mismo pago Laudus juega dos roles en estados ADYACENTES: denominador del FX del estado M−1 y
   asiento (b) del estado M. **El lump del asiento (b) = CLP REAL del pago Laudus (glosa-match), NUNCA
   `MONTO_CANCELADO_USD × FX_del_estado`** (se pagó a otro TC → dejaría residual de gasto falso). Mi
   §12.1 original ("una liquidación, dos roles del MISMO estado") estaba MAL y rompía el cuadre anual
   §7; corregido. El `derive_statement_fx` del dev ya usa bien `closing` + pago posterior.
2. **Lista de cuentas (8 `TC:Real` + Equity).** Una por tarjeta-moneda con actividad 2026: las 3
   productos (1027 Visa Infinity, 8996 Mastercard Lanpass, 0858 Visa Latanpass) × CLP/USD = 6, +
   `TcVariasEag` + `TcRaquelVentura` (CLP-only) + `Equity:Apertura:TarjetasSinDetalle`. **Skip Amex
   8083 (430011): cero actividad 2026.** Nombre = stem EXACTO del Laudus (decisión Ary). Raquel SÍ se
   itemiza (tarjeta que le paga EAG). Varias se crea pero queda en lump (cajón de varias físicas).
3. **Categorización PASIVO — el mecanismo real NO es el label.** El reporte agrupa el gasto por
   **`Categoria2`** (buckets DEPTO STGO / Casa Sur / Depto Miami / Gastos Personales), no por
   `Categoria1`. Lo que saca la cuenta del gasto es **`Categoria2`/`Categoria3` VACÍOS**. TRAP: las TC
   originales son `categoria2:"GASTOS PERSONALES"` — si se copia su metadata y solo se cambia
   Categoria1 a PASIVO, **igual suma al gasto**. Cada cuenta nueva necesita: `Categoria1` no-vacío
   (PASIVO / PATRIMONIO, evita el guard "sin categorizar" 10.2) + `Categoria2`/`Categoria3` vacíos +
   un `code` sintético (sin code, los postings colisionan en `accountnumber=""` y afloran como línea
   fantasma en el reporte). Verificado: asiento (b) reduce bien el bucket GASTOS PERSONALES.

## ✅ Cuentas TC:Real creadas (2026-06-25) — desbloqueo del desglose TC

Las 9 cuentas sintéticas del diseño §9 quedaron **declaradas en `accounts.beancount`** (commit
`1d6323b`, bean-check exit 0, 589 tests/0 regresiones):
- 8 `Liabilities:EAG:TC:Real:<stem>` (codes 230005/06/07/08/09/10/17/19 = espejo 2-prefix del code
  de gasto) + `Equity:Apertura:TarjetasSinDetalle` (311005). Amex 8083 omitida (cero actividad 2026).
- Metadata: `laudus_categoria1` no-vacía (PASIVO/PATRIMONIO), `categoria2`/`categoria3` **vacías**
  (mecanismo real de exclusión del reporte, que agrupa por cat2), `code` sintético (evita línea
  fantasma). Sin `bank_account_id` (la TC:Real se deriva por nombre, no se resuelve de la cartola).

**CORRECCIÓN importante de mi diseño §9:** el flujo 10.3 (`/cuentas-pendientes/promover`) **NO sirve**
para cuentas sintéticas — exige cuenta en cuarentena (404) + categoria3 obligatoria (choca con cat2/3
vacías). Las cuentas inventadas por nosotros se declaran **directo en el plan** (decisión Ary). El
flujo 10.3 es solo para promover cuentas que Laudus descubre.

**Item bank_account_id en las `...Us`: ya estaba resuelto** (las 9 cuentas-gasto TC ya lo tienen).

**Falta para que el desglose corra end-to-end** (dev/Ary, no contable): wirear el categorizador 9.7 en
`_build_importer` (hoy Noop→Suspense) + importar una cartola 2026 real por tarjeta. Ver [[BOND]].

## ✅ operation_type completo en desglose TC (2026-06-26) — cierra drop silencioso

La verificación end-to-end (cartola BCI 2026-04 real, sandbox) destapó que el builder solo manejaba
`{compra,cuota,abono,pago}` y **descartaba el resto en silencio** (impuesto+comisión BCI → $6.795
perdidos en AMBOS lados: pasivo `TC:Real` subvaluado Y gasto desaparecido). Test de completitud:
**`saldo TC:Real al cierre == −closing`**. Decisiones (detalle en §10.1/§12.4 del planning-artifact):

- **Cargos bancarios** (impuesto/comision/interes/seguro/mantencion) → `Expenses:EAG:GastosBancarios-430003`
  (existe, cat2 poblada → cuenta en reporte). **Global** (Ary). Determinístico por op, NO usa el 9.7.
- **`avance`** = préstamo (plata que entró), NO gasto → `Assets:EAG:Caja-111001` / `CajaUs-111003`
  (existen, sirven TC+débito). **Lección general: no todo lo que sube la deuda es gasto.**
- **Nunca descartar:** op no reconocida → asiento (a) contra `Suspense` + reportar en `result`.
- Cero cuentas nuevas — todo ya en el plan. Fix queda para dev (ampliar mapeo + surfacear no-mapeadas).

**Barrido 304 cartolas (2026-06-27):** `operation_type` de Gemini es vocabulario sucio → **630 líneas en
`None`** (compras sin taggear, MUCHO más que los $6.795 de BCI) + sinónimos `COMPRAS P.A.T.`/`pat`/
`compra_automatica`/`cargo_automatico` (→ compra) + `nota_credito` (→ abono). El builder DEBE normalizar
antes de despachar. Limitación: normalizar en el prompt 9.5 sería lo durable pero es riesgoso → band-aid
en el builder + red de seguridad (Suspense). Detalle §10.1.

**Recomendación + colores (Ary 2026-06-27):** el contador **confirma SIEMPRE, nada va a automático** (la
confirmación = su chequeo rápido). Lo que se afina es la recomendación + una **regla de 3 colores** (🟢/🟡/
🔴 = confianza, rojos arriba) para que vea de un vistazo dónde fijarse. **Aprendizaje sin auto:** el color
se pone más verde con cada confirmación (confianza historical = #conf/30); el umbral 30 deja de ser
compuerta y pasa a ser termómetro del color — nunca "deja de preguntar". Dev: el 9.7 ya calcula confianza+
fuente pero se pierden (`predict()[0]`); exponerlas + pintar en `/categorizacion`. Detalle §10.2/§12.5.

## ✅ Validado contra 14 cartolas reales (2026-06-29) + limitación Laudus nueva

Dry-run del desglose TC (fix "contabiliza todo operation_type", prod commit `26aacf4`) contra las 14
cartolas reales de `samples/` (3 tarjetas × CLP/USD × feb/mar/abr). **11 corrected / 3 blocked,
`unmapped` vacío en las 14** → el fix es robusto sobre datos reales, cero drops. Veredicto completo en
`_bmad-output/planning-artifacts/valentina-veredicto-desglose-tc-14cartolas-2026-06-29.md`.

**LIMITACIÓN DEL MATCHER (no de Laudus) — pagos Santander consolidados.** Los 3 bloqueos USD (Mastercard
8996 feb/mar, Latanpass 0858 feb) NO son bug, NO son impago, y (corregido tras ver los asientos
completos) NO es que Laudus esté mal: **los pagos están bien posteados por cuenta**. Santander paga las
tarjetas Santander con asientos CONSOLIDADOS — UN asiento "Visa Santander 0858" paga 4 cuentas TC a la
vez (Master CLP+USD, Latanpass CLP+USD) desde la cta cte Santander; la glosa nombra UNA tarjeta y UN USD
aunque paga varias. **El problema es que `derive_statement_fx` matchea por la GLOSA de texto** (que
Santander llena inconsistente), no por el monto CLP que entró a cada cuenta. Ese monto SÍ da FX sano:
Master USD feb 1.291.675/1.387,63 = **930,8 ✅**; Latanpass USD feb 3.000.722/3.217,07 = **932,7 ✅**.
→ es recuperable. **Excepción real: Master USD marzo** — ningún posting da FX sano; el 2026-05-06 postea
**51,3M CLP a la cuenta MasterUs** (~57k USD, muchísimo más que el closing) = lump acumulado o misposteo,
necesita revisión humana de Ary. Contraste: BCI 1027 USD tiene glosas limpias (1 asiento/tarjeta/moneda,
USD en glosa) → cuadró los 3 meses. **FIX correcto (NO es BCCh ni limpiar Laudus): augmentar el matcher**
— si la glosa no cuadra, caer a `CLP a la cuenta de esta tarjeta ÷ closing`, gateado por el chequeo BCCh
existente (rechaza FX absurdos, acepta ~930). Preserva el cuadre exacto §12.1. Story nueva (mi dominio).

**Contigüidad:** la apertura ancla una vez; un mes faltante desfasa el SALDO del pasivo (no la
itemización, que va estado por estado). Materializar en corridas CONTIGUAS por tarjeta. Recomendé a Ary:
materializar primero lo limpio (CLP de las 3 + Visa Infinity USD), dejar las USD Santander hasta limpiar
Laudus, NO forzar FX.

## Segundo libro Laudus — RUT2 / Fondo Común (2026-06-30)

Proyecto en curso: replicar el sistema para un SEGUNDO libro de Laudus (RUT placeholder `12.345.678-2`, no entidad legal — otro libro de la misma familia, mismos contadores). Entidad hermana de EAG. Clasifiqué su plan de cuentas real (357 cuentas). Detalle en `_bmad-output/planning-artifacts/valentina-clasificacion-rut2-fondo-comun-2026-06-30.md`.

- **Son DOS sub-entidades** (patrón EAG+hijas): **FFCC** (Fondo Común, raíces 1·2·3·4) y **JAB/FGK** (raíces 6·7·8, sin pasivo propio). Grupo de consolidación = [FFCC, JAB].
- **Mapeo raíz→Beancount mecánico**: 1/6→Assets, 2→Liabilities, 3/7→Income, 4/8→Expenses; entidad por dígito (1-4=FFCC, 6-8=JAB). NO depende de categoria1.
- **Reporte por sub-entidad + categoria2** (encabezado numérico): FFCC = 41 Gastos Grales / 43 Gastos Fijos Oficina; JAB = 81 Casas / 83 Aviones / 85 Yates / 87 Gastos Personales. 196 hojas de raíz 8 ruedan a ~7 buckets — clasificación mecánica.
- 🚩 **MISMO problema de tarjetas que EAG**: TC de JAB/FGK (871005/873005) están como GASTO lumpeado; pasivo (raíz 2) vacío. El reporte de RUT2 hereda la limitación TC. Detalle = requiere desglose Epic 6 (futuro, no bloquea).
- Resueltos 2026-07-10/11 (Ary): FGK/JAB = UNA sub-entidad; P&L 4 vs 8 separados como reporte pero TODO se financia del FFCC; apertura probablemente inexistente (plug de Equity al importar, no patrimonio real).

**Contexto de negocio (Ary 2026-07-11)** — detalle en `valentina-contexto-fondo-comun-jab-2026-07-11.md`:
- FFCC = caja de los fondos familiares; reparte a AAG/EAG/DAG (hijos de JAB), AZBA (4 nietos, hijos de SAG = la hija fallecida) y FGK (viuda). "JAB" en cuentas = FGK en la práctica. **Label RESUELTO: `JAB`** (congelado por 11.2, ratificado por Ary vía Excel 2026-07-11 — NO re-abrir; la equivalencia JAB≡FGK queda como conocimiento de negocio).
- **EAG retira del FFCC (cta 115023)** → conciliación cruzada futura contra nuestro libro principal.
- **VERIFICADO en el plan: los retiros (115021–115039) son ACTIVO del FFCC (CxC)** — el fondo registra lo repartido como "me lo deben". Sospecha Ary confirmada en estructura; si no hay recuperos = activo inflado que esconde que el fondo se achica. Mismo patrón que la auditoría inversiones EAG.
- **Hipótesis solo-gastos:** Laudus del RUT2 sin ingresos de rentabilidad acreditados (MBI en 0 en el reporte del contador), sin saldos iniciales → usan Laudus solo para gastos. Se verifica al importar.
- Activos: Vía Gris (casa FGK), Reñaca (VENDIDA 2026 → sin movimientos nuevos), Molco (campo con pérdidas; casas + golf), Miami, 1 avión vigente de 3 (identificar por movimientos), 1 yate conocido de 3 (Keiki Kai).
- **Watchlist post-import (8 ítems, §4 del doc de CONTEXTO `valentina-contexto-fondo-comun-jab-2026-07-11.md` — no confundir con el §4 del artefacto firmado, que es la tabla de cobertura)** — DIFERIDA por Ary a cuando los números estén en Beancount. Pregunta de negocio del reporte 13.1 ampliada: (a) en qué gasta el fondo/FGK por activo + (b) cuánto repartió y a quién.
- **Excel de clasificación DEVUELTO 2026-07-11:** 357/357 SI (mapeo y labels FFCC/JAB/FondoComun ratificados), 2 TC (871005 probablemente sin uso; 873005 FGK activa con ~3 tarjetas acumuladas en una cuenta), cero correcciones. → 12.1 tiene su insumo; mi clasificación 06-30 validada por el dueño.
- **Convención Equity de apertura ADJUDICADA (yo, 2026-07-11, story 12.1):** FFCC abre self-balancing vía `Liabilities:FFCC:Apertura-211005` (espejo Laudus, como EAG); Equity solo como respaldo, UNA por sub-entidad: `Equity:FFCC:Apertura` (plug residual) y `Equity:JAB:Apertura` (todo lo del lado JAB — sin pasivo/patrimonio propio). Entidad como 2º segmento obligatoria (11.1); no cruzar plugs entre entidades; el monto puede ser plug grande ≠ patrimonio real (revisar post-import). Metadata 12.3: cat1=PATRIMONIO, cat2/3 vacías, code sintético, declarar directo en accounts.beancount. Formalizada en `clasificacion-contable-rut2-firmada-2026-07-11.md`.
- **Dirección futura (Ary 2026-07-11): reconciliación de BANCOS e INVERSIONES, ambos libros incl. EAG** (§7 del artefacto contexto). Hoy nadie concilia bancos; TC fue primero solo porque estaba mal catalogada. Cta cte EAG = maquinaria ya construida (extractor 9.5 + motor Epic 6), gap operacional. Inversiones = capacidad nueva, desbloquea la auditoría diferida de inversiones EAG (≈26.193M) y testea "rentabilidad ausente" FFCC. Mi prioridad recomendada: inversiones ≥ cta cte; retomar post Epics 11–13 con un brief de epic.

## ✅ Piloto TC materializado + bug de datos + vista de cuadre (2026-07-02)

Piloto BCI Visa Infinity 1027 CLP (feb/mar/abr) posteado en prod, **cierra al peso: `TC:Real ==
−3.219.948`** (cierre abril). Detalle en `sessions/2026-07-02.md` y artefacto
`valentina-bug-categorizacion-destruye-tc-real-2026-07-02.md`.

- **BUG CRÍTICO hallado+arreglado:** categorizar una compra TC BORRABA la pata `Liabilities:TC:Real`
  (el rewrite reescribía las 2 patas a la cuenta de gasto porque decidía por `bank_account_id`, que
  en TC da el lump 430005, no la deuda). Daba saldo positivo falso. Fix: categorizar toca SOLO la
  pata `Expenses:`/`Income:`. **Regla general:** el patrón "preservar la pata del bank_account_id" NO
  sirve para TC (la deuda `TC:Real` es cuenta derivada por nombre, sin bank_account_id).
- **Vista de cuadre (v1, construida):** NO es página aparte — es un paso en el flujo de subida. Panel
  post-confirmación con **C1** (`TC:Real al cierre == −cierre`, el chequeo estrella que habría cachado
  el bug) + pago cartola vs **asiento de pago Laudus** (`Assets:Banco → 430005`, un asiento/mes, glosa
  corrida un mes, monto == PAGO PAC). Fase 2 diferida: herramientas de ajuste si no cuadra.
- Re-importar una cartola sobrescribe el archivo y **resetea sus categorizaciones** → hay alarma que
  avisa antes de re-subir una ya importada.

## ✅ Materialización TC completa + regla FX-revolving diseñada (2026-07-06)

Las 13 cartolas quedaron en prod, verificadas al peso (1027 CLP/USD, 8996 CLP, 0858 CLP exactas;
8996 USD feb+abr+may). **Único hueco: 8996 USD marzo (revolving — cerró US$2.234,84 sin pago propio,
rodó a abril) → C1 rojo $718.919 en abril/mayo.** 0858 USD retirada (pago consolidado; mi story del
fallback por monto sigue pendiente, problema DISTINTO).

**Regla nueva diseñada (brief `valentina-story-brief-fx-revolving-tc-usd-2026-07-06.md`, Ary decide):
un mes revolving hereda el fx del estado que ABSORBIÓ su saldo** (marzo hereda 899,64 de abril). No
es estimación — es el costo real: el pago de mayo ($51.301.494) pagó abril Y marzo juntos a 899,64.
La aritmética lo impone: es el ÚNICO fx que deja C1 verde en toda la cadena (C1-marzo es verde con
cualquier fx por el telescopio; C1-abril exige exactamente el fx de abril). BCCh descartada con
fundamento (rojo perpetuo ~$71k con un dólar que nadie pagó). Extensión transitiva de §12.1, no
excepción. Guardas: heredar solo de estado contiguo ya importado, metadata `fx_source:"inherited:…"`,
gate BCCh ±5% aplica igual, tope 3 meses, sin cadena de pago real → sigue bloqueando.

**Resuelto un flag mío del 2026-06-29:** el posting de 51,3M a MasterUs que marqué "lump acumulado o
misposteo, revisión humana" era el pago LEGÍTIMO del cierre de abril (abril absorbió marzo y creció a
~57k USD). No era misposteo. Lección: un monto "muchísimo más grande que el closing de un mes" puede
ser simplemente la cadena revolving mirada desde el mes equivocado.

## Reportes Aprobados
_Reportes que el dueño ha aprobado desarrollar. Actualizar a medida que se aprueban._

## Decisiones de Diseño
_Decisiones arquitecturales tomadas. Para no re-litigar._

**Corrección contable de TC vía cartolas (2026-06-20)** — ver
`_bmad-output/planning-artifacts/valentina-correccion-tc-cartolas-2026-06-20.md`.
- La corrección se hace **solo con asientos contables estándar** que emite el import de cartola. NO
  se toca el motor/importer/metadata existente (regla de oro: evitar bugs).
- Por tarjeta, al importar su cartola 2026: (a) compras itemizadas → `TC:Real`/`Expenses`;
  (b) pago reclasificado de `TC original (gasto)` a `TC:Real`, mismo mes, sin tocar el banco;
  (c) una vez, `opening` de la 1ª cartola → `TC:Real` contra **`Equity:Apertura`** (NO gasto).
- Cuenta nueva por tarjeta `Liabilities:EAG:TC:Real:*` con metadata `PASIVO`, creada por el flujo
  sancionado de cuentas pendientes. Las cuentas TC originales (categoria GASTO) quedan intactas.
- Sin doble conteo (prueba de suma anual: gasto 2026 = Σ compras 2026). Borde de salida (dic→ene) se
  arregla solo porque el import es continuo.
- Tarjeta/período sin cartola → queda tal cual (gasto en cuenta TC original). Corrección es por
  tarjeta y por período.

**Decisiones para Story 6.6 (vista de cuadre TC C1–C5) — code review (2026-07-04/05):**
- **C1 USD = comparar en CLP contra −closing×fx_del_estado.** ⚠️ CORRIGE un rodeo: el 04-07 se
  implementó "C1 en nativo" por un diagnóstico MÍO errado (creí que había un "drift multi-mes" =
  closing×Δfx). NO existe: el pago (b) de cada mes es el CLP REAL que canceló las compras del mes
  anterior → en CLP el saldo TC:Real **telescopa exacto** a −closing_M×fx_M. Verificado sobre 1027 USD
  feb/mar: **C1 en CLP diff = 0,00**; en nativo diff = 14,73 USD (falso rojo, porque el pago lleva CLP
  al fx del mes ANTERIOR pero está estampado con el del mes actual → ÷fx equivocado). Revertido a CLP
  el 05-07. **El fix REAL era solo la apertura (abajo), no el nativo.** (Caveat: la fórmula CLP asume
  pago-full; una tarjeta que arrastra saldo sin pagar sí tendría dif. de cambio real — no aplica a las
  pago-full que materializamos.)
- **Endpoint GET /tc/reconciliation = forma PLANA, no anidada.** El AC6 pedía {cartola/ledger/laudus/
  checks}; el dev entregó plano (todos los campos al nivel del row). Todos los datos están, el front ya
  lo consume. Utilidad>forma: reformar = retrabajo cero-valor. Actualizar el spec a plano; `card`=
  bank_account_id (no stem), detalle de API. Los nombres ya distinguen la fuente (`closing`=cartola,
  `tc_real_balance`=ledger, `laudus_payment_total`=Laudus).
- **Gotcha operacional:** el cuadre lee opening/closing de la metadata del asiento (6.6 Task 1). Una
  cartola importada con la v1 (sin esa metadata) da C1 contra 0 → rojo; hay que **re-importar** bajo 6.6
  para que estampe opening/closing. Feb 1027 USD estaba importada con v1 → re-import pendiente.

**Apertura USD al fx del pago que la salda, NO al fx del estado (2026-07-04) — cierra el C1-rojo de la 1027 USD:**
- Caso real (1027 Visa Infinity USD feb): C1 rojo, TC:Real −571,64 vs cierre −465,59 (US$106 / 98.736 CLP).
  Verificado: la apertura (deuda de enero US$1.448,79) se valorizaba a `opening×fx_ESTADO` (931 de feb) =
  1.348.897, pero enero se saldó con 1.250.161 CLP reales al fx de ENERO (~863). El pago real no limpia la
  apertura sobrevaluada → 98.736 de deuda fantasma. `98.736 = 1.448,79 × (931−863)` = dif. de cambio sobre
  la apertura.
- **FIX (opción A): valorizar la apertura al CLP REAL del pago (MONTO CANCELADO) que la salda, no a
  opening×fx_estado.** Misma regla del CLP real que el asiento (b). Apertura y primer MONTO CANCELADO son la
  MISMA deuda → mismo CLP → se netean. TC:Real cierra a −closing nativo, C1 verde. Arregla el balance (hoy
  TC:Real y Equity:Apertura están los 2 inflados en la dif. de cambio); manda bien a Equity el pago de la
  deuda pre-2026 (no es gasto 2026).
- **Solo la apertura (one-time).** Los demás meses se autocancelan: el fx del estado SALE del pago que lo
  salda (§12.1), así que compra@fx_M y su liquidación@fx_M comparten dólar por construcción (feb compras
  @931, feb pagado @931). La apertura es la única deuda cuyo fx de carga ≠ fx de settlement.
- **NO es (B)** (dif. de cambio a resultado): la apertura es un plug sin base CLP previa → valorizarla a lo
  que cuesta saldarla no genera ganancia/pérdida. (B) rompería el espejo-Laudus (no revaloriza). No rompe
  §12.1 ni el no-doble-conteo (la apertura va contra Equity, no toca gasto; el cuadre Σcompras×fx=lump es
  intra-estado).
- **CAVEAT:** limpio si la apertura se salda en la 1ª cartola (tarjeta pago-full, como 1027). Opening que
  se arrastra/paga en cuotas a fx distintos = posición de cambio abierta → repensar (valorizar al fx del 1er
  pago, aceptar residual hasta saldar). **Dev:** `tc_correction.emit_opening` hoy `opening_clp=opening×fx`;
  cambiar a el CLP del pago que salda la apertura (opening_fx = pago_CLP ÷ opening_USD, solo para apertura).

**Decisiones para Story 6.2 (2026-06-22)** — ver §12 del doc. Tres cierres clave:
- **FX USD** = lump CLP del pago que SALDA el estado (mes siguiente) ÷ total USD facturado. Fuerza
  Σ(compras×FX)=lump (cuadre exacto, no BCCh). Lump = FX-denominador Y asiento(b), un solo evento.
  Sin lump aún → bloqueante, no estimar.
- **Abono** = compra invertida (no distinguir impuesto vs devolución).
- **`TC:Real` una por LÍNEA DE CRÉDITO** (unifica nacional+USD; la deuda es una). Adicionales ruedan
  ahí → `card_suffix` deja de bloquear (metadata opcional, no toca el prompt 9.5).
