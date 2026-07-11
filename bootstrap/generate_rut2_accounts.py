"""Generador one-off del árbol de cuentas RUT2 (Fondo Común) — Story 12.3.

Lee el plan real `rut2-plan-cuentas-laudus-2026-07-10.json` (357 cuentas) e
implementa el artefacto FIRMADO
`_bmad-output/planning-artifacts/clasificacion-contable-rut2-firmada-2026-07-11.md`
(§1 mapeo raíz→root/entidad + convención de path; §3 Equity de apertura;
§8 qué consume 12.3): appendea a `ledger/accounts.beancount` los 311 opens
nuevos — 309 hojas + `Equity:FFCC:Apertura` + `Equity:JAB:Apertura`.
Las 48 cuentas intermedias del plan NO se crean (la jerarquía vive en la
numeración del código).

Patrón del retirado `generate_accounts.py`: se corre UNA vez, el output
appendeado queda commiteado en `accounts.beancount` (la SoT), y este script
queda como registro / disaster-recovery-only. NO cron, NO endpoint, NO re-correr
en rutina — se auto-protege con el marcador de sección.

Uso (desde la raíz del repo):
    PYTHONUTF8=1 python bootstrap/generate_rut2_accounts.py
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bootstrap.account_mapping import slugify  # canónico — NO copiar (TRAP #1 de 12.1)

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_JSON = (
    REPO_ROOT
    / "_bmad-output"
    / "planning-artifacts"
    / "rut2-plan-cuentas-laudus-2026-07-10.json"
)
ACCOUNTS_FILE = REPO_ROOT / "ledger" / "accounts.beancount"

# Artefacto §1 — dígito de raíz → (Root Beancount, Entidad). La entidad se
# deriva del dígito, NO de categoria1. `Liabilities:JAB` NO existe (JAB sin
# raíz 2 ni 9 — su contrapartida de apertura es Equity:JAB:Apertura, §3).
ROOT_MAP: dict[str, tuple[str, str]] = {
    "1": ("Assets", "FFCC"),
    "2": ("Liabilities", "FFCC"),
    "3": ("Income", "FFCC"),
    "4": ("Expenses", "FFCC"),
    "6": ("Assets", "JAB"),
    "7": ("Income", "JAB"),
    "8": ("Expenses", "JAB"),
}

# Artefacto §4 — hojas por raíz, verificadas mecánicamente (309 AUTORITATIVO;
# el "308" del epic es deriva documentada, §6).
EXPECTED_LEAVES_PER_ROOT = {"1": 26, "2": 1, "3": 9, "4": 63, "6": 12, "7": 2, "8": 196}

# Criterio espejo EAG (story 12.3 Task 1): bank_account_id SOLO para hojas de
# raíces 1/6 cuyo nombre indica banco ("Banco *"); las Cajas NO llevan
# (precedente Assets:EAG:Caja-111001 sin UUID). bank_name derivado del nombre,
# espejo del bloque EAG (accounts.beancount:25-67: Edwards → "Banco Chile").
BANK_NAME_MAP = (("Edwards", "Banco Chile"), ("BCI", "BCI"))

SECTION_MARKER = ";; ─── RUT2 (Fondo Común) — subárbol FFCC/JAB — Story 12.3 ───"

SECTION_HEADER = f"""

