"""Helper de escritura reusable — promover una cuenta al plan Beancount (Story 10.3).

Appendea un `open` final + metadata `laudus_categoria1/2/3` a `ledger/accounts.beancount`
(Camino A, ver D1 en la story), envuelto en el mismo andamiaje que el importer Laudus 9.4:
`acquire_lock` (mismo lock que el cron) → `bean_check` (NO-NEGOCIABLE; rollback si rojo) →
`git_commit_push` (degrada con gracia si el push falla).

**Diseñado como pieza reutilizable** — Story 9.14 (migrar bank-accounts a Beancount) reusa
`promote_account` para crear/editar cuentas bancarias con el mismo destino y garantías.

Que el code quede en `accounts.beancount` lo hace visible para `load_account_index()` del
writer, así que la próxima corrida del importer saca la cuenta de cuarentena y postea sus JEs
a la cuenta real (AC4). El backfill re-resuelve las JEs históricas (AC5).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Callable

from pipeline.importers.laudus_run import (
    _ledger_root,
    acquire_lock,
    bean_check,
    git_commit_push,
)

logger = logging.getLogger(__name__)

# Fecha-piso estable, igual que las cuentas existentes (accounts.beancount usa 2020-12-31).
# No inventar una fecha "de hoy" que preceda a las JEs históricas y rompa balances.
_OPEN_DATE = "2020-12-31"

# Cuenta Beancount válida: raíz canónica + componentes capitalizados.
_ACCOUNT_RE = re.compile(
    r"^(Assets|Liabilities|Equity|Income|Expenses)(:[A-Z0-9][A-Za-z0-9-]*)+$"
)


class PromoteError(RuntimeError):
    """`bean-check` rojo tras escribir → la escritura se revirtió, no se commiteó.

    `detail` lleva el resumen del error del loader para devolverlo en el 422.
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def is_valid_account(account: str) -> bool:
    """True si `account` es una cuenta Beancount con raíz canónica y componentes válidos."""
    return bool(_ACCOUNT_RE.match(account or ""))


def camel_leaf(name: str) -> str:
    """Nombre Laudus → componente CamelCase ASCII para la hoja de la cuenta.

    Espeja la convención de `accounts.beancount` (ej. "Mantención Vehículos" →
    "MantencionVehiculos"). Sin nombre utilizable → "Cuenta".
    """
    ascii_name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", ascii_name)
    leaf = "".join(w[:1].upper() + w[1:] for w in words)
    return leaf or "Cuenta"


def _esc(text: str) -> str:
    """Escapa una metadata para un string literal Beancount de una línea."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()


def build_open_block(
    account: str,
    code: str,
    laudus_account_name: str,
    categoria1: str,
    categoria2: str,
    categoria3: str,
) -> str:
    """Bloque `open` + metadata, espejo del formato de `accounts.beancount`."""
    return (
        f"\n{_OPEN_DATE} open {account} CLP\n"
        f'  code: "{_esc(code)}"\n'
        f'  laudus_account_name: "{_esc(laudus_account_name)}"\n'
        f'  laudus_categoria1: "{_esc(categoria1)}"\n'
        f'  laudus_categoria2: "{_esc(categoria2)}"\n'
        f'  laudus_categoria3: "{_esc(categoria3)}"\n'
    )


def promote_account(
    *,
    code: str,
    account: str,
    laudus_account_name: str,
    categoria1: str,
    categoria2: str,
    categoria3: str,
    ledger_root: Path | None = None,
    refresh_clone: Callable[[], None] | None = None,
) -> str | None:
    """Appendea el `open` final a `accounts.beancount` con lock + bean-check + git.

    Args:
        code: número de cuenta Laudus a promover.
        account: cuenta Beancount destino (ej. `Expenses:EAG:GastoNuevo-413077`).
        laudus_account_name / categoria1..3: metadata a escribir.
        ledger_root: raíz del ledger (dir que contiene `main.beancount` + `accounts.beancount`).
            Default: `_ledger_root()` (LEDGER_DIR o `<repo>/ledger`).
        refresh_clone: callable opcional que trae el clon a origin/main ANTES de escribir
            (dentro del lock, para no chocar con el push del cron). No-op en tests/local.

    Returns:
        El SHA del commit, o None si git está deshabilitado / nada que commitear.

    Raises:
        PromoteError: `bean-check` falló tras escribir → se revirtió la escritura.
        LockTimeout: no se pudo tomar el lock.
    """
    root = Path(ledger_root) if ledger_root else _ledger_root()
    accounts_path = root / "accounts.beancount"
    main_path = root / "main.beancount"
    lock_path = root / ".import.lock"

    block = build_open_block(account, code, laudus_account_name, categoria1, categoria2, categoria3)

    with acquire_lock(lock_path):
        if refresh_clone is not None:
            # Trae el clon a origin/main antes de escribir. OJO: el lock NO serializa contra el
            # cron (corre en otro proceso/disco con su propio .import.lock); si el cron pushea
            # entre este refresh y el push de abajo, el push falla non-fast-forward y se degrada
            # con gracia (CalledProcessError → el caller persiste local y avisa).
            refresh_clone()

        original = accounts_path.read_text(encoding="utf-8") if accounts_path.exists() else ""
        sep = "" if (not original or original.endswith("\n")) else "\n"
        accounts_path.write_text(original + sep + block, encoding="utf-8")

        ok, detail = bean_check(main_path)
        if not ok:
            accounts_path.write_text(original, encoding="utf-8")  # rollback — no commit
            logger.error("promote: bean-check rojo para %s → rollback: %s", code, detail)
            raise PromoteError(detail)

        sha = git_commit_push(
            root,
            ["ledger/accounts.beancount"],
            f"[promote] cuenta {code} → {categoria1}/{categoria2}/{categoria3}",
        )
        logger.info("promote: cuenta %s promovida (%s) commit=%s", code, account, sha)
        return sha
