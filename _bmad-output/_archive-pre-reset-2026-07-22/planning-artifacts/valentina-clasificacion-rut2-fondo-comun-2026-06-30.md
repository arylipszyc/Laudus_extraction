# Valentina — Clasificación contable de RUT2 (2º libro Laudus, Fondo Común)

**Fecha:** 2026-06-30
**Contexto:** Segundo libro de Laudus (RUT placeholder `12.345.678-2`) que replicará el sistema del family office como entidad hermana de EAG. Discovery técnico + pull del plan de cuentas real ya hechos (357 cuentas, 308 hojas). Ary pidió mi criterio contable para cerrar la clasificación cuentas → reporte.

## Hallazgo estructural: RUT2 son DOS sub-entidades, no una

El plan está partido en dos contabilidades paralelas dentro del mismo libro (patrón idéntico a EAG + hijas):

| Raíces | Sub-entidad | Roots contables presentes |
|---|---|---|
| 1·2·3·4 | **FFCC** (Fondo Común) | Activo · Pasivo · Ingreso · Gasto |
| 6·7·8 | **JAB / FGK** | Activo · Ingreso · Gasto (sin Pasivo propio) |

→ Responde el ítem #6 del intake: **2 sub-entidades**. Para el diseño técnico van como **entidades hermanas** (`Assets:FFCC:*`, `Assets:JAB:*`); grupo de consolidación del libro = **[FFCC, JAB]**. La entidad se deriva del **dígito de raíz** (1-4=FFCC, 6-8=JAB), NO de un string categoria1 → encaja con el fix `(entidad, code)`.

## Mapeo raíz → Beancount (mecánico)

| Dígito raíz | Beancount root | Entidad | Nombre Laudus |
|---|---|---|---|
| 1 | `Assets` | FFCC | ACTIVO FFCC |
| 2 | `Liabilities` | FFCC | PASIVO (casi vacío — solo Apertura) |
| 3 | `Income` | FFCC | INGRESOS |
| 4 | `Expenses` | FFCC | GASTOS |
| 6 | `Assets` | JAB | ACTIVO - JAB |
| 7 | `Income` | JAB | INGRESOS JAB |
| 8 | `Expenses` | JAB | GASTOS JAB |

## Respuestas a las 3 preguntas

1. **Raíz 8 = Gasto/P&L puro**, NO cuentas de orden. Árbol de resultado completo de JAB (sueldos, luz, agua, mantención) organizado por activo. → `Expenses`, entidad JAB.
2. **Raíz 6** = Activo JAB (cajas JAB/FGK, 4 bancos BCI, cuentas por cobrar). **Raíz 7** = Ingresos JAB (solo Molco + Otros Ingresos). Ambas verificadas hoja por hoja.
3. **Reporte en dos niveles**: (a) sub-entidad FFCC vs JAB; (b) por encabezado numérico = categoria2:
   - **FFCC:** `41` Gastos Generales (Sueldo Familia · Impuestos · Varios) · `43` Gastos Fijos Oficina (Gerencia · Oficina · Cepech)
   - **JAB:** `81` Casas (Vía Gris · Reñaca · Molco · Miami · Golf) · `83` Aviones · `85` Yates · `87` Gastos Personales
   - Las 196 hojas de raíz 8 ruedan a ~7 buckets — clasificación mecánica, no manual.

## 🚩 Landmine: mismo problema de tarjetas que EAG

- `871005 "JAB - Mastercard/Visa/Amex"` y `873005 "FGK - Mastercard/Visa/Amex"` cuelgan de **gasto** (raíz 8, gastos personales).
- Raíz 2 (Pasivo) prácticamente vacía (solo `211005 Apertura`) → **no hay pasivo de tarjeta**.
- **Conclusión:** las TC de JAB/FGK están como **gasto lumpeado** (pago mensual), no como pasivo itemizado — idéntico a EAG. El reporte de gastos de RUT2 debe marcar la limitación. Detalle de tarjetas = requiere el desglose de cartola del Epic 6 (decisión futura, no bloquea arranque).

## Pendientes para confirmar con el contador

- **No hay raíz de Patrimonio/Equity** ni Pasivo para JAB → la apertura necesitará una cuenta de equity para que el balance cierre (como en EAG con `Equity:Apertura`).
- **¿FGK y JAB son dos personas que se llevan juntas?** Tarjetas y gastos personales separados (871/873) pero comparten bancos en raíz 6. Definir si son una sub-entidad (JAB/FGK) o dos.
- **¿La raíz 4 (GASTOS FFCC) y raíz 8 (GASTOS JAB) son mundos separados** o hay gastos que deberían consolidar? Presumo separados (cada sub-entidad su P&L).

## Pregunta de negocio (mi estándar)

El reporte de RUT2 responde: *"¿en qué gasta el Fondo Común y en qué gasta JAB/FGK, por activo (casas/aviones/yates) y por categoría?"* — misma forma que el reporte de EAG. Confirma con Ary que esa ES la pregunta que quiere responder con este libro; si la pregunta es otra (ej. flujo entre FFCC y JAB, o aportes), el diseño cambia.
