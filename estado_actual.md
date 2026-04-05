# Estado Actual del Proyecto — Laudus API Sync

> **Revisión:** 2026-04-05  
> **Perspectiva:** Arquitecto de Software

---

## 1. ¿Qué hace este sistema?

Extrae datos contables (Balance General y Libro Mayor) desde la API de **Laudus ERP** y los almacena en **Google Sheets**, con dos modos de operación:

| Script | Propósito | Frecuencia esperada |
|---|---|---|
| `backfill_data.py` | Carga histórica masiva (Ene 2021 → hoy) | Una sola vez |
| `sync.py` | Sincronización incremental de nuevos datos | Recurrente (diario/mensual) |

---

## 2. Arquitectura actual

El proyecto sigue una estructura de capas bien definida:

```
┌─────────────────────────────────────────────────────┐
│           ORQUESTADORES (puntos de entrada)          │
│         sync.py          backfill_data.py            │
└────────────┬────────────────────────┬────────────────┘
             │                        │
   ┌──────────▼──────────┐  ┌────────▼────────┐
   │       SERVICIOS      │  │     CONFIG       │
   │  balance_sheet_     │  │  laudus_config  │
   │    service.py       │  │  gspread_config  │
   │  ledger_service.py  │  └─────────────────┘
   │  laudus_service.py  │
   └──────────┬──────────┘
              │
   ┌──────────▼──────────┐
   │       UTILS          │
   │     dates.py        │
   │   gspread_utils.py  │
   └─────────────────────┘
```

### Flujo de datos (sync.py)

```
1. Conectar a Google Sheets
   │
   ├─► Balance Sheet
   │     ├── Calcular último día del mes anterior
   │     ├── Verificar si ya existe en Sheets
   │     ├── Si no existe: llamar API → mapear → upsert
   │     └── Recalcular columna "is_latest"
   │
   └─► Ledger
         ├── Leer última fecha sincronizada desde pestaña "date_range"
         ├── Calcular rango incremental (última_fecha + 1 día → hoy)
         ├── Llamar API → mapear → upsert
         └── Actualizar pestaña "date_range"
```

---

## 3. Lo que está bien construido

### Separación de capas
La división entre `config/`, `services/` y `utils/` es correcta y respeta el principio de responsabilidad única.

### Lógica de upsert con clave primaria (`gspread_utils.py`)
La estrategia de descargar todo en memoria, mergear con diccionario y reescribir en lote es eficiente y previene duplicados. El uso de `USER_ENTERED` para preservar tipos de datos (números, fechas) es una decisión correcta.

### Manejo de token con reintentos (`laudus_service.py`)
El patrón de caché de token con `retry=False` en el segundo intento es limpio y funcional. Evita loops infinitos.

### Variables de entorno
Las credenciales se leen desde `.env` y `.gitignore` las excluye. Correcto.

---

## 4. Partes incompletas o con deuda técnica

### 4.1 Código duplicado — CRÍTICO

`BALANCE_HEADERS`, `LEDGER_HEADERS` y las funciones de mapeo están **definidas dos veces**: una en `sync.py` y otra en `backfill_data.py`. Si algún día cambia el esquema de datos de la API, habrá que actualizar dos archivos y es fácil que queden desincronizados.

**Solución:** Crear un archivo `models.py` (o `mappers.py`) con las constantes y las funciones de transformación compartidas.

---

### 4.2 URL del Balance Sheet hardcodeada en sync.py

En `sync.py` línea 103:
```python
balance_url = "https://api.laudus.cl/accounting/balanceSheet/totals"
```
Esta misma URL ya está definida en `laudus_config.py` dentro de `get_endpoints()`. Hay **dos fuentes de verdad** para la misma URL.

**Solución:** `sync.py` debería usar `get_endpoints()` al igual que `backfill_data.py`.

---

### 4.3 Servicios vacíos sin valor agregado

