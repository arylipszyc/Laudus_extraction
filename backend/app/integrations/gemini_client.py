"""GeminiClient — single point of contact with the Gemini SDK (NFR17).

Story 9.5: extracts a bank statement PDF into the canonical JSON v1.0 shape.
Only this module imports `google.genai`; all other code uses `GeminiClient`.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class GeminiExtractionError(Exception):
    """Raised when Gemini returns nothing parseable as JSON."""


@dataclass(frozen=True)
class _BankAccountHint:
    """Subset of the bank account passed to Gemini as context for extraction."""
    bank_account_id: str
    bank_name: str
    account_label: str
    account_type: str
    currency: str
    last4: str | None


_LIABILITY_TYPES = {"tarjeta_credito", "linea_credito"}


def _sign_convention_block(account_type: str) -> str:
    """Build the sign convention section based on Beancount account semantics.

    Liabilities (TC, línea de crédito): operations that INCREASE the debt are
    POSITIVE; operations that DECREASE the debt are NEGATIVE. This matches
    Beancount's natural sign for `Liabilities:*` postings.

    Assets (cta corriente / vista / ahorro): operations that DECREASE the
    balance (cargos, débitos) are NEGATIVE; operations that INCREASE it
    (abonos, depósitos) are POSITIVE.
    """
    if account_type in _LIABILITY_TYPES:
        return """**Convención de signo (CRÍTICO — esta cuenta es PASIVO en Beancount):**

   El saldo de una tarjeta de crédito o línea de crédito representa lo que
   le debés al banco. La convención es:

   - **POSITIVO (+)** — todo lo que INCREMENTA la deuda:
     · Compras (nacionales, internacionales, online)
     · Cargos automáticos (PAT — Pago Automático con Tarjeta)
     · Cuotas de compras pre-existentes que se cobran este mes (X/N con X≥1)
     · Comisiones, impuestos, intereses
     · Ajustes que aumentan deuda

   - **NEGATIVO (−)** — todo lo que DECREMENTA la deuda:
     · Pagos a la tarjeta (PAC — Pago Automático de Cuenta, transferencias del cliente)
     · Devoluciones de comercio (reversas de compra)
     · Notas de crédito / abonos
     · Ajustes que reducen deuda

   Verificación final OBLIGATORIA: `balances.closing - balances.opening`
   debe ser igual a `sum(transactions[].amount)` (con tolerancia ≤ 100 CLP
   por redondeos). Si no cuadra, REVISÁ los signos antes de devolver el JSON."""

    return """**Convención de signo (CRÍTICO — esta cuenta es ACTIVO en Beancount):**

   El saldo de una cuenta corriente / vista / ahorro representa lo que
   tenés disponible. La convención es:

   - **POSITIVO (+)** — todo lo que INCREMENTA el saldo:
     · Depósitos, transferencias recibidas
     · Abonos, intereses ganados
     · Devoluciones

   - **NEGATIVO (−)** — todo lo que DECREMENTA el saldo:
     · Cargos, débitos, pagos por transferencia
     · Comisiones, impuestos
     · Retiros

   Verificación final OBLIGATORIA: `balances.closing - balances.opening`
   debe ser igual a `sum(transactions[].amount)` (con tolerancia ≤ 100 CLP
   por redondeos). Si no cuadra, REVISÁ los signos antes de devolver el JSON."""


def _build_prompt(hint: _BankAccountHint) -> str:
    """Prompt covers the canonical shape, closed enums, sign rules, warning codes.

    Source of truth: `_bmad-output/planning-artifacts/architecture-c4.md` §4.1
    + Story 9.5 Moishe re-review patch (2026-05-06d): explicit Beancount sign
    convention by account_type, mandatory inclusion of pre-existing instalments,
    mandatory exclusion of future instalments and subtotals.
    """
    last4_clause = (
        f'La cuenta esperada termina en "{hint.last4}" (verificar match contra '
        "el PDF). Si no coincide, emite un warning con code=PARSE_AMBIGUOUS y "
        "detail explicando la discrepancia."
        if hint.last4
        else ""
    )
    sign_block = _sign_convention_block(hint.account_type)
    is_liability = hint.account_type in _LIABILITY_TYPES
    purchase_sign = "+" if is_liability else "−"
    payment_sign = "−" if is_liability else "+"

    return f"""Eres un extractor estructurado de cartolas bancarias chilenas.

Recibes un PDF de cartola/estado de cuenta y debes devolver EXCLUSIVAMENTE un JSON
válido que cumple el siguiente shape canónico v1.0. NO incluyas explicaciones,
markdown, ni texto fuera del JSON.

