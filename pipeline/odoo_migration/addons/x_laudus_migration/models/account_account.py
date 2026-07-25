from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    # SIN índice: es contexto (path categoria1/2/3 de Laudus), no llave de paridad.
    x_laudus_group = fields.Char(
        string="Laudus group",
        help="Path categoria1/2/3 de Laudus (contexto para reportería, no paridad).",
    )
