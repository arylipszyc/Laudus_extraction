# PROMPT — Guía interactiva de pruebas finales (materialización del desglose TC)

> ✅ **ESTADO 2026-07-06: la materialización se COMPLETÓ** — todas las tarjetas cuadradas al peso
> (1027 CLP/USD, 8996 CLP/USD, 0858 CLP; la 0858 USD fue **retirada** en `b93c102`, ver abajo).
> Esta guía queda como referencia histórica / para re-corridas. Si la re-usás, ojo con las
> correcciones marcadas ⚠️ (code-review 2026-07-06): la versión original tenía instrucciones
> que hoy corrompen datos o ya no aplican.

> Pegá TODO lo de abajo en una ventana nueva. Está pensado para que el asistente te vaya guiando paso a
> paso por la materialización real del desglose de tarjetas en la app deployada.

---

Sos mi copiloto para las **pruebas finales de materialización** del desglose de tarjetas de crédito del
family-office-eag. Guiame **interactivamente, un paso a la vez**: decime qué hacer, espero que te reporte
el resultado, lo verificás conmigo, y recién ahí seguimos. No avances sin mi confirmación de cada paso.

Repo: `c:\dev\bmad-workspace-new\family-office-eag`. Sos contable-consciente: para validar el cuadre podés
invocar la skill `agent-contadora` (Valentina, que diseñó esto). Contexto completo en:
- `_bmad-output/planning-artifacts/valentina-veredicto-desglose-tc-14cartolas-2026-06-29.md`
- `_bmad/memory/agent-contadora/sessions/2026-06-29.md` (bitácora con el estado y las decisiones)

## Qué estamos probando

El desglose TC ya está construido, revisado y **pusheado a prod** (main hasta commit `d52480e`; Render
redeploya solo). Todo el flujo se validó end-to-end en un smoke por navegador (Chrome real, sandbox): una
cartola Santander USD que antes bloqueaba posteó bien con FX del dólar real (BCCh). **HOY es OPERACIÓN, no
código:** subir las cartolas reales por la app de prod y confirmar que cuadran.

⚠️ **Esto es PROD.** El importer postea al ledger real y commitea a main. Es real, no un sandbox. Por eso:
piloto de 1 tarjeta primero, verificar el cuadre, y recién después el resto. Re-importar la misma cartola
es idempotente (sobrescribe el mismo archivo por slug), así que un reintento no duplica — ⚠️ **PERO
resetea las categorizaciones de esa cartola** (sobrescribe el archivo completo): si el contador ya
categorizó, un re-import le borra el trabajo en silencio y dispara la alarma anti-duplicado. No
re-importar cartolas ya categorizadas salvo que sea a propósito (y avisando).

## Paso 0 — Confirmar que el deploy está live

