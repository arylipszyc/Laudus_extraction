# Mapa de normalización — plan de cuentas Laudus → estructura ideal Odoo

**Autora:** Valentina · **Fecha:** 2026-07-23 · **Alimenta:** Epic E1 (import). Anexo del SPEC y del brief.
**Estado:** DISEÑO para revisión de Ary + sanity-check de las contadoras en los clusters marcados 🟡.

---

## 0. El principio

Laudus mezcla dos cosas que Odoo separa:

> **La CUENTA = la naturaleza del movimiento** (qué tipo de gasto/activo es).
> **La contraparte / objeto / propiedad / persona = una DIMENSIÓN** (analítica o partner).

Laudus, como no tiene capa analítica usable, crea **una cuenta por cada combinación** → explota el plan
(569 cuentas). Odoo levanta esas dimensiones y deja el plan limpio.

## 1. El hallazgo que hace esto casi automático

**Laudus YA tiene las dimensiones adentro — en `categoria3` y en el prefijo del nombre.** No hay que
adivinarlas: se leen de metadata que ya existe.

- **`categoria3` está poblada al 99%** (364/365 cuentas de gasto).
- En **JAB**, `categoria3` = **la propiedad/objeto**: `MANTENCION VIA GRIS`, `MANTENCION MOLCO`,
  `MANTENCION REÑACA`, `MANTENCION YATE KEIKI KAI`, `AVION CC-N225AW`, `DEPARTAMENTO MIAMI`, `CANCHA DE GOLF`…
  → 53 valores distintos.
- El **socio** está en el **prefijo del nombre**: `AAG - Familia Regalos`, `EAG - Impuesto Renta`, `FGK - Celular`.
- En **EAG/FFCC**, `categoria3` = **área/centro**: `OFICINA`, `GERENCIA`, `Cuentas Básicas`, `Vehículos`, `Salud`…

**Ejemplo canónico (tu caso de los aviones/agua):**

| Cuenta Laudus (hoy) | code | cat3 | → Cuenta Odoo | → Analítica |
|---|---|---|---|---|
| Agua | 811006 | MANTENCION VIA GRIS | `Servicios Básicos:Agua` | propiedad = Vía Gris |
| Agua | 813006 | MANTENCION REÑACA | `Servicios Básicos:Agua` | propiedad = Reñaca |
| Agua | 815006 | MANTENCION MOLCO | `Servicios Básicos:Agua` | propiedad = Molco |

Tres cuentas Laudus → **una** cuenta Odoo + la propiedad como dimensión. Y "todo el gasto de Molco" (hoy
= sumar 42 cuentas a mano) sale nativo.

## 2. Las dimensiones destino (alineadas con el SPEC §5)

| Dimensión | Mecanismo Odoo | Se deriva de | Tipo |
|---|---|---|---|
| **propiedad / objeto** | Cuenta analítica | `categoria3` de JAB (casas, yates, aviones, Miami, golf) | Disperso |
| **socio** | **Partner (contacto)** | Prefijo del nombre (AAG/EAG/DAG/FGK) + cuentas 115xxx | Partición (en 115xxx) |
| **beneficiario** | Cuenta analítica + **partner** | Cuenta dedicada + **glosa** (persona nombrada: Raquel, Deutsch, Gloria) | Disperso |
| **área / centro** | Cuenta analítica | `categoria3` de EAG/FFCC (Oficina, Gerencia, Vehículos, Salud…) | Disperso |
| **offshore** | Cuenta analítica | cuentas 111012/113021 + glosa (Leo, Tauro, JB, Pictet) | Disperso |
| **por cuenta de** | Cuenta analítica | ControlYLiquidación + PAT 0858 | Disperso |

> **Personas = partner, no analítica.** Para socios/deudores/beneficiarios de donación, el mecanismo correcto
> es **partner (res.partner)**, no tag analítico (los analíticos de Odoo son de P&L; el partner ledger da el
> saldo por persona nativo, incluso en cuentas de balance). Resuelve socios (115xxx), Johnny Guerra y los
> destinatarios de donaciones con un solo mecanismo.

## 3. Reglas de colapso por cluster

