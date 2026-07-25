"""Transformador de dimensiones analíticas + partners (story E1.4) — Tier A, SIN Odoo.

Tercer transformador de la cadena (`collapse → sincerar → dimensionar`). Agrega
el "quién" (partner) y el "sobre qué" (dimensiones analíticas) como METADATA
por línea — NO cambia cuentas, NO cambia montos, NO excluye moves. La paridad
es doblemente invariante: `run_tier_a` corre tras este transformador con el
MISMO `route`/`excluded_je_ids` que produjo E1.3 y tiene que dar idéntico.

Dos mecanismos, a propósito (winston §5.2 — partición vs disperso):
  - PARTICIÓN (socio-dueño, cuentas 115xxx FFCC): partner ledger que DEBE
    cuadrar al peso — `verify_particion` es el gate NUEVO de esta story. Es el
    "Resumen Retiros" que hoy se arma a mano. Se verifica por PARTNER, no por
    cuenta destino (115028 mapea a `Cuentas por cobrar` y aun así cuadra por
    partner DAG).
  - DISPERSO (todo lo demás): etiqueta que agrupa (deudores, donaciones,
    clubes, beneficiarios, socio-disperso, y los planes analíticos por columna
    del CSV). NUNCA se le exige sumar 100% de ninguna cuenta (AC3) — la
    métrica es visibilidad (reporte), no cobertura total (winston §6·B.4).

Fuentes de asignación de partner, en orden de precedencia:
  1. Columna `partner` del CSV (nivel cuenta) → tabla PARTNER_CANONICO.
  2. Pins por (entity, code) — filas donde el CSV deja `partner` vacío pero la
     lista de Valentina asigna igual (Jhonny 310045/310047, Raquel T/C 430019).
  3. Columna `socio` del CSV → partner socio-disperso (MISMO canónico que la
     partición — no crear duplicado; NO entra al gate de partición). Las
     personas NO van a un plan analítico: los analíticos no dan saldo y acá
     agrupan P&L (winston §5.2 "personas = partner").
  4. Glosa — SOLO alias YAML sección `personas` (nombre completo, word-boundary,
     `excluir_homonimos` vetan): beneficiarios en cuentas de gasto (caso
     Raquel) y socio-uso en retiros (plan socio_uso). Cualquier duda → sin
     estampar + reporte. NUNCA fuzzy, NUNCA substring. Scope pinneado
     (decisión Ary, review 2026-07-25): SOLO los tipos `beneficiario` y
     `socio` del YAML se evalúan por glosa — las menciones de tipos
     `deudor`/`apellido_azba` (Jhonny, Zeldis, …) NI estampan NI entran al
     reporte (esos partners se cubren por cuenta fija / pin de lista).

Los buckets dudosos (Deudores Varios, Otros hijos, CIS, Donaciones varias…)
quedan como placeholder con flag `revisar con contadoras` — nunca fusión a
ciegas (AC4). Deudores Varios es placeholder POR ENTIDAD.

Los 6 planes analíticos contenedores YA existen (E1.1, XML noupdate) y están
CONGELADOS: propiedad_objeto / area_centro / offshore_vehiculo / por_cuenta_de /
socio_uso / entidad. La dimensión entidad = `line.entity` (ya viaja en la
línea — no se duplica acá; E1.5 la convierte en analítica). El valor
`por-cuenta-de` de la columna `area` (8 filas Control y Liquidación) alimenta
el plan por_cuenta_de, no area_centro; el "por cuenta de QUIÉN" por línea no
es derivable a nivel cuenta → queda el marcador verbatim (refinar es de una
story futura, con Valentina).

Fail-loud: un valor de `partner`/`socio` del CSV sin entrada en la tabla
canónica revienta con contexto (población cerrada, patrón E1.3) — un partner
nuevo en la tabla no pasa en silencio.
"""

import dataclasses
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from pipeline.odoo_migration.mapping import MappingTable
from pipeline.odoo_migration.sincerar import (
    FLAG_REVISAR,
    LineRef,
    load_alias_table,
    normalize,
    resolve_alias,
)
from pipeline.odoo_migration.transform import (
    account_codes,
    entity_of_account,
    laudus_transactions,
)

# --- Categorías de partner (lista Valentina 2026-07-23, 4 categorías + apoyo) --

