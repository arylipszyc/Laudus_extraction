"""Normalizador de descripciones de transacción — Story 9.7 AC10.

Produce una key estable para agrupar descripciones equivalentes (para la regla supra y el
historical match). Dos descripciones que solo difieren en mayúsculas, espacios, puntuación
común, un sufijo numérico largo (folio/operación) o el prefijo "REF " colapsan a la misma key.

Algoritmo (en orden):
  1. uppercase + strip
  2. quitar prefijo "REF " (referencia bancaria)
  3. remover puntuación común `. , ; : #`
  4. colapsar espacios múltiples a uno
  5. remover un grupo de dígitos finales si tiene > 4 dígitos (folio/nro de operación;
     se preservan montos cortos como "24" que pueden ser parte del nombre)
"""
from __future__ import annotations

import re

_PUNCT = str.maketrans("", "", ".,;:#")
_TRAILING_DIGITS = re.compile(r"\s*\d{5,}$")
_WS = re.compile(r"\s+")


def normalize(description: str) -> str:
    s = (description or "").upper().strip()
    if s.startswith("REF "):
        s = s[4:]
    s = s.translate(_PUNCT)
    s = _WS.sub(" ", s).strip()
    s = _TRAILING_DIGITS.sub("", s).strip()
    return s
