# Lista cerrada de partners (res.partner) — seed para E1.4

**Autora:** Valentina · **Fecha:** 2026-07-23 · **Alimenta:** Story E1.4 (transformador de dimensiones + partners).
**Estado:** CERRADA para escribir ACs. Precondición del mapeo Laudus→`res.partner`.

**Fuentes:** `valentina-tabla-mapeo-odoo-2026-07-23.csv` (columna `partner` + flags `partner-benef` / `partner-por-deudor`),
`valentina-tabla-alias-2026-07-23.yaml` (socios/beneficiarios ya resueltos), `valentina-mapa-normalizacion-odoo-2026-07-23.md` §2/§3/§3.1.

**Regla de deduplicación aplicada:** una misma persona/institución que aparece bajo varias cuentas Laudus (variante de nombre,
sub-cuenta "Autos", o repetida en donación + membresía, o en EAG + JAB) colapsa a **un** partner. Las sub-cuentas se listan en
"Cuenta(s) Laudus". Los dudosos se incluyen igual, marcados `⚠ revisar con contadoras`.

---

## Categoría 1 — Socios / cuentas corriente (cluster 5)

**La PARTICIÓN que debe cuadrar.** Las cuentas corriente de socios viven **solo en FFCC (compañía RUT2)**, cuentas `115021–115041`.
No hay cuenta corriente de socio en la compañía EAG. Odoo destino = **una** cuenta `Cuentas corriente socios` (receivable) + partner.
Σ(líneas por partner) debe igualar el saldo de la 115xxx original (paridad `x_laudus_account_code`).

| Partner canónico | Cuenta(s) Laudus (115xxx / prefijo) | Saldo Laudus (CLP) | Odoo destino | Partición (cuadra) |
|---|---|---|---|---|
| **AAG** (Alfredo Avayú) | 115021 Retiros AAG | −4.438.135.788 | Cuentas corriente socios | ✅ partición |
| **EAG** (Eduardo Avayú) | 115023 Retiros EAG | −3.587.647.995 | Cuentas corriente socios | ✅ partición |
| **SAG** | 115025 Retiros SAG | +260.889.862 | Cuentas corriente socios | ✅ partición |
| **DAG** (Daniel Avayú) | 115027 Retiros DAG **+ 115028 Cta Cte DAG - Autos** | −3.362.663.937 | Cuentas corriente socios | ✅ partición (colapsa "Autos") |
| **AZBA** | 115029 Retiros AZBA | −493.043.375 | Cuentas corriente socios | ✅ partición (rama) |
| **José Alazraki** | 115031 | −482.345.420 | Cuentas corriente socios | ✅ partición (rama AZBA) |
| **Denise Zeldis** | 115033 **+ 115034 Denise Zeldis - Autos** | −485.461.560 | Cuentas corriente socios | ✅ partición (colapsa "Autos", rama AZBA) |
| **Michelle Zeldis** | 115035 | −494.335.026 | Cuentas corriente socios | ✅ partición (rama AZBA) |
| **Ariel Borzutzky** | 115037 | −534.603.111 | Cuentas corriente socios | ✅ partición (rama AZBA) |
| **Israel** | 115041 | +4.639.535 | Cuentas corriente socios | ✅ partición — ⚠ **revisar**: alias marca "israel" por glosa como DUDOSO (país/nombre de pila). La cuenta 115041 SÍ existe → identificar por CUENTA, nunca por glosa. Confirmar con contadoras que es el apellido de la rama AZBA. |
| **Otros hijos** (bucket) | 115039 Otros Retiros Hijos | 0 | Cuentas corriente socios | ⚠ **revisar**: cuenta-bolsa sin persona nombrada; saldo 0 hoy. Mantener como partner genérico o desglosar si aparece movimiento. |
| **FGK** (JAB) | *sin 115xxx* — prefijo `FGK -` en 873xxx (dimensión socio) | (gastos, no cta cte) | dimensión `socio` sobre cuentas de gasto | ❌ **NO partición** — socio disperso por prefijo, no tiene cuenta corriente propia. Es partner-socio pero se aplica como dimensión sobre gasto, no cuadra un saldo 115xxx. |

**Total categoría 1: 12 partners** (11 con partición 115xxx + FGK disperso). Dudosos: Israel, Otros hijos.