CONTEXTO DE LA CUENTA (provisto por el sistema, NO lo busques en el PDF):
- bank_account_id: "{hint.bank_account_id}"
- bank_name: "{hint.bank_name}"
- account_label: "{hint.account_label}"
- account_type: "{hint.account_type}"
- currency (top-level): "{hint.currency}"
- entity: USA "EAG" como fallback (el sistema lo sobrescribirá server-side).
{last4_clause}

REGLAS:

1. {sign_block}

2. **Inclusión OBLIGATORIA — líneas que afectan el saldo del período:**

   a. **Compras del período** — todas las operaciones de la sección principal
      (típicamente "DETALLE DE OPERACIONES DEL PERÍODO" o equivalente). NO omitir.

   b. **Cuotas pre-existentes que se cobran este mes** — sección típicamente
      llamada "INFORMACION COMPRAS EN CUOTAS" o "CUOTAS EN PROCESO". Las líneas
      con `X/N` donde **X ≥ 1** representan cuotas que se están cobrando ahora.
      Para cada una:
      - amount = `VALOR CUOTA MENSUAL` (con el signo de COMPRA según convención: {purchase_sign})
      - date = la fecha de operación original (col FECHA OPERACIÓN si existe;
        si no, primer día del período)
      - description = descripción del comercio + sufijo " (cuota X/N)"

   c. **Comisiones, impuestos, intereses** — sección típicamente "CARGOS,
      COMISIONES, IMPUESTOS Y ABONOS". Cada línea es una transaction
      (signo de CARGO según convención: {purchase_sign}).

   d. **Pagos del cliente a la cuenta** — PAC (Pago Automático de Cuenta),
      transferencias del cliente, abonos. Signo: {payment_sign}.

3. **Exclusión OBLIGATORIA — NO incluir como transactions:**

   a. **Cuotas FUTURAS** — líneas con `X/N` donde **X = 0** o "00/N". Estas
      indican proyecciones que se cobrarán en próximos meses, NO se cobran ahora.
      Sección típica: "INFORMACION COMPRAS EN CUOTAS EN PERIODO" donde aparece
      el calendario de cuotas a futuro.

   b. **Subtotales / totales** — líneas que dicen "TOTAL TARJETA XXXX",
      "TOTAL PAGOS A LA CUENTA", "TOTAL PAT", "TOTAL OPERACIONES",
      "TOTAL COMPRAS EN CUOTAS", "MONTO FACTURADO A PAGAR", etc. Son agregados,
      no transactions individuales.

4. **transactions[].line_no:** numeración secuencial empezando en 1 según el
   orden en el PDF. Único por transaction.

5. **transactions[].currency:** la moneda de cada línea individual. Casi siempre
   coincide con currency top-level; sólo difiere en TC con cargos en USD que
   aparecen en cartola CLP.

6. **transactions[].date:** ISO 8601 (YYYY-MM-DD). Si el PDF muestra DD/MM/YYYY
   o DD-MM-YY, convertir. **CRÍTICO**: prestá atención al año — si el PDF muestra
   sólo "DD/MM" o "DD-MM" (típico en TC chilenas), inferí el año del período.
   NO inventes fechas de años pasados arbitrarios.

7. **transactions[].description:** texto crudo de la cartola, sin normalizar.

8. **transactions[].raw:** opcional pero recomendado. Campos útiles:
   `merchant_country` (CL/US/...), `operation_type` (compra/pago/cuota/comision),
   `cuotas` ("X/N"), `valor_cuota`, etc.

9. **balances.opening / balances.closing (CRÍTICO — fuente de errores comunes):**

   - `balances.opening` = saldo de la cuenta al INICIO del período. En tarjetas
     de crédito chilenas viene típicamente etiquetado como "SALDO ANTERIOR",
     "MONTO FACTURADO ANTERIOR", "SALDO PERIODO ANTERIOR" o "DEUDA ANTERIOR".
     **NO uses 0 por default** — buscá esos labels. Si el saldo anterior fue
     pagado en el período (vía PAC), el opening sigue siendo el monto anterior;
     el pago aparece como transaction (signo {payment_sign}), no se "cancela"
     con el opening.

   - `balances.closing` = saldo al FIN del período. Etiquetas comunes:
     "MONTO FACTURADO A PAGAR", "NUEVO SALDO", "SALDO ACTUAL", "DEUDA TOTAL".

   - Convención de signo en balances: para PASIVOS (TC, línea de crédito)
     el saldo es el monto adeudado, expresado como POSITIVO (deuda). Para
     ACTIVOS (cta corriente/vista/ahorro), el saldo disponible es POSITIVO.

10. **period.start / period.end:** fechas del período de la cartola (ISO 8601).
    Verificar que period.start ≤ first_tx.date y last_tx.date ≤ period.end.

