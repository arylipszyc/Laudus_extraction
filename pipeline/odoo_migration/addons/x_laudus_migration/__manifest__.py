{
    "name": "Laudus Migration",
    "version": "18.0.1.0.0",
    "summary": "Campos custom de trazabilidad + planes analíticos + diarios + compañías "
    "para la migración Laudus → Odoo (Epic E1).",
    "description": "Estructura receptora de la migración Laudus → Odoo (story E1.1): "
    "campos custom de trazabilidad, 6 planes analíticos (contenedores), un diario por "
    "compañía, y las 2 compañías (EAG / RUT2) sin localización fiscal chilena. No carga datos.",
    "author": "Family Office EAG",
    "depends": ["account", "analytic"],
    "data": [
        "data/analytic_plans.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