🟢 = auto-derivable de metadata (alta confianza) · 🟡 = necesita sanity-check de las contadoras

| # | Cluster Laudus | Nº ctas | Regla → Odoo | Conf. |
|---|---|---|---|---|
| 1 | **Mantención casas** (Agua/Luz/Gas/Contribuciones/… × propiedad) | 97 (JAB) | Cuenta = tipo de gasto · analítica **propiedad** = cat3 | 🟢 |
| 2 | **Yates** (Keiki Kai / Destiny / Alfín II) | ~15 | Cuenta `Yates:<tipo>` · analítica **objeto** = cat3 (yate) | 🟢 |
| 3 | **Aviones** (N225AW / N266WW / AJK + generales) | ~18 | Cuenta `Aviones:<tipo>` · analítica **objeto** = cat3 (avión) | 🟢 |
| 4 | **Gastos personales por socio** (Regalos, Impuesto Renta, FGK-*) | ~90 | Cuenta = tipo · **partner/socio** = prefijo del nombre | 🟢 |
| 5 | **Cuentas corriente socios** (Retiros AAG/EAG/DAG/AZBA + apellidos) | ~11 (115xxx) | **1 cuenta** `Cuentas corriente socios` · **partner** = socio | 🟢 |
| 6 | **Préstamos / deudores one-off** (Johnny Guerra, Deudores Varios 2.175M) | varios | **1 cuenta** `Préstamos/Deudores a terceros` · **partner** = persona | ✅ Ary |
| 7 | **Donaciones / clubes / membresías** (Coanil, CIS, Club Naval…) | ~30 | Cuentas `Donaciones` / `Cuotas y Membresías` · **partner** = beneficiario | ✅ Ary |
| 7b | **Regalos** (por socio + por ocasión) | ~12 | **1 cuenta** `Regalos` · dimensión **socio** + **ocasión** | ✅ Ary |
| 7c | **Ayuda a personas** (Deutsch, Gloria) | ~4 | Cuenta `Asignaciones a personas` (**gasto, no por cobrar**) · **partner** + **beneficiario** | ✅ Ary |
| 7d | **Raquel Ventura** (cruzada: cta directa 625M + TC 225M + esparcida por glosa + transferencias) | ~2 + N | Cuenta = **naturaleza** · dimensión **beneficiario:Raquel** (auto por glosa) · transferencias a su cuenta = **gasto discrecional** (no por cobrar). Ver §3.1 | ✅ Ary |
| 8 | **Caja $ / US$ repetida por hija** | ~8 | **1 cuenta** `Caja` (× moneda) · **entidad** = compañía/hija | 🟢 |
| 9 | **Bancos** (cada cuenta bancaria) | ~20 | **Se mantiene 1:1** — una cuenta bancaria ES una cuenta legítima | ✋ keep |
| 10 | **Orígenes de inversión** (Tecnión, Nuevo Ciclo, Sade, Leo, Tauro…) | ~15 | Per SPEC §1.2 (activos de origen) · analítica **offshore** | 🟢 |
| 11 | **Cuentas de naturaleza real** (Sueldos, Dividendos, categorías de gasto genuinas) | resto | **Se mantiene 1:1** — es estructura de verdad | ✋ keep |

### 3.1 Caso Raquel Ventura (esposa de EAG) — motiva la dimensión `beneficiario`

Su gasto está **esparcido** (no es de un tipo): cuenta directa `SraRaquelVentura` 625M + TC 225M + ~60M
identificables en cuentas genéricas (Casa, Vehículos, Salud, Regalos) **solo por la glosa "raquel"** + se paga
desde varios bancos (BCI/Santander/Edwards, −1.140M = financiamiento, NO gasto extra) + toca otras entidades.