CAT_SOCIO_PARTICION = "socio-particion"
CAT_SOCIO_DISPERSO = "socio-disperso"
CAT_DEUDOR = "deudor"
CAT_RENDICION_P7 = "rendicion-p7"  # fuera de scope E1 (inventario §1.4)
CAT_DONACION = "donacion"
CAT_CLUB = "club"
CAT_BENEFICIARIO = "beneficiario"
CAT_BUCKET = "bucket"


@dataclass(frozen=True)
class PartnerSpec:
    """Partner canónico + categoría + flag. `por_entidad=True` = bucket
    placeholder que se instancia por entidad (`Deudores Varios (EAG)`, …)."""

    canonico: str
    categoria: str
    flag: str = ""
    por_entidad: bool = False


#: Valor de la columna `partner` del CSV → partner canónico. POBLACIÓN CERRADA:
#: cubre los 48 valores reales del CSV; un valor nuevo revienta en `dimensionar`
#: (test de completitud contra la tabla cargada). Colapsos y dudosos según la
#: lista de Valentina (reglas 1–5): sub-cuentas "Autos" colapsan al padre;
#: CIS / C.I. Santiago / C.I. Sefaradí son TRES partners separados hasta que
#: las contadoras confirmen; los buckets quedan placeholder + revisar.
PARTNER_CANONICO: dict[str, PartnerSpec] = {
    # -- Categoría 1: socios / cuentas corriente (PARTICIÓN, 115xxx FFCC) --
    "AAG": PartnerSpec("AAG", CAT_SOCIO_PARTICION),
    "EAG": PartnerSpec("EAG", CAT_SOCIO_PARTICION),
    "SAG": PartnerSpec("SAG", CAT_SOCIO_PARTICION),
    "DAG": PartnerSpec("DAG", CAT_SOCIO_PARTICION),
    "Cta Cte DAG - Autos": PartnerSpec("DAG", CAT_SOCIO_PARTICION),  # colapsa (regla 1)
    "AZBA": PartnerSpec("AZBA", CAT_SOCIO_PARTICION),
    "José Alazraki": PartnerSpec("José Alazraki", CAT_SOCIO_PARTICION),
    "Denise Zeldis": PartnerSpec("Denise Zeldis", CAT_SOCIO_PARTICION),
    "Denise Zeldis - Autos": PartnerSpec("Denise Zeldis", CAT_SOCIO_PARTICION),  # colapsa
    "Michelle Zeldis": PartnerSpec("Michelle Zeldis", CAT_SOCIO_PARTICION),
    "Ariel Borzutzky": PartnerSpec("Ariel Borzutzky", CAT_SOCIO_PARTICION),
    # Israel: identificar por CUENTA (115041), NUNCA por glosa (alias vacío).
    "Israel": PartnerSpec("Israel", CAT_SOCIO_PARTICION, FLAG_REVISAR),
    # Cuenta-bolsa sin persona nombrada, saldo 0 hoy (lista cat 1).
    "Otros hijos": PartnerSpec("Otros hijos", CAT_SOCIO_PARTICION, FLAG_REVISAR),
    # -- Rendiciones P-7 (115001–115007): FUERA de scope E1 — placeholder
    #    verbatim, sin partición, sin desglose (inventario §1.4).
    "Cuentas Corrientes del Personal": PartnerSpec(
        "Cuentas Corrientes del Personal", CAT_RENDICION_P7
    ),
    "Fondo Fijo": PartnerSpec("Fondo Fijo", CAT_RENDICION_P7),
    "Fondos por Rendir": PartnerSpec("Fondos por Rendir", CAT_RENDICION_P7),
    "Fondos por Rendir - US$": PartnerSpec("Fondos por Rendir - US$", CAT_RENDICION_P7),
    # -- Categoría 2: deudores / préstamos a terceros --
    # Cuenta-bolsa → placeholder POR ENTIDAD, nunca fusión a ciegas (AC4).
    "Deudores Varios": PartnerSpec("Deudores Varios", CAT_BUCKET, FLAG_REVISAR, por_entidad=True),
    # Deudores nominables por cuenta que la lista cat 2 no enumeró → partners
    # reales + revisar (pregunta guardada a Valentina, story Dev Notes 1).
    "Inmobiliaria Inv. Pirihueico SPA": PartnerSpec(
        "Inmobiliaria Inv. Pirihueico SPA", CAT_DEUDOR, FLAG_REVISAR
    ),
    "Grupo Gastronómico S.A.": PartnerSpec("Grupo Gastronómico S.A.", CAT_DEUDOR, FLAG_REVISAR),
    "Tierra y Huertos SpA": PartnerSpec("Tierra y Huertos SpA", CAT_DEUDOR, FLAG_REVISAR),
    # -- Categoría 3a: donaciones (instituciones) --
    "Keren Hayesod": PartnerSpec("Keren Hayesod", CAT_DONACION),  # colapsa EAG+JAB (regla 4)
    "WIZO": PartnerSpec("WIZO", CAT_DONACION),  # colapsa EAG+JAB
    "Coronas de Caridad": PartnerSpec("Coronas de Caridad", CAT_DONACION),
    "Coanil": PartnerSpec("Coanil", CAT_DONACION),
    "EZRA": PartnerSpec("EZRA", CAT_DONACION),
    "Hogar de Ancianos": PartnerSpec("Hogar de Ancianos", CAT_DONACION),
    "KKL": PartnerSpec("KKL", CAT_DONACION),
    "CREJ": PartnerSpec("CREJ", CAT_DONACION),
    # CIS ≠ C.I. Santiago ≠ C.I. Sefaradí: TRES partners hasta confirmar (regla 5).
    "CIS": PartnerSpec("CIS", CAT_DONACION, FLAG_REVISAR),
    "Hogar de Cristo": PartnerSpec("Hogar de Cristo", CAT_DONACION),
    "C. Jafetz y Jaim": PartnerSpec("C. Jafetz y Jaim", CAT_DONACION),
    "Fundación Mar de Chile": PartnerSpec("Fundación Mar de Chile", CAT_DONACION),  # colapsa 878019+879019
    "Fundación FOBEJU": PartnerSpec("Fundación FOBEJU", CAT_DONACION),
    # Cuentas-bolsa de donación → UN bucket "Donaciones varias" + revisar
    # (regla 3; FFCC 437055 mezcla donaciones+regalos).
    "Donaciones": PartnerSpec("Donaciones varias", CAT_BUCKET, FLAG_REVISAR),
    "Donaciones, Regalos": PartnerSpec("Donaciones varias", CAT_BUCKET, FLAG_REVISAR),
    "Otras Instituciones": PartnerSpec("Donaciones varias", CAT_BUCKET, FLAG_REVISAR),
    # -- Categoría 3b: clubes / membresías --
    "Club Naval Las Salinas": PartnerSpec("Club Naval Las Salinas", CAT_CLUB),
    "Club Naval de Valparaíso": PartnerSpec("Club Naval de Valparaíso", CAT_CLUB),
    "Museo Naval, Patrimonio": PartnerSpec("Museo Naval, Patrimonio", CAT_CLUB),
    "Club de Golf La Dehesa": PartnerSpec("Club de Golf La Dehesa", CAT_CLUB),
    "Club de Campo Granadilla": PartnerSpec("Club de Campo Granadilla", CAT_CLUB),
    "C.I. Sefaradi": PartnerSpec("C.I. Sefaradi", CAT_CLUB, FLAG_REVISAR),  # ver CIS
    "C.I. Santiago": PartnerSpec("C.I. Santiago", CAT_CLUB, FLAG_REVISAR),  # ver CIS
    # -- Categoría 4: beneficiarios de asignación (solo P&L, winston §5.2) --
    "Raquel Ventura": PartnerSpec("Raquel Ventura", CAT_BENEFICIARIO),
    "Jacqueline Deutsch": PartnerSpec("Jacqueline Deutsch", CAT_BENEFICIARIO),
    "Patricia Deutsch": PartnerSpec("Patricia Deutsch", CAT_BENEFICIARIO),  # ≠ Jacqueline
    "Gloria Jiménez": PartnerSpec("Gloria Jiménez", CAT_BENEFICIARIO),  # colapsa "… Bustos"
}

