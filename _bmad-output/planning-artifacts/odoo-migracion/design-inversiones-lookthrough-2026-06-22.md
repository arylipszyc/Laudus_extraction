---
title: "Módulo Inversiones — Ingesta de cartolas de custodia + motor Look-Through"
status: draft-design
author: "Diseño asistido (sesión Cowork) — para revisión de Winston/Ary"
date: "2026-06-22"
relatedDocs:
  - _bmad-output/planning-artifacts/architecture-c4.md   # §4.1 contrato canónico cartola, §3 chart Beancount
  - _bmad-output/planning-artifacts/epics.md             # Epic 4/9 (cartola PDF), Epic 6 (recon)
  - _bmad-output/planning-artifacts/valentina-auditoria-ingresos-inversiones-2026-06-20.md
scope: "Nueva capability (candidata a Epic 10). NO incluye código — solo diseño."
---

# Módulo Inversiones — Ingesta de cartolas de custodia + motor Look-Through

## 0. TL;DR

Extender el pipeline existente `PDF → Gemini → JSON canónico → Beancount` para **cartolas de
custodia de inversiones** (Julius Baer y otros bancos privados), y agregar un **motor de
look-through** que descompone cada instrumento hasta su exposición económica real en tres
dimensiones (renta fija/variable, geografía, sector), corrigiendo las etiquetas del banco.

Dos salidas:

1. **Análisis / dashboard** de exposición real (la foto corregida que hoy el estado de cuenta esconde).
2. **Reconciliación de posición** contra el ledger Beancount — el gancho que la auditoría de
   Valentina (2026-06-20) identificó como *el único modo de cazar* los errores de capital vs.
   ganancia en los rescates de inversión, porque Laudus y Beancount comparten el mismo error y solo
   se detecta contra la **posición real del custodio**.

Sourcing de datos por **ruta gratuita** (factsheets/justETF + EDGAR + portales de emisor vía
navegador), con la capa de datos diseñada como adaptadores *pluggables* para que mañana entre una
API de pago (EODHD/FactSet) sin tocar el motor. Extracción del PDF por **LLM (Gemini)**, consistente
con el flujo de cartolas bancarias ya en producción.

Este diseño nace de un prototipo validado end-to-end sobre dos cartolas Julius Baer reales
(portafolios `1313.3171` y `0320.5320 02.02`, TAURO LIMITED PARTNERSHIP) — ver §12 (mapeo prototipo→módulo).

---

## 1. Contexto y motivación

### 1.1 Qué ya existe (y reusamos)

| Pieza existente | Ubicación | Cómo se reusa |
|---|---|---|
| Upload PDF + extracción Gemini | `backend/app/integrations/gemini_client.py` | Mismo `GeminiClient`, nuevo prompt + nuevo schema de salida |
| Contrato canónico (patrón) | `cartola_schema.py` (`CartolaCanonicalV1`) | Se replica el patrón Pydantic para posiciones de inversión |
| Endpoint upload | `POST /api/v1/cartolas/upload` (architecture-c4 §4.1) | Endpoint análogo `POST /api/v1/investments/statements/upload` |
| Chart Beancount inversiones | `Assets:EAG:Inversiones:JuliusBaer-XXXXX` (c4 §3, type `cta_inversiones`) | Destino de la reconciliación de posición |
| Motor de reconciliación | Epic 9 (9.6b/9.10/9.12), wireado en Epic 6 | Patrón para el "balance check" de posición |
| Frontend upload + dashboards | `CartolaUploadPage.tsx`, Recharts, Radix/shadcn, TanStack Query | Páginas nuevas reusando los mismos componentes |
| RBAC 3 roles | `family` / `contador` / `admin` (docs/rbac-3-roles.md) | Mismo modelo de permisos |

### 1.2 El problema que resuelve (gancho Valentina)

La auditoría de inversiones encontró que los retiros/rescates **no separan capital de ganancia** y
que *"solo se pesca reconciliando contra la posición real del custodio (cartola del fondo/banco)"*.
Hoy esa cartola de custodio:

- llega en **PDF** (no estructurada),
- mezcla **productos estructurados dentro de "Acciones"** (infla la renta variable),
- esconde **private markets** y **fondos** sin descomponer,
- no entrega la **exposición económica real** que el head del family office necesita para decidir.

Este módulo convierte ese PDF en (a) una posición estructurada y conciliable contra el activo del
ledger, y (b) una foto de exposición real con trazabilidad de confianza.

### 1.3 Hallazgos del prototipo que el diseño debe preservar

- El banco etiquetó **54.2%** en "renta variable"; el look-through real fue **43.0%** — la diferencia
  eran ~USD 2.8M de notas estructuradas escondidas en "Acciones" y "Otros fondos".
- Hubo **errores de identidad por nombre abreviado** que solo se corrigen con fuente real (ej.
  `IE00BP3QZB59` no era "MSCI World" sino "MSCI World **Value Factor**"; `IE000IAXNM41` no era un ETF
  amplio sino "iShares Europe **Defence**").
- **EDGAR resuelve notas estructuradas de emisores US** (Citi/MS/JPM: full-text search por ISIN/CUSIP
  → pricing supplement → subyacentes), pero **no** las suizas (CH/XS) — esas requieren portal del emisor.
- La honestidad es un requisito, no un nice-to-have: **nunca mezclar dato duro con relleno**; cada
  posición lleva un nivel de resolución y los estimados se muestran distinto.

---

## 2. Objetivo y no-objetivos

**Objetivo.** Dado un PDF de cartola de custodia, producir:
1. Una **tabla canónica de posiciones** (valor, ISIN, cantidad, moneda, clase del banco) con cuadre validado contra el total del estado de cuenta.
2. Un **look-through** ponderado por market value en 3 dimensiones (asset class real, geografía, sector) con **nivel de resolución por posición**.
3. Un **snapshot persistido** y conciliable contra `Assets:*:Inversiones:*` en Beancount.

**No-objetivos (de esta fase).**
- No ejecuta operaciones ni mueve dinero (read-only analytics — alineado a las reglas de la plataforma).
- No reemplaza el ledger contable: el look-through es **analítico**, no genera asientos (salvo el seam de reconciliación, §8).
- No promete descomponer canastas estructuradas suizas sin term sheet (quedan en cola de pendientes, no se inventan).
- No incorpora API de datos de pago en esta fase (pero la capa queda lista para ello — §7).

---

## 3. Requerimientos (estilo PRD/epics existente)

### 3.1 Functional Requirements

**Ingesta**
- FR-INV-1: El contador puede subir una cartola de custodia (PDF) asociada a una `investment_account` (entidad + custodio + nº de portafolio).
- FR-INV-2: El sistema envía el PDF a Gemini con un prompt de extracción de posiciones y recibe el JSON canónico `PortfolioValuationCanonicalV1` (posiciones + totales + metadata de cuenta).
- FR-INV-3: El sistema valida el cuadre: Σ market value de posiciones = total del estado de cuenta (tolerancia configurable). Si no cuadra, bloquea la confirmación (override con justificación, igual que FR24/FR25 de cartolas).
- FR-INV-4: El sistema extrae y muestra: nº y nombre de cuenta/relación, custodio, fecha de valuación, moneda de referencia, y por posición: nombre, ISIN/security-no, cantidad/nominal, precio, market value, % NAV, clase del banco.