{SECTION_MARKER}
;; Generado one-off por bootstrap/generate_rut2_accounts.py (2026-07-11) desde el
;; plan real rut2-plan-cuentas-laudus-2026-07-10.json según la clasificación
;; FIRMADA (clasificacion-contable-rut2-firmada-2026-07-11.md §1/§3/§8).
;; 311 opens: 309 hojas {{Root}}:{{FFCC|JAB}}:{{slug}}-{{código}} + 2 Equity de apertura.
;; Las cuentas intermedias del plan (357−309=48) NO se crean: la jerarquía vive
;; en la numeración (8→81→811). TC 871005/873005 = hojas de gasto normales
;; (estado-1, artefacto §5) — ninguna TC:Real acá.
;; Equity:FFCC:Apertura / Equity:JAB:Apertura = respaldo/plug de apertura (§3):
;; sintéticas (no existen en Laudus), cat1 PATRIMONIO no-vacía (guard 10.2),
;; cat2/3 vacías (exclusión del reporte de gastos), code sintético 9-prefix
;; (raíz 9 no existe en el libro → cero colisión bajo (entidad, code)), sin
;; bank_account_id. Regla §3.4: un plug JAB jamás se tapa con Equity FFCC (ni
;; viceversa). El monto puede ser plug grande — NO es patrimonio real (§3.5).
"""


def is_bank(number: str, name: str) -> bool:
    return number[0] in ("1", "6") and name.startswith("Banco ")


def bank_currency(name: str) -> str:
    """USD si el nombre marca US$ (espejo EAG 111011) o la palabra USD
    (611007 "Banco BCI USD FGK 19681721" — mismo marcador, otra grafía)."""
    return "USD" if ("US$" in name or re.search(r"\bUSD\b", name)) else "CLP"


def bank_name(name: str) -> str:
    for needle, resolved in BANK_NAME_MAP:
        if needle in name:
            return resolved
    raise ValueError(f"banco sin bank_name conocido: {name!r}")


def build_opens() -> tuple[list[str], dict]:
    accounts = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    assert len(accounts) == 357, f"plan: se esperaban 357 cuentas, hay {len(accounts)}"

    numbers = {a["accountNumber"] for a in accounts}
    assert len(numbers) == 357, "plan: accountNumber duplicado"
    by_number = {a["accountNumber"]: a for a in accounts}

    def is_leaf(n: str) -> bool:
        return not any(m != n and m.startswith(n) for m in numbers)

    leaves = [a for a in accounts if is_leaf(a["accountNumber"])]
    per_root = Counter(a["accountNumber"][0] for a in leaves)
    assert len(leaves) == 309, f"se esperaban 309 hojas (artefacto §6), hay {len(leaves)}"
    assert dict(per_root) == EXPECTED_LEAVES_PER_ROOT, f"distribución por raíz: {per_root}"

    def categoria(number: str, depth: int) -> str:
        """Nombre del ancestro ESTRICTO por prefijo de `depth` dígitos; si el
        nivel no existe (o la hoja vive en ese nivel, ej. hoja "13") → ""."""
        prefix = number[:depth]
        if prefix == number or prefix not in by_number:
            return ""
        return by_number[prefix]["name"]

    opens: list[str] = []
    paths: list[str] = []
    stats = {"per_root_entity": Counter(), "bank_uuids": 0, "banks": []}

    for acc in sorted(leaves, key=lambda a: a["accountNumber"]):
        number, name = acc["accountNumber"], acc["name"]
        root, entity = ROOT_MAP[number[0]]
        path = f"{root}:{entity}:{slugify(name)}-{number}"
        paths.append(path)
        stats["per_root_entity"][(root, entity)] += 1

        currencies = "CLP"
        lines = [
            f"2020-12-31 open {path} {currencies}",
            f'  code: "{number}"',
            f'  laudus_account_name: "{name}"',
            f'  laudus_categoria1: "{by_number[number[0]]["name"]}"',
            f'  laudus_categoria2: "{categoria(number, 2)}"',
            f'  laudus_categoria3: "{categoria(number, 3)}"',
        ]
        if is_bank(number, name):
            currency = bank_currency(name)
            if currency == "USD":
                lines[0] = f"2020-12-31 open {path} CLP, USD"
            lines += [
                f'  bank_account_id: "{uuid.uuid4()}"',
                f'  bank_name: "{bank_name(name)}"',
                '  bank_account_type: "cta_corriente"',
                f'  bank_account_currency: "{currency}"',
            ]
            stats["bank_uuids"] += 1
            stats["banks"].append((number, name, currency))
        opens.append("\n".join(lines))

    # Artefacto §3 — las 2 Equity de respaldo, metadata precedente TC:Real
    # (accounts.beancount:2020-2046): cat1 no-vacía, cat2/3 vacías, code
    # sintético 9-prefix, sin bank_account_id.
    for entity, code in (("FFCC", "900001"), ("JAB", "900002")):
        path = f"Equity:{entity}:Apertura"
        paths.append(path)
        opens.append(
            "\n".join(
                [
                    f"2020-12-31 open {path} CLP",
                    f'  code: "{code}"',
                    f'  laudus_account_name: "Apertura {entity} — respaldo/plug'
                    ' (sintética, no existe en Laudus)"',
                    '  laudus_categoria1: "PATRIMONIO"',
                    '  laudus_categoria2: ""',
                    '  laudus_categoria3: ""',
                ]
            )
        )

    # Unicidad post-generación (TRAP #2 de 12.1: 31 grupos de hojas comparten
    # nombre — solo el sufijo -{código} garantiza paths únicos).
    dupes = [p for p, n in Counter(paths).items() if n > 1]
    assert not dupes, f"paths duplicados post-slugify: {dupes}"
    assert len(opens) == 311, f"se esperaban 311 opens, hay {len(opens)}"

    existing = ACCOUNTS_FILE.read_text(encoding="utf-8")
    already = [p for p in paths if f"open {p} " in existing or f"open {p}\n" in existing]
    assert not already, f"paths ya presentes en accounts.beancount: {already[:5]}"

    return opens, stats


def main() -> int:
    existing = ACCOUNTS_FILE.read_text(encoding="utf-8")
    if SECTION_MARKER in existing:
        print("ABORT: el bloque RUT2 ya existe en accounts.beancount — one-off ya corrido.")
        return 1

    opens, stats = build_opens()
    with ACCOUNTS_FILE.open("a", encoding="utf-8") as f:
        f.write(SECTION_HEADER + "\n" + "\n\n".join(opens) + "\n")

    print(f"OK: {len(opens)} opens appendeados a {ACCOUNTS_FILE}")
    for (root, entity), n in sorted(stats["per_root_entity"].items()):
        print(f"  {root}:{entity}: {n}")
    print(f"  Equity: 2 (FFCC/JAB Apertura)")
    print(f"  bank_account_id minteados: {stats['bank_uuids']}")
    for number, name, currency in stats["banks"]:
        print(f"    {number} {name} [{currency}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
