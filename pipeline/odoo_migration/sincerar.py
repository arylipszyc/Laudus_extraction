"""Transformador de sinceramiento por naturaleza (story E1.3) — Tier A, SIN Odoo.

Segundo transformador de la cadena (`collapse` → `sincerar`). Reclasifica cada
pata de INGRESO según su naturaleza (tabla-madre 0/A–H del inventario de
Valentina, población CERRADA) y excluye los washes de apertura/cierre por
IDENTIDAD (pares completos de moves, log auditable).

Naturalezas (inventario §2.2):
  0 WASH        — pares "Comprobante de apertura/cierre" iguales-y-opuestos →
                  excluir AMBOS moves (netean 0 por código). Nunca una pata suelta.
  A REAL        — allowlist por código (dividendos, sueldos, directorio…). Queda.
  B RETIRO      — retiro de inversión → activo de ORIGEN provisional (FR4a).
  C APORTE      — Sade. YA ruteado a nivel cuenta por la tabla (E1.2); acá solo
                  se estampa la naturaleza y el gate lo verifica.
  D DISPOSICION — venta de activos. P-2 ABIERTA y el activo a dar de baja no
                  existe en el libro (patrimonio = E1B) → queda en Income +
                  naturaleza estampada + flag `revisar`. SIN re-ruteo en E1.3.
  E GASTO_MOLCO — YA ruteado a nivel cuenta por la tabla (Expenses:MolcoFinanciamiento).
  F REEMBOLSO   — contra-gasto de baja materialidad. Queda como ingreso menor.
  G MIXTO       — OtrosIngresos: regla POR GLOSA (cascada SPEC §3.2) con
                  normalización + tabla de alias. Solo lo inequívoco se re-rutea;
                  el resto queda en Income + `sin clasificar`.
  H PRESTAMO    — Jhonny Guerra (310045/310047) → por-cobrar. Latinoamericana
                  (310009 FFCC / 310010 EAG) → excluir por PARES (netea 0, N-1).

Garantías (SPEC §3.3 + winston §6·B.2):
  - La paridad-origen es INVARIANTE: el código origen viaja en la línea pase lo
    que pase con la cuenta destino. `run_tier_a` corre tras este transformador.
  - Sin match ≠ mal clasificado: sin match = marcado + reporte, NUNCA descarte
    silencioso. NO fuzzy como decisor (tabla de alias explícita).
  - Cada línea tocada lleva metadata auditable (naturaleza, regla, destino de
    colapso original) — reversible y listable.
"""

import dataclasses
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml

from pipeline.odoo_migration.mapping import MappingTable
from pipeline.odoo_migration.transform import OdooLineRecord, OdooMoveRecord

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALIAS_PATH = (
    _REPO_ROOT
    / "_bmad-output/planning-artifacts/odoo-migracion/valentina-tabla-alias-2026-07-23.yaml"
)

# --- Naturalezas (tabla-madre 0/A–H) ---------------------------------------

WASH = "0"
REAL = "A"
RETIRO = "B"
APORTE = "C"
DISPOSICION = "D"
GASTO_MOLCO = "E"
REEMBOLSO = "F"
MIXTO = "G"
PRESTAMO = "H"

#: Columna `sinc` del CSV (seed del generador) → naturaleza de la tabla-madre.
#: Cross-check fail-loud: un label nuevo en la tabla no pasa en silencio.
NATURALEZA_POR_SINC = {
    "RETIRO→activo origen": RETIRO,
    "REAL(se queda)": REAL,
    "REAL(allowlist-dividendo)": REAL,
    "REEMBOLSO(se queda)": REEMBOLSO,
    "DISPOSICIÓN→baja activo": DISPOSICION,
    "MIXTO→regla por-glosa": MIXTO,
    "→GASTO(Molco financiamiento)": GASTO_MOLCO,
    "APORTE→Assets:InversionesSade": APORTE,
    # REAL?(revisar) se resuelve por (entity, code) en REVISAR_RESOLUCION.
}

