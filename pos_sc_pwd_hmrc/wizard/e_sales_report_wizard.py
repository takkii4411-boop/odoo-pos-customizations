from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import base64
import io
import datetime
import logging
import pytz
from pytz import timezone, UTC

_logger = logging.getLogger(__name__)

class ESalesReport(models.TransientModel):
    _name = 'e.sales.report.wizard'

    pos_id = fields.Many2one(
        'pos.config',
        string="POS Configuration",
        help="Select the Point of Sale configuration"
    )
    month = fields.Selection(
        selection=[
            ('01', 'January'),
            ('02', 'February'),
            ('03', 'March'),
            ('04', 'April'),
            ('05', 'May'),
            ('06', 'June'),
            ('07', 'July'),
            ('08', 'August'),
            ('09', 'September'),
            ('10', 'October'),
            ('11', 'November'),
            ('12', 'December'),
        ],
        string="Month",
        required=True,
        default=lambda self: datetime.datetime.now().strftime('%m')
    )
    year = fields.Selection(
        selection=[(str(y), str(y)) for y in range(2020, datetime.datetime.now().year + 5)],
        string="Year",
        required=True,
        default=lambda self: str(datetime.datetime.now().year)
    )
    registerID = fields.Boolean(
        string="Include Register ID", 
        default=False
    )
    preview_mode_on = fields.Boolean(
        string="Preview Mode", 
        default=True
    )   
    branchCode = fields.Boolean(
        string="Branch Code", 
        help="Enter the branch code for the report",
        default=False,
    )
    
    def action_generate_report(self):
        pass
    
    def action_preview_report(self):
        pass