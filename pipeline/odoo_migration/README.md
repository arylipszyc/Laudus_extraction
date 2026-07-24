# pipeline/odoo_migration — Migración Laudus (espejo Beancount) → Odoo

Scaffold de Epic **E1** (Fase 1a). Convierte el espejo crudo `ledger/main.beancount`
al modelo de Odoo 18. Este paquete es el **scaffold bloqueante (story E1.0)**: deja lista
la infra de desarrollo y verificación; la lógica de negocio la agregan E1.1→E1.6.

## Dos tiers de verificación (lección `tsc --noEmit`)

El gate por-commit tiene que ser **rápido, determinístico y el comando real del proyecto**
— no uno inventado que dé verde vacío.

| Tier | Qué | Cuándo | Cómo |
|------|-----|--------|------|
| **A** | `external_ids`, fixture golden (Python puro, sin Odoo) | por-commit | `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests pipeline -q` |
| **B** | Smoke Docker (levanta Odoo real) | gate de release, **opt-in** | `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -m odoo -q` |

El smoke (`test_odoo_smoke.py`) está marcado `@pytest.mark.odoo` y el `conftest.py` lo
**salta por defecto**: solo corre con `-m odoo` explícito. Así el harness por-commit no
depende de Docker.

## Piezas (E1.0)

- **`external_ids.py`** — external IDs determinísticos de Odoo. La columna vertebral de
  la idempotencia del loader (E1.5): re-correr hace upsert, no duplica. **El formato está
  congelado acá** (`acc_<company>_<code>`, `mv_<company>_<je_id>`, `aml_<company>_<je_id>_<n>`);
  no cambiarlo. Ver el docstring del módulo.
- **`tests/fixtures/golden_slice.beancount`** — slice **curado** (no un corte por fecha):
  cubre a propósito cada naturaleza de sinceramiento (retiro, aporte, traspaso, wash
  apertura/cierre, ambiguo) + ≥1 asiento **USD** (sintético — el mirror no tiene ningún
  posting en USD). Cada asiento anota su procedencia (id Laudus / glosa).
  `test_fixture_golden.py` es el guardrail: si alguien borra un caso, se pone rojo.

## Smoke Docker (Tier B) — cómo correrlo

Requiere Docker. Usa el compose del spike (`_spike-odoo/docker-compose.yml`, referenciado
—no duplicado—; E1.1 promoverá su propio compose cuando monte el addon custom real), pero
bajo un **project name aislado** (`migration_smoke`) para no tocar los volúmenes del stack
del spike.

```bash
PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -m odoo -q
```

Levanta Odoo 18 + Postgres 16, confirma que Odoo responde en `:8069`, hace scaffold +
`--stop-after-init -i` de un addon custom mínimo (prueba que el stack acepta instalar un
addon), y **siempre baja el stack** (`down -v` sobre su project aislado) al terminar. Es
lento (~2-3 min): por eso NO corre por-commit.
