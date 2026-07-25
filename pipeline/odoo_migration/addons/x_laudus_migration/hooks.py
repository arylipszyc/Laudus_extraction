"""post_init_hook: crea las 2 compañías (EAG/RUT2) + un diario por compañía.

Idempotente (buscar antes de crear → re-instalar no duplica). Se hace en Python y
no en XML porque crear compañías sin l10n_cl + fijar la moneda + dar acceso al admin
necesita lógica condicional. Referencia: _spike-odoo/import_to_odoo.py.

l10n_cl: NO se instala. El spike demostró que se pueden crear cuentas/diarios por ORM
sin plantilla de CoA (la contabilidad familiar no declara IVA/renta por Odoo). Si un
módulo futuro exigiera un CoA mínimo, se instalaría l10n_generic_coa y se archivarían
sus cuentas — no hace falta hoy. Ver winston-arquitectura §7.2.
"""

# Diario por compañía (code account.journal: único por compañía, ≤5 chars).
JOURNAL_CODE = {"EAG": "LAU1", "RUT2": "LAU2"}


def post_init_hook(env):
    # Cancelar la auto-carga del CoA genérico (generic_coa) que `account` programa
    # para la compañía principal al finalizar el install (account/models/ir_module.py
    # → _register_hook llama registry._auto_install_template). El diseño quiere las
    # compañías SIN localización/CoA (el plan Laudus-puro lo cargan E1.2/E1.5). Además
    # ese load, vía chart_template._load, BORRA los journals previos de la compañía
    # (incluido nuestro "Diario Laudus") cuando la compañía no tiene contabilidad aún.
    # Nuestro hook corre antes de _register_hook, así que lo desprogramamos acá.
    registry = env.registry
    if hasattr(registry, "_auto_install_template"):
        del registry._auto_install_template

    clp = env.ref("base.CLP")
    if not clp.active:
        clp.active = True

    Company = env["res.company"]
    companies = {}

    # EAG = la compañía principal (renombrada). Idempotente: si ya existe "EAG", se reusa.
    eag = Company.search([("name", "=", "EAG")], limit=1)
    if not eag:
        eag = env.ref("base.main_company")
        eag.name = "EAG"
    eag.currency_id = clp.id
    companies["EAG"] = eag

    rut2 = Company.search([("name", "=", "RUT2")], limit=1)
    if not rut2:
        rut2 = Company.create({"name": "RUT2", "currency_id": clp.id})
    companies["RUT2"] = rut2

    # El admin debe "ver" ambas compañías (multi-company).
    env.ref("base.user_admin").write(
        {"company_ids": [(4, eag.id), (4, rut2.id)]}
    )

    # Un diario "Diario Laudus" (tipo general) por compañía, idempotente.
    Journal = env["account.journal"]
    for name, company in companies.items():
        code = JOURNAL_CODE[name]
        # active_test=False: un diario archivado también cuenta (sin él, el create
        # chocaría con la unique constraint de code por compañía en un reinstall).
        exists = Journal.with_context(active_test=False).search(
            [("code", "=", code), ("company_id", "=", company.id)], limit=1
        )
        if not exists:
            Journal.with_company(company).create(
                {
                    "name": "Diario Laudus",
                    "code": code,
                    "type": "general",
                    "company_id": company.id,
                }
            )
