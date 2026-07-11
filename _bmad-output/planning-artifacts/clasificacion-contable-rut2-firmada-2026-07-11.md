# Clasificación contable RUT2 — FIRMADA (2026-07-11)

**Story:** 12.1 — Cerrar la clasificación contable con Valentina
**Estado:** FIRMADA. Este artefacto es el insumo autoritativo de la story 12.3 (árbol de cuentas RUT2 en `accounts.beancount`). Nada de lo aquí firmado se re-deriva ni se re-pregunta en 12.3.
**Fuentes:** clasificación técnica Valentina 2026-06-30 (`valentina-clasificacion-rut2-fondo-comun-2026-06-30.md`) · contexto de negocio + Excel devuelto (`valentina-contexto-fondo-comun-jab-2026-07-11.md` §5/§6) · intake Sección 1-bis, decisiones Ary 2026-07-10 (`discovery-segundo-rut-intake-2026-06-30.md`) · adjudicación Equity de Valentina 2026-07-11 (sesión 12.1, `_bmad/memory/agent-contadora/sessions/2026-07-11.md`) · plan real `rut2-plan-cuentas-laudus-2026-07-10.json`.

---

## 1. Mapeo raíz → (root Beancount, entidad)

Firmado y ratificado por Ary vía Excel (357/357 filas "SI", cero correcciones). La entidad se deriva del **dígito de raíz** del `accountNumber`, NO de categoria1.

| Dígito raíz | Nombre Laudus | Root Beancount | Entidad | Cuentas | Hojas |
|---|---|---|---|---|---|
| 1 | ACTIVO FFCC | `Assets` | FFCC | 30 | 26 |
| 2 | PASIVO | `Liabilities` | FFCC | 4 | 1 |
| 3 | INGRESOS | `Income` | FFCC | 11 | 9 |
| 4 | GASTOS | `Expenses` | FFCC | 73 | 63 |
| 6 | ACTIVO - JAB | `Assets` | JAB | 16 | 12 |
| 7 | INGRESOS JAB | `Income` | JAB | 4 | 2 |
| 8 | GASTOS JAB | `Expenses` | JAB | 219 | 196 |

**Convención de path para hojas (la usa 12.3):** `{Root}:{Entidad}:{slug}-{código}` — con **slug = `bootstrap/account_mapping.slugify`** (el algoritmo canónico que generó el árbol EAG; NO improvisar otro: 131 de las 309 hojas tienen caracteres no triviales — `$`, `/`, acentos, paréntesis). Ej. verificado contra el slugify real: `"Caja US$ - Fondo Común"` (111003) → `Assets:FFCC:CajaUsFondoComn-111003`. Mismo patrón que EAG (`Liabilities:EAG:Apertura-211005`).

> ⚠️ **Unicidad**: 31 grupos de hojas comparten NOMBRE bajo el mismo (root, entidad) — ej. "Teléfono" (433015/437015), "Mantención Equipos de Comunicación" ×4. El sufijo `-{código}` es lo único que garantiza paths únicos: ningún consumidor (12.3, reporte 13.1) debe agrupar ni mostrar por slug sin el código.
> Nota de firma: la columna "Hojas" de la tabla es **derivada del JSON** (verificación §4), no parte de la ratificación del Excel (que cubre sub-entidad y TC por fila).

## 2. Decisiones firmadas

| # | Decisión | Resolución | Fecha | Fuente |
|---|---|---|---|---|
| D1 | ¿Raíces 4 y 8 son P&L separados? | **Sí, como estructura de reporte** — pero conceptualmente TODO se financia del FFCC: raíz 4 = gasto de administrar el fondo; raíces 6–8 = gasto de la rama FGK. El reporte debe dejar ver "cuánto sale del fondo y hacia quién/qué". | 2026-07-11 | Valentina, contexto §5 |
| D2 | ¿FGK y JAB = una o dos sub-entidades? | **UNA sub-entidad** (label `JAB`). "JAB" en el plan = FGK en la práctica (el patriarca dio nombre al libro histórico). | 2026-07-10 | Ary, intake 1-bis ítem C |
| D3 | Labels de entidad y grupo | **`FFCC` / `JAB`**, grupo **`FondoComun`** — DEFINITIVOS, congelados por 11.2 y ratificados vía Excel. Cumplen restricciones del defer de 11.1: alfanuméricos, regex-safe, case-sensitive distintos de miembros EAG. | 2026-07-11 | `bql_queries.py` CONSOLIDATION_GROUPS + Excel 357/357 (contexto §6) |
| D4 | Convención Equity de apertura | Ver §3 (LA decisión que esta story cerró). **Auto-aprobada per project-context** como decisión técnico-contable — a diferencia de D1–D3/D5, NO pasó por Ary. | 2026-07-11 | Valentina, adjudicación sesión 12.1 |
| D5 | Cuentas TC del libro | Solo **871005** y **873005**, gasto lumpeado estado-1 (ver §5). | 2026-07-11 | Excel devuelto + contexto §2 |

