# Product Brief — Migración de la contabilidad familiar a Odoo

**Autora:** Valentina · **Fecha:** 2026-07-23 · **Tipo:** North Star (documento estratégico)
**Estado:** BORRADOR para revisión de Ary. Precede a los epics. El SPEC técnico
(`valentina-spec-estructura-odoo-2026-07-23.md`) es su anexo.

---

## 1. El problema

La contabilidad de la familia vive hoy en **Laudus**. El spike de Odoo destapó tres dolores que Laudus no
resuelve, y que **no son del modelo de datos** (ese está bien) sino de la herramienta:

1. **UI para las contadoras / manejo de maestros** — pesado, poco flexible.
2. **Reportería** — hoy se arma por fuera (nuestro stack Beancount + Excel a mano de las contadoras).
3. **Un solo ecosistema** — hoy la contabilidad, la reportería y el análisis están en piezas separadas.

Y hay un problema de **fondo contable** que ninguna herramienta arregla sola, pero que la migración es la
oportunidad de corregir: **el P&L de Laudus es ficción.** De 78.253M de "ingresos", **~46.000M son movimientos
de capital / traspasos entre bolsillos propios** mal catalogados como ingreso. El ingreso operativo real es
**< 10%**. Y el **patrimonio es invisible** — las inversiones offshore, el yate, el avión y las casas no están
en el balance; solo aparecen como gasto cuando se consumen.

## 2. La visión

**Odoo se convierte en el único lugar donde vive la contabilidad de la familia: la historia completa de Laudus,
cargada, corregida y bien estructurada — con un P&L sincerado, un patrimonio visible, y la analítica (retiros
por socio, costo por activo, offshore) generada sola en vez de a mano en Excel.**

El principio no cambia respecto de todo el proyecto: **cargamos la verdad con datos reales y dejamos que las
contadoras decidan sobre esa base.** Odoo con la data real corregida en la mano es, en sí mismo, la herramienta
que les permite evaluar si migran.

## 3. Objetivos y criterios de éxito

| Objetivo | Criterio de éxito (medible) |
|---|---|
| Historia completa en Odoo | Toda la historia Laudus (2021→hoy) cargada, **cuadra al peso** contra Laudus (misma disciplina de paridad del proyecto). |
| P&L sincerado | El ingreso operativo real (~7B) queda separado de los ~46B de traspasos/retiros/aportes; el reporte de resultado dice la verdad. |
| Patrimonio visible | Existe un **reporte de patrimonio** con los activos (inversiones, yate, avión, casas) en el balance a costo, con participación por socio. |
| Analítica sin Excel | El "Resúmen Retiros por socio" y el "costo por yate/avión" se generan nativos en Odoo y **reconcilian** (dimensión socio = partición). |
| Estructura limpia | Plan de cuentas = **Laudus puro** (sin el `l10n_cl` del SII auto-instalado); dimensiones analíticas y tags definidos. |

## 4. Alcance por fases

```
FASE 1 — Espejo corregido y estructurado  (el corazón; común a las dos decisiones de §5)
  · Importar toda la historia Laudus a Odoo (EAG · FFCC · JAB), paridad al peso.
  · Plan de cuentas Laudus puro (sin l10n_cl) + cuentas de activo NUEVAS (orígenes, InversionesSade).
  · Sinceramiento: regla determinística por naturaleza saca del ingreso los traspasos/retiros/aportes.
  · Dimensiones analíticas + tags (socio / propiedad / offshore / por-cuenta-de).
  · Activos al balance a costo + participación → REPORTE DE PATRIMONIO v1.
  ENTREGABLE: contabilidad histórica honesta y estructurada en Odoo, que las contadoras pueden evaluar.

FASE 2 — Reportería operativa encima
  · Conciliación de tarjetas de crédito (reusar la máquina ya construida).
  · Dashboards + reportes (gastos, cashflow, patrimonio).

FASE 3 — Módulo de análisis de inversiones  (cierra el círculo)
  · Valuación de orígenes (Leo/Tauro/Sade/JB) contra posición del custodio.
  · Reconocer ganancia/pérdida no registrada (separar capital vs resultado, método IAS 21).
  · Patrimonio a valor de mercado (revalúa los activos de la Fase 1).
```