**Clasificación + Look-through**
- FR-INV-5: El sistema clasifica cada posición en uno de los buckets: `caja`, `accion_directa`, `bono_directo`, `fondo_etf`, `estructurado_subyacente`, `estructurado_canasta`, `alternativo_commodity`, `alternativo_privado`.
- FR-INV-6: Para acciones y bonos directos, el sistema resuelve sector y país del emisor (ruta gratuita + verificación).
- FR-INV-7: Para fondos/ETF, el sistema obtiene el look-through real (asset allocation, world regions, sector weights) desde el factsheet del fondo; el top-N es dato duro, la cola se modela por composición del índice (marcado como tal).
- FR-INV-8: Para estructurados con subyacente único identificable en el nombre (ej. `META/BAEG`), el sistema los trata como renta variable de ese subyacente.
- FR-INV-9: Para estructurados de emisor **US**, el sistema resuelve subyacentes vía EDGAR (full-text search → pricing supplement 424B2/FWP).
- FR-INV-10: Para estructurados de canasta genérica suiza/europea sin subyacente en el nombre, el sistema NO inventa composición: los marca `requiere_term_sheet` y los deja en cola de pendientes con campo editable para carga manual.
- FR-INV-11: El sistema agrega el look-through ponderado por market value en 3 dimensiones y produce además la vista "etiquetas del banco" vs "look-through real".
- FR-INV-12: Cada posición lleva un **nivel de resolución**: `resuelto` · `por_mandato` · `requiere_term_sheet` · `requiere_detalle` · `error_fuente`, y la **fuente** del dato (factsheet/EDGAR/emisor/nombre/manual). El sistema reporta el % del portafolio por nivel.

**Salidas**
- FR-INV-13: El usuario (family/contador) ve un dashboard con los 3 breakdowns, un toggle banco↔look-through, una cinta de cobertura por nivel de resolución, y las porciones estimadas marcadas visualmente distinto.
- FR-INV-14: El usuario puede exportar la posición y el look-through (CSV/Excel).
- FR-INV-15: El contador puede cargar manualmente los subyacentes de una canasta pendiente; al guardarse, la posición se reincorpora al look-through y baja la cola de pendientes.
- FR-INV-16: El sistema persiste un **snapshot** por (cuenta, fecha de valuación) y permite comparar snapshots en el tiempo.

**Reconciliación (gancho Valentina)**
- FR-INV-17: El sistema concilia el market value por vehículo del snapshot contra el saldo del activo correspondiente en Beancount (`Assets:*:Inversiones:*`) y reporta la diferencia.
- FR-INV-18: Cuando la diferencia excede umbral, marca el vehículo como "posible error de capital/ganancia" (el patrón A/B de la auditoría) para revisión del contador.

### 3.2 Non-Functional Requirements
- NFR-INV-1: El PDF no se persiste (consistente con la política no-PDF-storage de cartolas); solo el JSON canónico y el snapshot.
- NFR-INV-2: Toda llamada a fuentes externas (factsheet/EDGAR/portal) pasa por una **cache** con TTL; el motor es determinístico dado el cache.
- NFR-INV-3: La capa de datos de mercado es un puerto (interface) con adaptadores intercambiables; agregar EODHD/FactSet no debe tocar el motor de look-through.
- NFR-INV-4: Trazabilidad: nunca se mezcla dato sourceado con estimado en la misma celda visual; el origen es auditable por posición.
- NFR-INV-5: Idempotencia: re-subir la misma cartola (mismo hash) no duplica snapshots.
- NFR-INV-6: Privacidad: ningún dato de cliente se manda a fuentes externas (solo se consultan ISIN/ticker públicos).

---

## 4. Arquitectura (cómo encaja)

### 4.1 Vista de contenedores (C4-ish, en prosa)

Sigue el patrón de cartolas: todo vive dentro del backend FastAPI existente (no servicio separado),
con un nuevo paquete `backend/app/investments/` y reuso de `integrations/gemini_client.py`.

```
┌────────────── frontend (React/Vite) ──────────────┐
│ InvestmentUploadPage · PortfolioLookThroughPage    │
│ PendingQueuePanel · ReconciliationPanel            │
│ (Recharts, Radix/shadcn, TanStack Query)           │
└───────────────┬────────────────────────────────────┘
                │ REST /api/v1/investments/*
┌───────────────▼──────────── backend FastAPI ───────────────┐
│ investments/router.py                                       │
│ investments/extract.py    → GeminiClient (reuse)            │
│ investments/schema.py     → PortfolioValuationCanonicalV1   │
│ investments/classify.py   → bucket rules                    │
│ investments/lookthrough.py→ motor de agregación + resolución│
│ investments/enrich/                                         │
│   ├─ ports.py  (MarketDataPort, StructuredNotePort)         │
│   ├─ factsheet_justetf.py     (adapter, ruta gratuita)      │
│   ├─ edgar.py                 (adapter, notas US)           │
│   ├─ issuer_portal_browser.py (adapter, portal emisor)      │
│   └─ cache.py                 (Supabase-backed, TTL)        │
│ investments/reconcile.py  → vs ledger_service (Beancount)   │
└───────────────┬─────────────────────────┬───────────────────┘
                │                          │
        Supabase (Postgres)         Beancount ledger
        - instrument_cache          Assets:*:Inversiones:*
        - portfolio_snapshot        (ledger_service / bql_queries)
        - position
        - pending_basket
```