#: Valor de la columna `socio` del CSV → partner canónico DISPERSO (mismo
#: canónico que la partición — "no crear duplicado", lista cat 1 nota; NO entra
#: al gate de partición). FGK no tiene 115xxx: es SOLO disperso (lista cat 1).
SOCIO_CANONICO: dict[str, str] = {
    "AAG": "AAG",
    "EAG": "EAG",
    "SAG": "SAG",
    "DAG": "DAG",
    "FGK": "FGK",
}

#: Población cerrada del plan socio_uso: los socios canónicos + AZBA (existe
#: en el YAML tipo `socio` pero no en la columna `socio` del CSV). Un nombre
#: fuera de este set en el YAML es typo/renombre → fail-loud, no mis-estampar
#: el plan congelado (E1.1).
_SOCIO_USO_VALIDOS = frozenset(SOCIO_CANONICO) | {"AZBA"}

#: Asignación pinneada por (entity, code) donde el CSV deja `partner`/`benef`
#: vacíos pero la lista de Valentina asigna igual (la lista completa lo que el
#: CSV no trae): Jhonny (cat 2 — un solo partner madre+hijo hasta que Valentina
#: resuelva si "hijo" va aparte) y el T/C de Raquel (cat 4: "el beneficiario
#: sigue siendo Raquel" aunque la cuenta mapee a Liabilities:TC).
PARTNER_PIN: dict[tuple[str, str], PartnerSpec] = {
    ("EAG", "310045"): PartnerSpec("Jhonny Guerra", CAT_DEUDOR, FLAG_REVISAR),
    ("EAG", "310047"): PartnerSpec("Jhonny Guerra", CAT_DEUDOR, FLAG_REVISAR),
    ("EAG", "430019"): PartnerSpec("Raquel Ventura", CAT_BENEFICIARIO),
}

