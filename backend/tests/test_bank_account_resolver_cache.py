"""Tests de `resolver_for` — el resolver cacheado por path (D7).

Cubre lo que el review de D7 dejó sin blindar: que el cache no parsee eager (regresión
`500`-vs-`200 []` con archivo ausente), que reuse la misma instancia, y que se invalide
cuando `accounts.beancount` cambia.
"""
from pipeline.importers.bank_account_resolver import (
    BankAccountResolver,
    resolver_for,
)

_ACCOUNTS = """\
2020-12-31 open Liabilities:EAG:TC:VisaInfinity-430005 CLP
  bank_account_id: "card-1"
  bank_account_type: "tarjeta_credito"
  bank_account_currency: "CLP"
"""

_ACCOUNTS_EDITED = """\
2020-12-31 open Liabilities:EAG:TC:VisaSignature-880011 CLP
  bank_account_id: "card-1"
  bank_account_type: "tarjeta_credito"
  bank_account_currency: "CLP"
"""


def test_resolver_for_missing_file_no_crash(tmp_path):
    """Regresión D7: con el archivo ausente, `resolver_for` NO parsea (es lazy) → no lanza.

    El bug era un `_ensure()` eager que parseaba en la construcción: `GET /tc/cartolas` con
    `accounts.beancount` ausente y cero cartolas devolvía `500` en vez de `200 []`.
    """
    missing = tmp_path / "accounts.beancount"  # no se escribe
    resolver = resolver_for(missing)  # no debe lanzar
    assert isinstance(resolver, BankAccountResolver)


def test_resolver_for_caches_same_instance(tmp_path):
    p = tmp_path / "accounts.beancount"
    p.write_text(_ACCOUNTS, encoding="utf-8")
    first = resolver_for(p)
    second = resolver_for(p)
    assert first is second  # mismo path + mismo (mtime, size) → misma instancia cacheada
    assert first.resolve("card-1") == "Liabilities:EAG:TC:VisaInfinity-430005"


def test_resolver_for_invalidates_on_change(tmp_path):
    p = tmp_path / "accounts.beancount"
    p.write_text(_ACCOUNTS, encoding="utf-8")
    before = resolver_for(p)
    assert before.resolve("card-1") == "Liabilities:EAG:TC:VisaInfinity-430005"

    p.write_text(_ACCOUNTS_EDITED, encoding="utf-8")  # cambia contenido y tamaño → stamp distinto
    after = resolver_for(p)
    assert after is not before
    assert after.resolve("card-1") == "Liabilities:EAG:TC:VisaSignature-880011"