### 4.2 Flujo end-to-end

1. **Upload** (`POST /api/v1/investments/statements/upload`, multipart PDF + `investment_account_id`).
2. **Extract** (Gemini): PDF → `PortfolioValuationCanonicalV1` (posiciones + totales + metadata). PDF se descarta.
3. **Validate cuadre**: Σ MV = total; warnings (`TOTAL_MISMATCH`, `LOW_CONFIDENCE`, `MISSING_ISIN`). Bloqueo + override.
4. **Classify**: cada posición → bucket (reglas §6.1).
5. **Enrich / look-through**: por bucket se llama al puerto de datos (cache-first). Acciones/bonos → sector+país; fondos → factsheet; estructurados → nombre/EDGAR/portal; canastas sin resolver → cola.
6. **Aggregate**: ponderar por MV en las 3 dimensiones + vista banco vs real + % por nivel de resolución.
7. **Persist snapshot** (cuenta, fecha) + posiciones + cola de pendientes.
8. **Reconcile** (opcional, gancho Valentina): MV por vehículo vs saldo `Assets:*:Inversiones:*`.
9. **Serve**: dashboard, export, cola editable.

---

## 5. Modelo de datos canónico

Replica el estilo de `CartolaCanonicalV1` (Pydantic, `extra="forbid"`, enums cerrados). Vive en
`backend/app/investments/schema.py`.

```python
SchemaVersion = Literal["inv-1.0"]
Currency      = Literal["USD","EUR","CHF","CLP","GBP","DKK", ...]   # extender según necesidad
BankAssetClass = Literal[                  # etiqueta CRUDA del banco (lo que dice el PDF)
    "cash","bonds","equities","alternative","other_funds"]
Bucket = Literal[                          # clasificación nuestra (look-through)
    "caja","accion_directa","bono_directo","fondo_etf",
    "estructurado_subyacente","estructurado_canasta",
    "alternativo_commodity","alternativo_privado"]
ResolutionLevel = Literal[
    "resuelto","por_mandato","requiere_term_sheet","requiere_detalle","error_fuente"]
DataSource = Literal[
    "statement","name","web_issuer","factsheet","edgar","manual","index_model"]

class StatementSource(BaseModel):          # análogo a CartolaSource
    investment_account_id: str
    custodian: str                         # "Julius Baer"
    relationship_no: str                   # "0320.5320"
    portfolio_no: str                      # "0320.5320 02.02"
    account_name: str                      # "TAURO LIMITED PARTNERSHIP"
    entity: str                            # entidad EAG mapeada
    reference_currency: Currency

class Position(BaseModel):
    line_no: int
    name: str
    isin: str | None                       # puede faltar (PE sin ISIN → security_no)
    security_no: str | None
    bank_asset_class: BankAssetClass
    quantity: Decimal | None
    currency: Currency
    price: Decimal | None
    market_value_ref: Decimal              # en moneda de referencia (USD) — base de TODAS las ponderaciones
    pct_nav: Decimal | None
    raw: dict[str, Any] = {}

class PortfolioTotals(BaseModel):
    total_value_ref: Decimal
    by_bank_class: dict[BankAssetClass, Decimal]

class PortfolioValuationCanonicalV1(BaseModel):
    schema_version: SchemaVersion
    source: StatementSource
    valuation_date: date
    totals: PortfolioTotals
    positions: list[Position]
    extraction: Extraction                 # {model, extracted_at, warnings[]}
```

