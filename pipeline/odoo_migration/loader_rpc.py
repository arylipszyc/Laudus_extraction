"""Cliente XML-RPC + carga idempotente (story E1.5) — la ÚNICA pieza que toca Odoo.

Aplica los payloads de `load.py` contra un Odoo 18 vivo vía XML-RPC (stdlib
`xmlrpc.client`, cero dependencias nuevas). Toda la inteligencia vive en el
builder (Tier A); acá solo hay upsert por external ID y posteo:

  - Los xmlids viven en `ir.model.data` bajo el módulo-namespace `__laudus__`
    (constante). Re-correr el loader los encuentra y SALTA lo ya cargado:
    **upsert = skip-si-existe**, porque el input es determinístico (mismo
    transformador → mismo payload). FR11: 2× → estado idéntico; borrar la
    mitad → re-correr converge.
  - Los alias del chart (N códigos Laudus → 1 cuenta colapsada) se registran
    TODOS apuntando al mismo `res_id` — el formato congelado de E1.0
    (`acc_<company>_<code>`) sobrevive al colapso.
  - Los asientos se crean por lote y se postean SOLO los recién creados
    (re-postear un move posteado revienta; los existentes ya quedaron
    posteados en la corrida que los creó).
  - **Convergencia ante corridas interrumpidas** (review E1.5, P2/P3): si una
    corrida murió entre el `create` y el registro del xmlid, la re-corrida
    ADOPTA el registro huérfano por su clave natural (cuenta: code+compañía;
    partner: nombre; analítica: nombre+plan; move: `x_laudus_je_id`+compañía)
    en vez de duplicarlo o chocar contra un unique de Odoo; y al final de cada
    corrida se postean los moves del payload que hayan quedado en draft (un
    crash entre registro y `action_post` ya no los deja borrador para siempre).

Disciplina de re-corrida (decisión de scope): este loader es para cargas
frescas o reanudación de una carga interrumpida. NO detecta drift en lo ya
registrado — si los TRANSFORMADORES cambian (nueva regla E1.3/E1.4), un move
ya cargado con la regla vieja queda como está (skip; la adopción sí verifica
contenido y acusa el drift de los huérfanos). Re-sincronizar tras un cambio
de reglas = db nueva + carga completa (barato: el loader es re-corrible). La
verificación real post-carga es E1.6.

CLI:
    PYTHONUTF8=1 venv/Scripts/python.exe -m pipeline.odoo_migration.loader_rpc \
        --db test_e15 [--url http://localhost:8070] [--ledger ledger/main.beancount]

Por defecto carga el GOLDEN slice (dry-run barato contra el compose
`migration_e1`); el full load real pasa `--ledger ledger/main.beancount` y es
una corrida operativa post-E1.6 (gates: D-1 Valentina + VPS — ver story).
"""

import argparse
import xmlrpc.client
from decimal import Decimal

from pipeline.odoo_migration.load import (
    JOURNAL_CODE,
    build_analytic,
    build_chart,
    build_moves,
    build_origin_accounts,
    build_partners,
)

#: Namespace (`ir.model.data.module`) de TODOS los xmlids de la migración.
XMLID_MODULE = "__laudus__"

#: Tamaño de lote para `create` de asientos (winston §9: loader batcheado).
BATCH_SIZE = 200

DEFAULT_URL = "http://localhost:8070"
DEFAULT_GOLDEN = "pipeline/odoo_migration/tests/fixtures/golden_slice.beancount"


class OdooClient:
    """Capa fina sobre `xmlrpc.client` (authenticate + execute_kw)."""

    def __init__(self, url: str, db: str, login: str, password: str):
        url = url.rstrip("/")  # …:8070/ armaría //xmlrpc → 404 confuso (P11)
        self.db = db
        self._password = password
        self._common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        self._object = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        self.uid = self._common.authenticate(db, login, password, {})
        if not self.uid:
            raise RuntimeError(f"loader: login {login!r} rechazado por {url} db={db!r}")

    def execute(self, model: str, method: str, *args, **kwargs):
        return self._object.execute_kw(
            self.db, self.uid, self._password, model, method, list(args), kwargs
        )


def _f(value) -> float:
    """Decimal → float para el marshalling XML-RPC. Los contravalores CLP van
    cuantizados a entero por `load._contravalor` — exactos en float64 (< 2^53).
    Los `amount_currency` no-CLP traen 2 decimales: float64 los representa
    aproximado y Odoo los redondea a la precisión de la moneda al escribir."""
    return float(value)


