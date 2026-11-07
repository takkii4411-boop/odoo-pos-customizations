from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import base64
import io
import datetime
import logging
import pytz
from pytz import timezone, UTC

_logger = logging.getLogger(__name__)


class EJournalWizard(models.TransientModel):
    _name = 'e.journal.wizard'

    pos_id = fields.Many2one(
        'pos.config',
        string="POS Configuration",
        help="Select the Point of Sale configuration"
    )

    def _default_date_from(self):
        """
        Start of current day in user's timezone → converted to naive UTC.
        """
        tz = self.env.user.tz or 'UTC'
        user_tz = timezone(tz)

        now_utc = datetime.datetime.now(UTC)
        now_user = now_utc.astimezone(user_tz)

        start_user = now_user.replace(hour=0, minute=0, second=0, microsecond=0)

        # Convert back to UTC and strip tz info
        start_utc = start_user.astimezone(UTC)
        return start_utc.replace(tzinfo=None)

    def _default_date_to(self):
        """
        End of current day in user's timezone → converted to naive UTC.
        """
        tz = self.env.user.tz or 'UTC'
        user_tz = timezone(tz)

        now_utc = datetime.datetime.now(UTC)
        now_user = now_utc.astimezone(user_tz)

        end_user = now_user.replace(hour=23, minute=59, second=59, microsecond=999999)

        end_utc = end_user.astimezone(UTC)
        return end_utc.replace(tzinfo=None)

    date_from = fields.Datetime(
        string="Start Date",
        required=True,
        default=_default_date_from
    )
    date_to = fields.Datetime(
        string="End Date",
        required=True,
        default=_default_date_to
    )
    registerID = fields.Boolean(
        string="Include Register ID",
        default=True,
        help="Include register ID in the report"
    )
    preview_mode_on = fields.Boolean(
        string="Preview Mode",
        default=True,
        help="Enable preview mode before final generation"
    )
    report_file = fields.Binary(
        string='E-Journal File',
        readonly=True,
    )
    report_file_name = fields.Char(
        string='File Name',
        default='e_journal_report.txt',
    )

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        """Ensure date_to is not earlier than date_from"""
        for record in self:
            if record.date_from and record.date_to:
                if record.date_to < record.date_from:
                    raise ValidationError(
                        _("End Date cannot be earlier than Start Date.")
                    )

    @api.constrains('date_from', 'date_to')
    def _check_date_future(self):
        """Prevent selecting future dates (date only, not time)"""
        for record in self:
            employee_timezone = pytz.timezone(self.env.user.tz or 'UTC')
            now_datetime = fields.Datetime.now().astimezone(employee_timezone)
            if record.date_from and record.date_from.date() > now_datetime.date():
                raise ValidationError(
                    _("Start Date cannot be in the future.")
                )

            if record.date_to and record.date_to.date() > now_datetime.date():
                raise ValidationError(
                    _("End Date cannot be in the future.")
                )

    @api.constrains('date_from', 'date_to')
    def _check_date_range_limit(self):
        """Optional: Limit the date range to prevent performance issues"""
        for record in self:
            if record.date_from and record.date_to:
                delta = record.date_to - record.date_from
                if delta.days > 365:  # Adjust the limit as needed
                    raise ValidationError(
                        _("Date range cannot exceed 365 days.")
                    )

    @api.onchange('date_from')
    def _onchange_date_from(self):
        """Auto-adjust date_to if it becomes invalid"""
        if self.date_from and self.date_to and self.date_to < self.date_from:
            self.date_to = self.date_from

    @api.onchange('pos_id')
    def _onchange_pos_id(self):
        """You can add logic here when POS configuration changes"""
        # Example: Set default dates based on POS session dates
        pass

    @api.model
    def action_preview_report(self):
        """Generate and preview the E-Journal report"""
        self.ensure_one()
        data = {
            'pos_id': self.pos_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'registerID': self.registerID,
            'preview_mode_on': self.preview_mode_on,
        }

        action = self.env.ref('pos_sc_pwd_hmrc.e_journal_report_action').report_action([], data=data)

        # Close the wizard after generating the report
        action.update({'close_on_report_download': True})
        return action



    def get_event_type_display(self, order):
        if not order.is_return_order:
            return 'SALE'
        if order.hmrc_is_void_order:
            return 'VOID'
        if order.hmrc_is_return_order:
            return 'RETURN'

        if order.hmrc_is_refund_order:
            return 'REFUND'
        return ''

    def _generate_sale_line(self, order, event_type, registerID=False):

        order_date = order.date_order.astimezone(
            pytz.timezone(self.env.user.tz or 'UTC')
        ).replace(tzinfo=None)

        formatted_date = order_date.strftime("%m-%d-%Y %H:%M:%S")

        return f"""{order.invoice_number},{order.transaction_number},{(order.original_inv_ref if order.hmrc_is_void_order else (order.original_inv_ref if order.hmrc_is_return_order and order.original_inv_ref != 0 else ''))},{formatted_date}"""

    # old funtion
    # def add_reprint_lines(self, order, lines, registerID=False):
    #     """
    #     Add reprint lines if the order has been reprinted.
    #     """
    #     if order.reprint_ids and len(order.reprint_ids) > 0:
    #         for rec in order.reprint_ids:
    #             lines.append(
    #                 f"REPRINT,{order.invoice_number},{order.return_invoice_number if order.return_invoice_number else ''}{order.void_invoice_number if order.void_invoice_number else ''},{rec.date},{rec.reason},{rec.reprint_by},{order.amount_total},{order.amount_tax},{registerID if registerID else ''}"
    #             )
    #     return lines

    def generate_lines(self, order, registerID=False):
        lines = []
        event_type = self.get_event_type_display(order)
        if event_type == 'SALE':
            lines.append(self._generate_sale_line(order, event_type, registerID=registerID))
        if event_type == 'RETURN':
            lines.append(self._generate_sale_line(order, event_type, registerID=registerID))
        if event_type == 'VOID':
            lines.append(self._generate_sale_line(order, event_type, registerID=registerID))
        if event_type == 'REFUND':
            lines.append(self._generate_sale_line(order, event_type, registerID=registerID))
        return lines

    def _generate_e_journal_content(self, data):
        pos_id = data.get('pos_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        registerID = data.get('registerID')
        min_id = data.get('min_id')
        pos_Serial_no = data.get('pos_Serial_no')

        # Get user timezone
        user_tz = 'UTC'
        # user_tz = self.env.user.tz or 'UTC'
        user_timezone = timezone(user_tz)
        utc_timezone = pytz.UTC

        if date_from:
            date_from_utc = user_timezone.localize(date_from.replace(tzinfo=None)).astimezone(utc_timezone)
        else:
            date_from_utc = fields.Datetime.now()

        if date_to:
            date_to_utc = user_timezone.localize(date_to.replace(tzinfo=None)).astimezone(utc_timezone)
        else:
            date_to_utc = fields.Datetime.now()

        # Build domain
        domain = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('date_order', '>=', date_from_utc),
            ('date_order', '<=', date_to_utc)
        ]

        if pos_id:
            domain.append(('config_id', '=', pos_id))

        # Search orders
        pos_orders = self.env['pos.order'].search(domain, order='date_order asc')

        # generate line-by-line text content
        xxregisterID = registerID and self.pos_id.register_id_char if registerID else False
        _logger.info(f"\n\n\n 101 -----> {xxregisterID=}\n\n\n")
        output = io.StringIO()

        """
        POS SHOP Name, Reg ID, MIN, S/N Number,

        """
        output.write(
            f"""{self.pos_id.name if self.pos_id.name else ''},{self.pos_id.register_id_char if self.pos_id.register_id_char else ''},{min_id if min_id else ''},{pos_Serial_no if pos_Serial_no else ''}\n\n""")
        symbol = '₱'
        # Products
        for order in pos_orders:
            line_text = f"{order.receipt_text} \n"
            output.write(line_text)
            self_lines = self.generate_lines(order, registerID=xxregisterID)
            for line in self_lines:
                output.write(line + '\n\n')
        return output.getvalue()


    def action_generate_report(self):
        """
        Generates the E-Journal content, attaches it to the wizard record,
        and triggers the download action.
        """
        self.ensure_one()

        # 1. Gather data
        data = {
            'pos_id': self.pos_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'registerID': self.registerID,
            'preview_mode_on': self.preview_mode_on,
            'min_id': self.pos_id.x_min_number,
            'pos_Serial_no': self.pos_id.x_serial_number,
            'register_id_char': self.pos_id.register_id_char,
        }

        # 2. Generate content
        content_string = self._generate_e_journal_content(data)

        # 3. Attach file data to the wizard record
        file_data = base64.b64encode(content_string.encode('utf-8'))

        # Agar koi data nahi mila, toh khali file ki jagah ek message likh dete hain
        if not content_string:
            content_string = "No data found for the selected dates."

        employee_timezone = pytz.timezone(self.env.user.tz or 'UTC')
        now_datetime = fields.Datetime.now().astimezone(employee_timezone)
        now_datetime = now_datetime.strftime('%Y%m%d')
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        formatted_date_from = self.date_from.replace(tzinfo=pytz.UTC).astimezone(user_tz).strftime('%m-%d-%Y')
        formatted_date_to = self.date_to.replace(tzinfo=pytz.UTC).astimezone(user_tz).strftime('%m-%d-%Y')

        _logger.info(f"\n\n\n 101 -----> {now_datetime=}\n\n\n")
        file_name = f"{self.pos_id.name or 'POS'}.e_Journal Report {formatted_date_from} To {formatted_date_to}.txt"
        self.write({
            'report_file': file_data,
            'report_file_name': file_name,
        })

        # # 4. Return the action to download the file
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/report_file/{self.report_file_name}?download=true',
            'target': 'self',
        }

    # action_preview_report is not typically used for direct file downloads.
    # If you want a "Preview", it usually means generating a report on screen (QWeb).
    # Since the request is for a text file download, we'll make Preview call Generate for simplicity.
    def action_preview_report(self):
        """In this context, Preview and Generate both lead to file download."""
        return self.action_generate_report()
