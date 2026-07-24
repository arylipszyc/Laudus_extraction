# Auditoría: ingresos de inversiones mal contabilizados (EAG)

**Fecha:** 2026-06-20
**Autora:** Valentina (asesora de finanzas)
**Alcance:** EAG. Las 4 hijas (Jocelyn, Jeannette, Johanna, Jael) quedan fuera — no está confirmado si sus retiros salen de fondos propios o de cuentas separadas.
**Fuente:** ledger Beancount (`ledger/imports/laudus/*.beancount`), espejo fiel de Laudus 2021–2025.

---

## Resumen para el contador

Los retiros/rescates de inversiones **no separan capital de ganancia**. Conviven dos errores opuestos,
y ninguno usa las cuentas de resultado de inversión (`Income:EAG:Resultado*` 510xxx → **0 asientos** en
todo el período).

- **Error A** — el retiro se carga **100% a una cuenta de ingreso** y **no baja el activo** → infla P&L
  e infla el balance (el activo nunca se reduce).
- **Error B** — el retiro se carga **100% contra el activo** sin reconocer ganancia → el activo queda en
  **saldo negativo** (imposible) y subdeclara ingreso.

**Importante:** esto **no lo detecta** la validación de paridad contra el contador, porque Beancount
copia fielmente a Laudus y el error está dentro de Laudus (ambos lados tienen el mismo error). Solo se
pesca reconciliando contra la **posición real del custodio** (cartola del fondo/banco).

> Nota: los dividendos de **Indumotora** (≈25.269M registrados como ingreso) están **correctos** — son
> reparto de utilidades de una sociedad operativa, no retiro de capital. No forman parte de los errores.

---

## Reconciliación por vehículo

| Vehículo | Tipo | Aportes (subió activo) | Retiro vía activo | Retiro vía **ingreso** | Saldo activo hoy | Problema |
|---|---|---:|---:|---:|---:|---|
| Tecnion | inversión | 2.510M | −3.627M | **12.204M** | **−1.117M** | activo negativo + 12.204M a ingreso |
| Nuevo Ciclo | inversión | 2.273M | 0 | **5.963M** | 2.273M | activo nunca bajó pese a cobrar 5.963M |
| MBI | inversión | 28.233M | 0 | **4.767M** | 28.233M | activo nunca bajó pese a rescatar 4.767M |
| JB | cta. inversión | 1.221M | −785M | **3.259M** | 436M | 3.259M de rescate a ingreso |
| BCI FM | fondos mutuos | 26.137M | −11.496M | 0 | 14.641M | Error B → 2 sub-fondos negativos |

(montos en CLP)

### Error A — retiro de inversión cargado como ingreso (debió mover el activo)

| Vehículo | Monto a ingreso |
|---|---:|
| Tecnion | 12.204M |
| Nuevo Ciclo | 5.963M |
| MBI | 4.767M |
| JB | 3.259M |
| **Total** | **≈ 26.193M CLP** |

### Error B — activos en saldo negativo (imposible)

| Cuenta | Saldo |
|---|---:|
| `InvTecnionLimitada-113018` | −3.353M |
| `FmBciCompetitivoSerieClass0-113004` | −202M |
| `FmBciCompetitivoSerieAp0-113002` | −26M |

---

## El caso más limpio (para mostrar el patrón)

**Nuevo Ciclo:** se aportaron 2.273M. Se cobraron 5.963M en asientos rotulados literalmente
**"Nuevo Ciclo: Devolución de préstamos"**. El activo `InversionesNuevoCiclo-115016` **sigue mostrando
los 2.273M completos**. Una devolución de préstamo nunca es ingreso: baja la cuenta por cobrar. Acá el
préstamo se pagó (y sobre-pagó) y la cuenta por cobrar nunca se redujo → activo inflado e ingreso
inflado por el componente de capital.

---

## Qué se necesita para corregir

Para cada vehículo hace falta la **posición real al día de hoy** según el custodio (cartola del fondo /
banco). Con eso:

1. Se ajusta el activo a su valor real.
2. La diferencia se reclasifica: la parte de **capital** sale de la cuenta de ingreso; la parte de
   **ganancia** va a `Income:EAG:Resultado*` (las cuentas correctas, hoy vacías).

Mientras no haya saldos del custodio confirmados, **no se debe corregir** — corregir con un número
inventado es peor que dejarlo marcado.

---

## Pendiente

- [ ] Contador confirma saldo real de cada vehículo (Tecnion, Nuevo Ciclo, MBI, JB, fondos BCI).
- [ ] Una vez confirmados, diseñar los asientos de corrección (estilo TC: solo asientos contables
      estándar, sin tocar el motor/importer).
- [ ] (Opcional) Auditar las 4 hijas si se aclara el origen de sus retiros.

**Método reproducible:** `_forense_inversiones.py` y `_forense_recon_vehiculo.py` (misma carpeta).