El **resultado del look-through** es un objeto derivado (no lo produce Gemini; lo produce el motor),
persistido aparte:

```python
class PositionLookThrough(BaseModel):
    line_no: int
    bucket: Bucket
    asset_class_final: Literal["RV","RF","caja","commodity","estructurado_pendiente","privado_pendiente"]
    geo: dict[str, Decimal]                 # país/región → peso (suma 1.0)
    sector: dict[str, Decimal]              # sector → peso (suma 1.0)
    resolution: ResolutionLevel
    source: DataSource
    as_of: date | None                      # fecha del factsheet/term sheet usado
    note: str

class LookThroughSnapshot(BaseModel):
    investment_account_id: str
    valuation_date: date
    total_value_ref: Decimal
    asset_class_bank: dict[str, Decimal]    # vista "etiquetas del banco"
    asset_class_real: dict[str, Decimal]    # vista look-through
    geo: dict[str, Decimal]
    sector: dict[str, Decimal]
    coverage: dict[ResolutionLevel, Decimal]
    positions: list[PositionLookThrough]
    pending: list[PendingBasket]            # cola requiere_term_sheet / requiere_detalle
```

**Invariantes validables (tests):** `Σ market_value_ref == total_value_ref`; cada `geo`/`sector` suma 1.0;
cada dimensión agregada suma `total_value_ref`; `Σ coverage == total_value_ref`. (Son exactamente los
checks que el prototipo ya corre.)

---

## 6. Motor de Look-Through

### 6.1 Reglas de clasificación (bucket)

| Condición | Bucket | Descomposición |
|---|---|---|
| `bank_asset_class == cash` | `caja` | sin geo/sector |
| nombre con subyacente único (`<cupón> <TICKER>/<EMISOR> <yy>`, o `BSKT` con índice/acción puntual) | `estructurado_subyacente` | RV del subyacente (resolver ticker) |
| nombre contiene `BSKT` genérico (sin subyacente) | `estructurado_canasta` | EDGAR si emisor US; si no → `requiere_term_sheet` |
| ISIN `IE`/`LU`/`CH`-fondo o nombre iShares/UBS/PIMCO/Xtrackers/Amundi/Nomura/Algebris… | `fondo_etf` | factsheet (asset alloc + regions + sectors) |
| sección `bonds`, ISIN no-fondo | `bono_directo` | emisor: soberano→Gobierno/país; corp→sector+país (captives: geo por grupo) |
| sección `equities`, emisor único | `accion_directa` | sector+país del emisor |
| `bank_asset_class == alternative` + nombre oro/`GldETF` | `alternativo_commodity` | commodity/oro |
| `bank_asset_class == alternative` + private markets/PE | `alternativo_privado` | `requiere_detalle` |

> Nota crítica del prototipo: la clasificación **no** confía en la sección del banco para estructurados —
> el banco los mete en "equities"/"other funds". El bucket de estructurado se decide por el patrón del
> nombre/ISIN, y luego se **saca** de renta variable en la vista real.

### 6.2 Resolución por bucket y nivel de confianza

| Bucket | Fuente primaria (ruta gratuita) | Nivel resultante |
|---|---|---|
| `accion_directa` | conocimiento + verificación web del emisor | `resuelto` |
| `bono_directo` | emisor (web); Treasuries evidentes | `resuelto` |
| `fondo_etf` | factsheet justETF/gestor (top-N real + fecha) | `resuelto` (cola del índice modelada → nota); `por_mandato` si el gestor no publica desglose |
| `estructurado_subyacente` | nombre + verificación del ticker | `resuelto` |
| `estructurado_canasta` (emisor US) | EDGAR (424B2/FWP) | `resuelto` |
| `estructurado_canasta` (CH/XS) | portal emisor (browser) o carga manual | `requiere_term_sheet` hasta resolver |
| `alternativo_commodity` | evidente (oro) | `resuelto` |
| `alternativo_privado` | n/a | `requiere_detalle` |

La regla de honestidad (NFR-INV-4) es dura: el top-N del factsheet es dato duro; la cola modelada por
índice va marcada; las canastas y PE sin fuente **no se rellenan**.

