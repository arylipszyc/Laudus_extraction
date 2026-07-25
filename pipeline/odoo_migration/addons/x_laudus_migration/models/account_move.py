from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    x_laudus_je_id = fields.Char(
        string="Laudus JE id",
        index=True,
        help="id del asiento Laudus a nivel cabecera. Idempotencia: upsert del move "
        "por external ID mv_<company>_<je_id> (E1.5).",
    )