#: Resolución pinneada de las 12 filas `REAL?(revisar)` (story E1.3, Dev Notes 3):
#: Latinoamericana → H-excluir por pares (inventario N-1, netea 0);
#: Jhonny Guerra → H por-cobrar (N-3); el resto → A con flag `revisar`.
LATAM_CODES = frozenset({("EAG", "310010"), ("FFCC", "310009")})
JHONNY_CODES = frozenset({("EAG", "310045"), ("EAG", "310047")})
REVISAR_A_CODES = frozenset(
    {
        ("EAG", "310025"),  # Fondos Mutuos BCI
        ("EAG", "510001"),  # Resultado Fondos Mutuos
        ("EAG", "510007"),  # Resultado C/V Acciones
        ("EAG", "510009"),  # Resultado Renta Fija
        ("Jocelyn", "670021"),
        ("Jeannette", "770021"),
        ("Johanna", "870021"),
        ("Jael", "970021"),
    }
)

JHONNY_DESTINO = "Assets:EAG:PrestamoJhonnyGuerra"

#: Destinos de activo de ORIGEN para la naturaleza B, keyed (entity, code).
#: Fuente: SPEC §1.2/§2.2; los que el SPEC no listó derivan con el mismo patrón
#: (story E1.3, Task 3). Test de completitud: cubre TODA fila con sinc RETIRO.
ORIGEN_ASSETS = {
    ("EAG", "310006"): "Assets:EAG:RetirosFondoComun",  # provisional + revisar (Dev Notes 4)
    ("EAG", "310013"): "Assets:EAG:InvTecnion",
    ("EAG", "310015"): "Assets:EAG:Pleyades",
    ("EAG", "310016"): "Assets:EAG:InvNuevoCiclo",
    ("EAG", "310017"): "Assets:EAG:InvCepech",
    ("EAG", "310018"): "Assets:EAG:InmobiliariaEspana",
    ("EAG", "310019"): "Assets:EAG:InmobiliariaMetropolitana",
    ("EAG", "310027"): "Assets:EAG:MBI",
    ("EAG", "310029"): "Assets:EAG:JuliusBaer",
    ("EAG", "510011"): "Assets:EAG:MBI",  # Resultado MBI → mismo vehículo (la tabla lo marca RETIRO)
    ("Jocelyn", "670011"): "Assets:Jocelyn:InvTecnion",
    ("Jocelyn", "670013"): "Assets:Jocelyn:Pleyades",
    ("Jocelyn", "670023"): "Assets:Jocelyn:MBI",
    ("Jeannette", "770011"): "Assets:Jeannette:InvTecnion",
    ("Jeannette", "770013"): "Assets:Jeannette:Pleyades",
    ("Jeannette", "770023"): "Assets:Jeannette:MBI",
    ("Johanna", "870011"): "Assets:Johanna:InvTecnion",
    ("Johanna", "870013"): "Assets:Johanna:Pleyades",
    ("Johanna", "870023"): "Assets:Johanna:MBI",
    ("Jael", "970010"): "Assets:Jael:JuliusBaer",
    ("Jael", "970011"): "Assets:Jael:InvTecnion",
    ("Jael", "970013"): "Assets:Jael:Pleyades",
    ("Jael", "970023"): "Assets:Jael:MBI",
    ("FFCC", "310003"): "Assets:FFCC:JuliusBaer",  # Bank JB
    ("FFCC", "310007"): "Assets:FFCC:MBI",
}

#: Códigos B con destino provisional dudoso → además flag `revisar` (Dev Notes 4).
RETIRO_REVISAR = frozenset({("EAG", "310006")})

FLAG_SIN_CLASIFICAR = "sin clasificar"
FLAG_REVISAR = "revisar con contadoras"

# --- Normalización de glosa + tabla de alias (winston §6·B.3) ---------------