### 6.3 Agregación

Ponderar cada `geo`/`sector` de cada posición por su `market_value_ref`; sumar; normalizar. Producir en
paralelo la vista "banco" (agrupando por `bank_asset_class`) y la "real" (por `asset_class_final`),
porque el delta entre ambas es el hallazgo de negocio (estructurados ocultos).

---

## 7. Capa de datos de mercado (ruta gratuita, pluggable)

### 7.1 Puertos (interfaces)

```python
class MarketDataPort(Protocol):
    def equity_profile(self, isin_or_ticker: str) -> SectorCountry | None: ...
    def fund_breakdown(self, isin: str) -> FundBreakdown | None:  # asset_alloc, regions, sectors, as_of
        ...

class StructuredNotePort(Protocol):
    def resolve_underlyings(self, isin_or_cusip: str) -> NoteTerms | None: ...
```

### 7.2 Adaptadores (esta fase = ruta gratuita)

| Adapter | Cubre | Técnica | Notas |
|---|---|---|---|
| `factsheet_justetf` | ETFs UCITS | `web_fetch` a justETF profile → tabla Countries/Sectors + link al PDF del gestor | top-4 + "Other"; PDF para detalle fino |
| `factsheet_issuer_pdf` | fondos activos (PIMCO/Nomura/Algebris/AB) | `web_fetch` al PDF mensual del gestor | algunos no publican país/sector → `por_mandato` |
| `edgar` | notas estructuradas US | `efts.sec.gov/LATEST/search-index?q="ISIN"` → 424B2/FWP → subyacentes | probado: resuelve Citi/MS/JPM por ISIN o CUSIP |
| `issuer_portal_browser` | notas CH/XS (Julius Bär, Vontobel, ZKB) | Claude-in-Chrome / Playwright (el repo ya tiene `.playwright-mcp/`) sobre `derivatives.juliusbaer.com` etc. | JS-rendered; fallback = carga manual |

> El repo **ya tiene Playwright MCP** (`.playwright-mcp/`), lo que hace viable el adapter de portal de
> emisor como job headless, no como acción interactiva.

### 7.3 Cache

Tabla `instrument_cache(key, kind, payload_json, as_of, fetched_at, ttl)`. El motor consulta cache-first;
solo va a la fuente si expiró. Esto da NFR-INV-2 (determinismo) y evita rate-limits.

### 7.4 Camino a futuro (no en esta fase)

Agregar un `eodhd_adapter` que implemente `MarketDataPort` no toca `lookthrough.py`. Es un swap de
binding por config (`MARKET_DATA_PROVIDER=free|eodhd`). El nivel de resolución de fondos sube de
`por_mandato` a `resuelto` automáticamente cuando la fuente devuelve breakdown real.

---

## 8. Integración con Beancount (gancho Valentina)

El look-through es analítico, pero el **market value por vehículo** del snapshot es la pieza que faltaba
para la reconciliación de inversiones:

- `reconcile.py` toma cada posición/vehículo del snapshot y consulta el saldo del activo en el ledger
  (`Assets:<entidad>:Inversiones:<custodio>-<cuenta>`) vía `ledger_service` / `bql_queries`.
- Diferencia `MV_custodio − saldo_ledger` por vehículo. Si supera umbral → flag.
- Esto detecta exactamente los patrones A/B de la auditoría: activo que "nunca bajó" (Error A) y activo
  en saldo negativo (Error B), porque ahora hay una **fuente externa al par Laudus↔Beancount**.
- **No** genera asientos automáticos (read-only). Produce un reporte para el contador (consistente con
  Epic 6: el motor de recon ya existe; esto es un *feed* nuevo hacia él).

Decisión abierta (§11): si el snapshot de posición debe además materializarse como `balance`/`price`
directives en un `ledger/imports/custodian/*.beancount` para que Fava lo muestre, o quedarse solo en
Supabase como capa analítica. Recomendación inicial: empezar analítico (Supabase), evaluar directivas
`price` después.

---

## 9. Frontend

