from odoo import models, fields,api

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    allowed_discount_types = fields.Selection([
        ('pwd', 'PWD'),
        ('senior', 'Senior Citizen'),
        ('naac', 'NAAC'),
        ('medal', 'MV'),
        ('spic', 'Solo Parent'),
    ], string="Allowed Discount Type")

    # Dynamic discount support - NEW FIELD
    supported_discount_ids = fields.Many2many(
        'pos.special.discount',
        'product_template_pos_special_discount_rel',
        'product_template_id',
        'discount_id',
        string='Supported Discounts',
        domain=[('is_enabled', '=', True)],
        help='Select which special discounts can be applied to this product'
    )

    supported_discount_codes = fields.Char(
        string='Supported Discount Codes',
        compute='_compute_supported_discount_codes',
        store=True,
        help='Comma-separated list of discount codes for quick POS lookup'
    )

    @api.depends('supported_discount_ids')
    def _compute_supported_discount_codes(self):
        for product in self:
            codes = set()
            # Add from new dynamic field
            for discount in product.supported_discount_ids:
                codes.add(discount.discount_code)
            # Legacy fields commented out - now only using Many2many
            product.supported_discount_codes = ','.join(codes) if codes else ''


class ProductProduct(models.Model):
    _inherit = 'product.product'

    allowed_discount_types = fields.Selection(
        related='product_tmpl_id.allowed_discount_types',
        store=False,
    )


    supported_discount_ids = fields.Many2many(
        related='product_tmpl_id.supported_discount_ids',
        store=False
    )
    supported_discount_codes = fields.Char(
        related='product_tmpl_id.supported_discount_codes',
        store=False
    )