def _xmlid_map(client: OdooClient) -> dict:
    """{name: res_id} de todo lo ya registrado bajo el namespace."""
    records = client.execute(
        "ir.model.data", "search_read",
        [("module", "=", XMLID_MODULE)],
        fields=["name", "res_id"],
    )
    return {r["name"]: r["res_id"] for r in records}


def _register(client: OdooClient, model: str, res_id: int, names: list) -> None:
    """Registra xmlids (todos → el mismo res_id para los alias del chart)."""
    client.execute(
        "ir.model.data", "create",
        [
            {"module": XMLID_MODULE, "name": name, "model": model,
             "res_id": res_id, "noupdate": True}
            for name in names
        ],
    )


def _companies(client: OdooClient) -> dict:
    rows = client.execute("res.company", "search_read", [], fields=["name"])
    companies = {r["name"]: r["id"] for r in rows}
    missing = {"EAG", "RUT2"} - set(companies)
    if missing:
        raise RuntimeError(
            f"loader: faltan las compañías {sorted(missing)!r} — ¿se instaló "
            f"x_laudus_migration en esta db? (el hook de E1.1 las crea)"
        )
    return companies


def _journals(client: OdooClient, companies: dict) -> dict:
    """{(company_name, journal_code): journal_id} — creados por el hook E1.1.

    Valida el diario de CADA compañía (no solo "hay alguno"): una db a medio
    instalar con LAU1 pero sin LAU2 reventaría con un KeyError pelado recién
    en el loop de lotes, DESPUÉS de escribir chart/partners (review P6)."""
    rows = client.execute(
        "account.journal", "search_read",
        [("code", "in", sorted(set(JOURNAL_CODE.values())))],
        fields=["code", "company_id"],
    )
    by_key = {(r["company_id"][1], r["code"]): r["id"] for r in rows}
    missing = [key for key in JOURNAL_CODE.items() if key not in by_key]
    if missing:
        raise RuntimeError(
            f"loader: faltan diarios {missing!r} (encontrados: "
            f"{sorted(by_key)!r}) — ¿x_laudus_migration a medio instalar?"
        )
    return by_key


def _plan_ids(client: OdooClient, plan_xmlids: set) -> dict:
    """Resuelve los planes contenedores de E1.1 (módulo x_laudus_migration)."""
    names = [x.split(".", 1)[1] for x in plan_xmlids]
    rows = client.execute(
        "ir.model.data", "search_read",
        [("module", "=", "x_laudus_migration"), ("name", "in", names)],
        fields=["name", "res_id"],
    )
    found = {f"x_laudus_migration.{r['name']}": r["res_id"] for r in rows}
    missing = plan_xmlids - set(found)
    if missing:
        raise RuntimeError(
            f"loader: planes analíticos {sorted(missing)!r} no existen en la "
            f"db — ¿versión vieja del módulo?"
        )
    return found


def _ensure_analytic_group(client: OdooClient) -> bool:
    """Crear `account.analytic.account` exige el grupo Technical/Analytic
    Accounting, que el admin de una db fresca NO tiene. Es un prerequisito del
    PROPIO usuario RPC del loader: se otorga solo si falta y queda contado en
    `counts["analytic_group_granted"]` — visible, no un write silencioso en
    cada corrida (review P9). Devuelve True si hubo que otorgarlo."""
    rows = client.execute(
        "ir.model.data", "search_read",
        [("module", "=", "analytic"), ("name", "=", "group_analytic_accounting")],
        fields=["res_id"],
    )
    if not rows:
        raise RuntimeError(
            "loader: no existe analytic.group_analytic_accounting — ¿db sin "
            "el módulo account/analytic instalado?"
        )
    gid = rows[0]["res_id"]
    user = client.execute("res.users", "read", [client.uid], fields=["groups_id"])[0]
    if gid in user["groups_id"]:
        return False
    client.execute("res.users", "write", [client.uid], {"groups_id": [(4, gid)]})
    return True


def _currency_id(client: OdooClient, name: str, counts: dict) -> int:
    """Id de la moneda; si existe pero está inactiva (db fresca) se activa —
    prerequisito del payload multi-moneda, contado en
    `counts["currencies_activated"]` (review P9). Inexistente → fail-loud."""
    rows = client.execute(
        "res.currency", "search_read",
        [("name", "=", name)],
        fields=["active"], context={"active_test": False},
    )
    if not rows:
        raise RuntimeError(f"loader: moneda {name!r} no existe en la db")
    if not rows[0]["active"]:
        client.execute("res.currency", "write", [rows[0]["id"]], {"active": True})
        counts["currencies_activated"] += 1
    return rows[0]["id"]


