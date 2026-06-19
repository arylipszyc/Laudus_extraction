"""Log de correcciones de categorización — Story 9.7 AC2/AC4/AC7.

`ledger/_meta/categorization-history.jsonl` es append-only: cada corrección del contador
(vía PATCH .../category) agrega una línea. La regla supra (≥30 correcciones a la misma
categoría para una `description_normalized`) y el historical match (1-29) leen de acá.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pipeline.importers.categorization.normalizer import normalize


def build_record(*, description: str, corrected_category: str, original_suggestion: str | None,
                 user: str, ts: str | None = None) -> dict:
    """Construye una entrada de corrección (la `description_normalized` se calcula acá)."""
    return {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "description_normalized": normalize(description),
        "corrected_category": corrected_category,
        "original_suggestion": original_suggestion,
        "user": user,
    }


def append_correction(jsonl_path: str | Path, record: dict) -> None:
    path = Path(jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


class CategorizationHistory:
    """Índice in-memory de correcciones por `description_normalized` (cargado al instanciar)."""

    def __init__(self, jsonl_path: str | Path) -> None:
        self._path = Path(jsonl_path)
        # description_normalized → Counter({category: n})
        self._by_desc: dict[str, Counter] = defaultdict(Counter)
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            desc = rec.get("description_normalized")
            cat = rec.get("corrected_category")
            if desc and cat:
                self._by_desc[desc][cat] += 1

    def count_for(self, description_normalized: str, category_account: str) -> int:
        return self._by_desc.get(description_normalized, Counter())[category_account]

    def dominant_category(self, description_normalized: str) -> tuple[str | None, int]:
        """(categoría más corregida, su conteo) para esa description, o (None, 0)."""
        counter = self._by_desc.get(description_normalized)
        if not counter:
            return None, 0
        category, count = counter.most_common(1)[0]
        return category, count
