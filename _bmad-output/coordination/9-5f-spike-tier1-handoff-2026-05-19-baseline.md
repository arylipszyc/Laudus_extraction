# Validation run — 2026-05-19 23:44:22
- PDFs evaluados: 14
- Corridas por PDF: 3
- Tiempo total: 41397.1s
- Modelo Gemini: gemini-2.5-flash

## Resumen
- 🟢 Verde: 0 (0.0%)
- 🟡 Amarillo: 6 (42.9%)
- 🔴 Rojo: 8 (57.1%)

**Gate 9.6a (≥90% verde):** FAIL

## Por banco
| Banco | Total | 🟢 | 🟡 | 🔴 | % verde |
|---|---|---|---|---|---|
| BCI | 1 | 0 | 1 | 0 | 0.0% |
| Desconocido | 12 | 0 | 5 | 7 | 0.0% |
| Santander | 1 | 0 | 0 | 1 | 0.0% |

## Detalle por PDF

### 🟡 35b537ba-012d-4bee-ae1f-08f1c91062b3.pdf
- bank: Desconocido
- estable: no (drift: warning_codes)
- warnings: PARSE_AMBIGUOUS×2, PERIOD_MISMATCH×2

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 20 | 4757783.00 | 3724232.00 | -1033551.00 | 0.00 | PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 2 | 20 | 4757783.00 | 3724232.00 | -1033551.00 | 0.00 | PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 3 | 20 | 4757783.00 | 3724232.00 | -1033551.00 | 0.00 |  |  |

### 🟡 74a660fc-7332-4cea-9282-a17f549277e9.pdf
- bank: Desconocido
- estable: no (drift: warning_codes)
- warnings: PARSE_AMBIGUOUS×4, PERIOD_MISMATCH×3

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 41 | 465.59 | 8652.46 | 8186.87 | 0.00 | PARSE_AMBIGUOUS|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 2 | 41 | 465.59 | 8652.46 | 8186.87 | 0.00 | PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 3 | 41 | 465.59 | 8652.46 | 8186.87 | 0.00 | PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |

### 🟡 bci-visa-202604.pdf
- bank: BCI
- estable: sí
- warnings: PARSE_AMBIGUOUS×3, PERIOD_MISMATCH×3

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 37 | 2054314.00 | 3219948.00 | 1165634.00 | 0.00 | PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 2 | 37 | 2054314.00 | 3219948.00 | 1165634.00 | 0.00 | PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 3 | 37 | 2054314.00 | 3219948.00 | 1165634.00 | 0.00 | PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |

### 🟡 e3841a02-d81c-4cb6-b304-7bd936f26c47.pdf
- bank: Desconocido
- estable: no (drift: warning_codes)
- warnings: PARSE_AMBIGUOUS×4, PERIOD_MISMATCH×2

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 26 | 1448.79 | 465.59 | -983.20 | 0.00 | PARSE_AMBIGUOUS|PARSE_AMBIGUOUS |  |
| 2 | 26 | 1448.79 | 465.59 | -983.20 | 0.00 | PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 3 | 26 | 1448.79 | 465.59 | -983.20 | 0.00 | PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |

### 🟡 estado-de-cuenta (26).pdf
- bank: Desconocido
- estable: no (drift: n_transactions, opening, sum_amounts, warning_codes)
- warnings: PARSE_AMBIGUOUS×4

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 15 | 0.00 | 9440753.00 | 9440753.00 | 0.00 | PARSE_AMBIGUOUS|PARSE_AMBIGUOUS |  |
| 2 | 16 | 4825462.00 | 9440753.00 | 4615291.00 | 0.00 | PARSE_AMBIGUOUS |  |
| 3 | 16 | 4825462.00 | 9440753.00 | 4615291.00 | 0.00 | PARSE_AMBIGUOUS |  |

### 🟡 estado-de-cuenta (28).pdf
- bank: Desconocido
- estable: sí
- warnings: PARSE_AMBIGUOUS×6

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 32 | 1967.62 | 3217.07 | 1249.45 | 0.00 | PARSE_AMBIGUOUS|PARSE_AMBIGUOUS |  |
| 2 | 32 | 1967.62 | 3217.07 | 1249.45 | 0.00 | PARSE_AMBIGUOUS|PARSE_AMBIGUOUS |  |
| 3 | 32 | 1967.62 | 3217.07 | 1249.45 | 0.00 | PARSE_AMBIGUOUS|PARSE_AMBIGUOUS |  |

### 🔴 19e17955-b0e8-4d63-9015-ce34f8b4d471.pdf
- bank: Desconocido
- estable: no (drift: n_transactions, sum_amounts, warning_codes)
- warnings: BALANCE_MISMATCH×2, PARSE_AMBIGUOUS×7, PERIOD_MISMATCH×3

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 51 | 8652.46 | 26188.93 | 12144.63 | 5391.84 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PARSE_AMBIGUOUS|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 2 | 93 | 8652.46 | 26188.93 | 17536.47 | 0.00 | PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 3 | 51 | 8652.46 | 26188.93 | 12144.63 | 5391.84 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PARSE_AMBIGUOUS|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |

