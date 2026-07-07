# Discovery — Segundo RUT (No EAG): intake de información

**Fecha:** 2026-06-30
**Objetivo:** recabar de una sola vez todo lo necesario para replicar el family office para un 2º RUT (relacionado a EAG, entidad hermana en el mismo ledger). Evitar pedirle al contador cosas de a poco.
**Arquitectura decidida:** un solo sistema, un solo ledger, RUT2 como entidad hermana de EAG. Ver `_bmad/memory` → `project_segundo_rut_multientidad`.

> **Cómo leer este doc:** la **Sección 1** es la base del mensaje al contador — ⚠️ al reenviarla, **quitá antes los bloques de nota interna** (los citados `>` dentro de B y G, y el aviso de colisión de códigos: son deliberaciones nuestras, no preguntas para él). Las Secciones 2–5 son decisiones/tareas internas (no molestar al contador con ellas).

---

## Sección 1 — Para el contador (lo que solo él/Laudus tiene)

### A. Identidad y acceso a Laudus
1. **RUT de la empresa** (con dígito verificador, formato `XX.XXX.XXX-X`). → es el `companyVATId` del importador.
2. **¿Está en la misma cuenta de Laudus que EAG (mismo login) o es una empresa/login distinto?** Necesitamos **usuario y clave con permiso de lectura vía API** para esa empresa.
3. **¿Desde qué fecha está la contabilidad cargada y al día en Laudus?** ¿Desde qué período quieres que importemos el histórico? (EAG arrancó en 2021.)

