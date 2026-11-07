# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class PosSpecialDiscount(models.Model):
    _name = 'pos.special.discount'
    _description = 'POS Special Discount Configuration'
    _order = 'sequence, name'

    # Basic Info
    name = fields.Char(
        string='Discount Name',
        required=True,
        help='Full name of the discount (e.g., "Senior Citizen Discount")'
    )

    discount_code = fields.Char(
        string='Discount Code',
        required=True,
        help='Unique code identifier (e.g., "senior", "pwd", "naac")'
    )

    discount_code_on_receipt = fields.Char(
        string='Discount Code On Receipt'
    )

    button_name = fields.Char(
        string='Button Name',
        required=True,
        help='Short name displayed on POS button (e.g., "SC", "PWD")'
    )

    # Discount Configuration
    discount_rate = fields.Float(
        string='Discount Rate (%)',
        required=True,
        help='Fixed discount percentage (e.g., 20 for 20%, 5 for 5%)'
    )

    fiscal_position_id = fields.Many2one(
        'account.fiscal.position',
        string='Fiscal Position',
        help='Fiscal position determines VAT treatment (Exempt/Zero-Rated/Neither)'
    )

    vat_treatment = fields.Selection([
        ('vat_inclusive_reapply', 'VAT Inclusive with Reapplication'),
        ('vat_inclusive', 'VAT Inclusive'),
        ('vat_exempt', 'VAT Exempt'),
        ('zero_rated', 'Zero Rated')
    ], string='VAT Treatment', required=True, default='vat_exempt',
       help='VAT Inclusive with Reapplication: Remove VAT → Discount → Reapply VAT on original price (BNPC 5%%, NAAC 20%%)\n'
            'VAT Exempt: Remove VAT → Discount → No VAT (SC 20%%, PWD 20%%, Solo Parent 10%%, Medal of Valor 20%%)\n'
            'Zero Rated: Remove VAT only, no discount (Diplomat/Foreign Mission)')

    on_line_text = fields.Char(
        string='On Product Line Text',
        required=True,
        help='Text displayed on receipt line (e.g., "Less 20% SC Discount")'
    )

    primary_codes = fields.Char(
        string='Primary Discount Codes',
        help='Comma-separated codes that can use this discount (e.g., "senior,pwd" for BNPC)'
    )

    # Control
    is_enabled = fields.Boolean(
        string='Enabled',
        default=True,
        help='Enable/disable this discount in POS'
    )

    is_default_discount = fields.Boolean(
        string='Is Default Discount',
        default=False,
        help='Mark as default discount type'
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Display order in POS'
    )

    # Metadata
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    # Constraints
    _sql_constraints = [
        ('discount_code_unique', 'UNIQUE(discount_code, company_id)',
         'Discount code must be unique per company!'),
    ]

    @api.constrains('discount_rate')
    def _check_discount_rate(self):
        for record in self:
            if record.discount_rate < 0 or record.discount_rate > 100:
                raise ValidationError(_('Discount rate must be between 0 and 100'))

    @api.constrains('discount_code')
    def _check_discount_code(self):
        for record in self:
            if not record.discount_code or ' ' in record.discount_code:
                raise ValidationError(_('Discount code cannot contain spaces'))