⚠️ **Corrección 2026-07-06:** el mínimo real es **`9f0c2f3` o posterior** (fix "categorizar preserva la
pata de deuda"), NO `d52480e`. Con un deploy `d52480e`-only, el Paso 3 (categorizar) **destruye la pata
`TC:Real`** del pasivo — exactamente el bug del 2026-07-02 (`valentina-bug-categorizacion-destruye-tc-real`).

Antes de nada, confirmá que Render terminó de deployar el commit `9f0c2f3` (o posterior). Si tenés acceso
a la API de Render (`RENDER_API_KEY` en env, servicio backend `srv-d7dk4hv41pts73a35aqg`), chequealo; si no,
preguntame la URL de la app de prod y verificá que carga. **No sigas hasta confirmar que prod tiene el
código nuevo** (si no, el upload de TC rechaza por `MISSING_LAST4` o el matcher no usa BCCh).

## Paso 1 — Piloto: BCI Visa Infinity (la tarjeta que cuadra al peso)

En la app de prod, andá a **"Cargar Cartola" (`/upload`)**. Vamos a subir la BCI Visa Infinity CLP en orden
cronológico (la apertura se emite en la más vieja). Las cartolas están en `samples/`, ya renombradas
`banco-tarjeta+4dígitos-moneda-YYYYMM.pdf`:

1. `samples/bci-visainfinity1027-clp-202602.pdf` (febrero)
2. `samples/bci-visainfinity1027-clp-202603.pdf` (marzo)
3. `samples/bci-visainfinity1027-clp-202604.pdf` (abril)

Por cada una, guiame: elegir la cuenta **"T/C: 1027 - Visa Infinity - $"** en el dropdown → subir el PDF →
esperar la extracción (Gemini, ~30-45s) → revisar que el balance **cuadra (discrepancia $0)** → **Confirmar
validación** → debe salir **"✅ Cartola importada"**.

**Cuadre esperado (verificalo conmigo tras las 3):** el pasivo `Liabilities:EAG:TC:Real:Tc1027VisaInfinity`
tiene que cerrar en **−3.219.948** (= −closing de abril; la cadena feb→mar→abr es contigua). Decime cómo
verlo — dashboard **Activos/Pasivos** o una query del ledger. Si da −3.219.948, el piloto pasó.

## Paso 2 — El resto de las tarjetas (tras validar el piloto)

Mismo flujo, **corridas contiguas por tarjeta** (subí siempre la más vieja primero). Inventario en `samples/`:

| Tarjeta | Cuenta en el dropdown | Cartolas (meses) | Esperado |
|---|---|---|---|
| Visa Infinity 1027 USD | T/C: 1027 - Visa Infinity - US$ | usd 02, 03, 04 | cuadra (glosa limpia BCI) |
| Mastercard 8996 CLP | T/C: 8996 - Mastercard Lanpass - $ | clp 02, 03, 04 | pasivo cierra **−4.448.873** (abr) |
| Mastercard 8996 USD | T/C: 8996 - Mastercard Lanpass - US$ | usd 02, 03, 04, 05 | **marzo BLOQUEA** (revolving, ok); resto postea con BCCh |
| Latanpass 0858 CLP | T/C: 0858 - Visa Latanpass - $ | clp 02, 03, 04, 05 | cuadra (contiguo) |
| ~~Latanpass 0858 USD~~ | ~~T/C: 0858 - Visa Latanpass - US$~~ | ~~usd 02, 03~~ | ⚠️ **NO SUBIR** — retirada en `b93c102` ("números basura + apertura fuera de orden"; pago consolidado Santander). Espera la story del matcher-por-monto. |

## Paso 3 — Categorizar

Todas las compras caen a **Suspense** (pendientes). Andá a **"Categorías Pendientes" (`/categorizacion`)**:
badge de color por ítem (🟢 verde = confiado / 🟡 amarillo = revisá / 🔴 rojo = decidí vos), **rojos arriba**.
El contador **confirma SIEMPRE** — nada se auto-confirma. Guiame a categorizar las de mayor monto primero.

## Gotchas que vas a ver (todos esperados, NO son bugs)

- **Warnings `DUPLICATE_LINE`** en la extracción: Gemini a veces marca líneas repetidas. Si el balance
  igual cuadra ($0), procedé; son para revisión, no bloquean.
- **Mastercard 8996 USD marzo BLOQUEA**: su saldo rodó a abril (revolving), no tuvo pago propio. Correcto.
- **`avance` → Caja** (no gasto), **impuesto/comisión → GastosBancarios**: así debe ser (§10.1).
- Si una USD Santander **bloquea inesperadamente**: es que el matcher no encontró el pago consolidado en el
  dólar BCCh de ese mes → avisame, lo miramos (puede faltar un mes de BCCh en `ledger/_meta/fx-bcch-eom.jsonl`).
- **BCCh de mayo USD**: `fx-bcch-eom.jsonl` termina en 2026-05 y el pago que salda mayo es de junio → el
  gate usa el **último BCCh disponible** (fallback por diseño, `fx_calculator._anchor_for`), no la tasa
  exacta de junio. Esperado, no bug.

## Tu rol

Guiame paso a paso, esperá mi reporte de cada resultado, y validá el cuadre con los números esperados. Si
algo no cuadra o bloquea distinto a lo previsto, pará y diagnostiquemos juntos antes de seguir. Al final,
resumime qué se materializó y qué quedó pendiente (bloqueadas + categorización).