### B. Plan de cuentas — **lo sacamos nosotros de Laudus, NO se lo pedimos al contador**
> (Los ítems 4–5 originales de esta sección quedaron absorbidos por la corrección de abajo; la numeración sigue en 6.)
> **Corrección 2026-06-30 (verificada con la sonda):** Laudus solo expone `accountId, accountNumber, name, notes` (`bootstrap/sources.py:19`). **No hay "categorías" que exportar** — las `categoria1/2/3` de EAG fueron una clasificación MANUAL (Supabase, hoy deprecada). Los códigos + nombres del plan de RUT2 los traemos directo de `/accounting/accounts/list`. Lo que NO existe y hay que **crear** es la clasificación (ver ítem G).
>
> ⚠️ **Colisión de códigos:** RUT2 reusa los mismos códigos que EAG (111001, 111005…). El importador rutea por `code`; hay que scopearlo a `(entidad, code)` y pre-crear el subárbol de RUT2 antes de importar. Trabajo interno (ítem #4 del plan), no del contador.

### C. Sub-entidades / consolidación
6. **¿Este RUT tiene sub-entidades o personas relacionadas cuya contabilidad viva dentro del mismo RUT** (como EAG contiene a Jocelyn, Jeannette, Johanna, Jael)? Si sí: la lista y **cómo se distinguen en el plan de cuentas** (por categoría, por prefijo de código, etc.).

### D. Cuentas bancarias y de inversión
7. **Lista de cuentas bancarias y de inversión** del RUT, con: **banco, número de cuenta, moneda (CLP/USD), tipo** (cuenta corriente / inversión). (El código y nombre ya vienen en el export B; esto confirma banco + moneda + tipo.)
8. **¿Están disponibles las cartolas (PDF) de esas cuentas y desde cuándo? ¿De qué bancos?**
   > Importa porque nuestro extractor de PDF está afinado por banco. Bancos ya probados: BCI (y otros de EAG). Un banco nuevo puede requerir ajuste — mejor saberlo ahora.

### E. Tarjetas de crédito
9. **¿El RUT tiene tarjetas de crédito?** Si sí: cuáles (banco/emisor), moneda, ¿hay cartola/estado de cuenta de la TC disponible?, y **¿cómo aparecen hoy en la contabilidad de Laudus** (a qué cuenta se cargan)?

### F. Apertura / saldos iniciales
10. **¿Cómo están registrados los saldos iniciales / apertura en Laudus?** (En EAG existe un asiento "Saldo anterior".) ¿Hay un asiento de apertura equivalente en Laudus, o necesitamos que nos entregues **saldos iniciales a una fecha de corte**?

### G. Clasificación + reporte (decisión, no export)
> Como Laudus no trae categorías, la clasificación de cada cuenta de RUT2 (a qué raíz Beancount va y cómo rolla en el reporte) es una **decisión que definimos nosotros** — idealmente con Valentina y/o el contador, igual que se hizo para EAG. NO es un archivo que el contador exporte.

11. **¿Qué reporte necesita este RUT?** ¿El mismo reporte de gastos mensual que EAG, un balance, ambos, otro?
12. **¿Cómo agrupar los gastos/cuentas en ese reporte?** (EAG agrupa por propiedad: Depto Santiago, Casa Sur, Miami, Gastos Personales.) → esto define tanto la clasificación de cuentas como la estructura del reporte del nuevo RUT.

### H. Ancla de validación
13. **Un dato conocido contra el cual validar:** saldo bancario real a una fecha reciente, o el balance de Laudus a fin de un mes. Nos permite reconciliar peso-por-peso como hicimos con EAG (así construimos la confianza en los números).

---

## Sección 2 — Decisiones de Ary (no del contador)

- **Nombre corto de la entidad en el sistema** (el "RUT2"): qué label usar en las rutas de cuenta (`Assets:<Label>:*`), en el selector del frontend y en `VALID_ENTITIES`. Ej.: iniciales o nombre corto.
- **Confirmar el grupo de consolidación:** RUT2 **NO** consolida bajo EAG (va aparte). Pendiente de definir: ¿alguna vez querrás una vista **combinada EAG+RUT2**? (Respondiste "a veces juntos" — dato para una fase posterior, no bloquea el arranque.)

## Sección 3 — Lo que generamos nosotros (NO pedir al contador)

- `bank_account_id` (UUID interno por cuenta bancaria; lo minteamos y lo ponemos en `accounts.beancount`).
- Rutas de cuenta Beancount (`Assets:RUT2:...`) — se derivan del export + convención.
- Afinamiento del extractor de PDF por banco.

## Sección 4 — Hallazgos de la sonda de lectura (2026-06-30, verificado)

Sonda read-only contra Laudus (`probe_laudus_rut2.py`, `pull_rut2_plan.py` en scratchpad). No tocó `ledger/` ni git.

- **Conexión:** mismas credenciales (`administrador`) + swap de `companyVATId` → funciona. El `companyVATId` SÍ cambia de libro (probado). RUT `12.345.678-2` = placeholder por diseño (no entidad legal; DV inválido esperado). ⚠️ Laudus NO falla ante RUT equivocado → el importador debe assertar la **empresa esperada por nombre** antes de escribir.
- **Qué es RUT2:** libro del **Fondo Común de otra rama familiar (JAB/FGK)** — casas, aviones, yates, gastos personales; retiros AAG/SAG/DAG/AZBA. NO es la misma familia/plantilla que EAG.
- **Plan de cuentas:** 308 cuentas hoja. Solo **31 códigos solapan** con EAG y **18 de esos son cuenta distinta bajo el mismo código** (set de colisión). El importador rutea por `code` → sin el fix `(entidad, code)` + subárbol pre-creado, los asientos de RUT2 se postean a cuentas de EAG en silencio.
- **Reporte (ítem #5) más chico de lo temido:** la jerarquía ya está en la numeración (8→81→811; encabezados = grupos: Casas/Aviones/Yates/G.Personales). Clasificación mayormente mecánica, no ~300 decisiones a mano.
- **Pendiente confirmar (Valentina/contador):** raíz 8 (196 hojas) → Expenses/P&L; qué son raíces 6 y 7; grupo top-level del reporte.

## Sección 5 — Precondición interna (nuestra, antes de importar data de RUT2)

- **Guardrail de consolidación por grupos** (`bql_queries.py`): reemplazar el supuesto "EAG = todas las cuentas" por grupos explícitos, para que los reportes de EAG no absorban a RUT2. Ítem #1 del work breakdown. **Hacer antes de meter cualquier dato de RUT2.**