#: La PARTICIÓN (lista cat 1): partner → sus códigos 115xxx en FFCC. El gate
#: cuadra por PARTNER sobre estos códigos (115028 tiene destino distinto en la
#: tabla y aun así cuadra por DAG). FGK NO está: no tiene cuenta corriente.
PARTICION_ENTITY = "FFCC"
PARTICION_CODES: dict[str, frozenset] = {
    "AAG": frozenset({"115021"}),
    "EAG": frozenset({"115023"}),
    "SAG": frozenset({"115025"}),
    "DAG": frozenset({"115027", "115028"}),
    "AZBA": frozenset({"115029"}),
    "José Alazraki": frozenset({"115031"}),
    "Denise Zeldis": frozenset({"115033", "115034"}),
    "Michelle Zeldis": frozenset({"115035"}),
    "Ariel Borzutzky": frozenset({"115037"}),
    "Otros hijos": frozenset({"115039"}),
    "Israel": frozenset({"115041"}),
}

#: (entity, code) de TODOS los códigos de partición — el scope de la regla
#: socio-uso por glosa (winston §5.1: "Vuelo X Hrs→RetirosDag").
_PARTICION_KEYS = frozenset(
    (PARTICION_ENTITY, code) for codes in PARTICION_CODES.values() for code in codes
)

#: Marcador de la columna `area` que alimenta el plan por_cuenta_de (8 filas
#: Control y Liquidación) — NO es un valor de area_centro.
POR_CUENTA_DE = "por-cuenta-de"

#: Nombre de entrada del YAML (sección personas, tipo beneficiario) → partner
#: canónico de la lista. El YAML keyea sin espacios; la lista con nombre real.
_BENEF_ALIAS_A_CANONICO = {
    "RaquelVentura": "Raquel Ventura",
    "JacquelineDeutsch": "Jacqueline Deutsch",
    "PatriciaDeutsch": "Patricia Deutsch",
    "GloriaJimenez": "Gloria Jiménez",
}


# --- Reporte de cobertura (FR10, versión E1.4) -------------------------------


@dataclass
class DimensionReport:
    """Cobertura del dimensionado: qué se estampó y qué quedó mencionado sin
    resolver. La métrica es visibilidad, no cobertura total (AC3/AC5)."""

    #: Patas donde la glosa MENCIONÓ una persona sin resolver a un canónico
    #: (ambigua o vetada por homónimo) — el listado del sign-off AC5.
    sin_match: list = field(default_factory=list)  # [LineRef]
    #: Patas estampadas con partner dudoso/placeholder (flag revisar).
    revisar: list = field(default_factory=list)  # [LineRef]
    por_categoria: dict = field(default_factory=dict)  # categoria → n patas
    por_plan: dict = field(default_factory=dict)  # plan → n patas estampadas

    def resumen(self) -> str:
        cats = ", ".join(f"{k}={v}" for k, v in sorted(self.por_categoria.items()))
        planes = ", ".join(f"{k}={v}" for k, v in sorted(self.por_plan.items()))
        return (
            f"cobertura dimensionado: partners[{cats}] | planes[{planes}] | "
            f"sin match={len(self.sin_match)} | revisar={len(self.revisar)}"
        )