**Fuera de alcance (por ahora):**
- La contabilidad de **Molco** (fundo/campo familiar) — entra más adelante como 3ª entidad (EAG · FFCC · Molco).
  Hoy los traspasos a Molco se tratan como **gasto** (se consume; no se capitaliza).
- **Depreciación** de yate/avión/casas — no aplica (uso personal); se revalúa a mercado cuando hay tasación.
- Corregir Laudus. Laudus no se toca; Odoo carga desde el espejo.

## 5. La decisión que queda en manos de las contadoras (no nos bloquea)

Una vez cargada la historia corregida en Odoo, las contadoras eligen el modo de operación **ongoing**:

| Opción | Qué implica | Para nosotros |
|---|---|---|
| **A — Siguen en Laudus** | Ellas trabajan en Laudus; nosotros importamos y corregimos hacia Odoo | Odoo = espejo corregido downstream → hace falta un **pipeline repetible** Laudus→Odoo |
| **B — Trabajan en Odoo** | Adoptan la estructura mejorada y tipean directo en Odoo | Odoo = fuente de registro → el import es una **migración de una sola vez** |

**Clave: la Fase 1 es idéntica en las dos.** Cargar y corregir toda la historia es el mismo trabajo, y es
justamente lo que les da la base para decidir. Solo cambia lo de *arriba* (pipeline repetible vs migración
única), y eso lo resuelve el diseño técnico, no bloquea el arranque.

## 6. Stakeholders

- **Ary** — dueño del proyecto; piensa en doble entrada; decide arquitectura y prioridades.
- **Contadoras del family office** — usuarias; deciden §5; responden las preguntas contables abiertas (§9).
- **La familia (AAG · EAG · DAG · rama AZBA · FGK)** — consumidores del reporte de patrimonio y de retiros.
- **Julius Baer (custodio)** — fuente de la valuación offshore para la Fase 3.

## 7. El reporte de patrimonio — la zanahoria temprana

Hoy la familia **no puede responder "¿cuánto valemos?"** desde Laudus: las inversiones, el yate, el avión y las
casas no están en el balance. La Fase 1 los pone ahí (a costo, con participación por socio) y produce un
**reporte de patrimonio v1** — tangible, visible, y que ninguna herramienta actual entrega. Es el win que hace
tocable todo el proyecto antes de llegar a la valuación fina (Fase 3). Recomiendo priorizarlo dentro de la Fase 1.

## 8. Riesgos y supuestos

- **La analítica hereda los huecos de Laudus.** Odoo hace la reportería reproducible y más rica, pero no inventa
  el valor de mercado de las inversiones ni capitaliza el yate/avión. Eso es data (Fase 3), no herramienta.
- **Saldos de origen provisionales.** Tras el sinceramiento, los activos de origen quedan negativos/raros. Es
  **esperado y conservador** — se valúan en Fase 3. No es un error de la regla.
- **Supuesto documentado (Indumotora):** los 25,3B de "Retiros Indumotora" se dejan como ingreso (dividendo) sin
  consolidar Indumotora. Revisable si algún día se consolida.
- **La decisión §5 no está tomada** — pero no bloquea la Fase 1. Se explicita como pregunta viva del proyecto.

## 9. Preguntas abiertas (para las contadoras / terceros)

- **AZBA:** los −2.490M a favor de la rama AZBA (5 cuentas corriente), ¿se liquidan en cash o quedan como reparto
  de patrimonio? (Pasivo real del fondo mientras tanto.)
- **Misc JB:** el descuento del custodio (Leo −1,9M / Tauro −6,4M), ¿qué es — préstamo Lombard, posición fuera?
- **Rendiciones del capitán del yate:** ¿viven en un sistema aparte (Fraser)? ¿Se traen a Odoo?
- **Trade-in de autos (P-2):** ¿Laudus refleja la cuenta por pagar transitoria con Indumotora, o solo el neto?
- **Barrido pendiente (nuestro):** buscar más "aportes de capital disfrazados de ingreso negativo" tipo Sade.

## 10. Resumen de una línea

> Cargar toda la historia de Laudus en Odoo — corregida (P&L sincerado), estructurada (plan Laudus puro +
> analítica) y con el patrimonio por fin visible — para que la familia vea la verdad y las contadoras decidan si
> migran. Reportería y valuación de inversiones vienen encima, por fases.
