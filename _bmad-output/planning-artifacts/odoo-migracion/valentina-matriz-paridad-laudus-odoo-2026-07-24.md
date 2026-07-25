# Matriz de paridad Laudus → Odoo — veredicto prueba #2 del spike

**Fecha:** 2026-07-24 · **Autora:** Valentina (con Ary + Moishe manejando Odoo en vivo)
**Contexto:** Spike de migración Laudus → Odoo Community. Este documento cierra la **prueba #2**
(¿la reportería/UI de Odoo le sirve a las contadoras?) con evidencia, no con fe.

---

## 1. El criterio de aceptación (definido por Ary)

> "Si Odoo puede darle a las contadoras, **como mínimo, lo mismo que hoy tienen en Laudus**,
> la prueba pasa 100%."

**Vara acordada:** las **3 superficies** que las contadoras tocan (maestros + registro + reportería),
asumiendo que eventualmente **operarían dentro de Odoo** (no solo espejo downstream).

## 2. Las 4 respuestas de Ary que fijaron la vara real

| # | Pregunta | Respuesta | Consecuencia |
|---|---|---|---|
| 1 | ¿Usan reportes formales de Laudus (balance clasificado, EERR)? | **No. Solo el workbook de gastos.** | El gap "Enterprise" (falta balance/EERR jerárquico en Community) es **irrelevante**. |
| 2 | ¿Trackean terceros con el maestro de contactos? | **No hay ni un contacto creado. Todo por cuenta.** | Odoo no necesita replicar maestro de terceros para dar paridad. |
| 3 | ¿El registro es manual o importado? | **100% manual. Nada se importa.** | El ingreso manual de asientos es **la superficie que decide la prueba**. |
| 4 | ¿Hacen SII / tributario (F29, libros) para estas entidades? | **No.** | Sin 4º bucket. Scope cerrado en 3. |

## 3. Matriz de paridad (verificada en vivo, Odoo 18 Community + OCA)

| Superficie | Laudus (hoy) | Odoo (verificado) | Veredicto |
|---|---|---|---|
| **REGISTRO manual** *(100% del trabajo)* | Teclean cada comprobante | Comprobante doble entrada: correlativo auto (`LAU1/2026/07/0001`), glosa, fecha, diario, líneas Cuenta/Débito/Crédito, **autocompleta por código Laudus** (411001 → "Sueldos, Ropa, Regalías"), cuadre forzado (Borrador→Registrar). Bonus: columna Distribución analítica + Contacto. | ✅ **Paridad + upside** |
| **MAESTROS — plan de cuentas** | Plan con códigos + Categoría 1/2/3 | Plan editable por grupo, **código Laudus preservado**, crear/editar cuenta, tipo, moneda, por empresa. | ✅ **Paridad** |
| **MAESTROS — terceros** | No usan (todo por cuenta) | No requiere replicar nada. | ✅ **N/A, sin brecha** |
| **REPORTERÍA — workbook de gastos** *(único entregable)* | Excel: gasto por cuenta agrupado por Categoría 2 / encabezado, por entidad, itemiza hijas | Trial Balance filtrado a gasto (411001→430008) reproduce **gasto por cuenta, itemizando hijas** (411=EAG · 413=hijas · 430=bancarios/TC); cuadra al peso vs fuente. **Encabezado = prefijo de código = `account.group` nativo Odoo** (subtotales = importar ~12 grupos, paso trivial). | ✅ **Paridad de sustancia** (subtotales por encabezado = 1 paso de config) |
| **REPORTERÍA — reportes formales Laudus** | No usan ninguno | — | ✅ **Gap Enterprise irrelevante** |
| **SII / tributario** | No hacen | — | ✅ **Fuera de scope** |

## 4. Evidencia dura

### Prueba #1 (cuadre del import) — PASS al peso
- Odoo EAG mayo (posted): **debe = haber = 638.744.739**, descuadre 0, 87 asientos / 253 patas.
- Diff **por cuenta** CSV-fuente vs Odoo: **0 en las 66 cuentas**.
- El asiento `draft` (id 217) es un comprobante **vacío** (0 líneas, $0), inofensivo, excluido de todo reporte.
- Cadena: CSV → Odoo = lossless (verificado hoy); CSV → Laudus → contador ya validado en Beancount.

### Prueba #2 (paridad de superficie) — capturas
- `docs/screenshots/plan-de-cuentas.png` — maestro plan de cuentas editable.
- `docs/screenshots/odoo-asiento-nuevo.png` + autocompletado 411001 — ingreso manual de comprobante.
- `docs/screenshots/eag-trial-balance-mayo.png` — balance de sumas y saldos completo.
- `docs/screenshots/eag-gastos-mayo.png` — **workbook de gastos reproducido** (411001→430008), gasto por cuenta.

### Totales de gasto EAG mayo (por encabezado = prefijo de código)
| Encabezado | Cuentas | Gasto |
|---|---|---|
| 411 (EAG) | 16 | 7.199.326 |
| 413 (hijas) | 29 | 136.203.633 |
| 430 (bancarios/TC) | 10 | 84.508.683 |
| **Total** | 55 | **227.911.642** |

## 5. Veredicto

**Prueba #2 = PASS.** Las dos superficies más difíciles (registro manual + maestros) pasan de forma
decisiva. La reportería reproduce el único entregable real (workbook de gastos) al peso. El fantasma
que preocupaba —falta de balance clasificado / EERR jerárquico en Community— **quedó irrelevante**
porque las contadoras no usan ningún reporte formal de Laudus.

**Prueba #3 (dev simple) = PASS colateral.** El módulo custom `spike_account_panel` (agrupa el plan de
cuentas por categoría vía campo stored + herencia de search view) ya está construido e instalado — un
módulo Python mínimo, evidencia de que desarrollar en Odoo es abordable.

## 6. Único trabajo pendiente para reportería "pixel-perfect" (no bloqueante)
- **Importar `laudus_group` como `account.group`** (por prefijo de código) → subtotales por encabezado
  automáticos en Trial Balance / Libro Mayor. Es config, no desarrollo. Ya anticipado en la tabla de mapeo.

## 7. Limitación honesta preservada
- Las cuentas **430xxx (TC)** entran como gasto lumpeado — es el problema estructural conocido de TC en
  Laudus (pasivo mal catalogado como gasto). Odoo muestra lo que Laudus muestra; la corrección TC es un
  tema de modelo de datos aparte, no de paridad de reportería. Ver MEMORY del sanctum.

## 8. Estado del spike tras esta sesión
- **Infra:** stack Odoo corre **local** (Docker Desktop), no en VPS (decisión 2026-07-24: el riesgo VPS es
  nulo y ortogonal; se valida local, el VPS es solo para producción). Base `familyoffice`, import completo.
- **Prueba #1:** PASS. **Prueba #2:** PASS. **Prueba #3:** PASS.
- **Conclusión del spike:** las 3 preguntas dan PASS → hay caso sólido para planificar la migración.
