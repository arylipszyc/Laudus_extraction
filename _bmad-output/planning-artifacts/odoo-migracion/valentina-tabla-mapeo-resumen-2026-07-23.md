# Tabla de mapeo completa Laudus → Odoo — resumen

**Autora:** Valentina · **Fecha:** 2026-07-23 · **Es el insumo directo de E1 (import).**
Aplica las reglas del [mapa de normalización](valentina-mapa-normalizacion-odoo-2026-07-23.md) a las **569 cuentas**.

## Los archivos

- **`valentina-tabla-mapeo-odoo-2026-07-23.csv`** — las 569 cuentas, una por fila, con: código Laudus, entidad,
  compañía, nombre, cat2/cat3, saldo, **cuenta Odoo destino**, tipo, y las dimensiones (entidad, propiedad, socio,
  beneficiario, área, offshore/vehículo, partner), el **sinceramiento** (para ingresos) y un **flag**.
- **`valentina-tabla-mapeo-generador-2026-07-23.py`** — el script que la genera. Es determinístico (lee
  name+cat2+cat3+glosa) y **es el seed de la lógica del importador de E1** — no hay que reescribir las reglas.

## Resultado

- **569 cuentas Laudus → 336 cuentas Odoo** (−41%).
- **Dimensiones pobladas automáticamente:**
  - **propiedad/objeto (12):** Vía Gris, Reñaca, Molco, Depto Miami, Cancha de Golf, Yates (Keiki Kai, Destiny,
    Alfín II), Aviones (N225AW, N266WW, AJK, general).
  - **socio (5):** AAG, EAG, DAG, SAG, FGK.
  - **beneficiario (4):** Raquel Ventura, Jacqueline Deutsch, Patricia Deutsch, Gloria Jiménez.
  - **offshore/vehículo de inversión (18):** Leo, Tauro, MBI, Tecnión (Internacional/LLC/Limitada), Hemanext,
    W&M, FIP, FM BCI (varias series), Sade, Traspaso a Fondo Común…
- **2 compañías:** EAG (con hijas Jocelyn/Jeannette/Johanna/Jael) y RUT2 (FFCC + JAB como dimensión).

## Qué dicen los flags (casi todos son intencionales, NO errores)

| Flag | Nº | Qué significa |
|---|---|---|
| `partner-benef` | 27 | Donaciones/clubes → cuenta por naturaleza + **partner** = institución ✅ |
| `keep-1:1` | 20 | Cuentas bancarias → se mantienen (una cuenta banco es legítima) ✅ |
| `inversión-hija(F3)` | 16 | FM BCI/MBI de las hijas (1.863B c/u) → `Inversiones:*`, valuar en Fase 3 |
| `inversión(F3-valuar)` | 13 (+3 neg) | Cartera de inversión EAG (FM BCI 14,6B, MBI 14,8B+13,4B, Tecnión…) → Fase 3 |
| `revisar-ingreso` | 12 | **Único residual real** — ver abajo |
| `TC-especial` | 9 | Tarjetas de crédito → desglose de Epic 6 (mecanismo ya construido) |
| `partner-por-deudor` | 7 | Deudores/préstamos → `Préstamos/Deudores a terceros` + partner ✅ |
| `mixto-por-glosa` | 7 | Otros Ingresos → regla por-glosa transacción a transacción ✅ |
| `origen-inv(SPEC)` / `keep` / `keep-normalizado` | 10 | Orígenes de inversión (SPEC) / pasivos / activos que mapean por nombre ✅ |

## Lo que hay que revisar (no bloquea E1, pero anotarlo)

**`revisar-ingreso` (12):** mayormente cuentas en $0 (las `Resultado*` 5xxx vacías = reservadas para Fase 2; Fondos
Mutuos BCI, Latinoamericana sin movimientos). Los dos con plata: **Jhonny Guerra** (−8,2M, devolución de préstamo →
debería bajar el activo `Préstamos a terceros`, no ser ingreso) y su hijo (−0,4M). Trivial de arreglar.

**3 inversiones con saldo NEGATIVO** (`inversión…|NEGATIVO`): `Inv. Tecnion Limitada −4.784M`, `FM BCI Competitivo
serie class 0 −202M`, `serie AP 0 −26M`. Son el **error B de la auditoría de inversiones** (retiro contra el activo
sin reconocer ganancia → activo imposible). Confirmado también acá. Se corrige en Fase 3 con la posición del custodio.

## Cómo se usa (E1)

El importador lee la tabla: para cada línea Laudus, la lleva a `odoo_account` + estampa las dimensiones/partner +
el `x_laudus_account_code` (paridad). Las columnas `sinceramiento` (ingresos → capital/gasto/queda) y los flags
`TC-especial`/`mixto-por-glosa` marcan las líneas que además pasan por una regla transaccional (SPEC §3).

## Caveat honesto

Es un **primer pase determinístico de alta cobertura**, no una verdad revelada. Los clusters mecánicos
(propiedad/socio/objeto/inversión) están sólidos; los ~12 `revisar-ingreso` y el sanity-check de las contadoras
(donaciones/deudores por-institución) son el pulido final. El generador es idempotente: cambia una regla, regenera,
y la tabla se actualiza — no es trabajo manual congelado.