def _register_lines(client: OdooClient, m, move_id: int, xmlids: dict) -> None:
    """Verifica el apareo payload↔líneas POR CONTENIDO y registra los `aml_*`
    que falten. Hoy las `(0,0,…)` se crean en orden y los ids salen
    ascendentes, pero nada lo garantiza a futuro: si el contenido no calza
    1:1 (código Laudus + debit/credit), fail-loud ANTES de registrar un
    `aml_*` contra la línea equivocada — el formato es CONGELADO y E1.6
    traza por él (review P4)."""
    rows = client.execute(
        "account.move.line", "search_read",
        [("move_id", "=", move_id)],
        fields=["x_laudus_account_code", "debit", "credit"], order="id",
    )
    if len(rows) != len(m.lines):
        raise RuntimeError(
            f"loader: el move {m.xmlid} quedó con {len(rows)} líneas en Odoo "
            f"pero el payload trae {len(m.lines)} — Odoo agregó/perdió "
            f"líneas; no se registran los aml_*"
        )
    for l, row in zip(m.lines, rows):
        if (
            row["x_laudus_account_code"] != l.x_laudus_account_code
            or abs(row["debit"] - _f(l.debit)) > 0.005
            or abs(row["credit"] - _f(l.credit)) > 0.005
        ):
            raise RuntimeError(
                f"loader: apareo payload↔línea roto en {m.xmlid}: la línea "
                f"Odoo id={row['id']} trae "
                f"({row['x_laudus_account_code']!r}, {row['debit']}, "
                f"{row['credit']}) y el payload {l.xmlid} esperaba "
                f"({l.x_laudus_account_code!r}, {l.debit}, {l.credit}) — no "
                f"se registran los aml_*"
            )
    pending = [
        {"module": XMLID_MODULE, "name": l.xmlid, "model": "account.move.line",
         "res_id": row["id"], "noupdate": True}
        for l, row in zip(m.lines, rows)
        if l.xmlid not in xmlids
    ]
    if pending:
        client.execute("ir.model.data", "create", pending)
        for d in pending:
            xmlids[d["name"]] = d["res_id"]


