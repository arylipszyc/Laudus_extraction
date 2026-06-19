"""Helper de escritura reusable al plan Beancount — Stories 10.3 + 9.14.

Toda escritura a `ledger/accounts.beancount` (Camino A, ver D1 en 10.3) pasa por
`apply_to_accounts`, que envuelve la mutación en el mismo andamiaje que el importer
Laudus 9.4: `acquire_lock` (mismo lock que el cron) → mutar el texto → `bean_check`
(NO-NEGOCIABLE; rollback si rojo) → `git_commit_push` (degrada con gracia si el push
falla).

Consumidores:
- **10.3** `promote_account`: appendea un `open` + metadata `laudus_categoria1/2/3`
  (promoción de cuentas en cuarentena).
- **9.14** (bank-accounts): agrega metadata bancaria a un `open` existente, escribe
  `close` para desactivar, edita `bank_name` — usando `apply_to_accounts` + los editores
  de bloque (`add_meta_to_open`, `set_open_meta`, `append_close`, `remove_close`).
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
_OPEN_LINE_RE = re.compile(r"^\d{4}-\d\d-\d\d open ")


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


def format_open(account: str, meta: dict[str, str], date: str = _OPEN_DATE) -> str:
    """Bloque `open` + metadata (orden de inserción del dict), espejo de accounts.beancount."""
    lines = [f"\n{date} open {account} CLP"]
    for key, value in meta.items():
        lines.append(f'  {key}: "{_esc(value)}"')
    return "\n".join(lines) + "\n"


def build_open_block(
    account: str,
    code: str,
    laudus_account_name: str,
    categoria1: str,
    categoria2: str,
    categoria3: str,
) -> str:
    """Bloque `open` de una cuenta promovida (10.3) — espejo del formato de accounts.beancount."""
    return format_open(account, {
        "code": code,
        "laudus_account_name": laudus_account_name,
        "laudus_categoria1": categoria1,
        "laudus_categoria2": categoria2,
        "laudus_categoria3": categoria3,
    })


# ── Editores de bloque `open` (para 9.14) ────────────────────────────────────


def _block_span(lines: list[str], predicate: Callable[[list[str]], bool]) -> tuple[int, int] | None:
    """Rango [start, end) de líneas del bloque `open` donde predicate(block_lines) es True.

    Un bloque va de una línea `open` hasta (sin incluir) la primera línea no indentada.
    """
    i, n = 0, len(lines)
    while i < n:
        if _OPEN_LINE_RE.match(lines[i]):
            j = i + 1
            while j < n and (lines[j].startswith(" ") or lines[j].startswith("\t")):
                j += 1
            if predicate(lines[i:j]):
                return i, j
            i = j
        else:
            i += 1
    return None


def _has_meta(block: list[str], key: str, value: str) -> bool:
    return any(re.match(rf'^\s*{re.escape(key)}:\s*"{re.escape(value)}"\s*$', ln) for ln in block)


def add_meta_to_open(text: str, code: str, meta: dict[str, str]) -> str:
    """Agrega líneas de metadata al `open` cuyo `code` coincide (sin duplicar claves presentes)."""
    lines = text.splitlines()
    span = _block_span(lines, lambda b: _has_meta(b, "code", code))
    if span is None:
        raise PromoteError(f"no se encontró un open con code {code!r} en accounts.beancount")
    start, end = span
    present = {re.match(r"^\s*([A-Za-z_][\w-]*):", ln).group(1)
               for ln in lines[start:end] if re.match(r"^\s*([A-Za-z_][\w-]*):", ln)}
    new_meta = [f'  {k}: "{_esc(v)}"' for k, v in meta.items() if k not in present]
    lines[end:end] = new_meta
    return "\n".join(lines) + "\n"


def set_open_meta(text: str, *, bank_account_id: str, key: str, value: str) -> str:
    """Setea (reemplaza o agrega) una metadata en el `open` con ese `bank_account_id`."""
    lines = text.splitlines()
    span = _block_span(lines, lambda b: _has_meta(b, "bank_account_id", bank_account_id))
    if span is None:
        raise PromoteError(f"no se encontró un open con bank_account_id {bank_account_id!r}")
    start, end = span
    new_line = f'  {key}: "{_esc(value)}"'
    for idx in range(start, end):
        if re.match(rf"^\s*{re.escape(key)}:", lines[idx]):
            lines[idx] = new_line
            break
    else:
        lines[end:end] = [new_line]
    return "\n".join(lines) + "\n"


def append_close(text: str, account: str, date: str) -> str:
    """Appendea una directiva `close` (desactivar una cuenta)."""
    body = text if text.endswith("\n") or not text else text + "\n"
    return body + f"\n{date} close {account}\n"


def remove_close(text: str, account: str) -> str:
    """Quita cualquier directiva `close` para esa cuenta (reactivar)."""
    pattern = re.compile(rf"^\d{{4}}-\d\d-\d\d close {re.escape(account)}\s*$")
    kept = [ln for ln in text.splitlines() if not pattern.match(ln)]
    return "\n".join(kept) + "\n"


# ── Core: lock → mutar → bean-check → rollback/commit+push ────────────────────


def apply_to_accounts(
    mutate: Callable[[str], str],
    commit_msg: str,
    *,
    ledger_root: Path | None = None,
    refresh_clone: Callable[[], None] | None = None,
) -> str | None:
    """Aplica `mutate` al texto de `accounts.beancount` con lock + bean-check + git.

    Args:
        mutate: `str -> str`, transforma el contenido actual del archivo.
        commit_msg: mensaje del commit de git.
        ledger_root: raíz del ledger (dir con `main.beancount`/`accounts.beancount`).
            Default `_ledger_root()` (LEDGER_DIR o `<repo>/ledger`).
        refresh_clone: callable opcional que trae el clon a origin/main ANTES de escribir
            (dentro del lock). No-op en tests/local.

    Returns: SHA del commit, o None si git está deshabilitado / nada que commitear.
    Raises: PromoteError (bean-check rojo → rollback), LockTimeout.
    """
    root = Path(ledger_root) if ledger_root else _ledger_root()
    accounts_path = root / "accounts.beancount"
    main_path = root / "main.beancount"
    lock_path = root / ".import.lock"

    with acquire_lock(lock_path):
        if refresh_clone is not None:
            refresh_clone()  # dentro del lock → el cron no puede pushear entre refresh y push

        original = accounts_path.read_text(encoding="utf-8") if accounts_path.exists() else ""
        accounts_path.write_text(mutate(original), encoding="utf-8")

        ok, detail = bean_check(main_path)
        if not ok:
            accounts_path.write_text(original, encoding="utf-8")  # rollback — no commit
            logger.error("apply_to_accounts: bean-check rojo → rollback: %s", detail)
            raise PromoteError(detail)

        sha = git_commit_push(root, ["ledger/accounts.beancount"], commit_msg)
        logger.info("apply_to_accounts: %s commit=%s", commit_msg, sha)
        return sha


def _append(block: str) -> Callable[[str], str]:
    """mutate que appendea `block` al final del texto (separando con newline)."""
    def _mutate(original: str) -> str:
        sep = "" if (not original or original.endswith("\n")) else "\n"
        return original + sep + block
    return _mutate


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
    """Appendea el `open` final de una cuenta promovida (10.3) — lock + bean-check + git.

    Raises: PromoteError (bean-check rojo → rollback), LockTimeout.
    """
    block = build_open_block(account, code, laudus_account_name, categoria1, categoria2, categoria3)
    return apply_to_accounts(
        _append(block),
        f"[promote] cuenta {code} → {categoria1}/{categoria2}/{categoria3}",
        ledger_root=ledger_root,
        refresh_clone=refresh_clone,
    )