def normalize(text: str) -> str:
    """Minúsculas, sin tildes, espacios colapsados. Previo a TODO match de glosa."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


@dataclass(frozen=True)
class AliasEntry:
    name: str
    aliases: tuple
    excluir: tuple
    tipo: str = ""  # sección `personas`: socio | beneficiario | apellido_azba | deudor


def load_alias_table(path: Path | str = DEFAULT_ALIAS_PATH) -> dict[str, list[AliasEntry]]:
    """Carga la tabla de alias de Valentina (data versionada — se extiende en el
    YAML, no en el código). Devuelve {seccion: [AliasEntry, ...]}."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or "vehiculos" not in raw:
        raise ValueError(
            f"sincerar: la tabla de alias {path} no tiene sección `vehiculos` — "
            f"la regla G quedaría ciega (todo caería a `sin clasificar` sin alarma)"
        )
    if "personas" not in raw:
        raise ValueError(
            f"sincerar: la tabla de alias {path} no tiene sección `personas` — "
            f"las reglas por glosa de E1.4 (beneficiarios/socio-uso) quedarían "
            f"ciegas sin alarma"
        )
    table: dict[str, list[AliasEntry]] = {}
    for section, entries in raw.items():
        parsed = [
            AliasEntry(
                name=name,
                aliases=tuple(normalize(a) for a in (spec.get("aliases") or [])),
                excluir=tuple(normalize(h) for h in (spec.get("excluir_homonimos") or [])),
                tipo=str(spec.get("tipo") or ""),
            )
            for name, spec in entries.items()
        ]
        for entry in parsed:
            if any(not a for a in entry.aliases) or any(not h for h in entry.excluir):
                raise ValueError(
                    f"sincerar: la entrada {entry.name!r} de la sección "
                    f"{section!r} en {path} tiene un alias/homónimo que "
                    f"normaliza a vacío — matchearía cualquier glosa (incluida "
                    f"la vacía)"
                )
        table[section] = parsed
    return table