> Nota: AAG/EAG/DAG/SAG también aparecen como **prefijo `socio`** en gastos personales por socio (cluster 4). Mismo partner —
> no crear duplicado. EAG-socio (la persona Eduardo Avayú) ≠ compañía EAG (el RUT/libro).

---

## Categoría 2 — Deudores / préstamos a terceros (cluster 6, flag `partner-por-deudor`)

Odoo destino = **una** cuenta `Préstamos/Deudores a terceros` (receivable) + partner.

| Partner canónico | Cuenta(s) Laudus | Saldo relevante | Naturaleza | Partición / disperso |
|---|---|---|---|---|
| **Jhonny Guerra** | Income 310045 Jhonny Guerra + 310047 Jhonny Guerra (hijo) + glosa "jhonny/guerra" (alias `JhonnyGuerra`) | 310045 = −8.200.000; 310047 = −400.000 | Deudor/handyman ("abono préstamo Jhonny") | Disperso por glosa. ⚠ **revisar**: ¿310047 "hijo" es un partner separado o el mismo grupo familiar? Grafía dominante "Jhonny" (NO "Johnny"). |
| **Deudores Varios** (bucket) | 115019 EAG (**2.175.295.625**) + 115019 FFCC + 613019 Jocelyn (5.664.366) + 613019 JAB (6.900.000) + 750017 Jeannette + 850001 Johanna + 950017 Jael | EAG 2.175M es material | Cuenta-bolsa de deudores sin nombrar | ⚠ **revisar**: NO es una persona única — es un catch-all. El saldo grande de EAG (2.175M) probablemente esconde préstamos nominables → desglosar por glosa para crear partners reales. Hoy = un partner genérico "Deudores Varios" por entidad. |

**Total categoría 2: 2 partners** (1 nombrado + 1 bucket). Ambos con caveat. Dudosos: los dos.

---

## Categoría 3 — Donaciones / clubes / membresías (cluster 7, flag `partner-benef`) — instituciones

Odoo destino = `Donaciones` o `Cuotas y Membresías` (expense) + partner = institución.

### 3a. Donaciones (cuenta `Donaciones`)

| Partner canónico | Cuenta(s) Laudus | Dedup |
|---|---|---|
| **Keren Hayesod** | EAG 430081 + JAB 878008 | ✅ colapsa EAG+JAB |
| **WIZO** | EAG 430083 + JAB 878009 | ✅ colapsa EAG+JAB |
| **Coronas de Caridad** | EAG 430089 | — |
| **Coanil** | JAB 878001 | — |
| **EZRA** | JAB 878003 | — |
| **Hogar de Ancianos** | JAB 878005 | — |
| **KKL** | JAB 878007 | — |
| **CREJ** | JAB 878011 | — |
| **CIS** | JAB 878013 | ⚠ **revisar**: ¿CIS = C.I. Santiago (879013) o C.I. Sefaradí (879011)? Son comunidades DISTINTAS. No fusionar sin confirmar. |
| **Hogar de Cristo** | JAB 878015 | — |
| **C. Jafetz y Jaim** | JAB 878017 | — |
| **Fundación Mar de Chile** | JAB 878019 **+ 879019** | ✅ colapsa donación + membresía (misma institución) |
| **Fundación FOBEJU** | JAB 878021 | — |
| **Donaciones (genérico)** (bucket) | EAG 430092 + FFCC 415055 + FFCC 437055 "Donaciones, Regalos" + JAB 878099 "Otras Instituciones" | ⚠ **revisar**: cuenta-bolsa sin institución nombrada. Mantener como partner genérico "Otras instituciones / Donaciones varias". FFCC 437055 mezcla donaciones+regalos. |

### 3b. Clubes / membresías (cuenta `Cuotas y Membresías`)

| Partner canónico | Cuenta Laudus | Dedup |
|---|---|---|
| **Club Naval Las Salinas** | JAB 879001 | — |
| **Club Naval de Valparaíso** | JAB 879003 | — |
| **Museo Naval, Patrimonio** | JAB 879005 | — |
| **Club de Golf La Dehesa** | JAB 879007 | — |
| **Club de Campo Granadilla** | JAB 879009 | — |
| **C.I. Sefaradí** | JAB 879011 | ⚠ ver CIS arriba |
| **C.I. Santiago** | JAB 879013 | ⚠ ver CIS arriba |