def load_all(client: OdooClient, chart, partners, analytic, moves) -> dict:
    """Aplica los 4 payloads con upsert por xmlid. Devuelve conteos.

    Convergencia (review P2/P3): lo creado sin xmlid por una corrida
    interrumpida se ADOPTA por clave natural (`*_adopted`) en vez de duplicar
    o chocar; los moves del payload que quedaron en draft se postean al final
    (`moves_reposted`). Los prerequisitos que el loader se asegura a sí mismo
    quedan contados (`analytic_group_granted`, `currencies_activated`)."""
    xmlids = _xmlid_map(client)
    companies = _companies(client)
    journals = _journals(client, companies)
    counts = {
        "accounts_created": 0, "accounts_skipped": 0, "accounts_adopted": 0,
        "partners_created": 0, "partners_skipped": 0, "partners_adopted": 0,
        "analytic_created": 0, "analytic_skipped": 0, "analytic_adopted": 0,
        "moves_created": 0, "moves_skipped": 0, "moves_adopted": 0,
        "moves_reposted": 0,
        "analytic_group_granted": 0, "currencies_activated": 0,
    }
    if _ensure_analytic_group(client):
        counts["analytic_group_granted"] = 1

    # --- chart (cuentas colapsadas; N alias xmlid → 1 res_id) ---------------
    # Pre-fetch por clave natural (code × compañía), UN roundtrip por cía:
    # adopta huérfanos de la ventana create→register en vez de chocar contra
    # unique(code). Por-compañía a propósito: en Odoo 18 `code` es
    # company-dependent (account_code_mapping) y se resuelve según la compañía
    # activa del context.
    existing_accounts: dict = {}
    if chart:
        codes = sorted({a.code for a in chart})
        for cid in sorted(companies.values()):
            for r in client.execute(
                "account.account", "search_read",
                [("code", "in", codes), ("company_ids", "in", cid)],
                fields=["code"],
                context={"allowed_company_ids": [cid]},
            ):
                existing_accounts[(cid, r["code"])] = r["id"]
    for acc in chart:
        cid = companies[acc.company]
        registered = [a for a in acc.aliases if a in xmlids]
        if registered:
            res_id = xmlids[registered[0]]
            counts["accounts_skipped"] += 1
        elif (cid, acc.code) in existing_accounts:
            res_id = existing_accounts[(cid, acc.code)]
            counts["accounts_adopted"] += 1
        else:
            res_id = client.execute(
                "account.account", "create",
                [{
                    "code": acc.code,
                    "name": acc.name,
                    "account_type": acc.account_type,
                    "x_laudus_group": acc.x_laudus_group,
                    "company_ids": [(6, 0, [cid])],
                }],
                context={"allowed_company_ids": [cid]},
            )[0]
            counts["accounts_created"] += 1
        missing_aliases = [a for a in acc.aliases if a not in xmlids]
        if missing_aliases:
            _register(client, "account.account", res_id, missing_aliases)
            for a in missing_aliases:
                xmlids[a] = res_id

    # --- partners (compartidos entre compañías: company_id False) -----------
    existing_partners: dict = {}
    to_create_p = [p for p in partners if p.xmlid not in xmlids]
    if to_create_p:
        rows = client.execute(
            "res.partner", "search_read",
            [("name", "in", [p.name for p in to_create_p])],
            fields=["name"],
        )
        for r in sorted(rows, key=lambda r: r["id"]):  # determinístico: menor id
            existing_partners.setdefault(r["name"], r["id"])
    for p in partners:
        if p.xmlid in xmlids:
            counts["partners_skipped"] += 1
            continue
        if p.name in existing_partners:
            res_id = existing_partners[p.name]
            counts["partners_adopted"] += 1
        else:
            res_id = client.execute(
                "res.partner", "create", [{"name": p.name, "company_id": False}]
            )[0]
            counts["partners_created"] += 1
        _register(client, "res.partner", res_id, [p.xmlid])
        xmlids[p.xmlid] = res_id

    # --- cuentas analíticas (bajo los planes de E1.1, compartidas) ----------
    plan_ids = _plan_ids(client, {a.plan_xmlid for a in analytic}) if analytic else {}
    existing_analytic: dict = {}
    to_create_a = [a for a in analytic if a.xmlid not in xmlids]
    if to_create_a:
        rows = client.execute(
            "account.analytic.account", "search_read",
            [("name", "in", [a.name for a in to_create_a])],
            fields=["name", "plan_id"],
        )
        for r in sorted(rows, key=lambda r: r["id"]):
            existing_analytic.setdefault((r["plan_id"][0], r["name"]), r["id"])
    for a in analytic:
        if a.xmlid in xmlids:
            counts["analytic_skipped"] += 1
            continue
        key = (plan_ids[a.plan_xmlid], a.name)
        if key in existing_analytic:
            res_id = existing_analytic[key]
            counts["analytic_adopted"] += 1
        else:
            res_id = client.execute(
                "account.analytic.account", "create",
                [{"name": a.name, "plan_id": plan_ids[a.plan_xmlid],
                  "company_id": False}],
            )[0]
            counts["analytic_created"] += 1
        _register(client, "account.analytic.account", res_id, [a.xmlid])
        xmlids[a.xmlid] = res_id

    # --- moves (adopción de huérfanos + create batcheado + post) ------------
    usd_cache: dict[str, int] = {}
    pending = [m for m in moves if m.xmlid not in xmlids]
    counts["moves_skipped"] = len(moves) - len(pending)
    if pending:
        # Huérfanos de la ventana create→register: existen en Odoo (con
        # x_laudus_je_id) pero sin mv_*. Adoptarlos re-verifica el contenido
        # línea a línea (drift de reglas → fail-loud) y registra mv_*/aml_*.
        rows = client.execute(
            "account.move", "search_read",
            [("x_laudus_je_id", "in", [m.x_laudus_je_id for m in pending])],
            fields=["x_laudus_je_id", "company_id"],
            context={"allowed_company_ids": sorted(companies.values())},
        )
        orphans = {(r["company_id"][1], r["x_laudus_je_id"]): r["id"] for r in rows}
        still_pending = []
        for m in pending:
            move_id = orphans.get((m.company, m.x_laudus_je_id))
            if move_id is None:
                still_pending.append(m)
                continue
            _register(client, "account.move", move_id, [m.xmlid])
            xmlids[m.xmlid] = move_id
            _register_lines(client, m, move_id, xmlids)
            counts["moves_adopted"] += 1
        pending = still_pending
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        vals_list = []
        for m in batch:
            cid = companies[m.company]
            line_vals = []
            for l in m.lines:
                vals = {
                    "account_id": xmlids[l.account_xmlid],
                    "name": l.name,
                    "debit": _f(l.debit),
                    "credit": _f(l.credit),
                    "x_laudus_account_code": l.x_laudus_account_code,
                    "x_laudus_je_id": m.x_laudus_je_id,
                    "x_laudus_entity": l.x_laudus_entity,
                }
                if l.currency is not None:
                    if l.currency not in usd_cache:
                        usd_cache[l.currency] = _currency_id(client, l.currency, counts)
                    vals["currency_id"] = usd_cache[l.currency]
                    vals["amount_currency"] = _f(l.amount_currency)
                if l.partner_xmlid:
                    vals["partner_id"] = xmlids[l.partner_xmlid]
                if l.analytic_xmlids:
                    vals["analytic_distribution"] = {
                        str(xmlids[x]): 100.0 for x in l.analytic_xmlids
                    }
                line_vals.append((0, 0, vals))
            vals_list.append({
                "move_type": "entry",
                "journal_id": journals[(m.company, m.journal_code)],
                "date": m.date.isoformat(),
                "ref": m.ref,
                "x_laudus_je_id": m.x_laudus_je_id,
                "line_ids": line_vals,
            })
        cids = sorted({companies[m.company] for m in batch})
        move_ids = client.execute(
            "account.move", "create", vals_list,
            context={"allowed_company_ids": cids},
        )
        for m, move_id in zip(batch, move_ids):
            _register(client, "account.move", move_id, [m.xmlid])
            xmlids[m.xmlid] = move_id
            _register_lines(client, m, move_id, xmlids)
        client.execute(
            "account.move", "action_post", move_ids,
            context={"allowed_company_ids": cids},
        )
        counts["moves_created"] += len(batch)

    # --- barrido final: ningún move del payload queda en draft (review P3) --
    # Un crash entre el registro del mv_* y el action_post dejaba drafts que
    # las re-corridas saltaban para siempre (los reportes los excluyen).
    known_ids = [xmlids[m.xmlid] for m in moves if m.xmlid in xmlids]
    if known_ids:
        draft_ids = client.execute(
            "account.move", "search",
            [("id", "in", known_ids), ("state", "!=", "posted")],
            context={"allowed_company_ids": sorted(companies.values())},
        )
        if draft_ids:
            client.execute(
                "account.move", "action_post", draft_ids,
                context={"allowed_company_ids": sorted(companies.values())},
            )
            counts["moves_reposted"] = len(draft_ids)
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_chain(ledger_path: str, table):
    """Cadena completa mirror → moves dimensionados (los transformadores E1.2–E1.4)."""
    from beancount import loader as bc_loader

    from pipeline.odoo_migration.dimensionar import dimensionar
    from pipeline.odoo_migration.sincerar import load_alias_table, sincerar
    from pipeline.odoo_migration.transform import collapse

    entries, errors, _ = bc_loader.load_file(ledger_path)
    if errors:
        raise RuntimeError(f"loader: el ledger {ledger_path!r} tiene {len(errors)} errores")
    aliases = load_alias_table()
    moves = collapse(entries, table)
    sinc = sincerar(moves, table, alias_table=aliases)
    dim = dimensionar(sinc.moves, table, alias_table=aliases)
    return dim.moves


def main(argv=None) -> int:
    import os

    from pipeline.odoo_migration.mapping import load_mapping_table

    parser = argparse.ArgumentParser(
        description="Loader idempotente Laudus→Odoo (E1.5). Default: golden slice."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--db", required=True)
    parser.add_argument("--login", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--ledger", default=DEFAULT_GOLDEN)
    args = parser.parse_args(argv)

    if not os.path.exists(args.ledger):
        parser.error(f"--ledger {args.ledger!r} no existe (¿ruta desde la raíz del repo?)")

    table = load_mapping_table()
    moves = run_chain(args.ledger, table)
    # Chart = tabla colapsada + cuentas de ORIGEN SINCERADO que las patas
    # re-ruteadas por E1.3 referencian (review P1).
    chart = build_chart(table) + build_origin_accounts(moves, table)
    partners = build_partners(moves)
    analytic = build_analytic(moves)
    payloads = build_moves(moves, chart)

    client = OdooClient(args.url, args.db, args.login, args.password)
    counts = load_all(client, chart, partners, analytic, payloads)
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
