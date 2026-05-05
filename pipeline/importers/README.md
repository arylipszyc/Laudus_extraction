# pipeline/importers — Imports y jobs hacia el ledger

Scripts y módulos que pueblan / actualizan el ledger Beancount.

---

## fx-bcch-eom — Dólar observado de cierre de mes (Story 9.10)

Refetch idempotente del dólar observado del cierre de un mes. Lo escribe a
`ledger/_meta/fx-bcch-eom.jsonl` para que Story 9.6b lo use como variable de
control (sanity check) contra la FX implícita derivada del matching
cartola↔Laudus, threshold 5%.

### Fuente de datos

[mindicador.cl](https://mindicador.cl) — proxy público y gratuito de las
series del Banco Central de Chile. Endpoint:
`GET https://mindicador.cl/api/dolar/DD-MM-YYYY`. Sin auth, sin registro.

> **Divergencia del story file:** el story file 9.10 menciona
> `api.bcentral.cl` (BCCh oficial). Decisión Ary 2026-05-05: usar
> mindicador.cl para evitar registro/credenciales. mindicador toma el dato
> directamente de BCCh, así que el rate es idéntico bajo el threshold de
> sanity check (5%).

### Cómo correrlo

#### Vía endpoint admin (recomendado)

```bash
curl -X POST "https://<backend>/api/v1/admin/fx-bcch/refetch?year_month=2026-04" \
  -H "Cookie: access_token=<owner-jwt>"
```

Response success:
```json
{
  "status": "fetched",
  "year_month": "2026-04",
  "bcch_date": "2026-04-30",
  "rate_clp_per_usd": 901.76,
  "source": "mindicador-dolar-observado"
}
```

Response idempotente (segunda llamada para el mismo mes):
```json
{
  "status": "skipped",
  "year_month": "2026-04",
  "bcch_date": "2026-04-30",
  "rate_clp_per_usd": 901.76,
  "source": "mindicador-dolar-observado"
}
```

RBAC: solo rol `owner` (Ary). `contador` recibe 403.

#### Vía CLI (debugging local)

```bash
python -m pipeline.importers.fx_bcch_eom 2026-04
```

Imprime el JSON resultado por stdout. Exit 0 (success/skip), 2 (validation),
3 (sin publicación).

### Garantías

| Caso | Comportamiento |
|---|---|
| `year_month` futuro | HTTP 400 — "es futuro respecto a hoy" |
| `year_month` = mes en curso | HTTP 400 — "es el mes en curso, esperá al cierre" |
| Mes ya cargado | HTTP 200 con `status: skipped` y los datos existentes |
| Último día del mes cae fin de semana / feriado | Itera hacia atrás hasta 7 días buscando publicación |
| 7 días sin publicación | HTTP 502 — reportar a mantenimiento (no debería pasar) |
| Mindicador caído / timeout | 3 retries con backoff exponencial (5s, 10s, 15s) → HTTP 502 si todos fallan |

### Shape del JSONL

`ledger/_meta/fx-bcch-eom.jsonl` (append-only, commiteado al repo):

```json
{"schema_version": "1.0", "year_month": "2026-04", "rate_clp_per_usd": 901.76, "fetched_at": "2026-05-05T18:54:42+00:00", "source": "mindicador-dolar-observado", "bcch_date": "2026-04-30"}
```

- `year_month` — clave de dedup. Una entrada por mes calendario.
- `bcch_date` — fecha real con publicación (puede no coincidir con último día calendario).
- `fetched_at` — timestamp UTC del momento del fetch (auditoría).

### Cron (deferred)

Story 9.10 entrega **endpoint on-demand only**. La automatización vía Render
Cron Job queda para una fase posterior — un cron mensual thin (curl al
endpoint) sin git push automatizado ni deploy keys. Ary dispara manualmente
hasta entonces.

### Out of scope

- Backfill batch (un endpoint por mes — iterá manualmente si necesitás varios).
- UF (no aparece en data Laudus, ver Dev Notes story 9.10).
- Cron diario (Q4 cerrada con cron mensual).
- Populación de `prices.beancount` — derivación automática vía plugin
  `implicit_prices` de Beancount es responsabilidad de Story 9.6b.