@dataclass
class DimensionadoResult:
    moves: list  # moves con partner + dims estampados (mismos moves, copias)
    report: DimensionReport


# --- El transformador ---------------------------------------------------------


def _partner_por_cuenta(row, entity: str, code: str) -> tuple[PartnerSpec | None, str]:
    """Partner a nivel CUENTA: columna `partner` del CSV (fuente primaria),
    pin por (entity, code), o columna `socio` (disperso). Fail-loud si el CSV
    trae un valor que la tabla canónica no enumera (población cerrada)."""
    if row.partner:
        try:
            return PARTNER_CANONICO[row.partner], "cuenta:partner"
        except KeyError:
            raise ValueError(
                f"dimensionar: valor partner={row.partner!r} del CSV "
                f"(entity={entity!r}, code={code!r}) sin entrada en "
                f"PARTNER_CANONICO — la población de partners es cerrada"
            ) from None
    pin = PARTNER_PIN.get((entity, code))
    if pin is not None:
        return pin, "cuenta:pin-lista"
    if row.socio:
        try:
            return (
                PartnerSpec(SOCIO_CANONICO[row.socio], CAT_SOCIO_DISPERSO),
                "cuenta:socio",
            )
        except KeyError:
            raise ValueError(
                f"dimensionar: valor socio={row.socio!r} del CSV "
                f"(entity={entity!r}, code={code!r}) sin entrada en "
                f"SOCIO_CANONICO — la población de socios es cerrada"
            ) from None
    return None, ""


def dimensionar(
    moves: list,
    mapping: MappingTable,
    *,
    alias_table: dict | None = None,
) -> DimensionadoResult:
    """Aplica partner + dimensiones al output de `sincerar`. Función pura: no
    muta el input; los moves devueltos son copias con la metadata estampada.
    NO toca `odoo_account` ni `amount` ni el set de moves (invariante E1.4)."""
    if alias_table is None:
        alias_table = load_alias_table()

    report = DimensionReport()
    out = []
    for move in moves:
        new_lines = []
        for line in move.lines:
            row = mapping.get(line.entity, line.laudus_code)
            key = (line.entity, line.laudus_code)
            glosa = normalize(line.desc)

            spec, regla = _partner_por_cuenta(row, line.entity, line.laudus_code)

            # Dimensiones dispersas por columna (nivel cuenta), verbatim.
            dim_propiedad = row.prop
            dim_area = "" if row.area == POR_CUENTA_DE else row.area
            dim_por_cuenta_de = row.area if row.area == POR_CUENTA_DE else ""
            dim_offshore = row.offshore
            dim_socio_uso = ""

            # Regla por glosa (a): beneficiario en cuentas de gasto sin partner
            # a nivel cuenta (caso Raquel, lista cat 4). Solo alias `personas`
            # tipo beneficiario — nombre completo, homónimos vetan. El scope es
            # el `otype` de la CUENTA (la columna `odoo` no usa prefijo
            # `Expenses:` — los gastos son `Gasto:…`, `Regalos`, …).
            if spec is None and row.odoo_type == "expense":
                name, candidata = resolve_alias(
                    glosa, alias_table, "personas", tipo="beneficiario"
                )
                if name is not None:
                    try:
                        canonico = _BENEF_ALIAS_A_CANONICO[name]
                    except KeyError:
                        raise ValueError(
                            f"dimensionar: entrada beneficiario {name!r} del YAML "
                            f"sin canónico en _BENEF_ALIAS_A_CANONICO — al agregar "
                            f"un beneficiario al YAML hay que extender el mapa "
                            f"(población cerrada)"
                        ) from None
                    spec = PartnerSpec(canonico, CAT_BENEFICIARIO)
                    regla = f"glosa:{name}"
                elif candidata:
                    report.sin_match.append(
                        _ref(move, line, "glosa:beneficiario-sin-resolver")
                    )

            # Regla por glosa (b): socio-USO en retiros de uso (plan socio_uso,
            # winston §5.1). Solo si el alias resuelve inequívoco.
            if key in _PARTICION_KEYS and glosa:
                name, candidata = resolve_alias(
                    glosa, alias_table, "personas", tipo="socio"
                )
                if name is not None:
                    # Los nombres de entrada tipo `socio` del YAML (EAG/AAG/
                    # DAG/SAG/AZBA/FGK) YA son el canónico — incluye AZBA, que
                    # no existe en la columna `socio` del CSV.
                    if name not in _SOCIO_USO_VALIDOS:
                        raise ValueError(
                            f"dimensionar: entrada socio {name!r} del YAML fuera "
                            f"de la población cerrada del plan socio_uso "
                            f"({sorted(_SOCIO_USO_VALIDOS)}) — typo/renombre en "
                            f"el YAML mis-estamparía el plan congelado"
                        )
                    dim_socio_uso = name
                    report.por_plan["socio_uso"] = report.por_plan.get("socio_uso", 0) + 1
                elif candidata:
                    report.sin_match.append(_ref(move, line, "glosa:socio-uso-sin-resolver"))

            partner = ""
            categoria = ""
            flag = ""
            if spec is not None:
                partner = (
                    f"{spec.canonico} ({line.entity})" if spec.por_entidad else spec.canonico
                )
                categoria = spec.categoria
                flag = spec.flag
                report.por_categoria[categoria] = report.por_categoria.get(categoria, 0) + 1
                if flag == FLAG_REVISAR:
                    report.revisar.append(_ref(move, line, f"{regla}→{partner}"))

            for plan, valor in (
                ("propiedad_objeto", dim_propiedad),
                ("area_centro", dim_area),
                ("offshore_vehiculo", dim_offshore),
                ("por_cuenta_de", dim_por_cuenta_de),
            ):
                if valor:
                    report.por_plan[plan] = report.por_plan.get(plan, 0) + 1

            # Copia SIEMPRE (también sin metadata nueva): función pura, el
            # dataclass es mutable y compartir el objeto rompería el contrato
            # (mismo criterio que sincerar, review E1.3 P-6).
            new_lines.append(
                dataclasses.replace(
                    line,
                    partner=partner,
                    partner_categoria=categoria,
                    partner_regla=regla if spec is not None else "",
                    partner_flag=flag,
                    dim_propiedad=dim_propiedad,
                    dim_area=dim_area,
                    dim_offshore=dim_offshore,
                    dim_por_cuenta_de=dim_por_cuenta_de,
                    dim_socio_uso=dim_socio_uso,
                )
            )
        out.append(dataclasses.replace(move, lines=new_lines))

    return DimensionadoResult(moves=out, report=report)


