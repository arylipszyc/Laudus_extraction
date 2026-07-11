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

**Convención de path para hojas (la usa 12.3):** `{Root}:{Entidad}:{slug}-{código}` — ej. `Assets:FFCC:CajaUs-111003`, `Expenses:JAB:...-871005`. Mismo patrón que EAG (`Liabilities:EAG:Apertura-211005`).

## 2. Decisiones firmadas

| # | Decisión | Resolución | Fecha | Fuente |
|---|---|---|---|---|
| D1 | ¿Raíces 4 y 8 son P&L separados? | **Sí, como estructura de reporte** — pero conceptualmente TODO se financia del FFCC: raíz 4 = gasto de administrar el fondo; raíces 6–8 = gasto de la rama FGK. El reporte debe dejar ver "cuánto sale del fondo y hacia quién/qué". | 2026-07-11 | Valentina, contexto §5 |
| D2 | ¿FGK y JAB = una o dos sub-entidades? | **UNA sub-entidad** (label `JAB`). "JAB" en el plan = FGK en la práctica (el patriarca dio nombre al libro histórico). | 2026-07-10 | Ary, intake 1-bis ítem C |
| D3 | Labels de entidad y grupo | **`FFCC` / `JAB`**, grupo **`FondoComun`** — DEFINITIVOS, congelados por 11.2 y ratificados vía Excel. Cumplen restricciones del defer de 11.1: alfanuméricos, regex-safe, case-sensitive distintos de miembros EAG. | 2026-07-11 | `bql_queries.py` CONSOLIDATION_GROUPS + Excel 357/357 (contexto §6) |
| D4 | Convención Equity de apertura | Ver §3 (LA decisión que esta story cerró). | 2026-07-11 | Valentina, adjudicación sesión 12.1 |
| D5 | Cuentas TC del libro | Solo **871005** y **873005**, gasto lumpeado estado-1 (ver §5). | 2026-07-11 | Excel devuelto + contexto §2 |

## 3. Convención de Equity de apertura (D4 — adjudicada por Valentina 2026-07-11)

**Principio rector:** espejo fiel de Laudus primero; Equity solo donde Laudus no tiene con qué cerrar. Igual que EAG.

1. **Apertura FFCC — mecanismo primario: SIN Equity.** La apertura entra self-balancing vía **`Liabilities:FFCC:Apertura-211005`** (la cuenta 211005 "Apertura" existe en el plan real, raíz 2 — única hoja de esa raíz). Mismo mecanismo que el JE "Saldo anterior" de EAG (`Liabilities:EAG:Apertura-211005`; evidencia: `ledger/opening-2021.beancount:7-13`, `ledger/imports/laudus/2021-01.beancount:11`). Si Laudus trae el asiento, Beancount lo copia y cierra solo.

2. **Cuentas Equity de respaldo — UNA por sub-entidad** (nombres completos, definitivos):

   | Cuenta | Cuándo se usa |
   |---|---|
   | `Equity:FFCC:Apertura` | SOLO si el subárbol FFCC no cierra tras el import histórico (plug residual). Probablemente chico o innecesario — 211005 existe. |
   | `Equity:JAB:Apertura` | Contrapartida de **cualquier** saldo de apertura o descuadre del lado JAB. JAB no tiene raíz de Pasivo ni Patrimonio — no hay otro lugar donde cuadrarlo. Si aparece un plug grande, vive acá. |

3. **Restricción técnica cumplida (11.1, NO negociable):** entidad como 2º segmento del path → `_group_pattern` asigna ambas mecánicamente al grupo `FondoComun`. **Prohibido** usar los namespaces sin entidad (`Equity:Apertura:*`, `Equity:Reconciliation:*` — lista congelada `_ENTITYLESS_EQUITY_NAMESPACES`, `bql_queries.py:42-45`): consolidan al grupo EAG en silencio.

4. **Regla de asignación del plug: nunca cruzar entidades.** Un descuadre JAB no se tapa con Equity de FFCC (y viceversa) — si se cruza, el per-entity de 11.2 mostraría cada sub-entidad individualmente descuadrada aunque el libro consolidado cierre.

5. **⚠️ Advertencia de Valentina (obligatoria de propagar a 12.4):** el monto de estas Equity puede ser un **plug grande**. Es artefacto de la hipótesis "Laudus solo para gastos" (sin saldos iniciales reales, sin rentabilidad acreditada), **NO patrimonio real** del fondo ni de FGK. No interpretarlo como riqueza hasta la revisión post-import (watchlist §4 del doc de contexto — diferida por Ary).

6. **Metadata para 12.3 (precedente TC:Real 2026-06-25):** son cuentas sintéticas (no existen en el plan Laudus) → se declaran **directo en `accounts.beancount`** (el flujo 10.3 no sirve: exige cuarentena + categoria3). Metadata: `laudus_categoria1` no-vacía (`PATRIMONIO`, evita el guard 10.2), `categoria2`/`categoria3` **vacías** (mecanismo real de exclusión del reporte de gastos), `code` sintético único respetando el índice `(entidad, code)` de 12.2, sin `bank_account_id`.

## 4. Cobertura verificada mecánicamente (2026-07-11)

Script sobre `rut2-plan-cuentas-laudus-2026-07-10.json` (descartable, scratchpad de la sesión dev 12.1). **Resultado: PASS** — sin cuentas sin destino.

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
(b) *¿cuánto repartió el fondo y a quién?* (retiros por persona — el reporte del contador gira en torno a esto; cuentas 115021–115029).

## 8. Qué consume 12.3 de este doc

- **Mapeo raíz→(root, entidad)** (§1, tabla 7 filas) + convención de path `{Root}:{Entidad}:{slug}-{código}` → generar las **309 hojas** (§6) bajo `Assets|Liabilities|Income|Expenses` × `FFCC|JAB`.
- **2 cuentas Equity nuevas** (§3.2): `Equity:FFCC:Apertura` y `Equity:JAB:Apertura`, con la metadata de §3.6 (cat1=PATRIMONIO, cat2/3 vacías, code sintético, sin bank_account_id), declaradas directo en `accounts.beancount`.
- **Labels congelados** `FFCC`/`JAB`/grupo `FondoComun` (§2 D3) — no re-abrir.
- **TC 871005/873005** (§5): se generan como hojas de gasto normales (estado-1); ninguna cuenta `TC:Real` se crea en 12.3.
- **`bank_account_id`**: NO vienen de aquí — 12.3 los mintea al crear las cuentas (intake Sección 3).
- **Gate de 12.3 sin cambios**: bean-check 0 + reportes EAG intactos (el subárbol RUT2 no debe tocar nada de EAG — guardrail 11.1 ya activo).
