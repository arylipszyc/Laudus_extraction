# Corre DENTRO del odoo shell (env disponible como superusuario).
# Lee los CSV montados en /mnt/csv y crea companies, cuentas, diario y asientos.
import csv

CFG = [
    # (company_name, accounts_csv, moves_csv, journal_code)
    ("EAG",  "/mnt/csv/accounts_EAG.csv",  "/mnt/csv/moves_EAG_2026-05.csv",  "LAU1"),
    ("RUT2", "/mnt/csv/accounts_RUT2.csv", "/mnt/csv/moves_RUT2_2026-05.csv", "LAU2"),
]

Account = env["account.account"]
Journal = env["account.journal"]
Move = env["account.move"]
Company = env["res.company"]
clp = env.ref("base.CLP")
usd = env.ref("base.USD")

# --- companies: renombra la default (id 1) a EAG, crea RUT2 ---
comp = {}
c1 = Company.browse(1)
c1.name = "EAG"
comp["EAG"] = c1
rut2 = Company.search([("name", "=", "RUT2")], limit=1)
if not rut2:
    rut2 = Company.create({"name": "RUT2", "currency_id": clp.id})
comp["RUT2"] = rut2
# el superusuario debe "ver" ambas companies
env.user.write({"company_ids": [(6, 0, [comp["EAG"].id, comp["RUT2"].id])]})
env.cr.commit()

for cname, acc_csv, mov_csv, jcode in CFG:
    cid = comp[cname].id
    print(f"\n==== {cname} (company id {cid}) ====")

    # --- cuentas ---
    code2id = {}
    with open(acc_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        vals = {
            "code": r["code"],
            "name": r["name"][:255],
            "account_type": r["account_type"],
            "company_ids": [(6, 0, [cid])],
        }
        if r["currency"] == "USD":
            vals["currency_id"] = usd.id
        acc = Account.with_company(cid).create(vals)
        code2id[r["code"]] = acc.id
    print(f"cuentas creadas: {len(code2id)}")

    # --- diario ---
    journal = Journal.with_company(cid).create({
        "name": "Diario Laudus", "code": jcode, "type": "general", "company_id": cid,
    })

    # --- asientos (formato o2m: fila con id = cabecera; filas con id vacio = patas) ---
    with open(mov_csv, encoding="utf-8") as f:
        mrows = list(csv.DictReader(f))
    moves = []
    cur = None
    for r in mrows:
        if r["id"]:  # nueva cabecera
            if cur:
                moves.append(cur)
            cur = {"ref": r["ref"], "date": r["date"], "lines": []}
        code = r["line_ids/account_id/id"].split("_", 2)[2]  # acc_EAG_111005 -> 111005
        cur["lines"].append({
            "account_id": code2id[code],
            "name": r["line_ids/name"][:200] or r["ref"],
            "debit": float(r["line_ids/debit"]),
            "credit": float(r["line_ids/credit"]),
        })
    if cur:
        moves.append(cur)

    created = env["account.move"]
    for m in moves:
        mv = Move.with_company(cid).create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": m["date"],
            "ref": m["ref"],
            "line_ids": [(0, 0, ln) for ln in m["lines"]],
        })
        created |= mv
    created.action_post()
    print(f"asientos creados y posteados: {len(created)}")

    # --- validacion: total gastos del mes (cuentas expense) ---
    exp_ids = Account.search([("account_type", "=", "expense"), ("company_ids", "in", cid)]).ids
    env.cr.execute("""
        SELECT COALESCE(SUM(l.debit - l.credit), 0)
        FROM account_move_line l
        WHERE l.company_id = %s AND l.account_id = ANY(%s)
    """, (cid, exp_ids))
    total_gastos = env.cr.fetchone()[0]
    print(f"TOTAL GASTOS {cname} 2026-05 = {total_gastos:,.0f} CLP")

env.cr.commit()
print("\nOK commit")