Reusa el stack actual (React 19, Vite, TanStack Query, Recharts, Radix/shadcn, Tailwind).

| Página/Componente | Reusa | Función |
|---|---|---|
| `InvestmentUploadPage.tsx` | patrón de `CartolaUploadPage.tsx` + `useCartolaUpload` | subir PDF, ver tabla extraída, validar cuadre |
| `PortfolioLookThroughPage.tsx` | Recharts (ya en deps) | 3 breakdowns, toggle banco↔real, cinta de cobertura, estimados rayados |
| `PendingQueuePanel.tsx` | Radix dialog | cola `requiere_term_sheet`/`requiere_detalle` + form de carga manual de subyacentes |
| `ReconciliationPanel.tsx` | patrón de `ReconciliationPage.tsx` | diff posición custodio vs ledger |
| `services/investments.ts` | patrón de `services/cartolas.ts` | cliente REST |

El dashboard del prototipo (HTML self-contained con toggle + cinta de cobertura + barras rayadas para
estimado) es la **referencia visual** directa para `PortfolioLookThroughPage`.

---

## 10. Persistencia (Supabase)

| Tabla | Campos clave | Notas |
|---|---|---|
| `investment_account` | id, entity, custodian, relationship_no, portfolio_no, account_name, ref_ccy | catálogo de cuentas de custodia |
| `portfolio_snapshot` | id, investment_account_id, valuation_date, total_value_ref, statement_hash | idempotencia por hash (NFR-INV-5) |
| `position` | snapshot_id, line_no, name, isin, bucket, market_value_ref, … | posición canónica |
| `position_lookthrough` | snapshot_id, line_no, asset_class_final, geo_json, sector_json, resolution, source, as_of | resultado del motor |
| `pending_basket` | snapshot_id, isin, reason, manual_underlyings_json (nullable) | cola editable |
| `instrument_cache` | key, kind, payload_json, as_of, fetched_at, ttl | cache de fuentes externas |

RBAC: `contador`/`admin` suben y editan; `family`/owner ve (read-only) — mismo modelo `RBAC_ROLE_MAPPING`.

---

## 11. Epic & story breakdown (propuesta — candidato Epic 10)

> Encaja como **Epic 10: Inversiones — Posición real y Look-Through** (Phase 2), después de que Epic 6
> (recon) esté wireado. Numeración sujeta a revisión de Bob/Winston.

- **Story 10.1 — Catálogo `investment_account` + endpoint upload.** Modelo de cuenta de custodia, `POST /investments/statements/upload`, persistencia base. *Verify:* upload de PDF JB de prueba retorna `batch_id`.
- **Story 10.2 — Extracción Gemini → `PortfolioValuationCanonicalV1`.** Prompt + schema Pydantic + validación de cuadre + warnings. *Verify:* las 2 cartolas TAURO/JB cuadran al centavo contra el total del banco.
- **Story 10.3 — Clasificador de buckets.** Reglas §6.1 + tests sobre los nombres reales (BSKT, META/BAEG, GldETF, PE). *Verify:* conteo por bucket reproduce el del prototipo.
- **Story 10.4 — Puerto + cache + adapter `factsheet_justetf`.** `MarketDataPort`, `instrument_cache`, fondos ETF resueltos. *Verify:* breakdown real con fecha para los ETFs grandes.
- **Story 10.5 — Adapter `edgar` (notas US).** Full-text search + parse 424B2/FWP → subyacentes. *Verify:* `US17333JBV17` → Netflix.
- **Story 10.6 — Motor de agregación + niveles de resolución.** Vista banco vs real, cobertura. *Verify:* invariantes (sumas 1.0 / total) pasan; delta banco-real reproduce el hallazgo.
- **Story 10.7 — Dashboard look-through (frontend).** 3 breakdowns + toggle + cinta + estimados rayados. *Verify:* paridad visual con el prototipo HTML.
- **Story 10.8 — Cola de pendientes + carga manual.** `pending_basket` + form; reincorpora al guardar. *Verify:* cargar subyacentes de una BSKT la mueve a `resuelto`.
- **Story 10.9 — Adapter `issuer_portal_browser` (Playwright).** Job headless sobre portal JB/Vontobel/ZKB. *Verify:* resuelve ≥1 ISIN CH end-to-end (con fallback manual si JS falla).
- **Story 10.10 — Reconciliación posición vs ledger (feed a Epic 6).** `reconcile.py` + `ReconciliationPanel`. *Verify:* reproduce los flags A/B de la auditoría Valentina sobre la cuenta JB.
- **Story 10.11 — Adapter `factsheet_issuer_pdf` (fondos activos).** PIMCO/Nomura/Algebris/AB. *Verify:* ≥1 fondo activo sube de `por_mandato` a `resuelto`.

