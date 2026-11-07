from odoo import fields, models, api
from datetime import date

class ResPartner(models.Model):

    _inherit = "res.partner"

    is_senior_person = fields.Boolean(string="Senior (PWD) Persons", help="Per-line discounts for Senior Citizens and Persons with Disability (PWD) as required by BIR regulations", default=False)
    @api.model
    def _get_discount_type_selection(self):
        """Fetch discount types from pos.special.discount for dynamic selection field."""
        discount_records = self.env['pos.special.discount'].search([
            ('is_enabled', '=', True)
        ], order='sequence, name')

        selection = [('', 'None')] + [(rec.discount_code, rec.name) for rec in discount_records]
        return selection

    # This field is used as discount type field - dynamic
    senior_pwd_person = fields.Selection(
        string="Discount type",
        selection='_get_discount_type_selection',
    )
    naac_id_no = fields.Char(string="NAAC Id No.")
    sc_id_no = fields.Char(string="SC ID No.")
    pwd_id_no = fields.Char(string="PWD ID No.")
    spic_id_no = fields.Char(string="Solo ID No.")
    medal_id_no = fields.Char(string="Medal of Valor ID No.")
    spic_child_name = fields.Char(string="Name of Child")
    spic_child_birth_date = fields.Date(string="Child’s Birth Date")
    spic_child_age = fields.Integer(string="Child’s Age", compute='_compute_spic_child_age', store=True)
    general_id_no = fields.Char(string="ID Number")

    res_partner_business_style = fields.Char(
        string="Business Style",store=True )

    special_discount_id = fields.Many2one(
        comodel_name='pos.special.discount',
        string='Special Discount',
        help='Select a special discount to auto-fill the discount code',
        ondelete='set null',
    )

    discount_code = fields.Char(
        string='Discount Code',
        help='Auto-filled from the selected Special Discount',
        readonly=True,
        store=True,
        compute='_compute_partner_discount_code',
    )

    @api.depends('special_discount_id', 'special_discount_id.discount_code_on_receipt')
    def _compute_partner_discount_code(self):
        for partner in self:
            if partner.special_discount_id:
                partner.discount_code = partner.special_discount_id.discount_code_on_receipt
            else:
                partner.discount_code = False

    @api.depends('spic_child_birth_date')
    def _compute_spic_child_age(self):
        today = date.today()
        for partner in self:
            if partner.spic_child_birth_date:
                birth = partner.spic_child_birth_date
                age = today.year - birth.year
                if (today.month, today.day) < (birth.month, birth.day):
                    age -= 1
                partner.spic_child_age = age
            else:
                partner.spic_child_age = 0

    @api.onchange('senior_pwd_person')
    def _onchange_senior_pwd_person(self):
        self.naac_id_no = ''
        self.general_id_no = ''
        self.sc_id_no = ''
        self.pwd_id_no = ''
        self.spic_id_no = ''
        self.medal_id_no = ''
        self.spic_child_name = ''
        self.spic_child_birth_date = False
        self.spic_child_age = 0