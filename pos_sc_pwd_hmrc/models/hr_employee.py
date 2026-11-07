from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    employee_db_id = fields.Integer(
        string='Employee ID',
        compute='_compute_employee_db_id',
        store=False,
    )

    def _compute_employee_db_id(self):
        for rec in self:
            rec.employee_db_id = rec._origin.id or rec.id