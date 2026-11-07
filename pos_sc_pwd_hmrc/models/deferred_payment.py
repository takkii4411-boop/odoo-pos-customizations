from odoo import api, fields, models, _
from datetime import timedelta

class DeferredPayment(models.Model):
    _name = "deferred.payment"
    _description = "Deferred Payment Log"
    _order = "id desc"
    
    name = fields.Char(string='Label', readonly=True)
    pos_order_id = fields.Many2one('pos.order', string='Order', required=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', related='pos_order_id.currency_id')
    amount = fields.Monetary(string='Amount', required=True, currency_field='currency_id', help="Total amount of the payment.")
    payment_method_id = fields.Many2one('pos.payment.method', string='Payment Method', required=True, domain=[('is_deferred_payment', '=', True)])
    due_date = fields.Datetime(string='Due Date', required=True, compute='_compute_due_date', store=True, inverse='_set_due_date')
    currency_rate = fields.Float(string='Conversion Rate', related='pos_order_id.currency_rate', help='Conversion rate from company currency to order currency.')
    partner_id = fields.Many2one('res.partner', string='Customer', related='pos_order_id.partner_id')
    session_id = fields.Many2one('pos.session', string='Session', related='pos_order_id.session_id', store=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', related='pos_order_id.company_id', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('paid', 'Paid'),
        ('canceled', 'Canceled'),
    ], string='Status', default='draft', required=True, readonly=True, help="Status of the deferred payment.")
    
    @api.depends('pos_order_id', 'payment_method_id', 'amount')
    def _compute_due_date(self):
        for record in self:
            if not (record.pos_order_id and record.payment_method_id):
                record.due_date = False
                continue

            payment_days = record.payment_method_id.payment_days or 0
            record.due_date = record.pos_order_id.date_order + timedelta(days=payment_days)

    def _set_due_date(self):
        for record in self:
            if record.due_date:
                payment_days = (record.due_date - record.pos_order_id.date_order).days
                record.payment_method_id.payment_days = payment_days

    def action_create_payments(self):
        self.ensure_one()
        # Update the current deferred payment instead of creating a new one
        self.write({
            'state': 'paid',
            'name': f"DP-{self.id}",  # Optional: Auto label
        })

        # Create the accounting entry
        self._create_accounting_entry()

        # Refresh order to display updated payments

        return {'type': 'ir.actions.act_window_close'}


    def _create_accounting_entry(self):
        # Placeholder for accounting entry creation logic
        pass
    
    def action_cancel_payments(self):
        for record in self:
            if record.state != 'paid':
                continue
            record.state = 'canceled'
        return {'type': 'ir.actions.act_window_close'}