def _phrase_matches(phrase: str, text: str) -> bool:
    """Match de frase completa con word-boundary (los tokens cortos jb/mbi/fip
    lo exigen — notas del YAML). NUNCA substring pelado."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _phrase_spans(phrase: str, text: str) -> list[tuple[int, int]]:
    """Todas las posiciones (start, end) donde la frase matchea con boundary."""
    return [m.span() for m in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", text)]


#: Vehículo de la tabla de alias → cuenta de activo de origen (por entidad de la
#: línea). Solo los vehículos con destino B conocido resuelven en la regla G;
#: el resto (Leo/Tauro/Hemanext/W&M/FIP/FM_BCI) NO tiene activo de origen en E1.3
#: → la pata queda sin clasificar (conservador).
VEHICULO_DESTINO = {
    "Tecnion": "Assets:{entity}:InvTecnion",
    "NuevoCiclo": "Assets:{entity}:InvNuevoCiclo",
    "MBI": "Assets:{entity}:MBI",
    "JuliusBaer": "Assets:{entity}:JuliusBaer",
    "Pleyades": "Assets:{entity}:Pleyades",
    "InmobiliariaEspana": "Assets:EAG:InmobiliariaEspana",
    "InmobiliariaMetropolitana": "Assets:EAG:InmobiliariaMetropolitana",
    "Sade": "Assets:FFCC:InversionesSade",
}


def resolve_alias(
    glosa_norm: str, alias_table: dict, section: str, *, tipo: str | None = None
) -> tuple[str | None, bool]:
    """Match único e inequívoco de una sección de la tabla en la glosa.

    Devuelve `(nombre, candidata)`: `nombre` es la entrada que matcheó (None si
    ninguna o más de una — ambiguo → conservador); `candidata=True` si la glosa
    MENCIONÓ algo de la sección sin resolver (alias ambiguo, u homónimo que
    veta) — la distinción alimenta el reporte de cobertura de E1.4
    (mencionado-pero-no-resuelto ≠ no-mencionado). OJO: `candidata` puede
    venir True aunque `nombre` SÍ haya resuelto (otra entrada de la sección
    quedó vetada en la misma glosa) — los callers deben mirarla solo cuando
    `nombre` es None (no doble-contar). Un homónimo presente en la glosa veta
    a su entrada (conservador). `tipo` filtra la sección `personas`
    (socio / beneficiario / …).
    """
    hits = []
    candidata = False
    for entry in alias_table.get(section, []):
        if tipo is not None and entry.tipo != tipo:
            continue
        alias_spans = [
            span for a in entry.aliases for span in _phrase_spans(a, glosa_norm)
        ]
        # El homónimo veta SOLO si aparece FUERA de un match de alias: el
        # nombre completo ("jacqueline deutsch") gana sobre su propio substring
        # excluido ("deutsch"); un homónimo suelto en la misma glosa sí veta
        # (conservador — caso "leo hernandez por leo limited").
        vetado = any(
            not any(s <= h_start and h_end <= e for s, e in alias_spans)
            for h in entry.excluir
            for h_start, h_end in _phrase_spans(h, glosa_norm)
        )
        if vetado:
            candidata = True  # menciona un término de la entrada, sin resolver
            continue
        if alias_spans:
            hits.append(entry.name)
    if len(hits) == 1:
        return hits[0], candidata
    if len(hits) > 1:
        return None, True  # más de una entrada distinta → ambiguo
    return None, candidata


def resolve_vehiculo(glosa_norm: str, alias_table: dict) -> str | None:
    """Vehículo único e inequívoco mencionado en la glosa, o None (regla G)."""
    name, _ = resolve_alias(glosa_norm, alias_table, "vehiculos")
    return name


# --- Clasificación (compartida por transformador y verificador) -------------

#: Patrones de la cascada §3.2 sobre glosa NORMALIZADA. El orden importa:
#: "devolucion de prestamo / abono prestamo" es capital (c), no reembolso (b).
_RE_INGRESO_REAL = re.compile(
    r"(?<!\w)(dividendos?|interes|intereses|directorios?|arriendos?|sueldos?)(?!\w)"
)
_RE_PRESTAMO = re.compile(
    r"(?<!\w)(abono\s+(de\s+)?prestamos?|devolucion\s+(de\s+)?prestamos?)(?!\w)"
)
_RE_REEMBOLSO = re.compile(r"(?<!\w)(reembolso|reemb|devolucion|devol)(?!\w)")
_RE_CAPITAL = re.compile(
    r"(?<!\w)(rescate|retiro|retiros|traspaso|abono\s+mandato)(?!\w)|(?<!\w)a\s+cta(?!\w)"
)
_RE_APORTE = re.compile(r"(?<!\w)aporte(?!\w)")
_RE_VENTA = re.compile(r"(?<!\w)venta(?!\w)")
_RE_POR_CUENTA_DE = re.compile(r"por\s+cuenta\s+de|(?<!\w)bupa(?!\w)")
_RE_COMPROBANTE = re.compile(r"comprobante\s+de\s+(apertura|cierre)")


@dataclass(frozen=True)
class Classification:
    """Veredicto para una pata de ingreso: a dónde va y por qué."""

    odoo_account: str  # destino final (== colapso si no se re-rutea)
    naturaleza: str  # 0/A..H
    regla: str  # qué decidió: "codigo" | "glosa:<patron>" | "cuenta-vs-glosa"
    flag: str = ""  # "" | FLAG_SIN_CLASIFICAR | FLAG_REVISAR


def naturaleza_de(entity: str, code: str, sinc: str) -> str:
    """Naturaleza de la cuenta (entity, code) según la tabla-madre 0/A–H.

    `sinc` viene de la tabla CSV (seed del generador); las filas `REAL?(revisar)`
    resuelven por la tabla pinneada de la story. Label desconocido → fail-loud
    (población cerrada: una cuenta de ingreso nueva no pasa en silencio).
    """
    key = (entity, code)
    if sinc == "REAL?(revisar)":
        if key in LATAM_CODES:
            return PRESTAMO  # → excluir por pares (N-1)
        if key in JHONNY_CODES:
            return PRESTAMO  # → por-cobrar
        if key in REVISAR_A_CODES:
            return REAL  # queda en Income + flag revisar
        raise ValueError(
            f"sincerar: (entity={entity!r}, code={code!r}) es REAL?(revisar) pero "
            f"no está en la resolución pinneada de la story — resolver y pinnear"
        )
    try:
        return NATURALEZA_POR_SINC[sinc]
    except KeyError:
        raise ValueError(
            f"sincerar: label sinc desconocido {sinc!r} en (entity={entity!r}, "
            f"code={code!r}) — la tabla trae una naturaleza que la tabla-madre "
            f"0/A–H no enumera"
        ) from None


def classify_line(
    entity: str,
    code: str,
    sinc: str,
    desc: str,
    amount: Decimal,
    collapsed_account: str,
    alias_table: dict,
) -> Classification | None:
    """Clasifica UNA pata. None = la pata no es del universo de sinceramiento
    (su cuenta no tiene naturaleza — no es cuenta de ingreso Laudus).

    Compartida por el transformador y el lado esperado del verificador de
    destino (mismo patrón que el filtro de universo de E1.2). El cross-check
    independiente son las cifras pinneadas del inventario (AC3).
    """
    if not sinc:
        if collapsed_account.startswith("Income:"):
            raise ValueError(
                f"sincerar: la cuenta de ingreso (entity={entity!r}, code={code!r}) "
                f"no tiene naturaleza en la tabla — la población 0/A–H es cerrada"
            )
        return None

    key = (entity, code)
    nat = naturaleza_de(entity, code, sinc)
    glosa = normalize(desc)

    # Wash que quedó SIN par (huérfano): nunca re-rutear ni dejar pasar en
    # silencio, cualquiera sea su naturaleza — un comprobante toca códigos
    # B/A/G por igual y una pata B huérfana inflaría un activo sin alarma.
    # Queda en su cuenta de colapso + revisar (review E1.3, P-1).
    if _RE_COMPROBANTE.search(glosa):
        return Classification(
            collapsed_account, nat, "glosa:comprobante-sin-par", FLAG_REVISAR
        )

    if nat == REAL:
        flag = FLAG_REVISAR if key in REVISAR_A_CODES else ""
        return Classification(collapsed_account, REAL, "codigo:allowlist", flag)

    if nat == RETIRO:
        # Ambiguo N-2 (AC5): pata en cuenta B con glosa de ingreso real →
        # conflicto cuenta-vs-glosa → queda en Income + revisar (manda el epic).
        if _RE_INGRESO_REAL.search(glosa):
            return Classification(
                collapsed_account, RETIRO, "cuenta-vs-glosa", FLAG_REVISAR
            )
        destino = ORIGEN_ASSETS.get(key)
        if destino is None:
            raise ValueError(
                f"sincerar: (entity={entity!r}, code={code!r}) es RETIRO pero no "
                f"tiene activo de origen en ORIGEN_ASSETS — completar el dict"
            )
        flag = FLAG_REVISAR if key in RETIRO_REVISAR else ""
        return Classification(destino, RETIRO, "codigo:retiro", flag)

    if nat == APORTE:
        # Ya ruteado a nivel cuenta por la tabla (Sade → Assets). Solo estampar.
        return Classification(collapsed_account, APORTE, "codigo:tabla")

    if nat == DISPOSICION:
        # P-2 abierta + el activo no existe en el libro → sin re-ruteo (Dev Notes 2).
        return Classification(collapsed_account, DISPOSICION, "codigo:P-2-abierta", FLAG_REVISAR)

    if nat == GASTO_MOLCO:
        return Classification(collapsed_account, GASTO_MOLCO, "codigo:tabla")

    if nat == REEMBOLSO:
        return Classification(collapsed_account, REEMBOLSO, "codigo:reembolso")

    if nat == PRESTAMO:
        if key in JHONNY_CODES:
            return Classification(JHONNY_DESTINO, PRESTAMO, "codigo:por-cobrar")
        # Latinoamericana: se excluye por PARES a nivel move (N-1). Una pata que
        # llegó acá quedó sin par → queda + revisar (nunca excluir una pata suelta).
        return Classification(collapsed_account, PRESTAMO, "codigo:latam-sin-par", FLAG_REVISAR)

    if nat == MIXTO:
        return _classify_mixto(glosa, amount, collapsed_account, entity, alias_table)

    raise ValueError(f"sincerar: naturaleza inesperada {nat!r} para {key!r}")


def _classify_mixto(
    glosa: str,
    amount: Decimal,
    collapsed_account: str,
    entity: str,
    alias_table: dict,
) -> Classification:
    """Cascada §3.2 por glosa para las cuentas MIXTO (G). Conservador: solo lo
    inequívoco se re-rutea; toda duda queda en Income + `sin clasificar`.
    (El caso comprobante-sin-par se atrapa antes, en `classify_line`, para
    TODAS las naturalezas — no solo G.)"""
    if _RE_INGRESO_REAL.search(glosa):
        return Classification(collapsed_account, MIXTO, "glosa:ingreso-real")
    if _RE_PRESTAMO.search(glosa):
        vehiculo = resolve_vehiculo(glosa, alias_table)
        destino = _destino_vehiculo(vehiculo, entity)
        if destino:
            return Classification(destino, MIXTO, f"glosa:prestamo→{vehiculo}")
        return Classification(collapsed_account, MIXTO, "glosa:prestamo-sin-vehiculo", FLAG_SIN_CLASIFICAR)
    if _RE_REEMBOLSO.search(glosa):
        return Classification(collapsed_account, MIXTO, "glosa:reembolso")
    if _RE_APORTE.search(glosa) and amount > 0:
        vehiculo = resolve_vehiculo(glosa, alias_table)
        destino = _destino_vehiculo(vehiculo, entity)
        if destino:
            return Classification(destino, MIXTO, f"glosa:aporte→{vehiculo}")
        return Classification(collapsed_account, MIXTO, "glosa:aporte-sin-vehiculo", FLAG_SIN_CLASIFICAR)
    if _RE_VENTA.search(glosa):
        # Disposición vía glosa: mismo tratamiento que D (P-2) — marcar, no rutear.
        return Classification(collapsed_account, MIXTO, "glosa:venta(P-2)", FLAG_REVISAR)
    if _RE_POR_CUENTA_DE.search(glosa):
        # Inventario §1.2: "por cuenta de" (caso FGK/BUPA) — destino contable no
        # inequívoco (por-cobrar vs contra-gasto) → marcar para contadoras.
        return Classification(collapsed_account, MIXTO, "glosa:por-cuenta-de", FLAG_REVISAR)
    if _RE_CAPITAL.search(glosa):
        vehiculo = resolve_vehiculo(glosa, alias_table)
        destino = _destino_vehiculo(vehiculo, entity)
        if destino:
            return Classification(destino, MIXTO, f"glosa:capital→{vehiculo}")
        return Classification(collapsed_account, MIXTO, "glosa:capital-sin-vehiculo", FLAG_SIN_CLASIFICAR)
    return Classification(collapsed_account, MIXTO, "glosa:sin-match", FLAG_SIN_CLASIFICAR)


#: Vehículos cuyo destino es una cuenta FIJA de UNA entidad: una glosa de otra
#: entidad que los mencione NO puede rutear ahí (sería cruzar de company — una
#: glosa EAG con "sade" contaminaría el ancla pinneada de Sade). Review E1.3, P-4.
_DESTINO_ENTIDAD_FIJA = {
    "InmobiliariaEspana": "EAG",
    "InmobiliariaMetropolitana": "EAG",
    "Sade": "FFCC",
}

#: Únicas cuentas que la regla G puede acuñar: las de ORIGEN_ASSETS + Sade.
#: Un template formateado fuera de esta allowlist (p.ej. Assets:JAB:MBI, que no
#: existe en ningún plan) NO se rutea → la pata queda sin clasificar.
_DESTINOS_G_VALIDOS = frozenset(ORIGEN_ASSETS.values()) | {"Assets:FFCC:InversionesSade"}


def _destino_vehiculo(vehiculo: str | None, entity: str) -> str | None:
    if vehiculo is None:
        return None
    template = VEHICULO_DESTINO.get(vehiculo)
    if template is None:
        return None
    fija = _DESTINO_ENTIDAD_FIJA.get(vehiculo)
    if fija is not None and entity != fija:
        return None
    destino = template.format(entity=entity)
    return destino if destino in _DESTINOS_G_VALIDOS else None


# --- Washes: exclusión por PARES con identidad (AC2) ------------------------


@dataclass(frozen=True)
class ExcludedPair:
    """Un par excluido, con identidad completa para el log auditable."""

    kind: str  # "comprobante" | "latinoamericana"
    company: str
    je_ids: tuple  # (je_id_a, je_id_b)
    dates: tuple
    n_lines: int
    #: Magnitud del wash POR CÓDIGO (Task 2: "montos por código"): neto del
    #: primer move por (code, currency) — el segundo es el espejo exacto.
    montos: tuple  # ((code, currency, amount), …) ordenado


def _signature(move: OdooMoveRecord) -> tuple:
    return tuple(sorted((l.laudus_code, l.currency, l.amount) for l in move.lines))


def _negated(sig: tuple) -> tuple:
    return tuple(sorted((code, cur, -amt) for code, cur, amt in sig))


def _is_comprobante(move: OdooMoveRecord) -> bool:
    texts = [move.narration] + [l.desc for l in move.lines]
    return any(_RE_COMPROBANTE.search(normalize(t)) for t in texts if t)


def _touches_latam(move: OdooMoveRecord) -> bool:
    return any((l.entity, l.laudus_code) in LATAM_CODES for l in move.lines)


def _pair_up(moves: list[OdooMoveRecord], kind: str) -> tuple[list[ExcludedPair], set]:
    """Empareja moves iguales-y-opuestos dentro del mismo ejercicio (año contable:
    el "Comprobante de apertura" del 1-ene cierra el ejercicio ANTERIOR).
    Devuelve (pares, je_ids excluidos). Lo que no empareja NO se excluye."""
    by_key: dict[tuple, list[OdooMoveRecord]] = defaultdict(list)

    def exercise_year(move: OdooMoveRecord) -> int:
        if move.date.month == 1 and move.date.day == 1:
            return move.date.year - 1
        return move.date.year

    for m in moves:
        by_key[(m.company, exercise_year(m), _signature(m))].append(m)

    pairs: list[ExcludedPair] = []
    excluded: set[tuple[str, str]] = set()
    for (company, year, sig), group in sorted(by_key.items()):
        counterpart = by_key.get((company, year, _negated(sig)), [])
        for a, b in zip(group, counterpart):
            key_a, key_b = (company, a.je_id), (company, b.je_id)
            if key_a in excluded or key_b in excluded or a.je_id == b.je_id:
                continue
            excluded.update((key_a, key_b))
            por_codigo: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
            for l in a.lines:
                por_codigo[(l.laudus_code, l.currency)] += l.amount
            pairs.append(
                ExcludedPair(
                    kind=kind,
                    company=company,
                    je_ids=(a.je_id, b.je_id),
                    dates=(a.date, b.date),
                    n_lines=len(a.lines) + len(b.lines),
                    montos=tuple(
                        sorted((c, cur, amt) for (c, cur), amt in por_codigo.items())
                    ),
                )
            )
    return pairs, excluded


# --- El transformador -------------------------------------------------------


@dataclass(frozen=True)
class LineRef:
    """Referencia auditable a una pata marcada (reporte de cobertura)."""

    company: str
    je_id: str
    code: str
    desc: str
    currency: str
    amount: Decimal
    regla: str


@dataclass
class CoverageReport:
    """Reporte de cobertura del transformador (FR10, versión E1.3)."""

    sin_clasificar: list = field(default_factory=list)
    revisar: list = field(default_factory=list)
    por_naturaleza: dict = field(default_factory=dict)

    def resumen(self) -> str:
        nat = ", ".join(f"{k}={v}" for k, v in sorted(self.por_naturaleza.items()))
        return (
            f"cobertura sinceramiento: {nat} | "
            f"sin clasificar={len(self.sin_clasificar)} | revisar={len(self.revisar)}"
        )


@dataclass
class SinceramientoResult:
    moves: list  # moves sincerados (los excluidos NO están)
    excluded_pairs: list  # [ExcludedPair] — el log auditable
    excluded_je_ids: set  # {(company, je_id)} — input directo de run_tier_a
    report: CoverageReport


def sincerar(
    moves: list,
    mapping: MappingTable,
    *,
    alias_table: dict | None = None,
) -> SinceramientoResult:
    """Aplica el sinceramiento al output de `collapse`. Función pura: no muta
    el input; los moves devueltos son copias con las patas re-ruteadas/estampadas."""
    if alias_table is None:
        alias_table = load_alias_table()

    comprobantes = [m for m in moves if _is_comprobante(m)]
    pairs_c, excl_c = _pair_up(comprobantes, "comprobante")
    latam = [
        m
        for m in moves
        if not _is_comprobante(m)
        and _touches_latam(m)
        and (m.company, m.je_id) not in excl_c
    ]
    pairs_l, excl_l = _pair_up(latam, "latinoamericana")

    excluded = excl_c | excl_l
    pairs = pairs_c + pairs_l

    report = CoverageReport()
    out: list[OdooMoveRecord] = []
    for move in moves:
        if (move.company, move.je_id) in excluded:
            continue
        new_lines = []
        for line in move.lines:
            row = mapping.get(line.entity, line.laudus_code)
            cls = classify_line(
                line.entity,
                line.laudus_code,
                row.sinc,
                line.desc,
                line.amount,
                line.odoo_account,
                alias_table,
            )
            if cls is None:
                # Copia también fuera del universo: el dataclass es mutable y
                # compartir el objeto rompería "función pura" si un consumidor
                # (E1.4 estampando dims) muta el resultado. Review E1.3, P-6.
                new_lines.append(dataclasses.replace(line))
                continue
            report.por_naturaleza[cls.naturaleza] = (
                report.por_naturaleza.get(cls.naturaleza, 0) + 1
            )
            new_line = dataclasses.replace(
                line,
                odoo_account=cls.odoo_account,
                sinc_naturaleza=cls.naturaleza,
                sinc_regla=cls.regla,
                sinc_flag=cls.flag,
                odoo_account_colapso=line.odoo_account,
            )
            ref = LineRef(
                company=move.company,
                je_id=move.je_id,
                code=line.laudus_code,
                desc=line.desc,
                currency=line.currency,
                amount=line.amount,
                regla=cls.regla,
            )
            if cls.flag == FLAG_SIN_CLASIFICAR:
                report.sin_clasificar.append(ref)
            elif cls.flag == FLAG_REVISAR:
                report.revisar.append(ref)
            new_lines.append(new_line)
        out.append(dataclasses.replace(move, lines=new_lines))

    return SinceramientoResult(
        moves=out,
        excluded_pairs=pairs,
        excluded_je_ids=excluded,
        report=report,
    )


def route_sincerado(mapping: MappingTable, alias_table: dict):
    """Función de ruteo esperado (mirror → cuenta destino) que INCLUYE el
    sinceramiento. La consume `verify_destination` (parity.py) para que el lado
    esperado del gate de destino aplique las MISMAS reglas que el transformador."""

    def route(entity: str, code: str, desc: str, amount: Decimal, collapsed_account: str) -> str:
        cls = classify_line(entity, code, mapping.get(entity, code).sinc, desc, amount, collapsed_account, alias_table)
        return collapsed_account if cls is None else cls.odoo_account

    return route