**Tratamiento:** la cuenta sigue siendo la **naturaleza** (Salud, Vehículos…); se aplica dimensión
**`beneficiario:Raquel`** a toda línea suya → el P&L filtrado por Raquel muestra **todos sus gastos agrupados**.
Auto-taggeo: cuentas dedicadas + **glosa-match "raquel"**. Las **transferencias a su cuenta personal = gasto
discrecional** (fondos para su uso, **NO por cobrar**) → cuenta de asignación + `beneficiario:Raquel`. **Raquel es
puramente P&L — sin posición de balance.** El **partner** es el "quién" (agrupar), sobre cuentas de gasto, no una
por-cobrar. **Honestidad:** lo que las contadoras no ven no se captura hasta que aparezca. **Revisar:** el asiento
de 238M en `ImpuestoRenta` con su nombre (¿su renta o traspaso?). El −1.140M de bancos es el financiamiento (de
dónde sale) → **no doble-contar** contra el gasto.

## 4. Magnitud del cambio

- **569 cuentas Laudus** hoy → plan Odoo estimado **~150-200 cuentas** (depende de cuán agresivo sea el colapso
  de los clusters 🟡). El grueso de la reducción: **gastos 365 → ~90-120** al levantar propiedad/socio/objeto
  como dimensiones.
- **Aclaración honesta:** el valor NO es principalmente "menos cuentas" — es que **las 53 propiedades/áreas y los
  socios pasan a ser cortes nativos**. Hoy "gasto de Molco" o "todo lo de EAG" se arma a mano; mañana es un filtro.
  El plan más limpio es la consecuencia, no el objetivo.

## 5. Cómo se preserva la paridad (la disciplina del proyecto)

Cada línea importada lleva **`x_laudus_account_code`** (+ `x_laudus_je_id`, `x_laudus_entity`) — campos custom en
`account.move.line`, equivalentes 1:1 a la metadata `code`/`je_num`/`entity` que hoy vive en Beancount.

> **La paridad se verifica agrupando por `x_laudus_account_code`**: Σ(líneas con code=X) debe igualar el saldo de
> la cuenta Laudus X. Independiente de a qué cuenta Odoo o dimensión mapeó. Así el plan queda limpio **y** el
> cuadre peso por peso se mantiene. El colapso nunca borra la trazabilidad al origen.

## 6. Decisiones — CERRADAS con Ary (2026-07-23)

- **Profundidad del colapso: AGRESIVO por default.** Se colapsa a la naturaleza en todos los clusters; los
  dudosos se resolvieron uno por uno (abajo).
- **Estructura de compañías: 2 compañías (EAG + RUT2), FFCC y JAB/FGK = dimensión entidad dentro de RUT2.**
  Razón: JAB/FGK no es entidad autónoma (FFCC costea sus gastos; sin pasivo/patrimonio propio). Compañía aparte
  forzaría inter-company en cada gasto de FGK. La vista de 3 (EAG/FFCC/JAB) se logra como **reporte por
  dimensión**. EAG y RUT2 sí son compañías (RUT/libros distintos).
- **Dudosos resueltos (aggressive + partner):** donaciones/clubes → `Donaciones`/`Cuotas y Membresías` + partner;
  ayuda a personas → `Asignaciones a personas` + partner + beneficiario; deudores/préstamos → `Préstamos/Deudores
  a terceros` + partner; regalos → `Regalos` + dimensión socio/ocasión; **Raquel** → beneficiario dimension (§3.1).

**Queda para sanity-check de las contadoras (no bloquea la tabla de mapeo):**
- Confirmar que colapsar donaciones/clubes/deudores a partner no rompe ningún reporte que ellas necesiten por
  cuenta-institución.
- Revisar el asiento de 238M en `ImpuestoRenta` con nombre de Raquel (§3.1).

## 7. Próximo paso

Con el marco y las decisiones del §6 resueltos, produzco la **tabla de mapeo completa** (las 569 cuentas → cuenta
Odoo + dimensiones + partner), que es el insumo directo del importador de E1. Es en su mayoría **determinística**
(se genera de name + cat2 + cat3 + prefijo), con una lista corta de casos que las contadoras confirman.

## 8. Resumen de una línea

> Laudus explotó el plan en 569 cuentas porque metió las dimensiones (propiedad, socio, objeto) adentro del nombre
> de la cuenta. Esas dimensiones ya están en `categoria3` + el prefijo del nombre, así que el colapso a un plan
> limpio (~150-200 cuentas) + analíticas + partners es **casi determinístico** — y la paridad se preserva
> estampando el código Laudus en cada línea.