## 3. Convención de Equity de apertura (D4 — adjudicada por Valentina 2026-07-11)

**Principio rector:** espejo fiel de Laudus primero; Equity solo donde Laudus no tiene con qué cerrar. Igual que EAG.

1. **Apertura FFCC — mecanismo primario: SIN Equity.** La apertura entra self-balancing vía **`Liabilities:FFCC:Apertura-211005`** (la cuenta 211005 "Apertura" existe en el plan real, raíz 2 — única hoja de esa raíz). Mismo mecanismo que el JE "Saldo anterior" de EAG (`Liabilities:EAG:Apertura-211005`; evidencia: `ledger/opening-2021.beancount:7-13`, `ledger/imports/laudus/2021-01.beancount:11`). Si Laudus trae el asiento, Beancount lo copia y cierra solo.

2. **Cuentas Equity de respaldo — UNA por sub-entidad** (nombres completos, definitivos):

   | Cuenta | Cuándo se usa |
   |---|---|
   | `Equity:FFCC:Apertura` | SOLO si el subárbol FFCC no cierra tras el import histórico (plug residual). Probablemente chico o innecesario — 211005 existe. |
   | `Equity:JAB:Apertura` | Contrapartida de **cualquier** saldo de apertura o descuadre del lado JAB. JAB no tiene raíz de Pasivo ni Patrimonio — no hay otro lugar donde cuadrarlo. Si aparece un plug grande, vive acá. |

> ⚠️ **Deriva vs la letra del epic (FR49/FR53) — esta convención SUPERSEDE al epic:** `epics-segundo-rut.md` dice "existe UNA cuenta de Equity de apertura para el libro" (FR49, AC de 12.3) y que el asiento de apertura "rutea a la cuenta de Equity de apertura (FR53)" (AC de 12.4). Lo firmado aquí es distinto y manda: el ruteo **primario** de la apertura FFCC es `Liabilities:FFCC:Apertura-211005` (espejo Laudus, precedente EAG), y las Equity son **dos** (una por sub-entidad, regla no-cruzar §3.4), solo como respaldo/plug. Sancionado por los Dev Notes de 12.1 + esta adjudicación. Quien redacte 12.3/12.4 desde el epic debe seguir este artefacto, no FR49/FR53 literales.

3. **Restricción técnica cumplida (11.1, NO negociable):** entidad como 2º segmento del path → `_group_pattern` asigna ambas mecánicamente al grupo `FondoComun`. **Prohibido** usar los namespaces sin entidad (`Equity:Apertura:*`, `Equity:Reconciliation:*` — lista congelada `_ENTITYLESS_EQUITY_NAMESPACES`, `bql_queries.py:42-45`): consolidan al grupo EAG en silencio.

4. **Regla de asignación del plug: nunca cruzar entidades.** Un descuadre JAB no se tapa con Equity de FFCC (y viceversa) — si se cruza, el per-entity de 11.2 mostraría cada sub-entidad individualmente descuadrada aunque el libro consolidado cierre.

5. **⚠️ Advertencia de Valentina (obligatoria de propagar a 12.4):** el monto de estas Equity puede ser un **plug grande**. Es artefacto de la hipótesis "Laudus solo para gastos" (sin saldos iniciales reales, sin rentabilidad acreditada), **NO patrimonio real** del fondo ni de FGK. No interpretarlo como riqueza hasta la revisión post-import (watchlist §4 del doc de contexto — diferida por Ary).

6. **Metadata para 12.3 (precedente TC:Real 2026-06-25, verificable en `ledger/accounts.beancount:2020-2046`):** son cuentas sintéticas (no existen en el plan Laudus) → se declaran **directo en `accounts.beancount`** (el flujo 10.3 no sirve: exige cuarentena + categoria3). Metadata: `laudus_categoria1` no-vacía (`PATRIMONIO`, evita el guard 10.2), `categoria2`/`categoria3` **vacías** (mecanismo real de exclusión del reporte de gastos), `code` sintético único respetando el índice `(entidad, code)` de 12.2, sin `bank_account_id`.

## 4. Cobertura verificada mecánicamente (2026-07-11)

Script sobre `rut2-plan-cuentas-laudus-2026-07-10.json`, **persistido como `_forense_verify_rut2_plan.py`** en este mismo directorio (patrón `_forense_*.py`; re-ejecutable ante cualquier disputa futura de conteos — la deriva 308/309 ya ocurrió una vez). **Resultado: PASS** — sin cuentas sin destino. Reproducido además 2× de forma independiente en el code-review de 12.1.

| Chequeo | Resultado |
|---|---|
| Total cuentas | **357** ✅ |
| Huérfanas (raíz ∉ {1,2,3,4,6,7,8}) | **0** ✅ |
| Duplicados de `accountNumber` | **0** ✅ |
| Hojas (sin descendiente por prefijo) | **309** ✅ |
| FFCC (raíces 1–4) | **118** ✅ |
| JAB (raíces 6–8) | **239** ✅ |
| Distribución por raíz | 1→30 · 2→4 · 3→11 · 4→73 · 6→16 · 7→4 · 8→219 ✅ |
| Hojas por raíz | 1→26 · 2→1 · 3→9 · 4→63 · 6→12 · 7→2 · 8→196 (FFCC 99 / JAB 210) |
| TC 871005 / 873005 | ambas existen y son hojas ✅ |