### 🔴 estado-de-cuenta (21).pdf
- bank: Desconocido
- estable: no (drift: opening)
- warnings: BALANCE_MISMATCH×3, PARSE_AMBIGUOUS×3, PERIOD_MISMATCH×3

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 76 | 604143.00 | 17045465.00 | 14986643.00 | 1454679.00 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 2 | 76 | 604143.00 | 17045465.00 | 14986643.00 | 1454679.00 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 3 | 76 | 628565.00 | 17045465.00 | 14986643.00 | 1430257.00 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |

### 🔴 estado-de-cuenta (22).pdf
- bank: Desconocido
- estable: no (drift: n_transactions, opening, sum_amounts)
- warnings: BALANCE_MISMATCH×3, PARSE_AMBIGUOUS×3, PERIOD_MISMATCH×3

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 35 | 1379906.00 | 2058822.00 | -6979478.00 | 7658394.00 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 2 | 34 | 604143.00 | 2058822.00 | 2058822.00 | -604143.00 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 3 | 35 | 1379906.00 | 2058822.00 | -6979478.00 | 7658394.00 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |

### 🔴 estado-de-cuenta (23).pdf
- bank: Desconocido
- estable: no (drift: error)
- warnings: PARSE_AMBIGUOUS×4

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  | TimeoutError:  |
| 2 | 12 | 1387.63 | 2234.84 | 847.21 | 0.00 | PARSE_AMBIGUOUS|PARSE_AMBIGUOUS |  |
| 3 | 12 | 1387.63 | 2234.84 | 847.21 | 0.00 | PARSE_AMBIGUOUS|PARSE_AMBIGUOUS |  |

### 🔴 estado-de-cuenta (24).pdf
- bank: Desconocido
- estable: no (drift: error)
- warnings: DUPLICATE_LINE×8, PARSE_AMBIGUOUS×4, PERIOD_MISMATCH×2

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 41 | 14774.29 | 1387.63 | -13386.66 | 0.00 | DUPLICATE_LINE|DUPLICATE_LINE|DUPLICATE_LINE|DUPLICATE_LINE|PARSE_AMBIGUOUS|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 2 | 41 | 14774.29 | 1387.63 | -13386.66 | 0.00 | DUPLICATE_LINE|DUPLICATE_LINE|DUPLICATE_LINE|DUPLICATE_LINE|PARSE_AMBIGUOUS|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 3 |  |  |  |  |  |  | TimeoutError:  |

### 🔴 estado-de-cuenta (25).pdf
- bank: Desconocido
- estable: no (drift: opening, warning_codes)
- warnings: BALANCE_MISMATCH×2, LOW_CONFIDENCE×1, PARSE_AMBIGUOUS×3, PERIOD_MISMATCH×3

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 23 | 0.00 | 8986948.00 | -453805.00 | 9440753.00 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 2 | 23 | 9440753.00 | 8986948.00 | -453805.00 | 0.00 | LOW_CONFIDENCE|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 3 | 23 | 0.00 | 8986948.00 | -453805.00 | 9440753.00 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |

### 🔴 estado-de-cuenta (27).pdf
- bank: Desconocido
- estable: no (drift: opening, closing, warning_codes)
- warnings: BALANCE_MISMATCH×2, LOW_CONFIDENCE×2, PARSE_AMBIGUOUS×4

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 0.00 | 0.00 | -3150.82 | 3150.82 | BALANCE_MISMATCH|LOW_CONFIDENCE|PARSE_AMBIGUOUS |  |
| 2 | 3 | 0.00 | 0.00 | -3150.82 | 3150.82 | BALANCE_MISMATCH|LOW_CONFIDENCE|PARSE_AMBIGUOUS |  |
| 3 | 3 | 3217.07 | 66.25 | -3150.82 | 0.00 | PARSE_AMBIGUOUS|PARSE_AMBIGUOUS |  |

### 🔴 santander-mastercard-202604.pdf
- bank: Santander
- estable: no (drift: error)
- warnings: BALANCE_MISMATCH×2, PARSE_AMBIGUOUS×5, PERIOD_MISMATCH×2

| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |
|---|---|---|---|---|---|---|---|
| 1 | 36 | 319523.00 | 4448873.00 | 3877849.00 | 251501.00 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PARSE_AMBIGUOUS|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |
| 2 |  |  |  |  |  |  | TimeoutError:  |
| 3 | 45 | 319523.00 | 4448873.00 | -12596592.00 | 16725942.00 | BALANCE_MISMATCH|PARSE_AMBIGUOUS|PARSE_AMBIGUOUS|PERIOD_MISMATCH |  |

## Sign distribution (agregado, primera corrida de cada PDF)
| Banco | %positivos | %negativos | %ceros |
|---|---|---|---|
| BCI | 97.3% | 2.7% | 0.0% |
| Desconocido | 95.9% | 4.1% | 0.0% |
| Santander | 100.0% | 0.0% | 0.0% |