def _ref(move, line, regla: str) -> LineRef:
    return LineRef(
        company=move.company,
        je_id=move.je_id,
        code=line.laudus_code,
        desc=line.desc,
        currency=line.currency,
        amount=line.amount,
        regla=regla,
    )


# --- Gate de partición (AC2) — el gate NUEVO de E1.4 ---------------------------


def verify_particion(entries, moves) -> list[str]:
    """AC2: para cada partner de partición, Σ(patas estampadas con ese partner,
    por moneda) == Σ del MIRROR crudo para sus códigos 115xxx — la expectativa
    se deriva del mirror SIN pasar por el transformador (patrón E1.3). El
    partner ledger es la única partición que reconcilia; devolver lista de
    problemas (vacía = gate verde). Para el gate completo, correr también
    `run_tier_a` (la paridad es invariante a esta story)."""
    codes = account_codes(entries)
    code_a_partner = {
        code: partner for partner, cs in PARTICION_CODES.items() for code in cs
    }
    expected: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for txn in laudus_transactions(entries):
        for posting in txn.postings:
            code = codes.get(posting.account)
            entity = entity_of_account(posting.account)
            if entity == PARTICION_ENTITY and code in code_a_partner:
                key = (code_a_partner[code], posting.units.currency)
                expected[key] += posting.units.number

    actual: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for move in moves:
        for line in move.lines:
            if line.partner_categoria == CAT_SOCIO_PARTICION:
                actual[(line.partner, line.currency)] += line.amount

    problems = []
    for key in sorted(set(expected) | set(actual)):
        esperado = expected.get(key, Decimal(0))
        estampado = actual.get(key, Decimal(0))
        if esperado != estampado:
            partner, currency = key
            problems.append(
                f"partición {partner!r} ({currency}): mirror={esperado} vs "
                f"estampado={estampado} (diff={esperado - estampado})"
            )
    return problems
