from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Los tres van INDEXADOS: el verificador de paridad (E1.6) hace
    # `GROUP BY x_laudus_account_code` sobre ~100k+ líneas × 5 años — es la query
    # más caliente del sistema. Ver winston-arquitectura §4.
    x_laudus_account_code = fields.Char(
        string="Laudus account code",
        index=True,
        help="Código Laudus ORIGINAL de la línea. La cuenta Odoo puede haber "
        "colapsado (569→336) o el sinceramiento haberla movido, pero cada línea "
        "conserva su código de origen: la paridad se verifica agrupando por este campo.",
    )
    x_laudus_je_id = fields.Char(
        string="Laudus JE id (line)",
        index=True,
        help="id del asiento Laudus. Idempotencia del loader (E1.5) + deep-link al origen.",
    )
    x_laudus_entity = fields.Char(
        string="Laudus entity",
        index=True,
        help="Entidad Laudus (EAG/Jocelyn/Jeannette/Johanna/Jael/FFCC/JAB) — "
        "para la paridad y el corte por entidad.",
    )