`balance_sheet_service.py` y `ledger_service.py` son wrappers de una sola línea que únicamente llaman a `get_info_API`. No añaden lógica, validación ni transformación propia.

```python
# balance_sheet_service.py — actualmente no hace nada propio
def fetch_balance_sheet(endpoint, params=None):
    return get_info_API(endpoint, params)
```

Esto crea complejidad de indirección sin beneficio real. Estos archivos serían valiosos si contuvieran la lógica de mapeo de respuesta, validación de campos obligatorios o manejo de errores específicos del endpoint.

---

### 4.4 La lógica de `accountNumberFrom` es frágil

En `sync.py` (línea 166) y `backfill_data.py` (línea 150), el parámetro `accountNumberFrom` para el Ledger se obtiene tomando **el primer registro** del balance sheet:

```python
ledger_cfg["params"]["accountNumberFrom"] = str(bal_records[0].get("account_number", ""))
```

Si el balance está vacío, ordenado de manera diferente, o si el primer número de cuenta no es el mínimo, la consulta del ledger puede retornar datos incompletos silenciosamente.

---

### 4.5 `backfill_data.py` tiene fechas hardcodeadas que caducan

```python
BALANCE_END_YEAR = 2026
BALANCE_END_MONTH = 3
```

Este script ya quedó desactualizado. La fecha de fin debería calcularse automáticamente como "el mes anterior a hoy", igual que lo hace `sync.py`.

---

### 4.6 Sin sistema de logging estructurado

Todo el sistema usa `print()`. Esto impide:
- Filtrar por nivel de severidad (INFO, WARNING, ERROR)
- Redirigir logs a un archivo sin modificar el código
- Integrar con herramientas de monitoreo futuras

**Solución mínima:**
```python
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
```

---

### 4.7 `gspread_config.py` referencia `FIREBASE_CREDENTIALS`

```python
cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("FIREBASE_CREDENTIALS")
```

`FIREBASE_CREDENTIALS` es un residuo de una versión anterior. Genera confusión y debería eliminarse.

---

### 4.8 Sin manejo de paginación de la API

No hay evidencia de que el código maneje respuestas paginadas de la API de Laudus. Si la API retorna los resultados en páginas (con `nextPage`, `offset`, o `limit`), el sistema estaría trayendo solo la primera página sin saberlo.

**Acción:** Verificar en la documentación de Laudus si los endpoints `/ledger` y `/balanceSheet/totals` paginan sus respuestas.

---

### 4.9 Sin pruebas automatizadas

No existe ningún test unitario ni de integración. El único archivo de prueba es `test_gspread.py`, que es un script manual de conectividad. Esto hace que cualquier cambio en el código requiera ejecución manual completa para validar.

---

## 5. Resumen de prioridades

| # | Problema | Impacto | Esfuerzo |
|---|---|---|---|
| 1 | Código duplicado (headers + mappers) | Alto — bugs silenciosos al crecer | Bajo |
| 2 | URL hardcodeada en `sync.py` | Medio — inconsistencia de configuración | Muy bajo |
| 3 | `accountNumberFrom` frágil | Alto — datos incompletos sin error visible | Medio |
| 4 | Fechas hardcodeadas en `backfill_data.py` | Medio — script caducado | Muy bajo |
| 5 | Servicios vacíos sin valor | Bajo — complejidad innecesaria | Bajo |
| 6 | Sin logging estructurado | Medio — operación sin visibilidad | Bajo |
| 7 | Sin paginación | Alto si la API pagina — pérdida de datos | Medio |
| 8 | Residuo `FIREBASE_CREDENTIALS` | Bajo — confusión de código | Muy bajo |

---

## 6. Siguiente paso recomendado

Antes de agregar nuevas funcionalidades, consolidar el código duplicado en un archivo `models.py` centralizado. Es el cambio de menor riesgo con mayor beneficio inmediato para la mantenibilidad del proyecto.
