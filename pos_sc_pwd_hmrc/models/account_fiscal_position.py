from odoo import models, fields


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    footer_text = fields.Char(
        string="Footer Text"
    )
