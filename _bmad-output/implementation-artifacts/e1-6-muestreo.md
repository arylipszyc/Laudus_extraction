# E1.6 — Muestreo dirigido (FR12d) para firma

Selección determinística: 20 asientos de mayor monto + 20 aleatorios (seed 20260723, pinneada). Moves en la muestra: **5**.

Las columnas *Odoo* están LEÍDAS de Odoo (cuenta, montos, partner, dims — no del payload); las *esperado* salen del payload de la cadena. Cada línea se parea por su identidad `aml_*`, no por posición. Revisar cada asiento a mano contra Laudus (cuenta + partner + dimensión) y firmar al pie.

## mv_rut2_3994 — RUT2 · JE 3994 · 2022-10-04

Glosa: JE 3980

| # | código | cuenta esperada (payload) | cuenta Odoo (real) | debit (esperado / Odoo) | credit (esperado / Odoo) | moneda | partner (esperado / Odoo) | dims (Odoo) |
|---|--------|---------------------------|--------------------|------------------------|-------------------------|--------|---------------------------|-------------|
| 0 | 111005 | acc_rut2_111005 | Bancos:Banco BCI - 28981162 | 0 / 0.00 | 3660000000.00 / 3660000000.00 | CLP | — / — | FFCC |
| 1 | 310011 | acc_rut2_310011 | Assets:FFCC:InversionesSade | 3660000000.00 / 3660000000.00 | 0 / 0.00 | CLP | — / — | FFCC |

## mv_eag_1237 — EAG · JE 1237 · 2022-03-23

Glosa: JE 1234

| # | código | cuenta esperada (payload) | cuenta Odoo (real) | debit (esperado / Odoo) | credit (esperado / Odoo) | moneda | partner (esperado / Odoo) | dims (Odoo) |
|---|--------|---------------------------|--------------------|------------------------|-------------------------|--------|---------------------------|-------------|
| 0 | 111005 | acc_eag_111005 | 111005 Bancos:Banco BCI - 10160175 | 1022700000.00 / 1022700000.00 | 0 / 0.00 | CLP | — / — | EAG |
| 1 | 310013 | accs_eag_assetseaginvtecnion | assetseaginvtecnion Assets:EAG:InvTecnion | 0 / 0.00 | 1022700000.00 / 1022700000.00 | CLP | — / — | EAG |
| 2 | 610005 | acc_eag_610005 | 610005 Bancos:Banco BCI 28977581 Jocelyn | 170450000.00 / 170450000.00 | 0 / 0.00 | CLP | — / — | Jocelyn |
| 3 | 670011 | accs_eag_assetsjocelyninvtecnion | assetsjocelyninvtecnion Assets:Jocelyn:InvTecnion | 0 / 0.00 | 170450000.00 / 170450000.00 | CLP | — / — | Jocelyn |
| 4 | 710005 | acc_eag_710005 | 710005 Bancos:Banco BCI 28981600 - Jeannette | 170450000.00 / 170450000.00 | 0 / 0.00 | CLP | — / — | Jeannette |
| 5 | 770011 | accs_eag_assetsjeannetteinvtecnion | assetsjeannetteinvtecnion Assets:Jeannette:InvTecnion | 0 / 0.00 | 170450000.00 / 170450000.00 | CLP | — / — | Jeannette |
| 6 | 810005 | acc_eag_810005 | 810005 Bancos:Banco BCI 28981618 - Johanna | 170450000.00 / 170450000.00 | 0 / 0.00 | CLP | — / — | Johanna |
| 7 | 870011 | accs_eag_assetsjohannainvtecnion | assetsjohannainvtecnion Assets:Johanna:InvTecnion | 0 / 0.00 | 170450000.00 / 170450000.00 | CLP | — / — | Johanna |
| 8 | 910005 | acc_eag_910005 | 910005 Bancos:Banco BCI 28980981 - Jael | 170450000.00 / 170450000.00 | 0 / 0.00 | CLP | — / — | Jael |
| 9 | 970011 | accs_eag_assetsjaelinvtecnion | assetsjaelinvtecnion Assets:Jael:InvTecnion | 0 / 0.00 | 170450000.00 / 170450000.00 | CLP | — / — | Jael |

## mv_eag_4158 — EAG · JE 4158 · 2024-11-22

Glosa: JE 4138

| # | código | cuenta esperada (payload) | cuenta Odoo (real) | debit (esperado / Odoo) | credit (esperado / Odoo) | moneda | partner (esperado / Odoo) | dims (Odoo) |
|---|--------|---------------------------|--------------------|------------------------|-------------------------|--------|---------------------------|-------------|
| 0 | 111005 | acc_eag_111005 | 111005 Bancos:Banco BCI - 10160175 | 32160000.00 / 32160000.00 | 0 / 0.00 | CLP | — / — | EAG |
| 1 | 310016 | acc_eag_310016 | 310016 Income:Retiros Inv. Nuevo Ciclo | 0 / 0.00 | 32160000.00 / 32160000.00 | CLP | — / — | EAG |

## mv_eag_29 — EAG · JE 29 · 2021-01-05

Glosa: JE 29

| # | código | cuenta esperada (payload) | cuenta Odoo (real) | debit (esperado / Odoo) | credit (esperado / Odoo) | moneda | partner (esperado / Odoo) | dims (Odoo) |
|---|--------|---------------------------|--------------------|------------------------|-------------------------|--------|---------------------------|-------------|
| 0 | 111007 | acc_eag_111007 | 111007 Bancos:Banco Edwards - 01-62-338082 | 106000.00 / 106000.00 | 0 / 0.00 | CLP | — / — | EAG |
| 1 | 310099 | acc_eag_310099 | 310099 Income:Otros Ingresos | 0 / 0.00 | 106000.00 / 106000.00 | CLP | — / — | EAG |

## mv_eag_9000003 — EAG · JE 9000003 · 2021-02-10

Glosa: Compra USD sintética (fuerza amount_currency para E1.5)

| # | código | cuenta esperada (payload) | cuenta Odoo (real) | debit (esperado / Odoo) | credit (esperado / Odoo) | moneda | partner (esperado / Odoo) | dims (Odoo) |
|---|--------|---------------------------|--------------------|------------------------|-------------------------|--------|---------------------------|-------------|
| 0 | 111003 | acc_eag_111003 | 111003 Caja USD | 80000 / 80000.00 | 0 / 0.00 | USD (100.0) | — / — | EAG |
| 1 | 111005 | acc_eag_111005 | 111005 Bancos:Banco BCI - 10160175 | 0 / 0.00 | 80000.00 / 80000.00 | CLP | — / — | EAG |

## Firma

| Revisor | Resultado (OK / observaciones) | Fecha | Firma |
|---------|--------------------------------|-------|-------|
| Ary |  |  |  |
| Valentina |  |  |  |

## Anexo — Cobertura de glosa (winston §6·B)

- cobertura sinceramiento: B=6, C=1, G=1 | sin clasificar=1 | revisar=1
- cobertura dimensionado: partners[] | planes[] | sin match=0 | revisar=0

### Histograma por glosa — patas MIXTO `sin clasificar` (E1.3)

| glosa (normalizada) | patas |
|---------------------|-------|
| traspaso de andres turski g. | 1 |
