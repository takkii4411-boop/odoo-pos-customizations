from odoo import api, fields, models, _
import logging
_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit='stock.picking'

    invoice_number = fields.Char(string="Sales Invoice Number", readonly=True, copy=False)
    return_order_ref = fields.Char(string="Return Order Ref.", readonly=True, copy=False,)

    @api.model
    def _create_picking_from_pos_order_lines(self, location_dest_id, lines, picking_type, partner=False):
        pickings = super()._create_picking_from_pos_order_lines(location_dest_id, lines, picking_type, partner=False)
        return pickings