## 5. Tarjetas de crédito (D5 — landmine documentado)

Únicas 2 cuentas TC del libro, ambas colgadas de **gasto** (raíz 8, Gastos Personales); raíz 2 sin pasivo de tarjeta → **gasto lumpeado estado-1**, igual que EAG (pago mensual = "gasto"; correcto e intencional hasta un futuro desglose estilo Epic 6).

| Cuenta | Titular | Estado |
|---|---|---|
| `871005` JAB - Mastercard/Visa/Amex | JAB | **Probablemente SIN uso** — verificar por movimientos al importar (12.4) |
| `873005` FGK - Mastercard/Visa/Amex | FGK | **Activa** — acumula ~3 tarjetas en una sola cuenta; cuando toque el desglose, se abre en una `TC:Real` por línea de crédito |

El reporte de RUT2 (13.1) debe marcar la limitación TC en el cuerpo, como hace EAG.

## 6. Deriva documental: 308 → 309 hojas

El epic y FR48 dicen "308 hojas" (conteo de la sonda 2026-06-30). El JSON re-bajado y persistido 2026-07-10 da **309 hojas** — número AUTORITATIVO firmado aquí y verificado mecánicamente (§4). 12.3 debe generar contra 309; si un conteo da 308, el desvío es del conteo viejo, no del plan.

## 7. Pregunta de negocio del reporte (referencia para 13.1 — NO se diseña aquí)

El diseño de 13.1 debe contemplar la **doble pregunta** (Valentina, contexto §5):
(a) *¿en qué gasta el fondo y en qué gasta FGK, por activo?* (como EAG);
(b) *¿cuánto repartió el fondo y a quién?* (retiros por persona — el reporte del contador gira en torno a esto). ⚠️ **13.1 NO debe acotar por rango numérico**: el bloque de retiros/beneficiarios es más ancho que las 5 cuentas principales. Verificado en el plan (2026-07-11): 115021 AAG · 115023 EAG · 115025 SAG · 115027 DAG · 115028 Cta Cte DAG - Autos · 115029 AZBA · 115031/33/35/37 AZBA individuales (José Alazraki/Denise Zeldis/Michelle Zeldis/Ariel Borzutzky) · 115034 Denise Zeldis - Autos · 115039 Otros Retiros Hijos · **115041 Israel** (el rango "–115039" citado en docs previos también se quedaba corto). La membresía se deriva del plan al diseñar 13.1, no de un rango firmado.

## 8. Qué consume 12.3 de este doc

- **Mapeo raíz→(root, entidad)** (§1, tabla 7 filas) + convención de path `{Root}:{Entidad}:{slug}-{código}` con slug = `slugify` canónico → generar **SOLO las 309 hojas** (§6). Las 48 cuentas intermedias del plan (357−309) **NO se crean**: la jerarquía vive en la numeración del código (8→81→811), no en cuentas Beancount intermedias. Combinaciones válidas de (root × entidad): FFCC = `Assets|Liabilities|Income|Expenses`; JAB = `Assets|Income|Expenses` — **`Liabilities:JAB` NO existe** (JAB no tiene raíz 2; su contrapartida de apertura es `Equity:JAB:Apertura`, §3).
- **2 cuentas Equity nuevas** (§3.2): `Equity:FFCC:Apertura` y `Equity:JAB:Apertura`, con la metadata de §3.6 (cat1=PATRIMONIO, cat2/3 vacías, code sintético, sin bank_account_id), declaradas directo en `accounts.beancount`. **Total de `open` nuevos en 12.3 = 311** (309 hojas + 2 Equity) — un gate literal de "309 cuentas creadas" está mal calibrado.
- **Labels congelados** `FFCC`/`JAB`/grupo `FondoComun` (§2 D3) — no re-abrir.
- **TC 871005/873005** (§5): se generan como hojas de gasto normales (estado-1); ninguna cuenta `TC:Real` se crea en 12.3.
- **`bank_account_id`**: NO vienen de aquí — 12.3 los mintea al crear las cuentas (intake Sección 3). ⚠️ **Advertencia (code-review 12.1):** `bank_account_index._resolve_entity` (`backend/app/integrations/bank_account_index.py:111`) NO conoce FFCC/JAB y su fallback es `EAG`; peor, las categoria1 de RUT2 raíces 2/3 se llaman literalmente `"PASIVO"` / `"INGRESOS"`, que el mapa asigna EXPLÍCITO a EAG. Latente hasta subir cartolas RUT2 (diferidas por Ary), pero el fix debe entrar con 12.2/12.3 — está en `deferred-work.md`.
- **Gate de 12.3 sin cambios**: bean-check 0 + reportes EAG intactos (el subárbol RUT2 no debe tocar nada de EAG — guardrail 11.1 ya activo).