11. **extraction.model:** "{DEFAULT_MODEL}".

12. **extraction.warnings[]:** sólo emite warnings de los siguientes códigos:
    - LOW_CONFIDENCE: alguna línea con datos ambiguos o ilegibles.
    - PARSE_AMBIGUOUS: estructura del PDF inusual; revisar detalle.
    Los códigos DUPLICATE_LINE, ZERO_AMOUNT, LARGE_AMOUNT, PERIOD_MISMATCH y
    BALANCE_MISMATCH los detecta el backend en post-process — NO los emitas tú.

ENUMS CERRADOS:

- account_type ∈ {{"tarjeta_credito", "cta_corriente", "cta_vista", "cta_ahorro", "linea_credito"}}
- currency ∈ {{"CLP", "USD", "EUR"}}
- warning code ∈ {{"DUPLICATE_LINE", "ZERO_AMOUNT", "LARGE_AMOUNT", "LOW_CONFIDENCE", "PARSE_AMBIGUOUS", "PERIOD_MISMATCH", "BALANCE_MISMATCH"}}

SHAPE EXACTO (ejemplo, account_type=tarjeta_credito):

{{
  "schema_version": "1.0",
  "source": {{
    "bank_account_id": "{hint.bank_account_id}",
    "bank_name": "{hint.bank_name}",
    "account_label": "{hint.account_label}",
    "account_type": "{hint.account_type}",
    "entity": "EAG"
  }},
  "period": {{"start": "2026-03-01", "end": "2026-03-31"}},
  "currency": "{hint.currency}",
  "balances": {{"opening": 1000000.00, "closing": 1850000.00}},
  "transactions": [
    {{
      "line_no": 1,
      "date": "2026-03-05",
      "description": "SUPERMERCADO JUMBO",
      "amount": 45000.00,
      "currency": "{hint.currency}",
      "raw": {{"merchant_country": "CL", "operation_type": "compra"}}
    }},
    {{
      "line_no": 2,
      "date": "2026-02-10",
      "description": "NETFLIX (cuota 3/6)",
      "amount": 5000.00,
      "currency": "{hint.currency}",
      "raw": {{"operation_type": "cuota", "cuotas": "3/6", "valor_cuota": "5000"}}
    }},
    {{
      "line_no": 3,
      "date": "2026-03-15",
      "description": "PAC PAGO TARJETA",
      "amount": -200000.00,
      "currency": "{hint.currency}",
      "raw": {{"operation_type": "pago"}}
    }},
    {{
      "line_no": 4,
      "date": "2026-03-31",
      "description": "COMISION MANTENIMIENTO",
      "amount": 1000.00,
      "currency": "{hint.currency}",
      "raw": {{"operation_type": "comision"}}
    }}
  ],
  "extraction": {{
    "model": "{DEFAULT_MODEL}",
    "extracted_at": "2026-04-30T15:00:00Z",
    "warnings": []
  }}
}}

Verificá ANTES de devolver: `closing(1850000) - opening(1000000) = 850000` y
`sum(45000 + 5000 + (-200000) + 1000 + ...resto compras) ≈ 850000`. Si no
cuadra, repasá signos y completitud.

Devuelve SOLAMENTE el JSON. Si no podés extraer nada confiable, devolvé el JSON
con transactions=[] y un warning LOW_CONFIDENCE explicando la razón.
"""


class GeminiClient:
    """Thin wrapper around `google.genai` for cartola PDF extraction."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL) -> None:
        from google import genai  # imported lazily so tests can mock it

        self._model = model
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY env var is required for GeminiClient"
            )
        self._client = genai.Client(api_key=key)

    @property
    def model(self) -> str:
        return self._model

    def extract_pdf(
        self,
        pdf_bytes: bytes,
        *,
        bank_account_id: str,
        bank_name: str,
        account_label: str,
        account_type: str,
        currency: str,
        last4: str | None,
    ) -> dict[str, Any]:
        """Run Gemini extraction; return the parsed JSON as a dict.

        Raises GeminiExtractionError if the response is not parseable as JSON.
        Pydantic validation of the canonical shape happens in the caller.
        """
        from google.genai import types

        hint = _BankAccountHint(
            bank_account_id=bank_account_id,
            bank_name=bank_name,
            account_label=account_label,
            account_type=account_type,
            currency=currency,
            last4=last4,
        )
        prompt = _build_prompt(hint)
        pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=[prompt, pdf_part],
            config=config,
        )
        raw = response.text or ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("GeminiClient: response is not valid JSON: %s", raw[:500])
            raise GeminiExtractionError(
                f"Gemini response is not valid JSON: {exc}"
            ) from exc