**Total categoría 3: 20 partners nombrados** (13 donaciones + 7 clubes) **+ 1 bucket genérico** = 21. Dudosos: CIS vs C.I. Santiago/Sefaradí (posible triple), bucket genérico.

---

## Categoría 4 — Beneficiarios de asignación (cluster 7c / 7d)

Odoo destino = `Asignaciones a personas` (**gasto, NO por cobrar**) + partner + dimensión beneficiario. Solo P&L, sin posición de balance (mapa §3.1).

| Partner canónico | Cuenta(s) Laudus | Saldo (CLP) | Nota |
|---|---|---|---|
| **Raquel Ventura** | 430021 Sra. Raquel Ventura (Asignaciones 625.337.453) **+ 430019 T/C Raquel Ventura (225.018.418, va a Liabilities:TC)** + disperso por glosa "raquel" en Salud/Vehículos/Regalos | ~625M directa + 225M TC | Esposa de EAG. Todo "raquel" es ella (sin homónimos). Transferencias a su cuenta = gasto discrecional, no por cobrar. Auto-tag por glosa. La 430019 (TC) mapea a Liabilities pero el beneficiario sigue siendo Raquel. |
| **Jacqueline Deutsch** | 430023 Sra. Jacqueline Deutsch | 372.499.008 | **PERSONA DISTINTA de Patricia.** Exigir nombre completo "jacqueline deutsch"; NUNCA matchear "deutsch" solo (hay varios Deutsch en la data). |
| **Patricia Deutsch** | 430024 Sra. Patricia Deutsch | 22.100.000 | **PERSONA DISTINTA de Jacqueline.** Exigir nombre completo "patricia deutsch". |
| **Gloria Jiménez** | EAG 430033 Gloria Jimenez (11.000.000) + FFCC 431002 + FFCC 433002 (Gloria Jimenez Bustos) | ~11M+ | ✅ colapsa "Gloria Jimenez" = "Gloria Jimenez Bustos". Exigir nombre completo: hay otras Glorias (Amoyao/Oporto/Palma) que son personas distintas. |

**Total categoría 4: 4 partners.** Sin dudosos de identidad (Jacqueline ≠ Patricia ya separadas).

---

## Resumen de conteo

| Categoría | Partners | De los cuales dudosos (`⚠ revisar`) |
|---|---|---|
| 1. Socios / cuentas corriente | 12 (11 partición + FGK disperso) | 2 (Israel, Otros hijos) |
| 2. Deudores / préstamos | 2 (Jhonny Guerra + bucket Deudores Varios) | 2 |
| 3. Donaciones / clubes / membresías | 21 (20 nombradas + 1 bucket) | 2 (CIS↔C.I. Santiago/Sefaradí, bucket genérico) |
| 4. Beneficiarios de asignación | 4 (Raquel, Jacqueline D., Patricia D., Gloria J.) | 0 |
| **TOTAL** | **39 partners** | **6 dudosos** |

## Reglas para los ACs de E1.4 (derivadas de esta lista)

1. **Socios (cat 1):** partner = valor de columna `partner` en 115xxx; colapsar sub-cuentas "Autos" al mismo partner; la suma por partner **debe** reconciliar el saldo de la 115xxx. FGK es socio-dimensión, no genera partición.
2. **Beneficiarios (cat 4) e identidades homónimas:** el mapeo por glosa exige **nombre completo** — nunca substring "deutsch", "gloria", "israel", "leo", "guerra" solo (ver `excluir_homonimos` en el YAML de alias). Jacqueline Deutsch y Patricia Deutsch son **dos `res.partner` separados**.
3. **Buckets genéricos** (Deudores Varios, Donaciones genérico/Otras Instituciones, Otros hijos): crear como partner placeholder por entidad; NO inventar una institución/persona. Marcar para desglose futuro.
4. **Dedup cross-entidad:** Keren Hayesod, WIZO, Fundación Mar de Chile, Gloria Jiménez colapsan a un solo partner aunque aparezcan en EAG+JAB o en donación+membresía.
5. **CIS ⚠:** no fusionar CIS (878013) con C.I. Santiago (879013) ni C.I. Sefaradí (879011) hasta que las contadoras confirmen si son la misma comunidad — son tres cuentas distintas y las comunidades Sefaradí y de Santiago son entidades diferentes.
