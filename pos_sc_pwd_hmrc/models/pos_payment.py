from odoo import fields, models, _


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    is_deferred_payment = fields.Boolean(string="Deferred Payment Method", help="Use this payment method for deferred manual collections Log", default=False)
    payment_days = fields.Integer(string="Payment (Days)", help="Number of days after the payment is due.", default=0)
    
    def _is_write_forbidden(self, fields):
        result = super()._is_write_forbidden(fields)
        whitelisted_fields = {'is_deferred_payment', 'payment_days'}
        return bool(fields - whitelisted_fields and self.open_session_ids) and result