Dependencias: 10.1→10.2→10.3→(10.4,10.5)→10.6→(10.7,10.8); 10.9/10.11 enriquecen; 10.10 requiere 10.6 + Epic 6.

---

## 12. Mapeo prototipo → módulo (qué ya está validado)

| Pieza del prototipo (sesión Cowork) | Equivalente en el módulo |
|---|---|
| Parser openpyxl/PDF + conteo por bucket + cuadre de total | Story 10.2 + 10.3 (`extract.py`, `classify.py`) |
| `build_model.py` (templates de índice, blend top-4 real) | `lookthrough.py` (motor §6) |
| `funds_real.json` (factsheets justETF + PDFs) | `factsheet_justetf` + `instrument_cache` (Story 10.4) |
| Búsqueda EDGAR por ISIN/CUSIP → 424B2 | `edgar.py` (Story 10.5) |
| Portal Julius Bär (intento browser) | `issuer_portal_browser.py` (Story 10.9) |
| Dashboard HTML (toggle + cinta + rayado) | `PortfolioLookThroughPage.tsx` (Story 10.7) |
| CSV una fila por posición + provenance | export FR-INV-14 |
| Niveles `resuelto/por mandato/requiere term sheet/requiere detalle` | `ResolutionLevel` enum + cobertura |
| Cruce: `XS3010104274` y `XD1432486425` aparecen en 2 cartolas | clave de des-duplicación cross-portfolio en `instrument_cache` |

El prototipo entregó: 115 posiciones / USD 17.5M cuadradas; cobertura 76.6% resuelta tras factsheets;
delta banco 54.2% RV → real 43.0% RV. Esos números son el **baseline de aceptación** de Stories 10.2/10.6.

---

## 13. Decisiones abiertas para Ary

1. **Snapshot → Beancount.** ¿El módulo solo concilia (analítico en Supabase), o además materializa
   `price`/`balance` directives para que Fava muestre la valuación del custodio? (Recomendación: analítico primero.)
2. **Alcance de entidades.** ¿Arrancamos solo con la(s) cuenta(s) Julius Baer (EAG/TAURO), o multi-custodio desde el inicio?
3. **Browser headless en prod.** ¿Aceptable correr Playwright en Render para el adapter de portal de emisor, o ese paso queda como carga manual asistida hasta una fase posterior?
4. **Política de "cola modelada".** ¿La cola del índice (más allá del top-N del factsheet) se muestra como
   parte del resuelto con nota, o se separa siempre como su propia franja estimada? (El prototipo la incluyó con nota.)
5. **Trigger de reconciliación.** ¿La recon posición-vs-ledger corre automática post-upload, o es una acción explícita del contador (consistente con cómo Epic 6 wirea el motor)?

---

## 14. Riesgos

- **Fragilidad de la ruta gratuita.** justETF/portales cambian el DOM; mitigado con cache + tests de
  contrato por adapter + fallback a carga manual. (El swap a una API de pago es el plan B estructural.)
- **Canastas suizas opacas.** Sin term sheet no hay composición; el diseño lo asume (cola, no relleno).
- **Identidad por nombre abreviado.** El banco abrevia (`iSh MSCI Wrl`); la verificación por ISIN contra
  fuente es obligatoria (lección del prototipo: era Value Factor, no World).
- **Costo de mantenimiento de adapters.** Cada banco/gestor nuevo puede requerir ajuste; el puerto
  `MarketDataPort` acota el blast radius.
```
