"""Persistencia append-only de hilos de comentario Owner↔Contador — Story 7.0 (habilitadora del Epic 7).

`ledger/_meta/owner-comments.jsonl` es la fuente única de los hilos de comentario sobre
transacciones (sin base de datos; mismo patrón que `discrepancy_writer.py` y los run-records).
Cada evento (`comment` raíz, `reply`, `resolution`, `anchor-heal`) es UNA línea con `thread_id`;
`read_threads` pliega las líneas por `thread_id` a hilos (última resolución gana, igual que
`list_periods` deriva el estado del último run).

**Los comentarios NO son asientos contables:** no van a ningún `.beancount`, no los lee el motor
beancount y NO pasan por `bean-check`. Son metadata de colaboración *sobre* el ledger.

## El spike que esta story resuelve: ancla resistente a re-imports

El `tx_id` (`transactions/service.py:31`) es `sha(filename, lineno, narration, amount)[:12]`: un
re-import de cartola sobrescribe el archivo entero (idempotencia por slug, Epic 6) → re-numera
líneas → `lineno` cambia → `tx_id` cambia. Un comentario anclado SOLO por `tx_id` quedaría
huérfano tras cada re-import. Por eso el ancla es de 3 capas + snapshot y se re-resuelve EN
CALIENTE en tiempo de lectura (`resolve_anchor`), sin reescribir el `tx_id` persistido:

  1. `tx_id`      — lookup primario O(1); VOLÁTIL ante re-import.
  2. `anchor_key` — `sha(date · amount · account · narration_normalizada)`; ESTABLE (datos
                    contables que el re-import preserva) → re-ancla cuando el `tx_id` ya no matchea.
  3. `tx_snapshot`— copia congelada (date/amount/currency/account/narration) para nunca mostrar un
                    hilo vacío si el ancla queda 100% huérfana.

`ledger_git_sha` se guarda como procedencia/auditoría (no participa de la resolución).

Ver ADR: `_bmad-output/planning-artifacts/adr-owner-comments-ancla-persistencia.md`.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
import uuid
from pathlib import Path

from beancount.core import data

from pipeline.importers.laudus_run import _ledger_root, acquire_lock, git_commit_push
from backend.app.api.v1.transactions.service import compute_tx_id

SCHEMA_VERSION = "1.0"


# ── Ancla capa 2: clave semántica estable (AC2) ──────────────────────────────


def _normalize_narration(narration: str) -> str:
    """Glosa → forma canónica para el `anchor_key`: sin acentos (NFKD ASCII, como `camel_leaf`
    en `beancount_promote.py:60`), minúsculas, espacios colapsados. Estable ante diferencias de
    capitalización/acentos/espaciado que una re-extracción o un re-render podrían introducir."""
    ascii_text = unicodedata.normalize("NFKD", narration or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def compute_anchor_key(date, amount, account: str, narration: str) -> str:
    """Clave semántica de respaldo = `sha256(date · amount · account · narration_normalizada)[:12]`.

    Pura y determinista. NO depende de `filename`/`lineno` → sobrevive un re-import (a diferencia
    de `tx_id`). `date` acepta `datetime.date` o string ISO; `amount` acepta Decimal/str/float
    (se estabiliza vía `str`). El mismo `(date, amount, account, narration)` con distinta
    capitalización/acentos/espaciado devuelve la MISMA key (AC2)."""
    date_str = date.isoformat() if hasattr(date, "isoformat") else str(date)
    base = f"{date_str}:{str(amount).strip()}:{account}:{_normalize_narration(narration)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]


def _tx_id_of(entry: data.Transaction) -> str:
    """Mapea un `entry` → `tx_id` (espeja `transactions/service.py:40`, reusando `compute_tx_id`)."""
    first = entry.postings[0].units.number if entry.postings and entry.postings[0].units else ""
    return compute_tx_id(entry.meta.get("filename", ""), entry.meta.get("lineno", 0),
                         entry.narration or "", first)


def _anchor_key_of(entry: data.Transaction) -> str:
    """Recomputa el `anchor_key` de un `entry` vivo (misma pata que `_tx_id_of` usa para el monto)."""
    first = entry.postings[0].units.number if entry.postings and entry.postings[0].units else ""
    account = entry.postings[0].account if entry.postings else ""
    return compute_anchor_key(entry.date, first, account, entry.narration or "")


# ── Resolvedor de ancla de 3 capas (AC3) ─────────────────────────────────────


class AnchorNotFound(Exception):
    """No hay transacción con ese `tx_id` en el ledger actual → no se puede comentar (HTTP 404)."""


def resolve_anchor(comment: dict, entries: list) -> dict:
    """Resuelve el ancla de un comentario contra los `entries` VIVOS del ledger (en caliente).

    Algoritmo de 3 capas (nunca pierde el hilo):
      1. Match por `tx_id` → exactamente uno → `status="resolved"` (el `tx_id` sigue vivo).
      2. Si falla, match por `anchor_key` recomputada sobre `entries` → exactamente uno →
         `status="re-anchored"` (+ el nuevo `tx_id`; el re-import cambió el `tx_id` pero los
         datos contables siguen). NO se reescribe el JSONL (re-resolución en caliente, decisión Ary).
      3. Cero o >1 matches (tx borrada, o `anchor_key` ambigua) → `status="orphaned"`, `entry=None`.
         El hilo NO se descarta: se muestra en modo histórico/degradado con su `tx_snapshot`.

    Devuelve `{status, tx_id, entry}`.
    """
    anchor = comment.get("anchor", comment)
    tx_id = anchor.get("tx_id")
    anchor_key = anchor.get("anchor_key")

    txns = [e for e in entries if isinstance(e, data.Transaction)]

    by_tx = [e for e in txns if _tx_id_of(e) == tx_id]
    if len(by_tx) == 1:
        return {"status": "resolved", "tx_id": tx_id, "entry": by_tx[0]}

    by_key = [e for e in txns if _anchor_key_of(e) == anchor_key]
    if len(by_key) == 1:
        entry = by_key[0]
        return {"status": "re-anchored", "tx_id": _tx_id_of(entry), "entry": entry}

    return {"status": "orphaned", "tx_id": None, "entry": None}


# ── Captura del ancla al crear un comentario (AC4/AC5) ────────────────────────


def ledger_head_sha(ledger_root=None) -> str | None:
    """SHA de `HEAD` del clon del ledger (`git -C <root> rev-parse HEAD`). Procedencia/auditoría.

    Tolerante: si git no está disponible o el dir no es un repo → `None` (no crashea). AC5."""
    root = Path(ledger_root) if ledger_root else _ledger_root()
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def build_anchor(tx_id: str, entries: list, ledger_root=None) -> dict:
    """Arma el bloque de ancla de 3 capas + snapshot para una transacción viva (helper de 7.1).

    Localiza la tx por `tx_id` (exactamente una), congela el `tx_snapshot`, computa el `anchor_key`
    (AC2) y adjunta el `ledger_git_sha` (AC5). Si el `tx_id` no resuelve → `AnchorNotFound` (no se
    puede comentar sobre una tx inexistente)."""
    matches = [e for e in entries if isinstance(e, data.Transaction) and _tx_id_of(e) == tx_id]
    if len(matches) != 1:
        raise AnchorNotFound(f"tx_id {tx_id!r} no resuelve a exactamente una transacción "
                             f"({len(matches)} matches) — no se puede anclar el comentario")
    entry = matches[0]
    posting = entry.postings[0]
    number = posting.units.number if posting.units else None
    return {
        "tx_id": tx_id,
        "ledger_git_sha": ledger_head_sha(ledger_root),
        "anchor_key": _anchor_key_of(entry),
        "tx_snapshot": {
            "date": entry.date.isoformat(),
            "amount": float(number) if number is not None else None,
            "currency": posting.units.currency if posting.units else None,
            "account": posting.account,
            "narration": entry.narration or "",
        },
    }


# ── Writer JSONL append-only (AC1) ───────────────────────────────────────────


def default_jsonl_path(ledger_root=None) -> Path:
    """Ruta por defecto del JSONL de comentarios: `<ledger>/_meta/owner-comments.jsonl`."""
    root = Path(ledger_root) if ledger_root else _ledger_root()
    return root / "_meta" / "owner-comments.jsonl"


def build_comment(*, anchor: dict, author_email: str, author_role: str, body: str, ts: str) -> dict:
    """Arma el comentario RAÍZ de un hilo (sin escribirlo). `thread_id = comment_id` (uuid4).

    `anchor` es el bloque de `build_anchor` (3 capas + snapshot). Sin dedup: cada evento es
    intencionalmente único (a diferencia de las discrepancias, que dedupean por contenido)."""
    comment_id = str(uuid.uuid4())
    return {
        "schema_version": SCHEMA_VERSION,
        "type": "comment",
        "comment_id": comment_id,
        "thread_id": comment_id,
        "anchor": anchor,
        "author_email": author_email,
        "author_role": author_role,
        "body": body,
        "ts": ts,
    }


def _append_line(record: dict, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_comment(comment: dict, path) -> None:
    """Appendea el comentario raíz (una línea `type="comment"`). `mkdir` del `_meta/` si falta."""
    _append_line(comment, path)


def append_reply(thread_id: str, reply: dict, path) -> None:
    """Appendea una respuesta que referencia el `thread_id` (línea `type="reply"`).

    `reply` = `{author_email, author_role, body, ts}` (más lo que el llamador quiera). Se le
    inyecta un `reply_id` si no lo trae."""
    record = {
        "schema_version": SCHEMA_VERSION,
        "type": "reply",
        "thread_id": thread_id,
        "reply_id": reply.get("reply_id", str(uuid.uuid4())),
        **{k: v for k, v in reply.items() if k != "reply_id"},
    }
    _append_line(record, path)


def append_resolution(thread_id: str, resolution: dict, path) -> None:
    """Appendea la resolución de un hilo (línea `type="resolution"`, patrón `discrepancy_writer:128`).

    `resolution` = `{action, resolved_by, resolved_at, ...}`. No reescribe nada; la última gana."""
    record = {
        "schema_version": SCHEMA_VERSION,
        "type": "resolution",
        "thread_id": thread_id,
        "resolution": resolution,
    }
    _append_line(record, path)


def read_threads(path, thread_id: str | None = None) -> list[dict]:
    """Pliega el JSONL a hilos `{thread_id, root, replies[], resolution|None}` (AC1).

    Agrupa por `thread_id`; el raíz es la línea `type="comment"`, las respuestas se acumulan en
    orden de archivo y la resolución es la ÚLTIMA línea `type="resolution"` (última acción gana,
    igual que `list_periods` deriva el estado del último run). `type="anchor-heal"` está modelado
    en el schema pero no se emite en esta story (re-resolución en caliente) → se ignora acá.
    Si se pasa `thread_id`, filtra a ese hilo."""
    path = Path(path)
    threads: dict[str, dict] = {}
    order: list[str] = []
    if not path.exists():
        return []
    # split("\n") — NO splitlines(): un registro se escribe con json.dumps(ensure_ascii=False)+"\n",
    # que deja crudos los separadores de línea Unicode (U+2028/U+2029/U+0085) si vienen en el body.
    # splitlines() SÍ rompe en ellos → partiría el JSON en fragmentos inválidos y el comentario se
    # perdería en silencio. split("\n") solo corta en el "\n" real que agrega el writer.
    for line in path.read_text(encoding="utf-8").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        tid = record.get("thread_id")
        if not tid:
            continue
        if tid not in threads:
            threads[tid] = {"thread_id": tid, "root": None, "replies": [], "resolution": None}
            order.append(tid)
        thread = threads[tid]
        rtype = record.get("type")
        if rtype == "comment":
            thread["root"] = record
        elif rtype == "reply":
            thread["replies"].append(record)
        elif rtype == "resolution":
            thread["resolution"] = record["resolution"]  # última gana
        # anchor-heal: ignorado en 7.0
    out = [threads[t] for t in order]
    if thread_id is not None:
        out = [t for t in out if t["thread_id"] == thread_id]
    return out


# ── Persistencia git bajo lock (AC6) ─────────────────────────────────────────


def persist_and_commit(mutate, commit_msg: str, ledger_root=None) -> str | None:
    """Envuelve una mutación del JSONL en el andamiaje de escritura del proyecto: lock → append → git.

    `mutate(path)` recibe la ruta del `owner-comments.jsonl` y hace el append (ej.
    `lambda p: append_comment(comment, p)`). Toma `.import.lock` (serializa con el cron/importer),
    corre la mutación y commitea+pushea vía `git_commit_push` (no-op si `IMPORTER_GIT_ENABLED` off).

    **Sin `bean-check`** — el JSONL NO es parte del ledger cargable (diferencia deliberada con
    `apply_to_accounts` de `beancount_promote.py`, que sí lo corre porque escribe `accounts.beancount`).
    Es la ÚNICA vía de escritura; 7.1–7.4 la consumen. Devuelve el SHA del commit (o None)."""
    root = Path(ledger_root) if ledger_root else _ledger_root()
    lock_path = root / ".import.lock"
    jsonl_path = root / "_meta" / "owner-comments.jsonl"

    with acquire_lock(lock_path):
        mutate(jsonl_path)
        return git_commit_push(root, ["ledger/_meta/owner-comments.jsonl"], commit_msg)
