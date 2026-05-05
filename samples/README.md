# samples/ — Cartolas y fixtures locales

Carpeta **gitignored** para archivos sample con datos personales reales
(cartolas PDF de tarjetas de crédito, etc.) que se usan para validar
desarrollos contra shape real pero **no se versionan al repo**.

## Política operativa

Decisión Ary 2026-05-05:

- Las cartolas reales viven acá **solo hasta que la story que las consume
  esté 100% conciliada** (smoke test verde, conciliación cartola↔Laudus
  exacta).
- Una vez conciliada → **borrar el PDF**. Si alguien (Eduardo, Valentina,
  auditor externo) necesita revisar la cartola después, la re-descarga
  directamente del banco.
- Para CI / tests automatizados: usar fixtures sintéticas (JSONs construidos
  a mano que reproducen el shape sin datos reales). Las cartolas reales son
  solo para smoke local manual.

## Convención de nombres

```
samples/{banco}-{producto}-{YYYYMM}.pdf
```

Ejemplos:
- `samples/santander-mastercard-202604.pdf`
- `samples/bci-visa-202604.pdf`

## Stories que usan esta carpeta

- **Story 9.5** — PDF upload + Gemini → JSON canónico. Smoke local con
  cartolas reales para validar que el prompt Gemini devuelve el shape
  v1.0 correcto.
