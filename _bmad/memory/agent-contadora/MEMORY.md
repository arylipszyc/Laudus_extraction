# Memory

_Conocimiento curado de largo plazo. Vacío al nacer — crece a través de las sesiones._

_Este archivo es para insights destilados, no notas crudas. Captura la esencia: decisiones tomadas, ideas que valen la pena, patrones detectados, lecciones aprendidas._

_Mantén bajo 200 líneas. Las notas crudas van en `sessions/YYYY-MM-DD.md` (no aquí). Destila insights de los session logs en este archivo. Poda lo obsoleto. Cada token aquí se carga en cada sesión — que cada uno cuente._

## Contexto del Proyecto

**family-office-eag** = family office de EAG. La contabilidad ahora vive en **Beancount** (antes se
exportaba de Laudus a Google Sheets; ese flujo se reemplazó). El importer Laudus→Beancount deja
Beancount = espejo fiel de Laudus. Ledger en `ledger/` (main.beancount + imports/laudus/ +
imports/cartolas/). Pipeline de import en `pipeline/importers/` (Stories 9.x).

## Modelo de Datos — Estado Actual

**Problema conocido — Tarjetas de crédito (diagnóstico verificado, corrige el entendimiento previo):**
NO es que "las compras estén como gasto". Lo real:
- Las compras individuales **no se registran**. Solo se registra el **pago mensual** (Banco → TC).
- Las cuentas `Liabilities:EAG:TC:*` son pasivo en el árbol Beancount, PERO su metadata dice
  `laudus_categoria1: "GASTOS - EGRESOS"`, así que el **reporte lee el pago como el gasto** (lumpeado).
- Verificado en histórico 2021-2022: 566 pagos vs 2 compras. Saldo TC absurdamente positivo.

**Estado:** Se corrige al importar cartolas de cada tarjeta (solo 2026 en adelante; proceso continuo).
**Acción requerida:** Reportes de gasto total / balance deben advertir la limitación mientras la
tarjeta no tenga cartola importada.

**Fuentes de datos:**
- Laudus → Beancount: activo (espejo fiel).
- Cartolas de tarjetas: import en construcción (Stories 9.5/9.6a/9.6b). Fuente de verdad de las compras.
- Cartolas bancarias (cta corriente): fuente de verdad planificada de movimientos de banco.

## Hallazgo — Ingresos de inversión mal contabilizados (2026-06-20, EAG)

Auditoría a pedido de Ary (sospechaba que cargaban mal los ingresos sin actualizar activos —
CONFIRMADO). Detalle en `_bmad-output/planning-artifacts/valentina-auditoria-ingresos-inversiones-2026-06-20.md`.

- Los retiros/rescates **no separan capital de ganancia**. Dos errores opuestos conviven:
  - **Error A:** retiro 100% a cuenta de ingreso, no baja el activo → infla P&L y balance.
    Tecnion 12.204M, Nuevo Ciclo 5.963M, MBI 4.767M, JB 3.259M = **≈26.193M CLP** mal cargados.
  - **Error B:** retiro 100% contra el activo sin reconocer ganancia → activo NEGATIVO (imposible).
    InvTecnionLimitada −3.353M, FmBciClass0 −202M, FmBciAp0 −26M.
- Cuentas de resultado de inversión `Income:EAG:Resultado*` (510xxx) = **0 asientos**. Nunca se usaron.
- Laudus NO hace revalorización a valor cuota (0 asientos de ajuste). La ganancia de fondos se fuga.
- Indumotora (≈25.269M a ingreso) = **dividendos, CORRECTO**, no es error (Ary lo clasificó).
- Clasificación de Ary: Tecnion/Nuevo Ciclo/MBI = inversiones; JB = cta inversión; BCI = fondos mutuos.
- **Clave:** la paridad contra el contador NO detecta esto — Beancount es espejo fiel de Laudus y el
  error está dentro de Laudus. Solo se pesca reconciliando vs posición real del custodio (cartolas).
- **No corregir sin saldos del custodio confirmados.** Fix futuro = estilo TC (solo asientos estándar).
- Hijas (Jocelyn/Jeannette/Johanna/Jael) FUERA de alcance: no se sabe si retiran de fondos propios.
- Herramientas: `_forense_inversiones.py`, `_forense_recon_vehiculo.py` (planning-artifacts).

## Reportes Aprobados
_Reportes que el dueño ha aprobado desarrollar. Actualizar a medida que se aprueban._

## Decisiones de Diseño
_Decisiones arquitecturales tomadas. Para no re-litigar._

**Corrección contable de TC vía cartolas (2026-06-20)** — ver
`_bmad-output/planning-artifacts/valentina-correccion-tc-cartolas-2026-06-20.md`.
- La corrección se hace **solo con asientos contables estándar** que emite el import de cartola. NO
  se toca el motor/importer/metadata existente (regla de oro: evitar bugs).
- Por tarjeta, al importar su cartola 2026: (a) compras itemizadas → `TC:Real`/`Expenses`;
  (b) pago reclasificado de `TC original (gasto)` a `TC:Real`, mismo mes, sin tocar el banco;
  (c) una vez, `opening` de la 1ª cartola → `TC:Real` contra **`Equity:Apertura`** (NO gasto).
- Cuenta nueva por tarjeta `Liabilities:EAG:TC:Real:*` con metadata `PASIVO`, creada por el flujo
  sancionado de cuentas pendientes. Las cuentas TC originales (categoria GASTO) quedan intactas.
- Sin doble conteo (prueba de suma anual: gasto 2026 = Σ compras 2026). Borde de salida (dic→ene) se
  arregla solo porque el import es continuo.
- Tarjeta/período sin cartola → queda tal cual (gasto en cuenta TC original). Corrección es por
  tarjeta y por período.

**Decisiones para Story 6.2 (2026-06-22)** — ver §12 del doc. Tres cierres clave:
- **FX USD** = lump CLP del pago que SALDA el estado (mes siguiente) ÷ total USD facturado. Fuerza
  Σ(compras×FX)=lump (cuadre exacto, no BCCh). Lump = FX-denominador Y asiento(b), un solo evento.
  Sin lump aún → bloqueante, no estimar.
- **Abono** = compra invertida (no distinguir impuesto vs devolución).
- **`TC:Real` una por LÍNEA DE CRÉDITO** (unifica nacional+USD; la deuda es una). Adicionales ruedan
  ahí → `card_suffix` deja de bloquear (metadata opcional, no toca el prompt 9.5).
