"""Acceso a la tabla de mapeo Laudus → Odoo (story E1.2).

La tabla de Valentina (`valentina-tabla-mapeo-odoo-2026-07-23.csv`, 569 filas)
es la fuente del colapso del plan: cada cuenta Laudus → su cuenta Odoo destino.
Las REGLAS viven en el generador de Valentina (que produce el CSV); este módulo
solo CONSUME la tabla generada — si una regla cambia, se regenera la tabla, no
se re-deriva acá.

Claves y rarezas de la data real (verificadas contra el CSV versionado):
  - Los códigos Laudus se REPITEN entre entidades (111005 existe en EAG y en
    FFCC; 710005 en Jeannette y en JAB) → la key de lookup es `(entity, code)`.
  - `(company, code)` también es único — lo validamos al cargar porque el
    external ID congelado `acc_<company>_<code>` (E1.0) depende de eso.
  - Hay exactamente UNA fila sin código: `Expenses:EAG:Suspense`, la cuenta
    interna de cuarentena del proyecto (no viene de Laudus). Se excluye del
    universo de mapeo y queda accesible en `skipped_no_code` (pinneada en test:
    un segundo caso futuro debe fallar fuerte, no pasar en silencio).
  - Las 2 aperturas Equity sintéticas (900001 FFCC / 900002 JAB) traen la
    columna `company` vacía → la company se deriva SIEMPRE de la entity (regla
    única, la misma del generador).

Fail-loud (patrón `external_ids.py`): tabla corrupta (keys duplicadas, destino
vacío) o lookup desconocido levantan excepción con contexto — nunca degradar en
silencio un mapeo del que depende la paridad.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TABLE_PATH = (
    _REPO_ROOT
    / "_bmad-output/planning-artifacts/odoo-migracion/valentina-tabla-mapeo-odoo-2026-07-23.csv"
)

#: Entidades internas de la compañía EAG (mismo criterio del generador de
#: Valentina). Todo lo demás (FFCC, JAB) es RUT2.
EAG_ENTITIES = frozenset({"EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"})


def company_for_entity(entity: str) -> str:
    """Compañía Odoo (EAG | RUT2) de una entidad interna del mirror."""
    if not entity or not str(entity).strip():
        raise ValueError("mapping: entity vacía — no se puede derivar la compañía")
    return "EAG" if entity in EAG_ENTITIES else "RUT2"


@dataclass(frozen=True)
class MappingRow:
    """Una cuenta Laudus y su destino Odoo según la tabla."""

    code: str
    entity: str
    company: str  # derivada de entity (la columna del CSV puede venir vacía)
    name: str
    odoo_account: str
    odoo_type: str
    sinc: str  # naturaleza de sinceramiento (la aplica E1.3, acá es contexto)
    flag: str


class MappingTable:
    """Tabla de mapeo indexada por `(entity, code)`."""

    def __init__(self, rows: list[MappingRow], skipped_no_code: list[dict]):
        self.rows = rows
        self.skipped_no_code = skipped_no_code
        self._by_entity_code = {(r.entity, r.code): r for r in rows}

    def get(self, entity: str, code: str) -> MappingRow:
        key = (str(entity), str(code))
        try:
            return self._by_entity_code[key]
        except KeyError:
            raise KeyError(
                f"mapping: (entity={entity!r}, code={code!r}) no existe en la "
                f"tabla de mapeo — cuenta Laudus sin destino Odoo"
            ) from None


#: Columnas sin las cuales la tabla no es la tabla (un header renombrado haría
#: que `raw.get(...)` devuelva None en TODAS las filas — tabla vacía silenciosa).
REQUIRED_COLUMNS = frozenset({"code", "entity", "company", "odoo"})


def load_mapping_table(path: Path | str = DEFAULT_TABLE_PATH) -> MappingTable:
    """Carga y valida la tabla CSV. Fail-loud ante tabla corrupta."""
    rows: list[MappingRow] = []
    skipped: list[dict] = []
    # utf-8-sig: un re-guardado con Excel agrega BOM y el primer header pasaría
    # a ser "﻿code" — mismas consecuencias que un header renombrado.
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"mapping: a la tabla {path} le faltan las columnas "
                f"{sorted(missing)} — ¿header renombrado o archivo equivocado?"
            )
        for raw in reader:
            code = (raw.get("code") or "").strip()
            if not code:
                skipped.append(raw)
                continue
            entity = (raw.get("entity") or "").strip()
            odoo_account = (raw.get("odoo") or "").strip()
            if not entity:
                raise ValueError(f"mapping: fila con code={code!r} sin entity")
            if not odoo_account:
                raise ValueError(
                    f"mapping: cuenta Laudus (entity={entity!r}, code={code!r}) "
                    f"sin cuenta Odoo destino"
                )
            company = company_for_entity(entity)
            csv_company = (raw.get("company") or "").strip()
            if csv_company and csv_company != company:
                raise ValueError(
                    f"mapping: (entity={entity!r}, code={code!r}) trae "
                    f"company={csv_company!r} en el CSV pero la entity deriva "
                    f"{company!r} — el generador y EAG_ENTITIES divergen"
                )
            rows.append(
                MappingRow(
                    code=code,
                    entity=entity,
                    company=company,
                    name=(raw.get("name") or "").strip(),
                    odoo_account=odoo_account,
                    odoo_type=(raw.get("otype") or "").strip(),
                    sinc=(raw.get("sinc") or "").strip(),
                    flag=(raw.get("flag") or "").strip(),
                )
            )

    if not rows:
        raise ValueError(
            f"mapping: la tabla {path} no tiene filas con código — vacía o corrupta"
        )
    if len(skipped) > 1:
        raise ValueError(
            f"mapping: {len(skipped)} filas sin código (se espera a lo más 1, "
            f"Expenses:EAG:Suspense): {[r.get('name') for r in skipped]!r}"
        )
    _validate_unique(rows, key=lambda r: (r.entity, r.code), label="(entity, code)")
    _validate_unique(rows, key=lambda r: (r.company, r.code), label="(company, code)")
    return MappingTable(rows, skipped)


def _validate_unique(rows, *, key, label):
    seen = {}
    for r in rows:
        k = key(r)
        if k in seen:
            raise ValueError(
                f"mapping: key {label} duplicada en la tabla: {k!r} "
                f"({seen[k].name!r} vs {r.name!r})"
            )
        seen[k] = r
