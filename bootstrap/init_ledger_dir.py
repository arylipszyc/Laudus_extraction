"""Crea / asegura la estructura inicial de ledger/ — Story 9.1 Task 1.

Idempotente: re-correr el script no destruye archivos existentes excepto
`main.beancount` (que es el index inmutable y se reescribe siempre desde
el template canónico de architecture-c4.md §1.5).

Uso:
    python -m bootstrap.init_ledger_dir [--ledger-path PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from textwrap import dedent

DEFAULT_LEDGER_PATH = Path("ledger")

# Template literal de architecture-c4.md §1.5 + plugins de Dev Notes 9.1 +
# custom directive para la Fava extension de Story 9.0 (preservada).
MAIN_TEMPLATE = dedent('''\
    ;; ledger/main.beancount — entry point del ledger LAUDUS
    ;;
    ;; Solo declaraciones globales + includes a las subzonas. No transactions.
    ;; Ver architecture-c4.md §1.5 para el template canónico.

    option "title" "LAUDUS — EAG Family Office"
    option "operating_currency" "CLP"

    plugin "beancount.plugins.implicit_prices"
    plugin "beancount.plugins.check_commodity"
    ;; NO usar auto_accounts — explicit opens only.

    ;; Commodities declaradas — exigidas por plugin check_commodity.
    1900-01-01 commodity CLP
      name: "Peso chileno"
    1900-01-01 commodity USD
      name: "Dólar estadounidense"

    ;; Fava extension para validación bean-check pre/post edit (Story 9.0)
    2021-01-01 custom "fava-extension" "fava_edit_validator"

    include "accounts.beancount"
    include "opening-2021.beancount"
    include "prices.beancount"
    include "imports/laudus/*.beancount"
    include "imports/cartolas/*.beancount"
    include "imports/_new-accounts-pending.beancount"
    include "manual/*.beancount"
''')

# Placeholders mínimos. Cada uno con header explicativo.
PLACEHOLDERS: dict[str, str] = {
    "opening-2021.beancount": dedent('''\
        ;; ledger/opening-2021.beancount — saldos iniciales 2021-01-01
        ;;
        ;; Generado por bootstrap/generate_opening_balances.py (Task 3 de Story 9.1).
        ;; Hasta que ese script corra, este archivo está vacío.
    '''),
    "prices.beancount": dedent('''\
        ;; ledger/prices.beancount — placeholder vacío
        ;;
        ;; Bajo Q4 (decisión 2026-05-05, FX Opción D cartola-derivada), las price
        ;; directives reales se derivan automáticamente de las Transactions con `@@`
        ;; notation vía plugin `implicit_prices` (Story 9.6b). Este archivo queda
        ;; vacío por consistencia formal con el template de main.beancount.
    '''),
    "imports/_new-accounts-pending.beancount": dedent('''\
        ;; ledger/imports/_new-accounts-pending.beancount
        ;;
        ;; Cuentas detectadas por el importer Laudus (Story 9.4) que NO existen
        ;; todavía en accounts.beancount. Cada entrada es un `open` tentativo +
        ;; sus JEs llevan tag #pending-account hasta que Ary las promueva
        ;; manualmente al accounts.beancount con su Cat1/2/3 + bank metadata.
        ;; Vacío en estado inicial.
    '''),
    "imports/laudus/_init.beancount": dedent('''\
        ;; ledger/imports/laudus/_init.beancount — placeholder para que el glob
        ;; `include "imports/laudus/*.beancount"` matchee algún archivo aún
        ;; cuando todavía no se ejecutó el importer Laudus (Story 9.4).
        ;; El importer escribe `imports/laudus/YYYY-MM.beancount` por mes;
        ;; este archivo queda inocuo en producción.
    '''),
    "imports/cartolas/_init.beancount": dedent('''\
        ;; ledger/imports/cartolas/_init.beancount — placeholder para que el
        ;; glob `include "imports/cartolas/*.beancount"` matchee algún archivo
        ;; aún cuando todavía no se procesó ninguna cartola (Story 9.6).
        ;; El importer escribe `imports/cartolas/{slug}.beancount` por cartola
        ;; promovida desde staging; este archivo queda inocuo en producción.
    '''),
}

DIRS_TO_ENSURE = [
    "imports",
    "imports/laudus",
    "imports/cartolas",
    "imports/cartolas/_staging",  # gitignored — Story 9.5
    "manual",
    "_meta",
]


def init_ledger(ledger_path: Path) -> dict:
    """Asegura estructura del ledger. Retorna summary de lo que hizo."""
    summary = {"created_dirs": [], "created_files": [], "rewrote_main": False}

    ledger_path.mkdir(parents=True, exist_ok=True)

    for rel in DIRS_TO_ENSURE:
        d = ledger_path / rel
        if not d.exists():
            d.mkdir(parents=True)
            summary["created_dirs"].append(str(rel))
        # .gitkeep para que git rastree los directorios vacíos.
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    main_path = ledger_path / "main.beancount"
    main_path.write_text(MAIN_TEMPLATE, encoding="utf-8")
    summary["rewrote_main"] = True

    for rel, content in PLACEHOLDERS.items():
        p = ledger_path / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            summary["created_files"].append(str(rel))

    accounts = ledger_path / "accounts.beancount"
    if not accounts.exists():
        accounts.write_text(
            dedent('''\
                ;; ledger/accounts.beancount — placeholder
                ;;
                ;; Generado por bootstrap/generate_accounts.py (Task 2 de Story 9.1).
                ;; Hasta que ese script corra con las 293 cuentas reales, este
                ;; archivo está vacío y bean-check fallará por cuentas no abiertas
                ;; si hay transactions que las referencian.
            '''),
            encoding="utf-8",
        )
        summary["created_files"].append("accounts.beancount")

    return summary


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger-path",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help="Ruta a la raíz del ledger (default: ./ledger)",
    )
    args = parser.parse_args()

    summary = init_ledger(args.ledger_path)
    print(f"Ledger root: {args.ledger_path.resolve()}")
    print(f"Rewrote main.beancount: {summary['rewrote_main']}")
    if summary["created_dirs"]:
        print("Created directories:")
        for d in summary["created_dirs"]:
            print(f"  + {d}/")
    if summary["created_files"]:
        print("Created placeholder files:")
        for f in summary["created_files"]:
            print(f"  + {f}")
    if not summary["created_dirs"] and not summary["created_files"]:
        print("All directories and placeholders already existed (idempotent re-run).")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
